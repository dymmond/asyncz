from datetime import datetime, tzinfo
from typing import Any, ClassVar, Optional, Union

from tzlocal import get_localzone

from asyncz.datastructures import DateState
from asyncz.triggers.base import BaseTrigger
from asyncz.utils import datetime_repr, to_datetime, to_timezone


class DateTrigger(BaseTrigger):
    """
    Triggers once on the given datetime. If run_at is left empty then the current time is used.

    Args:
        run_at: The date/time to run the task at.
        timezone: The time zone for the run_at if it does not have one already.
    """

    alias: ClassVar[str] = "date"

    def __init__(
        self,
        run_at: Optional[Union[datetime, str]] = None,
        timezone: Optional[Union[tzinfo, str]] = None,
        **kwargs: Any,
    ):
        super().__init__(**kwargs)
        timezone = to_timezone(timezone) or get_localzone()
        if run_at is not None:
            self.run_at = to_datetime(run_at, timezone, "run_at")
        else:
            self.run_at = datetime.now(timezone)

    def get_next_trigger_time(
        self, previous_time: Optional[datetime], now: Optional[datetime] = None
    ) -> Union[datetime, None]:
        if previous_time is None:
            return self.run_at
        return None

    def __getstate__(self) -> Any:
        """
        Handles the conversion to a dict to be able to pickle.
        """
        state = DateState(run_at=self.run_at)
        return state

    def __str__(self) -> str:
        return f"date[{datetime_repr(self.run_at)}]"

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} (run_at='{datetime_repr(self.run_at)}')>"
