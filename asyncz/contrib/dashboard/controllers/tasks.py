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
from asyncz.contrib.dashboard.audit import record_audit_event
from asyncz.contrib.dashboard.controllers._helpers import (
    build_task_dashboard_context,
    parse_ids_from_request_form,
    parse_trigger,
    render_table,
)
from asyncz.contrib.dashboard.controllers.logs import get_log_storage
from asyncz.contrib.dashboard.engine import templates
from asyncz.contrib.dashboard.history import get_run_history_storage
from asyncz.contrib.dashboard.messages import add_message
from asyncz.contrib.dashboard.mixins import DashboardMixin
from asyncz.exceptions import MaximumInstancesError, TaskLookupError
from asyncz.schedulers import AsyncIOScheduler
from asyncz.tasks.types import TaskType

_TRUE_VALUES = {"1", "true", "yes", "on"}
_FALSE_VALUES = {"0", "false", "no", "off"}


def _string_form_value(form: Any, key: str, default: str = "") -> str:
    value = form.get(key, default)
    if isinstance(value, bytes):
        return value.decode()
    return str(value)


def _json_text(value: Any) -> str:
    return json.dumps(value, indent=2, sort_keys=True)


def _task_update_snapshot(task: TaskType) -> dict[str, Any]:
    return {
        "name": task.name,
        "executor": task.executor,
        "callable_reference": task.fn_reference,
        "args": list(task.args),
        "kwargs": dict(task.kwargs),
        "coalesce": task.coalesce,
        "max_instances": task.max_instances,
        "mistrigger_grace_time": task.mistrigger_grace_time,
    }


def _build_update_diff(before: dict[str, Any], after: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        key: {"before": before.get(key), "after": after.get(key)}
        for key in before
        if before.get(key) != after.get(key)
    }


def _diff_rows(diff: dict[str, dict[str, Any]]) -> list[dict[str, str]]:
    return [
        {
            "field": field.replace("_", " ").title(),
            "before": _json_text(change["before"]),
            "after": _json_text(change["after"]),
        }
        for field, change in diff.items()
    ]


def _task_edit_form_from_task(task: TaskType) -> dict[str, str | bool]:
    return {
        "name": task.name or "",
        "callable_path": task.fn_reference or "",
        "args": _json_text(list(task.args)),
        "kwargs": _json_text(dict(task.kwargs)),
        "executor": task.executor or "default",
        "coalesce": "true" if task.coalesce else "false",
        "max_instances": str(task.max_instances),
        "mistrigger_grace_time": (
            "" if task.mistrigger_grace_time is None else str(task.mistrigger_grace_time)
        ),
        "clear_mistrigger_grace_time": task.mistrigger_grace_time is None,
    }


def _task_edit_form_from_post(form: Any) -> dict[str, str | bool]:
    return {
        "name": _string_form_value(form, "name").strip(),
        "callable_path": _string_form_value(form, "callable_path").strip(),
        "args": _string_form_value(form, "args").strip(),
        "kwargs": _string_form_value(form, "kwargs").strip(),
        "executor": _string_form_value(form, "executor").strip(),
        "coalesce": _string_form_value(form, "coalesce").strip().lower(),
        "max_instances": _string_form_value(form, "max_instances").strip(),
        "mistrigger_grace_time": _string_form_value(form, "mistrigger_grace_time").strip(),
        "clear_mistrigger_grace_time": form.get("clear_mistrigger_grace_time") is not None,
    }


def _parse_bool(value: str) -> bool:
    normalized = value.strip().lower()
    if normalized in _TRUE_VALUES:
        return True
    if normalized in _FALSE_VALUES:
        return False
    raise ValueError("coalesce must be true or false.")


def _parse_json_list(value: str) -> list[Any]:
    parsed = json.loads(value or "[]")
    if isinstance(parsed, str) or not isinstance(parsed, list):
        raise ValueError("args must be a JSON array.")
    return parsed


def _parse_json_object(value: str) -> dict[str, Any]:
    parsed = json.loads(value or "{}")
    if not isinstance(parsed, dict):
        raise ValueError("kwargs must be a JSON object.")
    return parsed


def _parse_positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise ValueError("max instances must be a positive integer.")
    return parsed


def _parse_mistrigger_grace_time(value: str) -> float | int | None:
    if not value:
        return None
    parsed = float(value)
    if parsed <= 0:
        raise ValueError("misfire grace time must be a positive number.")
    return int(parsed) if parsed.is_integer() else parsed


