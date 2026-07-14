from __future__ import annotations

import json
from typing import Annotated, Any

from sayer import Option, command, info

from asyncz.cli.bootstrap_loader import load_bootstrap_scheduler
from asyncz.cli.utils import build_stores_map, ensure_loop, maybe_await
from asyncz.schedulers import AsyncIOScheduler
from asyncz.schedulers.inspection import SchedulerInfo


def _serialize_scheduler_info(snapshot: SchedulerInfo) -> dict[str, Any]:
    return {
        "state": snapshot.state_label,
        "state_code": int(snapshot.state),
        "running": snapshot.running,
        "timezone": snapshot.timezone,
        "executors": list(snapshot.executor_aliases),
        "stores": list(snapshot.store_aliases),
        "task_count": snapshot.task_count,
        "scheduled_task_count": snapshot.scheduled_task_count,
        "paused_task_count": snapshot.paused_task_count,
        "pending_task_count": snapshot.pending_task_count,
        "submitted_task_count": snapshot.submitted_task_count,
        "store_retry_interval": snapshot.store_retry_interval,
        "startup_delay": snapshot.startup_delay,
    }


@command(name="status")
def status(
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
    Inspect scheduler runtime status and task counts.

    With ``--bootstrap``, the command reports the scheduler object returned by
    the bootstrap without starting it. Without ``--bootstrap``, Asyncz creates a
    temporary scheduler using the provided stores so persisted task counts can be
    inspected through the normal scheduler APIs.
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
            payload = _serialize_scheduler_info(scheduler.get_scheduler_info())
            if as_json:
                print(json.dumps(payload, default=str))
                return payload

            info(
                f"state={payload['state']} running={payload['running']} "
                f"timezone={payload['timezone']}"
            )
            info(
                f"tasks={payload['task_count']} scheduled={payload['scheduled_task_count']} "
                f"paused={payload['paused_task_count']} pending={payload['pending_task_count']}"
            )
            info(
                f"stores={','.join(payload['stores']) or '-'} "
                f"executors={','.join(payload['executors']) or '-'}"
            )
            return None
        finally:
            if not bootstrap_mode:
                await maybe_await(scheduler.shutdown())

    return loop.run_until_complete(main())
