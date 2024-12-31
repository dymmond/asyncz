from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import TYPE_CHECKING, Any, Optional

from asyncz.locks import NullLockProtected

if TYPE_CHECKING:
    from asyncz.protocols import LockProtectedProtocol
    from asyncz.schedulers.types import SchedulerType
    from asyncz.tasks.types import TaskType
else:
    LockProtectedProtocol = Any


class StoreType(ABC):
    """
    Base class for all task stores.
    """

    alias: Optional[str] = None
    lock: LockProtectedProtocol = NullLockProtected()

    @abstractmethod
    def start(self, scheduler: SchedulerType, alias: str) -> None:
        """
        Called by the scheduler when the scheduler is being started or when the task store is being
        added to an already running scheduler.

        Args:
            scheduler: The scheduler that is starting this task store.
            alias: Alias of this task store as it was assigned to the scheduler.
        """

    @abstractmethod
    def shutdown(self) -> None:
        """
        Frees any resources still bound to this task store.
        """
        ...

    @abstractmethod
    def lookup_task(self, task_id: str) -> Optional[TaskType]:
        """
        Returns a specific task, or None if it isn't found.

        The task store is responsible for setting the scheduler and store attributes of
        the returned task to point to the scheduler and itself, respectively.
        """
        ...

    @abstractmethod
    def get_due_tasks(self, now: datetime) -> list[TaskType]:
        """
        Returns the list of tasks that have next_run_time earlier or equal to now.
        The returned tasks must be sorted by next run time (ascending).
        """
        ...

    @abstractmethod
    def get_next_run_time(self) -> Optional[datetime]:
        """
        Returns the earliest run time of all the tasks stored in this task store, or None if
        there are no active tasks.
        """
        ...

    @abstractmethod
    def get_all_tasks(self) -> list[TaskType]:
        """
        Returns a list of all tasks in this task store.
        The returned tasks should be sorted by next run time (ascending).
        Paused tasks (next_run_time == None) should be sorted last.

        The task store is responsible for setting the scheduler and store attributes of
        the returned tasks to point to the scheduler and itself, respectively.
        """
        ...

    @abstractmethod
    def add_task(self, task: TaskType) -> None:
        """
        Adds the given task to this store.
        """
        ...

    @abstractmethod
    def update_task(self, task: TaskType) -> None:
        """
        Replaces the task in the store with the given newer version.
        """
        ...

    @abstractmethod
    def delete_task(self, task_id: str) -> None:
        """
        Removes the given task from this store.
        """
        ...

    @abstractmethod
    def remove_all_tasks(self) -> None:
        """Removes all tasks from this store."""
        ...
