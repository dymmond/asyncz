import os
import tempfile
import time
from datetime import datetime

import pytest
from sqlalchemy.pool import StaticPool

from asyncz.exceptions import ConflictIdError, TaskLookupError
from asyncz.schedulers import AsyncIOScheduler
from asyncz.stores.file import FileStore
from asyncz.stores.memory import MemoryStore
from asyncz.tasks import Task


def dummy_task():
    pass


def dummy_task2():
    pass


def dummy_task3():
    pass


class DummyClass:
    def dummy_method(self, a, b):
        return a + b

    @classmethod
    def dummy_classmethod(cls, a, b):
        return a + b


dummy_instance = DummyClass()


@pytest.fixture
def memstore():
    yield MemoryStore()


@pytest.fixture
def redistore():
    redis = pytest.importorskip("asyncz.stores.redis")
    store = redis.RedisStore()
    store.start(None, "redis")
    yield store
    store.remove_all_tasks()
    store.shutdown()


@pytest.fixture
def mongodbstore():
    mongodb = pytest.importorskip("asyncz.stores.mongo")
    store = mongodb.MongoDBStore(database="asyncz_unittest")
    store.start(None, "mongodb")
    yield store
    store.client.drop_database(store.collection.database.name)
    store.shutdown()


@pytest.fixture
def sqlalchemystore():
    sqlalchemy = pytest.importorskip("asyncz.stores.sqlalchemy")
    store = sqlalchemy.SQLAlchemyStore(database="sqlite:///./test_suite.sqlite3")
    store.start(None, "sqlalchemy")
    yield store
    # execute shutdown
    store.metadata.drop_all(store.engine)
    store.shutdown()


@pytest.fixture
def filestore(tmpdir):
    store = FileStore(directory=tmpdir)
    store.start(None, "file")
    yield store
    store.shutdown()


@pytest.fixture(
    params=[
        "memstore",
        "filestore",
        "mongodbstore",
        "sqlalchemystore",
        "redistore",
    ],
    ids=["memory", "file", "mongodb", "sqlalchemy", "redis"],
)
def store(request):
    return request.getfixturevalue(request.param)


@pytest.fixture(
    params=[
        "filestore",
        "mongodbstore",
        "sqlalchemystore",
        "redistore",
    ],
    ids=["file", "mongodb", "sqlalchemy", "redis"],
)
def persistent_store(request):
    return request.getfixturevalue(request.param)


@pytest.fixture
def create_add_task(timezone, create_task):
    def create(
        store,
        fn=dummy_task,
        run_at=datetime(2999, 1, 1),
        id=None,
        paused=False,
        **kwargs,
    ):
        run_at = timezone.localize(run_at)
        task = create_task(fn=fn, trigger="date", trigger_args={"run_at": run_at}, id=id, **kwargs)
        task.next_run_time = (
            None if paused else task.trigger.get_next_trigger_time(timezone, None, run_at)
        )
        if store:
            store.start(task.scheduler, "default")
            store.add_task(task)
        return task

    return create


def test_add_callable_instance_method_task(store, create_add_task):
    instance = DummyClass()
    initial_task = create_add_task(store, instance.dummy_method, kwargs={"a": 1, "b": 2})
    task = store.lookup_task(initial_task.id)
    assert task.fn(*task.args, **task.kwargs) == 3


def test_add_callable_class_method_task(store, create_add_task):
    initial_task = create_add_task(store, DummyClass.dummy_classmethod, kwargs={"a": 1, "b": 2})
    task = store.lookup_task(initial_task.id)
    assert task.fn(*task.args, **task.kwargs) == 3


def test_add_textual_instance_method_task(store, create_add_task):
    initial_task = create_add_task(
        store, "tests.test_stores:dummy_instance.dummy_method", kwargs={"a": 1, "b": 2}
    )
    task = store.lookup_task(initial_task.id)
    assert task.fn(*task.args, **task.kwargs) == 3


def test_add_textual_class_method_task(store, create_add_task):
    initial_task = create_add_task(
        store, "tests.test_stores:DummyClass.dummy_classmethod", kwargs={"a": 1, "b": 2}
    )
    task = store.lookup_task(initial_task.id)
    assert task.fn(*task.args, **task.kwargs) == 3


def test_lookup_task(store, create_add_task):
    initial_task = create_add_task(store)
    task = store.lookup_task(initial_task.id)
    assert task == initial_task


def test_lookup_nonexistent_task(store):
    assert store.lookup_task("foo") is None


def test_get_all_tasks(store, create_add_task):
    task1 = create_add_task(store, dummy_task, datetime(2025, 5, 3))
    task2 = create_add_task(store, dummy_task2, datetime(2022, 8, 14))
    task3 = create_add_task(store, dummy_task2, datetime(2022, 7, 11), paused=True)
    tasks = store.get_all_tasks()
    assert tasks == [task2, task1, task3]


