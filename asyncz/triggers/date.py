from datetime import datetime, tzinfo
from typing import Any, ClassVar, Optional, Union

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
    run_at: datetime

    def __init__(
        self,
        run_at: Optional[Union[datetime, str]] = None,
        timezone: Optional[Union[tzinfo, str]] = None,
        **kwargs: Any,
    ):
        timezone = to_timezone(timezone)
        if run_at is not None:
            kwargs["run_at"] = to_datetime(run_at, timezone, "run_at")
        else:
            kwargs["run_at"] = datetime.now(timezone)
            kwargs["allow_mistrigger_by_default"] = True
        super().__init__(**kwargs)

    def get_next_trigger_time(
        self, timezone: tzinfo, previous_time: Optional[datetime], now: Optional[datetime] = None
    ) -> Union[datetime, None]:
        if previous_time is None:
            return self.run_at.astimezone(timezone)
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
