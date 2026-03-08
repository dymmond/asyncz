from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable, Sequence
from datetime import datetime, tzinfo
from typing import Any, Optional, TypeVar

from asyncz.enums import TaskScheduleState
from asyncz.schedulers.types import SchedulerType
from asyncz.tasks.inspection import TaskInfo
from asyncz.triggers.types import TriggerType

DecoratedFn = TypeVar("DecoratedFn", bound=Callable[..., Any])


class TaskDefaultsType:
    mistrigger_grace_time: Optional[float] = 1
    coalesce: bool = True
    max_instances: int = 1


class TaskType(TaskDefaultsType, ABC):
    """
    Abstract task protocol shared by scheduler, store, executor, and UI layers.

    ``Task`` is the concrete implementation used by Asyncz, but several
    subsystems depend only on this contract so they can work with serialized or
    reconstructed tasks without caring about the exact subclass.
    """

    id: Optional[str] = None
    name: Optional[str] = None
    next_run_time: Optional[datetime] = None
    fn: Optional[Callable[..., Any]] = None
    args: Sequence[Any]
    kwargs: dict[str, Any]
    # are set by add_task if not set
    store_alias: Optional[str] = None
    executor: Optional[str] = None
    trigger: Optional[TriggerType] = None
    scheduler: Optional[SchedulerType] = None
    # are exclusively set by scheduler
    pending: bool = True
    submitted: bool = False

    @property
    def schedule_state(self) -> TaskScheduleState:
        """
        Return the scheduler-facing state of this task.

        The state is derived entirely from the task metadata so it works for both
        live tasks and tasks reconstructed from stores:

        - pending tasks have not yet been committed to a running store
        - paused tasks have no ``next_run_time``
        - scheduled tasks have a future or due ``next_run_time``
        """

        if self.pending:
            return TaskScheduleState.PENDING
        if self.next_run_time is None:
            return TaskScheduleState.PAUSED
        return TaskScheduleState.SCHEDULED

    @property
    def paused(self) -> bool:
        """
        Convenience flag used by management APIs and the dashboard.

        This intentionally distinguishes paused tasks from pending tasks so the
        caller can tell whether a task is merely unscheduled or still waiting to
        be committed at scheduler start time.
        """

        return self.schedule_state is TaskScheduleState.PAUSED

    @abstractmethod
    def update_task(self, **updates: Any) -> TaskType:
        """
        Makes the given updates to this json and save it in the associated store.
        Accepted keyword args are the same as the class variables.

        This one really updates the task
        """

    def update(self, **updates: Any) -> TaskType:
        """
        Makes the given updates to this json and save it in the associated store.
        Accepted keyword args are the same as the class variables.
        """
        scheduler = self.scheduler
        task_id = self.id
        if scheduler is not None and task_id is not None:
            scheduler.update_task(task_id, self.store_alias, **updates)
        return self

    def reschedule(self, trigger: TriggerType, **trigger_args: Any) -> TaskType:
        """
        Shortcut for switching the trigger on this task.
        """
        scheduler = self.scheduler
        task_id = self.id
        if scheduler is not None and task_id is not None:
            scheduler.reschedule_task(task_id, self.store_alias, trigger, **trigger_args)
        return self

    def pause(self) -> TaskType:
        """
        Temporarily suspenses the execution of a given task.
        """
        scheduler = self.scheduler
        task_id = self.id
        if scheduler is not None and task_id is not None:
            scheduler.pause_task(task_id, self.store_alias)
        return self

    def resume(self) -> TaskType:
        """
        Resume the schedule of this task if previously paused.
        """
        scheduler = self.scheduler
        task_id = self.id
        if scheduler is not None and task_id is not None:
            scheduler.resume_task(task_id, self.store_alias)
        return self

    def delete(self) -> TaskType:
        """
        Unschedules this task and removes it from its associated store.
        """
        scheduler = self.scheduler
        task_id = self.id
        if scheduler is not None and task_id is not None:
            scheduler.delete_task(task_id, self.store_alias)
        return self

    def snapshot(self) -> TaskInfo:
        """
        Build an immutable inspection snapshot for this task.

        The snapshot is the preferred representation for presentation-oriented
        code because it captures the task's observable state without exposing
        the live mutable task object.
        """

        from asyncz.utils import get_callable_name

        callable_name: str | None = None
        if self.fn is not None:
            try:
                callable_name = get_callable_name(self.fn)
            except TypeError:
                callable_name = None

        fn_reference = getattr(self, "fn_reference", None)
        if callable_name is None and fn_reference:
            callable_name = fn_reference.split(":")[-1]

        trigger = self.trigger
        return TaskInfo(
            id=self.id,
            name=self.name,
            callable_name=callable_name,
            callable_reference=fn_reference,
            trigger_alias=getattr(trigger, "alias", None),
            trigger_name=type(trigger).__name__ if trigger is not None else None,
            trigger_description=str(trigger) if trigger is not None else None,
            executor=self.executor,
            store_alias=self.store_alias,
            schedule_state=self.schedule_state,
            next_run_time=self.next_run_time,
            coalesce=self.coalesce,
            max_instances=self.max_instances,
            mistrigger_grace_time=self.mistrigger_grace_time,
            pending=self.pending,
            paused=self.paused,
            submitted=self.submitted,
        )

    @abstractmethod
    def get_run_times(self, timezone: tzinfo, now: datetime) -> list[datetime]:
        """
        Computes the scheduled run times `next_run_time` and `now`, inclusive.
        """

    @abstractmethod
    def __call__(self, fn: DecoratedFn) -> DecoratedFn: ...
