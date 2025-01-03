import os
import tempfile
import time

import pytest

from asyncz.exceptions import ConflictIdError
from asyncz.schedulers.asyncio import AsyncIOScheduler

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
@pytest.mark.parametrize(
    "param",
    [
        {
            "type": "sqlalchemy",
            "database": "sqlite:///./test_mp.sqlite3",
        },
        {"type": "file", "directory": tempfile.mkdtemp(), "cleanup_directory": True},
    ],
    ids=["sqlalchemy", "file"],
)
def test_simulated_multiprocess(tmpdir, param):
    scheduler1 = AsyncIOScheduler(
        stores={"default": param},
        lock_path=f"/{tmpdir}/{{store}}_asyncz_test.lock",
    )
    scheduler2 = AsyncIOScheduler(
        stores={"default": param},
        lock_path=f"/{tmpdir}/{{store}}_asyncz_test.lock",
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
        if param["type"] == "sqlalchemy":
            scheduler1.stores["default"].metadata.drop_all(scheduler1.stores["default"].engine)
    if param["type"] == "sqlalchemy":
        os.remove("./test_mp.sqlite3")
    else:
        time.sleep(0.1)
        assert not os.path.exists(param["directory"])

    assert dummy_job_called == 3