def test_get_pending_tasks(store, create_add_task, timezone):
    create_add_task(store, dummy_task, datetime(2022, 5, 3))
    task2 = create_add_task(store, dummy_task2, datetime(2020, 2, 26))
    task3 = create_add_task(store, dummy_task3, datetime(2019, 8, 14))
    create_add_task(store, dummy_task3, datetime(2019, 7, 11), paused=True)
    tasks = store.get_due_tasks(timezone.localize(datetime(2020, 2, 27)))
    assert tasks == [task3, task2]

    tasks = store.get_due_tasks(timezone.localize(datetime(2019, 8, 13)))
    assert tasks == []


def test_get_pending_tasks_subsecond_difference(store, create_add_task, timezone):
    task1 = create_add_task(store, dummy_task, datetime(2022, 7, 7, 0, 0, 0, 401))
    task2 = create_add_task(store, dummy_task2, datetime(2022, 7, 7, 0, 0, 0, 402))
    task3 = create_add_task(store, dummy_task3, datetime(2022, 7, 7, 0, 0, 0, 400))
    tasks = store.get_due_tasks(timezone.localize(datetime(2022, 7, 7, 1)))
    assert tasks == [task3, task1, task2]


def test_get_next_run_time(store, create_add_task, timezone):
    create_add_task(store, dummy_task, datetime(2022, 5, 3))
    create_add_task(store, dummy_task2, datetime(2020, 2, 26))
    create_add_task(store, dummy_task3, datetime(2019, 8, 14))
    create_add_task(store, dummy_task3, datetime(2019, 7, 11), paused=True)
    assert store.get_next_run_time() == timezone.localize(datetime(2019, 8, 14))


def test_add_task_conflicting_id(store, create_add_task):
    create_add_task(store, dummy_task, datetime(2022, 5, 3), id="blah")
    pytest.raises(
        ConflictIdError,
        create_add_task,
        store,
        dummy_task2,
        datetime(2020, 2, 26),
        id="blah",
    )


def test_update_task(store, create_add_task, timezone):
    task1 = create_add_task(store, dummy_task, datetime(2022, 5, 3))
    task2 = create_add_task(store, dummy_task2, datetime(2020, 2, 26))
    replacement = create_add_task(
        None, dummy_task, datetime(2022, 5, 4), id=task1.id, max_instances=6
    )
    assert replacement.max_instances == 6
    try:
        store.update_task(replacement)
    except TaskLookupError:
        store.add_task(replacement)

    tasks = store.get_all_tasks()
    assert len(tasks) == 2
    assert tasks[0].id == task2.id
    assert tasks[1].id == task1.id
    assert tasks[1].next_run_time == timezone.localize(datetime(2022, 5, 4))
    assert tasks[1].max_instances == 6


@pytest.mark.parametrize("next_run_time", [datetime(2019, 8, 13), None], ids=["earlier", "null"])
def test_update_task_next_runtime(store, create_add_task, next_run_time, timezone):
    task1 = create_add_task(store, dummy_task, datetime(2022, 5, 3))
    create_add_task(store, dummy_task2, datetime(2020, 2, 26))
    task3 = create_add_task(store, dummy_task3, datetime(2019, 8, 14))
    task1.next_run_time = timezone.localize(next_run_time) if next_run_time else None
    store.update_task(task1)

    if next_run_time:
        assert store.get_next_run_time() == task1.next_run_time
    else:
        assert store.get_next_run_time() == task3.next_run_time


@pytest.mark.parametrize("next_run_time", [datetime(2019, 8, 13), None], ids=["earlier", "null"])
@pytest.mark.parametrize("index", [0, 1, 2], ids=["first", "middle", "last"])
def test_update_task_clear_next_runtime_when_run_times_are_initially_the_same(
    store, create_add_task, next_run_time, timezone, index
):
    if isinstance(store, FileStore) and os.environ.get("CI") == "true":
        pytest.skip("CI server filesystem not suitable for this test with FileStore.")
    tasks = [
        create_add_task(store, dummy_task, datetime(2020, 2, 26), f"task{i}") for i in range(3)
    ]
    tasks[index].next_run_time = timezone.localize(next_run_time) if next_run_time else None
    store.update_task(tasks[index])
    due_date = timezone.localize(datetime(2020, 2, 27))
    due_tasks = store.get_due_tasks(due_date)

    assert len(due_tasks) == (3 if next_run_time else 2)
    due_task_ids = [task.id for task in due_tasks]
    if next_run_time:
        if index == 0:
            assert due_task_ids == ["task0", "task1", "task2"]
        elif index == 1:
            assert due_task_ids == ["task1", "task0", "task2"]
        else:
            assert due_task_ids == ["task2", "task0", "task1"]
    else:
        if index == 0:
            assert due_task_ids == ["task1", "task2"]
        elif index == 1:
            assert due_task_ids == ["task0", "task2"]
        else:
            assert due_task_ids == ["task0", "task1"]


