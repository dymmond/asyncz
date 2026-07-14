from __future__ import annotations

import contextlib
import json
from typing import Annotated, Any

import click
from sayer import Argument, Option, command, info

from asyncz.cli.bootstrap_loader import load_bootstrap_scheduler
from asyncz.cli.utils import build_stores_map, ensure_loop, maybe_await
from asyncz.schedulers import AsyncIOScheduler
from asyncz.tasks.inspection import TaskInfo


def _serialize_task(task: TaskInfo) -> dict[str, Any]:
    return {
        "id": task.id,
        "name": task.name,
        "state": task.schedule_state.value,
        "trigger": task.trigger_name,
        "trigger_alias": task.trigger_alias,
        "trigger_description": task.trigger_description,
        "next_run_time": task.next_run_time,
        "store": task.store_alias,
        "executor": task.executor,
        "callable_name": task.callable_name,
        "callable_reference": task.callable_reference,
        "pending": task.pending,
        "paused": task.paused,
    }


@command(name="inspect")
def inspect_task(
    job_id: Annotated[str, Argument(help="Job ID to inspect")],
    as_json: Annotated[bool, Option(False, "--json", help="Output as JSON")],
    count: Annotated[int, Option(5, "--count", help="Number of upcoming run times, 1-50")],
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
    Inspect one task's runtime state and upcoming run times.

    This combines the single-task view operators usually need before deciding
    whether to run, pause, resume, or remove a task.
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
            task = await maybe_await(scheduler.get_task(job_id))
            if task is None:
                raise click.ClickException(f"No task with id {job_id!r} was found.")

            snapshot = task.snapshot()
            preview = scheduler.preview_task_runs(job_id, count=count)
            payload = {
                "task": _serialize_task(snapshot),
                "requested_count": count,
                "returned_count": len(preview.run_times) if preview else 0,
                "exhausted": preview.exhausted if preview else True,
                "run_times": list(preview.run_times) if preview else [],
            }

            if as_json:
                print(json.dumps(payload, default=str))
                return payload

            task_payload = payload["task"]
            info(
                f"{task_payload['id']} {task_payload['name'] or '-'} "
                f"{task_payload['state']} {task_payload['trigger'] or '-'}"
            )
            info(
                f"store={task_payload['store'] or '-'} "
                f"executor={task_payload['executor'] or '-'} "
                f"callable={task_payload['callable_reference'] or task_payload['callable_name'] or '-'}"
            )
            info(f"next_run_time={task_payload['next_run_time'] or '-'}")
            for index, run_time in enumerate(payload["run_times"], start=1):
                info(f"{index:>2}. {run_time}")
            return None
        finally:
            if not bootstrap_mode:
                await maybe_await(scheduler.shutdown())

    return loop.run_until_complete(main())
