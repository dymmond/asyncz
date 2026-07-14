from __future__ import annotations

import contextlib
import json
from typing import Annotated, Any

import click
from sayer import Argument, Option, command, info

from asyncz.cli.bootstrap_loader import load_bootstrap_scheduler
from asyncz.cli.utils import build_stores_map, ensure_loop, maybe_await
from asyncz.schedulers import AsyncIOScheduler
from asyncz.tasks.inspection import TaskRunPreview


def _serialize_task_run_preview(preview: TaskRunPreview) -> dict[str, Any]:
    task = preview.task
    return {
        "task": {
            "id": task.id,
            "name": task.name,
            "state": task.schedule_state.value,
            "trigger": task.trigger_name,
            "trigger_alias": task.trigger_alias,
            "trigger_description": task.trigger_description,
            "store": task.store_alias,
            "executor": task.executor,
        },
        "timezone": preview.timezone,
        "generated_at": preview.generated_at,
        "requested_count": preview.requested_count,
        "returned_count": len(preview.run_times),
        "exhausted": preview.exhausted,
        "run_times": list(preview.run_times),
    }


@command(name="preview")
def preview(
    job_id: Annotated[str, Argument(help="Job ID to preview")],
    as_json: Annotated[bool, Option(False, "--json", help="Output as JSON")],
    count: Annotated[int, Option(5, "--count", help="Number of run times to preview, 1-50")],
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
    Preview upcoming run times for a task without modifying it.

    The command delegates to ``scheduler.preview_task_runs(...)`` so all trigger
    calculations come from Asyncz's real trigger implementations.
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
            preview_result = scheduler.preview_task_runs(job_id, count=count)
            if preview_result is None:
                raise click.ClickException(f"No task with id {job_id!r} was found.")

            payload = _serialize_task_run_preview(preview_result)
            if as_json:
                print(json.dumps(payload, default=str))
                return payload

            task = payload["task"]
            info(
                f"{task['id']} {task['name'] or '-'} "
                f"{task['state']} {task['trigger'] or '-'} {payload['timezone']}"
            )
            for index, run_time in enumerate(payload["run_times"], start=1):
                info(f"{index:>2}. {run_time}")
            if payload["exhausted"]:
                info("Trigger exhausted.")
            return None
        finally:
            if not bootstrap_mode:
                await maybe_await(scheduler.shutdown())

    return loop.run_until_complete(main())
