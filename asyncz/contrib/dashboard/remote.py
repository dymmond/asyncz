"""
Remote scheduler control surfaces for split app and worker deployments.

The worker process mounts `create_remote_scheduler_app(...)` beside the live
scheduler. The app process passes `RemoteSchedulerClient(...)` to `AsynczAdmin`
so dashboard reads and task actions travel over HTTP to the worker.
"""

from __future__ import annotations

import base64
import json
import pickle
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Mapping
from datetime import datetime
from enum import Enum
from typing import Any

from lilya.requests import Request
from lilya.responses import JSONResponse
from lilya.routing import RoutePath, Router

from asyncz.exceptions import (
    AsynczException,
    MaximumInstancesError,
    SchedulerNotRunningError,
    TaskLookupError,
)
from asyncz.schedulers.inspection import SchedulerInfo, SchedulerInstanceInfo
from asyncz.schedulers.types import SchedulerType
from asyncz.tasks.inspection import TaskInfo, TaskRunPreview
from asyncz.triggers.types import TriggerType
from asyncz.typing import Undefined, undefined
from asyncz.utils import obj_to_ref

Transport = Callable[
    [str, str, dict[str, Any] | None, dict[str, str], dict[str, Any] | None],
    tuple[int, dict[str, Any]],
]


class RemoteSchedulerError(AsynczException):
    """
    Raised when a remote scheduler control request fails.

    The error represents transport failures, unsupported remote payloads, or
    worker-side exceptions that do not map to one of Asyncz's existing scheduler
    exception classes.
    """


class RemoteTask:
    """
    Snapshot-backed task proxy used by the remote dashboard client.

    The app process cannot safely hold a live worker task object. This proxy
    exposes the task attributes the dashboard reads and supports local metadata
    mutation for edit previews before the final update is sent to the worker.
    """

    def __init__(self, info: TaskInfo) -> None:
        """
        Build a remote task proxy from an immutable task snapshot.

        The snapshot remains the source of truth for read-only scheduler state
        such as the current schedule state, trigger description, and next run
        time.
        """

        self._info = info
        self.id = info.id
        self.name = info.name
        self.fn = None
        self.fn_reference = info.callable_reference
        self.args = tuple(info.args)
        self.kwargs = dict(info.kwargs)
        self.coalesce = info.coalesce
        self.max_instances = info.max_instances
        self.mistrigger_grace_time = info.mistrigger_grace_time
        self.executor = info.executor
        self.store_alias = info.store_alias
        self.next_run_time = info.next_run_time
        self.pending = info.pending
        self.submitted = info.submitted
        self.trigger = info.trigger_description

    @property
    def paused(self) -> bool:
        """
        Return whether the remote task snapshot is paused.

        This mirrors the local `Task.paused` property without requiring access
        to the worker process task object.
        """

        return self._info.paused

    def model_copy(self) -> RemoteTask:
        """
        Return a copy of this proxy for dashboard edit previews.

        The dashboard mutates the copy to compute before/after differences while
        leaving the original snapshot unchanged until the worker accepts the
        update.
        """

        return RemoteTask(self.snapshot())

    def update_task(self, *, scheduler: Any = None, **updates: Any) -> RemoteTask:
        """
        Apply local metadata updates for preview rendering.

        Worker-side validation still runs when the dashboard applies the update.
        This local pass catches simple shape errors and lets the preview table
        show the same fields as the in-process scheduler path.
        """

        if "id" in updates:
            raise ValueError("The task ID may not be changed.")
        if "name" in updates:
            name = updates.pop("name")
            if name is not None and (not name or not isinstance(name, str)):
                raise TypeError("name must be a non empty string.")
            if name is not None:
                self.name = name
        if "fn" in updates:
            fn = updates.pop("fn")
            if not isinstance(fn, str):
                fn = obj_to_ref(fn)
            self.fn_reference = fn
        if "args" in updates:
            args = updates.pop("args")
            if isinstance(args, str) or not isinstance(args, list | tuple):
                raise TypeError("args must be a non-string iterable.")
            self.args = tuple(args)
        if "kwargs" in updates:
            kwargs = updates.pop("kwargs")
            if isinstance(kwargs, str) or not isinstance(kwargs, Mapping):
                raise TypeError("kwargs must be a dict-like object.")
            self.kwargs = dict(kwargs)
        if "executor" in updates:
            executor = updates.pop("executor")
            if not isinstance(executor, str):
                raise TypeError("executor must be a string.")
            self.executor = executor
        if "coalesce" in updates:
            self.coalesce = bool(updates.pop("coalesce"))
        if "max_instances" in updates:
            max_instances = updates.pop("max_instances")
            if not isinstance(max_instances, int) or max_instances <= 0:
                raise TypeError("max_instances must be a positive integer.")
            self.max_instances = max_instances
        if "mistrigger_grace_time" in updates:
            mistrigger_grace_time = updates.pop("mistrigger_grace_time")
            if mistrigger_grace_time is not None and (
                not isinstance(mistrigger_grace_time, int | float) or mistrigger_grace_time <= 0
            ):
                raise TypeError(
                    "mistrigger_grace_time must be either None or a positive float/integer."
                )
            self.mistrigger_grace_time = mistrigger_grace_time
        if updates:
            raise AttributeError(
                f"The following are not modifiable attributes of RemoteTask: {', '.join(updates)}."
            )
        return self

    def snapshot(self) -> TaskInfo:
        """
        Return an immutable task snapshot reflecting local proxy metadata.

        The schedule and trigger fields still come from the latest worker
        snapshot. Editable metadata reflects any preview-only mutations applied
        to this proxy.
        """

        return self._info.model_copy(
            update={
                "name": self.name,
                "callable_reference": self.fn_reference,
                "executor": self.executor,
                "store_alias": self.store_alias,
                "args": tuple(self.args),
                "kwargs": dict(self.kwargs),
                "coalesce": self.coalesce,
                "max_instances": self.max_instances,
                "mistrigger_grace_time": self.mistrigger_grace_time,
            }
        )

    def __repr__(self) -> str:
        """
        Return a compact representation for debugging remote dashboard state.

        The representation intentionally mirrors the local task representation
        enough to make logs and failed assertions readable.
        """

        return f"<RemoteTask (id={self.id} name={self.name})>"


