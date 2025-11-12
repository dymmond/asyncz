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
        url_prefix=DASH_PREFIX,
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
    response = client_login.get(f"{url}")

    assert response.status_code == 200


def test_index_renders(client: TestClient):
    response = client.get(f"{DASH_PREFIX}/")

    assert response.status_code == 200
    assert "Scheduler" in response.text
    assert "Total Tasks" in response.text


def test_tasks_page_renders(client: TestClient):
    response = client.get(f"{DASH_PREFIX}/tasks/")
    assert response.status_code == 200
    assert "Tasks" in response.text  # header


def test_tasks_partial_table_initial(client: TestClient):
    response = client.get(f"{DASH_PREFIX}/tasks/partials/table")

    assert response.status_code == 200

    # At minimum returns a <table> ... </table> fragment
    assert "<table" in response.text and "</table>" in response.text


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

    response = client.post(f"{DASH_PREFIX}/tasks/create", data=payload)

    assert response.status_code == 200

    # Should return the refreshed table fragment containing our task name
    assert "cli-dash-noop" in response.text

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
    response = client.post(f"{DASH_PREFIX}/tasks/create", data=payload)
    assert response.status_code == 200
    html = response.text

    # 2) Grab the job id from the returned table
    job_id = _extract_first_job_id_from_table(html)
    assert job_id, f"Could not find job id in: {html[:500]}"

    # 3) Run now
    response = client.post(f"{DASH_PREFIX}/tasks/{job_id}/run")
    assert response.status_code == 200

    # 4) Pause
    response = client.post(f"{DASH_PREFIX}/tasks/{job_id}/pause")
    assert response.status_code == 200
    assert "Paused" in response.text or "pause" in response.text.lower() or job_id in response.text

    # 5) Resume
    response = client.post(f"{DASH_PREFIX}/tasks/{job_id}/resume")
    assert response.status_code == 200
    assert "Resume" in response.text or "Scheduled" in response.text or job_id in response.text

    # 6) Remove
    response = client.post(f"{DASH_PREFIX}/tasks/{job_id}/remove")
    assert response.status_code == 200

    # Table should no longer contain the job
    r2 = client.get(f"{DASH_PREFIX}/tasks/partials/table")
    assert r2.status_code == 200
    assert job_id not in r2.text


def test_bulk_actions_pause_run_resume_remove(client: TestClient):
    # Create three tasks
    created_ids: list[str] = []
    for idx in range(3):
        response = client.post(
            f"{DASH_PREFIX}/tasks/create",
            data={
                "callable_path": "tests.fixtures:noop",
                "name": f"bulk-{idx}",
                "store": "default",
                "trigger_type": "interval",
                "trigger_value": "15s",
            },
        )
        assert response.status_code == 200
        jid = _extract_first_job_id_from_table(response.text)
        assert jid
        created_ids.append(jid)

    ids_json = json.dumps(created_ids)

    # Pause
    response = client.post(
        f"{DASH_PREFIX}/tasks/hx/bulk/pause",
        data={"ids": ids_json},
        headers={"HX-Request": "true"},
    )
    assert response.status_code == 200

    # Run
    response = client.post(
        f"{DASH_PREFIX}/tasks/hx/bulk/run",
        data={"ids": ids_json},
        headers={"HX-Request": "true"},
    )
    assert response.status_code == 200

    # Resume
    response = client.post(
        f"{DASH_PREFIX}/tasks/hx/bulk/resume",
        data={"ids": ids_json},
        headers={"HX-Request": "true"},
    )
    assert response.status_code == 200

    # Remove
    response = client.post(
        f"{DASH_PREFIX}/tasks/hx/bulk/remove",
        data={"ids": ids_json},
        headers={"HX-Request": "true"},
    )
    assert response.status_code == 200

    # Ensure they are gone
    r2 = client.get(f"{DASH_PREFIX}/tasks/partials/table")
    assert r2.status_code == 200

    for jid in created_ids:
        assert jid not in r2.text


