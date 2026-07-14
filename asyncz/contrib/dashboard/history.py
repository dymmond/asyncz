from __future__ import annotations

import contextlib
import hashlib
import threading
import weakref
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from asyncz.contrib.dashboard.logs.storage import LogStorage
from asyncz.events.base import SchedulerEvent, TaskExecutionEvent, TaskSubmissionEvent
from asyncz.events.constants import (
    TASK_ERROR,
    TASK_EXECUTED,
    TASK_MAX_INSTANCES,
    TASK_MISSED,
    TASK_SUBMITTED,
)

TERMINAL_STATUSES = {"succeeded", "failed", "missed", "max_instances"}
RUN_EVENT_MASK = TASK_SUBMITTED | TASK_MAX_INSTANCES | TASK_EXECUTED | TASK_ERROR | TASK_MISSED


@dataclass
class RunRecord:
    run_id: str
    task_id: str
    store: str | None
    scheduled_run_time: datetime | str | None
    task_name: str | None = None
    callable_reference: str | None = None
    executor: str | None = None
    scheduler_identity: str | None = None
    source: str = "unknown"
    status: str = "running"
    submitted_at: datetime | None = None
    finished_at: datetime | None = None
    return_value: str | None = None
    exception: str | None = None
    traceback: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    @property
    def status_label(self) -> str:
        return self.status.replace("_", " ").title()

    @property
    def source_label(self) -> str:
        return self.source.replace("_", " ").title()

    @property
    def task_label(self) -> str:
        return self.task_name or self.task_id

    @property
    def duration_ms(self) -> int | None:
        if not self.submitted_at or not self.finished_at:
            return None
        delta = self.finished_at - self.submitted_at
        return max(int(delta.total_seconds() * 1000), 0)


