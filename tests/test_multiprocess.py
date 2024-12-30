import datetime
import time

from asyncz.schedulers.asyncio import AsyncIOScheduler
from asyncz.stores.sqlalchemy import SQLAlchemyStore
from asyncz.triggers import DateTrigger

dummy_job_called = 0


# better use real fns here for checking all behavior, like retrieving name
def dummy_job():
    global dummy_job_called
    dummy_job_called += 1


def test_simulated_multiprocess():
    scheduler1 = AsyncIOScheduler(
        stores={"default": SQLAlchemyStore(database="sqlite:///./test_suite.sqlite3")},
        pid_path="/tmp/{store}_asyncz_test.pid",
    )
    scheduler2 = AsyncIOScheduler(
        stores={"default": SQLAlchemyStore(database="sqlite:///./test_suite.sqlite3")},
        pid_path="/tmp/{store}_asyncz_test.pid",
    )
    now = datetime.datetime.now(datetime.UTC)

    scheduler1.add_task(dummy_job, id="dummy1")
    scheduler2.add_task(dummy_job, id="dummy1")

    scheduler1.add_task(
        dummy_job,
        id="dummy2",
        replace_existing=True,
        trigger=DateTrigger(now + datetime.timedelta(seconds=1)),
    )
    scheduler2.add_task(
        dummy_job,
        id="dummy2",
        replace_existing=True,
        trigger=DateTrigger(now + datetime.timedelta(seconds=1)),
    )
    assert len(scheduler1.get_tasks()) == 2
    assert len(scheduler2.get_tasks()) == 2
    assert dummy_job_called == 0
    with scheduler1, scheduler2:
        assert scheduler1.running
        assert scheduler2.running
        time.sleep(2)
        assert dummy_job_called == 2
        scheduler1.add_task(dummy_job, id="dummy3", replace_existing=True)
        time.sleep(0.1)
        scheduler2.add_task(dummy_job, id="dummy3")
        # fix CancelledError, by giving scheduler more time to send the tasks to the  pool
        # if the pool is closed, newly submitted tasks are cancelled
        time.sleep(1)

    assert dummy_job_called == 4
