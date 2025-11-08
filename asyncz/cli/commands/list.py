from __future__ import annotations

import json
from typing import Annotated

from sayer import Option, command, info

from asyncz.cli.utils import build_stores_map, ensure_loop, maybe_await
from asyncz.schedulers import AsyncIOScheduler


@command(name="list")
def list_jobs(
    as_json: Annotated[bool, Option(False, "--json", help="Output as JSON")],
    store: Annotated[list[str], Option([], "--store", help="Store spec alias=value. Repeatable.")],
):
    """List jobs; if a persistent store is provided, it will reflect stored jobs."""
    loop = ensure_loop()

    async def main():
        cfg = {"stores": build_stores_map(store)} if store else {}
        sched = AsyncIOScheduler(**cfg)
        await maybe_await(sched.start())
        jobs = await maybe_await(sched.get_tasks())
        payload = [
            {
                "id": j.id,
                "name": j.name,
                "trigger": type(j.trigger).__name__,
                "next_run_time": getattr(j, "next_run_time", None),
            }
            for j in jobs
        ]
        if as_json:
            info(json.dumps(payload, default=str))
        else:
            for r in payload:
                info(
                    f"{r['id']:<24} {r['name'] or '-':<24} {r['trigger']:<12} {r['next_run_time']}"
                )
        await maybe_await(sched.shutdown())

    loop.run_until_complete(main())