def test_url_prefix_is_stable_across_pages(client: TestClient):
    # Load tasks page and ensure links point back to prefix (no duplication)
    response = client.get(f"{DASH_PREFIX}/tasks")

    assert response.status_code == 200

    # The partials URL is absolute to prefix
    assert 'hx-get="partials/table"' in response.text


def _create_task(
    client: TestClient,
    name: str,
    trigger_type="interval",
    trigger_value="10s",
) -> str:
    response = client.post(
        f"{DASH_PREFIX}/tasks/create",
        data={
            "callable_path": "tests.fixtures:noop",
            "name": name,
            "store": "default",
            "trigger_type": trigger_type,
            "trigger_value": trigger_value,
        },
    )
    assert response.status_code == 200

    jid = _extract_first_job_id_from_table(response.text)

    assert jid, "Could not extract job id from table HTML"
    return jid


def test_tasks_search_filters_full_page_by_name(client: TestClient):
    _create_task(client, "alpha-one")
    _create_task(client, "Beta-two")
    _create_task(client, "gamma-three")

    response = client.get(f"{DASH_PREFIX}/tasks/?q=beta")
    assert response.status_code == 200

    txt = response.text

    assert "Beta-two" in txt
    assert "alpha-one" not in txt
    assert "gamma-three" not in txt


def test_tasks_search_filters_partial_by_name(client: TestClient):
    _create_task(client, "alpha-one")
    _create_task(client, "Beta-two")

    response = client.get(f"{DASH_PREFIX}/tasks/partials/table?q=alpha")
    assert response.status_code == 200

    txt = response.text
    assert "alpha-one" in txt
    assert "Beta-two" not in txt


def test_tasks_search_is_case_insensitive(client: TestClient):
    _create_task(client, "MiXeD-Case-Name")

    response = client.get(f"{DASH_PREFIX}/tasks/?q=mixed")
    assert response.status_code == 200
    assert "MiXeD-Case-Name" in response.text

    r2 = client.get(f"{DASH_PREFIX}/tasks/partials/table?q=NAME")
    assert r2.status_code == 200
    assert "MiXeD-Case-Name" in r2.text


def test_tasks_search_can_match_by_trigger_type(client: TestClient):
    # one interval, one cron
    _create_task(client, "interval-one", trigger_type="interval", trigger_value="5s")
    _create_task(client, "cronny", trigger_type="cron", trigger_value="*/5 * * * *")

    # Full page search for "cron" should show only the cron job
    response = client.get(f"{DASH_PREFIX}/tasks/?q=cron")
    assert response.status_code == 200
    assert "cronny" in response.text
    assert "interval-one" not in response.text

    # Partials search for "interval" should show only the interval job
    r2 = client.get(f"{DASH_PREFIX}/tasks/partials/table?q=interval")
    assert r2.status_code == 200
    assert "interval-one" in r2.text
    assert "cronny" not in r2.text


def test_tasks_search_can_match_by_id(client: TestClient):
    jid = _create_task(client, "id-searchable")

    # Search by the exact id should return the row
    response = client.get(f"{DASH_PREFIX}/tasks/?q={jid}")
    assert response.status_code == 200
    assert jid in response.text
    assert "id-searchable" in response.text

    # Partials too
    r2 = client.get(f"{DASH_PREFIX}/tasks/partials/table?q={jid}")
    assert r2.status_code == 200
    assert jid in r2.text


def test_tasks_search_reset_link_clears_query(client: TestClient):
    _create_task(client, "only-one")

    # With a filter that excludes our row
    response = client.get(f"{DASH_PREFIX}/tasks/?q=zzz-nothing")
    assert response.status_code == 200
    assert "only-one" not in response.text

    # Simulate clicking the "Reset" link (go to /tasks without q)
    r2 = client.get(f"{DASH_PREFIX}/tasks")
    assert r2.status_code == 200
    assert "only-one" in r2.text
