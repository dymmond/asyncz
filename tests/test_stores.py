from datetime import datetime

import pytest
from asyncz.exceptions import ConflictIdError, JobLookupError
from asyncz.stores.memory import MemoryStore


def dummy_job():
    pass


def dummy_job2():
    pass


def dummy_job3():
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
    store.remove_all_jobs()
    store.shutdown()


@pytest.fixture
def mongodbstore():
    mongodb = pytest.importorskip("asyncz.stores.mongo")
    store = mongodb.MongoDBStore(database="asyncz_unittest")
    store.start(None, "mongodb")
    yield store
    store.client.drop_database(store.collection.database.name)
    store.shutdown()


@pytest.fixture(
    params=[
        "memstore",
        "mongodbstore",
        "redistore",
    ],
    ids=["memory", "mongodb", "redis"],
)
def store(request):
    return request.getfixturevalue(request.param)


@pytest.fixture(
    params=[
        "mongodbstore",
        "redistore",
    ],
    ids=["mongodb", "redis"],
)
def persistent_store(request):
    return request.getfixturevalue(request.param)


@pytest.fixture
def create_add_job(timezone, create_job):
    def create(store, fn=dummy_job, run_at=datetime(2999, 1, 1), id=None, paused=False, **kwargs):
        run_at = timezone.localize(run_at)
        job = create_job(fn=fn, trigger="date", trigger_args={"run_at": run_at}, id=id, **kwargs)
        job.next_run_time = None if paused else job.trigger.get_next_trigger_time(None, run_at)
        if store:
            store.add_job(job)
        return job

    return create


def test_add_callable_instance_method_job(store, create_add_job):
    instance = DummyClass()
    initial_job = create_add_job(store, instance.dummy_method, kwargs={"a": 1, "b": 2})
    job = store.lookup_job(initial_job.id)
    assert job.fn(*job.args, **job.kwargs) == 3


def test_add_callable_class_method_job(store, create_add_job):
    initial_job = create_add_job(store, DummyClass.dummy_classmethod, kwargs={"a": 1, "b": 2})
    job = store.lookup_job(initial_job.id)
    assert job.fn(*job.args, **job.kwargs) == 3


def test_add_textual_instance_method_job(store, create_add_job):
    initial_job = create_add_job(
        store, "tests.test_stores:dummy_instance.dummy_method", kwargs={"a": 1, "b": 2}
    )
    job = store.lookup_job(initial_job.id)
    assert job.fn(*job.args, **job.kwargs) == 3


def test_add_textual_class_method_job(store, create_add_job):
    initial_job = create_add_job(
        store, "tests.test_stores:DummyClass.dummy_classmethod", kwargs={"a": 1, "b": 2}
    )
    job = store.lookup_job(initial_job.id)
    assert job.fn(*job.args, **job.kwargs) == 3


def test_lookup_job(store, create_add_job):
    initial_job = create_add_job(store)
    job = store.lookup_job(initial_job.id)
    assert job == initial_job


def test_lookup_nonexistent_job(store):
    assert store.lookup_job("foo") is None


def test_get_all_jobs(store, create_add_job):
    job1 = create_add_job(store, dummy_job, datetime(2025, 5, 3))
    job2 = create_add_job(store, dummy_job2, datetime(2022, 8, 14))
    job3 = create_add_job(store, dummy_job2, datetime(2022, 7, 11), paused=True)
    jobs = store.get_all_jobs()
    assert jobs == [job2, job1, job3]


def test_get_pending_jobs(store, create_add_job, timezone):
    create_add_job(store, dummy_job, datetime(2022, 5, 3))
    job2 = create_add_job(store, dummy_job2, datetime(2020, 2, 26))
    job3 = create_add_job(store, dummy_job3, datetime(2019, 8, 14))
    create_add_job(store, dummy_job3, datetime(2019, 7, 11), paused=True)
    jobs = store.get_due_jobs(timezone.localize(datetime(2020, 2, 27)))
    assert jobs == [job3, job2]

    jobs = store.get_due_jobs(timezone.localize(datetime(2019, 8, 13)))
    assert jobs == []


def test_get_pending_jobs_subsecond_difference(store, create_add_job, timezone):
    job1 = create_add_job(store, dummy_job, datetime(2022, 7, 7, 0, 0, 0, 401))
    job2 = create_add_job(store, dummy_job2, datetime(2022, 7, 7, 0, 0, 0, 402))
    job3 = create_add_job(store, dummy_job3, datetime(2022, 7, 7, 0, 0, 0, 400))
    jobs = store.get_due_jobs(timezone.localize(datetime(2022, 7, 7, 1)))
    assert jobs == [job3, job1, job2]


def test_get_next_run_time(store, create_add_job, timezone):
    create_add_job(store, dummy_job, datetime(2022, 5, 3))
    create_add_job(store, dummy_job2, datetime(2020, 2, 26))
    create_add_job(store, dummy_job3, datetime(2019, 8, 14))
    create_add_job(store, dummy_job3, datetime(2019, 7, 11), paused=True)
    assert store.get_next_run_time() == timezone.localize(datetime(2019, 8, 14))


def test_add_job_conflicting_id(store, create_add_job):
    create_add_job(store, dummy_job, datetime(2022, 5, 3), id="blah")
    pytest.raises(
        ConflictIdError, create_add_job, store, dummy_job2, datetime(2020, 2, 26), id="blah"
    )


