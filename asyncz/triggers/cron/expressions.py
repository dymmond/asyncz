import re
from calendar import monthrange
from datetime import date, datetime
from typing import TYPE_CHECKING, Any, ClassVar, Optional, Union

from pydantic import BaseModel, ConfigDict, Field

from asyncz.triggers.cron.constants import MAX_VALUES, MIN_VALUES, MONTHS, OPTIONS, WEEKDAYS
from asyncz.utils import to_int

if TYPE_CHECKING:
    from asyncz.triggers.cron.types import FieldType


class BaseExpression(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True, extra="allow")
    regex: ClassVar[re.Pattern]


class AllExpression(BaseExpression):
    regex: ClassVar[re.Pattern] = re.compile(r"\*(?:/(?P<step>\d+))?$")
    step: Optional[int] = Field(gt=0, default=None)

    def __init__(self, step: Optional[Union[int, float]] = None, **kwargs: Any):
        kwargs["step"] = to_int(step)
        super().__init__(**kwargs)

    def validate_range(self, field_name: str) -> None:
        value_range = MAX_VALUES[field_name] - MIN_VALUES[field_name]
        if self.step and self.step > value_range:
            raise ValueError(
                f"The step value ({self.step}) is higher than the total range of the "
                f"expression ({value_range})."
            )

    def get_next_value(self, date: Union[date, datetime], field: "FieldType") -> Optional[int]:
        start = field.get_value(date)
        min_value = field.get_min(date)
        max_value = field.get_max(date)
        start = max(start, min_value)

        if not self.step:
            next_v = start
        else:
            distance_to_next = (self.step - (start - min_value)) % self.step
            next_v = start + distance_to_next

        if next_v <= max_value:
            return next_v
        return None

    def __eq__(self, other: Any) -> bool:
        return isinstance(other, self.__class__) and self.step == other.step

    def __str__(self) -> str:
        if self.step:
            return "*/%d" % self.step
        return "*"

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}({self.step})"


class RangeExpression(AllExpression):
    regex: ClassVar[re.Pattern] = re.compile(
        r"(?P<first>\d+)(?:-(?P<last>\d+))?(?:/(?P<step>\d+))?$"
    )

    def __init__(
        self,
        first: Union[str, float],
        last: Optional[Union[str, float]] = None,
        # for supporting positional as well as keyword calls
        step: Optional[Union[int, float]] = None,
        **kwargs: Any,
    ):
        super().__init__(step=step, **kwargs)
        first: Optional[int] = to_int(first)  # type: ignore
        last: Optional[int] = to_int(last)  # type: ignore

        if last is None and self.step is None:
            last = first
        if last is not None and first > last:  # type: ignore
            raise ValueError("The minimum value in a range must not be higher than the maximum.")

        self.first: int = first  # type: ignore
        self.last: int = last  # type: ignore

    def validate_range(self, field_name: str) -> None:
        super().validate_range(field_name)

        if self.first < MIN_VALUES[field_name]:
            raise ValueError(
                f"The first value ({self.first}) is lower than the minimum value ({MIN_VALUES[field_name]})."
            )

        if self.last is not None and self.last > MAX_VALUES[field_name]:
            raise ValueError(
                f"The last value ({self.last}) is higher than the maximum value ({MAX_VALUES[field_name]})."
            )

        value_range = (self.last or MAX_VALUES[field_name]) - self.first

        if self.step and self.step > value_range:
            raise ValueError(
                f"The step value ({self.step}) is higher than the total range of the "
                f"expression ({value_range})."
            )

    def get_next_value(self, date: Union[date, datetime], field: "FieldType") -> Optional[int]:
        start_value = field.get_value(date)
        min_value = field.get_min(date)
        max_value = field.get_max(date)

        min_value = max(min_value, self.first)
        max_value = min(max_value, self.last) if self.last is not None else max_value
        next_value = max(min_value, start_value)

        if self.step:
            distance_to_next = (self.step - (next_value - min_value)) % self.step
            next_value += distance_to_next

        return next_value if next_value <= max_value else None

    def __eq__(self, other: Any) -> bool:
        return (
            isinstance(other, self.__class__)
            and self.first == other.first
            and self.last == other.last
        )

    def __str__(self) -> str:
        if self.last != self.first and self.last is not None:
            range = "%d-%d" % (self.first, self.last)
        else:
            range = str(self.first)

        if self.step:
            return "%s/%d" % (range, self.step)
        return range

    def __repr__(self) -> str:
        args = [str(self.first)]
        if self.last != self.first and self.last is not None or self.step:
            args.append(str(self.last))
        if self.step:
            args.append(str(self.step))
        return f"{self.__class__.__name__}({', '.join(args)})"


