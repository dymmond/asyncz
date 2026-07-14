from __future__ import annotations

import json
import re
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
from asyncz.contrib.dashboard.audit import MemoryAuditTrailStorage, get_audit_storage
from asyncz.contrib.dashboard.events import get_scheduler_event_storage
from asyncz.contrib.dashboard.history import MemoryRunHistoryStorage
from asyncz.contrib.dashboard.logs.storage import MemoryLogStorage
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
    admin = AsynczAdmin(
        scheduler=scheduler,
        log_storage=MemoryLogStorage(maxlen=1_000),
        run_history_storage=MemoryRunHistoryStorage(maxlen=1_000),
        audit_storage=MemoryAuditTrailStorage(maxlen=1_000),
    )
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
        log_storage=MemoryLogStorage(maxlen=1_000),
        run_history_storage=MemoryRunHistoryStorage(maxlen=1_000),
        audit_storage=MemoryAuditTrailStorage(maxlen=1_000),
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
    assert 'class="az-shell"' in response.text
    assert 'x-data="asynczShell"' in response.text
    assert "data-sidebar-toggle" in response.text
    assert 'class="az-workspace"' in response.text
    assert "Operate" in response.text
    assert "Review" in response.text
    assert "Events" in response.text


def test_tasks_page_renders(client: TestClient):
    response = client.get(f"{DASH_PREFIX}/tasks/")
    assert response.status_code == 200
    assert "Tasks" in response.text  # header
    assert 'x-data="asynczTasks"' in response.text
    assert "az-task-toolbar" in response.text
    assert "Table density" in response.text
    assert 'x-on:click="toggleFilters"' in response.text
    assert "az-table-wrap--resizable az-table-wrap--sticky-actions" in response.text


def test_runtime_page_renders_scheduler_components(client: TestClient):
    _create_task(client, "runtime-visible")

    response = client.get(f"{DASH_PREFIX}/runtime/")

    assert response.status_code == 200
    assert "Scheduler Runtime" in response.text
    assert "Runtime Profile" in response.text
    assert "Scheduler ID" in response.text
    assert "Started At" in response.text
    assert "Uptime" in response.text
    assert "MemoryStore" in response.text
    assert "AsyncIOExecutor" in response.text
    assert "runtime-visible" not in response.text
    assert "asyncz.stores.default" in response.text
    assert "asyncz.executors.default" in response.text
    assert 'title="Runtime"' in response.text
    assert 'aria-current="page"' in response.text


def test_instances_page_renders_process_local_scheduler(client: TestClient):
    _create_task(client, "instance-visible")

    response = client.get(f"{DASH_PREFIX}/instances/")

    assert response.status_code == 200
    assert "Scheduler Instances" in response.text
    assert "process-local" in response.text
    assert "Active" in response.text
    assert "instance-visible" not in response.text
    assert "MemoryStore" not in response.text
    assert 'title="Instances"' in response.text
    assert 'aria-current="page"' in response.text


def test_timeline_page_renders_upcoming_runs(client: TestClient):
    _create_task(client, "timeline-interval", trigger_type="interval", trigger_value="5s")
    _create_task(
        client,
        "timeline-date",
        trigger_type="date",
        trigger_value="2027-01-01T10:00:00+00:00",
    )

    response = client.get(f"{DASH_PREFIX}/timeline/?per_task=2&limit=10")

    assert response.status_code == 200
    assert "Run Timeline" in response.text
    assert "Upcoming Run Times" in response.text
    assert "timeline-interval" in response.text
    assert "timeline-date" in response.text
    assert "previewed run" in response.text
    assert 'title="Timeline"' in response.text
    assert 'aria-current="page"' in response.text


