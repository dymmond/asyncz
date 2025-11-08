from __future__ import annotations

import asyncio
from typing import Annotated, Any

from sayer import Argument, Option, command, success

from asyncz.cli.utils import build_stores_map, ensure_loop, maybe_await
from asyncz.schedulers import AsyncIOScheduler
from asyncz.stores.base import BaseStore
from asyncz.tasks import Task as AsynczTask


@command
def pause(
    job_id: Annotated[str, Argument(help="Job ID")],
    store: Annotated[list[str], Option([], "--store", help="Store spec alias=value. Repeatable.")],
) -> None:
    """
    Pause a job by ID.

    This command initializes a temporary scheduler, connects to the specified job store,
    and instructs the store to temporarily suspend the execution of the specified job ID.

    This implementation achieves the pause by **directly setting the task's next run time to None**
    in the persistent store, avoiding scheduler events that might interfere with CLI execution.

    Examples:
        asyncz pause <job_id>
        asyncz pause <job_id> --store durable=sqlite:///scheduler.db
    """
    loop: asyncio.AbstractEventLoop = ensure_loop()

    async def main() -> None:
        """The core asynchronous logic for pausing the job by directly manipulating its next_run_time."""

        # 1. Configuration and Initialization
        # Build stores config the same way as 'add' / 'run' so we target the same alias
        stores_cfg: dict[str, dict[str, Any]] = (
            build_stores_map(store) if store else {"default": {"type": "memory"}}
        )
        cfg: dict[str, dict[str, Any]] = {"stores": stores_cfg}

        # Determine the target store alias
        target_alias: str = next(iter(stores_cfg.keys()))

        sched: AsyncIOScheduler = AsyncIOScheduler(**cfg)
        await maybe_await(sched.start())

        # 2. Lookup Task and Store
        task: AsynczTask
        store_obj: BaseStore

        # Look up the task (raises TaskLookupError if missing)
        task, _ = sched.lookup_task(job_id, target_alias)  # type: ignore

        # Get the store object
        store_obj = sched.lookup_store(target_alias)  # type: ignore

        # 3. Mark Paused: Update task state directly and persist
        # Mark paused by clearing next_run_time (this is the state used by the scheduler to skip the job)
        task.update_task(next_run_time=None)
        store_obj.update_task(task)

        success(f"Paused job {job_id}")

        # 4. Shutdown
        await maybe_await(sched.shutdown())

    loop.run_until_complete(main())
