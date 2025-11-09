from typing import Any

from lilya.apps import Lilya
from lilya.requests import Request
from lilya.routing import Include, RoutePath
from lilya.staticfiles import StaticFiles

from asyncz import monkay
from asyncz.contrib.dashboard.controllers import home
from asyncz.contrib.dashboard.controllers.tasks import (
    TaskBulkPauseController,
    TaskBulkRemoveController,
    TaskBulkResumeController,
    TaskBulkRunController,
    TaskCreateController,
    TaskHXPauseController,
    TaskHXRemoveController,
    TaskHXResumeController,
    TaskHXRunController,
    TasklistController,
    TaskTablePartialController,
)
from asyncz.contrib.dashboard.engine import templates


async def not_found(request: Request, exc: Exception) -> Any:
    return templates.get_template_response(
        request,
        "404.html",
        context={
            "title": "Not Found",
            "url_prefix": monkay.settings.dashboard_config.dashboard_url_prefix,
        },
        status_code=404,
    )


def create_dashboard_app(scheduler: Any) -> Lilya:
    """
    Build a Lilya sub-application wired to an AsyncZ AsyncIOScheduler.
    The scheduler must be a live scheduler instance owned by the host app.
    """
    app = Lilya(
        routes=[
            RoutePath(
                "/",
                home.DashboardController.with_init(scheduler=scheduler),
                name="dashboard:index",
            ),
            Include(
                path="/tasks",
                routes=[
                    RoutePath(
                        "/",
                        TasklistController.with_init(scheduler=scheduler),
                        name="tasks:index",
                    ),
                    RoutePath(
                        "/partials/table",
                        TaskTablePartialController.with_init(scheduler=scheduler),
                        name="tasks:table",
                    ),
                    RoutePath(
                        "/create",
                        TaskCreateController.with_init(scheduler=scheduler),
                        name="tasks:create",
                    ),
                    RoutePath(
                        "/hx/bulk/pause",
                        TaskBulkPauseController.with_init(scheduler=scheduler),
                        name="tasks:bulk_pause",
                    ),
                    RoutePath(
                        "/hx/bulk/resume",
                        TaskBulkResumeController.with_init(scheduler=scheduler),
                        name="tasks:bulk_resume",
                    ),
                    RoutePath(
                        "/hx/bulk/remove",
                        TaskBulkRemoveController.with_init(scheduler=scheduler),
                        name="tasks:bulk_remove",
                    ),
                    RoutePath(
                        "/hx/bulk/run",
                        TaskBulkRunController.with_init(scheduler=scheduler),
                        name="tasks:bulk_run",
                    ),
                    RoutePath(
                        "/{task_id:str}/run",
                        TaskHXRunController.with_init(scheduler=scheduler),
                        name="tasks:hx_run",
                    ),
                    RoutePath(
                        "/{task_id:str}/pause",
                        TaskHXPauseController.with_init(scheduler=scheduler),
                        name="tasks:hx_pause",
                    ),
                    RoutePath(
                        "/{task_id:str}/resume",
                        TaskHXResumeController.with_init(scheduler=scheduler),
                        name="tasks:hx_resume",
                    ),
                    RoutePath(
                        "/{task_id:str}/remove",
                        TaskHXRemoveController.with_init(scheduler=scheduler),
                        name="tasks:hx_remove",
                    ),
                ],
            ),
            Include(
                "/static",
                app=StaticFiles(packages=["asyncz.contrib.dashboard"], html=True),
                name="statics",
            ),
        ],
        exception_handlers={404: not_found},
    )
    return app