def test_audit_page_tracks_task_management_actions(client: TestClient):
    get_audit_storage().clear()
    job_id = _create_task(client, "audited-task")

    run_response = client.post(f"{DASH_PREFIX}/tasks/{job_id}/run")
    assert run_response.status_code == 200

    response = client.get(f"{DASH_PREFIX}/audit/")

    assert response.status_code == 200
    assert "Audit Trail" in response.text
    assert "Task Create" in response.text
    assert "Task Run" in response.text
    assert job_id in response.text
    assert "audited-task" in response.text
    assert 'title="Audit"' in response.text
    assert 'aria-current="page"' in response.text

    filtered = client.get(f"{DASH_PREFIX}/audit/?action=task.run")
    assert filtered.status_code == 200
    assert "Task Run" in filtered.text


def test_events_page_tracks_scheduler_events(client: TestClient):
    get_scheduler_event_storage().clear()
    job_id = _create_task(client, "event-visible")

    response = client.get(f"{DASH_PREFIX}/events/?task_id={job_id}")

    assert response.status_code == 200
    assert "Scheduler Events" in response.text
    assert "Task Added" in response.text
    assert job_id in response.text
    assert "Observed Events" in response.text

    filtered = client.get(f"{DASH_PREFIX}/events/?name=task.added&task_id={job_id}")
    assert filtered.status_code == 200
    assert "Task Added" in filtered.text


def test_events_page_tracks_task_submission_metadata(client: TestClient):
    get_scheduler_event_storage().clear()
    job_id = _create_task(client, "event-run")

    response = client.post(f"{DASH_PREFIX}/tasks/{job_id}/run")
    assert response.status_code == 200

    events = client.get(f"{DASH_PREFIX}/events/?task_id={job_id}")

    assert events.status_code == 200
    assert "Task Submitted" in events.text
    assert "scheduled_run_times" in events.text


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


def test_create_date_task_and_list(client: TestClient):
    payload = {
        "callable_path": "tests.fixtures:noop",
        "name": "cli-dash-date",
        "store": "default",
        "trigger_type": "date",
        "trigger_value": "2027-01-01T10:00:00+00:00",
        "args": "",
        "kwargs": "",
    }

    response = client.post(f"{DASH_PREFIX}/tasks/create", data=payload)

    assert response.status_code == 200
    assert "cli-dash-date" in response.text


def test_task_table_links_to_edit_page(client: TestClient):
    job_id = _create_task(client, "editable-row")

    response = client.get(f"{DASH_PREFIX}/tasks/partials/table")

    assert response.status_code == 200
    assert f'href="{DASH_PREFIX}/tasks/{job_id}"' in response.text
    assert f'href="{DASH_PREFIX}/tasks/{job_id}/edit"' in response.text
    assert f'href="{DASH_PREFIX}/logs?task_id={job_id}"' in response.text
    assert 'title="Details"' in response.text
    assert 'title="Edit"' in response.text
    assert 'title="Logs"' in response.text


def test_task_detail_page_renders_task_context(client: TestClient):
    job_id = _create_task(client, "detail-row")

    run_response = client.post(f"{DASH_PREFIX}/tasks/{job_id}/run")
    assert run_response.status_code == 200

    response = client.get(f"{DASH_PREFIX}/tasks/{job_id}")
    for _ in range(20):
        if "Task run succeeded" in response.text:
            break
        time.sleep(0.01)
        response = client.get(f"{DASH_PREFIX}/tasks/{job_id}")

    assert response.status_code == 200
    assert "Task Detail" in response.text
    assert "detail-row" in response.text
    assert job_id in response.text
    assert "Upcoming Runs" in response.text
    assert "Recent Runs" in response.text
    assert "Recent Logs" in response.text
    assert "Task run succeeded" in response.text
    assert f'href="{DASH_PREFIX}/history?task_id={job_id}"' in response.text
    assert f'href="{DASH_PREFIX}/logs?task_id={job_id}"' in response.text


def test_task_detail_page_handles_missing_task(client: TestClient):
    response = client.get(f"{DASH_PREFIX}/tasks/missing-task")

    assert response.status_code == 404
    assert "Task not found" in response.text


