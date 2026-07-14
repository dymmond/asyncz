from __future__ import annotations

import contextlib
import hashlib
import threading
import weakref
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from asyncz.events.base import (
    SchedulerEvent,
    TaskEvent,
    TaskExecutionEvent,
    TaskSubmissionEvent,
)
from asyncz.events.constants import (
    ALL_EVENTS,
    ALL_TASKS_REMOVED,
    EXECUTOR_ADDED,
    EXECUTOR_REMOVED,
    SCHEDULER_PAUSED,
    SCHEDULER_RESUMED,
    SCHEDULER_SHUTDOWN,
    SCHEDULER_STARTED,
    STORE_ADDED,
    STORE_REMOVED,
    TASK_ADDED,
    TASK_ERROR,
    TASK_EXECUTED,
    TASK_MAX_INSTANCES,
    TASK_MISSED,
    TASK_MODIFIED,
    TASK_REMOVED,
    TASK_SUBMITTED,
)

EVENT_NAMES = {
    SCHEDULER_STARTED: "scheduler.started",
    SCHEDULER_SHUTDOWN: "scheduler.shutdown",
    SCHEDULER_PAUSED: "scheduler.paused",
    SCHEDULER_RESUMED: "scheduler.resumed",
    EXECUTOR_ADDED: "executor.added",
    EXECUTOR_REMOVED: "executor.removed",
    STORE_ADDED: "store.added",
    STORE_REMOVED: "store.removed",
    ALL_TASKS_REMOVED: "task.all_removed",
    TASK_ADDED: "task.added",
    TASK_REMOVED: "task.removed",
    TASK_MODIFIED: "task.modified",
    TASK_EXECUTED: "task.executed",
    TASK_ERROR: "task.error",
    TASK_MISSED: "task.missed",
    TASK_SUBMITTED: "task.submitted",
    TASK_MAX_INSTANCES: "task.max_instances",
}


TERMINAL_EVENT_CODES = {
    TASK_EXECUTED,
    TASK_ERROR,
    TASK_MISSED,
    TASK_MAX_INSTANCES,
    SCHEDULER_SHUTDOWN,
}


@dataclass(frozen=True)
class SchedulerEventRecord:
    event_id: str
    code: int
    name: str
    category: str
    observed_at: datetime
    alias: str | None = None
    task_id: str | None = None
    store: str | None = None
    scheduler_identity: str | None = None
    details: dict[str, Any] = field(default_factory=dict)

    @property
    def observed_at_label(self) -> str:
        return self.observed_at.strftime("%Y-%m-%d %H:%M:%S")

    @property
    def name_label(self) -> str:
        return self.name.replace(".", " ").replace("_", " ").title()

    @property
    def category_label(self) -> str:
        return self.category.title()


class MemorySchedulerEventStorage:
    def __init__(self, maxlen: int = 10_000) -> None:
        self.maxlen = maxlen
        self._records: deque[SchedulerEventRecord] = deque(maxlen=maxlen)
        self._lock = threading.Lock()

    def clear(self) -> None:
        with self._lock:
            self._records.clear()

    def append(self, event: SchedulerEvent, *, scheduler: Any) -> SchedulerEventRecord:
        record = _event_record(event, scheduler=scheduler)
        with self._lock:
            self._records.append(record)
        return record

    def query(
        self,
        *,
        category: str | None = None,
        name: str | None = None,
        task_id: str | None = None,
        q: str | None = None,
        limit: int = 200,
    ) -> list[SchedulerEventRecord]:
        category_filter = (category or "").strip().lower()
        name_filter = (name or "").strip().lower()
        needle = (q or "").strip().lower()
        with self._lock:
            records = list(self._records)

        out: list[SchedulerEventRecord] = []
        for record in reversed(records):
            if category_filter and record.category != category_filter:
                continue
            if name_filter and record.name != name_filter:
                continue
            if task_id and record.task_id != task_id:
                continue
            if needle:
                haystack = " ".join(
                    value or ""
                    for value in (
                        record.name,
                        record.category,
                        record.alias,
                        record.task_id,
                        record.store,
                        record.scheduler_identity,
                        record.event_id,
                        _details_text(record.details),
                    )
                ).lower()
                if needle not in haystack:
                    continue
            out.append(record)
            if len(out) >= limit:
                break
        return out

    def summary(self) -> dict[str, int]:
        with self._lock:
            records = list(self._records)
        return {
            "total": len(records),
            "scheduler": sum(1 for record in records if record.category == "scheduler"),
            "task": sum(1 for record in records if record.category == "task"),
            "terminal": sum(1 for record in records if record.code in TERMINAL_EVENT_CODES),
        }


_storage: MemorySchedulerEventStorage | None = None
_installed_listeners: dict[int, tuple[weakref.ReferenceType[Any], Any]] = {}


