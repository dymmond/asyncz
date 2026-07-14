from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any

from lilya.requests import Request
from lilya.responses import Response
from lilya.templating.controllers import TemplateController

from asyncz.contrib.dashboard.mixins import DashboardMixin
from asyncz.schedulers import AsyncIOScheduler


def _component_rows(
    components: Mapping[str, Any],
    counts: Counter[str],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for alias, component in sorted(components.items()):
        component_type = type(component)
        rows.append(
            {
                "alias": alias,
                "class_name": component_type.__name__,
                "module": component_type.__module__,
                "task_count": counts.get(alias, 0),
                "logger_name": getattr(component, "logger_name", ""),
            }
        )
    return rows


def _snapshot_mapping(scheduler: AsyncIOScheduler, attr: str, lock_attr: str) -> dict[str, Any]:
    lock = getattr(scheduler, lock_attr, None)
    if lock is None:
        return dict(getattr(scheduler, attr, {}))

    with lock:
        return dict(getattr(scheduler, attr, {}))


def build_runtime_context(scheduler: AsyncIOScheduler) -> dict[str, Any]:
    scheduler_info = scheduler.get_scheduler_info()
    task_infos = scheduler.get_task_infos()
    stores = _snapshot_mapping(scheduler, "stores", "store_lock")
    executors = _snapshot_mapping(scheduler, "executors", "executor_lock")
    store_counts = Counter(info.store_alias or "default" for info in task_infos)
    executor_counts = Counter(info.executor or "default" for info in task_infos)

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "scheduler_running": scheduler_info.running,
        "scheduler_state": scheduler_info.state_label,
        "scheduler_state_code": int(scheduler_info.state),
        "timezone": scheduler_info.timezone,
        "total_tasks": scheduler_info.task_count,
        "scheduled_tasks": scheduler_info.scheduled_task_count,
        "paused_tasks": scheduler_info.paused_task_count,
        "pending_tasks": scheduler_info.pending_task_count,
        "submitted_tasks": scheduler_info.submitted_task_count,
        "store_retry_interval": scheduler_info.store_retry_interval,
        "startup_delay": scheduler_info.startup_delay,
        "stores": _component_rows(stores, store_counts),
        "executors": _component_rows(executors, executor_counts),
    }


class RuntimePageController(DashboardMixin, TemplateController):
    template_name = "runtime/index.html"

    def __init__(self, *, scheduler: AsyncIOScheduler) -> None:
        super().__init__()
        self.scheduler = scheduler

    async def get(self, request: Request) -> Response:
        context = await self.get_context_data(
            request=request,
            title="Runtime",
            page_header="Scheduler Runtime",
            active_page="runtime",
        )
        context.update(build_runtime_context(self.scheduler))
        return await self.render_template(request, context=context)
