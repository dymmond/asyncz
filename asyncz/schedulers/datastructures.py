from datetime import datetime
from typing import Any, Callable, Optional, Union

from asyncz.triggers.types import TriggerType
from asyncz.typing import DictAny, UndefinedType
from pydantic import BaseModel


class BaseStruct(BaseModel):
    class Config:
        arbitrary_types_allowed = True


class JobStruct(BaseStruct):
    """
    fn: Callable (or a textual reference to one) to run at the given time.
    trigger: Trigger that determines when fn is called.
    args: List of positional arguments to call fn with.
    kwargs: Dict of keyword arguments to call fn with.
    id: Explicit identifier for the job (for modifying it later).
    name: Textual description of the job.
    mistriger_grace_time: Seconds after the designated runtime that the job is still
        allowed to be run (or None to allow the job to run no matter how late it is).
    coalesce: Run once instead of many times if the scheduler determines that the
        job should be run more than once in succession.
    max_instances: Maximum number of concurrently running instances allowed for this job.
    next_trigger_time: When to first run the job, regardless of the trigger (pass
        None to add the job as paused).
    store: Alias of the job store to store the job in.
    executor: Alias of the executor to run the job with.
    """

    trigger: Optional[TriggerType]
    executor: Optional[str]
    fn: Optional[Callable[..., Any]]
    args: Optional[Any]
    kwargs: Optional["DictAny"]
    id: Optional[str]
    name: Optional[str]
    mistrigger_grace_time: Optional[Union[int, "UndefinedType"]]
    coalesce: Optional[Union[bool, "UndefinedType"]]
    max_instances: Optional[Union[int, "UndefinedType"]]
    next_run_time: Optional[Union[datetime, str]]


class JobDefaultStruct(BaseStruct):
    mistrigger_grace_time: Optional[Union[int, "UndefinedType"]]
    coalesce: Optional[Union[bool, "UndefinedType"]]
    max_instances: Optional[Union[int, "UndefinedType"]]
