from datetime import datetime
from typing import Any, Dict, List, Optional, Union

import pytest
from asyncz.contrib.esmerald.decorator import scheduler
from asyncz.contrib.esmerald.scheduler import EsmeraldScheduler
from asyncz.executors.base import BaseExecutor
from asyncz.jobs.types import JobType
from asyncz.schedulers import AsyncIOScheduler
from asyncz.schedulers.base import BaseScheduler
from asyncz.stores.base import BaseStore
from asyncz.triggers import IntervalTrigger
from asyncz.triggers.base import BaseTrigger
from esmerald import Esmerald
from loguru import logger
from mock import MagicMock, Mock, patch


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

    def remove_job(self, job_id: Union[str, int]):
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


def scheduler_tasks() -> Dict[str, str]:
    return {
        "task_one": "tests.contrib.esmerald.test_esmerald",
        "task_two": "tests.contrib.esmerald.test_esmerald",
    }


@scheduler(name="task1", trigger=IntervalTrigger(seconds=1), max_intances=3, is_enabled=True)
def task_one():
    value = 3
    logger.info(value)
    return 3


@scheduler(name="task2", trigger=IntervalTrigger(seconds=3), max_intances=3, is_enabled=True)
def task_two():
    value = 8
    logger.info(value)
    return 8


def test_esmerald_starts_scheduler():
    app = Esmerald(scheduler_class=AsyncIOScheduler, scheduler_tasks=scheduler_tasks())
    assert app.scheduler_tasks == scheduler_tasks()
    assert app.scheduler_class == AsyncIOScheduler


@pytest.fixture
def scheduler(monkeypatch):
    scheduler_class = AsyncIOScheduler
    scheduler_class._configure = MagicMock()
    monkeypatch.setattr("esmerald.applications.Scheduler", Mock(side_effect=EsmeraldScheduler))
    return scheduler_class


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
def test_esmerald_scheduler_configurations(scheduler, global_config):
    app = Esmerald(
        scheduler_class=scheduler,
        scheduler_tasks=scheduler_tasks(),
        scheduler_configurations=global_config,
        enable_scheduler=True,
    )

    app.scheduler_class._configure.assert_called_once_with(
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
        }
    )
