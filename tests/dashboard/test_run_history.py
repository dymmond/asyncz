from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime, timedelta, timezone

import pytest
from lilya.apps import Lilya
from lilya.testclient import TestClient

from asyncz.contrib.dashboard.admin import AsynczAdmin
from asyncz.contrib.dashboard.history import MemoryRunHistoryStorage
from asyncz.contrib.dashboard.logs.storage import MemoryLogStorage
from asyncz.executors.debug import DebugExecutor
from asyncz.schedulers.asyncio import AsyncIOScheduler

DASH_PREFIX = "/dashboard"


def noop() -> str:
    return "ok"


def boom() -> None:
    raise RuntimeError("history boom")


@pytest.fixture()
def scheduler() -> Iterator[AsyncIOScheduler]:
    sched = AsyncIOScheduler(executors={"default": DebugExecutor()})
    sched.start(paused=True)
    try:
        yield sched
    finally:
        sched.shutdown()


@pytest.fixture()
def history_storage() -> MemoryRunHistoryStorage:
    return MemoryRunHistoryStorage(maxlen=100)


@pytest.fixture()
def log_storage() -> MemoryLogStorage:
    return MemoryLogStorage(maxlen=100)


@pytest.fixture()
def client(
    scheduler: AsyncIOScheduler,
    history_storage: MemoryRunHistoryStorage,
    log_storage: MemoryLogStorage,
) -> Iterator[TestClient]:
    app = Lilya()
    admin = AsynczAdmin(
        url_prefix=DASH_PREFIX,
        scheduler=scheduler,
        log_storage=log_storage,
        run_history_storage=history_storage,
    )
    admin.include_in(app)
    with TestClient(app) as c:
        yield c


def _future_run_at() -> datetime:
    return datetime.now(timezone.utc) + timedelta(days=1)


def test_manual_run_records_history_and_correlated_logs(
    client: TestClient,
    scheduler: AsyncIOScheduler,
    history_storage: MemoryRunHistoryStorage,
) -> None:
    scheduler.add_task(
        noop,
        "date",
        id="manual-history",
        name="Manual History",
        run_at=_future_run_at(),
    )

    response = client.post(f"{DASH_PREFIX}/tasks/manual-history/run")

    assert response.status_code == 200
    record = history_storage.latest_for_task("manual-history")
    assert record is not None
    assert record.status == "succeeded"
    assert record.source == "manual"
    assert record.finished_at is not None

    task_page = client.get(f"{DASH_PREFIX}/tasks/")
    assert task_page.status_code == 200
    assert "Last Run" in task_page.text
    assert record.run_id in task_page.text

    history = client.get(f"{DASH_PREFIX}/history/partials/table?task_id=manual-history")
    assert history.status_code == 200
    assert "Manual History" in history.text
    assert "Succeeded" in history.text
    assert "Manual" in history.text
    assert "Inspect Logs" in history.text

    detail = client.get(f"{DASH_PREFIX}/history/{record.run_id}")
    assert detail.status_code == 200
    assert record.run_id in detail.text
    assert "Task run succeeded" in detail.text

    logs = client.get(f"{DASH_PREFIX}/logs/partials/table?run_id={record.run_id}")
    assert logs.status_code == 200
    assert record.run_id in logs.text
    assert "Task run succeeded" in logs.text


def test_failed_manual_run_preserves_exception_detail(
    client: TestClient,
    scheduler: AsyncIOScheduler,
    history_storage: MemoryRunHistoryStorage,
) -> None:
    scheduler.add_task(
        boom,
        "date",
        id="failed-history",
        name="Failed History",
        run_at=_future_run_at(),
    )

    response = client.post(f"{DASH_PREFIX}/tasks/failed-history/run")

    assert response.status_code == 200
    record = history_storage.latest_for_task("failed-history")
    assert record is not None
    assert record.status == "failed"
    assert "history boom" in (record.exception or "")

    detail = client.get(f"{DASH_PREFIX}/history/{record.run_id}")
    assert detail.status_code == 200
    assert "Failed" in detail.text
    assert "RuntimeError" in detail.text
    assert "history boom" in detail.text
