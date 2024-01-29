import platform
import sys
from datetime import date, datetime, timedelta, tzinfo
from functools import partial, wraps
from types import ModuleType
from unittest.mock import Mock

import pytest
import pytz

from asyncz.exceptions import AsynczException
from asyncz.tasks import Task
from asyncz.utils import (
    check_callable_args,
    datetime_ceil,
    datetime_repr,
    datetime_to_utc_timestamp,
    get_callable_name,
    maybe_ref,
    obj_to_ref,
    ref_to_obj,
    repr_escape,
    timedelta_seconds,
    to_bool,
    to_datetime,
    to_float,
    to_int,
    to_timezone,
    utc_timestamp_to_datetime,
)


class DummyClass:
    def meth(self): ...

    @staticmethod
    def staticmeth(): ...

    @classmethod
    def classmeth(cls): ...

    def __call__(self): ...

    class InnerDummyClass:
        @classmethod
        def innerclassmeth(cls): ...


class InheritedDummyClass(Task): ...


class TestToFloat:
    @pytest.mark.parametrize("value", ["5fs", "shplse"], ids=["digit first", "text"])
    def test_invalid_value(self, value):
        pytest.raises(ValueError, to_float, value)

    def test_number(self):
        assert to_float("539") == 539.0

    def test_none(self):
        assert to_float(None) is None


class TestToInt:
    @pytest.mark.parametrize("value", ["5s", "shplse"], ids=["digit first", "text"])
    def test_invalid_value(self, value):
        pytest.raises(ValueError, to_int, value)

    def test_number(self):
        assert to_int("539") == 539

    def test_none(self):
        assert to_int(None) is None


class TestToBool:
    @pytest.mark.parametrize(
        "value",
        [" True", "true ", "Yes", " yes ", "1  ", True],
        ids=["capital true", "lowercase true", "capital yes", "lowercase yes", "one", "True"],
    )
    def test_true(self, value):
        assert to_bool(value) is True

    @pytest.mark.parametrize(
        "value",
        [" False", "false ", "No", " no ", "0  ", False],
        ids=["capital", "lowercase false", "capital no", "lowercase no", "zero", "False"],
    )
    def test_false(self, value):
        assert to_bool(value) is False

    def test_bad_value(self):
        assert to_bool("yep") is False


class TestToTimezone:
    def test_str(self):
        value = to_timezone("Europe/London")
        assert isinstance(value, tzinfo)

    def test_tz(self):
        tz = pytz.timezone("Europe/London")
        value = to_timezone(tz)
        assert tz is value

    def test_none(self):
        assert to_timezone(None) is None

    def test_bad_timezone_type(self):
        exc = pytest.raises(TypeError, to_timezone, tzinfo())
        assert "Only timezones from the pytz library are supported" in str(exc.value)

    def test_bad_local_timezone(self):
        zone = Mock(tzinfo, localize=None, normalize=None, tzname=lambda dt: "local")
        exc = pytest.raises(ValueError, to_timezone, zone)
        assert "Unable to determine the name of the local timezone" in str(exc.value)

    def test_bad_value(self):
        exc = pytest.raises(TypeError, to_timezone, 4)
        assert "Expected tzinfo, got int instead" in str(exc.value)


class TestConvertToDatetime:
    @pytest.mark.parametrize(
        "input,expected",
        [
            (None, None),
            (date(2022, 8, 1), datetime(2022, 8, 1)),
            (datetime(2022, 8, 1, 5, 6, 12), datetime(2022, 8, 1, 5, 6, 12)),
            ("2022-8-1", datetime(2022, 8, 1)),
            ("2022-8-1 5:16:12", datetime(2022, 8, 1, 5, 16, 12)),
            ("2022-8-1T5:16:12Z", datetime(2022, 8, 1, 5, 16, 12, tzinfo=pytz.utc)),
            (
                "2022-8-1T5:16:12+02:30",
                pytz.FixedOffset(150).localize(datetime(2022, 8, 1, 5, 16, 12)),
            ),
            (
                "2022-8-1T5:16:12-05:30",
                pytz.FixedOffset(-330).localize(datetime(2022, 8, 1, 5, 16, 12)),
            ),
            (
                pytz.FixedOffset(-60).localize(datetime(2022, 8, 1)),
                pytz.FixedOffset(-60).localize(datetime(2022, 8, 1)),
            ),
        ],
        ids=[
            "None",
            "date",
            "datetime",
            "date as text",
            "datetime as text",
            "utc",
            "tzoffset",
            "negtzoffset",
            "existing tzinfo",
        ],
    )
    def test_date(self, timezone, input, expected):
        returned = to_datetime(input, timezone, None)
        if expected is not None:
            assert isinstance(returned, datetime)
            expected = timezone.localize(expected) if not expected.tzinfo else expected

        assert returned == expected

    def test_invalid_input_type(self, timezone):
        exc = pytest.raises(AsynczException, to_datetime, 92123, timezone, "foo")
        assert str(exc.value) == "Unsupported type for foo: int."

    def test_invalid_input_value(self, timezone):
        exc = pytest.raises(AsynczException, to_datetime, "19700-12-1", timezone, None)
        assert str(exc.value) == "Invalid date string."

    def test_missing_timezone(self):
        exc = pytest.raises(AsynczException, to_datetime, "2022-8-1", None, "argname")
        assert str(exc.value) == (
            'The "tz" argument must be specified if argname has no timezone information'
        )

    def test_text_timezone(self):
        returned = to_datetime("2022-08-01", "UTC", None)
        assert returned == datetime(2022, 8, 1, tzinfo=pytz.utc)


