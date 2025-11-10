from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from datetime import datetime, timedelta
from typing import Any

from lilya.controllers import Controller
from lilya.requests import Request
from lilya.responses import HTMLResponse, RedirectResponse
from lilya.templating.controllers import TemplateController

from asyncz.cli.utils import import_callable
from asyncz.contrib.dashboard.controllers._helpers import (
    filter_items,
    parse_ids_from_request_form,
    parse_trigger,
    render_table,
    safe_lookup_executor,
    safe_lookup_store,
    serialize,
)
from asyncz.contrib.dashboard.mixins import DashboardMixin
from asyncz.exceptions import TaskLookupError
from asyncz.schedulers import AsyncIOScheduler
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

        # Simple server-side filter for the search box in the toolbar
        q: str | None = request.query_params.get("q") if request.query_params else None
        filtered: list[dict[str, Any]] = filter_items(items, q)

        ctx: dict[str, Any] = await self.get_context_data(request)
        ctx.update(
            {
                "title": "Tasks",
                "page_header": "Tasks",
                "active_page": "tasks",
                "tasks": filtered,
                "q": q or "",
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
        executor = safe_lookup_executor(self.scheduler, getattr(task, "executor", None))
        if executor is not None:
            executor.send_task(task, run_times)

        # Update schedule state
        last_run: datetime = run_times[-1]
        next_run: datetime | None = task.trigger.get_next_trigger_time(  # type: ignore
            self.scheduler.timezone, last_run, now
        )

        if next_run:
            # Update the task's next run time and persist the change
            task.update_task(next_run_time=next_run)
        else:
            # No further runs: keep task but mark as paused (do NOT delete)
            task.update_task(next_run_time=None)
        store_obj = safe_lookup_store(self.scheduler, store_alias, task.id)
        store_obj.update_task(task)

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
        store_obj = safe_lookup_store(self.scheduler, store_alias, task.id)
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
        else:
            # No further runs: keep task but mark as paused
            task.update_task(next_run_time=None)
        store_obj = safe_lookup_store(self.scheduler, store_alias, task.id)
        store_obj.update_task(task)

        return await self._redirect()


class TaskRemoveController(_BaseTaskAction):
    """Handles removing a task via a standard HTTP POST (non-HTMX)."""

    async def post(self, request: Request) -> Any:
        """Permanently removes the specified task from its store."""
        task_id: str = request.path_params["task_id"]

        # Lookup to get store alias
        _, store_alias = self.scheduler.lookup_task(task_id, None)

        self.scheduler.delete_task(task_id, store_alias)

        return await self._redirect()


class TaskTablePartialController(DashboardMixin, Controller):
    """Renders the HTML table fragment of tasks, used by HTMX for real-time updates."""

    def __init__(self, *, scheduler: AsyncIOScheduler) -> None:
        self.scheduler: AsyncIOScheduler = scheduler

    async def get(self, request: Request) -> HTMLResponse:
        """Handles GET request and returns the rendered table partial (with search)."""
        tasks: Sequence[AsynczTask] = self.scheduler.get_tasks()  # type: ignore
        items: list[dict[str, Any]] = [serialize(t) for t in tasks]
        q: str | None = request.query_params.get("q") if request.query_params else None
        filtered: list[dict[str, Any]] = filter_items(items, q)

        context = await self.get_context_data(request)
        context.update({"tasks": filtered, "q": q or ""})
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
            # Lookup task and store
            task: AsynczTask
            store_alias: str
            task, store_alias = self.scheduler.lookup_task(task_id, None)  # type: ignore

            # Pause by setting next_run_time to None
            task.update_task(next_run_time=None)

            # Persist state
            store_obj = safe_lookup_store(self.scheduler, store_alias, task.id)
            store_obj.update_task(task)

        context = await self.get_context_data(request)
        return await render_table(self.scheduler, request, context)


class TaskBulkRunController(DashboardMixin, Controller):
    """
    Handles triggering multiple scheduled tasks to run immediately (bulk run action).

    Instead of fiddling with next_run_time (which can cause tight rescheduling loops
    around "now"), we mirror the single-row run flow: compute due run times,
    send to the executor, and then advance (or remove) the task based on the
    trigger's next time. This makes the action deterministic and prevents loops.
    """

    def __init__(self, *, scheduler: AsyncIOScheduler) -> None:
        self.scheduler: AsyncIOScheduler = scheduler

    async def post(self, request: Request) -> HTMLResponse:
        form: Any = await request.form()
        ids: list[str] = parse_ids_from_request_form(form)

        now: datetime = datetime.now(self.scheduler.timezone)

        for task_id in ids:
            try:
                # Lookup the task and its store
                task: AsynczTask
                store_alias: str
                task, store_alias = self.scheduler.lookup_task(task_id, None)  # type: ignore

                # Determine run times; force an immediate one-off run if not yet due
                run_times: list[datetime] = task.get_run_times(self.scheduler.timezone, now)
                if not run_times:
                    run_times = [now]

                # Submit to executor
                executor = safe_lookup_executor(self.scheduler, getattr(task, "executor", None))
                if executor is not None:
                    executor.send_task(task, run_times)

                # Advance schedule and persist (with anti-loop guard)
                last_run: datetime = run_times[-1]
                next_run: datetime | None = task.trigger.get_next_trigger_time(  # type: ignore
                    self.scheduler.timezone, last_run, now
                )
                if next_run is not None and next_run <= now:
                    next_run = now + timedelta(milliseconds=5)

                if next_run:
                    task.update_task(next_run_time=next_run)
                else:
                    # No further runs: mark paused instead of deleting
                    task.update_task(next_run_time=None)
                store_obj = safe_lookup_store(self.scheduler, store_alias, task.id)
                store_obj.update_task(task)
            except Exception:
                # Ignore bad IDs or transient store issues; table will reflect actual state
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
            else:
                # No further runs: mark paused
                task.update_task(next_run_time=None)
            store_obj = safe_lookup_store(self.scheduler, store_alias, task.id)
            store_obj.update_task(task)

        context = await self.get_context_data(request)
        return await render_table(self.scheduler, request, context)


class TaskBulkRemoveController(DashboardMixin, Controller):
    """Handles removing multiple tasks via an HTMX POST request."""

    def __init__(self, *, scheduler: AsyncIOScheduler) -> None:
        self.scheduler: AsyncIOScheduler = scheduler

    async def post(self, request: Request) -> HTMLResponse:
        """Processes a list of task IDs, removes each one, and returns the updated task table."""
        form: Any = await request.form()
        raw_ids = form.get("ids")

        # Accept JSON-encoded list, a Python list from the form parser, or a comma-separated string.
        ids: list[str]
        if isinstance(raw_ids, list):
            ids = [str(x) for x in raw_ids]
        elif isinstance(raw_ids, str):
            raw = raw_ids.strip()
            try:
                # Try JSON first (e.g. '["id1", "id2"]')
                parsed = json.loads(raw)
                ids = [str(x) for x in parsed] if isinstance(parsed, list) else [str(parsed)]
            except Exception:  # noqa
                # Fallback: comma/space separated string
                ids = [s for s in (x.strip() for x in raw.split(",")) if s]
        else:
            ids = []

        # De-duplicate while preserving order
        seen = set()
        ids = [x for x in ids if not (x in seen or seen.add(x))]  # type: ignore

        for task_id in ids:
            try:
                # Look up to get the correct store alias, then delete from that store.
                _, store_alias = self.scheduler.lookup_task(task_id, None)
                self.scheduler.delete_task(task_id, store_alias)
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
        """Triggers the specified task to run immediately and returns the updated table partial."""
        task_id: str = request.path_params["task_id"]

        task: AsynczTask
        store_alias: str
        task, store_alias = self.scheduler.lookup_task(task_id, None)  # type: ignore

        # Use a timezone-aware "now"
        now: datetime = datetime.now(self.scheduler.timezone)

        # Determine due run times; if nothing is due yet, force a one-off immediate run
        run_times: list[datetime] = task.get_run_times(self.scheduler.timezone, now)
        if not run_times:
            run_times = [now]

        # Submit task to the executor (one-shot run for the calculated times)
        executor = safe_lookup_executor(self.scheduler, getattr(task, "executor", None))
        if executor is not None:
            executor.send_task(task, run_times)

        # Advance the schedule deterministically to avoid tight reschedule loops
        last_run: datetime = run_times[-1]
        next_run: datetime | None = task.trigger.get_next_trigger_time(  # type: ignore
            self.scheduler.timezone, last_run, now
        )

        # Guard: never persist a next_run_time that is <= now, otherwise the scheduler
        # will wake immediately and can create a tight loop under test load.
        if next_run is not None and next_run <= now:
            next_run = now + timedelta(milliseconds=5)

        if next_run:
            task.update_task(next_run_time=next_run)
        else:
            # No further runs: keep task but mark as paused
            task.update_task(next_run_time=None)
        store_obj = safe_lookup_store(self.scheduler, store_alias, task.id)
        store_obj.update_task(task)

        context = await self.get_context_data(request)
        return await render_table(self.scheduler, request, context)


class TaskHXPauseController(DashboardMixin, Controller):
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

        store_obj = safe_lookup_store(self.scheduler, store_alias, task.id)
        store_obj.update_task(task)

        context = await self.get_context_data(request)
        return await render_table(self.scheduler, request, context)


class TaskHXResumeController(DashboardMixin, Controller):
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
        else:
            # No further runs: mark paused
            task.update_task(next_run_time=None)
        store_obj = safe_lookup_store(self.scheduler, store_alias, task.id)
        store_obj.update_task(task)

        context = await self.get_context_data(request)
        return await render_table(self.scheduler, request, context)


class TaskHXRemoveController(DashboardMixin, Controller):
    """Handles removing a single task, returning the updated table partial."""

    def __init__(self, *, scheduler: AsyncIOScheduler) -> None:
        self.scheduler: AsyncIOScheduler = scheduler

    async def post(self, request: Request) -> HTMLResponse:
        """Permanently removes the specified task and returns the updated task table."""
        task_id: str = request.path_params["task_id"]

        try:
            # Resolve store alias first to ensure we remove from the correct store.
            _, store_alias = self.scheduler.lookup_task(task_id, None)
            self.scheduler.delete_task(task_id, store_alias)
        except TaskLookupError:
            # If it's already gone, just refresh the table.
            ...

        context = await self.get_context_data(request)
        return await render_table(self.scheduler, request, context)
