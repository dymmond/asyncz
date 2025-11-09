from __future__ import annotations

import importlib
from typing import Any

from asyncz.schedulers import AsyncIOScheduler

BOOTSTRAP_CACHE: dict[str, AsyncIOScheduler] = {}


def import_protocol(path: str) -> Any:
    """
    Dynamically imports a class, function, or object instance from a dotted path string.

    The path must be in the format 'package.module:AttrName'.

    Args:
        path: The dotted path string.

    Returns:
        The imported attribute (class, function, or object).

    Raises:
        ValueError: If the path is not in the required 'pkg.mod:AttrName' format.
        ValueError: If the attribute is not found in the specified module.
    """
    if ":" not in path:
        raise ValueError("Bootstrap must be in 'pkg.mod:AttrName' form")

    mod_path: str
    attr: str
    mod_path, attr = path.split(":", 1)

    module: Any = importlib.import_module(mod_path)

    try:
        return getattr(module, attr)
    except AttributeError as e:
        raise ValueError(f"'{attr}' not found in '{mod_path}'") from e


def load_bootstrap_scheduler(path: str) -> AsyncIOScheduler:
    """
    Dynamically loads the active `AsyncIOScheduler` instance from a specified import path.

    This function supports three common patterns for exposing the scheduler instance:
    1. **Class Path (Convention):** Imports a class, instantiates it with zero arguments,
       and calls its `get_scheduler()` method. (Assumes class implements `AsynczClientProtocol`).
    2. **Object Path:** Imports an existing object instance that has a callable `get_scheduler()` method.
    3. **Callable Path:** Imports a function that, when called, returns the scheduler instance directly.

    Args:
        path: The dotted path string pointing to the class, object, or callable.

    Returns:
        The active `AsyncIOScheduler` instance.

    Raises:
        TypeError: If the resolved target does not match one of the supported patterns
                   or if the final result is not an `AsyncIOScheduler`.
    """
    if path in BOOTSTRAP_CACHE:
        return BOOTSTRAP_CACHE[path]

    obj: Any = import_protocol(path)

    # 1. Class with get_scheduler() (e.g., BootstrapApp)
    if isinstance(obj, type):
        instance: Any = obj()  # zero-arg constructor by convention
        if hasattr(instance, "get_scheduler") and callable(instance.get_scheduler):
            scheduler: AsyncIOScheduler = instance.get_scheduler()
            assert_scheduler(scheduler)
            BOOTSTRAP_CACHE[path] = scheduler
            return scheduler

    # 2. Object with get_scheduler() (e.g., a globally instantiated manager)
    if hasattr(obj, "get_scheduler") and callable(obj.get_scheduler):
        scheduler = obj.get_scheduler()
        assert_scheduler(scheduler)
        BOOTSTRAP_CACHE[path] = scheduler
        return scheduler

    # 3. Callable returning a scheduler (e.g., `get_global_scheduler`)
    if callable(obj):
        scheduler = obj()
        assert_scheduler(scheduler)
        BOOTSTRAP_CACHE[path] = scheduler
        return scheduler

    raise TypeError(
        "Bootstrap target must be a class/object with 'get_scheduler()' or a callable returning AsyncIOScheduler."
    )


def assert_scheduler(scheduler: Any) -> None:
    """
    Internal helper to validate that the result of the bootstrap process is an
    `AsyncIOScheduler` instance.

    Args:
        scheduler: The object returned by the bootstrap protocol.

    Raises:
        TypeError: If the object is not an instance of `AsyncIOScheduler`.
    """
    if not isinstance(scheduler, AsyncIOScheduler):
        raise TypeError("Bootstrap did not return an AsyncIOScheduler instance.")


def clear_bootstrap_cache() -> None:
    """
    Clears the internal cache used for storing dynamically loaded scheduler bootstrap targets.

    This function is necessary, particularly in testing or development environments (e.g., hot-reloading),
    to ensure that the application reloads the scheduler instance from its source path
    and doesn't rely on a stale, previously cached reference.
    """
    # Assuming BOOTSTRAP_CACHE is callable and has a standard `.clear()` method
    # (e.g., it is a dictionary or a cache object from functools or similar library).
    BOOTSTRAP_CACHE.clear()
