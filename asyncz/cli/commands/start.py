from __future__ import annotations

import asyncio
import contextlib
import importlib
import sys
from typing import Annotated, Any

from sayer import Option, command, info, success

from asyncz.cli.loader import load_jobs_from_config, load_jobs_from_module
from asyncz.cli.utils import (
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
):
    """Start an AsyncIOScheduler with configurable stores/executors, optional hooks, and hot reload."""
    loop = ensure_loop()

    async def boot_once() -> AsyncIOScheduler:
        cfg: dict[str, Any] = {}
        if timezone:
            cfg["timezone"] = timezone
        if store:
            cfg["stores"] = build_stores_map(store)
        if executor:
            cfg["executors"] = build_executors_map(executor)

        sched = AsyncIOScheduler(**cfg)

        # Load jobs BEFORE start so misconfig fails fast
        if module:
            await maybe_await(load_jobs_from_module(sched, module))
        elif config:
            await maybe_await(load_jobs_from_config(sched, config))

        with contextlib.suppress(SchedulerAlreadyRunningError):
            await maybe_await(sched.start())

        await maybe_await(_call_hook(on_start))
        success("Scheduler started.")
        return sched

    async def run_forever():
        sched = await boot_once()
        if not watch and not standalone:
            await maybe_await(_call_hook(on_stop))
            await maybe_await(sched.shutdown(wait=True))
            return  # quick lifecycle: start -> stop -> exit

        targets = collect_watch_targets(module, config) if watch else []
        try:
            while True:
                if watch and changed(targets):
                    info("Change detected, reloading...")
                    await maybe_await(_call_hook(on_stop))
                    await maybe_await(sched.shutdown(wait=True))
                    if module:
                        mod_name, _, _ = module.partition(":")
                        if mod_name in sys.modules:
                            importlib.reload(sys.modules[mod_name])
                    sched = await boot_once()

                await asyncio.sleep(watch_interval)
        except (KeyboardInterrupt, asyncio.CancelledError):
            pass
        finally:
            await maybe_await(_call_hook(on_stop))
            await maybe_await(sched.shutdown(wait=True))

    loop.run_until_complete(run_forever())