class MemoryRunHistoryStorage:
    def __init__(self, maxlen: int = 5_000) -> None:
        self.maxlen = maxlen
        self._records: dict[str, RunRecord] = {}
        self._order: deque[str] = deque()
        self._key_index: dict[tuple[str, str | None, str], str] = {}
        self._lock = threading.Lock()

    def clear(self) -> None:
        with self._lock:
            self._records.clear()
            self._order.clear()
            self._key_index.clear()

    def get(self, run_id: str) -> RunRecord | None:
        with self._lock:
            return self._records.get(run_id)

    def latest_for_task(self, task_id: str) -> RunRecord | None:
        matches = self.query(task_id=task_id, limit=1)
        return matches[0] if matches else None

    def query(
        self,
        *,
        task_id: str | None = None,
        status: str | None = None,
        source: str | None = None,
        q: str | None = None,
        limit: int = 200,
    ) -> list[RunRecord]:
        needle = (q or "").strip().lower()
        status_filter = (status or "").strip().lower()
        source_filter = (source or "").strip().lower()
        with self._lock:
            records = list(self._records.values())

        def sort_key(record: RunRecord) -> datetime:
            return (
                record.finished_at
                or record.submitted_at
                or record.updated_at
                or record.created_at
                or _utc_now()
            )

        out: list[RunRecord] = []
        for record in sorted(records, key=sort_key, reverse=True):
            if task_id and record.task_id != task_id:
                continue
            if status_filter and record.status != status_filter:
                continue
            if source_filter and record.source != source_filter:
                continue
            if needle:
                haystack = " ".join(
                    value or ""
                    for value in (
                        record.task_id,
                        record.task_name,
                        record.callable_reference,
                        record.scheduler_identity,
                        record.status,
                        record.source,
                        record.run_id,
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
            records = list(self._records.values())
        return {
            "total": len(records),
            "running": sum(1 for record in records if record.status == "running"),
            "succeeded": sum(1 for record in records if record.status == "succeeded"),
            "failed": sum(1 for record in records if record.status == "failed"),
            "missed": sum(1 for record in records if record.status == "missed"),
            "max_instances": sum(1 for record in records if record.status == "max_instances"),
        }

    def record_submission(
        self,
        event: TaskSubmissionEvent,
        *,
        scheduler: Any,
        log_storage: LogStorage | None = None,
    ) -> list[RunRecord]:
        now = _utc_now()
        source = str(getattr(event, "source", None) or "scheduled")
        status = "max_instances" if event.code == TASK_MAX_INSTANCES else "running"
        records: list[RunRecord] = []

        for scheduled_run_time in event.scheduled_run_times:
            record = self._upsert(
                task_id=event.task_id,
                store=event.store,
                scheduled_run_time=scheduled_run_time,
                scheduler=scheduler,
                scheduler_identity=event.scheduler_identity,
                now=now,
            )
            was_terminal = record.status in TERMINAL_STATUSES
            record.source = source
            record.submitted_at = record.submitted_at or (record.finished_at or now)
            if record.status not in TERMINAL_STATUSES:
                record.status = status
            if status == "max_instances":
                record.finished_at = record.finished_at or now
            record.updated_at = now
            records.append(record)

            if log_storage is not None:
                if status == "max_instances":
                    _append_run_log(
                        log_storage,
                        record,
                        "WARNING",
                        f"Task run skipped: maximum instances reached for {record.task_label}.",
                    )
                elif not was_terminal:
                    _append_run_log(
                        log_storage,
                        record,
                        "INFO",
                        f"Task run submitted for {record.task_label}.",
                    )

        return records

    def record_execution(
        self,
        event: TaskExecutionEvent,
        *,
        scheduler: Any,
        log_storage: LogStorage | None = None,
    ) -> RunRecord:
        now = _utc_now()
        record = self._upsert(
            task_id=event.task_id,
            store=event.store,
            scheduled_run_time=event.scheduled_run_time,
            scheduler=scheduler,
            scheduler_identity=event.scheduler_identity,
            now=now,
        )
        record.finished_at = now
        record.submitted_at = record.submitted_at or now
        record.status = _status_from_execution_code(event.code)
        record.return_value = (
            _safe_repr(event.return_value) if event.return_value is not None else None
        )
        record.exception = _safe_repr(event.exception) if event.exception is not None else None
        record.traceback = event.traceback
        record.updated_at = now

        if log_storage is not None:
            if record.status == "succeeded":
                _append_run_log(
                    log_storage,
                    record,
                    "INFO",
                    f"Task run succeeded for {record.task_label}.",
                )
            elif record.status == "missed":
                _append_run_log(
                    log_storage,
                    record,
                    "WARNING",
                    f"Task run missed for {record.task_label}.",
                )
            else:
                _append_run_log(
                    log_storage,
                    record,
                    "ERROR",
                    f"Task run failed for {record.task_label}: {record.exception or 'unknown error'}.",
                )

        return record

    def _upsert(
        self,
        *,
        task_id: str,
        store: str | None,
        scheduled_run_time: Any,
        scheduler: Any,
        scheduler_identity: str | None,
        now: datetime,
    ) -> RunRecord:
        normalized_run_time = _normalize_run_time(scheduled_run_time)
        key = _run_key(task_id, store, normalized_run_time)
        metadata = _task_metadata(scheduler, task_id, store)
        run_scheduler_identity = scheduler_identity or _scheduler_identity(scheduler)

        with self._lock:
            run_id = self._key_index.get(key)
            if run_id is None:
                run_id = _run_id(key)
                self._key_index[key] = run_id
                record = RunRecord(
                    run_id=run_id,
                    task_id=task_id,
                    store=store,
                    scheduled_run_time=normalized_run_time,
                    scheduler_identity=run_scheduler_identity,
                    created_at=now,
                    updated_at=now,
                    **metadata,
                )
                self._records[run_id] = record
                self._order.append(run_id)
                self._trim()
            else:
                record = self._records[run_id]
                for field, value in metadata.items():
                    if value and not getattr(record, field):
                        setattr(record, field, value)
                if run_scheduler_identity and not record.scheduler_identity:
                    record.scheduler_identity = run_scheduler_identity
            return record

    def _trim(self) -> None:
        while len(self._order) > self.maxlen:
            old_run_id = self._order.popleft()
            old_record = self._records.pop(old_run_id, None)
            if old_record is not None:
                self._key_index.pop(
                    _run_key(old_record.task_id, old_record.store, old_record.scheduled_run_time),
                    None,
                )


_storage: MemoryRunHistoryStorage | None = None
_installed_listeners: dict[int, tuple[weakref.ReferenceType[Any], Any]] = {}


def get_run_history_storage(
    storage: MemoryRunHistoryStorage | None = None,
) -> MemoryRunHistoryStorage:
    global _storage
    if storage is not None:
        _storage = storage
    elif _storage is None:
        _storage = MemoryRunHistoryStorage()
    return _storage


def install_run_history_listener(
    scheduler: Any,
    *,
    storage: MemoryRunHistoryStorage | None = None,
    log_storage: LogStorage | None = None,
) -> MemoryRunHistoryStorage:
    history_storage = get_run_history_storage(storage)
    key = id(scheduler)
    installed = _installed_listeners.get(key)
    if installed is not None and installed[0]() is scheduler:
        with contextlib.suppress(Exception):
            scheduler.remove_listener(installed[1])

    def _listener(event: SchedulerEvent) -> None:
        if isinstance(event, TaskSubmissionEvent) and event.code in {
            TASK_SUBMITTED,
            TASK_MAX_INSTANCES,
        }:
            history_storage.record_submission(event, scheduler=scheduler, log_storage=log_storage)
        elif isinstance(event, TaskExecutionEvent) and event.code in {
            TASK_EXECUTED,
            TASK_ERROR,
            TASK_MISSED,
        }:
            history_storage.record_execution(event, scheduler=scheduler, log_storage=log_storage)

    scheduler.add_listener(_listener, mask=RUN_EVENT_MASK)
    _installed_listeners[key] = (weakref.ref(scheduler), _listener)
    return history_storage


def logs_for_run(
    record: RunRecord,
    log_storage: LogStorage,
    *,
    limit: int = 200,
) -> list[Any]:
    direct = list(log_storage.query(run_id=record.run_id, limit=limit))
    if len(direct) >= limit:
        return direct[:limit]

    start = record.submitted_at or record.finished_at or record.created_at
    end = record.finished_at or record.updated_at or _utc_now()
    if start is None:
        return direct

    since = start - timedelta(seconds=5)
    until = end + timedelta(seconds=5)
    correlated = list(
        log_storage.query(task_id=record.task_id, since=since, until=until, limit=limit)
    )
    seen: set[tuple[Any, str, str, str]] = set()
    out: list[Any] = []
    for entry in [*direct, *correlated]:
        key = (entry.ts, entry.level, entry.logger, entry.message)
        if key in seen:
            continue
        seen.add(key)
        out.append(entry)
        if len(out) >= limit:
            break
    return out


def _status_from_execution_code(code: int) -> str:
    if code == TASK_EXECUTED:
        return "succeeded"
    if code == TASK_MISSED:
        return "missed"
    return "failed"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _normalize_run_time(value: Any) -> datetime | str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    return str(value)


def _run_key(
    task_id: str,
    store: str | None,
    scheduled_run_time: datetime | str | None,
) -> tuple[str, str | None, str]:
    if isinstance(scheduled_run_time, datetime):
        run_time = scheduled_run_time.isoformat()
    else:
        run_time = str(scheduled_run_time or "")
    return task_id, store, run_time


def _run_id(key: tuple[str, str | None, str]) -> str:
    raw = "|".join(part or "" for part in key)
    return hashlib.sha256(raw.encode()).hexdigest()[:20]


def _task_metadata(scheduler: Any, task_id: str, store: str | None) -> dict[str, Any]:
    try:
        task = scheduler.get_task(task_id, store)
    except Exception:
        task = None
    if task is None:
        return {}

    try:
        info = task.snapshot()
    except Exception:
        return {
            "task_name": getattr(task, "name", None),
            "executor": getattr(task, "executor", None),
        }

    return {
        "task_name": info.name,
        "callable_reference": info.callable_reference or info.callable_name,
        "executor": info.executor,
    }


def _scheduler_identity(scheduler: Any) -> str | None:
    try:
        info = scheduler.get_scheduler_info()
        identity = getattr(info, "identity", None)
    except Exception:
        identity = getattr(scheduler, "identity", None)
    identity = str(identity or "").strip()
    return identity or None


def _safe_repr(value: Any, limit: int = 500) -> str:
    try:
        rendered = repr(value)
    except Exception:
        rendered = f"<{type(value).__name__}>"
    if len(rendered) > limit:
        return f"{rendered[: limit - 3]}..."
    return rendered


def _append_run_log(
    storage: LogStorage,
    record: RunRecord,
    level: str,
    message: str,
) -> None:
    storage.append(
        {
            "ts": _utc_now(),
            "level": level,
            "message": message,
            "logger": "asyncz.dashboard.history",
            "task_id": record.task_id,
            "extra": {
                "run_id": record.run_id,
                "status": record.status,
                "source": record.source,
                "scheduler_identity": record.scheduler_identity,
                "scheduled_run_time": (
                    record.scheduled_run_time.isoformat()
                    if isinstance(record.scheduled_run_time, datetime)
                    else record.scheduled_run_time
                ),
            },
        }
    )
