from __future__ import annotations

import asyncio
import contextlib
import importlib
import sys
from typing import Annotated, Any, Dict, List, Coroutine, Sequence, Type

from sayer import Option, command, info, success
from anyio.abc import TaskGroup, CancelScope

from asyncz.cli.loader import load_jobs_from_config, load_jobs_from_module
from asyncz.cli.utils import (
    _call_hook,
    build_executors_map,
    build_stores_map,
    changed,
    collect_watch_targets,
    ensure_loop,
    maybe_await,
    WatchTarget,
)
from asyncz.exceptions import SchedulerAlreadyRunningError
from asyncz.schedulers import AsyncIOScheduler
from uvicorn.config import Config as UvicornConfig


@command
def start(
    module: Annotated[
        str | None, Option(None, help="Python path to a registry (e.g. pkg.jobs:registry)")
    ],
    config: Annotated[str | None, Option(None, help="YAML/JSON jobs file")],
    timezone: Annotated[str | None, Option(None, help="Timezone (e.g. Europe/Zurich)")],
    standalone: Annotated[bool, Option(False, help="Run until Ctrl+C")],
    store: Annotated[list[str], Option([], "--store", help="Store spec alias=value. Repeatable.")],
    executor: Annotated[
        list[str], Option([], "--executor", help="Executor spec alias=type[:workers]. Repeatable.")
    ],
    on_start: Annotated[
        str | None, Option(None, help="Dotted hook callable run after scheduler start")
    ],
    on_stop: Annotated[
        str | None, Option(None, help="Dotted hook callable run before scheduler shutdown")
    ],
    watch: Annotated[bool, Option(False, help="Hot-reload on file changes (module/config)")],
    watch_interval: Annotated[float, Option(1.0, help="Polling seconds for --watch")],
) -> None:
    """
    Start an AsyncIOScheduler with configurable stores/executors, optional hooks, and hot reload.

    This command loads jobs from a module or config file, initializes the scheduler,
    runs the on_start hook, and enters a run loop that handles hot-reloading or
    waits for shutdown signals.
    """
    loop: asyncio.AbstractEventLoop = ensure_loop()

    async def boot_once() -> AsyncIOScheduler:
        """
        Configures, loads jobs into, and starts a fresh scheduler instance.

        Returns:
            The fully initialized and started `AsyncIOScheduler`.
        """
        cfg: dict[str, Any] = {}
        if timezone:
            cfg["timezone"] = timezone
        if store:
            cfg["stores"] = build_stores_map(store)
        if executor:
            cfg["executors"] = build_executors_map(executor)

        sched: AsyncIOScheduler = AsyncIOScheduler(**cfg)

        # Load jobs BEFORE starting the scheduler
        if module:
            await maybe_await(load_jobs_from_module(sched, module))
        elif config:
            await maybe_await(load_jobs_from_config(sched, config))

        # Start the scheduler (suppressing error if already running during a hot reload cycle)
        with contextlib.suppress(SchedulerAlreadyRunningError):
            await maybe_await(sched.start())

        await maybe_await(_call_hook(on_start))
        success("Scheduler started.")
        return sched

    async def run_forever() -> None:
        """
        The main asynchronous loop that orchestrates scheduling, watching, and reloading.
        """
        sched: AsyncIOScheduler = await boot_once()

        # Determine watch targets if hot-reloading is enabled
        targets: list[WatchTarget] = collect_watch_targets(module, config) if watch else []

        # Quick exit if not running in standalone/watch mode
        if not watch and not standalone:
            await maybe_await(_call_hook(on_stop))
            await maybe_await(sched.shutdown(wait=True))
            return  # quick lifecycle: start -> stop -> exit

        try:
            while True:
                if watch and changed(targets):
                    info("Change detected, reloading...")

                    # 1. Graceful shutdown of old scheduler and hooks
                    await maybe_await(_call_hook(on_stop))
                    await maybe_await(sched.shutdown(wait=True))

                    # 2. Reload module if necessary (crucial for re-registering tasks)
                    if module:
                        mod_name: str = module.partition(":")[0]
                        if mod_name in sys.modules:
                            importlib.reload(sys.modules[mod_name])

                    # 3. Boot new scheduler instance
                    sched = await boot_once()

                # Sleep interval for polling/waiting
                await asyncio.sleep(watch_interval)

        except (KeyboardInterrupt, asyncio.CancelledError):
            # Exit loop gracefully on standard interrupt signals
            pass

        finally:
            # Final shutdown and cleanup
            await maybe_await(_call_hook(on_stop))
            await maybe_await(sched.shutdown(wait=True))

    loop.run_until_complete(run_forever())
