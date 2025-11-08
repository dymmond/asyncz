from __future__ import annotations

import asyncio
from typing import Annotated, Any

from sayer import Argument, Option, command, success

from asyncz.cli.utils import build_stores_map, ensure_loop, maybe_await
from asyncz.schedulers import AsyncIOScheduler


@command
def remove(
    job_id: Annotated[str, Argument(help="Job ID")],
    store: Annotated[list[str], Option([], "--store", help="Store spec alias=value. Repeatable.")],
) -> None:
    """
    Remove a job by ID.

    This command initializes a temporary scheduler, connects to the specified job store,
    and permanently deletes the specified job ID from the store.

    Examples:

        asyncz remove <job_id>
        asyncz remove <job_id> --store durable=sqlite:///scheduler.db
    """
    loop: asyncio.AbstractEventLoop = ensure_loop()

    async def main() -> None:
        """The core asynchronous logic for removing the job."""

        # 1. Build configuration for stores
        cfg: dict[str, dict[str, Any]] = {"stores": build_stores_map(store)} if store else {}

        # 2. Initialize and start a temporary scheduler instance
        sched: AsyncIOScheduler = AsyncIOScheduler(**cfg)
        await maybe_await(sched.start())

        # 3. Delete the job (delete_task is synchronous on the scheduler object, but may involve I/O in stores)
        # Note: The original logic implicitly uses the default store (first one defined)
        await maybe_await(sched.delete_task(job_id))  # type: ignore

        success(f"Removed job {job_id}")

        # 4. Shutdown the temporary scheduler
        await maybe_await(sched.shutdown())

    loop.run_until_complete(main())
