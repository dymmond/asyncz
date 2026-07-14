from __future__ import annotations

import contextlib
import json
from datetime import datetime, timezone
from typing import Annotated, Any

from sayer import Option, command, info

from asyncz.cli.bootstrap_loader import load_bootstrap_scheduler
from asyncz.cli.utils import build_stores_map, ensure_loop, maybe_await
from asyncz.schedulers import AsyncIOScheduler
from asyncz.tasks.inspection import TaskInfo


def _bounded(value: int, *, minimum: int, maximum: int) -> int:
    return max(minimum, min(value, maximum))


def _serialize_task(task: TaskInfo) -> dict[str, Any]:
    return {
        "id": task.id,
        "name": task.name,
        "state": task.schedule_state.value,
        "trigger": task.trigger_name,
        "trigger_alias": task.trigger_alias,
        "trigger_description": task.trigger_description,
        "store": task.store_alias,
        "executor": task.executor,
        "callable_name": task.callable_name,
        "callable_reference": task.callable_reference,
    }


def _timeline_payload(
    scheduler: AsyncIOScheduler,
    *,
    per_task: int,
    limit: int,
) -> dict[str, Any]:
    scheduler_info = scheduler.get_scheduler_info()
    task_infos = scheduler.get_task_infos(sort_by="next_run_time")
    rows: list[dict[str, Any]] = []
    exhausted_task_count = 0

    for task in task_infos:
        if task.id is None:
            continue

        preview = scheduler.preview_task_runs(task.id, count=per_task)
        if preview is None:
            continue
        if preview.exhausted:
            exhausted_task_count += 1

        for run_time in preview.run_times:
            rows.append(
                {
                    "run_time": run_time,
                    "task": _serialize_task(task),
                }
            )

    rows.sort(key=lambda row: row["run_time"])
    limited_rows = rows[:limit]

    return {
        "timezone": scheduler_info.timezone,
        "generated_at": datetime.now(timezone.utc),
        "requested_per_task": per_task,
        "limit": limit,
        "task_count": len(task_infos),
        "total_count": len(rows),
        "returned_count": len(limited_rows),
        "exhausted_task_count": exhausted_task_count,
        "rows": limited_rows,
    }


@command(name="timeline")
def timeline(
    as_json: Annotated[bool, Option(False, "--json", help="Output as JSON")],
    per_task: Annotated[int, Option(3, "--per-task", help="Run times to preview per task, 1-10")],
    limit: Annotated[int, Option(100, "--limit", help="Maximum rows to return, 1-500")],
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
    Preview upcoming run times across all tasks without mutating scheduler state.
    """

    loop = ensure_loop()

    async def main() -> dict[str, Any] | None:
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
            scheduler = AsyncIOScheduler(stores=stores_cfg)
            await maybe_await(scheduler.start())

        try:
            payload = _timeline_payload(
                scheduler,
                per_task=_bounded(per_task, minimum=1, maximum=10),
                limit=_bounded(limit, minimum=1, maximum=500),
            )

            if as_json:
                print(json.dumps(payload, default=str))
                return payload

            info(
                f"timezone={payload['timezone']} tasks={payload['task_count']} "
                f"upcoming={payload['total_count']} showing={payload['returned_count']}"
            )
            for row in payload["rows"]:
                task = row["task"]
                info(
                    f"{row['run_time']} {task['id']} {task['name'] or '-'} "
                    f"{task['state']} {task['trigger'] or '-'} "
                    f"store={task['store'] or '-'} executor={task['executor'] or '-'}"
                )
            return None
        finally:
            if not bootstrap_mode:
                await maybe_await(scheduler.shutdown())

    return loop.run_until_complete(main())
