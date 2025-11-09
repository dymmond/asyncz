from __future__ import annotations

import asyncio
import contextlib
from datetime import datetime
from typing import Annotated, Any

from sayer import Argument, Option, command, info, success

from asyncz.cli.bootstrap_loader import load_bootstrap_scheduler
from asyncz.cli.utils import build_stores_map, ensure_loop, maybe_await
from asyncz.schedulers import AsyncIOScheduler
from asyncz.stores.base import BaseStore
from asyncz.tasks import Task as AsynczTask


@command
def resume(
    job_id: Annotated[str, Argument(help="Job ID")],
    bootstrap: Annotated[
        str | None,
        Option(
            None,
            help="Dotted path to a class with get_scheduler(), e.g. 'ravyn.contrib.asyncz:AsynczSpec'",
        ),
    ],
    store: Annotated[list[str], Option([], "--store", help="Store spec alias=value. Repeatable.")],
) -> None:
    """
    Resume a paused job by ID.

    This command initializes a temporary scheduler instance, connects to the specified job store,
    and instructs the store to reactivate the execution schedule for the specified job ID.

    Examples:
        asyncz resume <job_id>
        asyncz resume <job_id> --store durable=sqlite:///scheduler.db
    """
    loop: asyncio.AbstractEventLoop = ensure_loop()

    async def main() -> None:
        """Core async logic for resuming a job and recalculating its next run time."""
        # 1) Resolve scheduler
        bootstrap_mode = bool(bootstrap)
        if bootstrap_mode:
            if store:
                info("Using --bootstrap; ignoring --store.")
            scheduler: AsyncIOScheduler = load_bootstrap_scheduler(bootstrap)  # type: ignore[arg-type]
            with contextlib.suppress(Exception):
                await maybe_await(scheduler.start())
        else:
            stores_cfg: dict[str, dict[str, Any]] = (
                build_stores_map(store) if store else {"default": {"type": "memory"}}
            )
            cfg: dict[str, dict[str, Any]] = {"stores": stores_cfg}
            scheduler = AsyncIOScheduler(**cfg)
            await maybe_await(scheduler.start())

        # 2) Lookup the task and its backing store alias
        # Use None to let the scheduler find the correct store alias for the task.
        task: AsynczTask
        store_alias: str
        task, store_alias = scheduler.lookup_task(job_id, None)  # type: ignore

        # 3) Compute the next run time from "now" (resume semantics)
        now: datetime = datetime.now(scheduler.timezone)
        next_run: datetime | None = task.trigger.get_next_trigger_time(  # type: ignore[union-attr]
            scheduler.timezone, None, now
        )

        # 4) Update or delete in the appropriate store
        if next_run:
            task.update_task(next_run_time=next_run)
            store_obj: BaseStore = scheduler.lookup_store(store_alias)  # type: ignore
            store_obj.update_task(task)
            success(f"Resumed job {job_id}")
        else:
            # No further runs: remove the task entirely
            scheduler.delete_task(job_id, store_alias)
            success(f"Removed job {job_id} (schedule finished)")

        # 5) Shutdown only if we created a temporary scheduler
        if not bootstrap_mode:
            await maybe_await(scheduler.shutdown())

    loop.run_until_complete(main())
