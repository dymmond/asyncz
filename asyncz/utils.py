import inspect
import re
from asyncio import iscoroutinefunction
from calendar import timegm
from datetime import date, datetime, time, timedelta, tzinfo
from functools import partial
from typing import Any, Dict, Union

from asyncz.exceptions import AsynczException, AsynczLookupError
from pytz import FixedOffset, timezone, utc

try:
    from threading import TIMEOUT_MAX
except ImportError:
    TIMEOUT_MAX = 4294967

BOOL_VALIDATION = {
    "true": ["true", "yes", "on", "y", "t", "1", True],
    "false": ["false", "no", "off", "f", "0", False],
}

DATE_REGEX = re.compile(
    r"(?P<year>\d{4})-(?P<month>\d{1,2})-(?P<day>\d{1,2})"
    r"(?:[ T](?P<hour>\d{1,2}):(?P<minute>\d{1,2}):(?P<second>\d{1,2})"
    r"(?:\.(?P<microsecond>\d{1,6}))?"
    r"(?P<timezone>Z|[+-]\d\d:\d\d)?)?$"
)


def repr_escape(string):
    return string


def to_int(value: Union[str, float]) -> int:
    """
    Safely converts a value to integer.
    """
    if value is not None:
        return int(value)


def to_float(value: Union[str, int]) -> float:
    """
    Safely converts a value to float.
    """
    if value is not None:
        return float(value)


def to_bool(value: str) -> bool:
    """
    Converts the given value into a boolean.
    """
    if isinstance(value, str):
        value = value.strip().lower()
    if value in BOOL_VALIDATION["true"]:
        return True
    elif value in BOOL_VALIDATION["false"]:
        return False
    return False


def to_timezone(value: Any) -> timezone:
    """
    Converts a value to timezone object.
    """
    if isinstance(value, str):
        return timezone(value)
    if isinstance(value, tzinfo):
        if not hasattr(value, "localize") or not hasattr(value, "normalize"):
            raise TypeError("Only timezones from the pytz library are supported.")
        if value.tzname(None) == "local":
            raise ValueError(
                "Unable to determine the name of the local timezone -- you must explicitly "
                "specify the name of the local timezone. Please refrain from using timezones like "
                "BST to prevent problems with daylight saving time. Instead, use a locale based "
                "timezone name (such as Europe/London)."
            )
        return value
    if value is not None:
        raise TypeError("Expected tzinfo, got %s instead" % value.__class__.__name__)


def to_datetime(value: Union[str, datetime], tz: tzinfo, arg_name: str) -> datetime:
    """
    Converts the given value to a timezone compatible aware datetime object.

    If a timezone aware datetime object is passed, it is returned unmodified.
    If a native datetime object is passed, it is given the specified timezone.
    If the input is a string, it is parsed as a datetime with the given timezone.
    """
    if not value or value is None:
        return

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
            tz = utc
        elif tzname:
            hours, minutes = (int(x) for x in tzname[1:].split(":"))
            sign = 1 if tzname[0] == "+" else -1
            tz = FixedOffset(sign * (hours * 60 + minutes))

        values = {k: int(v or 0) for k, v in values.items()}
        _datetime = datetime(**values)
    else:
        raise AsynczException(
            detail=f"Unsupported type for {arg_name}: {value.__class__.__name__}."
        )

    if _datetime.tzinfo is not None:
        return _datetime

    if tz is None:
        raise AsynczException(
            detail='The "tz" argument must be specified if %s has no timezone information'
            % arg_name
        )

    if isinstance(tz, str):
        tz = timezone(tz)

    return localize(_datetime, tz)


def datetime_to_utc_timestamp(timeval: datetime):
    """
    Converts a datetime instance to a timestamp.
    """
    if timeval is not None:
        return timegm(timeval.utctimetuple()) + timeval.microsecond / 1000000


def utc_timestamp_to_datetime(timestamp: Union[int, float]) -> datetime:
    """
    Converts the given timestamp to a datetime instance.
    """
    if timestamp is not None:
        return datetime.fromtimestamp(timestamp, utc)


def timedelta_seconds(delta: Any) -> Union[int, float]:
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


def datetime_repr(dateval: datetime) -> str:
    return dateval.strftime("%Y-%m-%d %H:%M:%S %Z") if dateval else "None"


def get_callable_name(func: Any) -> str:
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
        return "%s.%s" % (f_class.__name__, func.__name__)

    if hasattr(func, "__call__"):
        if hasattr(func, "__name__"):
            return func.__name__
        return func.__class__.__name__

    raise TypeError("Unable to determine a name for %r -- maybe it is not a callable?" % func)


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
    return "%s:%s" % (module, name)


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
        raise AsynczLookupError("Error resolving reference %s: could not import module" % ref)

    try:
        for name in rest.split("."):
            obj = getattr(obj, name)
        return obj
    except Exception:
        raise AsynczLookupError("Error resolving reference %s: error looking up object" % ref)


def maybe_ref(ref: str) -> Any:
    """
    Returns the object that the given reference points to, if it is indeed a reference.
    If it is not a reference, the object is returned as-is.
    """
    if not isinstance(ref, str):
        return ref
    return ref_to_obj(ref)


def check_callable_args(func, args: Any, kwargs: Dict[Any, Any]) -> None:
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
        raise AsynczException(detail=str(e))

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
            "The following arguments are supplied in both args and kwargs: %s"
            % ", ".join(pos_kwargs_conflicts)
        )

    if positional_only_kwargs:
        raise ValueError(
            "The following arguments cannot be given as keyword arguments: %s"
            % ", ".join(positional_only_kwargs)
        )

    if unsatisfied_args:
        raise ValueError(
            "The following arguments have not been supplied: %s" % ", ".join(unsatisfied_args)
        )

    if unsatisfied_kwargs:
        raise ValueError(
            "The following keyword-only arguments have not been supplied in kwargs: %s"
            % ", ".join(unsatisfied_kwargs)
        )

    if not has_varargs and unmatched_args:
        raise ValueError(
            "The list of positional arguments is longer than the target callable can handle "
            "(allowed: %d, given in args: %d)" % (len(args) - len(unmatched_args), len(args))
        )

    if not has_var_kwargs and unmatched_kwargs:
        raise ValueError(
            "The target callable does not accept the following keyword arguments: %s"
            % ", ".join(unmatched_kwargs)
        )


def iscoroutinefunction_partial(f: Any) -> bool:
    while isinstance(f, partial):
        f = f.func
    return iscoroutinefunction(f)


def normalize(value: datetime) -> datetime:
    return datetime.fromtimestamp(value.timestamp(), value.tzinfo)


def localize(value: datetime, tzinfo: tzinfo) -> datetime:
    if hasattr(tzinfo, "localize"):
        return tzinfo.localize(value)

    return normalize(value.replace(tzinfo=tzinfo))
