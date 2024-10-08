from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    import logging

    from asyncz.events import TaskExecutionEvent
    from asyncz.schedulers.types import SchedulerType
    from asyncz.tasks.types import TaskType


class ExecutorType(ABC):
    logger: Optional[logging.Logger]

    @abstractmethod
    def start(self, scheduler: SchedulerType, alias: str) -> None:
        """
        Called by the scheduler when the scheduler is being started or when the executor is being
        added to an already running scheduler.

        Args:
            scheduler - The scheduler that is starting this executor.
            alias - The alias of this executor as it was assigned to the scheduler.
        """

    @abstractmethod
    def shutdown(self, wait: bool = True) -> None:
        """
        Shuts down the executor.

        Args:
            wait - Boolean indicating to wait until all submitted tasks have been executed.
        """

    @abstractmethod
    def send_task(self, task: TaskType, run_times: list[datetime]) -> None:
        """
        Sends the task for execution.

        Args:
            task: A Task instance to execute.
            run_times: A list of datetimes specifying when the task should have been run.
        """

    @abstractmethod
    def do_send_task(self, task: TaskType, run_times: list[datetime]) -> Any:
        """
        Executes the actual task of scheduling `run_task` to be called.
        """
        ...

    @abstractmethod
    def run_task_success(self, task_id: str, events: list[TaskExecutionEvent]) -> None:
        """
        Called by the executor with the list of generated events when the function run_task has
        been successfully executed.
        """

    @abstractmethod
    def run_task_error(self, task_id: str) -> None:
        """
        Called by the executor with the exception if there is an error calling the run_task.
        """