def xtest_update_task_nonexistent_task(store, create_add_task):
    task = create_add_task(None, dummy_task, datetime(2022, 5, 3))
    pytest.raises(TaskLookupError, store.update_task, task)


def test_one_task_fails_to_load(persistent_store, create_add_task, monkeypatch, timezone):
    task1 = create_add_task(persistent_store, dummy_task, datetime(2022, 5, 3))
    task2 = create_add_task(persistent_store, dummy_task2, datetime(2020, 2, 26))
    create_add_task(persistent_store, dummy_task3, datetime(2019, 8, 14))

    monkeypatch.delitem(globals(), "dummy_task3")

    tasks = persistent_store.get_all_tasks()
    assert tasks == [task2, task1]

    assert persistent_store.get_next_run_time() == timezone.localize(datetime(2020, 2, 26))


def test_remove_task(store, create_add_task):
    task1 = create_add_task(store, dummy_task, datetime(2022, 5, 3))
    task2 = create_add_task(store, dummy_task2, datetime(2020, 2, 26))

    store.delete_task(task1.id)
    tasks = store.get_all_tasks()
    assert tasks == [task2]

    store.delete_task(task2.id)
    tasks = store.get_all_tasks()
    assert tasks == []


def test_remove_nonexistent_task(store):
    pytest.raises(TaskLookupError, store.delete_task, "blah")


def test_remove_all_tasks(store, create_add_task):
    create_add_task(store, dummy_task, datetime(2022, 5, 3))
    create_add_task(store, dummy_task2, datetime(2020, 2, 26))

    store.remove_all_tasks()
    tasks = store.get_all_tasks()
    assert tasks == []


def test_repr_memstore(memstore):
    assert repr(memstore) == "<MemoryStore>"


def test_repr_filestore(filestore):
    assert repr(filestore).startswith("<FileStore ")


def test_repr_sqlalchemystore(sqlalchemystore):
    assert repr(sqlalchemystore) == "<SQLAlchemyStore (database=sqlite:///./test_suite.sqlite3)>"


def test_repr_mongodbstore(mongodbstore):
    assert repr(mongodbstore).startswith("<MongoDBStore (client=MongoClient(")


def test_repr_redistaskstore(redistore):
    assert repr(redistore) == "<RedisStore>"


@pytest.mark.parametrize(
    "task_id",
    ["../foo", ".foo", "\\foo", "/foo"],
)
def test_file_store_dangerous_ids(task_id, filestore):
    with pytest.raises(RuntimeError):
        filestore.lookup_task(task_id)
    with pytest.raises(RuntimeError):
        filestore.delete_task(task_id)
    with pytest.raises(RuntimeError):
        filestore.add_task(Task(lambda: None, id=task_id))
    with pytest.raises(RuntimeError):
        filestore.update_task(Task(lambda: None, id=task_id))


def test_memstore_close(memstore, create_add_task):
    create_add_task(memstore, dummy_task, datetime(2022, 5, 3))
    memstore.shutdown()
    assert not memstore.get_all_tasks()


def test_mongodb_client_ref():
    global mongodb_client
    mongodb = pytest.importorskip("asyncz.stores.mongo")
    mongodb_client = mongodb.MongoClient()
    try:
        mongodb.MongoDBStore(client=f"{__name__}:mongodb_client")
    finally:
        mongodb_client.close()
        del mongodb_client


def test_mongodb_null_database():
    mongodb = pytest.importorskip("asyncz.stores.mongo")
    exc = pytest.raises(ValueError, mongodb.MongoDBStore, database="")
    assert "database" in str(exc.value)


@pytest.mark.parametrize(
    "param",
    [
        {
            "type": "sqlalchemy",
            "database": "sqlite:///:memory:",
            "poolclass": StaticPool,
        },
        {"type": "memory"},
        {"type": "file", "directory": tempfile.mkdtemp(), "cleanup_directory": True},
    ],
    ids=["sqlalchemy", "memory", "file"],
)
def test_store_as_type(param):
    scheduler = AsyncIOScheduler(stores={"default": param})
    if param["type"] != "sqlalchemy":
        scheduler.add_task(dummy_task)
        assert len(scheduler.get_tasks()) == 1
    scheduler.start()
    time.sleep(0.1)
    if param["type"] != "sqlalchemy":
        assert len(scheduler.get_tasks()) == 0
    scheduler.shutdown()
    if param["type"] == "file":
        time.sleep(0.1)
        assert not os.path.exists(param["directory"])
