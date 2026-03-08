from typing import Any

from lilya.requests import Request
from lilya.templating.controllers import TemplateController

from asyncz.contrib.dashboard.controllers._helpers import serialize
from asyncz.contrib.dashboard.mixins import DashboardMixin


class Teste(DashboardMixin, TemplateController):
    template_name = "index.html"

    async def get(self, request: Request) -> Any:
        context = await self.get_context_data(request)
        return await self.render_template(request, context=context)


class DashboardController(DashboardMixin, TemplateController):
    """Render the dashboard overview using scheduler inspection snapshots."""

    template_name = "index.html"

    def __init__(self, *, scheduler: Any) -> None:
        super().__init__()
        self.scheduler = scheduler

    async def get(self, request: Request) -> Any:
        running = getattr(self.scheduler, "running", False)
        tz = getattr(self.scheduler, "timezone", None)
        task_infos = self.scheduler.get_task_infos()
        total_tasks = len(task_infos)
        scheduled_tasks = sum(1 for info in task_infos if info.schedule_state.value == "scheduled")
        paused_tasks = sum(1 for info in task_infos if info.schedule_state.value == "paused")
        pending_tasks = sum(1 for info in task_infos if info.schedule_state.value == "pending")
        recent_tasks = [serialize(task_info) for task_info in task_infos[:10]]
        stores = sorted({info.store_alias or "default" for info in task_infos if info.store_alias})
        executors = sorted({info.executor or "default" for info in task_infos if info.executor})

        context = await self.get_context_data(
            request,
            title="Overview",
            page_header="Dashboard",
            active_page="dashboard",
            scheduler_running=running,
            timezone=str(tz),
            total_tasks=total_tasks,
            scheduled_tasks=scheduled_tasks,
            paused_tasks=paused_tasks,
            pending_tasks=pending_tasks,
            store_count=len(stores),
            executor_count=len(executors),
            tasks=recent_tasks,
        )
        return await self.render_template(request, context=context)
