from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from asyncz.enums import TaskScheduleState


class TaskInfo(BaseModel):
    """
    Immutable snapshot of a task's observable scheduling metadata.

    The model is intentionally detached from the live ``Task`` instance so callers
    can safely use it in CLIs, dashboards, logs, or tests without mutating the
    scheduler's in-memory state. It focuses on the information Asyncz users most
    commonly need when inspecting a task:

    - which callable will run
    - which trigger and executor are in use
    - whether the task is pending, paused, or actively scheduled
    - when the next execution is due
    - which scheduling safeguards are configured
    """

    model_config = ConfigDict(frozen=True)

    id: str | None
    name: str | None
    callable_name: str | None
    callable_reference: str | None
    trigger_alias: str | None
    trigger_name: str | None
    trigger_description: str | None
    executor: str | None
    store_alias: str | None
    schedule_state: TaskScheduleState
    next_run_time: datetime | None
    coalesce: bool
    max_instances: int
    mistrigger_grace_time: float | int | None
    pending: bool
    paused: bool
    submitted: bool
