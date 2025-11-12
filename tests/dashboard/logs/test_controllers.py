# tests/dashboard/test_logger.py
from __future__ import annotations

import time
from collections.abc import Iterator

import pytest
from lilya.apps import Lilya
from lilya.testclient import TestClient

from asyncz.contrib.dashboard.admin import (
    AsynczAdmin,
    SimpleUsernamePasswordBackend,
    User,
)
from asyncz.schedulers.asyncio import AsyncIOScheduler

DASH_PREFIX = "/dashboard"


@pytest.fixture()
def scheduler() -> Iterator[AsyncIOScheduler]:
    sched = AsyncIOScheduler()
    sched.start()
    try:
        yield sched
    finally:
        sched.shutdown()


def verify(u, p):
    if u == "admin" and p == "secret":
        return User(id="admin", name="Admin")
    return None


@pytest.fixture()
def client(scheduler: AsyncIOScheduler) -> Iterator[TestClient]:
    """
    Unauthenticated dashboard client (sufficient if logs page is public).
    """
    app = Lilya()
    admin = AsynczAdmin(url_prefix=DASH_PREFIX, scheduler=scheduler)
    admin.include_in(app)
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def client_login(scheduler: AsyncIOScheduler) -> Iterator[TestClient]:
    """
    Authenticated variant, in case your logs page is behind AuthGateMiddleware.
    Adjust if you protect /logs behind login.
    """
    app = Lilya()
    admin = AsynczAdmin(
        url_prefix=DASH_PREFIX,
        scheduler=scheduler,
        enable_login=True,
        backend=SimpleUsernamePasswordBackend(verify),
    )
    admin.include_in(app)
    with TestClient(app) as c:
        resp = c.post(
            f"{DASH_PREFIX}/login",
            data={"username": "admin", "password": "secret"},
            follow_redirects=True,
        )
        assert resp.status_code in (200, 303, 307)
        yield c


@pytest.fixture(scope="module")
def _log_helpers():
    """
    Access the logging helpers/sinks used by the dashboard.
    We do imports here so tests skip cleanly if the module path changes.

    Expected helpers:
      - install_task_log_handler(storage=...)
      - get_task_logger(task_id)
      - install_loguru_sink(storage=...)  (or logger.add(...) wrapper)
      - get_log_storage()
    """
    try:
        from asyncz.contrib.dashboard.controllers.logs import (  # type: ignore
            get_log_storage,
        )
        from asyncz.contrib.dashboard.logs.handler import (  # type: ignore
            get_task_logger,
            install_task_log_handler,
        )

        # Optional: if you exposed a convenience installer for loguru
        try:
            from asyncz.contrib.dashboard.logs.handler import (  # type: ignore
                install_loguru_sink,
            )
        except Exception:  # pragma: no cover - optional helper
            install_loguru_sink = None

        return {
            "install_task_log_handler": install_task_log_handler,
            "get_task_logger": get_task_logger,
            "get_log_storage": get_log_storage,
            "install_loguru_sink": install_loguru_sink,
        }
    except Exception as e:
        pytest.skip(f"Logs handler/storage helpers not available yet: {e!r}")


@pytest.fixture(autouse=True)
def _wire_logging(_log_helpers):
    """
    Ensure both stdlib and loguru events land in the same in-memory storage
    that the Logs controller reads from.

    Called automatically for each test.
    """
    storage = _log_helpers["get_log_storage"]()
    # Clear storage between tests if your storage supports it
    if hasattr(storage, "clear"):
        storage.clear()

    # stdlib → storage
    _log_helpers["install_task_log_handler"](storage=storage)

    # loguru → storage (if you exposed a helper). Otherwise, tests will still pass
    # for stdlib-only paths, and the loguru test will skip if missing.
    if _log_helpers["install_loguru_sink"]:
        _log_helpers["install_loguru_sink"](storage=storage)
    yield
    # Optional teardown/cleanup can go here.


