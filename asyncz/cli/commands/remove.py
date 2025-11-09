from __future__ import annotations

import asyncio
import contextlib
from typing import Annotated, Any

from sayer import Argument, Option, command, info, success

from asyncz.cli.bootstrap_loader import load_bootstrap_scheduler
from asyncz.cli.utils import build_stores_map, ensure_loop, maybe_await
from asyncz.schedulers import AsyncIOScheduler


@command
def remove(
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

        # 1) Resolve scheduler
        bootstrap_mode = bool(bootstrap)
        if bootstrap_mode:
            if store:
                info("Using --bootstrap; ignoring --store.")
            scheduler: AsyncIOScheduler = load_bootstrap_scheduler(bootstrap)  # type: ignore[arg-type]

            with contextlib.suppress(Exception):
                await maybe_await(scheduler.start())
        else:
            cfg: dict[str, dict[str, Any]] = {"stores": build_stores_map(store)} if store else {}
            scheduler = AsyncIOScheduler(**cfg)
            await maybe_await(scheduler.start())

        # 2) Determine the store alias that holds the job (so delete works across multi-store setups)
        #    If your scheduler supports delete by ID only, this lookup is still safe and provides validation.
        _, store_alias = scheduler.lookup_task(job_id, None)

        # 3) Delete the job
        await maybe_await(scheduler.delete_task(job_id, store_alias))  # type: ignore

        success(f"Removed job {job_id}")

        # 4) Shutdown only if we created a temporary scheduler
        if not bootstrap_mode:
            await maybe_await(scheduler.shutdown())

    loop.run_until_complete(main())
