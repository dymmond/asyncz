from __future__ import annotations

import json
from typing import Annotated, Any

import click
from sayer import Option, command, info

from asyncz.cli.bootstrap_loader import load_bootstrap_scheduler
from asyncz.cli.commands.status import _serialize_scheduler_info
from asyncz.cli.utils import build_stores_map, ensure_loop, maybe_await
from asyncz.schedulers import AsyncIOScheduler
from asyncz.schedulers.inspection import SchedulerInfo


def _check(name: str, status: str, message: str) -> dict[str, str]:
    return {"name": name, "status": status, "message": message}


def _health_from_checks(checks: list[dict[str, str]]) -> str:
    if any(check["status"] == "failed" for check in checks):
        return "failed"
    if any(check["status"] == "warning" for check in checks):
        return "warning"
    return "ok"


def _build_checks(snapshot: SchedulerInfo) -> list[dict[str, str]]:
    checks = [
        _check(
            "scheduler_running",
            "ok" if snapshot.running else "warning",
            "Scheduler is running." if snapshot.running else "Scheduler is not running.",
        ),
        _check(
            "stores_registered",
            "ok" if snapshot.store_aliases else "failed",
            f"{len(snapshot.store_aliases)} store(s) registered."
            if snapshot.store_aliases
            else "No stores are registered.",
        ),
        _check(
            "executors_registered",
            "ok" if snapshot.executor_aliases else "failed",
            f"{len(snapshot.executor_aliases)} executor(s) registered."
            if snapshot.executor_aliases
            else "No executors are registered.",
        ),
        _check(
            "task_inventory",
            "ok",
            f"{snapshot.task_count} task(s) inspected through scheduler APIs.",
        ),
    ]

    if (
        snapshot.running
        and snapshot.started_at is not None
        and snapshot.uptime_seconds is not None
    ):
        checks.append(
            _check(
                "lifecycle_clock",
                "ok",
                f"Started at {snapshot.started_at}; uptime {snapshot.uptime_seconds:.3f}s.",
            )
        )
    elif snapshot.running:
        checks.append(
            _check(
                "lifecycle_clock",
                "failed",
                "Scheduler is running but start-time metadata is missing.",
            )
        )
    else:
        checks.append(
            _check(
                "lifecycle_clock",
                "warning",
                "Scheduler is stopped; no active start time is available.",
            )
        )

    return checks


def _build_doctor_payload(scheduler: AsyncIOScheduler) -> dict[str, Any]:
    snapshot = scheduler.get_scheduler_info()
    checks = _build_checks(snapshot)
    health = _health_from_checks(checks)
    ready = snapshot.running and health == "ok"
    return {
        "health": health,
        "ready": ready,
        "scheduler": _serialize_scheduler_info(snapshot),
        "checks": checks,
    }


@command(name="doctor")
def doctor(
    as_json: Annotated[bool, Option(False, "--json", help="Output as JSON")],
    strict: Annotated[
        bool,
        Option(False, "--strict", help="Exit with an error when health is not ok."),
    ],
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
    Run scheduler diagnostics and readiness checks.

    With ``--bootstrap``, Asyncz inspects the returned scheduler without starting
    it. Without ``--bootstrap``, Asyncz starts a temporary scheduler using the
    provided stores so readiness checks use the normal runtime path.
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
            payload = _build_doctor_payload(scheduler)
            if as_json:
                print(json.dumps(payload, default=str))
            else:
                scheduler_payload = payload["scheduler"]
                info(
                    f"health={payload['health']} ready={payload['ready']} "
                    f"identity={scheduler_payload['identity']}"
                )
                for check in payload["checks"]:
                    info(f"{check['status']:<7} {check['name']}: {check['message']}")

            if strict and payload["health"] != "ok":
                raise click.ClickException(
                    f"Scheduler doctor reported {payload['health']} health."
                )

            return payload if as_json else None
        finally:
            if not bootstrap_mode:
                await maybe_await(scheduler.shutdown())

    return loop.run_until_complete(main())
