from datetime import datetime, timedelta, tzinfo
from math import ceil
from typing import Any, ClassVar, Optional, Union

from asyncz.datastructures import IntervalState
from asyncz.triggers.base import BaseTrigger
from asyncz.utils import datetime_repr, normalize, timedelta_seconds, to_datetime, to_timezone


class IntervalTrigger(BaseTrigger):
    """
    Triggers on a specific intervals, starting on start_at if specified or datetime.now() + interval otherwise.

    Args:
        weeks: Number of weeks to wait.
        days: Number of days to wait.
        hours: Number of hours to wait.
        minutes: Number of minutes to wait.
        seconds: Number of seconds to wait.
        start_at: Starting point for the interval calculation.
        end_at: Latest possible date/time to trigger on.
        timezone: Time zone to use gor the date/time calculations.
        jitter: Delay the task execution by jitter seconds at most.
    """

    alias: ClassVar[str] = "interval"
    timezone: Optional[tzinfo] = None

    def __init__(
        self,
        weeks: int = 0,
        days: int = 0,
        hours: int = 0,
        minutes: int = 0,
        seconds: int = 0,
        start_at: Optional[Union[datetime, str]] = None,
        end_at: Optional[Union[datetime, str]] = None,
        timezone: Optional[Union[tzinfo, str]] = None,
        jitter: Optional[int] = None,
        **kwargs: Any,
    ):
        super().__init__(jitter=jitter, **kwargs)
        self.interval = timedelta(
            weeks=weeks, days=days, hours=hours, minutes=minutes, seconds=seconds
        )
        self.interval_size = timedelta_seconds(self.interval)

        if self.interval_size == 0:
            self.interval = timedelta(seconds=1)
            self.interval_size = 1

        if timezone:
            self.timezone = to_timezone(timezone)
        elif isinstance(start_at, datetime) and start_at.tzinfo:
            self.timezone = start_at.tzinfo
        elif isinstance(end_at, datetime) and end_at.tzinfo:
            self.timezone = end_at.tzinfo
        else:
            self.timezone = None

        start_at = start_at or (datetime.now(self.timezone) + self.interval)
        self.start_at = to_datetime(start_at, self.timezone, "start_at", require_tz=False)
        self.end_at = to_datetime(end_at, self.timezone, "end_at", require_tz=False)

    def get_next_trigger_time(
        self,
        timezone: tzinfo,
        previous_time: Optional[datetime],
        now: Union[datetime, None] = None,
    ) -> Union[datetime, None]:
        timezone = self.timezone or timezone
        if now is None:
            now = datetime.now(timezone)
        next_trigger_time: Optional[datetime]
        start_at = (
            self.start_at.replace(tzinfo=timezone)
            if self.start_at and self.start_at.tzinfo is None
            else self.start_at
        )
        if previous_time:
            next_trigger_time = previous_time + self.interval
        elif start_at > now:
            next_trigger_time = start_at
        else:
            time_difference_seconds = timedelta_seconds(now - start_at)
            next_interval_number = int(ceil(time_difference_seconds / self.interval_size))
            next_trigger_time = start_at + self.interval * next_interval_number

        if self.jitter is not None:
            next_trigger_time = self.apply_jitter(
                next_trigger_time=next_trigger_time, jitter=self.jitter, now=now
            )
        end_at = (
            self.end_at.replace(tzinfo=timezone)
            if self.end_at and self.end_at.tzinfo is None
            else self.end_at
        )

        if not end_at or next_trigger_time <= end_at:
            return normalize(value=next_trigger_time)
        return None

    def __getstate__(self) -> IntervalState:  # type: ignore
        state = IntervalState(
            timezone=self.timezone,
            start_at=self.start_at,
            end_at=self.end_at,
            interval=self.interval,
            jitter=self.jitter,
        )
        return state

    def __str__(self) -> str:
        return f"interval[{self.interval}]"

    def __repr__(self) -> str:
        options = [
            f"interval={self.interval!r}",
            f"start_at={datetime_repr(self.start_at)!r}",
        ]
        if self.end_at:
            options.append(f"end_at={datetime_repr(self.end_at)!r}")
        if self.jitter:
            options.append(f"jitter={self.jitter}")

        return "<{} ({}, timezone='{}')>".format(
            self.__class__.__name__,
            ", ".join(options),
            self.timezone,
        )
