import gc
import weakref
from datetime import datetime, timedelta
from functools import partial

import pytest
from asyncz.datastructures import JobState
from asyncz.exceptions import AsynczException
from asyncz.jobs import Job
from asyncz.schedulers.base import BaseScheduler
from asyncz.triggers import DateTrigger
from mock import MagicMock, patch


def dummyfn():
    ...


@pytest.fixture
def job(create_job):
    return create_job(fn=dummyfn)


@pytest.mark.parametrize("job_id", ["testid", None])
def test_constructor(job_id):
    with patch("asyncz.jobs.base.Job._update") as _update:
        scheduler_mock = MagicMock(BaseScheduler)
        job = Job(scheduler_mock, id=job_id)
        assert job.scheduler is scheduler_mock
        assert job.store_alias is None

        update_kwargs = _update.call_args[1]
        if job_id is None:
            assert len(update_kwargs["id"]) == 32
        else:
            assert update_kwargs["id"] == job_id


def test_update(job):
    job.update(bah=1, foo="x")
    job.scheduler.update_job.assert_called_once_with(job.id, None, bah=1, foo="x")


def test_reschedule(job):
    job.reschedule("trigger", bah=1, foo="x")
    job.scheduler.reschedule_job.assert_called_once_with(job.id, None, "trigger", bah=1, foo="x")


def test_pause(job):
    job.pause()
    job.scheduler.pause_job.assert_called_once_with(job.id, None)


def test_resume(job):
    job.resume()
    job.scheduler.resume_job.assert_called_once_with(job.id, None)


def test_remove(job):
    job.delete()
    job.scheduler.remove_job.assert_called_once_with(job.id, None)


def test_weakref(create_job):
    job = create_job(fn=dummyfn)
    ref = weakref.ref(job)
    del job
    gc.collect()
    assert ref() is None


def test_pending(job):
    assert job.pending

    job.store_alias = "test"
    assert not job.pending


def test_get_run_times(create_job, timezone):
    run_time = timezone.localize(datetime(2023, 12, 13, 0, 8))
    expected_times = [run_time + timedelta(seconds=1), run_time + timedelta(seconds=2)]
    job = create_job(
        trigger="interval",
        trigger_args={"seconds": 1, "timezone": timezone, "start_date": run_time},
        next_run_time=expected_times[0],
        fn=dummyfn,
    )

    run_times = job.get_run_times(run_time)
    assert run_times == []

    run_times = job.get_run_times(expected_times[0])
    assert run_times == [expected_times[0]]

    run_times = job.get_run_times(expected_times[1])
    assert run_times == expected_times


def test_private_update_bad_id(job):
    del job.id
    exc = pytest.raises(TypeError, job._update, id=3)
    assert str(exc.value) == "Id must be a non empty string."


def test_private_update_id(job):
    exc = pytest.raises(ValueError, job._update, id="alternate")
    assert str(exc.value) == "The job ID may not be changed."


def test_private_update_bad_fn(job):
    exc = pytest.raises(TypeError, job._update, fn=1)
    assert str(exc.value) == "fn must be a callable or a textual reference to a callable."


def test_private_update_func_ref(job):
    job._update(fn="tests.test_jobs:dummyfn")
    assert job.fn is dummyfn
    assert job.fn_reference == "tests.test_jobs:dummyfn"


def test_private_update_unreachable_fn(job):
    fn = partial(dummyfn)
    job._update(fn=fn)
    assert job.fn is fn
    assert job.fn_reference is None


def test_private_update_name(job):
    del job.name
    job._update(fn=dummyfn)
    assert job.name == "dummyfn"


def test_private_update_bad_args(job):
    exc = pytest.raises(TypeError, job._update, args=1)
    assert str(exc.value) == "args must be a non-string iterable."


def test_private_update_bad_kwargs(job):
    exc = pytest.raises(TypeError, job._update, kwargs=1)
    assert str(exc.value) == "kwargs must be a dict-like object."


