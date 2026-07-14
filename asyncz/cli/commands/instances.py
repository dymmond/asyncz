from __future__ import annotations

import json
from typing import Annotated, Any

from sayer import Option, command, info

from asyncz.cli.bootstrap_loader import load_bootstrap_scheduler
from asyncz.cli.utils import build_stores_map, ensure_loop, maybe_await
from asyncz.schedulers import AsyncIOScheduler
from asyncz.schedulers.inspection import SchedulerInstanceInfo


def _serialize_scheduler_instance(snapshot: SchedulerInstanceInfo) -> dict[str, Any]:
    return {
        "identity": snapshot.identity,
        "scope": snapshot.scope,
        "state": snapshot.state_label,
        "state_code": int(snapshot.state),
        "active": snapshot.active,
        "stale": snapshot.stale,
        "started_at": snapshot.started_at,
        "last_seen_at": snapshot.last_seen_at,
        "uptime_seconds": snapshot.uptime_seconds,
        "heartbeat_age_seconds": snapshot.heartbeat_age_seconds,
        "stale_after_seconds": snapshot.stale_after_seconds,
        "timezone": snapshot.timezone,
        "executors": list(snapshot.executor_aliases),
        "stores": list(snapshot.store_aliases),
        "task_count": snapshot.task_count,
        "scheduled_task_count": snapshot.scheduled_task_count,
        "paused_task_count": snapshot.paused_task_count,
        "pending_task_count": snapshot.pending_task_count,
        "submitted_task_count": snapshot.submitted_task_count,
    }


@command(name="instances")
def instances(
    as_json: Annotated[bool, Option(False, "--json", help="Output as JSON")],
    bootstrap: Annotated[
        str | None,
        Option(
            None,
            help="Dotted path to a class with get_scheduler(), e.g. 'ravyn.contrib.asyncz:AsynczSpec'",
        ),
    ],
    store: Annotated[list[str], Option([], "--store", help="Store spec alias=value. Repeatable.")],
) -> dict[str, Any] | None:
    """
    List scheduler instances visible to the current runtime.

    The current Asyncz runtime exposes process-local instance inspection. It does
    not fabricate distributed scheduler membership from task stores.
    """

    loop = ensure_loop()

    async def main() -> dict[str, Any] | None:
        bootstrap_mode = bool(bootstrap)
        if bootstrap_mode:
            if store:
                info("Using --bootstrap; ignoring --store.")
            scheduler: AsyncIOScheduler = load_bootstrap_scheduler(bootstrap)  # type: ignore[arg-type]
        else:
            stores_cfg: dict[str, dict[str, Any]] = (
                build_stores_map(store) if store else {"default": {"type": "memory"}}
            )
            scheduler = AsyncIOScheduler(stores=stores_cfg)
            await maybe_await(scheduler.start())

        try:
            snapshots = scheduler.get_scheduler_instance_infos()
            payload = {
                "scope": "process-local",
                "count": len(snapshots),
                "instances": [_serialize_scheduler_instance(snapshot) for snapshot in snapshots],
            }

            if as_json:
                print(json.dumps(payload, default=str))
                return payload

            info(f"scope={payload['scope']} count={payload['count']}")
            for item in payload["instances"]:
                info(
                    f"{item['identity']} state={item['state']} active={item['active']} "
                    f"stale={item['stale']} last_seen_at={item['last_seen_at']}"
                )
            return None
        finally:
            if not bootstrap_mode:
                await maybe_await(scheduler.shutdown())

    return loop.run_until_complete(main())
