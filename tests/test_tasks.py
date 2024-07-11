import gc
import weakref
from datetime import datetime, timedelta
from functools import partial
from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError

from asyncz.datastructures import TaskState
from asyncz.exceptions import AsynczException
from asyncz.schedulers.base import BaseScheduler
from asyncz.tasks import Task
from asyncz.triggers import DateTrigger


def dummyfn(): ...


@pytest.fixture
def task(create_task):
    return create_task(fn=dummyfn)


@pytest.mark.parametrize("task_id", ["testid", None])
def test_constructor(task_id):
    scheduler_mock = MagicMock(BaseScheduler)
    task = Task(scheduler_mock, id=task_id)
    assert task.scheduler is scheduler_mock
    assert task.store_alias is None

    if task_id is None:
        assert len(task.id) == 32
    else:
        assert task.id == task_id


def test_update(task):
    task.update(bah=1, foo="x")
    task.scheduler.update_task.assert_called_once_with(task.id, None, bah=1, foo="x")


def test_reschedule(task):
    task.reschedule("trigger", bah=1, foo="x")
    task.scheduler.reschedule_task.assert_called_once_with(
        task.id, None, "trigger", bah=1, foo="x"
    )


def test_pause(task):
    task.pause()
    task.scheduler.pause_task.assert_called_once_with(task.id, None)


def test_resume(task):
    task.resume()
    task.scheduler.resume_task.assert_called_once_with(task.id, None)


def test_remove(task):
    task.delete()
    task.scheduler.delete_task.assert_called_once_with(task.id, None)


def test_weakref(create_task):
    task = create_task(fn=dummyfn)
    ref = weakref.ref(task)
    del task
    gc.collect()
    assert ref() is None


def test_pending(task):
    assert task.pending

    task.store_alias = "test"
    assert not task.pending


def test_get_run_times(create_task, timezone):
    run_time = timezone.localize(datetime(2023, 12, 13, 0, 8))
    expected_times = [run_time + timedelta(seconds=1), run_time + timedelta(seconds=2)]
    task = create_task(
        trigger="interval",
        trigger_args={"seconds": 1, "timezone": timezone, "start_at": run_time},
        next_run_time=expected_times[0],
        fn=dummyfn,
    )

    run_times = task.get_run_times(run_time)
    assert run_times == []

    run_times = task.get_run_times(expected_times[0])
    assert run_times == [expected_times[0]]

    run_times = task.get_run_times(expected_times[1])
    assert run_times == expected_times


def test_create_bad_id(create_task):
    exc = pytest.raises(ValidationError, create_task, id=3)
    assert exc.value.errors()[0]["type"] == "string_type"


def test_private_update_id(task):
    exc = pytest.raises(ValueError, task._update, id="alternate")
    assert str(exc.value) == "The task ID may not be changed."


def test_private_update_bad_fn(task):
    exc = pytest.raises(TypeError, task._update, fn=1)
    assert str(exc.value) == "fn must be a callable or a textual reference to a callable."


def test_private_update_func_ref(task):
    task._update(fn="tests.test_tasks:dummyfn")
    assert task.fn is dummyfn
    assert task.fn_reference == "tests.test_tasks:dummyfn"


def test_private_update_unreachable_fn(task):
    fn = partial(dummyfn)
    task._update(fn=fn)
    assert task.fn is fn
    assert task.fn_reference is None


def test_private_update_name(task):
    del task.name
    task._update(fn=dummyfn)
    assert task.name == "dummyfn"


def test_private_update_bad_args(task):
    exc = pytest.raises(TypeError, task._update, args=1)
    assert str(exc.value) == "args must be a non-string iterable."


def test_private_update_bad_kwargs(task):
    exc = pytest.raises(TypeError, task._update, kwargs=1)
    assert str(exc.value) == "kwargs must be a dict-like object."


@pytest.mark.parametrize("value", [1, ""], ids=["integer", "empty string"])
def test_private_update_bad_name(task, value):
    exc = pytest.raises(TypeError, task._update, name=value)
    assert str(exc.value) == "name must be a non empty string."


