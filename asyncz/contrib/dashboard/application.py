import logging
from typing import Any

from lilya.routing import Include, RoutePath, Router
from lilya.staticfiles import StaticFiles

from asyncz.contrib.dashboard.controllers import home
from asyncz.contrib.dashboard.controllers.logs import (
    LogsPageController,
    LogsTablePartialController,
    get_log_storage,
)
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
from asyncz.contrib.dashboard.logs.handler import install_task_log_handler
from asyncz.contrib.dashboard.logs.storage import LogStorage


def create_dashboard_app(scheduler: Any, log_storage: LogStorage | None = None) -> Router:
    """
    Build a Lilya sub-application wired to an AsyncZ AsyncIOScheduler.
    The scheduler must be a live scheduler instance owned by the host app.
    """
    install_task_log_handler(storage=get_log_storage(storage=log_storage))

    # Ensure stdlib logs on the namespaced logger bubble up to our handler.
    # Our TaskLogHandler is installed by install_task_log_handler() on a parent logger.
    # Make sure the child logger used by tests (`asyncz.task`) propagates upward.
    logging.getLogger("asyncz").setLevel(logging.INFO)
    logging.getLogger("asyncz").propagate = True

    app = Router(
        routes=[
            Include(
                path="/logs",
                routes=[
                    RoutePath("/", LogsPageController, name="index"),
                    RoutePath("/partials/table", LogsTablePartialController, name="table"),
                ],
                name="logs",
            ),
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
