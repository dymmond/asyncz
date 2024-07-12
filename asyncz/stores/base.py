from typing import TYPE_CHECKING, Any, List, Optional

from loguru import logger

from asyncz.state import BaseStateExtra
from asyncz.stores.types import StoreType

if TYPE_CHECKING:
    from asyncz.schedulers.types import SchedulerType
    from asyncz.tasks.types import TaskType


class BaseStore(BaseStateExtra, StoreType):
    """
    Base class for all task stores.
    """

    def __init__(self, scheduler: Optional["SchedulerType"] = None, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.scheduler = scheduler
        self.logger = logger

    def start(self, scheduler: "SchedulerType", alias: str) -> None:
        """
        Called by the scheduler when the scheduler is being started or when the task store is being
        added to an already running scheduler.

        Args:
            scheduler: The scheduler that is starting this task store.
            alias: Alias of this task store as it was assigned to the scheduler.
        """
        self.scheduler = scheduler
        self.alias = alias

    def shutdown(self) -> None:
        """
        Frees any resources still bound to this task store.
        """
        ...

    def fix_paused_tasks(self, tasks: List["TaskType"]) -> None:
        for index, task in enumerate(tasks):
            if task.next_run_time is not None:
                if index > 0:
                    paused_tasks = tasks[:index]
                    del tasks[:index]
                    tasks.extend(paused_tasks)
                break

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__}>"
