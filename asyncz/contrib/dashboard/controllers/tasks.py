from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from datetime import datetime
from typing import Any

from lilya.controllers import Controller
from lilya.requests import Request
from lilya.responses import HTMLResponse, RedirectResponse
from lilya.templating.controllers import TemplateController

from asyncz.cli.utils import import_callable
from asyncz.contrib.dashboard.controllers._helpers import (
    parse_trigger,
    render_table,
    serialize,
)
from asyncz.contrib.dashboard.mixins import DashboardMixin
from asyncz.executors.base import BaseExecutor
from asyncz.schedulers import AsyncIOScheduler
from asyncz.stores.base import BaseStore
from asyncz.tasks import Task as AsynczTask


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
        """Handles the GET request, retrieves tasks, and renders the full dashboard page."""
        tasks: Sequence[AsynczTask] = self.scheduler.get_tasks()  # type: ignore
        items: list[dict[str, Any]] = [serialize(t) for t in tasks]

        ctx: dict[str, Any] = await self.get_context_data(request)
        ctx.update(
            {
                "title": "Tasks",
                "page_header": "Tasks",
                "active_page": "tasks",
                "tasks": items,
            }
        )
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
        """Triggers the specified task to run immediately and updates its schedule."""
        task_id: str = request.path_params["task_id"]

        # Lookup task (raises TaskLookupError if not found)
        task: AsynczTask
        store_alias: str
        task, store_alias = self.scheduler.lookup_task(task_id, None)  # type: ignore

        # Calculate run times (forces run now if no schedule is active)
        now: datetime = datetime.now(self.scheduler.timezone)
        run_times: list[datetime] = task.get_run_times(self.scheduler.timezone, now)
        if not run_times:
            run_times = [now]

        # Submit task to executor
        executor: BaseExecutor = self.scheduler.lookup_executor(task.executor)  # type: ignore
        executor.send_task(task, run_times)

        # Update schedule state
        last_run: datetime = run_times[-1]
        next_run: datetime | None = task.trigger.get_next_trigger_time(  # type: ignore
            self.scheduler.timezone, last_run, now
        )

        if next_run:
            # Update the task's next run time and persist the change
            task.update_task(next_run_time=next_run)
            store_obj: BaseStore = self.scheduler.lookup_store(store_alias)  # type: ignore
            store_obj.update_task(task)
        else:
            # If schedule is finished, delete the task
            self.scheduler.delete_task(task.id, store_alias)

        return await self._redirect()


class TaskPauseController(_BaseTaskAction):
    """Handles pausing a task via a standard HTTP POST (non-HTMX)."""

    async def post(self, request: Request) -> Any:
        """Pauses the specified task by setting its next_run_time to None and persists the state."""
        task_id: str = request.path_params["task_id"]

        # Lookup task
        task: AsynczTask
        store_alias: str
        task, store_alias = self.scheduler.lookup_task(task_id, None)  # type: ignore

        # Pause by setting next_run_time to None
        task.update_task(next_run_time=None)

        # Persist the state change directly to the store
        store_obj: BaseStore = self.scheduler.lookup_store(store_alias)  # type: ignore
        store_obj.update_task(task)

        return await self._redirect()


class TaskResumeController(_BaseTaskAction):
    """Handles resuming a paused task via a standard HTTP POST (non-HTMX)."""

    async def post(self, request: Request) -> Any:
        """Resumes the specified task by recalculating its next run time and persisting the state."""
        task_id: str = request.path_params["task_id"]

        # Lookup task
        task: AsynczTask
        store_alias: str
        task, store_alias = self.scheduler.lookup_task(task_id, None)  # type: ignore

        # Calculate next run time based on current time (None for last_run_time)
        now: datetime = datetime.now(self.scheduler.timezone)
        next_run: datetime | None = task.trigger.get_next_trigger_time(  # type: ignore
            self.scheduler.timezone, None, now
        )

        if next_run:
            # Update the task's next run time and persist the change
            task.update_task(next_run_time=next_run)
            store_obj: BaseStore = self.scheduler.lookup_store(store_alias)  # type: ignore
            store_obj.update_task(task)
        else:
            # If schedule is finished, delete the task
            self.scheduler.delete_task(task.id, store_alias)

        return await self._redirect()


