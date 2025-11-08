from __future__ import annotations

from typing import Annotated

from sayer import Argument, Option, command, success

from asyncz.cli.utils import build_stores_map, ensure_loop, maybe_await
from asyncz.schedulers import AsyncIOScheduler


@command
def resume(
    job_id: Annotated[str, Argument(help="Job ID")],
    store: Annotated[list[str], Option([], "--store", help="Store spec alias=value. Repeatable.")],
):
    """Resume a paused job by ID."""
    loop = ensure_loop()

    async def main():
        cfg = {"stores": build_stores_map(store)} if store else {}
        sched = AsyncIOScheduler(**cfg)
        await maybe_await(sched.start())
        await maybe_await(sched.resume_task(job_id))
        success(f"Resumed job {job_id}")
        await maybe_await(sched.shutdown())

    loop.run_until_complete(main())