@pytest.mark.parametrize("value", [1, ""], ids=["integer", "empty string"])
def test_private_update_bad_name(job, value):
    exc = pytest.raises(TypeError, job._update, name=value)
    assert str(exc.value) == "name must be a non empty string."


@pytest.mark.parametrize("value", ["foo", 0, -1], ids=["string", "zero", "negative"])
def test_private_update_bad_misfire_grace_time(job, value):
    exc = pytest.raises(TypeError, job._update, mistrigger_grace_time=value)
    assert str(exc.value) == "mistrigger_grace_time must be either None or a positive integer."


@pytest.mark.parametrize("value", [None, "foo", 0, -1], ids=["None", "string", "zero", "negative"])
def test_private_update_bad_max_instances(job, value):
    exc = pytest.raises(TypeError, job._update, max_instances=value)
    assert str(exc.value) == "max_instances must be a positive integer."


def test_private_update_bad_trigger(job):
    exc = pytest.raises(TypeError, job._update, trigger="foo")
    assert str(exc.value) == "Expected a trigger instance, got str instead."


def test_private_update_bad_executor(job):
    exc = pytest.raises(TypeError, job._update, executor=1)
    assert str(exc.value) == "executor must be a string."


def test_private_update_bad_next_run_time(job):
    exc = pytest.raises(AsynczException, job._update, next_run_time=1)
    assert str(exc.value) == "Unsupported type for next_run_time: int."


def test_private_update_bad_argument(job):
    exc = pytest.raises(AttributeError, job._update, scheduler=1)
    assert str(exc.value) == "The following are not modifiable attributes of Job: scheduler."


def test_getstate(job):
    state = job.__getstate__()

    assert state.id == b"t\xc3\xa9st\xc3\xafd".decode("utf-8")
    assert state.name == b"n\xc3\xa4m\xc3\xa9".decode("utf-8")
    assert state.fn == "tests.test_jobs:dummyfn"
    assert state.args == ()
    assert state.coalesce == False
    assert state.trigger == job.trigger
    assert state.executor == "default"
    assert state.mistrigger_grace_time == 1
    assert state.max_instances == 1
    assert state.next_run_time == None
    assert state.kwargs == {}


def test_setstate(job, timezone):
    trigger = DateTrigger("2022-12-14 13:05:00", timezone)
    state = JobState(
        scheduler=MagicMock(),
        store=MagicMock(),
        trigger=trigger,
        name="testjob.dummyfn",
        executor="dummyexecutor",
        fn="tests.test_jobs:dummyfn",
        fn_reference="tests.test_jobs:dummyfn",
        args=[],
        kwargs={},
        id="other_id",
        mistrigger_grace_time=2,
        coalesce=True,
        max_instances=2,
        next_run_time=None,
    )

    job.__setstate__(state)
    assert job.id == "other_id"
    assert job.fn == dummyfn
    assert job.fn_reference == "tests.test_jobs:dummyfn"
    assert job.trigger == trigger
    assert job.executor == "dummyexecutor"
    assert job.args == []
    assert job.kwargs == {}
    assert job.name == "testjob.dummyfn"
    assert job.mistrigger_grace_time == 2
    assert job.coalesce is True
    assert job.max_instances == 2
    assert job.next_run_time is None


def test_eq(create_job):
    job = create_job(fn=lambda: None, id="foo")
    job2 = create_job(fn=lambda: None, id="foo")
    job3 = create_job(fn=lambda: None, id="bar")
    assert job == job2
    assert not job == job3
    assert not job == "foo"


def test_repr(job):
    assert repr(job) == b"<Job (id=t\xc3\xa9st\xc3\xafd name=n\xc3\xa4m\xc3\xa9)>".decode("utf-8")


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
def test_str(create_job, status, unicode, expected_status):
    job = create_job(fn=dummyfn)
    if status == "scheduled":
        job.next_run_time = job.trigger.run_at
    elif status == "pending":
        del job.next_run_time

    expected = (
        b"n\xc3\xa4m\xc3\xa9 (trigger: date[2022-11-03 18:40:00 GMT], %s)".decode("utf-8")
        % expected_status
    )

    result = job.__str__()
    assert result == expected
