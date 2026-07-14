from __future__ import annotations

import threading
import uuid
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class AuditRecord:
    event_id: str
    action: str
    status: str
    target_type: str = "task"
    target_id: str | None = None
    message: str | None = None
    actor: str = "dashboard"
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    details: dict[str, Any] = field(default_factory=dict)

    @property
    def action_label(self) -> str:
        return self.action.replace("_", " ").replace(".", " ").title()

    @property
    def status_label(self) -> str:
        return self.status.replace("_", " ").title()

    @property
    def created_at_label(self) -> str:
        return self.created_at.isoformat(timespec="seconds")


class MemoryAuditTrailStorage:
    def __init__(self, maxlen: int = 5_000) -> None:
        self.maxlen = maxlen
        self._records: dict[str, AuditRecord] = {}
        self._order: deque[str] = deque()
        self._lock = threading.Lock()

    def clear(self) -> None:
        with self._lock:
            self._records.clear()
            self._order.clear()

    def append(
        self,
        *,
        action: str,
        status: str,
        target_type: str = "task",
        target_id: str | None = None,
        message: str | None = None,
        actor: str = "dashboard",
        details: dict[str, Any] | None = None,
    ) -> AuditRecord:
        record = AuditRecord(
            event_id=uuid.uuid4().hex[:20],
            action=action,
            status=status,
            target_type=target_type,
            target_id=target_id,
            message=message,
            actor=actor,
            details=details or {},
        )
        with self._lock:
            self._records[record.event_id] = record
            self._order.append(record.event_id)
            self._trim()
        return record

    def query(
        self,
        *,
        action: str | None = None,
        status: str | None = None,
        q: str | None = None,
        limit: int = 200,
    ) -> list[AuditRecord]:
        action_filter = (action or "").strip().lower()
        status_filter = (status or "").strip().lower()
        needle = (q or "").strip().lower()

        with self._lock:
            records = [self._records[event_id] for event_id in reversed(self._order)]

        out: list[AuditRecord] = []
        for record in records:
            if action_filter and record.action != action_filter:
                continue
            if status_filter and record.status != status_filter:
                continue
            if needle:
                haystack = " ".join(
                    value or ""
                    for value in (
                        record.event_id,
                        record.action,
                        record.status,
                        record.target_type,
                        record.target_id,
                        record.message,
                        record.actor,
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
            "succeeded": sum(1 for record in records if record.status == "succeeded"),
            "failed": sum(1 for record in records if record.status == "failed"),
            "warning": sum(1 for record in records if record.status == "warning"),
        }

    def _trim(self) -> None:
        while len(self._order) > self.maxlen:
            old_event_id = self._order.popleft()
            self._records.pop(old_event_id, None)


_storage: MemoryAuditTrailStorage | None = None


def get_audit_storage(
    storage: MemoryAuditTrailStorage | None = None,
) -> MemoryAuditTrailStorage:
    global _storage
    if storage is not None:
        _storage = storage
    elif _storage is None:
        _storage = MemoryAuditTrailStorage()
    return _storage


def record_audit_event(
    action: str,
    *,
    status: str = "succeeded",
    target_type: str = "task",
    target_id: str | None = None,
    message: str | None = None,
    actor: str = "dashboard",
    details: dict[str, Any] | None = None,
) -> AuditRecord:
    return get_audit_storage().append(
        action=action,
        status=status,
        target_type=target_type,
        target_id=target_id,
        message=message,
        actor=actor,
        details=details,
    )