def _parse_task_edit_updates(form: Any, task: TaskType) -> tuple[dict[str, Any], list[str]]:
    values = _task_edit_form_from_post(form)
    updates: dict[str, Any] = {}
    errors: list[str] = []

    name = str(values["name"]).strip()
    if name:
        updates["name"] = name
    elif task.name and form.get("name") is not None:
        errors.append("name cannot be blank.")

    callable_path = str(values["callable_path"]).strip()
    if callable_path:
        updates["fn"] = callable_path
    elif task.fn_reference:
        errors.append("callable reference is required.")

    executor = str(values["executor"]).strip()
    if executor:
        updates["executor"] = executor
    else:
        errors.append("executor is required.")

    try:
        updates["args"] = _parse_json_list(str(values["args"]))
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        errors.append(str(exc))

    try:
        updates["kwargs"] = _parse_json_object(str(values["kwargs"]))
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        errors.append(str(exc))

    try:
        updates["coalesce"] = _parse_bool(str(values["coalesce"]))
    except ValueError as exc:
        errors.append(str(exc))

    try:
        updates["max_instances"] = _parse_positive_int(str(values["max_instances"]))
    except (TypeError, ValueError) as exc:
        errors.append(str(exc))

    try:
        if values["clear_mistrigger_grace_time"]:
            updates["mistrigger_grace_time"] = None
        else:
            updates["mistrigger_grace_time"] = _parse_mistrigger_grace_time(
                str(values["mistrigger_grace_time"])
            )
    except (TypeError, ValueError) as exc:
        errors.append(str(exc))

    return updates, errors


