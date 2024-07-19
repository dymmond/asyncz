from datetime import datetime
from typing import TYPE_CHECKING, List

from asyncz.executors.base import BaseExecutor, run_task

if TYPE_CHECKING:
    from asyncz.tasks.types import TaskType


class DebugExecutor(BaseExecutor):
    """
    A special executor that executes the target callable directly instead of deferring it to a
    thread or process.
    """

    def do_send_task(
        self,
        task: "TaskType",
        run_times: List[datetime],
    ) -> None:
        assert task.id is not None, "Cannot send decorator type task"
        try:
            events = run_task(task, task.store_alias, run_times, self.logger)  # type: ignore
        except Exception:
            self.run_task_error(task.id)
        else:
            self.run_task_success(task.id, events)
