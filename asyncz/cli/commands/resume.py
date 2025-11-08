from __future__ import annotations

import asyncio
from typing import Annotated, Any

from sayer import Argument, Option, command, success

from asyncz.cli.utils import build_stores_map, ensure_loop, maybe_await
from asyncz.schedulers import AsyncIOScheduler


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
        """The core asynchronous logic for resuming the job."""

        # 1. Build configuration for stores
        cfg: dict[str, dict[str, Any]] = {"stores": build_stores_map(store)} if store else {}

        # 2. Initialize and start a temporary scheduler instance
        sched: AsyncIOScheduler = AsyncIOScheduler(**cfg)
        await maybe_await(sched.start())

        # 3. Resume the job (resume_task is asynchronous, as it interacts with the store)
        await maybe_await(sched.resume_task(job_id))

        success(f"Resumed job {job_id}")

        # 4. Shutdown the temporary scheduler
        await maybe_await(sched.shutdown())

    loop.run_until_complete(main())
