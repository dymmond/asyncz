from abc import ABC, abstractmethod
from datetime import datetime
from typing import TYPE_CHECKING, Any, List, Optional, Union

from asyncz.state import BaseStateExtra
from asyncz.typing import DictAny
from loguru import logger

if TYPE_CHECKING:
    from asyncz.tasks.types import TaskType


class BaseStore(BaseStateExtra, ABC):
    """
    Base class for all task stores.
    """

    def __init__(
        self, scheduler: Optional[Any] = None, alias: Optional[str] = None, **kwargs: "DictAny"
    ) -> None:
        super().__init__(**kwargs)
        self.logger = logger
        self.scheduler = scheduler
        self.alias = alias

    def start(self, scheduler: Any, alias: str):
        """
        Called by the scheduler when the scheduler is being started or when the task store is being
        added to an already running scheduler.

        Args:
            scheduler: The scheduler that is starting this task store.
            alias: Alias of this task store as it was assigned to the scheduler.
        """
        self.scheduler = scheduler
        self.alias = alias

    def shutdown(self):
        """
        Frees any resources still bound to this task store.
        """
        ...

    def fix_paused_tasks(self, tasks: List["TaskType"]):
        for index, task in enumerate(tasks):
            if task.next_run_time is not None:
                if index > 0:
                    paused_tasks = tasks[:index]
                    del tasks[:index]
                    tasks.extend(paused_tasks)
                break

    @abstractmethod
    def lookup_task(self, task_id: Union[str, int]) -> "TaskType":
        """
        Returns a specific task, or None if it isn't found.

        The task store is responsible for setting the scheduler and store attributes of
        the returned task to point to the scheduler and itself, respectively.
        """
        ...

    @abstractmethod
    def get_due_tasks(self, now: datetime) -> List["TaskType"]:
        """
        Returns the list of tasks that have next_run_time earlier or equal to now.
        The returned tasks must be sorted by next run time (ascending).
        """
        ...

    @abstractmethod
    def get_next_run_time(self) -> datetime:
        """
        Returns the earliest run time of all the tasks stored in this task store, or None if
        there are no active tasks.
        """
        ...

    @abstractmethod
    def get_all_tasks(self) -> List["TaskType"]:
        """
        Returns a list of all tasks in this task store.
        The returned tasks should be sorted by next run time (ascending).
        Paused tasks (next_run_time == None) should be sorted last.

        The task store is responsible for setting the scheduler and store attributes of
        the returned tasks to point to the scheduler and itself, respectively.
        """
        ...

    @abstractmethod
    def add_task(self, task: "TaskType"):
        """
        Adds the given task to this store.
        """
        ...

    @abstractmethod
    def update_task(self, task: "TaskType"):
        """
        Replaces the task in the store with the given newer version.
        """
        ...

    @abstractmethod
    def delete_task(self, task_id: Union[str, int]):
        """
        Removes the given task from this store.
        """
        ...

    @abstractmethod
    def remove_all_tasks(self):
        """Removes all tasks from this store."""
        ...

    def __repr__(self):
        return f"<{self.__class__.__name__}>"
