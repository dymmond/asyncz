from datetime import datetime, timedelta, timezone, tzinfo
from typing import TYPE_CHECKING, Any, Callable, List, Optional, Union

from asyncz.typing import DictAny
from pydantic import BaseModel

if TYPE_CHECKING:
    from asyncz.stores.types import StoreType
    from asyncz.triggers.types import TriggerType
else:
    StoreType = Any
    TriggerType = Any


class BaseDatastructureState(BaseModel):
    class Config:
        arbitrary_types_allowed = True


class DateState(BaseDatastructureState):
    """
    Handles the state for a DateTrigger.
    """

    run_at: datetime


class IntervalState(BaseDatastructureState):
    """
    Handles the state for a IntervalTrigger.
    """

    timezone: Union[timezone, str, tzinfo]
    start_at: datetime
    end_at: Optional[datetime]
    interval: Optional[Union[timezone, timedelta]]
    jitter: int


class CombinationState(BaseDatastructureState):
    """
    Handles the state of the BaseCombination.
    """

    triggers: List[Any]
    jitter: Optional[int]


class CronState(BaseDatastructureState):
    """
    Handles the state of the CronTrigger.
    """

    timezone: Optional[Union[timezone, str, tzinfo]]
    start_at: Optional[datetime]
    end_at: Optional[datetime]
    fields: Optional[List[Any]]
    jitter: Optional[int]


class TaskState(BaseDatastructureState):
    id: Optional[str]
    name: Optional[str]
    fn: Optional[Union[Callable[..., Any], str]]
    fn_reference: Optional[str]
    args: Optional[Any]
    kwargs: Optional["DictAny"]
    coalesce: Optional[bool]
    trigger: Optional[Union[str, TriggerType]]
    executor: Optional[str]
    mistrigger_grace_time: Optional[int]
    max_instances: Optional[int]
    next_run_time: Optional[datetime]
    scheduler: Optional[Any]
    store_alias: Optional[str]
    store: Optional[Union[str, StoreType]]