def test_logs_page_renders(client: TestClient):
    response = client.get(f"{DASH_PREFIX}/logs")
    # Some apps redirect /logs -> /logs/; follow that:
    if response.status_code in (301, 302, 303, 307, 308):
        response = client.get(f"{DASH_PREFIX}/logs/")

    assert response.status_code == 200

    # Basic smoke markers: page title and the HTMX container for the table partial.
    assert "Logs" in response.text
    assert 'hx-get="partials/table"' in response.text


def test_logs_stdlib_visible_in_ui(client: TestClient, _log_helpers):
    """
    Emit a stdlib log bound to a task id and ensure it appears in the logs table.
    """
    task_id = "jid-stdlib-1"
    msg = "hello from stdlib"
    logger = _log_helpers["get_task_logger"](task_id)
    logger.info(msg, extra={"task_id": task_id})

    # If the UI async-loads, a tiny sleep helps the storage flush (esp. with enqueue/queues).
    time.sleep(0.02)

    # Pull the table partial, filter by the task id just to be deterministic
    response = client.get(f"{DASH_PREFIX}/logs/partials/table?task_id={task_id}")

    assert response.status_code == 200
    assert task_id in response.text
    assert msg in response.text


def test_logs_filter_by_text_and_level(client: TestClient, _log_helpers):
    """
    Create a few mixed-level entries and verify filtering by q and level.
    """
    task_id = "jid-mixed"
    log = _log_helpers["get_task_logger"](task_id)
    log.debug("dbg hidden")  # Usually filtered out in UI default, but will exist in storage
    log.info("index built")
    log.warning("latency spike")
    log.error("boom failure")

    time.sleep(0.01)

    # Filter by free text ("latency")
    response = client.get(f"{DASH_PREFIX}/logs/partials/table?q=latency")

    assert response.status_code == 200
    assert "latency spike" in response.text
    assert "index built" not in response.text

    # Filter by level=ERROR (exactly the error row)
    response = client.get(f"{DASH_PREFIX}/logs/partials/table?level=ERROR")

    assert response.status_code == 200
    assert "boom failure" in response.text
    assert "latency spike" not in response.text

    # Combine level + q
    response = client.get(f"{DASH_PREFIX}/logs/partials/table?level=INFO&q=index")

    assert response.status_code == 200
    assert "index built" in response.text
    assert "boom failure" not in response.text


def test_logs_filter_by_task_id(client: TestClient, _log_helpers):
    """
    Two different tasks, ensure filtering isolates rows by task_id.
    """
    log_a = _log_helpers["get_task_logger"]("jid-A")
    log_b = _log_helpers["get_task_logger"]("jid-B")

    log_a.info("only A", extra={"task_id": "jid-A"})
    log_b.info("only B", extra={"task_id": "jid-B"})

    time.sleep(0.01)

    ra = client.get(f"{DASH_PREFIX}/logs/partials/table?task_id=jid-A")
    rb = client.get(f"{DASH_PREFIX}/logs/partials/table?task_id=jid-B")

    assert ra.status_code == 200 and rb.status_code == 200
    assert "only A" in ra.text and "only B" not in ra.text
    assert "only B" in rb.text and "only A" not in rb.text


def test_logs_reset_link(client: TestClient, _log_helpers):
    """
    When a filter hides rows, the Reset link (to /logs) should clear filters.
    """
    task_id = "jid-reset"
    log = _log_helpers["get_task_logger"](task_id)
    log.info("visible after reset")

    time.sleep(0.01)

    # A filter that excludes it
    response = client.get(f"{DASH_PREFIX}/logs/?q=zzz-nothing")
    assert response.status_code in (200, 303, 307)

    # Simulate clicking the "Reset" link (navigate to /logs)
    response = client.get(f"{DASH_PREFIX}/logs")
    if response.status_code in (301, 302, 303, 307, 308):
        response = client.get(f"{DASH_PREFIX}/logs/")

    assert response.status_code == 200

    # After navigation, fetch the partials table (HTMX would load this in the browser).
    response = client.get(f"{DASH_PREFIX}/logs/partials/table")
    assert response.status_code == 200
    assert "visible after reset" in response.text
