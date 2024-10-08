import asyncio
import logging
import pickle
import time
from datetime import datetime, timedelta, tzinfo
from threading import Thread
from typing import Any, List, Optional, Union
from unittest.mock import MagicMock, patch

import pytest

from asyncz.enums import SchedulerState
from asyncz.events.base import SchedulerEvent
from asyncz.events.constants import (
    ALL_EVENTS,
    ALL_TASKS_REMOVED,
    EXECUTOR_ADDED,
    EXECUTOR_REMOVED,
    SCHEDULER_PAUSED,
    SCHEDULER_RESUMED,
    SCHEDULER_SHUTDOWN,
    SCHEDULER_STARTED,
    STORE_ADDED,
    STORE_REMOVED,
    TASK_ADDED,
    TASK_EXECUTED,
    TASK_MAX_INSTANCES,
    TASK_MODIFIED,
    TASK_REMOVED,
    TASK_SUBMITTED,
)
from asyncz.exceptions import (
    ConflictIdError,
    MaximumInstancesError,
    SchedulerAlreadyRunningError,
    SchedulerNotRunningError,
    TaskLookupError,
)
from asyncz.executors.base import BaseExecutor
from asyncz.executors.debug import DebugExecutor
from asyncz.schedulers.asyncio import AsyncIOScheduler, NativeAsyncIOScheduler
from asyncz.schedulers.base import BaseScheduler, ClassicLogging
from asyncz.stores.base import BaseStore
from asyncz.stores.memory import MemoryStore
from asyncz.tasks import Task
from asyncz.tasks.types import TaskType
from asyncz.triggers.base import BaseTrigger
from asyncz.utils import make_async_function, make_function

try:
    from zoneinfo import ZoneInfo
except ImportError:
    from backports.zoneinfo import ZoneInfo

object_setter = object.__setattr__


