from __future__ import annotations

import json
from typing import Annotated

from sayer import Argument, Option, command, info

from asyncz.cli.types import parse_trigger
from asyncz.cli.utils import build_stores_map, ensure_loop, import_callable, maybe_await
from asyncz.schedulers import AsyncIOScheduler


@command
def add(
    callable_path: Annotated[str, Argument(help="Python path to callable, e.g. pkg.mod:func")],
    name: Annotated[str | None, Option(None, help="Job name")],
    cron: Annotated[str | None, Option(None, help="Cron like '*/5 * * * *'")],
    interval: Annotated[str | None, Option(None, help="Interval '10s'|'5m'|'2h'")],
    at: Annotated[str | None, Option(None, help="ISO datetime to run once")],
    args: Annotated[str | None, Option(None, help="JSON array for *args")],
    kwargs: Annotated[str | None, Option(None, help="JSON object for **kwargs")],
    store: Annotated[list[str], Option([], "--store", help="Store spec alias=value. Repeatable.")],
):
    """Add a job with a cron/interval/date trigger."""
    loop = ensure_loop()

    async def main():
        t = parse_trigger(cron=cron, interval=interval, at=at)
        pos = json.loads(args) if args else []
        kw = json.loads(kwargs) if kwargs else {}

        # Build stores config and pick the default alias to submit into
        stores_cfg = build_stores_map(store) if store else {"default": {"type": "memory"}}
        cfg = {"stores": stores_cfg}

        # The first key in stores_cfg is the alias we should target (e.g., "durable")
        default_store_alias = next(iter(stores_cfg.keys()))

        sched = AsyncIOScheduler(**cfg)
        await maybe_await(sched.start())

        # Resolve callable; let the scheduler wrap it as a Task internally
        func = import_callable(callable_path)
        job = await maybe_await(
            sched.add_task(
                func, trigger=t, args=pos, kwargs=kw, name=name, store=default_store_alias
            )
        )

        info(f"Added job {job.id} ({job.name or func.__name__})")

        await maybe_await(sched.shutdown())

    loop.run_until_complete(main())
