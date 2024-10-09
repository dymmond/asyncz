from datetime import datetime
from typing import Any, Optional, Union

from pydantic import BaseModel, ConfigDict


class SchedulerEvent(BaseModel):
    """
    The event itself.

    Args:
        code: The code type for the event
        alias: The alias given to store or executor.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)
    code: Union[int, int]
    alias: Optional[str] = None

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} (code={self.code})>"


class TaskEvent(SchedulerEvent):
    """
    The events for a specific task.

    Args:
        task_id: The identifier given to a task.
        store: The alias given to a store.
    """

    task_id: str
    store: Optional[str] = None


class TaskSubmissionEvent(TaskEvent):
    """
    Event related to the submission of a task.

    Args:
        scheduled_run_times: List of datetimes when the task is supposed to run.
    """

    scheduled_run_times: list[datetime]


class TaskExecutionEvent(TaskEvent):
    """
    Event relared to the running of a task within the executor.

    Args:
        scheduled_run_times: The time when the task was scheduled to be run.
        return_value: The return value of the task successfully executed.
        exception: The exception raised by the task.
        traceback: A formated traceback for the exception.
    """

    scheduled_run_time: Union[int, str, Any]
    return_value: Any = None
    exception: Optional[Exception] = None
    traceback: Optional[str] = None
