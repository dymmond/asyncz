from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    List,
    Optional,
)

from asyncz.schedulers.types import SchedulerType

if TYPE_CHECKING:
    from asyncz.triggers.types import TriggerType


class TaskType(ABC):
    """BaseType of task."""

    id: str
    name: Optional[str] = None
    next_run_time: Optional[datetime] = None
    store_alias: Optional[str] = None
    scheduler: Optional[SchedulerType] = None

    @property
    def pending(self) -> bool:
        """
        Returns true if the referenced task is still waiting to be added to its designated task
        store.
        """
        return self.store_alias is None

    @abstractmethod
    def update(self, **updates: Any) -> TaskType:
        """
        Makes the given updates to this json and save it in the associated store.
        Accepted keyword args are the same as the class variables.
        """

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

    def __call__(self, fn: Callable[..., Any]) -> Callable:
        self._update(fn=fn)
        return fn