def get_scheduler_event_storage(
    storage: MemorySchedulerEventStorage | None = None,
) -> MemorySchedulerEventStorage:
    global _storage
    if storage is not None:
        _storage = storage
    elif _storage is None:
        _storage = MemorySchedulerEventStorage()
    return _storage


def install_scheduler_event_listener(
    scheduler: Any,
    *,
    storage: MemorySchedulerEventStorage | None = None,
) -> MemorySchedulerEventStorage:
    event_storage = get_scheduler_event_storage(storage)
    key = id(scheduler)
    installed = _installed_listeners.get(key)
    if installed is not None and installed[0]() is scheduler:
        with contextlib.suppress(Exception):
            scheduler.remove_listener(installed[1])

    def _listener(event: SchedulerEvent) -> None:
        event_storage.append(event, scheduler=scheduler)

    scheduler.add_listener(_listener, mask=ALL_EVENTS)
    _installed_listeners[key] = (weakref.ref(scheduler), _listener)
    return event_storage


def _event_record(event: SchedulerEvent, *, scheduler: Any) -> SchedulerEventRecord:
    observed_at = datetime.now(timezone.utc)
    name = EVENT_NAMES.get(event.code, f"event.{event.code}")
    category = _event_category(event, name)
    task_id = getattr(event, "task_id", None) if isinstance(event, TaskEvent) else None
    store = getattr(event, "store", None) if isinstance(event, TaskEvent) else None
    scheduler_identity = (
        getattr(event, "scheduler_identity", None)
        if isinstance(event, TaskEvent)
        else _scheduler_identity(scheduler)
    )
    details = _event_details(event)
    event_id = _event_id(
        observed_at,
        event.code,
        task_id=task_id,
        alias=event.alias,
        store=store,
        details=details,
    )
    return SchedulerEventRecord(
        event_id=event_id,
        code=event.code,
        name=name,
        category=category,
        observed_at=observed_at,
        alias=event.alias,
        task_id=task_id,
        store=store,
        scheduler_identity=scheduler_identity,
        details=details,
    )


def _event_category(event: SchedulerEvent, name: str) -> str:
    if isinstance(event, TaskEvent):
        return "task"
    if name.startswith("executor."):
        return "executor"
    if name.startswith("store."):
        return "store"
    return "scheduler"


def _event_details(event: SchedulerEvent) -> dict[str, Any]:
    if isinstance(event, TaskSubmissionEvent):
        return {
            "source": event.source or "unknown",
            "submitted_run_count": len(event.scheduled_run_times),
            "coalesced_run_count": event.coalesced_run_count,
            "scheduled_run_times": [
                _datetime_text(run_time) for run_time in event.scheduled_run_times
            ],
        }
    if isinstance(event, TaskExecutionEvent):
        return {
            "scheduled_run_time": _datetime_text(event.scheduled_run_time),
            "return_value": _safe_repr(event.return_value),
            "exception_type": _exception_type(event.exception),
            "exception_message": _safe_str(event.exception),
        }
    return {}


def _event_id(
    observed_at: datetime,
    code: int,
    *,
    task_id: str | None,
    alias: str | None,
    store: str | None,
    details: dict[str, Any],
) -> str:
    raw = "|".join(
        (
            observed_at.isoformat(),
            str(code),
            task_id or "",
            alias or "",
            store or "",
            _details_text(details),
        )
    )
    return hashlib.sha256(raw.encode()).hexdigest()[:20]


def _details_text(details: dict[str, Any]) -> str:
    parts: list[str] = []
    for key, value in details.items():
        if value is None:
            continue
        parts.extend((str(key), str(value)))
    return " ".join(parts)


def _scheduler_identity(scheduler: Any) -> str | None:
    try:
        info = scheduler.get_scheduler_info()
        identity = getattr(info, "identity", None)
    except Exception:
        identity = getattr(scheduler, "identity", None)
    identity = str(identity or "").strip()
    return identity or None


def _datetime_text(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _safe_repr(value: Any, limit: int = 500) -> str | None:
    if value is None:
        return None
    try:
        rendered = repr(value)
    except Exception:
        rendered = f"<{type(value).__name__}>"
    if len(rendered) > limit:
        return f"{rendered[: limit - 3]}..."
    return rendered


def _safe_str(value: Any, limit: int = 500) -> str | None:
    if value is None:
        return None
    try:
        rendered = str(value)
    except Exception:
        rendered = f"<{type(value).__name__}>"
    if len(rendered) > limit:
        return f"{rendered[: limit - 3]}..."
    return rendered


def _exception_type(value: BaseException | None) -> str | None:
    if value is None:
        return None
    cls = value.__class__
    if cls.__module__ == "builtins":
        return cls.__qualname__
    return f"{cls.__module__}.{cls.__qualname__}"
