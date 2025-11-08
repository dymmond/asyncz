from __future__ import annotations

import json
from typing import Annotated, Any

from sayer import Option, command, info

from asyncz.cli.utils import build_stores_map, ensure_loop, maybe_await
from asyncz.schedulers import AsyncIOScheduler


@command(name="list")
def list_jobs(
    as_json: Annotated[bool, Option(False, "--json", help="Output as JSON")],
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
    """
    loop = ensure_loop()

    async def main() -> list[dict[str, Any]] | None:
        # 1) Build configuration for stores
        stores_cfg: dict[str, dict[str, Any]] = build_stores_map(store)
        cfg: dict[str, dict[str, dict[str, Any]]] = {"stores": stores_cfg}

        # 2) Initialize and start a temporary scheduler instance
        sched: AsyncIOScheduler = AsyncIOScheduler(**cfg)
        await maybe_await(sched.start())

        try:
            # 3) Fetch jobs
            jobs = await maybe_await(sched.get_tasks())

            # 4) Format payload
            payload: list[dict[str, Any]] = [
                {
                    "id": j.id,
                    "name": j.name,
                    "trigger": type(j.trigger).__name__,
                    "next_run_time": getattr(j, "next_run_time", None),
                }
                for j in jobs
            ]

            # 5) Output or return
            if as_json:
                # Print JSON so stdout-based parsers work…
                info(json.dumps(payload, default=str))
                # …and also return it so r.return_value works if supported.
                return payload
            else:
                for r in payload:
                    info(
                        f"{r['id']:<32} {r['name'] or '-':<24} "
                        f"{r['trigger']:<16} {r['next_run_time']}"
                    )
                return None
        finally:
            # 6) Shutdown the temporary scheduler
            await maybe_await(sched.shutdown())

    loop.run_until_complete(main())
