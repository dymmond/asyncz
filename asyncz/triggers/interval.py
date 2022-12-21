from datetime import datetime, timedelta, tzinfo
from math import ceil
from typing import Any, Dict, Optional, Union

from asyncz.datastructures import IntervalState
from asyncz.triggers.base import BaseTrigger
from asyncz.typing import DictAny
from asyncz.utils import (
    datetime_repr,
    normalize,
    timedelta_seconds,
    to_datetime,
    to_timezone,
)
from tzlocal import get_localzone


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

    alias: str = "interval"

    def __init__(
        self,
        weeks: Optional[int] = 0,
        days: Optional[int] = 0,
        hours: Optional[int] = 0,
        minutes: Optional[int] = 0,
        seconds: Optional[int] = 0,
        start_at: Optional[Union[datetime, str]] = None,
        end_at: Optional[Union[datetime, str]] = None,
        timezone: Optional[Union[tzinfo, str]] = None,
        jitter: Optional[int] = None,
        **kwargs: Dict[str, Any],
    ):
        super().__init__(**kwargs)
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
            self.timezone = get_localzone()

        start_at = start_at or (datetime.now(self.timezone) + self.interval)
        self.start_at = to_datetime(start_at, self.timezone, "start_at")
        self.end_at = to_datetime(end_at, self.timezone, "start_at")
        self.jitter = jitter

    def get_next_trigger_time(
        self, previous_time: datetime, now: datetime
    ) -> Union[datetime, None]:

        if previous_time:
            next_trigger_time = previous_time + self.interval
        elif self.start_at > now:
            next_trigger_time = self.start_at
        else:
            time_difference_seconds = timedelta_seconds(now - self.start_at)
            next_interval_number = int(ceil(time_difference_seconds / self.interval_size))
            next_trigger_time = self.start_at + self.interval * next_interval_number

        if self.jitter is not None:
            next_trigger_time = self.apply_jitter(
                next_trigger_time=next_trigger_time, jitter=self.jitter, now=now
            )

        if not self.end_at or next_trigger_time <= self.end_at:
            return normalize(value=next_trigger_time)

    def __getstate__(self) -> IntervalState:
        state = IntervalState(
            timezone=self.timezone,
            start_at=self.start_at,
            end_at=self.end_at,
            interval=self.interval,
            jitter=self.jitter,
        )
        return state

    def __setstate__(self, state: "DictAny") -> None:
        trigger = super().__setstate__(state)
        trigger.interval_size = timedelta_seconds(self.interval)

    def __str__(self) -> str:
        return f"interval[{self.interval}]"

    def __repr__(self) -> str:
        options = ["interval=%r" % self.interval, "start_at=%r" % datetime_repr(self.start_at)]
        if self.end_at:
            options.append("end_at=%r" % datetime_repr(self.end_at))
        if self.jitter:
            options.append("jitter=%s" % self.jitter)

        return "<%s (%s, timezone='%s')>" % (
            self.__class__.__name__,
            ", ".join(options),
            self.timezone,
        )
