from abc import ABC, abstractmethod
from datetime import datetime, tzinfo
from typing import ClassVar, Optional, Union, overload


class TriggerType(ABC):
    alias: ClassVar[str]
    jitter: Optional[int] = None
    allow_mistrigger_by_default: bool = False

    @abstractmethod
    def get_next_trigger_time(
        self, timezone: tzinfo, previous_time: Optional[datetime], now: Optional[datetime] = None
    ) -> Union[datetime, None]:
        """
        Returns the next datetime to trigger. If the datetime cannot be calculated, then returns None.

        Args:
            previous_time: The previous time the trigger was fired.
            now: The current datetime.
        """
        ...

    @overload
    def apply_jitter(
        self, next_trigger_time: datetime, jitter: Optional[int], now: datetime
    ) -> datetime: ...

    @overload
    def apply_jitter(
        self, next_trigger_time: None, jitter: Optional[int], now: datetime
    ) -> None: ...

    @abstractmethod
    def apply_jitter(
        self, next_trigger_time: Optional[datetime], jitter: Optional[int], now: datetime
    ) -> Union[datetime, None]: ...
