from datetime import datetime
from typing import TYPE_CHECKING, cast

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
        run_times: list[datetime],
    ) -> None:
        assert task.id is not None, "Cannot send decorator type task"
        assert self.logger is not None, "logger is None"
        try:
            events = run_task(task, cast(str, task.store_alias), run_times, self.logger)
        except Exception:
            self.run_task_error(task.id)
        else:
            self.run_task_success(task.id, events)
