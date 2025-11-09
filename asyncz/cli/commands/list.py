from __future__ import annotations

import contextlib
import json
from typing import Annotated, Any

from sayer import Option, command, info

from asyncz.cli.bootstrap_loader import load_bootstrap_scheduler
from asyncz.cli.utils import build_stores_map, ensure_loop, maybe_await
from asyncz.schedulers import AsyncIOScheduler


@command(name="list")
def list_jobs(
    as_json: Annotated[bool, Option(False, "--json", help="Output as JSON")],
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
    List jobs; if a persistent store is provided, it will reflect stored jobs.

    This command initializes a temporary scheduler instance, connects to the specified
    stores (or the default in-memory store), fetches all scheduled jobs, and prints
    their details.

    Examples:

        asyncz list
        asyncz list --store durable=sqlite:///scheduler.db
        asyncz list --json --store default=memory
        asyncz list --bootstrap ravyn.contrib.asyncz:AsynczSpec
    """
    loop = ensure_loop()

    async def main() -> list[dict[str, Any]] | None:
        # 1) Resolve scheduler
        bootstrap_mode = bool(bootstrap)
        if bootstrap_mode:
            if store:
                info("Using --bootstrap; ignoring --store.")
            scheduler: AsyncIOScheduler = load_bootstrap_scheduler(bootstrap)  # type: ignore[arg-type]

            with contextlib.suppress(Exception):
                await maybe_await(scheduler.start())

        else:
            # Default to an in-memory store if none provided to make the command useful out of the box
            stores_cfg: dict[str, dict[str, Any]] = (
                build_stores_map(store) if store else {"default": {"type": "memory"}}
            )
            cfg: dict[str, dict[str, dict[str, Any]]] = {"stores": stores_cfg}
            scheduler = AsyncIOScheduler(**cfg)
            await maybe_await(scheduler.start())

        try:
            # 2) Fetch jobs
            jobs = await maybe_await(scheduler.get_tasks())

            # 3) Format payload
            payload: list[dict[str, Any]] = [
                {
                    "id": j.id,
                    "name": j.name,
                    "trigger": type(j.trigger).__name__,
                    "next_run_time": getattr(j, "next_run_time", None),
                }
                for j in jobs
            ]

            # 4) Output
            if as_json:
                info(json.dumps(payload, default=str))
                return payload
            else:
                for r in payload:
                    info(
                        f"{r['id']:<32} {r['name'] or '-':<24} "
                        f"{r['trigger']:<16} {r['next_run_time']}"
                    )
                return None
        finally:
            # 5) Shutdown only if we created a temporary scheduler
            if not bootstrap_mode:
                await maybe_await(scheduler.shutdown())

    loop.run_until_complete(main())
