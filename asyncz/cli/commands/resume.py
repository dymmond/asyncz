from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Annotated, Any

from sayer import Argument, Option, command, success

from asyncz.cli.utils import build_stores_map, ensure_loop, maybe_await
from asyncz.schedulers import AsyncIOScheduler
from asyncz.stores.base import BaseStore
from asyncz.tasks import Task as AsynczTask


@command
def resume(
    job_id: Annotated[str, Argument(help="Job ID")],
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
        """The core asynchronous logic for resuming the job, recalculating its next run time."""

        # 1. Configuration and Initialization
        stores_cfg: dict[str, dict[str, Any]] = (
            build_stores_map(store) if store else {"default": {"type": "memory"}}
        )
        cfg: dict[str, dict[str, Any]] = {"stores": stores_cfg}
        target_alias: str = next(iter(stores_cfg.keys()))

        sched: AsyncIOScheduler = AsyncIOScheduler(**cfg)
        await maybe_await(sched.start())

        # 2. Lookup Task and Store
        task: AsynczTask
        store_obj: BaseStore
        # TaskLookupError raised if missing
        task, _ = sched.lookup_task(job_id, target_alias)  # type: ignore
        store_obj = sched.lookup_store(target_alias)  # type: ignore

        # 3. Compute Next Run Time
        now: datetime = datetime.now(sched.timezone)
        # Use None for last_run_time to calculate the next trigger time based on the current time ('now').
        next_run: datetime | None = task.trigger.get_next_trigger_time(sched.timezone, None, now)  # type: ignore[union-attr]

        # 4. Update or Remove Task
        if next_run:
            # Update the in-memory task object and persist directly to the store
            task.update_task(next_run_time=next_run)
            store_obj.update_task(task)
            success(f"Resumed job {job_id}")
        else:
            # If the schedule yields no further run times, delete the task (schedule finished)
            sched.delete_task(job_id, target_alias)
            success(f"Removed job {job_id} (schedule finished)")

        # 5. Shutdown
        await maybe_await(sched.shutdown())

    loop.run_until_complete(main())
