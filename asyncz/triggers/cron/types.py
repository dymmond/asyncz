from typing import Union

from asyncz.triggers.cron.fields import (
    BaseField,
    DayOfMonthField,
    DayOfWeekField,
    MonthField,
    WeekField,
)

FieldType = Union[BaseField, DayOfMonthField, WeekField, DayOfWeekField, MonthField]