def _dump_json(value: Any) -> Any:
    """
    Convert Asyncz models and common Python values into JSON-compatible data.

    The remote control API is intentionally JSON-based for inspectable control
    traffic. Values that are not JSON-compatible should be kept out of remote
    dashboard operations.
    """

    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, tuple | list):
        return [_dump_json(item) for item in value]
    if isinstance(value, Mapping):
        return {str(key): _dump_json(item) for key, item in value.items()}
    return value


def _encode_trigger(trigger: TriggerType) -> str:
    """
    Serialize a trigger object for a trusted remote control request.

    This path is used only when the dashboard passes an already-built trigger
    instance. The remote control endpoint must be protected and private because
    trigger pickles are not an untrusted input format.
    """

    return base64.b64encode(pickle.dumps(trigger)).decode("ascii")


def _decode_trigger(value: str) -> TriggerType:
    """
    Restore a trigger object sent by a trusted remote dashboard client.

    The worker receives this only after token validation. Deployments must not
    expose the remote control endpoint to untrusted clients.
    """

    return pickle.loads(base64.b64decode(value.encode("ascii")))


def _success(data: Any = None) -> JSONResponse:
    """
    Build a successful remote control JSON response.

    Every response uses a top-level `data` field so clients can distinguish
    successful `None` results from error payloads.
    """

    return JSONResponse({"data": _dump_json(data)})


