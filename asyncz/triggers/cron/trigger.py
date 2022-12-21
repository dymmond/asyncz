from datetime import datetime, timedelta, tzinfo
from typing import Any, Dict, Optional, Union

from asyncz.datastructures import CronState
from asyncz.triggers.base import BaseTrigger
from asyncz.triggers.cron.constants import DEFAULT_VALUES
from asyncz.triggers.cron.fields import (
    BaseField,
    DayOfMonthField,
    DayOfWeekField,
    MonthField,
    WeekField,
)
from asyncz.typing import DictAny
from asyncz.utils import (
    datetime_ceil,
    datetime_repr,
    localize,
    normalize,
    to_datetime,
    to_timezone,
)
from tzlocal import get_localzone


class CronTrigger(BaseTrigger):
    """
    Triggers when the current time matches all specified time constraints. Very simlar to the way
    UNIX cron scheduler works.

    ┌───────────── minute (0 - 59)
    │ ┌───────────── hour (0 - 23)
    │ │ ┌───────────── day of the month (1 - 31)
    │ │ │ ┌───────────── month (1 - 12)
    │ │ │ │ ┌───────────── day of the week (0 - 6) (Sunday to Saturday;
    │ │ │ │ │                                   7 is also Sunday on some systems)
    │ │ │ │ │
    │ │ │ │ │
    * * * * * <command to execute>

    Args:
        year: 4-digit value.
        month: Month (1-12).
        day: Day of the month (1-31).
        week: ISO week (1-53).
        day_of_week: Number or name of weekday (0-6 or mon,tue,wed,thu,fri,sat,sun).
        hour: Hour (0-23).
        minute: Minute (0-59).
        second: Second (0-59).
        start_at: Earliest possible date/time to trigger on (inclusive).
        end_at: Latest possible date/time to trier on (inclusive).
        timezone: Time zone to use for the date/time calculations (defaults to scheduler timezone).
        jitter: Delay the task executions by jitter seconds at most.

    The first day of the week is always monday.
    """

    alias: str = "cron"

    def __init__(
        self,
        year: Optional[Union[int, str]] = None,
        month: Optional[Union[int, str]] = None,
        day: Optional[Union[int, str]] = None,
        week: Optional[Union[int, str]] = None,
        day_of_week: Optional[Union[int, str]] = None,
        hour: Optional[Union[int, str]] = None,
        minute: Optional[Union[int, str]] = None,
        second: Optional[Union[int, str]] = None,
        start_at: Optional[Union[datetime, str]] = None,
        end_at: Optional[Union[datetime, str]] = None,
        timezone: Optional[Union[tzinfo, str]] = None,
        jitter: Optional[int] = None,
        **kwargs: Dict[str, Any],
    ):
        super().__init__(**kwargs)
        self.year = year
        self.month = month
        self.day = day
        self.week = week
        self.day_of_week = day_of_week
        self.hour = hour
        self.minute = minute
        self.second = second
        self.minute = minute
        self.field_names = (
            "year",
            "month",
            "day",
            "week",
            "day_of_week",
            "hour",
            "minute",
            "second",
        )
        self.fields_map = {
            "year": BaseField,
            "month": MonthField,
            "week": WeekField,
            "day": DayOfMonthField,
            "day_of_week": DayOfWeekField,
            "hour": BaseField,
            "minute": BaseField,
            "second": BaseField,
        }

        if timezone:
            self.timezone = to_timezone(timezone)
        elif isinstance(start_at, datetime) and start_at.tzinfo:
            self.timezone = start_at.tzinfo
        elif isinstance(end_at, datetime) and end_at.tzinfo:
            self.timezone = end_at.tzinfo
        else:
            self.timezone = get_localzone()

        self.start_at = to_datetime(start_at, self.timezone, "start_at")
        self.end_at = to_datetime(end_at, self.timezone, "end_at")
        self.jitter = jitter

        values = dict(
            (key, value)
            for key, value in iter(locals().items())
            if key in self.field_names and value is not None
        )

        self.fields = []
        assign_defaults = False

        for field_name in self.field_names:
            if field_name in values:
                expressions = values.pop(field_name)
                is_default = False
                assign_defaults = not values
            elif assign_defaults:
                expressions = DEFAULT_VALUES[field_name]
                is_default = True
            else:
                expressions = "*"
                is_default = True

            field_class = self.fields_map[field_name]
            field = field_class(field_name, expressions, is_default)
            self.fields.append(field)

    @classmethod
    def from_crontab(
        cls: "CronTrigger",
        expression: Union[str, Any],
        timezone: Optional[Union[str, tzinfo]] = None,
    ):
        """
        Creates a class CronTrigger from a standard crontab expression.
        See https://en.wikipedia.org/wiki/Cron for more information on the format accepted here.

        Args:
            expression - minute, hour, day of month, month, day of week.
            timezone  Time zone to use for the date/time calculations. Defaults to scheduler timezone.
        """
        values = expression.split()
        if len(values) != 5:
            raise ValueError(f"Wrong number of fields. Got {len(values)}, expected 5.")

        return cls(
            minute=values[0],
            hour=values[1],
            day=values[2],
            month=values[3],
            day_of_week=values[4],
            timezone=timezone,
        )

    def increment_field_value(self, dateval: datetime, field_number: int):
        """
        Increments the designated field and resets all significant fields to their minimum values
        """
        values = {}
        count = 0

        while count < len(self.fields):
            field = self.fields[count]

            if not field.real:
                if count == field_number:
                    field_number -= 1
                    count -= 1
                else:
                    count += 1
                continue

            if count < field_number:
                values[field.name] = field.get_value(dateval)
                count += 1
            elif count > field_number:
                values[field.name] = field.get_min(dateval)
                count += 1
            else:
                value = field.get_value(dateval)
                max_value = field.get_max(dateval)
                if value == max_value:
                    field_number -= 1
                    count -= 1
                else:
                    values[field.name] = value + 1
                    count += 1

        difference = datetime(**values) - dateval.replace(tzinfo=None)
        return normalize(dateval + difference), field_number

    def set_field_value(self, dateval: datetime, field_number: int, new_value: Any):
        values = {}
        for i, field in enumerate(self.fields):
            if field.real:
                if i < field_number:
                    values[field.name] = field.get_value(dateval)
                elif i > field_number:
                    values[field.name] = field.get_min(dateval)
                else:
                    values[field.name] = new_value

        return localize(datetime(**values), self.timezone)

    def get_next_trigger_time(
        self, previous_time: datetime, now: Optional[datetime] = None
    ) -> Union[datetime, None]:
        if previous_time:
            start_at = min(now, previous_time + timedelta(microseconds=1))
            if start_at == previous_time:
                start_at += timedelta(microseconds=1)
        else:
            start_at = max(now, self.start_at) if self.start_at else now

        fieldnum = 0
        next_date = datetime_ceil(start_at).astimezone(self.timezone)
        while 0 <= fieldnum < len(self.fields):
            field = self.fields[fieldnum]
            curr_value = field.get_value(next_date)
            next_value = field.get_next_value(next_date)

            if next_value is None:
                next_date, fieldnum = self.increment_field_value(next_date, fieldnum - 1)
            elif next_value > curr_value:
                if field.real:
                    next_date = self.set_field_value(next_date, fieldnum, next_value)
                    fieldnum += 1
                else:
                    next_date, fieldnum = self.increment_field_value(next_date, fieldnum)
            else:
                fieldnum += 1

            if self.end_at and next_date > self.end_at:
                return None

        if fieldnum >= 0:
            next_date = self.apply_jitter(next_date, self.jitter, now)
            return min(next_date, self.end_at) if self.end_at else next_date

    def __getstate__(self) -> "DictAny":
        state = CronState(
            timezone=self.timezone,
            start_at=self.start_at,
            end_at=self.end_at,
            fields=self.fields,
            jitter=self.jitter,
        )
        return state

    def __setstate__(self, state: "DictAny") -> Any:
        if isinstance(state, tuple):
            return state[1]
        super().__setstate__(state)

    def __str__(self):
        options = [f"{f.name}='{f}'" for f in self.fields if not f.is_default]
        return f"cron[{', '.join(options)}]"

    def __repr__(self) -> str:
        options = [f"{f.name}='{f}'" for f in self.fields if not f.is_default]
        if self.start_at:
            options.append(f"start_at='{datetime_repr(self.start_at)}'")
        if self.end_at:
            options.append(f"end_at='{datetime_repr(self.end_at)}'")

        if self.jitter:
            options.append(f"jitter='{self.jitter}'")

        return f"<{self.__class__.__name__} ({', '.join(options)}, timezone='{self.timezone}')>"
