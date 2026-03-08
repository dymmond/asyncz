from __future__ import annotations

import contextlib
import json
from collections.abc import Callable
from typing import Any

from lilya.controllers import Controller
from lilya.requests import Request
from lilya.responses import HTMLResponse, RedirectResponse
from lilya.templating.controllers import TemplateController

from asyncz.cli.utils import import_callable
from asyncz.contrib.dashboard.controllers._helpers import (
    build_task_dashboard_context,
    parse_ids_from_request_form,
    parse_trigger,
    render_table,
)
from asyncz.contrib.dashboard.messages import add_message
from asyncz.contrib.dashboard.mixins import DashboardMixin
from asyncz.exceptions import MaximumInstancesError, TaskLookupError
from asyncz.schedulers import AsyncIOScheduler


class TasklistController(DashboardMixin, TemplateController):
    """
    Renders the main task management dashboard page, displaying a list of all scheduled tasks.
    """

    template_name: str = "tasks/tasks.html"

    def __init__(self, *, scheduler: AsyncIOScheduler) -> None:
        """Initializes the controller with the active scheduler instance."""
        super().__init__()
        self.scheduler: AsyncIOScheduler = scheduler

    async def get(self, request: Request) -> Any:
        """Render the main task page using the scheduler-native task inspection API."""
        ctx: dict[str, Any] = await self.get_context_data(request)
        ctx.update(
            {
                "title": "Tasks",
                "page_header": "Tasks",
                "active_page": "tasks",
            }
        )
        ctx.update(build_task_dashboard_context(self.scheduler, request))
        return await self.render_template(request, context=ctx)


class _BaseTaskAction(Controller):
    """
    Base class for task action controllers (Run, Pause, Resume, Remove) that
    require scheduler access and redirect on completion.
    """

    def __init__(self, *, scheduler: AsyncIOScheduler) -> None:
        self.scheduler: AsyncIOScheduler = scheduler

    async def _redirect(self) -> RedirectResponse:
        """Returns a redirect response to the main tasks list page."""
        return RedirectResponse(url="/tasks", status_code=302)


class TaskRunController(_BaseTaskAction):
    """Handles running a task immediately via a standard HTTP POST (non-HTMX)."""

    async def post(self, request: Request) -> Any:
        """Trigger the specified task immediately through the scheduler API."""
        task_id: str = request.path_params["task_id"]
        try:
            self.scheduler.run_task(task_id, remove_finished=False)
        except MaximumInstancesError as exc:
            add_message(request, "warning", str(exc))
        return await self._redirect()


class TaskPauseController(_BaseTaskAction):
    """Handles pausing a task via a standard HTTP POST (non-HTMX)."""

    async def post(self, request: Request) -> Any:
        """Pause the specified task through the scheduler API."""
        task_id: str = request.path_params["task_id"]
        self.scheduler.pause_task(task_id)
        return await self._redirect()


class TaskResumeController(_BaseTaskAction):
    """Handles resuming a paused task via a standard HTTP POST (non-HTMX)."""

    async def post(self, request: Request) -> Any:
        """Resume the specified task through the scheduler API."""
        task_id: str = request.path_params["task_id"]
        self.scheduler.resume_task(task_id)
        return await self._redirect()


class TaskRemoveController(_BaseTaskAction):
    """Handles removing a task via a standard HTTP POST (non-HTMX)."""

    async def post(self, request: Request) -> Any:
        """Permanently removes the specified task from its store."""
        task_id: str = request.path_params["task_id"]
        self.scheduler.delete_task(task_id)
        return await self._redirect()


class TaskTablePartialController(DashboardMixin, Controller):
    """Renders the HTML table fragment of tasks, used by HTMX for real-time updates."""

    def __init__(self, *, scheduler: AsyncIOScheduler) -> None:
        self.scheduler: AsyncIOScheduler = scheduler

    async def get(self, request: Request) -> HTMLResponse:
        """Render the filtered HTMX task table fragment."""
        context = await self.get_context_data(request)
        return await render_table(self.scheduler, request, context)


class TaskCreateController(DashboardMixin, Controller):
    """Handles creation of a new task via a modal form submission."""

    def __init__(self, *, scheduler: AsyncIOScheduler) -> None:
        self.scheduler: AsyncIOScheduler = scheduler

    async def post(self, request: Request) -> HTMLResponse:
        """
        Processes form data, validates and adds the new task to the scheduler,
        then returns the updated task table.
        """
        # Process form data
        form: Any = await request.form()

        callable_path: str = (form.get("callable_path") or "").strip()
        name: str | None = (form.get("name") or None) or None
        store_alias: str = (form.get("store") or "default").strip() or "default"
        trigger_type: str = (form.get("trigger_type") or "interval").strip()
        trigger_value: str = (form.get("trigger_value") or "10s").strip()

        # Parse args/kwargs JSON
        raw_args: str = (form.get("args") or "").strip()
        raw_kwargs: str = (form.get("kwargs") or "").strip()
        args: list[Any] = json.loads(raw_args) if raw_args else []
        kwargs: dict[str, Any] = json.loads(raw_kwargs) if raw_kwargs else {}

        # Import callable and parse trigger
        try:
            func: Callable[..., Any] = import_callable(callable_path)
            trigger: Any = parse_trigger(trigger_type, trigger_value)
        except Exception as e:
            message = str(e)
            add_message(request, "error", f"{message}")
            context = await self.get_context_data(request)
            return await render_table(self.scheduler, request, context)

        # Add task to the scheduler
        self.scheduler.add_task(
            func,
            trigger=trigger,
            args=args,
            kwargs=kwargs,
            name=name,
            store=store_alias,
        )

        # Return updated table partial (HTMX response)
        context = await self.get_context_data(request)
        return await render_table(self.scheduler, request, context)


