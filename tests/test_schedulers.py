import logging
import pickle
from datetime import datetime, timedelta
from threading import Thread
from typing import Any, List, Optional, Union

import pytest
from asyncz.enums import SchedulerState
from asyncz.events.base import SchedulerEvent
from asyncz.events.constants import (
    ALL_EVENTS,
    ALL_JOBS_REMOVED,
    EXECUTOR_ADDED,
    EXECUTOR_REMOVED,
    JOB_ADDED,
    JOB_EXECUTED,
    JOB_MAX_INSTANCES,
    JOB_MODIFIED,
    JOB_REMOVED,
    JOB_SUBMITTED,
    SCHEDULER_PAUSED,
    SCHEDULER_RESUMED,
    SCHEDULER_SHUTDOWN,
    SCHEDULER_STARTED,
    STORE_ADDED,
    STORE_REMOVED,
)
from asyncz.exceptions import (
    ConflictIdError,
    JobLookupError,
    MaxInterationsReached,
    SchedulerAlreadyRunningError,
    SchedulerNotRunningError,
)
from asyncz.executors.base import BaseExecutor
from asyncz.executors.debug import DebugExecutor
from asyncz.jobs import Job
from asyncz.jobs.types import JobType
from asyncz.schedulers.base import BaseScheduler
from asyncz.stores.base import BaseStore
from asyncz.stores.memory import MemoryStore
from asyncz.triggers.base import BaseTrigger
from asyncz.typing import undefined
from mock import MagicMock, patch
from pytz import utc