def test_datetime_to_utc_timestamp(timezone):
    dt = timezone.localize(datetime(2022, 3, 12, 5, 40, 13, 254012))
    timestamp = datetime_to_utc_timestamp(dt)
    dt2 = utc_timestamp_to_datetime(timestamp)
    assert dt2 == dt


def test_timedelta_seconds():
    delta = timedelta(minutes=2, seconds=30)
    seconds = timedelta_seconds(delta)
    assert seconds == 150


@pytest.mark.parametrize(
    "input,expected",
    [
        (datetime(2022, 4, 7, 2, 10, 16, 4000), datetime(2022, 4, 7, 2, 10, 17)),
        (datetime(2022, 4, 7, 2, 10, 16), datetime(2022, 4, 7, 2, 10, 16)),
    ],
    ids=["milliseconds", "exact"],
)
def test_datetime_ceil(input, expected):
    assert datetime_ceil(input) == expected


@pytest.mark.parametrize(
    "input,expected",
    [
        (None, "None"),
        (
            pytz.timezone("Europe/London").localize(datetime(2022, 5, 30, 7, 12, 20)),
            "2022-05-30 07:12:20 BST",
        ),
    ],
    ids=["None", "datetime+tzinfo"],
)
def test_datetime_repr(input, expected):
    assert datetime_repr(input) == expected


class TestGetCallableName:
    @pytest.mark.parametrize(
        "input,expected",
        [
            (to_int, "to_int"),
            (
                DummyClass.staticmeth,
                "DummyClass.staticmeth" if hasattr(DummyClass, "__qualname__") else "staticmeth",
            ),
            (DummyClass.classmeth, "DummyClass.classmeth"),
            (DummyClass.meth, "meth" if sys.version_info[:2] == (3, 2) else "DummyClass.meth"),
            (DummyClass().meth, "DummyClass.meth"),
            (DummyClass, "DummyClass"),
            (DummyClass(), "DummyClass"),
        ],
        ids=[
            "function",
            "static method",
            "class method",
            "unbounded method",
            "bounded method",
            "class",
            "instance",
        ],
    )
    def test_inputs(self, input, expected):
        assert get_callable_name(input) == expected

    def test_bad_input(self):
        pytest.raises(TypeError, get_callable_name, object())


class TestObjToRef:
    @pytest.mark.parametrize(
        "obj, error",
        [
            (partial(DummyClass.meth), "Cannot create a reference to a partial()"),
            (lambda: None, "Cannot create a reference to a lambda"),
        ],
        ids=["partial", "lambda"],
    )
    def test_errors(self, obj, error):
        exc = pytest.raises(ValueError, obj_to_ref, obj)
        assert str(exc.value) == error

    @pytest.mark.skipif(
        sys.version_info[:2] < (3, 3), reason="Requires __qualname__ (Python 3.3+)"
    )
    def test_nested_function_error(self):
        def nested():
            pass

        exc = pytest.raises(ValueError, obj_to_ref, nested)
        assert str(exc.value) == "Cannot create a reference to a nested function"

    @pytest.mark.parametrize(
        "input,expected",
        [
            (DummyClass.meth, "tests.test_utils:DummyClass.meth"),
            (DummyClass.classmeth, "tests.test_utils:DummyClass.classmeth"),
            pytest.param(
                DummyClass.InnerDummyClass.innerclassmeth,
                "tests.test_utils:DummyClass.InnerDummyClass.innerclassmeth",
                marks=[
                    pytest.mark.skipif(
                        sys.version_info < (3, 3), reason="Requires __qualname__ (Python 3.3+)"
                    )
                ],
            ),
            pytest.param(
                DummyClass.staticmeth,
                "tests.test_utils:DummyClass.staticmeth",
                marks=[
                    pytest.mark.skipif(
                        sys.version_info < (3, 3), reason="Requires __qualname__ (Python 3.3+)"
                    )
                ],
            ),
            (timedelta, "datetime:timedelta"),
        ],
        ids=[
            "class method",
            "inner class method",
            "static method",
            "inherited class method",
            "timedelta",
        ],
    )
    def test_valid_refs(self, input, expected):
        assert obj_to_ref(input) == expected