class TaskBulkPauseController(DashboardMixin, Controller):
    """Handles pausing multiple tasks via an HTMX POST request."""

    def __init__(self, *, scheduler: AsyncIOScheduler) -> None:
        self.scheduler: AsyncIOScheduler = scheduler

    async def post(self, request: Request) -> HTMLResponse:
        """Processes a list of task IDs, pauses each one, and returns the updated task table."""
        form: Any = await request.form()
        ids: list[str] = parse_ids_from_request_form(form)

        for task_id in ids:
            try:
                self.scheduler.pause_task(task_id)
            except TaskLookupError:
                continue

        context = await self.get_context_data(request)
        return await render_table(self.scheduler, request, context)


class TaskBulkRunController(DashboardMixin, Controller):
    """
    Handles triggering multiple scheduled tasks to run immediately (bulk run action).
    """

    def __init__(self, *, scheduler: AsyncIOScheduler) -> None:
        self.scheduler: AsyncIOScheduler = scheduler

    async def post(self, request: Request) -> HTMLResponse:
        form: Any = await request.form()
        ids: list[str] = parse_ids_from_request_form(form)

        for task_id in ids:
            try:
                self.scheduler.run_task(task_id, remove_finished=False)
            except MaximumInstancesError as exc:
                add_message(request, "warning", str(exc))
            except TaskLookupError:
                continue

        # Return refreshed table fragment for HTMX swap
        context = await self.get_context_data(request)
        return await render_table(self.scheduler, request, context)


class TaskBulkResumeController(DashboardMixin, Controller):
    """Handles resuming multiple paused tasks via an HTMX POST request."""

    def __init__(self, *, scheduler: AsyncIOScheduler) -> None:
        self.scheduler: AsyncIOScheduler = scheduler

    async def post(self, request: Request) -> HTMLResponse:
        """
        Processes a list of task IDs, resumes each one (or deletes if finished),
        and returns the updated task table.
        """
        form: Any = await request.form()
        ids: list[str] = parse_ids_from_request_form(form)

        for task_id in ids:
            try:
                self.scheduler.resume_task(task_id)
            except TaskLookupError:
                continue

        context = await self.get_context_data(request)
        return await render_table(self.scheduler, request, context)


class TaskBulkRemoveController(DashboardMixin, Controller):
    """Handles removing multiple tasks via an HTMX POST request."""

    def __init__(self, *, scheduler: AsyncIOScheduler) -> None:
        self.scheduler: AsyncIOScheduler = scheduler

    async def post(self, request: Request) -> HTMLResponse:
        """Processes a list of task IDs, removes each one, and returns the updated task table."""
        form: Any = await request.form()
        ids: list[str] = parse_ids_from_request_form(form)

        for task_id in ids:
            try:
                self.scheduler.delete_task(task_id)
            except TaskLookupError:
                # Already removed or not found; keep operation idempotent.
                continue

        context = await self.get_context_data(request)
        return await render_table(self.scheduler, request, context)


class TaskHXRunController(DashboardMixin, Controller):
    """Handles running a single task immediately, returning the updated table partial."""

    def __init__(self, *, scheduler: AsyncIOScheduler) -> None:
        self.scheduler: AsyncIOScheduler = scheduler

    async def post(self, request: Request) -> HTMLResponse:
        """Trigger the specified task immediately and return the refreshed table."""
        task_id: str = request.path_params["task_id"]
        try:
            self.scheduler.run_task(task_id, remove_finished=False)
        except MaximumInstancesError as exc:
            add_message(request, "warning", str(exc))
        except TaskLookupError:
            ...

        context = await self.get_context_data(request)
        return await render_table(self.scheduler, request, context)


class TaskHXPauseController(DashboardMixin, Controller):
    """Handles pausing a single task, returning the updated table partial."""

    def __init__(self, *, scheduler: AsyncIOScheduler) -> None:
        self.scheduler: AsyncIOScheduler = scheduler

    async def post(self, request: Request) -> HTMLResponse:
        """Pause the specified task and return the refreshed task table."""
        task_id: str = request.path_params["task_id"]
        with contextlib.suppress(TaskLookupError):
            self.scheduler.pause_task(task_id)

        context = await self.get_context_data(request)
        return await render_table(self.scheduler, request, context)


class TaskHXResumeController(DashboardMixin, Controller):
    """Handles resuming a single task, returning the updated table partial."""

    def __init__(self, *, scheduler: AsyncIOScheduler) -> None:
        self.scheduler: AsyncIOScheduler = scheduler

    async def post(self, request: Request) -> HTMLResponse:
        """Resume the specified task and return the refreshed task table."""
        task_id: str = request.path_params["task_id"]
        with contextlib.suppress(TaskLookupError):
            self.scheduler.resume_task(task_id)

        context = await self.get_context_data(request)
        return await render_table(self.scheduler, request, context)


class TaskHXRemoveController(DashboardMixin, Controller):
    """Handles removing a single task, returning the updated table partial."""

    def __init__(self, *, scheduler: AsyncIOScheduler) -> None:
        self.scheduler: AsyncIOScheduler = scheduler

    async def post(self, request: Request) -> HTMLResponse:
        """Permanently removes the specified task and returns the updated task table."""
        task_id: str = request.path_params["task_id"]

        with contextlib.suppress(TaskLookupError):
            self.scheduler.delete_task(task_id)

        context = await self.get_context_data(request)
        return await render_table(self.scheduler, request, context)