class DummyScheduler(BaseScheduler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.wakeup = MagicMock()

    def shutdown(self, wait=True):
        super().shutdown(wait)

    def wakeup(self):
        ...


class DummyTrigger(BaseTrigger):
    def __init__(self, **args):
        super().__init__(**args)
        self.args = args

    def get_next_trigger_time(
        self, previous_time: datetime, now: Optional[datetime] = None
    ) -> Union[datetime, None]:
        ...


class DummyExecutor(BaseExecutor):
    def __init__(self, **args):
        super().__init__(**args)
        self.args = args
        self.start = MagicMock()
        self.shutdown = MagicMock()
        self.send_job = MagicMock()

    def do_send_job(self, job: "JobType", run_times: List[datetime]) -> Any:
        return super().do_send_job(job, run_times)


class DummyStore(BaseStore):
    def __init__(self, **args):
        super().__init__(**args)
        self.args = args
        self.start = MagicMock()
        self.shutdown = MagicMock()

    def get_due_jobs(self, now: datetime) -> List["JobType"]:
        ...

    def lookup_job(self, job_id: Union[str, int]) -> "JobType":
        ...

    def delete_job(self, job_id: Union[str, int]):
        ...

    def remove_all_jobs(self):
        ...

    def get_next_run_time(self) -> datetime:
        ...

    def get_all_jobs(self) -> List["JobType"]:
        ...

    def add_job(self, job: "JobType"):
        ...

    def update_job(self, job: "JobType"):
        ...


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
        with patch("%s.DummyScheduler.configure" % __name__) as configure:
            global_config = {"asyncz.foo": "bar", "asyncz.x": "y"}
            options = {"bar": "baz", "xyz": 123}
            DummyScheduler(global_config, **options)

        configure.assert_called_once_with(global_config, **options)

    @pytest.mark.parametrize(
        "global_config",
        [
            {
                "asyncz.timezone": "UTC",
                "asyncz.job_defaults.mistrigger_grace_time": "5",
                "asyncz.job_defaults.coalesce": "false",
                "asyncz.job_defaults.max_instances": "9",
                "asyncz.executors.default.class": "%s:DummyExecutor" % __name__,
                "asyncz.executors.default.arg1": "3",
                "asyncz.executors.default.arg2": "a",
                "asyncz.executors.alter.class": "%s:DummyExecutor" % __name__,
                "asyncz.executors.alter.arg": "true",
                "asyncz.stores.default.class": "%s:DummyStore" % __name__,
                "asyncz.stores.default.arg1": "3",
                "asyncz.stores.default.arg2": "a",
                "asyncz.stores.bar.class": "%s:DummyStore" % __name__,
                "asyncz.stores.bar.arg": "false",
            },
            {
                "asyncz.timezone": "UTC",
                "asyncz.job_defaults": {
                    "mistrigger_grace_time": "5",
                    "coalesce": "false",
                    "max_instances": "9",
                },
                "asyncz.executors": {
                    "default": {"class": "%s:DummyExecutor" % __name__, "arg1": "3", "arg2": "a"},
                    "alter": {"class": "%s:DummyExecutor" % __name__, "arg": "true"},
                },
                "asyncz.stores": {
                    "default": {"class": "%s:DummyStore" % __name__, "arg1": "3", "arg2": "a"},
                    "bar": {"class": "%s:DummyStore" % __name__, "arg": "false"},
                },
            },
        ],
        ids=["ini-style", "yaml-style"],
    )
    def test_configure(self, scheduler, global_config):
        scheduler._configure = MagicMock()
        scheduler.configure(global_config, timezone="Other timezone")

        scheduler._configure.assert_called_once_with(
            {
                "timezone": "Other timezone",
                "job_defaults": {
                    "mistrigger_grace_time": "5",
                    "coalesce": "false",
                    "max_instances": "9",
                },
                "executors": {
                    "default": {"class": "%s:DummyExecutor" % __name__, "arg1": "3", "arg2": "a"},
                    "alter": {"class": "%s:DummyExecutor" % __name__, "arg": "true"},
                },
                "stores": {
                    "default": {"class": "%s:DummyStore" % __name__, "arg1": "3", "arg2": "a"},
                    "bar": {"class": "%s:DummyStore" % __name__, "arg": "false"},
                },
            }
        )

    @pytest.mark.parametrize("method", [BaseScheduler.configure, BaseScheduler.start])
    def test_scheduler_already_running(self, method, scheduler):
        """
        Test that SchedulerAlreadyRunningError is raised when certain methods are called before
        the scheduler has been started.
        """
        scheduler.start(paused=True)
        pytest.raises(SchedulerAlreadyRunningError, method, scheduler)

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

    def test_start(self, scheduler, create_job):
        scheduler.executors = {"exec1": MagicMock(BaseExecutor), "exec2": MagicMock(BaseExecutor)}
        scheduler.stores = {"store1": MagicMock(BaseStore), "store2": MagicMock(BaseStore)}
        job = create_job(fn=lambda: None)
        scheduler.pending_jobs = [(job, "store1", False)]
        scheduler.real_add_job = MagicMock()
        scheduler.dispatch_event = MagicMock()
        scheduler.start()

        scheduler.executors["exec1"].start.assert_called_once_with(scheduler, "exec1")
        scheduler.executors["exec2"].start.assert_called_once_with(scheduler, "exec2")
        scheduler.stores["store1"].start.assert_called_once_with(scheduler, "store1")
        scheduler.stores["store2"].start.assert_called_once_with(scheduler, "store2")

        assert len(scheduler.executors) == 3
        assert len(scheduler.stores) == 3
        assert "default" in scheduler.executors
        assert "default" in scheduler.stores

        scheduler.real_add_job.assert_called_once_with(job, "store1", False)
        assert scheduler.pending_jobs == []

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

    @pytest.mark.parametrize("wait", [True, False], ids=["wait", "nowait"])
    def test_shutdown(self, scheduler, scheduler_events, wait):
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
            str(exc.value) == "This scheduler already has a job store by the alias of 'default'."
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

    def test_add_job_return_value(self, scheduler, timezone):
        """Test that when a job is added to a stopped scheduler, a Job instance is returned."""
        job = scheduler.add_job(
            lambda x, y: None,
            "date",
            [1],
            {"y": 2},
            "my-id",
            "dummy",
            next_run_time=datetime(2020, 5, 23, 10),
            run_at="2020-06-01 08:41:00",
        )

        assert isinstance(job, Job)
        assert job.id == "my-id"

        assert not hasattr(job, "mistrigger_grace_time")
        assert not hasattr(job, "coalesce")
        assert not hasattr(job, "max_instances")

        assert job.next_run_time.tzinfo.zone == timezone.zone

    def test_add_job_pending(self, scheduler, scheduler_events):
        scheduler.configure(
            job_defaults={"mistrigger_grace_time": 3, "coalesce": False, "max_instances": 6}
        )
        job = scheduler.add_job(lambda: None, "interval", hours=1)
        assert not scheduler_events

        scheduler.start(paused=True)

        assert len(scheduler_events) == 3
        assert scheduler_events[2].code == JOB_ADDED
        assert scheduler_events[2].job_id is job.id

        assert job.mistrigger_grace_time == 3
        assert not job.coalesce
        assert job.max_instances == 6

    def test_add_job_id_conflict(self, scheduler):
        scheduler.start(paused=True)
        scheduler.add_job(lambda: None, "interval", id="testjob", seconds=1)
        pytest.raises(
            ConflictIdError, scheduler.add_job, lambda: None, "interval", id="testjob", seconds=1
        )

    def test_add_job_replace_existing_true(self, scheduler):
        scheduler.start(paused=True)
        scheduler.add_job(lambda: None, "interval", id="testjob", seconds=1)
        scheduler.add_job(
            lambda: None, "cron", id="testjob", name="replacement", replace_existing=True
        )
        jobs = scheduler.get_jobs()
        assert len(jobs) == 1
        assert jobs[0].name == "replacement"

    def test_scheduled_job(self, scheduler):
        def fn(x, y):
            ...

        scheduler.add_job = MagicMock()
        decorator = scheduler.scheduled_job(
            "date", [1], {"y": 2}, "my-id", "dummy", run_at="2022-06-01 08:41:00"
        )
        decorator(fn)

        scheduler.add_job.assert_called_once_with(
            fn=fn,
            trigger="date",
            args=[1],
            kwargs={"y": 2},
            id="my-id",
            name="dummy",
            mistrigger_grace_time=undefined,
            coalesce=undefined,
            max_instances=undefined,
            next_run_time=undefined,
            store="default",
            executor="default",
            replace_existing=True,
            run_at="2022-06-01 08:41:00",
        )

    @pytest.mark.parametrize("pending", [True, False], ids=["pending job", "scheduled job"])
    def test_update_job(self, scheduler, pending, timezone):

        job = MagicMock()
        scheduler.dispatch_event = MagicMock()
        scheduler.lookup_job = MagicMock(return_value=(job, None if pending else "default"))
        if not pending:
            store = MagicMock()
            scheduler.lookup_store = lambda alias: store if alias == "default" else None
        scheduler.update_job(
            "blah",
            mistrigger_grace_time=5,
            max_instances=2,
            next_run_time=datetime(2022, 10, 17),
        )

        job.update.assert_called_once_with(
            mistrigger_grace_time=5, max_instances=2, next_run_time=datetime(2022, 10, 17)
        )
        if not pending:
            store.update_job.assert_called_once_with(job)

        assert scheduler.dispatch_event.call_count == 1
        event = scheduler.dispatch_event.call_args[0][0]
        assert event.code == JOB_MODIFIED
        assert event.store == (None if pending else "default")

    def test_reschedule_job(self, scheduler):
        scheduler.update_job = MagicMock()
        trigger = MagicMock(get_next_trigger_time=lambda previous, now: 1)
        scheduler.create_trigger = MagicMock(return_value=trigger)
        scheduler.reschedule_job("my-id", "store", "date", run_at="2022-06-01 08:41:00")

        assert scheduler.update_job.call_count == 1
        assert scheduler.update_job.call_args[0] == ("my-id", "store")
        assert scheduler.update_job.call_args[1] == {"trigger": trigger, "next_run_time": 1}

    def test_pause_job(self, scheduler):
        scheduler.update_job = MagicMock()
        scheduler.pause_job("job_id", "store")

        scheduler.update_job.assert_called_once_with("job_id", "store", next_run_time=None)

    @pytest.mark.parametrize("dead_job", [True, False], ids=["dead job", "live job"])
    def test_resume_job(self, scheduler, freeze_time, dead_job):
        next_trigger_time = None if dead_job else freeze_time.current + timedelta(seconds=1)
        trigger = MagicMock(BaseTrigger, get_next_trigger_time=lambda prev, now: next_trigger_time)
        returned_job = MagicMock(Job, id="foo", trigger=trigger)
        scheduler.lookup_job = MagicMock(return_value=(returned_job, "bar"))
        scheduler.update_job = MagicMock()
        scheduler.delete_job = MagicMock()
        scheduler.resume_job("foo")

        if dead_job:
            scheduler.delete_job.assert_called_once_with("foo", "bar")
        else:
            scheduler.update_job.assert_called_once_with(
                "foo", "bar", next_run_time=next_trigger_time
            )

    @pytest.mark.parametrize("scheduler_started", [True, False], ids=["running", "stopped"])
    @pytest.mark.parametrize("store", [None, "other"], ids=["all stores", "specific store"])
    def test_get_jobs(self, scheduler, scheduler_started, store):
        scheduler.add_store(MemoryStore(), "other")
        scheduler.add_job(lambda: None, "interval", seconds=1, id="job1")
        scheduler.add_job(lambda: None, "interval", seconds=1, id="job2", store="other")
        if scheduler_started:
            scheduler.start(paused=True)

        expected_job_ids = {"job2"}
        if store is None:
            expected_job_ids.add("job1")

        job_ids = {job.id for job in scheduler.get_jobs(store)}
        assert job_ids == expected_job_ids

    @pytest.mark.parametrize("store", [None, "bar"], ids=["any store", "specific store"])
    def test_get_job(self, scheduler, store):
        returned_job = object()
        scheduler.lookup_job = MagicMock(return_value=(returned_job, "bar"))
        job = scheduler.get_job("foo", store)

        assert job is returned_job

    def test_get_job_nonexistent_job(self, scheduler):
        scheduler.lookup_job = MagicMock(side_effect=JobLookupError("foo"))
        assert scheduler.get_job("foo") is None

    def test_get_job_nonexistent_store(self, scheduler):
        assert scheduler.get_job("foo", "bar") is None

    @pytest.mark.parametrize("start_scheduler", [True, False])
    @pytest.mark.parametrize("store", [None, "other"], ids=["any store", "specific store"])
    def test_remove_job(self, scheduler, scheduler_events, start_scheduler, store):
        scheduler.add_store(MemoryStore(), "other")
        scheduler.add_job(lambda: None, id="job1")
        if start_scheduler:
            scheduler.start(paused=True)

        del scheduler_events[:]
        if store:
            pytest.raises(JobLookupError, scheduler.delete_job, "job1", store)
            assert len(scheduler.get_jobs()) == 1
            assert len(scheduler_events) == 0
        else:
            scheduler.delete_job("job1", store)
            assert len(scheduler.get_jobs()) == 0
            assert len(scheduler_events) == 1
            assert scheduler_events[0].code == JOB_REMOVED

    def test_remove_nonexistent_job(self, scheduler):
        pytest.raises(JobLookupError, scheduler.delete_job, "foo")

    @pytest.mark.parametrize("start_scheduler", [True, False])
    @pytest.mark.parametrize("store", [None, "other"], ids=["all", "single store"])
    def test_remove_all_jobs(self, scheduler, start_scheduler, scheduler_events, store):
        scheduler.add_store(MemoryStore(), "other")
        scheduler.add_job(lambda: None, id="job1")
        scheduler.add_job(lambda: None, id="job2")
        scheduler.add_job(lambda: None, id="job3", store="other")
        if start_scheduler:
            scheduler.start(paused=True)

        del scheduler_events[:]
        scheduler.remove_all_jobs(store)
        jobs = scheduler.get_jobs()

        assert len(jobs) == (2 if store else 0)
        assert len(scheduler_events) == 1
        assert scheduler_events[0].code == ALL_JOBS_REMOVED
        assert scheduler_events[0].alias == store

    @pytest.mark.parametrize(
        "config",
        [
            {
                "timezone": "UTC",
                "job_defaults": {
                    "mistrigger_grace_time": "5",
                    "coalesce": "false",
                    "max_instances": "9",
                },
                "executors": {
                    "default": {"class": "%s:DummyExecutor" % __name__, "arg1": "3", "arg2": "a"},
                    "alter": {"class": "%s:DummyExecutor" % __name__, "arg": "true"},
                },
                "stores": {
                    "default": {"class": "%s:DummyStore" % __name__, "arg1": "3", "arg2": "a"},
                    "bar": {"class": "%s:DummyStore" % __name__, "arg": "false"},
                },
            },
            {
                "timezone": utc,
                "job_defaults": {
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
        scheduler._configure(config)

        assert scheduler.timezone is utc
        assert scheduler.job_defaults == {
            "mistrigger_grace_time": 5,
            "coalesce": False,
            "max_instances": 9,
        }
        assert set(scheduler.executors.keys()) == set(["default", "alter"])
        assert scheduler.executors["default"].args == {"arg1": "3", "arg2": "a"}
        assert scheduler.executors["alter"].args == {"arg": "true"}
        assert set(scheduler.stores.keys()) == set(["default", "bar"])
        assert scheduler.stores["default"].args == {"arg1": "3", "arg2": "a"}
        assert scheduler.stores["bar"].args == {"arg": "false"}

    def test_configure_private_invalid_executor(self, scheduler):
        exc = pytest.raises(TypeError, scheduler._configure, {"executors": {"default": 6}})
        assert str(exc.value) == (
            "Expected executor instance or dict for executors['default'], " "got int instead."
        )

    def test_configure_private_invalid_store(self, scheduler):
        exc = pytest.raises(TypeError, scheduler._configure, {"stores": {"default": 6}})
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

    def test_process_jobs_empty(self, scheduler):
        assert scheduler.process_jobs() is None

    def test_job_submitted_event(self, scheduler, freeze_time):
        events = []
        scheduler.add_job(lambda: None, run_at=freeze_time.get())
        scheduler.add_listener(events.append, JOB_SUBMITTED)
        scheduler.start()
        scheduler.process_jobs()

        assert len(events) == 1
        assert events[0].scheduled_run_times == [freeze_time.get(scheduler.timezone)]

    @pytest.mark.parametrize(
        "scheduler_events", [JOB_MAX_INSTANCES], indirect=["scheduler_events"]
    )
    def test_job_max_instances_event(self, scheduler, scheduler_events, freeze_time):
        class MaxedOutExecutor(DebugExecutor):
            def send_job(self, job, run_times):
                raise MaxInterationsReached(job)

        executor = MaxedOutExecutor()
        scheduler.add_executor(executor, "maxed")
        scheduler.add_job(lambda: None, run_at=freeze_time.get(), executor="maxed")
        scheduler.start()
        scheduler.process_jobs()

        assert len(scheduler_events) == 1
        assert scheduler_events[0].scheduled_run_times == [freeze_time.get(scheduler.timezone)]

    def test_serialize_scheduler(self, scheduler):
        pytest.raises(TypeError, pickle.dumps, scheduler).match("Schedulers cannot be serialized.")


class TestProcessJobs:
    @pytest.fixture
    def job(self):
        job = MagicMock(Job, id=999, executor="default", coalesce=False, max_instances=1)
        job.trigger = MagicMock(get_next_trigger_time=MagicMock(return_value=None))
        job.__str__ = lambda x: "job 999"
        return job

    @pytest.fixture
    def scheduler(self):
        scheduler = DummyScheduler()
        scheduler.start()
        return scheduler

    @pytest.fixture
    def store(self, scheduler, job):
        store = MagicMock(
            BaseStore,
            get_due_jobs=MagicMock(return_value=[job]),
            get_next_trigger_time=MagicMock(return_value=None),
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

        assert scheduler.process_jobs() is None

        store.delete_job.assert_called_once_with(999)

        assert len(caplog.records) == 1

        assert (
            caplog.records[0].message
            == "Executor lookup ('default') failed for job 'job 999'. Removing it from the store."
        )

    def test_executor_error(self, scheduler, store, executor, caplog):
        caplog.set_level(logging.ERROR)
        executor.send_job = MagicMock(side_effect=Exception("test message"))

        assert scheduler.process_jobs() is None
        assert len(caplog.records) == 1
        assert "test message" in caplog.records[0].message
        assert "Error submitting job" in caplog.records[0].message

    def test_job_update(self, scheduler, job, store, freeze_time):
        next_run_time = freeze_time.current + timedelta(seconds=6)
        job.trigger.get_next_trigger_time = MagicMock(return_value=next_run_time)

        assert scheduler.process_jobs() is None

        job._update.assert_called_once_with(next_run_time=next_run_time)
        store.update_job.assert_called_once_with(job)


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

    def test_add_pending_job(self, scheduler, freeze_time, eventqueue, start_scheduler):
        freeze_time.set_increment(timedelta(seconds=0.2))
        scheduler.add_job(lambda x, y: x + y, "date", args=[1, 2], run_date=freeze_time.next())
        start_scheduler()

        assert self.wait_event(eventqueue).code == STORE_ADDED
        assert self.wait_event(eventqueue).code == JOB_ADDED
        assert self.wait_event(eventqueue).code == SCHEDULER_STARTED

        event = self.wait_event(eventqueue)

        assert event.code == JOB_EXECUTED
        assert event.return_value == 3
        assert self.wait_event(eventqueue).code == JOB_REMOVED

    def test_add_live_job(self, scheduler, freeze_time, eventqueue, start_scheduler):
        freeze_time.set_increment(timedelta(seconds=0.2))
        start_scheduler()

        assert self.wait_event(eventqueue).code == STORE_ADDED
        assert self.wait_event(eventqueue).code == SCHEDULER_STARTED

        scheduler.add_job(
            lambda x, y: x + y,
            "date",
            args=[1, 2],
            run_date=freeze_time.next() + freeze_time.increment * 2,
        )
        assert self.wait_event(eventqueue).code == JOB_ADDED

        event = self.wait_event(eventqueue)

        assert event.code == JOB_EXECUTED
        assert event.return_value == 3
        assert self.wait_event(eventqueue).code == JOB_REMOVED

    def test_shutdown(self, scheduler, eventqueue, start_scheduler):
        start_scheduler()
        assert self.wait_event(eventqueue).code == STORE_ADDED
        assert self.wait_event(eventqueue).code == SCHEDULER_STARTED

        scheduler.shutdown()
        assert self.wait_event(eventqueue).code == SCHEDULER_SHUTDOWN


class TestAsyncIOScheduler(SchedulerImpBaseTest):
    @pytest.fixture
    def event_loop(self):
        asyncio = pytest.importorskip("asyncz.schedulers.asyncio")
        return asyncio.asyncio.new_event_loop()

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
