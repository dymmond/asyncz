from __future__ import annotations

import asyncio
import contextlib
import importlib
import sys
from typing import Annotated, Any

from sayer import Option, command, info, success

from asyncz.cli.bootstrap_loader import load_bootstrap_scheduler
from asyncz.cli.loader import load_jobs_from_config, load_jobs_from_module
from asyncz.cli.utils import (
    WatchTarget,
    _call_hook,
    build_executors_map,
    build_stores_map,
    changed,
    collect_watch_targets,
    ensure_loop,
    maybe_await,
)
from asyncz.exceptions import SchedulerAlreadyRunningError
from asyncz.schedulers import AsyncIOScheduler


@command
def start(
    bootstrap: Annotated[
        str | None,
        Option(
            None,
            help="Dotted path to a class with get_scheduler(), e.g. 'ravyn.contrib.asyncz:AsynczSpec'",
        ),
    ],
    module: Annotated[
        str | None,
        Option(None, help="Python path to a registry (e.g. pkg.jobs:registry)"),
    ],
    config: Annotated[str | None, Option(None, help="YAML/JSON jobs file")],
    timezone: Annotated[str | None, Option(None, help="Timezone (e.g. Europe/Zurich)")],
    standalone: Annotated[bool, Option(False, help="Run until Ctrl+C")],
    store: Annotated[list[str], Option([], "--store", help="Store spec alias=value. Repeatable.")],
    executor: Annotated[
        list[str],
        Option([], "--executor", help="Executor spec alias=type[:workers]. Repeatable."),
    ],
    on_start: Annotated[
        str | None, Option(None, help="Dotted hook callable run after scheduler start")
    ],
    on_stop: Annotated[
        str | None,
        Option(None, help="Dotted hook callable run before scheduler shutdown"),
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
        if bootstrap:
            if any([module, config, timezone, store, executor, on_start, watch]):
                info(
                    "Using --bootstrap; ignoring --module/--config/--timezone/--store/--executor/--on-start/--watch."
                )
            scheduler: AsyncIOScheduler = load_bootstrap_scheduler(bootstrap)

            # The bootstrap owns configuration; just start it if needed.
            with contextlib.suppress(SchedulerAlreadyRunningError):
                await maybe_await(scheduler.start())
            success("Scheduler started via bootstrap.")
            return scheduler

        # If no bootstrap is provided

        cfg: dict[str, Any] = {}
        if timezone:
            cfg["timezone"] = timezone
        if store:
            cfg["stores"] = build_stores_map(store)
        if executor:
            cfg["executors"] = build_executors_map(executor)

        scheduler = AsyncIOScheduler(**cfg)

        # Load jobs BEFORE starting the scheduler
        if module:
            await maybe_await(load_jobs_from_module(scheduler, module))
        elif config:
            await maybe_await(load_jobs_from_config(scheduler, config))

        # Start the scheduler (suppressing error if already running during a hot reload cycle)
        with contextlib.suppress(SchedulerAlreadyRunningError):
            await maybe_await(scheduler.start())

        await maybe_await(_call_hook(on_start))
        success("Scheduler started.")
        return scheduler

    async def run_forever() -> None:
        """
        The main asynchronous loop that orchestrates scheduling, watching, and reloading.
        """
        scheduler: AsyncIOScheduler = await boot_once()

        # Determine watch targets if hot-reloading is enabled
        targets: list[WatchTarget] = collect_watch_targets(module, config) if watch else []

        # Quick exit if not running in standalone/watch mode
        if not watch and not standalone:
            await maybe_await(_call_hook(on_stop))
            await maybe_await(scheduler.shutdown(wait=True))
            return

        try:
            while True:
                if watch and changed(targets):
                    info("Change detected, reloading...")

                    # 1. Graceful shutdown of old scheduler and hooks
                    await maybe_await(_call_hook(on_stop))
                    await maybe_await(scheduler.shutdown(wait=True))

                    # 2. Reload module if necessary (crucial for re-registering tasks)
                    if module:
                        mod_name: str = module.partition(":")[0]
                        if mod_name in sys.modules:
                            importlib.reload(sys.modules[mod_name])

                    # 3. Boot new scheduler instance
                    scheduler = await boot_once()

                # Sleep interval for polling/waiting
                await asyncio.sleep(watch_interval)

        except (KeyboardInterrupt, asyncio.CancelledError):
            # Exit loop gracefully on standard interrupt signals
            pass

        finally:
            # Final shutdown and cleanup
            await maybe_await(_call_hook(on_stop))
            await maybe_await(scheduler.shutdown(wait=True))

    loop.run_until_complete(run_forever())
