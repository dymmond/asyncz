from datetime import datetime
from typing import Any, List, Optional, Union

from pydantic import BaseModel


class SchedulerEvent(BaseModel):
    """
    The event itself.

    Args:
        code: The code type for the event
        alias: The alias given to store or executor.
    """

    code: Union[int, int]
    alias: Optional[str]

    class Config:
        arbitrary_types_allowed = True

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} (code={self.code})>"


class JobEvent(SchedulerEvent):
    """
    The events for a specific job.

    Args:
        job_id: The identifier given to a job.
        store: The alias given to a store.
    """

    job_id: Union[str, int]
    store: Union[str, Any]


class JobSubmissionEvent(JobEvent):
    """
    Event related to the submission of a job.

    Args:
        scheduled_run_times: List of datetimes when the job is supposed to run.
    """

    scheduled_run_times: List[datetime]


class JobExecutionEvent(JobEvent):
    """
    Event relared to the running of a job within the executor.

    Args:
        scheduled_run_times: The time when the job was scheduled to be run.
        return_value: The return value of the job successfully executed.
        exception: The exception raised by the job.
        traceback: A formated traceback for the exception.
    """

    scheduled_run_time: Union[int, str, Any]
    return_value: Any
    exception: Optional[Exception]
    traceback: Optional[str]