class TestRefToObj:
    def test_valid_ref(self):
        from logging.handlers import RotatingFileHandler

        assert ref_to_obj("logging.handlers:RotatingFileHandler") is RotatingFileHandler

    def test_complex_path(self):
        pkg1 = ModuleType("pkg1")
        pkg1.pkg2 = "blah"
        pkg2 = ModuleType("pkg1.pkg2")
        pkg2.varname = "test"
        sys.modules["pkg1"] = pkg1
        sys.modules["pkg1.pkg2"] = pkg2
        assert ref_to_obj("pkg1.pkg2:varname") == "test"

    @pytest.mark.parametrize(
        "input,error",
        [(object(), TypeError), ("module", AsynczException), ("module:blah", LookupError)],
        ids=["raw object", "module", "module attribute"],
    )
    def test_lookup_error(self, input, error):
        pytest.raises(error, ref_to_obj, input)


@pytest.mark.parametrize(
    "input,expected",
    [("datetime:timedelta", timedelta), (timedelta, timedelta)],
    ids=["textref", "direct"],
)
def test_maybe_ref(input, expected):
    assert maybe_ref(input) == expected


@pytest.mark.parametrize(
    "input,expected",
    [(b"T\xc3\xa9ste".decode("utf-8"), "Téste"), (1, 1)],
    ids=["string", "int"],
)
def test_repr_escape_py2(input, expected):
    assert repr_escape(input) == expected


class TestCheckCallableArgs:
    def test_invalid_callable_args(self):
        """
        Tests that attempting to create a task with an invalid number of arguments raises an
        exception.

        """
        exc = pytest.raises(ValueError, check_callable_args, lambda x: None, [1, 2], {})
        assert str(exc.value) == (
            "The list of positional arguments is longer than the target callable can handle "
            "(allowed: 1, given in args: 2)"
        )

    def test_invalid_callable_kwargs(self):
        """
        Tests that attempting to schedule a task with unmatched keyword arguments raises an
        exception.

        """
        exc = pytest.raises(ValueError, check_callable_args, lambda x: None, [], {"x": 0, "y": 1})
        assert str(exc.value) == (
            "The target callable does not accept the following keyword " "arguments: y"
        )

    def test_missing_callable_args(self):
        """Tests that attempting to schedule a task with missing arguments raises an exception."""
        exc = pytest.raises(ValueError, check_callable_args, lambda x, y, z: None, [1], {"y": 0})
        assert str(exc.value) == "The following arguments have not been supplied: z"

    def test_default_args(self):
        """Tests that default values for arguments are properly taken into account."""
        exc = pytest.raises(ValueError, check_callable_args, lambda x, y, z=1: None, [1], {})
        assert str(exc.value) == "The following arguments have not been supplied: y"

    def test_conflicting_callable_args(self):
        """
        Tests that attempting to schedule a task where the combination of args and kwargs are in
        conflict raises an exception.

        """
        exc = pytest.raises(ValueError, check_callable_args, lambda x, y: None, [1, 2], {"y": 1})
        assert str(exc.value) == "The following arguments are supplied in both args and kwargs: y"

    def test_signature_positional_only(self):
        """Tests that a function where signature() fails is accepted."""
        check_callable_args(object().__setattr__, ("blah", 1), {})

    @pytest.mark.skipif(
        platform.python_implementation() == "PyPy",
        reason="PyPy does not expose signatures of builtins",
    )
    def test_positional_only_args(self):
        """
        Tests that an attempt to use keyword arguments for positional-only arguments raises an
        exception.

        """
        exc = pytest.raises(
            ValueError, check_callable_args, object.__setattr__, ["blah"], {"value": 1}
        )
        assert str(exc.value) == (
            "The following arguments cannot be given as keyword arguments: " "value"
        )

    def test_unfulfilled_kwargs(self):
        """
        Tests that attempting to schedule a task where not all keyword-only arguments are fulfilled
        raises an exception.

        """
        func = eval("lambda x, *, y, z=1: None")
        exc = pytest.raises(ValueError, check_callable_args, func, [1], {})
        assert str(exc.value) == (
            "The following keyword-only arguments have not been supplied in " "kwargs: y"
        )

    def test_wrapped_func(self):
        """
        Test that a wrapped function can be scheduled even if it cannot accept the arguments given
        in add_task() if the wrapper can.
        """

        def func():
            pass

        @wraps(func)
        def wrapper(arg):
            func()

        check_callable_args(wrapper, (1,), {})
