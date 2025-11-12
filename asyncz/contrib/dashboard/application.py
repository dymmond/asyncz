from typing import Any

from lilya.routing import Include, RoutePath, Router
from lilya.staticfiles import StaticFiles

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


def create_dashboard_app(scheduler: Any) -> Router:
    """
    Build a Lilya sub-application wired to an AsyncZ AsyncIOScheduler.
    The scheduler must be a live scheduler instance owned by the host app.
    """
    app = Router(
        routes=[
            Include(
                path="/tasks",
                routes=[
                    RoutePath(
                        "/",
                        TasklistController.with_init(scheduler=scheduler),
                        name="index",
                    ),
                    RoutePath(
                        "/partials/table",
                        TaskTablePartialController.with_init(scheduler=scheduler),
                        name="table",
                    ),
                    RoutePath(
                        "/create",
                        TaskCreateController.with_init(scheduler=scheduler),
                        name="create",
                    ),
                    RoutePath(
                        "/hx/bulk/pause",
                        TaskBulkPauseController.with_init(scheduler=scheduler),
                        name="bulk_pause",
                    ),
                    RoutePath(
                        "/hx/bulk/resume",
                        TaskBulkResumeController.with_init(scheduler=scheduler),
                        name="bulk_resume",
                    ),
                    RoutePath(
                        "/hx/bulk/remove",
                        TaskBulkRemoveController.with_init(scheduler=scheduler),
                        name="bulk_remove",
                    ),
                    RoutePath(
                        "/hx/bulk/run",
                        TaskBulkRunController.with_init(scheduler=scheduler),
                        name="bulk_run",
                    ),
                    RoutePath(
                        "/{task_id:str}/run",
                        TaskHXRunController.with_init(scheduler=scheduler),
                        name="hx_run",
                    ),
                    RoutePath(
                        "/{task_id:str}/pause",
                        TaskHXPauseController.with_init(scheduler=scheduler),
                        name="hx_pause",
                    ),
                    RoutePath(
                        "/{task_id:str}/resume",
                        TaskHXResumeController.with_init(scheduler=scheduler),
                        name="hx_resume",
                    ),
                    RoutePath(
                        "/{task_id:str}/remove",
                        TaskHXRemoveController.with_init(scheduler=scheduler),
                        name="hx_remove",
                    ),
                ],
                name="tasks",
            ),
            Include(
                "/static",
                app=StaticFiles(packages=["asyncz.contrib.dashboard"], html=True),
                name="statics",
            ),
            RoutePath(
                "/",
                home.DashboardController.with_init(scheduler=scheduler),
                name="index",
            ),
        ],
    )
    return app
