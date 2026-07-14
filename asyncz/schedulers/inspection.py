from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from asyncz.enums import SchedulerState


class SchedulerInfo(BaseModel):
    """
    Immutable snapshot of scheduler-level operational metadata.

    The scheduler owns this projection so dashboards, CLIs, and custom tooling can
    inspect runtime state without reaching into private scheduler dictionaries or
    recomputing task counts independently.
    """

    model_config = ConfigDict(frozen=True)

    identity: str
    state: SchedulerState
    state_label: str
    running: bool
    started_at: datetime | None = None
    uptime_seconds: float | None = None
    timezone: str
    executor_aliases: tuple[str, ...]
    store_aliases: tuple[str, ...]
    task_count: int
    scheduled_task_count: int
    paused_task_count: int
    pending_task_count: int
    submitted_task_count: int
    store_retry_interval: float
    startup_delay: float


class SchedulerInstanceInfo(BaseModel):
    """
    Immutable process-local scheduler instance inspection snapshot.

    This model intentionally describes the scheduler process currently reachable
    through the runtime object. It is not a distributed registry record.
    """

    model_config = ConfigDict(frozen=True)

    identity: str
    scope: str
    state: SchedulerState
    state_label: str
    active: bool
    stale: bool
    started_at: datetime | None = None
    last_seen_at: datetime
    uptime_seconds: float | None = None
    heartbeat_age_seconds: float
    stale_after_seconds: float
    timezone: str
    executor_aliases: tuple[str, ...]
    store_aliases: tuple[str, ...]
    task_count: int
    scheduled_task_count: int
    paused_task_count: int
    pending_task_count: int
    submitted_task_count: int
