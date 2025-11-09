from typing import Any

from lilya.requests import Request
from lilya.templating.controllers import TemplateController

from asyncz.contrib.dashboard.mixins import DashboardMixin


class Teste(DashboardMixin, TemplateController):
    template_name = "index.html"

    async def get(self, request: Request) -> Any:
        context = await self.get_context_data(request)
        return await self.render_template(request, context=context)


class DashboardController(DashboardMixin, TemplateController):
    template_name = "index.html"

    def __init__(self, *, scheduler: Any) -> None:
        super().__init__()
        self.scheduler = scheduler

    async def get(self, request: Request) -> Any:
        running = getattr(self.scheduler, "running", False)
        tz = getattr(self.scheduler, "timezone", None)
        tasks = self.scheduler.get_tasks()
        total_tasks = len(tasks)

        context = await self.get_context_data(
            request,
            title="Overview",
            page_header="Dashboard",
            active_page="dashboard",
            scheduler_running=running,
            timezone=str(tz),
            total_tasks=total_tasks,
        )
        return await self.render_template(request, context=context)
