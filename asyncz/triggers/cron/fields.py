import re
from calendar import monthrange
from datetime import date, datetime
from typing import Any, ClassVar, Optional, Union, cast

from pydantic import BaseModel, ConfigDict

from asyncz.triggers.cron.constants import MAX_VALUES, MIN_VALUES
from asyncz.triggers.cron.expressions import (
    AllExpression,
    BaseExpression,
    LastDayOfMonthExpression,
    MonthRangeExpression,
    RangeExpression,
    WeekdayPositionExpression,
    WeekdayRangeExpression,
)

SEPARATOR = re.compile(" *, *")


class BaseField(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    name: str
    exprs: Any
    is_default: bool
    real: ClassVar[bool] = True
    compilers: ClassVar[tuple[type[BaseExpression], ...]] = (AllExpression, RangeExpression)
    expressions: list[BaseExpression]

    def __init__(
        self,
        name: str,
        exprs: Any,
        is_default: Optional[bool] = False,
        **kwargs: Any,
    ):
        super().__init__(name=name, exprs=exprs, is_default=is_default, expressions=[], **kwargs)
        self.compile_expressions(self.exprs)

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        if cls is not BaseField:
            cls.compilers = (AllExpression, RangeExpression, *cls.compilers)

    def get_min(self, dateval: Union[date, datetime]) -> int:
        # We need dateval for calculation the limits of e.g. the current month
        return MIN_VALUES[self.name]

    def get_max(self, dateval: Union[date, datetime]) -> int:
        # We need dateval for calculation the limits of e.g. the current month
        return MAX_VALUES[self.name]

    def get_value(self, dateval: Union[date, datetime]) -> int:
        return cast(int, getattr(dateval, self.name))

    def get_next_value(self, dateval: datetime) -> Optional[int]:
        smallest: Optional[int] = None
        for expr in self.expressions:
            value = expr.get_next_value(dateval, self)
            if smallest is None or (value is not None and value < smallest):
                smallest = value

        return smallest

    def compile_expressions(self, exprs: Any) -> None:
        self.expressions: list[Any] = []

        for expr in SEPARATOR.split(str(exprs).strip()):
            self.compile_expression(expr)

    def compile_expression(self, expr: Any) -> None:
        for compiler in self.compilers or []:
            match = compiler.regex.match(expr)
            if match:
                compiled_expr = compiler(**match.groupdict())
                try:
                    compiled_expr.validate_range(self.name)
                except ValueError as e:
                    message = f"Error validating expression {expr!r}: {e}"
                    raise ValueError(message) from e
                self.expressions.append(compiled_expr)
                return

        raise ValueError(f'Unrecognized expression "{expr}" for field "{self.name}"')

    def __eq__(self, other: Any) -> bool:
        return isinstance(self, self.__class__) and self.expressions == other.expressions

    def __str__(self) -> str:
        expr_strings = (str(e) for e in self.expressions)
        return ",".join(expr_strings)

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}('{self.name}', '{self}')"


class WeekField(BaseField):
    real: ClassVar[bool] = False

    def get_value(self, dateval: Union[date, datetime]) -> int:
        return dateval.isocalendar()[1]


class DayOfMonthField(BaseField):
    compilers = (WeekdayPositionExpression, LastDayOfMonthExpression)

    def get_max(self, dateval: Union[date, datetime]) -> int:
        return monthrange(dateval.year, dateval.month)[1]


class DayOfWeekField(BaseField):
    real: ClassVar[bool] = False
    compilers = (WeekdayRangeExpression,)

    def get_value(self, dateval: Union[date, datetime]) -> int:
        return dateval.weekday()


class MonthField(BaseField):
    compilers = (MonthRangeExpression,)
