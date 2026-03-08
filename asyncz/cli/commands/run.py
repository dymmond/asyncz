from __future__ import annotations

import asyncio
import contextlib
from typing import Annotated, Any

from sayer import Argument, Option, command, info

from asyncz.cli.bootstrap_loader import load_bootstrap_scheduler
from asyncz.cli.utils import build_stores_map, ensure_loop, maybe_await
from asyncz.schedulers import AsyncIOScheduler


@command
def run(
    job_id: Annotated[str, Argument(help="Job ID to run now")],
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
    Trigger a job to run immediately.

    This command delegates to ``scheduler.run_task(...)`` so the CLI, dashboard,
    and programmatic APIs all share the same "run now" semantics.

    Examples:

        asyncz run <job_id>
        asyncz run <job_id> --store durable=sqlite:///scheduler.db
    """
    loop: asyncio.AbstractEventLoop = ensure_loop()

    async def main() -> None:
        """The core asynchronous logic for running the job immediately."""
        bootstrap_mode = bool(bootstrap)
        if bootstrap_mode:
            if store:
                info("Using --bootstrap; ignoring --store flag.")

            scheduler: AsyncIOScheduler = load_bootstrap_scheduler(bootstrap)  # type: ignore[arg-type]
            # Try starting the scheduler if not already running
            with contextlib.suppress(Exception):
                await maybe_await(scheduler.start())
        else:
            # 1. Build configuration and initialize a temporary scheduler
            cfg: dict[str, dict[str, Any]] = {"stores": build_stores_map(store)} if store else {}
            scheduler = AsyncIOScheduler(**cfg)
            await maybe_await(scheduler.start())

        # 2. Delegate the "run now" flow to the scheduler itself.
        await maybe_await(scheduler.run_task(job_id))
        info(f"Triggered job {job_id}")

        # 3. Shutdown the temporary scheduler
        if not bootstrap_mode:
            await maybe_await(scheduler.shutdown())

    loop.run_until_complete(main())
