from datetime import datetime
from typing import Any, Dict, List, Optional, Union
from unittest.mock import MagicMock

import pytest

from asyncz._mapping import AsynczObjectMapping
from asyncz.executors.base import BaseExecutor
from asyncz.stores.base import BaseStore
from asyncz.tasks.types import TaskType
from asyncz.triggers.base import BaseTrigger


class DummyTrigger(BaseTrigger):
    def __init__(self, **args):
        super().__init__(**args)
        self.args = args

    def get_next_trigger_time(
        self, previous_time: datetime, now: Optional[datetime] = None
    ) -> Union[datetime, None]: ...


class DummyExecutor(BaseExecutor):
    def __init__(self, **args):
        super().__init__(**args)
        self.args = args
        self.start = MagicMock()
        self.shutdown = MagicMock()
        self.send_task = MagicMock()

    def do_send_task(self, task: "TaskType", run_times: List[datetime]) -> Any:
        return super().do_send_task(task, run_times)


class DummyStore(BaseStore):
    def __init__(self, **args):
        super().__init__(**args)
        self.args = args
        self.start = MagicMock()
        self.shutdown = MagicMock()

    def get_due_tasks(self, now: datetime) -> List["TaskType"]: ...

    def lookup_task(self, task_id: str) -> "TaskType": ...

    def delete_task(self, task_id: str): ...

    def remove_all_tasks(self): ...

    def get_next_run_time(self) -> Optional[datetime]: ...

    def get_all_tasks(self) -> List["TaskType"]: ...

    def add_task(self, task: "TaskType"): ...

    def update_task(self, task: "TaskType"): ...


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

    assert trigger in mapping.triggers


@pytest.mark.parametrize("store", ["memory", "mongodb", "redis"])
def test_default_mapping_stores(store):
    mapping = AsynczObjectMapping()

    assert store in mapping.stores


@pytest.mark.parametrize("executor", ["debug", "threadpool", "processpool", "asyncio"])
def test_default_mapping_executors(executor):
    mapping = AsynczObjectMapping()

    assert executor in mapping.executors


@pytest.mark.parametrize("trigger", ["date", "cron", "or", "and", "interval", "dummy"])
def test_custom_mapping_triggers(trigger):
    mapping = DummyMapping()

    assert trigger in mapping.triggers


@pytest.mark.parametrize("store", ["memory", "mongodb", "redis", "dummy"])
def test_custom_mapping_stores(store):
    mapping = DummyMapping()

    assert store in mapping.stores


@pytest.mark.parametrize("executor", ["debug", "threadpool", "processpool", "asyncio", "dummy"])
def test_custom_mapping_executors(executor):
    mapping = DummyMapping()

    assert executor in mapping.executors
