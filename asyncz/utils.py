import inspect
import re
from collections.abc import Callable
from datetime import date, datetime, time, timedelta, tzinfo
from datetime import timezone as dttz
from functools import partial
from typing import Any, Optional, Union, cast, overload

from asyncz.exceptions import AsynczException, AsynczLookupError

try:
    from tzlocal import get_localzone as _get_localzone

    def get_localzone() -> tzinfo:
        return _get_localzone()
except ImportError:

    def get_localzone() -> tzinfo:
        return dttz.utc


try:
    from zoneinfo import ZoneInfo  # type: ignore[import-not-found,unused-ignore]
except ImportError:
    from backports.zoneinfo import ZoneInfo  # type: ignore[no-redef,unused-ignore]


DATE_REGEX = re.compile(
    r"(?P<year>\d{4})-(?P<month>\d{1,2})-(?P<day>\d{1,2})"
    r"(?:[ T](?P<hour>\d{1,2}):(?P<minute>\d{1,2}):(?P<second>\d{1,2})"
    r"(?:\.(?P<microsecond>\d{1,6}))?"
    r"(?P<timezone>Z|[+-]\d\d:\d\d)?)?$"
)


@overload
def to_int(value: None) -> None: ...


@overload
def to_int(value: Union[str, float]) -> int: ...


def to_int(value: Union[str, float, None]) -> Optional[int]:
    """
    Safely converts a value to integer.
    """
    if value is not None:
        return int(value)
    return None


@overload
def to_float(value: None) -> None: ...


@overload
def to_float(value: Union[str, int, float]) -> float: ...


def to_float(value: Union[str, int, float, None]) -> Optional[float]:
    """
    Safely converts a value to float.
    """
    if value is not None:
        return float(value)
    return None


@overload
def to_timezone(value: None) -> None: ...


@overload
def to_timezone(value: Union[str, tzinfo]) -> tzinfo: ...


def to_timezone(value: Any) -> Optional[tzinfo]:
    """
    Converts a value to timezone object.
    """
    if isinstance(value, str):
        # python 3.8 typing issue
        return cast(tzinfo, ZoneInfo(value))
    if isinstance(value, tzinfo):
        return value
    if value is not None:
        raise TypeError(f"Expected tzinfo, got {value.__class__.__name__} instead")
    return None


def to_timezone_with_fallback(value: Any = None) -> tzinfo:
    timezone: Optional[tzinfo] = to_timezone(value)
    if timezone is None:
        timezone = get_localzone()
    return timezone


@overload
def to_datetime(
    value: None, tz: Union[tzinfo, str, None], arg_name: str, require_tz: bool = True
) -> None: ...


@overload
def to_datetime(
    value: Union[str, datetime, date],
    tz: Union[tzinfo, str, None],
    arg_name: str,
    require_tz: bool = True,
) -> Union[datetime, Any]: ...


def to_datetime(
    value: Union[str, datetime, date, None],
    tz: Union[tzinfo, str, None],
    arg_name: str,
    require_tz: bool = True,
) -> Union[datetime, None, Any]:
    """
    Converts the given value to a timezone compatible aware datetime object.

    If a timezone aware datetime object is passed, it is returned unmodified.
    If a native datetime object is passed, it is given the specified timezone.
    If the input is a string, it is parsed as a datetime with the given timezone.
    """
    if not value or value is None:
        return None

    if isinstance(value, datetime):
        _datetime = value
    elif isinstance(value, date):
        _datetime = datetime.combine(value, time())
    elif isinstance(value, str):
        _value = DATE_REGEX.match(value)

        if not _value:
            raise AsynczException(detail="Invalid date string.")

        values = _value.groupdict()
        tzname = values.pop("timezone")

        if tzname == "Z":
            tz = dttz.utc
        elif tzname:
            hours, minutes = (int(x) for x in tzname[1:].split(":"))
            sign = 1 if tzname[0] == "+" else -1
            tz = dttz(sign * timedelta(hours=hours, minutes=minutes))

        values = {k: int(v or 0) for k, v in values.items()}
        _datetime = datetime(**values)  # type: ignore
    else:
        raise AsynczException(
            detail=f"Unsupported type for {arg_name}: {value.__class__.__name__}."
        )

    if _datetime.tzinfo is not None:
        return _datetime

    if tz is None:
        if not require_tz:
            return _datetime
        raise AsynczException(
            detail=f'The "tz" argument must be specified if {arg_name} has no timezone information'
        )

    if isinstance(tz, str):
        # python 3.8 typing issue
        tz = cast(tzinfo, ZoneInfo(tz))

    return localize(_datetime, tz)