def _error(exc: Exception, *, status_code: int = 500, task_id: str | None = None) -> JSONResponse:
    """
    Build a structured error response for remote control failures.

    Known Asyncz exception types are preserved by name so clients can translate
    worker-side failures back into local exceptions.
    """

    payload: dict[str, Any] = {
        "error": exc.__class__.__name__,
        "message": str(exc),
    }
    if task_id is not None:
        payload["task_id"] = task_id
    if isinstance(exc, MaximumInstancesError):
        payload["task_id"] = getattr(exc, "task_id", task_id)
        payload["max_instances"] = getattr(exc, "total", None)
    return JSONResponse(payload, status_code=status_code)


async def _json_body(request: Request) -> dict[str, Any]:
    """
    Read a JSON request body into a dictionary.

    Empty bodies are accepted for POST-style action endpoints that only need path
    parameters.
    """

    try:
        body = await request.json()
    except json.JSONDecodeError:
        return {}
    if body is None:
        return {}
    if not isinstance(body, dict):
        raise ValueError("Remote scheduler payloads must be JSON objects.")
    return body


def _require_token(request: Request, token: str | None) -> JSONResponse | None:
    """
    Validate the optional remote control token.

    The token is deliberately simple because Asyncz should not own a full auth
    system here. Production deployments should place this endpoint behind their
    normal private network and service authentication controls.
    """

    if token is None:
        return None
    if request.headers.get("x-asyncz-remote-token") == token:
        return None
    return JSONResponse(
        {"error": "Unauthorized", "message": "Invalid remote token."}, status_code=401
    )


