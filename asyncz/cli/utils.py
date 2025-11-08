import asyncio
import importlib
import inspect
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from asyncz.cli._parsers import parse_store_option


async def maybe_await(value: Any) -> Any:
    """
    Awaits the provided value only if it is awaitable (e.g., a coroutine, Future, or Task).

    Args:
        value: The value to potentially await.

    Returns:
        The result of the awaitable, or the original value if it was not awaitable.
    """
    return await value if inspect.isawaitable(value) else value


async def _call_hook(path: str | None) -> None:
    """
    Imports and executes a synchronous or asynchronous hook function specified by a dotted path.
    Awaits the function's result if it is a coroutine.

    Args:
        path: The dotted path to the hook callable (e.g., 'pkg.mod:func').
    """
    if not path:
        return
    fn: Callable[..., Any] = import_callable(path)
    maybe_coro: Any = fn()
    await maybe_await(maybe_coro)


def ensure_loop() -> asyncio.AbstractEventLoop:
    """
    Retrieves the currently running event loop. If no loop is running in the current
    thread, it creates a new event loop and sets it as the current one.

    Returns:
        The active or newly created `asyncio.AbstractEventLoop`.
    """
    try:
        return asyncio.get_running_loop()
    except RuntimeError:
        loop: asyncio.AbstractEventLoop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        return loop


def import_callable(path: str) -> Callable[..., Any]:
    """
    Dynamically imports and returns a callable object from a dotted path string.

    The path must be in the format 'package.module:callable_name'.

    Args:
        path: The dotted path string.

    Returns:
        The imported callable object (function, class, etc.).

    Raises:
        ValueError: If the path does not contain the required ':callable_name' separator.
        ImportError: If the module cannot be found.
        AttributeError: If the callable name is not found in the module.
    """
    mod_name: str
    attr: str
    mod_name, _, attr = path.partition(":")
    if not attr:
        raise ValueError(f"Expected dotted path 'pkg.mod:callable', got '{path}'")

    mod: Any = importlib.import_module(mod_name)
    return cast(Callable[..., Any], getattr(mod, attr))


def parse_executor(spec: str) -> tuple[str, dict[str, Any]]:
    """
    Parses an executor specification string into an alias and a configuration dictionary.

    Format: `alias=type[:workers]`
    Examples: `default=asyncio`, `io=thread`, `cpu=process:4`

    Args:
        spec: The executor specification string.

    Returns:
        A tuple: (alias, config_dict). Config dict includes 'type' and optionally 'max_workers'.

    Raises:
        ValueError: If the specification format is invalid.
    """
    alias: str
    right: str
    alias, _, right = spec.partition("=")

    if not _:
        raise ValueError("Executor must be 'alias=type' (optionally ':workers').")

    typ: str
    workers: str
    typ, _, workers = right.partition(":")
    typ = typ.strip().lower()

    cfg: dict[str, Any] = {"type": typ}

    if workers:
        try:
            cfg["max_workers"] = int(workers)
        except ValueError:
            raise ValueError(
                f"Executor worker count must be an integer, got '{workers}'."
            ) from None

    return alias.strip(), cfg


def parse_store(spec: str) -> tuple[str, dict[str, Any]]:
    """
    Parses a store specification string into an alias and a configuration dictionary.

    Format: `alias=value` where value is 'memory' or a URL.
    Examples: `default=memory`, `durable=sqlite:///asyncz.db`, `cache=redis://...`

    Args:
        spec: The store specification string.

    Returns:
        A tuple: (alias, config_dict). Config dict includes 'type' and backend-specific details.

    Raises:
        ValueError: If the specification format is invalid.
    """
    alias: str
    value: str
    alias, _, value = spec.partition("=")

    if not _:
        raise ValueError("Store must be 'alias=value' (value can be 'memory' or a URL).")

    alias = alias.strip()
    value = value.strip()

    if value == "memory":
        return alias, {"type": "memory"}

    if value.startswith("file://"):
        return alias, {"type": "file", "path": value.removeprefix("file://")}

    if value.startswith("redis://"):
        return alias, {"type": "redis", "url": value}

    if value.startswith("mongo://") or value.startswith("mongodb://"):
        return alias, {"type": "mongo", "url": value}

    # fallback to sqlalchemy for anything else that looks like a DB URL
    return alias, {"type": "sqlalchemy", "database": value}


