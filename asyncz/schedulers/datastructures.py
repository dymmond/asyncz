from datetime import datetime
from typing import Any, Callable, Optional, Union

from asyncz.triggers.types import TriggerType
from asyncz.typing import DictAny, UndefinedType
from pydantic import BaseModel


class BaseStruct(BaseModel):
    class Config:
        arbitrary_types_allowed = True


class TaskStruct(BaseStruct):
    """
    fn: Callable (or a textual reference to one) to run at the given time.
    trigger: Trigger that determines when fn is called.
    args: List of positional arguments to call fn with.
    kwargs: Dict of keyword arguments to call fn with.
    id: Explicit identifier for the task (for modifying it later).
    name: Textual description of the task.
    mistriger_grace_time: Seconds after the designated runtime that the task is still
        allowed to be run (or None to allow the task to run no matter how late it is).
    coalesce: Run once instead of many times if the scheduler determines that the
        task should be run more than once in succession.
    max_instances: Maximum number of concurrently running instances allowed for this task.
    next_trigger_time: When to first run the task, regardless of the trigger (pass
        None to add the task as paused).
    store: Alias of the task store to store the task in.
    executor: Alias of the executor to run the task with.
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


class TaskDefaultStruct(BaseStruct):
    mistrigger_grace_time: Optional[Union[int, "UndefinedType"]]
    coalesce: Optional[Union[bool, "UndefinedType"]]
    max_instances: Optional[Union[int, "UndefinedType"]]