def create_remote_scheduler_app(scheduler: SchedulerType, *, token: str | None = None) -> Router:
    """
    Create a worker-side ASGI control app for a scheduler.

    Mount this application in the process that owns and starts the scheduler.
    A dashboard running in another process can then use `RemoteSchedulerClient`
    to forward management operations to this worker.
    """

    async def info(request: Request) -> JSONResponse:
        """
        Return scheduler-level operational metadata.

        The response is built from the same scheduler inspection API used by the
        in-process dashboard.
        """

        if response := _require_token(request, token):
            return response
        return _success(scheduler.get_scheduler_info())

    async def instances(request: Request) -> JSONResponse:
        """
        Return scheduler instance metadata visible to the worker.

        The worker remains the authority for its runtime identity and lifecycle
        state.
        """

        if response := _require_token(request, token):
            return response
        return _success(list(scheduler.get_scheduler_instance_infos()))

    async def tasks(request: Request) -> JSONResponse:
        """
        Return filtered task snapshots from the worker scheduler.

        Query parameters mirror `scheduler.get_task_infos(...)` so the dashboard
        can reuse its existing filtering and sorting behavior.
        """

        if response := _require_token(request, token):
            return response
        params = request.query_params
        descending = str(params.get("descending", "")).lower() in {"1", "true", "yes"}
        try:
            return _success(
                scheduler.get_task_infos(
                    store=params.get("store") or None,
                    schedule_state=params.get("schedule_state") or None,
                    executor=params.get("executor") or None,
                    trigger=params.get("trigger") or None,
                    q=params.get("q") or None,
                    sort_by=params.get("sort_by") or "next_run_time",
                    descending=descending,
                )
            )
        except Exception as exc:
            return _error(exc, status_code=400)

    async def task_detail(request: Request) -> JSONResponse:
        """
        Return one task snapshot from the worker scheduler.

        A missing task returns a typed 404 payload so the dashboard can render
        its existing not-found state.
        """

        if response := _require_token(request, token):
            return response
        task_id = request.path_params["task_id"]
        task = scheduler.get_task_info(task_id, request.query_params.get("store") or None)
        if task is None:
            return _error(TaskLookupError(task_id), status_code=404, task_id=task_id)
        return _success(task)

    async def preview(request: Request) -> JSONResponse:
        """
        Return upcoming run times for one worker task.

        The worker performs trigger calculations so the app process does not need
        trigger objects or scheduler-local timezone state.
        """

        if response := _require_token(request, token):
            return response
        task_id = request.path_params["task_id"]
        count = int(request.query_params.get("count") or 5)
        result = scheduler.preview_task_runs(
            task_id,
            request.query_params.get("store") or None,
            count=count,
        )
        if result is None:
            return _error(TaskLookupError(task_id), status_code=404, task_id=task_id)
        return _success(result)

    async def add_task(request: Request) -> JSONResponse:
        """
        Create a task through the worker scheduler.

        The worker imports the callable reference and owns trigger construction,
        persistence, and validation.
        """

        if response := _require_token(request, token):
            return response
        body = await _json_body(request)
        trigger: Any
        trigger_args = dict(body.get("trigger_args") or {})
        if body.get("trigger_pickle"):
            trigger = _decode_trigger(str(body["trigger_pickle"]))
        else:
            trigger = body.get("trigger")
        kwargs = {
            key: body[key]
            for key in (
                "id",
                "name",
                "args",
                "kwargs",
                "mistrigger_grace_time",
                "coalesce",
                "max_instances",
                "next_run_time",
                "store",
                "executor",
                "replace_existing",
            )
            if key in body
        }
        try:
            task = scheduler.add_task(body.get("fn"), trigger=trigger, **kwargs, **trigger_args)
        except Exception as exc:
            return _error(exc, status_code=400)
        return _success(task.snapshot())

    async def update_task(request: Request) -> JSONResponse:
        """
        Update a worker task and return its latest snapshot.

        The worker scheduler remains responsible for validation, persistence,
        and wakeup behavior after the update.
        """

        if response := _require_token(request, token):
            return response
        task_id = request.path_params["task_id"]
        body = await _json_body(request)
        try:
            task = scheduler.update_task(
                task_id, body.get("store"), **dict(body.get("updates") or {})
            )
        except TaskLookupError as exc:
            return _error(exc, status_code=404, task_id=task_id)
        except Exception as exc:
            return _error(exc, status_code=400, task_id=task_id)
        return _success(task.snapshot())

    async def task_action(request: Request) -> JSONResponse:
        """
        Run, pause, resume, or remove a worker task.

        These operations must execute in the worker process because only that
        process owns the active scheduler and executors.
        """

        if response := _require_token(request, token):
            return response
        task_id = request.path_params["task_id"]
        action = request.path_params["action"]
        body = await _json_body(request)
        store = body.get("store")
        try:
            if action == "run":
                task = scheduler.run_task(
                    task_id,
                    store,
                    force=bool(body.get("force", True)),
                    remove_finished=bool(body.get("remove_finished", True)),
                )
                return _success(task.snapshot() if task is not None else None)
            if action == "pause":
                return _success(scheduler.pause_task(task_id, store).snapshot())
            if action == "resume":
                task = scheduler.resume_task(task_id, store)
                return _success(task.snapshot() if task is not None else None)
            if action == "remove":
                scheduler.delete_task(task_id, store)
                return _success(None)
        except TaskLookupError as exc:
            return _error(exc, status_code=404, task_id=task_id)
        except SchedulerNotRunningError as exc:
            return _error(exc, status_code=409, task_id=task_id)
        except MaximumInstancesError as exc:
            return _error(exc, status_code=409, task_id=task_id)
        except Exception as exc:
            return _error(exc, status_code=400, task_id=task_id)
        return _error(ValueError(f"Unsupported task action: {action}"), status_code=404)

    return Router(
        routes=[
            RoutePath("/info", info, methods=["GET"], name="info"),
            RoutePath("/instances", instances, methods=["GET"], name="instances"),
            RoutePath("/tasks", tasks, methods=["GET"], name="tasks"),
            RoutePath("/tasks", add_task, methods=["POST"], name="add_task"),
            RoutePath("/tasks/{task_id:str}", task_detail, methods=["GET"], name="task"),
            RoutePath("/tasks/{task_id:str}", update_task, methods=["PATCH"], name="update_task"),
            RoutePath(
                "/tasks/{task_id:str}/preview",
                preview,
                methods=["GET"],
                name="preview_task",
            ),
            RoutePath(
                "/tasks/{task_id:str}/{action:str}",
                task_action,
                methods=["POST"],
                name="task_action",
            ),
        ],
    )