class TaskRemoveController(_BaseTaskAction):
    """Handles removing a task via a standard HTTP POST (non-HTMX)."""

    async def post(self, request: Request) -> Any:
        """Permanently removes the specified task from its store."""
        task_id: str = request.path_params["task_id"]

        # Lookup to get store alias
        _, store_alias = self.scheduler.lookup_task(task_id, None)

        await self.scheduler.delete_task(task_id, store_alias)  # type: ignore

        return await self._redirect()


class TaskTablePartialController(Controller):
    """Renders the HTML table fragment of tasks, used by HTMX for real-time updates."""

    def __init__(self, *, scheduler: AsyncIOScheduler) -> None:
        self.scheduler: AsyncIOScheduler = scheduler

    async def get(self, request: Request) -> HTMLResponse:
        """Handles GET request and returns the rendered table partial."""
        return await render_table(self.scheduler, request)


class TaskCreateController(Controller):
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
        func: Callable[..., Any] = import_callable(callable_path)
        trigger: Any = parse_trigger(trigger_type, trigger_value)

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
        return await render_table(self.scheduler, request)


class TaskBulkPauseController(Controller):
    """Handles pausing multiple tasks via an HTMX POST request."""

    def __init__(self, *, scheduler: AsyncIOScheduler) -> None:
        self.scheduler: AsyncIOScheduler = scheduler

    async def post(self, request: Request) -> HTMLResponse:
        """Processes a list of task IDs, pauses each one, and returns the updated task table."""
        form: Any = await request.form()
        ids: list[str] = json.loads(form.get("ids") or "[]")

        for task_id in ids:
            # Lookup task and store
            task: AsynczTask
            store_alias: str
            task, store_alias = self.scheduler.lookup_task(task_id, None)  # type: ignore

            # Pause by setting next_run_time to None
            task.update_task(next_run_time=None)

            # Persist state
            store_obj: BaseStore = self.scheduler.lookup_store(store_alias)  # type: ignore
            store_obj.update_task(task)

        return await render_table(self.scheduler, request)


class TaskBulkResumeController(Controller):
    """Handles resuming multiple paused tasks via an HTMX POST request."""

    def __init__(self, *, scheduler: AsyncIOScheduler) -> None:
        self.scheduler: AsyncIOScheduler = scheduler

    async def post(self, request: Request) -> HTMLResponse:
        """
        Processes a list of task IDs, resumes each one (or deletes if finished),
        and returns the updated task table.
        """
        form: Any = await request.form()
        ids: list[str] = json.loads(form.get("ids") or "[]")
        now: datetime = datetime.now(self.scheduler.timezone)

        for task_id in ids:
            # Lookup task
            task: AsynczTask
            store_alias: str
            task, store_alias = self.scheduler.lookup_task(task_id, None)  # type: ignore

            # Calculate next run time based on current time (None for last_run_time)
            next_run: datetime | None = task.trigger.get_next_trigger_time(  # type: ignore
                self.scheduler.timezone, None, now
            )

            if next_run:
                # Update task and persist state
                task.update_task(next_run_time=next_run)
                store_obj: BaseStore = self.scheduler.lookup_store(store_alias)  # type: ignore
                store_obj.update_task(task)
            else:
                # Schedule finished, delete task
                self.scheduler.delete_task(task.id, store_alias)

        return await render_table(self.scheduler, request)


class TaskBulkRemoveController(Controller):
    """Handles removing multiple tasks via an HTMX POST request."""

    def __init__(self, *, scheduler: AsyncIOScheduler) -> None:
        self.scheduler: AsyncIOScheduler = scheduler

    async def post(self, request: Request) -> HTMLResponse:
        """Processes a list of task IDs, removes each one, and returns the updated task table."""
        form: Any = await request.form()
        ids: list[str] = json.loads(form.get("ids") or "[]")

        for task_id in ids:
            # Note: delete_task handles store lookup internally when store_alias is None
            await self.scheduler.delete_task(task_id)  # type: ignore

        return await render_table(self.scheduler, request)