@pytest.mark.parametrize("value", ["foo", 0, -1], ids=["string", "zero", "negative"])
def test_private_update_bad_misfire_grace_time(task, value):
    exc = pytest.raises(TypeError, task._update, mistrigger_grace_time=value)
    assert str(exc.value) == "mistrigger_grace_time must be either None or a positive integer."


@pytest.mark.parametrize("value", [None, "foo", 0, -1], ids=["None", "string", "zero", "negative"])
def test_private_update_bad_max_instances(task, value):
    exc = pytest.raises(TypeError, task._update, max_instances=value)
    assert str(exc.value) == "max_instances must be a positive integer."


def test_private_update_bad_trigger(task):
    exc = pytest.raises(TypeError, task._update, trigger="foo")
    assert str(exc.value) == "Expected a trigger instance, got str instead."


def test_private_update_bad_executor(task):
    exc = pytest.raises(TypeError, task._update, executor=1)
    assert str(exc.value) == "executor must be a string."


def test_private_update_bad_next_run_time(task):
    exc = pytest.raises(AsynczException, task._update, next_run_time=1)
    assert str(exc.value) == "Unsupported type for next_run_time: int."


def test_private_update_bad_argument(task):
    exc = pytest.raises(AttributeError, task._update, scheduler=1)
    assert str(exc.value) == "The following are not modifiable attributes of Task: scheduler."


def test_getstate(task):
    state = task.__getstate__()

    assert state.id == b"t\xc3\xa9st\xc3\xafd".decode("utf-8")
    assert state.name == b"n\xc3\xa4m\xc3\xa9".decode("utf-8")
    assert state.fn == "tests.test_tasks:dummyfn"
    assert state.args == ()
    assert state.coalesce is False
    assert state.trigger == task.trigger
    assert state.executor == "default"
    assert state.mistrigger_grace_time == 1
    assert state.max_instances == 1
    assert state.next_run_time is None
    assert state.kwargs == {}


def test_setstate(task, timezone):
    trigger = DateTrigger("2022-12-14 13:05:00", timezone)
    state = TaskState(
        scheduler=MagicMock(),
        store=MagicMock(),
        trigger=trigger,
        name="testtask.dummyfn",
        executor="dummyexecutor",
        fn="tests.test_tasks:dummyfn",
        fn_reference="tests.test_tasks:dummyfn",
        args=[],
        kwargs={},
        id="other_id",
        mistrigger_grace_time=2,
        coalesce=True,
        max_instances=2,
        next_run_time=None,
    )

    task.__setstate__(state)
    assert task.id == "other_id"
    assert task.fn == dummyfn
    assert task.fn_reference == "tests.test_tasks:dummyfn"
    assert task.trigger == trigger
    assert task.executor == "dummyexecutor"
    assert task.args == []
    assert task.kwargs == {}
    assert task.name == "testtask.dummyfn"
    assert task.mistrigger_grace_time == 2
    assert task.coalesce is True
    assert task.max_instances == 2
    assert task.next_run_time is None


def test_eq(create_task):
    task = create_task(fn=lambda: None, id="foo")
    task2 = create_task(fn=lambda: None, id="foo")
    task3 = create_task(fn=lambda: None, id="bar")
    assert task == task2
    assert task != task3
    assert task != "foo"


def test_repr(task):
    assert repr(task) == b"<Task (id=t\xc3\xa9st\xc3\xafd name=n\xc3\xa4m\xc3\xa9)>".decode(
        "utf-8"
    )


@pytest.mark.parametrize(
    "status, expected_status",
    [
        ("scheduled", "next run at: 2022-11-03 18:40:00 GMT"),
        ("paused", "paused"),
        ("pending", "pending"),
    ],
    ids=["scheduled", "paused", "pending"],
)
@pytest.mark.parametrize("unicode", [False, True], ids=["nativestr", "unicode"])
def test_str(create_task, status, unicode, expected_status):
    task = create_task(fn=dummyfn)
    if status == "scheduled":
        task.next_run_time = task.trigger.run_at
    elif status == "pending":
        del task.next_run_time

    expected = (
        b"n\xc3\xa4m\xc3\xa9 (trigger: date[2022-11-03 18:40:00 GMT], %s)".decode("utf-8")
        % expected_status
    )

    result = task.__str__()
    assert result == expected
