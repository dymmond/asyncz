import gc
import time
from asyncio import CancelledError
from collections import defaultdict
from datetime import datetime
from threading import Event
from unittest.mock import MagicMock, Mock, patch

import pytest
import pytz
from loguru import logger

from asyncz.events.constants import TASK_ERROR, TASK_EXECUTED, TASK_MISSED
from asyncz.exceptions import MaximumInstancesError
from asyncz.executors.asyncio import AsyncIOExecutor
from asyncz.executors.base import run_coroutine_task, run_task
from asyncz.schedulers.asyncio import AsyncIOScheduler
from asyncz.schedulers.base import BaseScheduler, LoguruLogging
from asyncz.tasks import Task


@pytest.fixture
def scheduler_mocked(timezone):
    scheduler_ = Mock(BaseScheduler, timezone=timezone)
    scheduler_.instances = defaultdict(lambda: 0)
    scheduler_.create_lock = MagicMock()
    scheduler_.loggers = LoguruLogging()
    return scheduler_


@pytest.fixture(params=["threadpool", "other"])
def executor(request, scheduler_mocked):
    if request.param == "threadpool":
        from asyncz.executors.pool import ThreadPoolExecutor

        executor = ThreadPoolExecutor()
    else:
        from asyncz.executors.process_pool import ProcessPoolExecutor

        executor = ProcessPoolExecutor()

    executor.start(scheduler_mocked, "dummy")
    yield executor
    executor.shutdown()


def wait_event():
    time.sleep(0.2)
    return "test"


def failure():
    raise Exception("test failure")


def success():
    return 5


def test_max_instances(scheduler_mocked, executor, create_task, freeze_time):
    events = []
    scheduler_mocked.dispatch_event = lambda event: events.append(event)
    task = create_task(fn=wait_event, max_instances=2, next_run_time=None)
    executor.send_task(task, [freeze_time.current])
    executor.send_task(task, [freeze_time.current])

    pytest.raises(MaximumInstancesError, executor.send_task, task, [freeze_time.current])
    executor.shutdown()
    assert len(events) == 2
    assert events[0].return_value == "test"
    assert events[1].return_value == "test"


@pytest.mark.parametrize(
    "event_code,fn",
    [(TASK_EXECUTED, success), (TASK_MISSED, failure), (TASK_ERROR, failure)],
    ids=["executed", "missed", "error"],
)
def test_send_task(scheduler_mocked, executor, create_task, freeze_time, timezone, event_code, fn):
    scheduler_mocked.dispatch_event = MagicMock()
    task = create_task(fn=fn, id="foo")
    task.store_alias = "test_store"
    run_time = (
        timezone.localize(datetime(1970, 1, 1))
        if event_code == TASK_MISSED
        else freeze_time.current
    )
    executor.send_task(task, [run_time])
    executor.shutdown()

    assert scheduler_mocked.dispatch_event.call_count == 1
    event = scheduler_mocked.dispatch_event.call_args[0][0]
    assert event.code == event_code
    assert event.task_id == "foo"
    assert event.store == "test_store"

    if event_code == TASK_EXECUTED:
        assert event.return_value == 5
    elif event_code == TASK_ERROR:
        assert str(event.exception) == "test failure"
        assert isinstance(event.traceback, str)


class FakeTask:
    id = "abc"
    max_instances = 1
    store_alias = "foo"


def dummy_run_task(task, store_alias, run_times, logger_name):
    raise Exception("dummy")


def test_run_task_error(monkeypatch, executor):
    """
    Tests that run_task_error is properly called. Since we use loguru, there is no need to parse the exceptions.
    """

    def run_task_error(task_id, exc, traceback):
        assert task_id == "abc"
        exc_traceback[:] = [exc, traceback]
        event.set()

    event = Event()
    exc_traceback = [None, None]
    monkeypatch.setattr("asyncz.executors.base.run_task", dummy_run_task)
    monkeypatch.setattr("asyncz.executors.pool.run_task", dummy_run_task)
    monkeypatch.setattr(executor, "run_task_error", run_task_error)
    executor.send_task(FakeTask(), [])

    event.wait(5)
    assert exc_traceback[0] is None
    assert exc_traceback[1] is None


def test_run_task_memory_leak():
    class FooBar:
        pass

    def fn():
        foo = FooBar()  # noqa: F841
        raise Exception("dummy")

    fake_task = Mock(Task, id="dummy", fn=fn, args=(), kwargs={}, mistrigger_grace_time=1)
    with patch("loguru.logger"):
        for _ in range(5):
            run_task(fake_task, "foo", [datetime.now(pytz.UTC)], logger)

    foos = [x for x in gc.get_objects() if type(x) is FooBar]
    assert len(foos) == 0


@pytest.fixture
def asyncio_scheduler(event_loop):
    scheduler = AsyncIOScheduler(event_loop=event_loop)
    scheduler.start(paused=True)
    yield scheduler
    scheduler.shutdown(False)


@pytest.fixture
def asyncio_executor(asyncio_scheduler):
    executor = AsyncIOExecutor()
    executor.start(asyncio_scheduler, "default")
    yield executor
    executor.shutdown()


async def waiter(sleep, exception):
    await sleep(0.1)
    if exception:
        raise Exception("dummy error")
    else:
        return True


def test_asyncio_executor_shutdown(event_loop, asyncio_scheduler, asyncio_executor):
    """Test that the AsyncIO executor cancels its pending tasks on shutdown."""
    from asyncio import sleep

    task = asyncio_scheduler.add_task(waiter, "interval", seconds=1, args=[sleep, None])
    asyncio_executor.send_task(task, [datetime.now(pytz.utc)])
    futures = asyncio_executor.pending_futures.copy()
    assert len(futures) == 1

    asyncio_executor.shutdown()
    with pytest.raises(CancelledError):
        event_loop.run_until_complete(futures.pop())


@pytest.mark.asyncio
async def test_run_task_memory_leak_two():
    class FooBar:
        pass

    async def fn():
        foo = FooBar()  # noqa: F841
        raise Exception("dummy")

    fake_task = Mock(Task, id="dummy", fn=fn, args=(), kwargs={}, mistrigger_grace_time=1)
    with patch("loguru.logger"):
        for _ in range(5):
            await run_coroutine_task(fake_task, "foo", [datetime.now(pytz.utc)], logger)

    foos = [x for x in gc.get_objects() if type(x) is FooBar]
    assert len(foos) == 0