class TaskHXRunController(Controller):
    """Handles running a single task immediately, returning the updated table partial."""

    def __init__(self, *, scheduler: AsyncIOScheduler) -> None:
        self.scheduler: AsyncIOScheduler = scheduler

    async def post(self, request: Request) -> HTMLResponse:
        """Triggers the specified task to run immediately and returns the updated table partial."""
        task_id: str = request.path_params["task_id"]

        task: AsynczTask
        store_alias: str
        task, store_alias = self.scheduler.lookup_task(task_id, None)  # type: ignore

        now: datetime = datetime.now(self.scheduler.timezone)
        run_times: list[datetime] = task.get_run_times(self.scheduler.timezone, now)

        if not run_times:
            run_times = [now]

        executor: BaseExecutor = self.scheduler.lookup_executor(task.executor)  # type: ignore
        executor.send_task(task, run_times)

        last_run: datetime = run_times[-1]
        next_run: datetime | None = task.trigger.get_next_trigger_time(  # type: ignore
            self.scheduler.timezone, last_run, now
        )

        if next_run:
            task.update_task(next_run_time=next_run)
            store_obj: BaseStore = self.scheduler.lookup_store(store_alias)  # type: ignore
            store_obj.update_task(task)
        else:
            self.scheduler.delete_task(task.id, store_alias)

        return await render_table(self.scheduler, request)


class TaskHXPauseController(Controller):
    """Handles pausing a single task, returning the updated table partial."""

    def __init__(self, *, scheduler: AsyncIOScheduler) -> None:
        self.scheduler: AsyncIOScheduler = scheduler

    async def post(self, request: Request) -> HTMLResponse:
        """Pauses the specified task by setting next_run_time to None and returns the updated table partial."""
        task_id: str = request.path_params["task_id"]

        task: AsynczTask
        store_alias: str
        task, store_alias = self.scheduler.lookup_task(task_id, None)  # type: ignore

        task.update_task(next_run_time=None)

        store_obj: BaseStore = self.scheduler.lookup_store(store_alias)  # type: ignore
        store_obj.update_task(task)

        return await render_table(self.scheduler, request)


class TaskHXResumeController(Controller):
    """Handles resuming a single task, returning the updated table partial."""

    def __init__(self, *, scheduler: AsyncIOScheduler) -> None:
        self.scheduler: AsyncIOScheduler = scheduler

    async def post(self, request: Request) -> HTMLResponse:
        """Resumes the specified task by recalculating next_run_time and returns the updated table partial."""
        task_id: str = request.path_params["task_id"]

        task: AsynczTask
        store_alias: str
        task, store_alias = self.scheduler.lookup_task(task_id, None)  # type: ignore

        now: datetime = datetime.now(self.scheduler.timezone)
        next_run: datetime | None = task.trigger.get_next_trigger_time(  # type: ignore
            self.scheduler.timezone, None, now
        )

        if next_run:
            task.update_task(next_run_time=next_run)
            store_obj: BaseStore = self.scheduler.lookup_store(store_alias)  # type: ignore
            store_obj.update_task(task)
        else:
            self.scheduler.delete_task(task.id, store_alias)

        return await render_table(self.scheduler, request)


class TaskHXRemoveController(Controller):
    """Handles removing a single task, returning the updated table partial."""

    def __init__(self, *, scheduler: AsyncIOScheduler) -> None:
        self.scheduler: AsyncIOScheduler = scheduler

    async def post(self, request: Request) -> HTMLResponse:
        """Permanently removes the specified task and returns the updated task table."""
        task_id: str = request.path_params["task_id"]

        self.scheduler.delete_task(task_id)

        return await render_table(self.scheduler, request)
