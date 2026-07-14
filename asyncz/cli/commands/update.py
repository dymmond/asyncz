from __future__ import annotations

import contextlib
import json
from typing import Annotated, Any

import click
from sayer import Argument, Option, command, info, success

from asyncz.cli.bootstrap_loader import load_bootstrap_scheduler
from asyncz.cli.utils import build_stores_map, ensure_loop, maybe_await
from asyncz.schedulers import AsyncIOScheduler
from asyncz.tasks.types import TaskType


def _parse_coalesce(value: str | None) -> bool | None:
    if value is None:
        return None

    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise click.BadParameter("coalesce must be one of true, false, yes, no, 1, or 0")


def _task_update_snapshot(task: TaskType) -> dict[str, Any]:
    return {
        "name": task.name,
        "executor": task.executor,
        "callable_reference": task.fn_reference,
        "args": list(task.args),
        "kwargs": dict(task.kwargs),
        "coalesce": task.coalesce,
        "max_instances": task.max_instances,
        "mistrigger_grace_time": task.mistrigger_grace_time,
    }


def _build_diff(before: dict[str, Any], after: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        key: {"before": before.get(key), "after": after.get(key)}
        for key in before
        if before.get(key) != after.get(key)
    }


@command(name="update")
def update(
    job_id: Annotated[str, Argument(help="Job ID to update")],
    name: Annotated[str | None, Option(None, "--name", help="Set the task name.")],
    callable_path: Annotated[
        str | None,
        Option(None, "--callable", help="Set the task callable reference, e.g. pkg.mod:func."),
    ],
    args: Annotated[str | None, Option(None, "--args", help="JSON array for *args.")],
    kwargs: Annotated[str | None, Option(None, "--kwargs", help="JSON object for **kwargs.")],
    executor: Annotated[str | None, Option(None, "--executor", help="Set executor alias.")],
    coalesce: Annotated[
        str | None,
        Option(None, "--coalesce", help="Set coalesce to true or false."),
    ],
    max_instances: Annotated[
        int | None,
        Option(None, "--max-instances", help="Set maximum concurrent task instances."),
    ],
    mistrigger_grace_time: Annotated[
        float | None,
        Option(None, "--mistrigger-grace-time", help="Set misfire grace time in seconds."),
    ],
    clear_mistrigger_grace_time: Annotated[
        bool,
        Option(False, "--clear-mistrigger-grace-time", help="Clear misfire grace time."),
    ],
    yes: Annotated[bool, Option(False, "--yes", "-y", help="Apply without prompting.")],
    dry_run: Annotated[bool, Option(False, "--dry-run", help="Show the diff without applying.")],
    as_json: Annotated[bool, Option(False, "--json", help="Output as JSON.")],
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
    Safely update supported task fields and show a before/after diff.

    This command delegates persistence to ``scheduler.update_task(...)``. Use
    ``--dry-run`` to inspect the proposed mutation and ``--yes`` for
    non-interactive application.
    """

    loop = ensure_loop()

    async def main() -> dict[str, Any] | None:
        parsed_coalesce = _parse_coalesce(coalesce)
        updates: dict[str, Any] = {}

        if name is not None:
            updates["name"] = name
        if callable_path is not None:
            updates["fn"] = callable_path
        if args is not None:
            parsed_args = json.loads(args)
            if isinstance(parsed_args, str) or not isinstance(parsed_args, list):
                raise click.BadParameter("args must be a JSON array.")
            updates["args"] = parsed_args
        if kwargs is not None:
            parsed_kwargs = json.loads(kwargs)
            if not isinstance(parsed_kwargs, dict):
                raise click.BadParameter("kwargs must be a JSON object.")
            updates["kwargs"] = parsed_kwargs
        if executor is not None:
            updates["executor"] = executor
        if parsed_coalesce is not None:
            updates["coalesce"] = parsed_coalesce
        if max_instances is not None:
            updates["max_instances"] = max_instances
        if clear_mistrigger_grace_time:
            updates["mistrigger_grace_time"] = None
        elif mistrigger_grace_time is not None:
            updates["mistrigger_grace_time"] = mistrigger_grace_time

        if not updates:
            raise click.ClickException("No updates were provided.")

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
            task, store_alias = scheduler.lookup_task(job_id, None)
            before = _task_update_snapshot(task)

            proposed = task.model_copy()
            proposed.update_task(scheduler=scheduler, **updates)
            proposed_after = _task_update_snapshot(proposed)
            diff = _build_diff(before, proposed_after)

            payload: dict[str, Any] = {
                "id": job_id,
                "store": store_alias,
                "dry_run": dry_run,
                "applied": False,
                "changed": bool(diff),
                "diff": diff,
            }

            if not diff:
                if as_json:
                    print(json.dumps(payload, default=str))
                    return payload
                info(f"No changes for job {job_id}.")
                return None

            if not as_json:
                info(f"Proposed update for job {job_id}:")
                for field, change in diff.items():
                    info(f"{field}: {change['before']!r} -> {change['after']!r}")

            if dry_run:
                if as_json:
                    print(json.dumps(payload, default=str))
                    return payload
                info("Dry run only. No changes applied.")
                return None

            if not yes:
                click.confirm("Apply this task update?", abort=True)

            updated = await maybe_await(scheduler.update_task(job_id, store_alias, **updates))
            payload["applied"] = True
            payload["after"] = _task_update_snapshot(updated)

            if as_json:
                print(json.dumps(payload, default=str))
                return payload

            success(f"Updated job {job_id}")
            return None
        finally:
            if not bootstrap_mode:
                await maybe_await(scheduler.shutdown())

    return loop.run_until_complete(main())
