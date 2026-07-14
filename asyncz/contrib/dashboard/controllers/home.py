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
        scheduler_info = self.scheduler.get_scheduler_info()
        task_infos = self.scheduler.get_task_infos()
        recent_tasks = [serialize(task_info) for task_info in task_infos[:10]]

        context = await self.get_context_data(
            request,
            title="Overview",
            page_header="Dashboard",
            active_page="dashboard",
            scheduler_running=scheduler_info.running,
            scheduler_state=scheduler_info.state_label,
            timezone=scheduler_info.timezone,
            total_tasks=scheduler_info.task_count,
            scheduled_tasks=scheduler_info.scheduled_task_count,
            paused_tasks=scheduler_info.paused_task_count,
            pending_tasks=scheduler_info.pending_task_count,
            store_count=len(scheduler_info.store_aliases),
            executor_count=len(scheduler_info.executor_aliases),
            tasks=recent_tasks,
        )
        return await self.render_template(request, context=context)