def _audit_task_action(
    action: str,
    task_id: str | None,
    *,
    status: str = "succeeded",
    message: str | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    record_audit_event(
        f"task.{action}",
        status=status,
        target_id=task_id,
        message=message,
        details=details,
    )


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
        """Render the main task page using the scheduler task inspection API."""
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
            _audit_task_action("run", task_id, message=f"Triggered task {task_id} manually.")
        except MaximumInstancesError as exc:
            add_message(request, "warning", str(exc))
            _audit_task_action("run", task_id, status="warning", message=str(exc))
        except TaskLookupError:
            _audit_task_action("run", task_id, status="failed", message="Task was not found.")
        return await self._redirect()


class TaskPauseController(_BaseTaskAction):
    """Handles pausing a task via a standard HTTP POST (non-HTMX)."""

    async def post(self, request: Request) -> Any:
        """Pause the specified task through the scheduler API."""
        task_id: str = request.path_params["task_id"]
        try:
            self.scheduler.pause_task(task_id)
            _audit_task_action("pause", task_id, message=f"Paused task {task_id}.")
        except TaskLookupError:
            _audit_task_action("pause", task_id, status="failed", message="Task was not found.")
        return await self._redirect()


class TaskResumeController(_BaseTaskAction):
    """Handles resuming a paused task via a standard HTTP POST (non-HTMX)."""

    async def post(self, request: Request) -> Any:
        """Resume the specified task through the scheduler API."""
        task_id: str = request.path_params["task_id"]
        try:
            self.scheduler.resume_task(task_id)
            _audit_task_action("resume", task_id, message=f"Resumed task {task_id}.")
        except TaskLookupError:
            _audit_task_action("resume", task_id, status="failed", message="Task was not found.")
        return await self._redirect()


class TaskRemoveController(_BaseTaskAction):
    """Handles removing a task via a standard HTTP POST (non-HTMX)."""

    async def post(self, request: Request) -> Any:
        """Permanently removes the specified task from its store."""
        task_id: str = request.path_params["task_id"]
        try:
            self.scheduler.delete_task(task_id)
            _audit_task_action("remove", task_id, message=f"Removed task {task_id}.")
        except TaskLookupError:
            _audit_task_action("remove", task_id, status="failed", message="Task was not found.")
        return await self._redirect()


class TaskTablePartialController(DashboardMixin, Controller):
    """Renders the HTML table fragment of tasks, used by HTMX for real-time updates."""

    def __init__(self, *, scheduler: AsyncIOScheduler) -> None:
        self.scheduler: AsyncIOScheduler = scheduler

    async def get(self, request: Request) -> HTMLResponse:
        """Render the filtered HTMX task table fragment."""
        context = await self.get_context_data(request)
        return await render_table(self.scheduler, request, context)


class TaskDetailController(DashboardMixin, Controller):
    """Render one task with related scheduler history and logs."""

    template_name: str = "tasks/detail.html"

    def __init__(self, *, scheduler: AsyncIOScheduler) -> None:
        self.scheduler: AsyncIOScheduler = scheduler

    async def _render(
        self,
        request: Request,
        *,
        task: TaskType | None,
        store_alias: str | None = None,
        status_code: int = 200,
    ) -> HTMLResponse:
        context = await self.get_context_data(
            request,
            title="Task Detail",
            page_header="Task Detail",
            active_page="tasks",
        )
        task_id = request.path_params["task_id"]
        preview = None
        recent_runs = []
        recent_logs = []
        info = None
        if task is not None:
            info = task.snapshot()
            with contextlib.suppress(Exception):
                preview = self.scheduler.preview_task_runs(task_id, count=5)
            recent_runs = get_run_history_storage().query(task_id=task_id, limit=6)
            recent_logs = list(get_log_storage().query(task_id=task_id, limit=6))

        context.update(
            {
                "task": task,
                "task_info": info,
                "store_alias": store_alias,
                "preview": preview,
                "recent_runs": recent_runs,
                "recent_logs": recent_logs,
                "args_json": _json_text(list(task.args)) if task else "[]",
                "kwargs_json": _json_text(dict(task.kwargs)) if task else "{}",
            }
        )
        return templates.get_template_response(
            request,
            self.template_name,
            context=context,
            status_code=status_code,
        )

    async def get(self, request: Request) -> HTMLResponse:
        task_id: str = request.path_params["task_id"]
        try:
            task, store_alias = self.scheduler.lookup_task(task_id, None)
        except TaskLookupError:
            return await self._render(request, task=None, status_code=404)
        return await self._render(request, task=task, store_alias=store_alias)


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
            _audit_task_action(
                "create",
                callable_path or None,
                status="failed",
                message=message,
                details={"callable_path": callable_path, "trigger_type": trigger_type},
            )
            context = await self.get_context_data(request)
            return await render_table(self.scheduler, request, context)

        # Add task to the scheduler
        task = self.scheduler.add_task(
            func,
            trigger=trigger,
            args=args,
            kwargs=kwargs,
            name=name,
            store=store_alias,
        )
        _audit_task_action(
            "create",
            task.id,
            message=f"Created task {task.name or task.id}.",
            details={
                "callable_path": callable_path,
                "trigger_type": trigger_type,
                "store": store_alias,
            },
        )

        # Return updated table partial (HTMX response)
        context = await self.get_context_data(request)
        return await render_table(self.scheduler, request, context)


class TaskEditController(DashboardMixin, Controller):
    """Handles previewing and applying safe task metadata updates."""

    template_name: str = "tasks/edit.html"

    def __init__(self, *, scheduler: AsyncIOScheduler) -> None:
        self.scheduler: AsyncIOScheduler = scheduler

    async def _render(
        self,
        request: Request,
        *,
        task: TaskType | None,
        store_alias: str | None = None,
        form: dict[str, str | bool] | None = None,
        diff: dict[str, dict[str, Any]] | None = None,
        errors: list[str] | None = None,
        applied: bool = False,
        status_code: int = 200,
    ) -> HTMLResponse:
        context = await self.get_context_data(
            request,
            title="Edit Task",
            page_header="Edit Task",
            active_page="tasks",
        )
        context.update(
            {
                "task": task,
                "store_alias": store_alias,
                "form": form or (_task_edit_form_from_task(task) if task else {}),
                "diff": diff or {},
                "diff_rows": _diff_rows(diff or {}),
                "errors": errors or [],
                "applied": applied,
            }
        )
        return templates.get_template_response(
            request,
            self.template_name,
            context=context,
            status_code=status_code,
        )

    def _lookup_task(self, task_id: str) -> tuple[TaskType, str | None]:
        task, store_alias = self.scheduler.lookup_task(task_id, None)
        return task, store_alias

    async def get(self, request: Request) -> HTMLResponse:
        """Render the task edit form with values from the live scheduler task."""
        task_id: str = request.path_params["task_id"]
        try:
            task, store_alias = self._lookup_task(task_id)
        except TaskLookupError:
            return await self._render(request, task=None, status_code=404)
        return await self._render(request, task=task, store_alias=store_alias)

    async def post(self, request: Request) -> HTMLResponse:
        """Validate, preview, or apply task metadata updates."""
        task_id: str = request.path_params["task_id"]
        try:
            task, store_alias = self._lookup_task(task_id)
        except TaskLookupError:
            _audit_task_action("update", task_id, status="failed", message="Task was not found.")
            return await self._render(request, task=None, status_code=404)

        form_data: Any = await request.form()
        intent = _string_form_value(form_data, "intent", "preview").strip().lower()
        form = _task_edit_form_from_post(form_data)
        updates, errors = _parse_task_edit_updates(form_data, task)
        before = _task_update_snapshot(task)
        diff: dict[str, dict[str, Any]] = {}

        if not errors:
            proposed = task.model_copy()
            try:
                proposed.update_task(scheduler=self.scheduler, **updates)
            except Exception as exc:
                errors.append(str(exc))
            else:
                diff = _build_update_diff(before, _task_update_snapshot(proposed))

        if errors:
            _audit_task_action(
                "update",
                task_id,
                status="failed",
                message="Task update validation failed.",
                details={"errors": errors},
            )
            return await self._render(
                request,
                task=task,
                store_alias=store_alias,
                form=form,
                diff=diff,
                errors=errors,
                status_code=400,
            )

        if intent != "apply" or not diff:
            return await self._render(
                request,
                task=task,
                store_alias=store_alias,
                form=form,
                diff=diff,
            )

        updated = self.scheduler.update_task(task_id, store_alias, **updates)
        _audit_task_action(
            "update",
            task_id,
            message=f"Updated task {updated.name or task_id}.",
            details={"store": store_alias, "diff": diff},
        )
        return await self._render(
            request,
            task=updated,
            store_alias=store_alias,
            form=_task_edit_form_from_task(updated),
            diff=diff,
            applied=True,
        )


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
                _audit_task_action("pause", task_id, message=f"Paused task {task_id}.")
            except TaskLookupError:
                _audit_task_action(
                    "pause", task_id, status="failed", message="Task was not found."
                )
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
                _audit_task_action("run", task_id, message=f"Triggered task {task_id} manually.")
            except MaximumInstancesError as exc:
                add_message(request, "warning", str(exc))
                _audit_task_action("run", task_id, status="warning", message=str(exc))
            except TaskLookupError:
                _audit_task_action("run", task_id, status="failed", message="Task was not found.")
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
                _audit_task_action("resume", task_id, message=f"Resumed task {task_id}.")
            except TaskLookupError:
                _audit_task_action(
                    "resume", task_id, status="failed", message="Task was not found."
                )
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
                _audit_task_action("remove", task_id, message=f"Removed task {task_id}.")
            except TaskLookupError:
                # Already removed or not found; keep operation idempotent.
                _audit_task_action(
                    "remove", task_id, status="failed", message="Task was not found."
                )
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
            _audit_task_action("run", task_id, message=f"Triggered task {task_id} manually.")
        except MaximumInstancesError as exc:
            add_message(request, "warning", str(exc))
            _audit_task_action("run", task_id, status="warning", message=str(exc))
        except TaskLookupError:
            _audit_task_action("run", task_id, status="failed", message="Task was not found.")

        context = await self.get_context_data(request)
        return await render_table(self.scheduler, request, context)


class TaskHXPauseController(DashboardMixin, Controller):
    """Handles pausing a single task, returning the updated table partial."""

    def __init__(self, *, scheduler: AsyncIOScheduler) -> None:
        self.scheduler: AsyncIOScheduler = scheduler

    async def post(self, request: Request) -> HTMLResponse:
        """Pause the specified task and return the refreshed task table."""
        task_id: str = request.path_params["task_id"]
        try:
            self.scheduler.pause_task(task_id)
            _audit_task_action("pause", task_id, message=f"Paused task {task_id}.")
        except TaskLookupError:
            _audit_task_action("pause", task_id, status="failed", message="Task was not found.")

        context = await self.get_context_data(request)
        return await render_table(self.scheduler, request, context)


class TaskHXResumeController(DashboardMixin, Controller):
    """Handles resuming a single task, returning the updated table partial."""

    def __init__(self, *, scheduler: AsyncIOScheduler) -> None:
        self.scheduler: AsyncIOScheduler = scheduler

    async def post(self, request: Request) -> HTMLResponse:
        """Resume the specified task and return the refreshed task table."""
        task_id: str = request.path_params["task_id"]
        try:
            self.scheduler.resume_task(task_id)
            _audit_task_action("resume", task_id, message=f"Resumed task {task_id}.")
        except TaskLookupError:
            _audit_task_action("resume", task_id, status="failed", message="Task was not found.")

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
            self.scheduler.delete_task(task_id)
            _audit_task_action("remove", task_id, message=f"Removed task {task_id}.")
        except TaskLookupError:
            _audit_task_action("remove", task_id, status="failed", message="Task was not found.")

        context = await self.get_context_data(request)
        return await render_table(self.scheduler, request, context)