def build_executors_map(executors: list[str]) -> dict[str, dict[str, Any]]:
    """
    Translates a list of CLI executor specification strings into the final
    Asyncz scheduler 'executors' configuration map, ready for instantiation.

    Args:
        executors: A list of executor specifications (e.g., ['default=asyncio', 'cpu=process:4']).

    Returns:
        A dictionary mapping executor aliases to their full configuration, including the `class` path.

    Raises:
        ValueError: If an unknown executor type is specified.
    """
    out: dict[str, dict[str, Any]] = {}
    for spec in executors:
        alias: str
        cfg: dict[str, Any]
        alias, cfg = parse_executor(spec)
        etype: str = cfg.pop("type")

        # Map simple type alias to the full class path
        if etype == "asyncio":
            out[alias] = {"class": "asyncz.executors.asyncio:AsyncIOExecutor", **cfg}
        elif etype in ("thread", "threads", "pool"):
            out[alias] = {"class": "asyncz.executors.pool:ThreadPoolExecutor", **cfg}
        elif etype in ("process", "proc", "processpool"):
            out[alias] = {"class": "asyncz.executors.process_pool:ProcessPoolExecutor", **cfg}
        elif etype == "debug":
            out[alias] = {"class": "asyncz.executors.debug:DebugExecutor", **cfg}
        else:
            raise ValueError(f"Unknown executor type: {etype}")

    return out


def build_stores_map(specs: list[str]) -> dict[str, dict[str, Any]]:
    """
    Builds the AsyncIOScheduler 'stores' configuration map from parsed store specifications.

    If the input list is empty, it defaults to a single 'default=memory' store.

    Args:
        specs: A list of store specifications (or parse results from `parse_store_option`).

    Returns:
        A dictionary mapping store aliases to their configuration dictionary.

    Raises:
        ValueError: If the input parse result format is unexpected.
    """
    if not specs:
        return {"default": {"type": "memory"}}

    stores: dict[str, dict[str, Any]] = {}
    for i, spec in enumerate(specs):
        parsed: tuple[str | Any, ...] = parse_store_option(spec)

        if not isinstance(parsed, tuple):
            raise ValueError(f"Unexpected parse_store_option() result type: {type(parsed)!r}")

        plugin: str
        kwargs: dict[str, Any]
        alias_hint: str | None

        if len(parsed) == 3:
            plugin, kwargs, alias_hint = parsed
        elif len(parsed) == 2:
            plugin, kwargs = parsed
            alias_hint = None
        else:
            raise ValueError(f"Unexpected parse_store_option() result: {parsed!r}")

        # Determine the alias: use hint, or 'default' for the first store, or the plugin type
        alias: str = alias_hint or ("default" if i == 0 else plugin)

        stores[alias] = {"type": plugin, **kwargs}

    return stores


@dataclass
class WatchTarget:
    """Represents a file or module path to monitor for modifications."""

    path: Path
    """The resolved file system path of the target."""
    mtime: float
    """The last modification time (mtime) of the file when last checked."""


def collect_watch_targets(module_path: str | None, config_path: str | None) -> list[WatchTarget]:
    """
    Collects file paths for modules and configuration files that should be watched
    for changes (e.g., in --reload mode).

    Args:
        module_path: The dotted path to the main module containing tasks (e.g., 'pkg.mod:callable').
        config_path: The path to the scheduler configuration file.

    Returns:
        A list of `WatchTarget` objects with their initial modification times.
    """
    targets: list[WatchTarget] = []
    if config_path:
        p: Path = Path(config_path).resolve()
        if p.exists():
            targets.append(WatchTarget(p, p.stat().st_mtime))

    if module_path:
        mod_name: str
        mod_name, _, _ = module_path.partition(":")
        try:
            mod: Any = importlib.import_module(mod_name)
            # Find the actual file path of the module
            file: Path = Path(mod.__file__).resolve()
            if file.exists():
                targets.append(WatchTarget(file, file.stat().st_mtime))
        except Exception:
            # Silently ignore modules that cannot be imported or don't resolve to a file
            pass

    return targets


def changed(targets: list[WatchTarget]) -> bool:
    """
    Checks if the modification time of any watched file has changed since the last check.

    If a file is found to be modified, its `mtime` is updated in the target list.
    If a file is missing, it is considered changed/deleted.

    Args:
        targets: The list of `WatchTarget` objects.

    Returns:
        True if any target file has been modified or deleted, False otherwise.
    """
    changed_status: bool = False
    for t in targets:
        try:
            m: float = t.path.stat().st_mtime
            if m != t.mtime:
                changed_status = True
                t.mtime = m  # Update mtime for the next check
        except FileNotFoundError:
            changed_status = True

    return changed_status