@overload
def datetime_to_utc_timestamp(timeval: None) -> None: ...


@overload
def datetime_to_utc_timestamp(timeval: datetime) -> float: ...


def datetime_to_utc_timestamp(timeval: Optional[datetime]) -> Optional[float]:
    """
    Converts a datetime instance to a timestamp.
    """
    if timeval is not None:
        return timeval.timestamp()
    return None


@overload
def utc_timestamp_to_datetime(timestamp: None) -> None: ...


@overload
def utc_timestamp_to_datetime(timestamp: Union[int, float]) -> datetime: ...


def utc_timestamp_to_datetime(timestamp: Union[int, float, None]) -> Optional[datetime]:
    """
    Converts the given timestamp to a datetime instance.
    """
    if timestamp is not None:
        return datetime.fromtimestamp(timestamp, dttz.utc)
    return None


def timedelta_seconds(delta: timedelta) -> float:
    """
    Converts the given timedelta to seconds.
    """
    return delta.days * 24 * 60 * 60 + delta.seconds + delta.microseconds / 1000000.0


def datetime_ceil(dateval: datetime) -> datetime:
    """
    Rounds the given datetime object upwards.
    """
    if dateval.microsecond > 0:
        return dateval + timedelta(seconds=1, microseconds=-dateval.microsecond)
    return dateval


def datetime_repr(dateval: Optional[datetime]) -> str:
    return dateval.strftime("%Y-%m-%d %H:%M:%S %Z") if dateval else "None"


def get_callable_name(func: Callable) -> str:
    """
    Returns the best available display name for the given function/callable.
    """
    # the easy case (on Python 3.3+)
    if hasattr(func, "__qualname__"):
        return func.__qualname__

    # class methods, bound and unbound methods
    f_self = getattr(func, "__self__", None) or getattr(func, "im_self", None)
    if f_self and hasattr(func, "__name__"):
        f_class = f_self if inspect.isclass(f_self) else f_self.__class__
    else:
        f_class = getattr(func, "im_class", None)

    if f_class and hasattr(func, "__name__"):
        return f"{f_class.__name__}.{func.__name__}"

    if hasattr(func, "__call__"):  # noqa
        if hasattr(func, "__name__"):
            return func.__name__
        return func.__class__.__name__

    raise TypeError(f"Unable to determine a name for {func!r} -- maybe it is not a callable?")


def obj_to_ref(obj: Any) -> str:
    """
    Returns the path to the given callable.
    """
    if isinstance(obj, partial):
        raise ValueError("Cannot create a reference to a partial()")

    name = get_callable_name(obj)
    if "<lambda>" in name:
        raise ValueError("Cannot create a reference to a lambda")
    if "<locals>" in name:
        raise ValueError("Cannot create a reference to a nested function")

    if inspect.ismethod(obj):
        if hasattr(obj, "im_self") and obj.im_self:
            module = obj.im_self.__module__
        elif hasattr(obj, "im_class") and obj.im_class:
            module = obj.im_class.__module__
        else:
            module = obj.__module__
    else:
        module = obj.__module__
    return f"{module}:{name}"


def ref_to_obj(ref: str) -> Any:
    """
    Returns the object pointed to by ``ref``.
    """
    if not isinstance(ref, str):
        raise TypeError("References must be strings")
    if ":" not in ref:
        raise AsynczException("Invalid reference")

    modulename, rest = ref.split(":", 1)
    try:
        obj = __import__(modulename, fromlist=[rest])
    except ImportError:
        raise AsynczLookupError(
            f"Error resolving reference {ref}: could not import module"
        ) from None
    try:
        for name in rest.split("."):
            obj = getattr(obj, name)

        # It might come from a class containing the fn attribute
        # implementation of the __call__ method
        if hasattr(obj, "fn"):
            obj = obj.fn
        return obj
    except Exception:
        raise AsynczLookupError(
            f"Error resolving reference {ref}: error looking up object"
        ) from None


