from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Callable, List, Optional, TypeVar

from asyncz.schedulers.types import SchedulerType
from asyncz.triggers.types import TriggerType

DecoratedFn = TypeVar("DecoratedFn", bound=Callable[..., Any])


class TaskDefaultsType:
    mistrigger_grace_time: Optional[float] = 1
    coalesce: bool = True
    max_instances: int = 1


class TaskType(TaskDefaultsType, ABC):
    """BaseType of task."""

    id: str
    pending: bool = True
    name: Optional[str] = None
    next_run_time: Optional[datetime] = None
    store_alias: Optional[str] = None
    scheduler: Optional[SchedulerType] = None
    trigger: Optional[TriggerType] = None
    executor: Optional[str] = None

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
        if scheduler is not None:
            scheduler.update_task(self.id, self.store_alias, **updates)
        return self

    def reschedule(self, trigger: TriggerType, **trigger_args: Any) -> TaskType:
        """
        Shortcut for switching the trigger on this task.
        """
        scheduler = self.scheduler
        if scheduler is not None:
            scheduler.reschedule_task(self.id, self.store_alias, trigger, **trigger_args)
        return self

    def pause(self) -> TaskType:
        """
        Temporarily suspenses the execution of a given task.
        """
        scheduler = self.scheduler
        if scheduler is not None:
            scheduler.pause_task(self.id, self.store_alias)
        return self

    def resume(self) -> TaskType:
        """
        Resume the schedule of this task if previously paused.
        """
        scheduler = self.scheduler
        if scheduler is not None:
            scheduler.resume_task(self.id, self.store_alias)
        return self

    def delete(self) -> TaskType:
        """
        Unschedules this task and removes it from its associated store.
        """
        scheduler = self.scheduler
        if scheduler is not None:
            scheduler.delete_task(self.id, self.store_alias)
        return self

    @abstractmethod
    def get_run_times(self, now: datetime) -> List[datetime]:
        """
        Computes the scheduled run times `next_run_time` and `now`, inclusive.
        """

    def __call__(self, fn: DecoratedFn) -> DecoratedFn:
        self.update_task(fn=fn)
        scheduler = self.scheduler
        if scheduler is not None:
            scheduler.add_task(self, replace_existing=True)
        return fn
