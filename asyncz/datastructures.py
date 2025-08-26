from collections.abc import Callable
from datetime import datetime, timedelta, tzinfo
from typing import TYPE_CHECKING, Any, Optional, Union

from pydantic import BaseModel, ConfigDict

if TYPE_CHECKING:
    from asyncz.stores.types import StoreType
    from asyncz.triggers.types import TriggerType
else:
    StoreType = Any
    TriggerType = Any


class BaseDatastructureState(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)


class DateState(BaseDatastructureState):
    """
    Handles the state for a DateTrigger.
    """

    run_at: datetime


class IntervalState(BaseDatastructureState):
    """
    Handles the state for a IntervalTrigger.
    """

    timezone: Optional[tzinfo] = None
    start_at: datetime
    end_at: Optional[datetime] = None
    interval: Optional[timedelta] = None
    jitter: Optional[int] = None


class CombinationState(BaseDatastructureState):
    """
    Handles the state of the BaseCombination.
    """

    triggers: list[Any]
    jitter: Optional[int] = None


class CronState(BaseDatastructureState):
    """
    Handles the state of the CronTrigger.
    """

    timezone: Optional[tzinfo] = None
    start_at: Optional[datetime] = None
    end_at: Optional[datetime] = None
    fields: Optional[list[Any]] = None
    jitter: Optional[int] = None


class TaskState(BaseDatastructureState):  # type: ignore
    id: Optional[str] = None
    name: Optional[str] = None
    fn: Optional[Union[Callable[..., Any], str]] = None
    fn_reference: Optional[str] = None
    args: Optional[Any] = None
    kwargs: Optional[Any] = None
    coalesce: Optional[bool] = None
    trigger: Optional[TriggerType] = None
    executor: Optional[str] = None
    mistrigger_grace_time: Optional[int] = None
    max_instances: Optional[int] = None
    next_run_time: Optional[datetime] = None
    scheduler: Optional[Any] = None
    store_alias: Optional[str] = None