def maybe_ref(ref: Any) -> Any:
    """
    Returns the object that the given reference points to, if it is indeed a reference.
    If it is not a reference, the object is returned as-is.
    """
    if not isinstance(ref, str):
        return ref
    return ref_to_obj(ref)


def make_function(func: Any) -> Callable[..., Any]:
    """For wrapping generator fns."""

    def _(*args: Any, **kwargs: Any) -> Any:
        return func(*args, **kwargs)

    return _


def make_async_function(func: Any) -> Callable[..., Any]:
    """For wrapping generator fns."""

    async def _(*args: Any, **kwargs: Any) -> Any:
        return await func(*args, **kwargs)

    return _


def check_callable_args(func: Callable[..., Any], args: Any, kwargs: Any) -> None:
    """
    Ensures that the given callable can be called with the given arguments.
    """
    pos_kwargs_conflicts = []
    positional_only_kwargs = []
    unsatisfied_args = []
    unsatisfied_kwargs = []
    unmatched_args = list(args)
    unmatched_kwargs = list(kwargs)
    has_varargs = has_var_kwargs = False

    try:
        sig = inspect.signature(func, follow_wrapped=False)
    except ValueError as e:
        raise AsynczException(detail=str(e)) from e

    for param in sig.parameters.values():
        if param.kind == param.POSITIONAL_OR_KEYWORD:
            if param.name in unmatched_kwargs and unmatched_args:
                pos_kwargs_conflicts.append(param.name)
            elif unmatched_args:
                del unmatched_args[0]
            elif param.name in unmatched_kwargs:
                unmatched_kwargs.remove(param.name)
            elif param.default is param.empty:
                unsatisfied_args.append(param.name)
        elif param.kind == param.POSITIONAL_ONLY:
            if unmatched_args:
                del unmatched_args[0]
            elif param.name in unmatched_kwargs:
                unmatched_kwargs.remove(param.name)
                positional_only_kwargs.append(param.name)
            elif param.default is param.empty:
                unsatisfied_args.append(param.name)
        elif param.kind == param.KEYWORD_ONLY:
            if param.name in unmatched_kwargs:
                unmatched_kwargs.remove(param.name)
            elif param.default is param.empty:
                unsatisfied_kwargs.append(param.name)
        elif param.kind == param.VAR_POSITIONAL:
            has_varargs = True
        elif param.kind == param.VAR_KEYWORD:
            has_var_kwargs = True

    if pos_kwargs_conflicts:
        raise ValueError(
            "The following arguments are supplied in both args and kwargs: {}".format(
                ", ".join(pos_kwargs_conflicts)
            )
        )

    if positional_only_kwargs:
        raise ValueError(
            "The following arguments cannot be given as keyword arguments: {}".format(
                ", ".join(positional_only_kwargs)
            )
        )

    if unsatisfied_args:
        raise ValueError(
            "The following arguments have not been supplied: {}".format(
                ", ".join(unsatisfied_args)
            )
        )

    if unsatisfied_kwargs:
        raise ValueError(
            "The following keyword-only arguments have not been supplied in kwargs: {}".format(
                ", ".join(unsatisfied_kwargs)
            )
        )

    if not has_varargs and unmatched_args:
        raise ValueError(
            "The list of positional arguments is longer than the target callable can handle "
            f"(allowed: {len(args) - len(unmatched_args)}, given in args: {len(args)})"
        )

    if not has_var_kwargs and unmatched_kwargs:
        raise ValueError(
            "The target callable does not accept the following keyword arguments: {}".format(
                ", ".join(unmatched_kwargs)
            )
        )


def normalize(value: datetime) -> datetime:
    # applies dst change
    return datetime.fromtimestamp(value.timestamp(), value.tzinfo)


def localize(value: datetime, tzinfo: tzinfo) -> datetime:
    if hasattr(tzinfo, "localize"):
        # pytz localize
        return cast(datetime, tzinfo.localize(value))

    return normalize(value.replace(tzinfo=tzinfo))
