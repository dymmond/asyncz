from typing import Dict

import pytest
from esmerald import Esmerald
from loguru import logger

from asyncz.contrib.esmerald.decorator import scheduler
from asyncz.schedulers import AsyncIOScheduler
from asyncz.stores.mongo import MongoDBStore
from asyncz.triggers import IntervalTrigger


def scheduler_tasks() -> Dict[str, str]:
    return {
        "task_one": "tests.contrib.esmerald.test_esmerald_config",
        "task_two": "tests.contrib.esmerald.test_esmerald_config",
    }


@scheduler(name="task1", trigger=IntervalTrigger(seconds=1), max_instances=3, is_enabled=True)
def task_one():
    value = 3
    logger.info(value)
    return 3


@scheduler(name="task2", trigger=IntervalTrigger(seconds=3), max_instances=3, is_enabled=True)
def task_two():
    value = 8
    logger.info(value)
    return 8


def test_esmerald_with_configs_scheduler():
    scheduler = {
        "asyncz.stores.mongo": {"type": "mongodb"},
        "asyncz.stores.default": {"type": "redis", "database": "0"},
        "asyncz.executors.pool": {
            "max_workers": "20",
            "class": "asyncz.executors.pool:ThreadPoolExecutor",
        },
        "asyncz.executors.default": {"class": "asyncz.executors.asyncio:AsyncIOExecutor"},
        "asyncz.task_defaults.coalesce": "false",
        "asyncz.task_defaults.max_instances": "3",
        "asyncz.task_defaults.timezone": "UTC",
    }

    app = Esmerald(
        scheduler_tasks=scheduler_tasks(),
        scheduler_configurations=scheduler,
        enable_scheduler=True,
    )

    assert app.scheduler_tasks == scheduler_tasks()


@pytest.fixture
def mongodbstore():
    mongodb = pytest.importorskip("asyncz.stores.mongo")
    store = mongodb.MongoDBStore(database="asyncz_unittest")
    store.start(None, "mongodb")
    yield store
    store.client.drop_database(store.collection.database.name)
    store.shutdown()


def test_config():
    global_config = {
        "asyncz.stores.mongo": {"type": "mongodb"},
        "asyncz.stores.default": {"type": "redis", "database": "0"},
        "asyncz.executors.pool": {
            "max_workers": "20",
            "class": "asyncz.executors.pool:ThreadPoolExecutor",
        },
        "asyncz.executors.default": {"class": "asyncz.executors.asyncio:AsyncIOExecutor"},
        "asyncz.task_defaults.coalesce": "false",
        "asyncz.task_defaults.max_instances": "3",
        "asyncz.task_defaults.timezone": "UTC",
    }
    stores = {"mongodb": MongoDBStore()}
    scheduler = AsyncIOScheduler(global_config=global_config, stores=stores)
    scheduler.start()
    scheduler.shutdown()


def test_config_with_esmerald():
    global_config = {
        "asyncz.stores.mongo": {"type": "mongodb"},
        "asyncz.stores.default": {"type": "redis", "database": "0"},
        "asyncz.executors.pool": {
            "max_workers": "20",
            "class": "asyncz.executors.pool:ThreadPoolExecutor",
        },
        "asyncz.executors.default": {"class": "asyncz.executors.asyncio:AsyncIOExecutor"},
        "asyncz.task_defaults.coalesce": "false",
        "asyncz.task_defaults.max_instances": "3",
        "asyncz.task_defaults.timezone": "UTC",
    }
    stores = {"mongodb": MongoDBStore()}
    scheduler = AsyncIOScheduler(global_config=global_config, stores=stores)

    Esmerald(on_startup=[scheduler.start], on_shutdown=[scheduler.shutdown])
