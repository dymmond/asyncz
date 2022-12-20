from datetime import datetime
from typing import Any, Dict, List, Optional, Union

import pytest
from asyncz._mapping import AsynczObjectMapping
from asyncz.executors.base import BaseExecutor
from asyncz.jobs.types import JobType
from asyncz.stores.base import BaseStore
from asyncz.triggers.base import BaseTrigger
from mock import MagicMock


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


class DummyMapping(AsynczObjectMapping):
    @property
    def triggers(self) -> Dict[str, str]:
        _triggers = super().triggers
        triggers = {"dummy": "tests.test_mapping:DummyTrigger"}
        _triggers.update(triggers)
        return _triggers

    @property
    def executors(self) -> Dict[str, str]:
        _executors = super().executors
        executors = {"dummy": "tests.test_mapping:DummyExecutor"}
        _executors.update(executors)
        return _executors

    @property
    def stores(self) -> Dict[str, str]:
        _stores = super().stores
        stores = {"dummy": " tests.test_mapping:DummyStore"}
        _stores.update(stores)
        return _stores


@pytest.mark.parametrize("trigger", ["date", "cron", "or", "and", "interval"])
def test_default_mapping_triggers(trigger):
    mapping = AsynczObjectMapping()

    assert trigger in mapping.triggers.keys()


@pytest.mark.parametrize("store", ["memory", "mongo", "redis"])
def test_default_mapping_stores(store):
    mapping = AsynczObjectMapping()

    assert store in mapping.stores.keys()


@pytest.mark.parametrize("executor", ["debug", "threadpool", "processpool", "asyncio"])
def test_default_mapping_executors(executor):
    mapping = AsynczObjectMapping()

    assert executor in mapping.executors.keys()


@pytest.mark.parametrize("trigger", ["date", "cron", "or", "and", "interval", "dummy"])
def test_custom_mapping_triggers(trigger):

    mapping = DummyMapping()

    assert trigger in mapping.triggers.keys()


@pytest.mark.parametrize("store", ["memory", "mongo", "redis", "dummy"])
def test_custom_mapping_stores(store):
    mapping = DummyMapping()

    assert store in mapping.stores.keys()


@pytest.mark.parametrize("executor", ["debug", "threadpool", "processpool", "asyncio", "dummy"])
def test_custom_mapping_executors(executor):
    mapping = DummyMapping()

    assert executor in mapping.executors.keys()
