from __future__ import annotations

import asyncio
import contextlib
from typing import Annotated, Any

from sayer import Argument, Option, command, info, success

from asyncz.cli.bootstrap_loader import load_bootstrap_scheduler
from asyncz.cli.utils import build_stores_map, ensure_loop, maybe_await
from asyncz.schedulers import AsyncIOScheduler


@command
def pause(
    job_id: Annotated[str, Argument(help="Job ID")],
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
    Pause a job by ID.

    The CLI delegates to ``scheduler.pause_task(...)`` so command-line behavior
    stays aligned with the scheduler's own pause semantics.

    Examples:
        asyncz pause <job_id>
        asyncz pause <job_id> --store durable=sqlite:///scheduler.db
    """
    loop: asyncio.AbstractEventLoop = ensure_loop()

    async def main() -> None:
        """The core asynchronous logic for pausing the job by directly manipulating its next_run_time."""
        # 1. Configuration and Initialization
        bootstrap_mode = bool(bootstrap)
        if bootstrap_mode:
            if store:
                info("Using --bootstrap; ignoring --store.")
            scheduler: AsyncIOScheduler = load_bootstrap_scheduler(bootstrap)  # type: ignore[arg-type]
            with contextlib.suppress(Exception):
                await maybe_await(scheduler.start())

        else:
            stores_cfg: dict[str, dict[str, Any]] = (
                build_stores_map(store) if store else {"default": {"type": "memory"}}
            )
            cfg: dict[str, dict[str, Any]] = {"stores": stores_cfg}
            scheduler = AsyncIOScheduler(**cfg)
            await maybe_await(scheduler.start())

        # 2) Delegate to the scheduler API.
        await maybe_await(scheduler.pause_task(job_id))

        success(f"Paused job {job_id}")

        # 3) Shutdown only if we created a temporary scheduler
        if not bootstrap_mode:
            await maybe_await(scheduler.shutdown())

    loop.run_until_complete(main())