class DummyScheduler(BaseScheduler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        object_setter(self, "wakeup", MagicMock())

    def shutdown(self, wait=True):
        return super().shutdown(wait)

    def wakeup(self): ...


class DummyTrigger(BaseTrigger):
    def __init__(self, **args):
        super().__init__(**args)
        self.args = args

    def get_next_trigger_time(
        self, timezone: tzinfo, previous_time: datetime, now: Optional[datetime] = None
    ) -> Union[datetime, None]: ...


class DummyExecutor(BaseExecutor):
    def __init__(self, **args):
        super().__init__(**args)
        self.args = args
        object_setter(self, "start", MagicMock())
        object_setter(self, "shutdown", MagicMock())
        object_setter(self, "send_task", MagicMock())

    def do_send_task(self, task: "TaskType", run_times: List[datetime]) -> Any:
        return super().do_send_task(task, run_times)


class DummyStore(BaseStore):
    def __init__(self, **args):
        super().__init__(**args)
        self.args = args
        object_setter(self, "start", MagicMock())
        object_setter(self, "shutdown", MagicMock())

    def get_due_tasks(self, now: datetime) -> List["TaskType"]:
        return []

    def lookup_task(self, task_id: str) -> Union["TaskType", None]:
        return None

    def delete_task(self, task_id: str): ...

    def remove_all_tasks(self): ...

    def get_next_run_time(self) -> Optional[datetime]:
        return None

    def get_all_tasks(self) -> List["TaskType"]:
        return []

    def add_task(self, task: "TaskType"): ...

    def update_task(self, task: "TaskType"): ...


class TestBaseScheduler:
    @pytest.fixture
    def scheduler(self, timezone):
        return DummyScheduler()

    @pytest.fixture
    def scheduler_events(self, request, scheduler):
        events = []
        mask = getattr(request, "param", ALL_EVENTS ^ SCHEDULER_STARTED)
        scheduler.add_listener(events.append, mask)
        return events

    def test_constructor(self):
        with patch(f"{__name__}.DummyScheduler.setup") as setup:
            global_config = {"asyncz.foo": "bar", "asyncz.x": "y"}
            options = {"bar": "baz", "xyz": 123}
            DummyScheduler(global_config, **options)

        setup.assert_called_once_with(global_config, **options)

    @pytest.mark.parametrize(
        "global_config",
        [
            {
                "asyncz.timezone": "UTC",
                "asyncz.task_defaults.mistrigger_grace_time": "5",
                "asyncz.task_defaults.coalesce": "false",
                "asyncz.task_defaults.max_instances": "9",
                "asyncz.executors.default.class": f"{__name__}:DummyExecutor",
                "asyncz.executors.default.arg1": "3",
                "asyncz.executors.default.arg2": "a",
                "asyncz.executors.alter.class": f"{__name__}:DummyExecutor",
                "asyncz.executors.alter.arg": "true",
                "asyncz.stores.default.class": f"{__name__}:DummyStore",
                "asyncz.stores.default.arg1": "3",
                "asyncz.stores.default.arg2": "a",
                "asyncz.stores.bar.class": f"{__name__}:DummyStore",
                "asyncz.stores.bar.arg": "false",
            },
            {
                "asyncz.timezone": "UTC",
                "asyncz.task_defaults": {
                    "mistrigger_grace_time": "5",
                    "coalesce": "false",
                    "max_instances": "9",
                },
                "asyncz.executors": {
                    "default": {
                        "class": f"{__name__}:DummyExecutor",
                        "arg1": "3",
                        "arg2": "a",
                    },
                    "alter": {"class": f"{__name__}:DummyExecutor", "arg": "true"},
                },
                "asyncz.stores": {
                    "default": {
                        "class": f"{__name__}:DummyStore",
                        "arg1": "3",
                        "arg2": "a",
                    },
                    "bar": {"class": f"{__name__}:DummyStore", "arg": "false"},
                },
            },
        ],
        ids=["ini-style", "yaml-style"],
    )
    def test_configure(self, scheduler, global_config):
        scheduler._setup = MagicMock()
        scheduler.setup(global_config, timezone="Other timezone")

        scheduler._setup.assert_called_once_with(
            {
                "timezone": "Other timezone",
                "task_defaults": {
                    "mistrigger_grace_time": "5",
                    "coalesce": "false",
                    "max_instances": "9",
                },
                "executors": {
                    "default": {
                        "class": f"{__name__}:DummyExecutor",
                        "arg1": "3",
                        "arg2": "a",
                    },
                    "alter": {"class": f"{__name__}:DummyExecutor", "arg": "true"},
                },
                "stores": {
                    "default": {
                        "class": f"{__name__}:DummyStore",
                        "arg1": "3",
                        "arg2": "a",
                    },
                    "bar": {"class": f"{__name__}:DummyStore", "arg": "false"},
                },
            }
        )

    def test_scheduler_change_logger_direct_class(self):
        """
        Test scheduler is picking up the right loggers class
        """
        scheduler = DummyScheduler(loggers_class=ClassicLogging)
        scheduler.start(paused=True)
        assert isinstance(scheduler.loggers, ClassicLogging)
        assert scheduler.logger_name == "asyncz.schedulers"

    def test_scheduler_change_logger_class_path(self):
        """
        Test scheduler is picking up the right loggers class
        """
        scheduler = DummyScheduler(loggers_class="asyncz.schedulers.base:ClassicLogging")
        scheduler.start(paused=True)
        assert isinstance(scheduler.loggers, ClassicLogging)
        assert scheduler.logger_name == "asyncz.schedulers"

    def test_scheduler_change_logger_config(self):
        """
        Test scheduler is picking up the right loggers class
        """
        scheduler = DummyScheduler(
            global_config={"asyncz.loggers_class": "asyncz.schedulers.base:ClassicLogging"}
        )
        scheduler.start(paused=True)
        assert isinstance(scheduler.loggers, ClassicLogging)
        assert scheduler.logger_name == "asyncz.schedulers"

    def test_scheduler_change_logger_name(self):
        """
        Test scheduler is picking up the right logger name for loggers
        """
        scheduler = DummyScheduler(
            global_config={"asyncz.loggers_class": "asyncz.schedulers.base:ClassicLogging"},
            logger_name="test",
        )
        scheduler.start(paused=True)
        assert isinstance(scheduler.loggers, ClassicLogging)
        assert scheduler.logger_name == "asyncz.schedulers.test"

    @patch("asyncz.schedulers.base.default_loggers_class", side_effect=ClassicLogging)
    def test_scheduler_change_logger_change_default(self, patched):
        """
        Test scheduler is picking up the right loggers class
        """
        scheduler = DummyScheduler()
        scheduler.start(paused=True)
        assert isinstance(scheduler.loggers, ClassicLogging)
        assert scheduler.logger_name == "asyncz.schedulers"

    @pytest.mark.parametrize("method", [BaseScheduler.setup, BaseScheduler.start])
    def test_scheduler_already_running(self, method, scheduler):
        """
        Test that SchedulerAlreadyRunningError is raised when certain methods are called before
        the scheduler has been started.
        """
        scheduler.start(paused=True)
        # multi init is possible
        if method is BaseScheduler.start:
            assert method(scheduler) is False
        else:
            pytest.raises(SchedulerAlreadyRunningError, method, scheduler)

    def test_scheduler_multi_init(self, scheduler):
        assert scheduler.start(paused=True) is True
        assert scheduler.start(paused=True) is False
        assert scheduler.shutdown(wait=True) is False
        assert scheduler.shutdown(wait=True) is True

    @pytest.mark.parametrize(
        "method",
        [BaseScheduler.pause, BaseScheduler.resume, BaseScheduler.shutdown],
        ids=["pause", "resume", "shutdown"],
    )
    def test_scheduler_not_running(self, scheduler, method):
        """
        Test that the SchedulerNotRunningError is raised when certain methods are called before
        the scheduler has been started.

        """
        pytest.raises(SchedulerNotRunningError, method, scheduler)

    @patch("asyncz.schedulers.base.BaseScheduler.dispatch_event", side_effect=MagicMock())
    @patch("asyncz.schedulers.base.BaseScheduler.real_add_task", side_effect=MagicMock())
    def test_start(self, real_add_task, dispatch_events, scheduler, create_task):
        scheduler.executors = {
            "exec1": MagicMock(BaseExecutor),
            "exec2": MagicMock(BaseExecutor),
        }
        scheduler.stores = {
            "store1": MagicMock(BaseStore),
            "store2": MagicMock(BaseStore),
        }
        task = create_task(fn=lambda: None)
        scheduler.pending_tasks = [(task, False, True)]
        scheduler.start()

        scheduler.executors["exec1"].start.assert_called_once_with(scheduler, "exec1")
        scheduler.executors["exec2"].start.assert_called_once_with(scheduler, "exec2")
        scheduler.stores["store1"].start.assert_called_once_with(scheduler, "store1")
        scheduler.stores["store2"].start.assert_called_once_with(scheduler, "store2")

        assert len(scheduler.executors) == 3
        assert len(scheduler.stores) == 3
        assert "default" in scheduler.executors
        assert "default" in scheduler.stores

        scheduler.real_add_task.assert_called_once_with(task, False, True)
        assert scheduler.pending_tasks == []

        assert scheduler.dispatch_event.call_count == 3
        event = scheduler.dispatch_event.call_args_list[0][0][0]
        assert event.code == EXECUTOR_ADDED
        assert event.alias == "default"

        event = scheduler.dispatch_event.call_args_list[1][0][0]
        assert event.code == STORE_ADDED
        assert event.alias == "default"
        event = scheduler.dispatch_event.call_args_list[2][0][0]
        assert event.code == SCHEDULER_STARTED

        assert scheduler.state == SchedulerState.STATE_RUNNING

    @patch("asyncz.stores.base.BaseStore.shutdown", side_effect=MagicMock())
    @patch("asyncz.executors.base.BaseExecutor.shutdown", side_effect=MagicMock())
    @pytest.mark.parametrize("wait", [True, False], ids=["wait", "nowait"])
    def test_shutdown(
        self, mock_exc_shutdown, mock_store_shutdown, scheduler, scheduler_events, wait
    ):
        executor = DummyExecutor()
        store = DummyStore()
        scheduler.add_executor(executor)
        scheduler.add_store(store)
        scheduler.start(paused=True)
        del scheduler_events[:]
        scheduler.shutdown(wait)

        assert scheduler.state == SchedulerState.STATE_STOPPED
        assert len(scheduler_events) == 1
        assert scheduler_events[0].code == SCHEDULER_SHUTDOWN

        executor.shutdown.assert_called_once_with(wait)
        store.shutdown.assert_called_once_with()

    def test_pause_resume(self, scheduler, scheduler_events):
        scheduler.start()
        del scheduler_events[:]
        scheduler.wakeup.reset_mock()

        scheduler.pause()

        assert len(scheduler_events) == 1
        assert scheduler_events[0].code == SCHEDULER_PAUSED
        assert not scheduler.wakeup.called

        scheduler.resume()
        assert len(scheduler_events) == 2
        assert scheduler_events[1].code == SCHEDULER_RESUMED
        assert scheduler.wakeup.called

    @pytest.mark.parametrize("start_scheduler", [True, False])
    def test_running(self, scheduler, start_scheduler):
        if start_scheduler:
            scheduler.start()
        assert scheduler.running is start_scheduler

    @pytest.mark.parametrize("start_scheduler", [True, False])
    def test_add_remove_executor(self, scheduler, scheduler_events, start_scheduler):
        if start_scheduler:
            scheduler.start(paused=True)

        del scheduler_events[:]
        executor = DummyExecutor()
        scheduler.add_executor(executor, "exec1")

        assert len(scheduler_events) == 1
        assert scheduler_events[0].code == EXECUTOR_ADDED
        assert scheduler_events[0].alias == "exec1"
        if start_scheduler:
            executor.start.assert_called_once_with(scheduler, "exec1")
        else:
            assert not executor.start.called

        scheduler.remove_executor("exec1")
        assert len(scheduler_events) == 2
        assert scheduler_events[1].code == EXECUTOR_REMOVED
        assert scheduler_events[1].alias == "exec1"
        assert executor.shutdown.called

    def test_add_executor_already_exists(self, scheduler):
        executor = DummyExecutor()
        scheduler.add_executor(executor)
        exc = pytest.raises(ValueError, scheduler.add_executor, executor)
        assert (
            str(exc.value) == "This scheduler already has an executor by the alias of 'default'."
        )

    def test_remove_executor_nonexistent(self, scheduler):
        pytest.raises(KeyError, scheduler.remove_executor, "foo")

    @pytest.mark.parametrize("start_scheduler", [True, False])
    def test_add_store(self, scheduler, scheduler_events, start_scheduler):
        if start_scheduler:
            scheduler.start()
        else:
            scheduler.wakeup = MagicMock().assert_not_called()

        del scheduler_events[:]
        store = DummyStore()
        scheduler.add_store(store, "store1")

        assert len(scheduler_events) == 1
        assert scheduler_events[0].code == STORE_ADDED
        assert scheduler_events[0].alias == "store1"

        if start_scheduler:
            assert scheduler.wakeup.called
            store.start.assert_called_once_with(scheduler, "store1")
        else:
            assert not store.start.called

    def test_add_store_already_exists(self, scheduler):
        store = MemoryStore()
        scheduler.add_store(store)
        exc = pytest.raises(ValueError, scheduler.add_store, store)
        assert (
            str(exc.value) == "This scheduler already has a task store by the alias of 'default'."
        )

    def test_remove_store(self, scheduler, scheduler_events):
        scheduler.add_store(MemoryStore(), "foo")
        scheduler.remove_store("foo")

        assert len(scheduler_events) == 2
        assert scheduler_events[1].code == STORE_REMOVED
        assert scheduler_events[1].alias == "foo"

    def test_remove_store_nonexistent(self, scheduler):
        pytest.raises(KeyError, scheduler.remove_store, "foo")

    def test_add_remove_listener(self, scheduler):
        events = []
        scheduler.add_listener(events.append, EXECUTOR_ADDED)
        scheduler.add_executor(DummyExecutor(), "exec1")
        scheduler.remove_listener(events.append)
        scheduler.add_executor(DummyExecutor(), "exec2")
        assert len(events) == 1

    def test_add_task_return_value(self, scheduler, timezone):
        """Test that when a task is added to a stopped scheduler, a Task instance is returned."""
        task = scheduler.add_task(
            lambda x, y: None,
            "date",
            [1],
            {"y": 2},
            "my-id",
            "dummy",
            next_run_time=datetime(2020, 5, 23, 10),
            run_at="2020-06-01 08:41:00",
        )

        assert isinstance(task, Task)
        assert task.id == "my-id"

        assert task.mistrigger_grace_time == 1
        assert task.coalesce is True
        assert task.max_instances == 1

        assert task.next_run_time.tzinfo.zone == timezone.zone

    def test_add_task_obj_return_value(self, scheduler, timezone):
        """Test that when a task is added to a stopped scheduler, a Task instance is returned."""
        task = Task(
            fn=lambda x, y: None,
            id="my-id",
            name="dummy",
            args=[1],
            kwargs={"y": 2},
        )
        assert task.scheduler is None
        task = scheduler.add_task(task, trigger="date", run_at="2020-06-01 08:41:00")

        assert isinstance(task, Task)
        assert task.id == "my-id"
        assert task.trigger is not None
        assert task.scheduler is not None

        assert task.mistrigger_grace_time == 1
        assert task.coalesce is True
        assert task.max_instances == 1
        assert task.submitted
        # test that submitting works only once
        with pytest.raises(AssertionError):
            scheduler.add_task(task)

    def test_add_task_obj_paused_update(self, scheduler, timezone):
        """Test that when a task is added to a stopped scheduler, a Task instance is returned."""
        task = Task(
            fn=lambda x, y: None,
            id="my-id",
            name="dummy",
            args=[1],
            kwargs={"y": 2},
        )
        task = scheduler.add_task(task, trigger="date", run_at="2020-06-01 08:41:00")

        assert isinstance(task, Task)
        assert task.id == "my-id"
        assert task.trigger

        assert task.mistrigger_grace_time == 1
        assert task.coalesce is True
        assert task.max_instances == 1

    def test_add_task_pending(self, scheduler, scheduler_events):
        scheduler.setup(
            task_defaults={
                "mistrigger_grace_time": 3,
                "coalesce": False,
                "max_instances": 6,
            }
        )
        task = scheduler.add_task(lambda: None, "interval", hours=1)
        assert not scheduler_events

        scheduler.start(paused=True)

        assert len(scheduler_events) == 3
        assert scheduler_events[2].code == TASK_ADDED
        assert scheduler_events[2].task_id is task.id

        assert task.mistrigger_grace_time == 3
        assert not task.coalesce
        assert task.max_instances == 6

    def test_add_paused_task(self, scheduler, scheduler_events):
        scheduler.setup(
            task_defaults={
                "mistrigger_grace_time": 3,
                "coalesce": False,
                "max_instances": 6,
            }
        )
        task = scheduler.add_task(lambda: None, trigger="interval", hours=1, next_run_time=None)
        assert not scheduler_events

        scheduler.start()

        assert len(scheduler_events) == 3
        assert scheduler_events[2].code == TASK_ADDED
        assert scheduler_events[2].task_id is task.id

        assert task.next_run_time is None

    def test_add_task_id_conflict(self, scheduler):
        scheduler.start(paused=True)
        scheduler.add_task(lambda: None, "interval", id="testtask", seconds=1)
        pytest.raises(
            ConflictIdError,
            scheduler.add_task,
            lambda: None,
            "interval",
            id="testtask",
            seconds=1,
        )

    def test_add_task_replace_existing_true(self, scheduler):
        scheduler.start(paused=True)
        scheduler.add_task(lambda: None, "interval", id="testtask", seconds=1)
        scheduler.add_task(
            lambda: None,
            "cron",
            id="testtask",
            name="replacement",
            replace_existing=True,
        )
        tasks = scheduler.get_tasks()
        assert len(tasks) == 1
        assert tasks[0].name == "replacement"

    def test_add_task_task(self, scheduler):
        scheduler.start(paused=True)
        scheduler.add_task(lambda: None, "interval", id="testtask", seconds=1, name="original")
        decorator = scheduler.add_task(
            None,
            "cron",
            id="testtask",
            name="replacement",
        )
        tasks = scheduler.get_tasks()
        assert len(tasks) == 1
        assert tasks[0].name == "original"

        def fn():
            return None

        assert decorator(fn) is fn
        tasks = scheduler.get_tasks()
        assert len(tasks) == 1
        assert tasks[0].name == "replacement"

    def test_add_task_to_decorator(self, scheduler):
        def fn(x, y): ...

        decorator = scheduler.add_task(
            None,
            "date",
            [1],
            {"y": 2},
            description="dummy",
            run_at="2022-06-01 08:41:00",
        )
        object_setter(scheduler, "add_task", MagicMock())
        decorator(fn)

        scheduler.add_task.assert_called_once()
        assert hasattr(fn, "asyncz_tasks")
        assert len(fn.asyncz_tasks) == 1

    @pytest.mark.parametrize("pending", [True, False], ids=["pending task", "scheduled task"])
    def test_update_task(self, scheduler, pending, timezone):
        task = MagicMock()
        object_setter(scheduler, "dispatch_event", MagicMock())
        object_setter(
            scheduler,
            "lookup_task",
            MagicMock(return_value=(task, None if pending else "default")),
        )
        if not pending:
            store = MagicMock()
            object_setter(
                scheduler,
                "lookup_store",
                lambda alias: store if alias == "default" else None,
            )
        scheduler.update_task(
            "blah",
            mistrigger_grace_time=5,
            max_instances=2,
            next_run_time=datetime(2022, 10, 17),
        )

        task.update.assert_called_once_with(
            mistrigger_grace_time=5,
            max_instances=2,
            next_run_time=datetime(2022, 10, 17),
        )
        if not pending:
            store.update_task.assert_called_once_with(task)

        assert scheduler.dispatch_event.call_count == 1
        event = scheduler.dispatch_event.call_args[0][0]
        assert event.code == TASK_MODIFIED
        assert event.store == (None if pending else "default")

    def test_reschedule_task(self, scheduler):
        object_setter(scheduler, "update_task", MagicMock())
        trigger = MagicMock(get_next_trigger_time=lambda timezone, previous, now: 1)
        object_setter(scheduler, "create_trigger", MagicMock(return_value=trigger))
        scheduler.reschedule_task("my-id", "store", "date", run_at="2022-06-01 08:41:00")

        assert scheduler.update_task.call_count == 1
        assert scheduler.update_task.call_args[0] == ("my-id", "store")
        assert scheduler.update_task.call_args[1] == {
            "trigger": trigger,
            "next_run_time": 1,
        }

    def test_pause_task(self, scheduler):
        object_setter(scheduler, "update_task", MagicMock())
        scheduler.pause_task("task_id", "store")

        scheduler.update_task.assert_called_once_with("task_id", "store", next_run_time=None)

    @pytest.mark.parametrize("dead_task", [True, False], ids=["dead task", "live task"])
    def test_resume_task(self, scheduler, freeze_time, dead_task):
        next_trigger_time = None if dead_task else freeze_time.current + timedelta(seconds=1)
        trigger = MagicMock(
            BaseTrigger, get_next_trigger_time=lambda timezone, prev, now: next_trigger_time
        )
        returned_task = MagicMock(Task, id="foo", trigger=trigger)
        object_setter(scheduler, "lookup_task", MagicMock(return_value=(returned_task, "bar")))
        object_setter(scheduler, "update_task", MagicMock())
        object_setter(scheduler, "delete_task", MagicMock())
        scheduler.resume_task("foo")

        if dead_task:
            scheduler.delete_task.assert_called_once_with("foo", "bar")
        else:
            scheduler.update_task.assert_called_once_with(
                "foo", "bar", next_run_time=next_trigger_time
            )

    @pytest.mark.parametrize("scheduler_started", [True, False], ids=["running", "stopped"])
    @pytest.mark.parametrize("store", [None, "other"], ids=["all stores", "specific store"])
    def test_get_tasks(self, scheduler, scheduler_started, store):
        scheduler.add_store(MemoryStore(), "other")
        scheduler.add_task(lambda: None, "interval", seconds=1, id="task1")
        scheduler.add_task(lambda: None, "interval", seconds=1, id="task2", store="other")
        if scheduler_started:
            scheduler.start(paused=True)

        expected_task_ids = {"task2"}
        if store is None:
            expected_task_ids.add("task1")

        task_ids = {task.id for task in scheduler.get_tasks(store)}
        assert task_ids == expected_task_ids

    @pytest.mark.parametrize("store", [None, "bar"], ids=["any store", "specific store"])
    def test_get_task(self, scheduler, store):
        returned_task = object()
        object_setter(scheduler, "lookup_task", MagicMock(return_value=(returned_task, "bar")))
        task = scheduler.get_task("foo", store)

        assert task is returned_task

    def test_get_task_nonexistent_task(self, scheduler):
        object_setter(scheduler, "lookup_task", MagicMock(side_effect=TaskLookupError("foo")))
        assert scheduler.get_task("foo") is None

    def test_get_task_nonexistent_store(self, scheduler):
        assert scheduler.get_task("foo", "bar") is None

    @pytest.mark.parametrize("start_scheduler", [True, False])
    @pytest.mark.parametrize("store", [None, "other"], ids=["any store", "specific store"])
    def test_remove_task(self, scheduler, scheduler_events, start_scheduler, store):
        scheduler.add_store(MemoryStore(), "other")
        scheduler.add_task(lambda: None, id="task1")
        if start_scheduler:
            scheduler.start(paused=True)

        del scheduler_events[:]
        if store:
            pytest.raises(TaskLookupError, scheduler.delete_task, "task1", store)
            assert len(scheduler.get_tasks()) == 1
            assert len(scheduler_events) == 0
        else:
            scheduler.delete_task("task1", store)
            assert len(scheduler.get_tasks()) == 0
            assert len(scheduler_events) == 1
            assert scheduler_events[0].code == TASK_REMOVED

    def test_remove_nonexistent_task(self, scheduler):
        pytest.raises(TaskLookupError, scheduler.delete_task, "foo")

    @pytest.mark.parametrize("start_scheduler", [True, False])
    @pytest.mark.parametrize("store", [None, "other"], ids=["all", "single store"])
    def test_remove_all_tasks(self, scheduler, start_scheduler, scheduler_events, store):
        scheduler.add_store(MemoryStore(), "other")
        scheduler.add_task(lambda: None, id="task1")
        scheduler.add_task(lambda: None, id="task2")
        scheduler.add_task(lambda: None, id="task3", store="other")
        if start_scheduler:
            scheduler.start(paused=True)

        del scheduler_events[:]
        scheduler.remove_all_tasks(store)
        tasks = scheduler.get_tasks()

        assert len(tasks) == (2 if store else 0)
        assert len(scheduler_events) == 1
        assert scheduler_events[0].code == ALL_TASKS_REMOVED
        assert scheduler_events[0].alias == store

    @pytest.mark.parametrize(
        "config",
        [
            {
                "timezone": "UTC",
                "task_defaults": {
                    "mistrigger_grace_time": "5",
                    "coalesce": "false",
                    "max_instances": "9",
                },
                "executors": {
                    "default": {
                        "class": f"{__name__}:DummyExecutor",
                        "arg1": "3",
                        "arg2": "a",
                    },
                    "alter": {"class": f"{__name__}:DummyExecutor", "arg": "true"},
                },
                "stores": {
                    "default": {
                        "class": f"{__name__}:DummyStore",
                        "arg1": "3",
                        "arg2": "a",
                    },
                    "bar": {"class": f"{__name__}:DummyStore", "arg": "false"},
                },
            },
            {
                "timezone": ZoneInfo("UTC"),
                "task_defaults": {
                    "mistrigger_grace_time": 5,
                    "coalesce": False,
                    "max_instances": 9,
                },
                "executors": {
                    "default": DummyExecutor(arg1="3", arg2="a"),
                    "alter": DummyExecutor(arg="true"),
                },
                "stores": {
                    "default": DummyStore(arg1="3", arg2="a"),
                    "bar": DummyStore(arg="false"),
                },
            },
        ],
        ids=["references", "instances"],
    )
    def test_configure_private(self, scheduler, config):
        scheduler._setup(config)

        assert scheduler.timezone is ZoneInfo("UTC")
        assert scheduler.task_defaults.model_dump() == {
            "mistrigger_grace_time": 5,
            "coalesce": False,
            "max_instances": 9,
        }

        assert set(scheduler.executors.keys()) == {"default", "alter"}
        assert scheduler.executors["default"].args == {"arg1": "3", "arg2": "a"}
        assert scheduler.executors["alter"].args == {"arg": "true"}
        assert set(scheduler.stores.keys()) == {"default", "bar"}
        assert scheduler.stores["default"].args == {"arg1": "3", "arg2": "a"}
        assert scheduler.stores["bar"].args == {"arg": "false"}

    def test_configure_private_invalid_executor(self, scheduler):
        exc = pytest.raises(TypeError, scheduler._setup, {"executors": {"default": 6}})
        assert str(exc.value) == (
            "Expected executor instance or dict for executors['default'], " "got int instead."
        )

    def test_configure_private_invalid_store(self, scheduler):
        exc = pytest.raises(TypeError, scheduler._setup, {"stores": {"default": 6}})
        assert str(exc.value) == (
            "Expected store instance or dict for stores['default'], " "got int instead."
        )

    def test_create_default_executor(self, scheduler):
        executor = scheduler.create_default_executor()
        assert isinstance(executor, BaseExecutor)

    def test_create_default_store(self, scheduler):
        store = scheduler.create_default_store()
        assert isinstance(store, BaseStore)

    def test_lookup_executor(self, scheduler):
        executor = object()
        scheduler.executors = {"executor": executor}
        assert scheduler.lookup_executor("executor") is executor

    def test_lookup_executor_nonexistent(self, scheduler):
        pytest.raises(KeyError, scheduler.lookup_executor, "executor")

    def test_lookup_store(self, scheduler):
        store = object()
        scheduler.stores = {"store": store}
        assert scheduler.lookup_store("store") is store

    def test_lookup_store_nonexistent(self, scheduler):
        pytest.raises(KeyError, scheduler.lookup_store, "store")

    def test_dispatch_event(self, scheduler):
        event = SchedulerEvent(code=1)
        scheduler.listeners = [
            (MagicMock(), 2),
            (MagicMock(side_effect=Exception), 1),
            (MagicMock(), 1),
        ]
        scheduler.dispatch_event(event)

        assert not scheduler.listeners[0][0].called
        scheduler.listeners[1][0].assert_called_once_with(event)

    @pytest.mark.parametrize("load_plugin", [True, False], ids=["load plugin", "plugin loaded"])
    @patch("asyncz.schedulers.base.BaseScheduler.resolve_load_plugin")
    def test_create_trigger(self, mocked_plugin, scheduler, load_plugin):
        mocked_plugin.return_value = DummyTrigger

        scheduler.trigger_plugins = {}
        scheduler.trigger_classes = {}
        if load_plugin:
            scheduler.trigger_plugins["dummy"] = MagicMock(
                load=MagicMock(return_value=DummyTrigger)
            )
        else:
            scheduler.trigger_classes["dummy"] = DummyTrigger

        result = scheduler.create_trigger("dummy", {"a": 1, "b": "x"})

        assert isinstance(result, DummyTrigger)
        assert result.args == {"a": 1, "b": "x", "timezone": scheduler.timezone}

    def test_create_trigger_instance(self, scheduler):
        trigger_instance = DummyTrigger()

        assert scheduler.create_trigger(trigger_instance, {}) is trigger_instance

    def test_create_trigger_default_type(self, scheduler):
        scheduler.trigger_classes = {"date": DummyTrigger}
        result = scheduler.create_trigger(None, {"a": 1})

        assert isinstance(result, DummyTrigger)
        assert result.args == {"a": 1, "timezone": scheduler.timezone}

    def test_create_trigger_bad_trigger_type(self, scheduler):
        exc = pytest.raises(TypeError, scheduler.create_trigger, 1, {})
        assert str(exc.value) == "Expected a trigger instance or string, got 'int' instead."

    @patch("asyncz.schedulers.base.BaseScheduler.resolve_load_plugin")
    def test_create_trigger_bad_plugin_type(self, mocked_plugin, scheduler):
        mocked_plugin.return_value = DummyStore

        mock_plugin = MagicMock()
        mock_plugin.load.configure_mock(return_value=object)
        scheduler.trigger_classes = {}
        scheduler.trigger_plugins = {"dummy": mock_plugin}
        exc = pytest.raises(TypeError, scheduler.create_trigger, "dummy", {})
        assert str(exc.value) == "The trigger entry point does not point to a trigger class."

    def test_create_trigger_nonexisting_plugin(self, scheduler):
        exc = pytest.raises(LookupError, scheduler.create_trigger, "dummy", {})
        assert str(exc.value) == "No trigger by the name 'dummy' was found."

    def test_create_lock(self, scheduler):
        lock = scheduler.create_lock()
        assert hasattr(lock, "__enter__")

    def test_process_tasks_empty(self, scheduler):
        assert scheduler.process_tasks() is None

    def test_task_submitted_event(self, scheduler, freeze_time):
        events = []
        scheduler.add_task(lambda: None, run_at=freeze_time.get())
        scheduler.add_listener(events.append, TASK_SUBMITTED)
        scheduler.start()
        scheduler.process_tasks()

        assert len(events) == 1
        assert events[0].scheduled_run_times == [freeze_time.get(scheduler.timezone)]

    @pytest.mark.parametrize(
        "scheduler_events", [TASK_MAX_INSTANCES], indirect=["scheduler_events"]
    )
    def test_task_max_instances_event(self, scheduler, scheduler_events, freeze_time):
        class MaxedOutExecutor(DebugExecutor):
            def send_task(self, task, run_times):
                raise MaximumInstancesError(task, 1)

        executor = MaxedOutExecutor()
        scheduler.add_executor(executor, "maxed")
        scheduler.add_task(lambda: None, run_at=freeze_time.get(), executor="maxed")
        scheduler.start()
        scheduler.process_tasks()

        assert len(scheduler_events) == 1
        assert scheduler_events[0].scheduled_run_times == [freeze_time.get(scheduler.timezone)]

    def test_serialize_scheduler(self, scheduler):
        pytest.raises(TypeError, pickle.dumps, scheduler).match("Schedulers cannot be serialized.")


class TestProcessTasks:
    @pytest.fixture
    def task(self):
        task = MagicMock(Task, id="999", executor="default", coalesce=False, max_instances=1)
        task.trigger = MagicMock(get_next_trigger_time=MagicMock(return_value=None))
        task.__str__ = lambda x: "task 999"
        return task

    @pytest.fixture
    def scheduler(self):
        scheduler = DummyScheduler()
        scheduler.start()
        return scheduler

    @pytest.fixture
    def store(self, scheduler, task):
        store = MagicMock(
            BaseStore,
            get_due_tasks=MagicMock(return_value=[task]),
            get_next_run_time=MagicMock(return_value=None),
        )
        scheduler.stores["default"] = store
        return store

    @pytest.fixture
    def executor(self, scheduler):
        executor = MagicMock(BaseExecutor)
        scheduler.executors["default"] = executor
        return executor

    def test_nonexistent_executor(self, scheduler, store, caplog):
        caplog.set_level(logging.ERROR)
        scheduler.remove_executor("default")

        assert scheduler.process_tasks() is None

        store.delete_task.assert_called_once_with("999")

        assert len(caplog.records) == 1

        assert (
            caplog.records[0].message
            == "Executor lookup ('default') failed for task 'task 999'. Removing it from the store."
        )

    def test_executor_error(self, scheduler, store, executor, caplog):
        caplog.set_level(logging.ERROR)
        executor.send_task = MagicMock(side_effect=Exception("test message"))

        assert scheduler.process_tasks() is None
        assert len(caplog.records) == 1
        assert "test message" in caplog.records[0].message
        assert "Error submitting task" in caplog.records[0].message

    def test_task_update(self, scheduler, task, store, freeze_time):
        next_run_time = freeze_time.current + timedelta(seconds=6)
        task.trigger.get_next_trigger_time = MagicMock(return_value=next_run_time)

        assert scheduler.process_tasks() is None

        task.update_task.assert_called_once_with(next_run_time=next_run_time)
        store.update_task.assert_called_once_with(task)


class SchedulerImpBaseTest:
    @pytest.fixture(autouse=True)
    def executor(self, scheduler):
        scheduler.add_executor(DebugExecutor())

    @pytest.fixture
    def start_scheduler(self, request, scheduler):
        yield scheduler.start
        if scheduler.running:
            scheduler.shutdown()

    @pytest.fixture
    def eventqueue(self, scheduler):
        from queue import Queue

        events = Queue()
        scheduler.add_listener(events.put)
        return events

    def wait_event(self, queue):
        return queue.get(True, 1)

    def test_add_pending_task(self, scheduler, freeze_time, eventqueue, start_scheduler):
        freeze_time.set_increment(timedelta(seconds=0.2))
        scheduler.add_task(lambda x, y: x + y, "date", args=[1, 2], run_at=freeze_time.next())
        start_scheduler()

        assert self.wait_event(eventqueue).code == STORE_ADDED
        assert self.wait_event(eventqueue).code == TASK_ADDED
        assert self.wait_event(eventqueue).code == SCHEDULER_STARTED

        event = self.wait_event(eventqueue)

        assert event.code == TASK_EXECUTED
        assert event.return_value == 3
        assert self.wait_event(eventqueue).code == TASK_REMOVED

    def test_add_live_task(self, scheduler, freeze_time, eventqueue, start_scheduler):
        freeze_time.set_increment(timedelta(seconds=0.2))
        start_scheduler()

        assert self.wait_event(eventqueue).code == STORE_ADDED
        assert self.wait_event(eventqueue).code == SCHEDULER_STARTED

        scheduler.add_task(
            lambda x, y: x + y,
            "date",
            args=[1, 2],
            run_at=freeze_time.next() + freeze_time.increment * 2,
        )
        assert self.wait_event(eventqueue).code == TASK_ADDED

        event = self.wait_event(eventqueue)

        assert event.code == TASK_EXECUTED
        assert event.return_value == 3
        assert self.wait_event(eventqueue).code == TASK_REMOVED

    def test_add_live_task_bg(self, scheduler, freeze_time, eventqueue, start_scheduler):
        freeze_time.set_increment(timedelta(seconds=0.2))
        start_scheduler()

        assert self.wait_event(eventqueue).code == STORE_ADDED
        assert self.wait_event(eventqueue).code == SCHEDULER_STARTED

        task = scheduler.add_task(
            lambda x, y: x + y,
            args=[1, 2],
        )
        assert task.mistrigger_grace_time is None
        assert self.wait_event(eventqueue).code == TASK_ADDED

        event = self.wait_event(eventqueue)

        assert event.code == TASK_EXECUTED
        assert event.return_value == 3
        assert self.wait_event(eventqueue).code == TASK_REMOVED

    def test_shutdown(self, scheduler, eventqueue, start_scheduler):
        start_scheduler()
        assert self.wait_event(eventqueue).code == STORE_ADDED
        assert self.wait_event(eventqueue).code == SCHEDULER_STARTED

        scheduler.shutdown()
        assert self.wait_event(eventqueue).code == SCHEDULER_SHUTDOWN


class TestAsyncIOScheduler(SchedulerImpBaseTest):
    @pytest.fixture
    def scheduler(self, event_loop):
        asyncio = pytest.importorskip("asyncz.schedulers.asyncio")
        return asyncio.AsyncIOScheduler(event_loop=event_loop)

    @pytest.fixture
    def start_scheduler(self, request, event_loop, scheduler):
        event_loop.call_soon_threadsafe(scheduler.start)
        thread = Thread(target=event_loop.run_forever)
        yield thread.start

        if scheduler.running:
            event_loop.call_soon_threadsafe(scheduler.shutdown)
        event_loop.call_soon_threadsafe(event_loop.stop)
        thread.join()


def test_generator():
    call_count = 0
    is_setup = False
    is_exited = False

    scheduler = AsyncIOScheduler()

    def lifespan_gen():
        nonlocal call_count, is_setup, is_exited
        # setup
        scheduler.add_task(make_function(generator.send), args=[True], name="advance")
        scheduler.add_task(
            make_function(generator.send), args=[False], trigger="shutdown", name="shutdown"
        )
        is_setup = True
        running = yield
        while running:
            call_count += 1
            running = yield
        is_exited = True

    generator = lifespan_gen()
    assert is_setup is False
    assert call_count == 0
    assert is_exited is False
    generator.send(None)
    assert is_setup is True
    assert call_count == 0
    assert is_exited is False
    with scheduler:
        time.sleep(0.5)
        assert is_setup is True
        assert call_count == 1
        assert is_exited is False

    # cleanup time
    time.sleep(0.2)

    assert is_setup is True
    assert call_count == 1
    assert is_exited is True


def test_async_generator_in_sync():
    call_count = 0
    is_setup = False
    is_exited = False
    loop = asyncio.new_event_loop()
    scheduler = AsyncIOScheduler()

    async def lifespan_gen():
        nonlocal call_count, is_setup, is_exited
        # setup
        scheduler.add_task(make_async_function(generator.asend), args=[True], name="advance")
        scheduler.add_task(
            make_async_function(generator.asend), args=[False], trigger="shutdown", name="shutdown"
        )
        is_setup = True
        running = yield
        while running:
            call_count += 1
            running = yield
        is_exited = True

    generator = lifespan_gen()
    assert is_setup is False
    assert call_count == 0
    assert is_exited is False
    loop.run_until_complete(generator.asend(None))
    assert is_setup is True
    assert call_count == 0
    assert is_exited is False
    with scheduler:
        assert scheduler.event_loop_thread is not None
        time.sleep(0.5)
        assert is_setup is True
        assert call_count == 1
        assert is_exited is False

    # cleanup time
    time.sleep(0.2)

    assert scheduler.event_loop_thread is None
    assert is_setup is True
    assert call_count == 1
    assert is_exited is True


@pytest.mark.asyncio(loop_scope="function")
async def test_async_generator_in_async():
    call_count = 0
    is_setup = False
    is_exited = False
    scheduler = AsyncIOScheduler()

    async def lifespan_gen():
        nonlocal call_count, is_setup, is_exited
        # setup
        scheduler.add_task(make_async_function(generator.asend), args=[True], name="advance")
        scheduler.add_task(
            make_async_function(generator.asend), args=[False], trigger="shutdown", name="shutdown"
        )
        is_setup = True
        running = yield
        while running:
            call_count += 1
            running = yield
        is_exited = True

    generator = lifespan_gen()
    assert is_setup is False
    assert call_count == 0
    assert is_exited is False
    await generator.asend(None)
    assert is_setup is True
    assert call_count == 0
    assert is_exited is False

    async with scheduler:
        await asyncio.sleep(0.5)
        assert is_setup is True
        assert call_count == 1
        assert is_exited is False

    await asyncio.sleep(0.2)
    assert is_setup is True
    assert call_count == 1
    assert is_exited is True


@pytest.mark.asyncio(loop_scope="function")
async def test_native_async_generator_in_async():
    call_count = 0
    is_setup = False
    is_exited = False

    async def lifespan_gen():
        nonlocal call_count, is_setup, is_exited
        # setup
        scheduler.add_task(make_async_function(generator.asend), args=[True], name="advance")
        scheduler.add_task(
            make_async_function(generator.asend), args=[False], trigger="shutdown", name="shutdown"
        )
        is_setup = True
        running = yield
        while running:
            call_count += 1
            running = yield
        is_exited = True

    scheduler = NativeAsyncIOScheduler()
    generator = lifespan_gen()
    assert is_setup is False
    assert call_count == 0
    assert is_exited is False
    await generator.asend(None)
    assert is_setup is True
    assert call_count == 0
    assert is_exited is False

    async with scheduler:
        await asyncio.sleep(0.5)
        assert is_setup is True
        assert call_count == 1
        assert is_exited is False
    assert is_setup is True
    assert call_count == 1
    assert is_exited is True
