from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from lilya.requests import Request
from lilya.responses import Response
from lilya.templating.controllers import TemplateController

from asyncz.contrib.dashboard.mixins import DashboardMixin
from asyncz.schedulers import AsyncIOScheduler


def _format_datetime(value: datetime | None) -> str:
    return value.isoformat(timespec="seconds") if value else "-"


def _format_seconds(value: float | None) -> str:
    return f"{value:.3f}s" if value is not None else "-"


def build_instances_context(scheduler: AsyncIOScheduler) -> dict[str, Any]:
    snapshots = scheduler.get_scheduler_instance_infos()
    rows = [
        {
            "identity": snapshot.identity,
            "scope": snapshot.scope,
            "state": snapshot.state_label,
            "active": snapshot.active,
            "stale": snapshot.stale,
            "started_at": _format_datetime(snapshot.started_at),
            "last_seen_at": _format_datetime(snapshot.last_seen_at),
            "uptime": _format_seconds(snapshot.uptime_seconds),
            "heartbeat_age": _format_seconds(snapshot.heartbeat_age_seconds),
            "stale_after": _format_seconds(snapshot.stale_after_seconds),
            "timezone": snapshot.timezone,
            "executors": ", ".join(snapshot.executor_aliases) or "-",
            "stores": ", ".join(snapshot.store_aliases) or "-",
            "task_count": snapshot.task_count,
            "scheduled_task_count": snapshot.scheduled_task_count,
            "paused_task_count": snapshot.paused_task_count,
            "pending_task_count": snapshot.pending_task_count,
            "submitted_task_count": snapshot.submitted_task_count,
        }
        for snapshot in snapshots
    ]

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "scope": "process-local",
        "instances": rows,
        "instance_count": len(rows),
        "active_count": sum(1 for row in rows if row["active"]),
        "stale_count": sum(1 for row in rows if row["stale"]),
    }


class InstancesPageController(DashboardMixin, TemplateController):
    template_name = "instances/index.html"

    def __init__(self, *, scheduler: AsyncIOScheduler) -> None:
        super().__init__()
        self.scheduler = scheduler

    async def get(self, request: Request) -> Response:
        context = await self.get_context_data(
            request=request,
            title="Instances",
            page_header="Scheduler Instances",
            active_page="instances",
        )
        context.update(build_instances_context(self.scheduler))
        return await self.render_template(request, context=context)
