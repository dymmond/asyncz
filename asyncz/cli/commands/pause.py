from __future__ import annotations

from typing import Annotated

from sayer import Argument, Option, command, success

from asyncz.cli.utils import build_stores_map, ensure_loop, maybe_await
from asyncz.schedulers import AsyncIOScheduler


@command
def pause(
    job_id: Annotated[str, Argument(help="Job ID")],
    store: Annotated[list[str], Option([], "--store", help="Store spec alias=value. Repeatable.")],
):
    """Pause a job by ID."""
    loop = ensure_loop()

    async def main():
        cfg_stores = build_stores_map(store) if store else {"default": {"type": "memory"}}
        cfg = {"stores": cfg_stores}
        default_store_alias = next(iter(cfg_stores.keys()))

        sched = AsyncIOScheduler(**cfg)
        await maybe_await(sched.start())
        # pause_task is synchronous; call it directly and target the same store alias used when adding
        sched.pause_task(job_id, store=default_store_alias)
        success(f"Paused job {job_id}")
        await maybe_await(sched.shutdown())

    loop.run_until_complete(main())
