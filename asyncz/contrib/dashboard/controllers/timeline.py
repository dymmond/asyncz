from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Any

from lilya.requests import Request
from lilya.responses import Response
from lilya.templating.controllers import TemplateController

from asyncz.contrib.dashboard.mixins import DashboardMixin
from asyncz.schedulers import AsyncIOScheduler


def _bounded_int(value: str | None, *, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value or default)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(parsed, maximum))


def _timeline_filters(request: Request) -> dict[str, int]:
    params: Mapping[str, Any] = request.query_params
    return {
        "per_task": _bounded_int(params.get("per_task"), default=3, minimum=1, maximum=10),
        "limit": _bounded_int(params.get("limit"), default=100, minimum=1, maximum=500),
    }


def _display_datetime(value: datetime) -> str:
    return value.isoformat(timespec="seconds")


def build_timeline_context(scheduler: AsyncIOScheduler, request: Request) -> dict[str, Any]:
    filters = _timeline_filters(request)
    task_infos = scheduler.get_task_infos(sort_by="next_run_time")
    rows: list[dict[str, Any]] = []
    exhausted_count = 0

    for task_info in task_infos:
        if task_info.id is None:
            continue

        preview = scheduler.preview_task_runs(task_info.id, count=filters["per_task"])
        if preview is None:
            continue
        if preview.exhausted:
            exhausted_count += 1

        for run_time in preview.run_times:
            rows.append(
                {
                    "task_id": task_info.id,
                    "task_name": task_info.name or task_info.id,
                    "callable_reference": task_info.callable_reference
                    or task_info.callable_name
                    or "",
                    "run_time": run_time,
                    "run_time_label": _display_datetime(run_time),
                    "trigger": task_info.trigger_alias or task_info.trigger_name or "-",
                    "trigger_description": task_info.trigger_description or "-",
                    "state": task_info.schedule_state.value,
                    "store": task_info.store_alias or "default",
                    "executor": task_info.executor or "default",
                }
            )

    rows.sort(key=lambda row: row["run_time"])
    limited_rows = rows[: filters["limit"]]

    return {
        "filters": filters,
        "rows": limited_rows,
        "total_rows": len(rows),
        "visible_rows": len(limited_rows),
        "task_count": len(task_infos),
        "exhausted_count": exhausted_count,
        "next_run": limited_rows[0] if limited_rows else None,
    }


class TimelinePageController(DashboardMixin, TemplateController):
    template_name = "timeline/index.html"

    def __init__(self, *, scheduler: AsyncIOScheduler) -> None:
        super().__init__()
        self.scheduler = scheduler

    async def get(self, request: Request) -> Response:
        context = await self.get_context_data(
            request=request,
            title="Timeline",
            page_header="Run Timeline",
            active_page="timeline",
        )
        context.update(build_timeline_context(self.scheduler, request))
        return await self.render_template(request, context=context)