def test_task_edit_previews_and_applies_update(client: TestClient, scheduler: AsyncIOScheduler):
    get_audit_storage().clear()
    job_id = _create_task(client, "edit-before")

    response = client.get(f"{DASH_PREFIX}/tasks/{job_id}/edit")

    assert response.status_code == 200
    assert "Edit Task" in response.text
    assert "edit-before" in response.text
    assert "Task Metadata" in response.text

    payload = {
        "name": "edit-after",
        "callable_path": "tests.fixtures:noop",
        "executor": "default",
        "coalesce": "false",
        "max_instances": "4",
        "mistrigger_grace_time": "",
        "clear_mistrigger_grace_time": "1",
        "args": "[]",
        "kwargs": "{}",
        "intent": "preview",
    }
    preview = client.post(f"{DASH_PREFIX}/tasks/{job_id}/edit", data=payload)

    assert preview.status_code == 200
    assert "Proposed Changes" in preview.text
    assert "edit-after" in preview.text
    task = scheduler.get_task(job_id)
    assert task is not None
    assert task.name == "edit-before"

    payload["intent"] = "apply"
    applied = client.post(f"{DASH_PREFIX}/tasks/{job_id}/edit", data=payload)

    assert applied.status_code == 200
    assert "Task update applied." in applied.text
    assert "Applied Changes" in applied.text
    task = scheduler.get_task(job_id)
    assert task is not None
    assert task.name == "edit-after"
    assert task.coalesce is False
    assert task.max_instances == 4
    assert task.mistrigger_grace_time is None

    audit = client.get(f"{DASH_PREFIX}/audit/?action=task.update")
    assert audit.status_code == 200
    assert "Task Update" in audit.text
    assert job_id in audit.text


def test_dashboard_index_shows_recent_task_metadata(client: TestClient):
    _create_task(client, "overview-task")

    response = client.get(f"{DASH_PREFIX}/")

    assert response.status_code == 200
    assert "overview-task" in response.text
    assert "noop" in response.text


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


def test_tasks_filter_by_state_and_executor(client: TestClient):
    paused_id = _create_task(client, "paused-task")
    _create_task(client, "scheduled-task")

    pause_response = client.post(f"{DASH_PREFIX}/tasks/{paused_id}/pause")
    assert pause_response.status_code == 200

    response = client.get(f"{DASH_PREFIX}/tasks/?state=paused&executor=default")
    assert response.status_code == 200
    assert "paused-task" in response.text
    assert "scheduled-task" not in response.text


def test_tasks_partial_preserves_active_filters(client: TestClient):
    _create_task(client, "filter-me")

    response = client.get(
        f"{DASH_PREFIX}/tasks/partials/table?q=filter&state=scheduled&page=2&per_page=25"
    )

    assert response.status_code == 200
    assert "q=filter&amp;state=scheduled&amp;per_page=25" in response.text


def test_tasks_table_paginates_full_page(client: TestClient):
    _create_task(client, "alpha-page")
    _create_task(client, "bravo-page")
    _create_task(client, "charlie-page")

    response = client.get(f"{DASH_PREFIX}/tasks/?sort=name&per_page=2")

    assert response.status_code == 200
    assert "Showing 1-2 of 3 matching tasks" in response.text
    assert "Page 1 of 2" in response.text
    assert "alpha-page" in response.text
    assert "bravo-page" in response.text
    assert "charlie-page" not in response.text
    assert "page=2&amp;per_page=2" in response.text


def test_tasks_table_paginates_partial_page(client: TestClient):
    _create_task(client, "alpha-partial")
    _create_task(client, "bravo-partial")
    _create_task(client, "charlie-partial")

    response = client.get(f"{DASH_PREFIX}/tasks/partials/table?sort=name&per_page=2&page=2")

    assert response.status_code == 200
    assert "Showing 3-3 of 3 matching tasks" in response.text
    assert "Page 2 of 2" in response.text
    assert "charlie-partial" in response.text
    assert "alpha-partial" not in response.text
    assert "bravo-partial" not in response.text


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
