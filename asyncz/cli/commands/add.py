from __future__ import annotations

import asyncio
import contextlib
import json
from collections.abc import Callable
from typing import Annotated, Any

from sayer import Argument, Option, command, info

from asyncz.cli.bootstrap_loader import load_bootstrap_scheduler
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

        # 1) Parse trigger (mutually exclusive)
        t: BaseTrigger = parse_trigger(cron=cron, interval=interval, at=at)

        # 2) Parse JSON args/kwargs
        pos: list[Any] = json.loads(args) if args else []
        kw: dict[str, Any] = json.loads(kwargs) if kwargs else {}

        # 3) Resolve scheduler
        bootstrap_mode = bool(bootstrap)
        if bootstrap_mode:
            if store:
                info("Using --bootstrap; ignoring --store.")
            scheduler: AsyncIOScheduler = load_bootstrap_scheduler(bootstrap)  # type: ignore[arg-type]

            with contextlib.suppress(Exception):
                await maybe_await(scheduler.start())

            # Determine a target store alias from the framework scheduler (best effort)
            target_store_alias: str | None = None
            try:
                # Prefer explicit default if exposed
                target_store_alias = getattr(scheduler, "default_store", None)
                if not target_store_alias:
                    stores_dict = getattr(scheduler, "stores", None)
                    if isinstance(stores_dict, dict) and stores_dict:
                        target_store_alias = next(iter(stores_dict.keys()))
            except Exception:
                target_store_alias = None

        else:
            # Build stores config and pick the default alias to submit into
            stores_cfg: dict[str, dict[str, Any]] = (
                build_stores_map(store) if store else {"default": {"type": "memory"}}
            )
            cfg: dict[str, Any] = {"stores": stores_cfg}
            target_store_alias = next(iter(stores_cfg.keys()))
            scheduler = AsyncIOScheduler(**cfg)
            await maybe_await(scheduler.start())

        # 4) Resolve callable and add task
        func: Callable[..., Any] = import_callable(callable_path)
        job = await maybe_await(
            scheduler.add_task(
                func,
                trigger=t,
                args=pos,
                kwargs=kw,
                name=name,
                store=target_store_alias,  # may be None in bootstrap mode; scheduler decides default
            )
        )

        info(f"Added job {job.id} ({job.name or func.__name__})")

        # 5) Shutdown only if we created a temporary scheduler
        if not bootstrap_mode:
            await maybe_await(scheduler.shutdown())

    loop.run_until_complete(main())