class RemoteSchedulerClient:
    """
    Dashboard-side scheduler proxy that talks to a worker control app.

    Use this in the app process when the scheduler is owned by a separate worker.
    The client implements the scheduler inspection and task-control methods the
    dashboard uses, while all execution stays in the worker.
    """

    is_remote = True

    def __init__(
        self,
        base_url: str | None = None,
        *,
        token: str | None = None,
        transport: Transport | None = None,
    ) -> None:
        """
        Configure the remote scheduler client.

        Provide `base_url` for real HTTP communication, or `transport` in tests
        and embedded deployments that need to call an ASGI test client directly.
        """

        if base_url is None and transport is None:
            raise ValueError("RemoteSchedulerClient requires base_url or transport.")
        self.base_url = base_url.rstrip("/") if base_url else None
        self.token = token
        self.transport = transport

    @property
    def running(self) -> bool:
        """
        Return whether the worker scheduler reports itself as running.

        This property mirrors the local scheduler shortcut used by dashboard
        code and derives the value from the worker's scheduler snapshot.
        """

        return self.get_scheduler_info().running

    def _headers(self) -> dict[str, str]:
        """
        Return HTTP headers for a remote scheduler request.

        The optional token header is the only authentication mechanism owned by
        this helper. Deployments can still layer stronger service auth around it.
        """

        headers = {"content-type": "application/json"}
        if self.token is not None:
            headers["x-asyncz-remote-token"] = self.token
        return headers

    def _urllib_request(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None,
        headers: dict[str, str],
        query: dict[str, Any] | None,
    ) -> tuple[int, dict[str, Any]]:
        """
        Execute a remote request with the Python standard library.

        Asyncz avoids adding another runtime dependency for this small control
        client. Tests can bypass this path with a custom transport.
        """

        assert self.base_url is not None
        url = f"{self.base_url}{path}"
        if query:
            url = f"{url}?{urllib.parse.urlencode(query)}"
        data = None if payload is None else json.dumps(_dump_json(payload)).encode()
        request = urllib.request.Request(url, data=data, method=method, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                body = response.read().decode() or "{}"
                return response.status, json.loads(body)
        except urllib.error.HTTPError as exc:
            body = exc.read().decode() or "{}"
            return exc.code, json.loads(body)
        except urllib.error.URLError as exc:
            raise RemoteSchedulerError(f"Remote scheduler request failed: {exc}") from exc

    def _request(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
        *,
        query: dict[str, Any] | None = None,
    ) -> Any:
        """
        Send one control request and return the response `data` field.

        Worker-side errors are translated back into local Asyncz exceptions where
        the dashboard already has specific handling.
        """

        headers = self._headers()
        if self.transport is not None:
            status_code, response = self.transport(method, path, payload, headers, query)
        else:
            status_code, response = self._urllib_request(method, path, payload, headers, query)
        if status_code < 400:
            return response.get("data")
        self._raise_remote_error(response)

    def _raise_remote_error(self, response: dict[str, Any]) -> None:
        """
        Translate a worker error payload into a local exception.

        Known scheduler errors keep their existing exception type so dashboard
        controllers continue to handle task lookup and concurrency failures.
        """

        error = response.get("error")
        message = str(response.get("message") or error or "Remote scheduler error.")
        task_id = response.get("task_id")
        if error == "TaskLookupError":
            raise TaskLookupError(task_id)
        if error == "SchedulerNotRunningError":
            raise SchedulerNotRunningError()
        if error == "MaximumInstancesError":
            raise MaximumInstancesError(
                str(task_id or "unknown"),
                int(response.get("max_instances") or 0),
            )
        if error == "ValueError":
            raise ValueError(message)
        raise RemoteSchedulerError(message)

    def _task_from_data(self, data: dict[str, Any] | None) -> RemoteTask | None:
        """
        Convert remote task snapshot data into a task proxy.

        `None` is preserved for operations such as run or resume that can remove
        a finished task.
        """

        if data is None:
            return None
        return RemoteTask(TaskInfo.model_validate(data))

    def get_scheduler_info(self) -> SchedulerInfo:
        """
        Fetch scheduler metadata from the worker.

        The returned object is the same `SchedulerInfo` projection used by the
        local scheduler path.
        """

        return SchedulerInfo.model_validate(self._request("GET", "/info"))

    def get_scheduler_instance_infos(self) -> tuple[SchedulerInstanceInfo, ...]:
        """
        Fetch worker scheduler instance metadata.

        The app process reports what the worker exposes; it does not synthesize a
        local scheduler identity.
        """

        data = self._request("GET", "/instances")
        return tuple(SchedulerInstanceInfo.model_validate(item) for item in data)

    def get_task_infos(
        self,
        store: str | None = None,
        *,
        schedule_state: Any = None,
        executor: str | None = None,
        trigger: str | None = None,
        q: str | None = None,
        sort_by: str = "next_run_time",
        descending: bool = False,
    ) -> list[TaskInfo]:
        """
        Fetch filtered task snapshots from the worker.

        Parameters mirror `AsyncIOScheduler.get_task_infos(...)` so the dashboard
        can use the same helper code for local and remote schedulers.
        """

        query = {
            "store": store,
            "schedule_state": getattr(schedule_state, "value", schedule_state),
            "executor": executor,
            "trigger": trigger,
            "q": q,
            "sort_by": sort_by,
            "descending": str(descending).lower(),
        }
        data = self._request(
            "GET",
            "/tasks",
            query={key: value for key, value in query.items() if value not in (None, "")},
        )
        return [TaskInfo.model_validate(item) for item in data]

    def get_task_info(self, task_id: str, store: str | None = None) -> TaskInfo | None:
        """
        Fetch one task snapshot from the worker.

        Missing tasks return `None` to match the local scheduler inspection API.
        """

        try:
            data = self._request(
                "GET",
                f"/tasks/{urllib.parse.quote(task_id, safe='')}",
                query={"store": store} if store else None,
            )
        except TaskLookupError:
            return None
        return TaskInfo.model_validate(data)

    def get_task(self, task_id: str, store: str | None = None) -> RemoteTask | None:
        """
        Fetch one task as a remote task proxy.

        The proxy is suitable for dashboard read and edit-preview operations but
        does not execute task logic in the app process.
        """

        info = self.get_task_info(task_id, store)
        return RemoteTask(info) if info is not None else None

    def lookup_task(self, task_id: str, store: str | None = None) -> tuple[RemoteTask, str | None]:
        """
        Fetch one task or raise `TaskLookupError`.

        This mirrors the local scheduler method used by dashboard detail and edit
        controllers.
        """

        task = self.get_task(task_id, store)
        if task is None:
            raise TaskLookupError(task_id)
        return task, task.store_alias

    def preview_task_runs(
        self,
        task_id: str,
        store: str | None = None,
        *,
        count: int = 5,
        now: datetime | None = None,
    ) -> TaskRunPreview | None:
        """
        Ask the worker to calculate upcoming run times.

        The worker owns trigger instances and timezone behavior, so preview
        calculation stays in the scheduler process.
        """

        query: dict[str, Any] = {"count": count}
        if store:
            query["store"] = store
        if now is not None:
            query["now"] = now.isoformat()
        try:
            data = self._request(
                "GET",
                f"/tasks/{urllib.parse.quote(task_id, safe='')}/preview",
                query=query,
            )
        except TaskLookupError:
            return None
        return TaskRunPreview.model_validate(data)

    def add_task(
        self,
        fn_or_task: Any = None,
        trigger: Any = None,
        args: Any = None,
        kwargs: Any = None,
        id: str | None = None,
        name: str | None = None,
        mistrigger_grace_time: int | float | Undefined | None = undefined,
        coalesce: bool | Undefined = undefined,
        max_instances: int | Undefined | None = undefined,
        next_run_time: datetime | str | Undefined | None = undefined,
        store: str | Undefined | None = None,
        executor: str | Undefined | None = None,
        replace_existing: bool = False,
        fn: Any = None,
        **trigger_args: Any,
    ) -> RemoteTask:
        """
        Create a task through the worker scheduler.

        Callable objects are converted to textual references before crossing the
        remote boundary. Trigger objects are serialized for a trusted private
        control request.
        """

        if fn is not None:
            fn_or_task = fn
        if not isinstance(fn_or_task, str):
            fn_or_task = obj_to_ref(fn_or_task)
        payload: dict[str, Any] = {
            "fn": fn_or_task,
            "args": list(args or ()),
            "kwargs": dict(kwargs or {}),
            "replace_existing": replace_existing,
        }
        if isinstance(trigger, str) or trigger is None:
            payload["trigger"] = trigger
            payload["trigger_args"] = trigger_args
        else:
            payload["trigger_pickle"] = _encode_trigger(trigger)
        for key, value in {
            "id": id,
            "name": name,
            "mistrigger_grace_time": mistrigger_grace_time,
            "coalesce": coalesce,
            "max_instances": max_instances,
            "next_run_time": next_run_time,
            "store": store,
            "executor": executor,
        }.items():
            if value is not undefined and value is not None:
                payload[key] = value
        data = self._request("POST", "/tasks", payload)
        task = self._task_from_data(data)
        assert task is not None
        return task

    def update_task(self, task_id: Any, store: str | None = None, **updates: Any) -> RemoteTask:
        """
        Update task metadata through the worker scheduler.

        The worker validates callable references, args, kwargs, concurrency
        limits, and persistence changes before returning the latest snapshot.
        """

        if isinstance(task_id, RemoteTask):
            task_id = task_id.id
        data = self._request(
            "PATCH",
            f"/tasks/{urllib.parse.quote(str(task_id), safe='')}",
            {"store": store, "updates": updates},
        )
        task = self._task_from_data(data)
        assert task is not None
        return task

    def run_task(
        self,
        task_id: Any,
        store: str | None = None,
        *,
        force: bool = True,
        remove_finished: bool = True,
    ) -> RemoteTask | None:
        """
        Submit a task through the worker scheduler immediately.

        Execution never happens in the app process; the worker owns executor
        lookup, max-instance checks, events, and schedule advancement.
        """

        if isinstance(task_id, RemoteTask):
            task_id = task_id.id
        data = self._request(
            "POST",
            f"/tasks/{urllib.parse.quote(str(task_id), safe='')}/run",
            {"store": store, "force": force, "remove_finished": remove_finished},
        )
        return self._task_from_data(data)

    def pause_task(self, task_id: Any, store: str | None = None) -> RemoteTask:
        """
        Pause a task through the worker scheduler.

        The worker persists the paused state in its configured store.
        """

        if isinstance(task_id, RemoteTask):
            task_id = task_id.id
        data = self._request(
            "POST",
            f"/tasks/{urllib.parse.quote(str(task_id), safe='')}/pause",
            {"store": store},
        )
        task = self._task_from_data(data)
        assert task is not None
        return task

    def resume_task(self, task_id: Any, store: str | None = None) -> RemoteTask | None:
        """
        Resume a task through the worker scheduler.

        Finished one-shot schedules can still return `None`, matching local
        scheduler behavior.
        """

        if isinstance(task_id, RemoteTask):
            task_id = task_id.id
        data = self._request(
            "POST",
            f"/tasks/{urllib.parse.quote(str(task_id), safe='')}/resume",
            {"store": store},
        )
        return self._task_from_data(data)

    def delete_task(self, task_id: Any, store: str | None = None) -> None:
        """
        Delete a task through the worker scheduler.

        The worker removes the task from its configured store; the app process
        only receives success or a typed failure.
        """

        if isinstance(task_id, RemoteTask):
            task_id = task_id.id
        self._request(
            "POST",
            f"/tasks/{urllib.parse.quote(str(task_id), safe='')}/remove",
            {"store": store},
        )
