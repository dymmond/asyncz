from __future__ import annotations

import json
import re
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
    app = Lilya()
    admin = AsynczAdmin(scheduler=scheduler)
    admin.include_in(app)
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def client_login(scheduler: AsyncIOScheduler) -> Iterator[TestClient]:
    app = Lilya()
    admin = AsynczAdmin(
        scheduler=scheduler,
        enable_login=True,
        backend=SimpleUsernamePasswordBackend(verify),
    )
    admin.include_in(app)
    with TestClient(app) as c:
        yield c


def _extract_first_job_id_from_table(html: str) -> str | None:
    """
    Try multiple resilient patterns to find a task id in the HTML table
    returned by /tasks/partials/table. We support several render variants:
      - bulk checkbox:  <input name="row" value="...">
      - data attribute: <tr data-jid="...">
      - mono cell div:  <div class="font-mono ...">...</div>
      - bare fallback inside a <td> (last resort)
    """
    patterns = [
        # <input name="row" ... value="ID">
        r'name\s*=\s*["\']row["\'][^>]*\bvalue\s*=\s*["\']([a-f0-9\-]{16,})["\']',
        # <tr data-jid="ID">
        r'\bdata-jid\s*=\s*["\']([a-f0-9\-]{16,})["\']',
        # <div class="font-mono ...">ID</div>
        r'<div[^>]*class="[^"]*\bfont-mono\b[^"]*"[^>]*>\s*([a-f0-9\-]{16,})\s*</div>',
        # Fallback: a bare hex-ish id inside a <td>
        r"<td[^>]*>\s*([a-f0-9]{32})\s*</td>",
    ]
    for pat in patterns:
        m = re.search(pat, html, re.I | re.S)
        if m:
            return m.group(1)
    return None


@pytest.mark.parametrize("url", ["/login", "/logout"])
def test_login_and_logout_page(client_login, url):
    r = client_login.get(f"{DASH_PREFIX}/{url}")

    assert r.status_code == 200


def test_index_renders(client: TestClient):
    r = client.get(f"{DASH_PREFIX}/")
    assert r.status_code == 200
    assert "Scheduler" in r.text
    assert "Total Tasks" in r.text


def test_tasks_page_renders(client: TestClient):
    r = client.get(f"{DASH_PREFIX}/tasks/")
    assert r.status_code == 200
    assert "Tasks" in r.text  # header


def test_tasks_partial_table_initial(client: TestClient):
    r = client.get(f"{DASH_PREFIX}/tasks/partials/table")

    assert r.status_code == 200

    # At minimum returns a <table> ... </table> fragment
    assert "<table" in r.text and "</table>" in r.text


def test_create_task_and_list(client: TestClient):
    payload = {
        "callable_path": "tests.fixtures:noop",
        "name": "cli-dash-noop",
        "store": "default",
        "trigger_type": "interval",
        "trigger_value": "5s",
        "args": "",
        "kwargs": "",
    }

    r = client.post(f"{DASH_PREFIX}/tasks/create", data=payload)

    assert r.status_code == 200

    # Should return the refreshed table fragment containing our task name
    assert "cli-dash-noop" in r.text

    # Double-check through partials endpoint
    r2 = client.get(f"{DASH_PREFIX}/tasks/partials/table")
    assert r2.status_code == 200
    assert "cli-dash-noop" in r2.text


def test_per_row_actions_run_pause_resume_remove(client: TestClient):
    # 1) Create
    payload = {
        "callable_path": "tests.fixtures:noop",
        "name": "row-actions",
        "store": "default",
        "trigger_type": "interval",
        "trigger_value": "10s",
    }
    r = client.post(f"{DASH_PREFIX}/tasks/create", data=payload)
    assert r.status_code == 200
    html = r.text

    # 2) Grab the job id from the returned table
    job_id = _extract_first_job_id_from_table(html)
    assert job_id, f"Could not find job id in: {html[:500]}"

    # 3) Run now
    r = client.post(f"{DASH_PREFIX}/tasks/{job_id}/run")
    assert r.status_code == 200

    # 4) Pause
    r = client.post(f"{DASH_PREFIX}/tasks/{job_id}/pause")
    assert r.status_code == 200
    assert "Paused" in r.text or "pause" in r.text.lower() or job_id in r.text

    # 5) Resume
    r = client.post(f"{DASH_PREFIX}/tasks/{job_id}/resume")
    assert r.status_code == 200
    assert "Resume" in r.text or "Scheduled" in r.text or job_id in r.text

    # 6) Remove
    r = client.post(f"{DASH_PREFIX}/tasks/{job_id}/remove")
    assert r.status_code == 200

    # Table should no longer contain the job
    r2 = client.get(f"{DASH_PREFIX}/tasks/partials/table")
    assert r2.status_code == 200
    assert job_id not in r2.text


def test_bulk_actions_pause_run_resume_remove(client: TestClient):
    # Create three tasks
    created_ids: list[str] = []
    for idx in range(3):
        r = client.post(
            f"{DASH_PREFIX}/tasks/create",
            data={
                "callable_path": "tests.fixtures:noop",
                "name": f"bulk-{idx}",
                "store": "default",
                "trigger_type": "interval",
                "trigger_value": "15s",
            },
        )
        assert r.status_code == 200
        jid = _extract_first_job_id_from_table(r.text)
        assert jid
        created_ids.append(jid)

    ids_json = json.dumps(created_ids)

    # Pause
    r = client.post(
        f"{DASH_PREFIX}/tasks/hx/bulk/pause",
        data={"ids": ids_json},
        headers={"HX-Request": "true"},
    )
    assert r.status_code == 200

    # Run
    r = client.post(
        f"{DASH_PREFIX}/tasks/hx/bulk/run",
        data={"ids": ids_json},
        headers={"HX-Request": "true"},
    )
    assert r.status_code == 200

    # Resume
    r = client.post(
        f"{DASH_PREFIX}/tasks/hx/bulk/resume",
        data={"ids": ids_json},
        headers={"HX-Request": "true"},
    )
    assert r.status_code == 200

    # Remove
    r = client.post(
        f"{DASH_PREFIX}/tasks/hx/bulk/remove",
        data={"ids": ids_json},
        headers={"HX-Request": "true"},
    )
    assert r.status_code == 200

    # Ensure they are gone
    r2 = client.get(f"{DASH_PREFIX}/tasks/partials/table")
    assert r2.status_code == 200

    for jid in created_ids:
        assert jid not in r2.text


def test_url_prefix_is_stable_across_pages(client: TestClient):
    # Load tasks page and ensure links point back to prefix (no duplication)
    r = client.get(f"{DASH_PREFIX}/tasks")

    assert r.status_code == 200

    # The sidebar link back to dashboard should be absolute to prefix
    assert f'href="{DASH_PREFIX}"' in r.text

    # The partials URL is absolute to prefix
    assert 'hx-get="partials/table"' in r.text
