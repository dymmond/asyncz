from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from typing import Annotated, Any

from sayer import Argument, Option, command, info

from asyncz.cli.types import parse_trigger
from asyncz.cli.utils import build_stores_map, ensure_loop, import_callable, maybe_await
from asyncz.schedulers import AsyncIOScheduler
from asyncz.triggers.base import BaseTrigger


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
) -> None:
    """
    Add a job with a cron/interval/date trigger.

    The job is submitted to a temporary scheduler instance which handles configuration
    and persistence. You must specify exactly one of --cron, --interval, or --at.

    Examples:

        asyncz add myapp.tasks:email --cron '0 0 * * *' --name email-daily
        asyncz add myapp.tasks:cleanup --interval '1h'
        asyncz add myapp.tasks:report --at '2026-01-01T10:00:00' --args '["user_id", 123]'
    """
    loop: asyncio.AbstractEventLoop = ensure_loop()

    async def main() -> None:
        """The core asynchronous logic for submitting the job."""

        # Parse the mutually exclusive trigger argument
        t: BaseTrigger = parse_trigger(cron=cron, interval=interval, at=at)

        # Parse JSON string arguments
        pos: list[Any] = json.loads(args) if args else []
        kw: dict[str, Any] = json.loads(kwargs) if kwargs else {}

        # Build stores config and pick the default alias to submit into
        stores_cfg: dict[str, dict[str, Any]] = (
            build_stores_map(store) if store else {"default": {"type": "memory"}}
        )
        cfg: dict[str, Any] = {"stores": stores_cfg}

        # The first key in stores_cfg is the alias we should target
        # (e.g., "default" or a user-defined alias like "durable")
        default_store_alias: str = next(iter(stores_cfg.keys()))

        # Initialize and start a temporary scheduler instance
        sched: AsyncIOScheduler = AsyncIOScheduler(**cfg)
        await maybe_await(sched.start())

        # Resolve callable path and add the job
        func: Callable[..., Any] = import_callable(callable_path)
        job = await maybe_await(
            sched.add_task(
                func, trigger=t, args=pos, kwargs=kw, name=name, store=default_store_alias
            )
        )

        info(f"Added job {job.id} ({job.name or func.__name__})")

        # Shutdown the temporary scheduler
        await maybe_await(sched.shutdown())

    loop.run_until_complete(main())
