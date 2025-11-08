from __future__ import annotations

import asyncio
from typing import Annotated, Any

from sayer import Argument, Option, command, success

from asyncz.cli.utils import build_stores_map, ensure_loop, maybe_await
from asyncz.schedulers import AsyncIOScheduler


@command
def pause(
    job_id: Annotated[str, Argument(help="Job ID")],
    store: Annotated[list[str], Option([], "--store", help="Store spec alias=value. Repeatable.")],
) -> None:
    """
    Pause a job by ID.

    This command initializes a temporary scheduler, connects to the specified job store,
    and instructs the store to temporarily suspend the execution of the specified job ID.

    Examples:

        asyncz pause <job_id>
        asyncz pause <job_id> --store durable=sqlite:///scheduler.db
    """
    loop: asyncio.AbstractEventLoop = ensure_loop()

    async def main() -> None:
        """The core asynchronous logic for pausing the job."""

        # 1. Build configuration for stores
        cfg_stores: dict[str, dict[str, Any]] = (
            build_stores_map(store) if store else {"default": {"type": "memory"}}
        )
        cfg: dict[str, dict[str, dict[str, Any]]] = {"stores": cfg_stores}

        # Determine the target store alias (the first one defined, assumed to be the store where the job resides)
        default_store_alias: str = next(iter(cfg_stores.keys()))

        # 2. Initialize and start a temporary scheduler instance
        sched: AsyncIOScheduler = AsyncIOScheduler(**cfg)
        await maybe_await(sched.start())

        # 3. Pause the job (pause_task is synchronous on the scheduler object)
        sched.pause_task(job_id, store=default_store_alias)

        success(f"Paused job {job_id}")

        # 4. Shutdown the temporary scheduler
        await maybe_await(sched.shutdown())

    loop.run_until_complete(main())