class MonthRangeExpression(RangeExpression):
    regex: ClassVar[re.Pattern] = re.compile(
        r"(?P<first>[a-z]+)(?:-(?P<last>[a-z]+))?", re.IGNORECASE
    )
    step: Optional[int] = None

    def __init__(
        self,
        first: Union[str, float],
        last: Optional[Union[str, float]] = None,
        **kwargs: Any,
    ) -> None:
        if isinstance(first, float):
            first = str(first)

        try:
            first_number = MONTHS.index(first.lower()) + 1
        except ValueError:
            raise ValueError(f"Invalid month name '{first}'.") from None

        if not last:
            last_number = None
        else:
            if isinstance(last, float):
                last = str(last)

            try:
                last_number = MONTHS.index(last.lower()) + 1
            except ValueError:
                raise ValueError(f"Invalid month name '{last}'.") from None

        super().__init__(first_number, last_number, **kwargs)

    def __str__(self) -> str:
        if self.last != self.first and self.last is not None:
            return f"{MONTHS[self.first - 1]}-{MONTHS[self.last - 1]}"
        return MONTHS[self.first - 1]

    def __repr__(self) -> str:
        args = [f"'{MONTHS[self.first]}'"]
        if self.last != self.first and self.last is not None:
            args.append(f"'{MONTHS[self.last - 1]}'")
        return f"{self.__class__.__name__}({', '.join(args)})"


class WeekdayRangeExpression(RangeExpression):
    regex: ClassVar[re.Pattern] = re.compile(
        r"(?P<first>[a-z]+)(?:-(?P<last>[a-z]+))?", re.IGNORECASE
    )

    def __init__(
        self,
        first: Union[str, float],
        last: Optional[Union[str, float]] = None,
        **kwargs: Any,
    ):
        if isinstance(first, float):
            first = str(first)

        try:
            first_number = WEEKDAYS.index(first.lower())
        except ValueError:
            raise ValueError(f"Invalid weekday name '{first}'.") from None

        if not last:
            last_number = None
        else:
            if isinstance(last, float):
                last = str(last)

            try:
                last_number = WEEKDAYS.index(last.lower())
            except ValueError:
                raise ValueError(f"Invalid weekday name '{last}'") from None
        super().__init__(first_number, last_number, **kwargs)

    def __str__(self) -> str:
        if self.last != self.first and self.last is not None:
            return f"{WEEKDAYS[self.first]}-{WEEKDAYS[self.last]}"
        return WEEKDAYS[self.first]

    def __repr__(self) -> str:
        args = [f"'{WEEKDAYS[self.first]}'"]
        if self.last != self.first and self.last is not None:
            args.append(f"'{WEEKDAYS[self.last]}'")
        return f"{self.__class__.__name__}({', '.join(args)})"


class WeekdayPositionExpression(AllExpression):
    regex: ClassVar[re.Pattern] = re.compile(
        r"(?P<option_name>{}) +(?P<weekday_name>(?:\d+|\w+))".format("|".join(OPTIONS)),
        re.IGNORECASE,
    )

    def __init__(self, option_name: str, weekday_name: str, **kwargs: Any):
        super().__init__(step=None, **kwargs)
        try:
            self.option_number = OPTIONS.index(option_name.lower())
        except ValueError:
            raise ValueError(f'Invalid weekday position "{option_name}".') from None

        try:
            self.weekday = WEEKDAYS.index(weekday_name.lower())
        except ValueError:
            raise ValueError(f'Invalid weekday name "{weekday_name}".') from None

    def get_next_value(self, date: Union[date, datetime], field: "FieldType") -> Union[None, int]:
        first_day_wday, last_day = monthrange(date.year, date.month)

        first_hit_day = self.weekday - first_day_wday + 1
        if first_hit_day <= 0:
            first_hit_day += 7

        if self.option_number < 5:
            target_day = first_hit_day + self.option_number * 7
        else:
            target_day = first_hit_day + ((last_day - first_hit_day) // 7) * 7

        if target_day <= last_day and target_day >= date.day:
            return target_day
        return None

    def __eq__(self, other: Any) -> bool:
        return (
            super().__eq__(other)
            and self.option_number == other.option_num
            and self.weekday == other.weekday
        )

    def __str__(self) -> str:
        return f"{OPTIONS[self.option_number]} {WEEKDAYS[self.weekday]}"

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}('{OPTIONS[self.option_number]}"
            f"', '{WEEKDAYS[self.weekday]}')"
        )


class LastDayOfMonthExpression(AllExpression):
    regex: ClassVar[re.Pattern] = re.compile(r"last", re.IGNORECASE)

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(step=None, **kwargs)

    def get_next_value(self, date: Union[date, datetime], field: "FieldType") -> Optional[int]:
        return monthrange(date.year, date.month)[1]

    def __str__(self) -> str:
        return "last"

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}()"