def test_update_job(store, create_add_job, timezone):
    job1 = create_add_job(store, dummy_job, datetime(2022, 5, 3))
    job2 = create_add_job(store, dummy_job2, datetime(2020, 2, 26))
    replacement = create_add_job(
        None, dummy_job, datetime(2022, 5, 4), id=job1.id, max_instances=6
    )
    assert replacement.max_instances == 6
    store.update_job(replacement)

    jobs = store.get_all_jobs()
    assert len(jobs) == 2
    assert jobs[0].id == job2.id
    assert jobs[1].id == job1.id
    assert jobs[1].next_run_time == timezone.localize(datetime(2022, 5, 4))
    assert jobs[1].max_instances == 6


@pytest.mark.parametrize("next_run_time", [datetime(2019, 8, 13), None], ids=["earlier", "null"])
def test_update_job_next_runtime(store, create_add_job, next_run_time, timezone):
    job1 = create_add_job(store, dummy_job, datetime(2022, 5, 3))
    create_add_job(store, dummy_job2, datetime(2020, 2, 26))
    job3 = create_add_job(store, dummy_job3, datetime(2019, 8, 14))
    job1.next_run_time = timezone.localize(next_run_time) if next_run_time else None
    store.update_job(job1)

    if next_run_time:
        assert store.get_next_run_time() == job1.next_run_time
    else:
        assert store.get_next_run_time() == job3.next_run_time


@pytest.mark.parametrize("next_run_time", [datetime(2019, 8, 13), None], ids=["earlier", "null"])
@pytest.mark.parametrize("index", [0, 1, 2], ids=["first", "middle", "last"])
def test_update_job_clear_next_runtime_when_run_times_are_initially_the_same(
    store, create_add_job, next_run_time, timezone, index
):
    jobs = [create_add_job(store, dummy_job, datetime(2020, 2, 26), "job%d" % i) for i in range(3)]
    jobs[index].next_run_time = timezone.localize(next_run_time) if next_run_time else None
    store.update_job(jobs[index])
    due_date = timezone.localize(datetime(2020, 2, 27))
    due_jobs = store.get_due_jobs(due_date)

    assert len(due_jobs) == (3 if next_run_time else 2)
    due_job_ids = [job.id for job in due_jobs]
    if next_run_time:
        if index == 0:
            assert due_job_ids == ["job0", "job1", "job2"]
        elif index == 1:
            assert due_job_ids == ["job1", "job0", "job2"]
        else:
            assert due_job_ids == ["job2", "job0", "job1"]
    else:
        if index == 0:
            assert due_job_ids == ["job1", "job2"]
        elif index == 1:
            assert due_job_ids == ["job0", "job2"]
        else:
            assert due_job_ids == ["job0", "job1"]


def test_update_job_nonexistent_job(store, create_add_job):
    job = create_add_job(None, dummy_job, datetime(2022, 5, 3))
    pytest.raises(JobLookupError, store.update_job, job)


def test_one_job_fails_to_load(persistent_store, create_add_job, monkeypatch, timezone):
    job1 = create_add_job(persistent_store, dummy_job, datetime(2022, 5, 3))
    job2 = create_add_job(persistent_store, dummy_job2, datetime(2020, 2, 26))
    create_add_job(persistent_store, dummy_job3, datetime(2019, 8, 14))

    monkeypatch.delitem(globals(), "dummy_job3")

    jobs = persistent_store.get_all_jobs()
    assert jobs == [job2, job1]

    assert persistent_store.get_next_run_time() == timezone.localize(datetime(2020, 2, 26))


def test_remove_job(store, create_add_job):
    job1 = create_add_job(store, dummy_job, datetime(2022, 5, 3))
    job2 = create_add_job(store, dummy_job2, datetime(2020, 2, 26))

    store.remove_job(job1.id)
    jobs = store.get_all_jobs()
    assert jobs == [job2]

    store.remove_job(job2.id)
    jobs = store.get_all_jobs()
    assert jobs == []


def test_remove_nonexistent_job(store):
    pytest.raises(JobLookupError, store.remove_job, "blah")


def test_remove_all_jobs(store, create_add_job):
    create_add_job(store, dummy_job, datetime(2022, 5, 3))
    create_add_job(store, dummy_job2, datetime(2020, 2, 26))

    store.remove_all_jobs()
    jobs = store.get_all_jobs()
    assert jobs == []


def test_repr_memstore(memstore):
    assert repr(memstore) == "<MemoryStore>"


def xtest_repr_mongodbstore(mongodbstore):
    assert repr(mongodbstore).startswith("<MongoDBStore (client=MongoClient(")


def test_repr_redisjobstore(redistore):
    assert repr(redistore) == "<RedisStore>"


def test_memstore_close(memstore, create_add_job):
    create_add_job(memstore, dummy_job, datetime(2022, 5, 3))
    memstore.shutdown()
    assert not memstore.get_all_jobs()


def test_mongodb_client_ref():
    global mongodb_client
    mongodb = pytest.importorskip("asyncz.stores.mongo")
    mongodb_client = mongodb.MongoClient()
    try:
        mongodb.MongoDBStore(client="%s:mongodb_client" % __name__)
    finally:
        mongodb_client.close()
        del mongodb_client


def test_mongodb_null_database():
    mongodb = pytest.importorskip("asyncz.stores.mongo")
    exc = pytest.raises(ValueError, mongodb.MongoDBStore, database="")
    assert "database" in str(exc.value)
