from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from lilya.apps import Lilya
from lilya.routing import Include
from lilya.testclient import TestClient

from asyncz.contrib.dashboard import (
    RemoteSchedulerClient,
    RemoteSchedulerError,
    create_remote_scheduler_app,
)
from asyncz.contrib.dashboard.admin import AsynczAdmin
from asyncz.contrib.dashboard.audit import MemoryAuditTrailStorage
from asyncz.contrib.dashboard.history import MemoryRunHistoryStorage
from asyncz.contrib.dashboard.logs.storage import MemoryLogStorage
from asyncz.schedulers.asyncio import AsyncIOScheduler

DASH_PREFIX = "/dashboard"
REMOTE_PREFIX = "/asyncz-remote"
REMOTE_TOKEN = "test-remote-token"


@pytest.fixture()
def worker_scheduler() -> Iterator[AsyncIOScheduler]:
    """
    Provide a scheduler that represents the separate worker process.

    The dashboard tests deliberately avoid passing this object to `AsynczAdmin`
    so all dashboard communication must cross the remote client boundary.
    """

    scheduler = AsyncIOScheduler()
    scheduler.start()
    try:
        yield scheduler
    finally:
        scheduler.shutdown()


def _remote_transport(worker_client: TestClient):
    """
    Build a transport adapter over Lilya's test client.

    Production users call the same remote app over HTTP. The test adapter keeps
    the same method, path, payload, header, and query contract without opening a
    network port.
    """

    def transport(
        method: str,
        path: str,
        payload: dict[str, Any] | None,
        headers: dict[str, str],
        query: dict[str, Any] | None,
    ) -> tuple[int, dict[str, Any]]:
        """
        Forward one remote scheduler request into the worker ASGI app.

        The return shape matches `RemoteSchedulerClient`'s injectable transport
        protocol exactly.
        """

        response = worker_client.request(
            method,
            f"{REMOTE_PREFIX}{path}",
            json=payload,
            headers=headers,
            params=query or {},
        )
        return response.status_code, response.json()

    return transport


@pytest.fixture()
def remote_scheduler(worker_scheduler: AsyncIOScheduler) -> Iterator[RemoteSchedulerClient]:
    """
    Provide a dashboard-side scheduler proxy backed by the worker app.

    This fixture is the in-test equivalent of pointing the app container at a
    worker container URL such as `http://worker:8000/asyncz-remote`.
    """

    worker_app = Lilya(
        routes=[
            Include(
                REMOTE_PREFIX,
                app=create_remote_scheduler_app(worker_scheduler, token=REMOTE_TOKEN),
            )
        ]
    )
    with TestClient(worker_app) as worker_client:
        yield RemoteSchedulerClient(
            token=REMOTE_TOKEN,
            transport=_remote_transport(worker_client),
        )


@pytest.fixture()
def remote_dashboard_client(
    remote_scheduler: RemoteSchedulerClient,
) -> Iterator[TestClient]:
    """
    Provide an app-side dashboard that has no live scheduler object.

    The admin instance receives only `RemoteSchedulerClient`, matching a
    production app process that serves the UI while scheduler execution is
    enabled in a worker process.
    """

    app = Lilya()
    admin = AsynczAdmin(
        scheduler=remote_scheduler,
        log_storage=MemoryLogStorage(maxlen=1_000),
        run_history_storage=MemoryRunHistoryStorage(maxlen=1_000),
        audit_storage=MemoryAuditTrailStorage(maxlen=1_000),
    )
    admin.include_in(app)
    with TestClient(app) as client:
        yield client


def test_remote_client_controls_worker_scheduler(
    worker_scheduler: AsyncIOScheduler,
    remote_scheduler: RemoteSchedulerClient,
) -> None:
    """
    Prove the remote client performs real scheduler reads and writes.

    The task is created, previewed, paused, resumed, run, and deleted through
    `RemoteSchedulerClient`; assertions inspect the worker scheduler directly.
    """

    task = remote_scheduler.add_task(
        "tests.fixtures:noop",
        trigger="interval",
        seconds=60,
        id="remote-direct",
        name="remote direct",
        args=["payload"],
        kwargs={"source": "remote"},
        replace_existing=True,
    )

    assert task.id == "remote-direct"
    assert task.args == ("payload",)
    assert task.kwargs == {"source": "remote"}
    assert worker_scheduler.get_task_info("remote-direct") is not None

    preview = remote_scheduler.preview_task_runs("remote-direct", count=2)
    assert preview is not None
    assert preview.task.id == "remote-direct"
    assert preview.requested_count == 2

    remote_scheduler.pause_task("remote-direct")
    paused = worker_scheduler.get_task_info("remote-direct")
    assert paused is not None
    assert paused.paused is True

    remote_scheduler.resume_task("remote-direct")
    resumed = worker_scheduler.get_task_info("remote-direct")
    assert resumed is not None
    assert resumed.paused is False

    assert remote_scheduler.run_task("remote-direct", remove_finished=False) is not None

    remote_scheduler.delete_task("remote-direct")
    assert worker_scheduler.get_task_info("remote-direct") is None


def test_remote_dashboard_serves_admin_without_local_scheduler(
    worker_scheduler: AsyncIOScheduler,
    remote_dashboard_client: TestClient,
) -> None:
    """
    Prove the dashboard can run in an app process without a scheduler.

    Task creation and row actions are sent to the worker control app. The worker
    scheduler remains the only runtime object that owns task state.
    """

    payload = {
        "callable_path": "tests.fixtures:noop",
        "name": "remote-created",
        "store": "default",
        "trigger_type": "interval",
        "trigger_value": "5s",
        "args": "",
        "kwargs": "",
    }

    created = remote_dashboard_client.post(f"{DASH_PREFIX}/tasks/create", data=payload)
    assert created.status_code == 200
    assert "remote-created" in created.text

    infos = worker_scheduler.get_task_infos(q="remote-created")
    assert len(infos) == 1
    task_id = infos[0].id
    assert task_id is not None

    page = remote_dashboard_client.get(f"{DASH_PREFIX}/tasks/")
    assert page.status_code == 200
    assert "remote-created" in page.text

    paused = remote_dashboard_client.post(f"{DASH_PREFIX}/tasks/{task_id}/pause")
    assert paused.status_code == 200
    paused_info = worker_scheduler.get_task_info(task_id)
    assert paused_info is not None
    assert paused_info.paused is True

    resumed = remote_dashboard_client.post(f"{DASH_PREFIX}/tasks/{task_id}/resume")
    assert resumed.status_code == 200
    resumed_info = worker_scheduler.get_task_info(task_id)
    assert resumed_info is not None
    assert resumed_info.paused is False

    removed = remote_dashboard_client.post(f"{DASH_PREFIX}/tasks/{task_id}/remove")
    assert removed.status_code == 200
    assert worker_scheduler.get_task_info(task_id) is None


def test_remote_scheduler_rejects_invalid_token(
    worker_scheduler: AsyncIOScheduler,
) -> None:
    """
    Prove the worker control plane enforces its optional shared token.

    The token is intentionally small because deployment authentication still
    belongs to the private network, proxy, or service platform around it.
    """

    worker_app = Lilya(
        routes=[
            Include(
                REMOTE_PREFIX,
                app=create_remote_scheduler_app(worker_scheduler, token=REMOTE_TOKEN),
            )
        ]
    )
    with TestClient(worker_app) as worker_client:
        remote = RemoteSchedulerClient(
            token="wrong-token",
            transport=_remote_transport(worker_client),
        )

        with pytest.raises(RemoteSchedulerError):
            remote.get_scheduler_info()
