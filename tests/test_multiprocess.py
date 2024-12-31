import contextlib
import os
import time

import pytest

from asyncz.exceptions import ConflictIdError
from asyncz.schedulers.asyncio import AsyncIOScheduler
from asyncz.stores.sqlalchemy import SQLAlchemyStore

dummy_job_called = 0


# better use real fns here for checking all behavior, like retrieving name
def dummy_job():
    global dummy_job_called
    dummy_job_called += 1


def dummy_job2():
    global dummy_job_called
    time.sleep(0.5)
    dummy_job_called += 1


@pytest.fixture(autouse=True, scope="function")
def reset_job_called():
    global dummy_job_called
    yield
    dummy_job_called = 0


@pytest.mark.flaky(reruns=2)
def test_simulated_multiprocess():
    scheduler1 = AsyncIOScheduler(
        stores={"default": SQLAlchemyStore(database="sqlite:///./test_mp.sqlite3")},
        lock_path="/tmp/{store}_asyncz_test.pid",
    )
    scheduler2 = AsyncIOScheduler(
        stores={"default": SQLAlchemyStore(database="sqlite:///./test_mp.sqlite3")},
        lock_path="/tmp/{store}_asyncz_test.pid",
    )

    scheduler1.add_task(dummy_job, id="dummy1")
    scheduler2.add_task(dummy_job, id="dummy1")

    scheduler1.add_task(
        dummy_job,
        id="dummy2",
        replace_existing=True,
    )
    scheduler2.add_task(
        dummy_job,
        id="dummy2",
        replace_existing=True,
    )
    assert len(scheduler1.get_tasks()) == 2
    assert len(scheduler2.get_tasks()) == 2
    assert dummy_job_called == 0
    with scheduler1, scheduler2:
        assert scheduler1.running
        assert scheduler2.running
        time.sleep(2)
        assert dummy_job_called == 2
        scheduler1.add_task(dummy_job2, id="dummy3")
        with pytest.raises(ConflictIdError):
            scheduler2.add_task(dummy_job2, id="dummy3")
        assert dummy_job_called == 2
        # fix CancelledError, by giving scheduler more time to send the tasks to the  pool
        # if the pool is closed, newly submitted tasks are cancelled
        time.sleep(1)
        scheduler1.stores["default"].metadata.drop_all(scheduler1.stores["default"].engine)
    with contextlib.suppress(FileNotFoundError):
        os.remove("./test_mp.sqlite3")

    assert dummy_job_called == 3
