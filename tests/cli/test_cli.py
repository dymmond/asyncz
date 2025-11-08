import json
import re
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from sayer.testing import SayerTestClient

from asyncz.cli.app import asyncz_cli


@pytest.fixture()
def client() -> SayerTestClient:
    return SayerTestClient(asyncz_cli)


@pytest.fixture()
def sqlite_url(tmp_path: Path) -> str:
    db = tmp_path / "asyncz_test.db"
    return f"sqlite:///{db}"


def _list_json(client: SayerTestClient, store: str):
    r = client.invoke(["list", "--json", "--store", store])
    assert r.exit_code == 0, r.stderr

    # 1) Prefer Sayer return_value when the command *returns* JSON (list/dict)
    if isinstance(r.return_value, (list, dict)):
        return r.return_value

    # 2) If return_value is a JSON string, use it
    if isinstance(r.return_value, str) and r.return_value.strip():
        out = r.return_value.strip()
    else:
        # 3) Fall back to stdout, then stderr
        out = (r.stdout or "").strip() or (r.stderr or "").strip()

    # Be resilient to Sayer info prefixes (e.g., "ℹ …")
    if out.startswith("ℹ"):
        out = out.lstrip("ℹ️ ").lstrip()

    # Extract the first JSON array/object in case of surrounding log noise
    m = re.search(r"(\[.*\]|\{.*\})", out, re.S)
    assert m, f"Expected JSON in output, got: {out!r}"
    return json.loads(m.group(1))


def test_add_and_list_with_sqlite_store(client: SayerTestClient, sqlite_url: str):
    # add a job with an interval trigger
    r = client.invoke(
        [
            "add",
            "tests.fixtures:noop",
            "--name",
            "test-noop",
            "--interval",
            "5s",
            "--store",
            f"durable={sqlite_url}",
        ]
    )

    assert r.exit_code == 0, r.stderr
    assert "Added job" in r.stdout

    # list jobs and ensure it appears
    r = client.invoke(
        [
            "list",
            "--store",
            f"durable={sqlite_url}",
        ]
    )
    assert r.exit_code == 0, r.stderr

    out = r.stdout

    assert "test-noop" in out
    assert "IntervalTrigger" in out


def test_add_run_pause_resume_remove_flow(client: SayerTestClient, sqlite_url: str):
    # add
    r = client.invoke(
        [
            "add",
            "tests.fixtures:noop",
            "--name",
            "flow-noop",
            "--interval",
            "10s",
            "--store",
            f"durable={sqlite_url}",
        ]
    )
    assert r.exit_code == 0, r.stderr

    m = re.search(r"Added job\s+(\S+)", r.stdout)

    assert m, f"Could not parse job id from: {r.stdout!r}"

    job_id = m.group(1)

    # run now
    r = client.invoke(["run", job_id, "--store", f"durable={sqlite_url}"])

    assert r.exit_code == 0, r.stderr
    assert f"Triggered job {job_id}" in r.stdout

    # pause
    r = client.invoke(["pause", job_id, "--store", f"durable={sqlite_url}"])

    assert r.exit_code == 0, r.stderr
    assert f"Paused job {job_id}" in r.stdout

    # resume
    r = client.invoke(["resume", job_id, "--store", f"durable={sqlite_url}"])

    assert r.exit_code == 0, r.stderr
    assert f"Resumed job {job_id}" in r.stdout

    # remove
    r = client.invoke(["remove", job_id, "--store", f"durable={sqlite_url}"])

    assert r.exit_code == 0, r.stderr
    assert f"Removed job {job_id}" in r.stdout


def test_start_quick_lifecycle_no_watch(client: SayerTestClient, sqlite_url: str):
    # With no --standalone and no --watch, start should start and then cleanly exit
    r = client.invoke(
        [
            "start",
            "--store",
            f"durable={sqlite_url}",
            "--executor",
            "default=asyncio",
            # no --standalone, no --watch
        ]
    )

    assert r.exit_code == 0, r.stderr
    assert "Scheduler started." in r.stdout


def test_add_uses_explicit_store_alias(client: SayerTestClient, sqlite_url: str):
    # Ensure we really write into "durable" (not "default")
    r = client.invoke(
        [
            "add",
            "tests.fixtures:noop",
            "--name",
            "aliased",
            "--interval",
            "5s",
            "--store",
            f"durable={sqlite_url}",
        ]
    )
    assert r.exit_code == 0, r.stderr

    jobs = _list_json(client, f"durable={sqlite_url}")

    assert any(j["name"] == "aliased" for j in jobs)


def test_add_with_args_kwargs_and_json_list(client: SayerTestClient, sqlite_url: str):
    r = client.invoke(
        [
            "add",
            "tests.fixtures:echo",
            "--name",
            "echoer",
            "--interval",
            "10s",
            "--args",
            '["a", 123]',
            "--kwargs",
            '{"flag": true, "x": 7}',
            "--store",
            f"durable={sqlite_url}",
        ]
    )

    assert r.exit_code == 0, r.stderr

    # List as JSON should parse and include our job
    jobs = _list_json(client, f"durable={sqlite_url}")

    assert any(j["name"] == "echoer" and j["trigger"] == "IntervalTrigger" for j in jobs)


def test_run_advances_next_run_time(client: SayerTestClient, sqlite_url: str):
    # Add an every-10s job
    r = client.invoke(
        [
            "add",
            "tests.fixtures:noop",
            "--name",
            "advance",
            "--interval",
            "10s",
            "--store",
            f"durable={sqlite_url}",
        ]
    )

    assert r.exit_code == 0, r.stderr

    m = re.search(r"Added job\s+(\S+)", r.stdout)
    job_id = m.group(1)

    # Capture current next_run_time
    before = _list_json(client, f"durable={sqlite_url}")
    nrt0 = next(j["next_run_time"] for j in before if j["id"] == job_id)

    assert nrt0 is not None

    # Force a run; this should reschedule forward
    r = client.invoke(["run", job_id, "--store", f"durable={sqlite_url}"])

    assert r.exit_code == 0, r.stderr

    after = _list_json(client, f"durable={sqlite_url}")
    nrt1 = next(j["next_run_time"] for j in after if j["id"] == job_id)

    assert nrt1 is not None

    # Should move forward in time
    assert nrt1 > nrt0


def test_pause_sets_next_run_time_null_and_resume_sets_future(
    client: SayerTestClient, sqlite_url: str
):
    r = client.invoke(
        [
            "add",
            "tests.fixtures:noop",
            "--name",
            "pauser",
            "--interval",
            "10s",
            "--store",
            f"durable={sqlite_url}",
        ]
    )

    assert r.exit_code == 0, r.stderr

    job_id = re.search(r"Added job\s+(\S+)", r.stdout).group(1)

    # Pause (use direct-store update path)
    r = client.invoke(["pause", job_id, "--store", f"durable={sqlite_url}"])

    assert r.exit_code == 0, r.stderr
    assert f"Paused job {job_id}" in r.stdout

    jobs = _list_json(client, f"durable={sqlite_url}")
    nxt = next(j["next_run_time"] for j in jobs if j["id"] == job_id)

    assert nxt is None, "pause should clear next_run_time"

    # Resume (compute a new next_run_time via trigger)
    r = client.invoke(["resume", job_id, "--store", f"durable={sqlite_url}"])

    assert r.exit_code == 0, r.stderr
    assert f"Resumed job {job_id}" in r.stdout

    jobs2 = _list_json(client, f"durable={sqlite_url}")
    nxt2 = next(j["next_run_time"] for j in jobs2 if j["id"] == job_id)

    assert nxt2 is not None

    # Should be in the future (a tiny tolerance for clock drift)
    assert datetime.fromisoformat(nxt2).replace(tzinfo=None) > datetime.utcnow() - timedelta(
        seconds=1
    )


def test_remove_actually_deletes(client: SayerTestClient, sqlite_url: str):
    r = client.invoke(
        [
            "add",
            "tests.fixtures:noop",
            "--name",
            "deleteme",
            "--interval",
            "5s",
            "--store",
            f"durable={sqlite_url}",
        ]
    )

    assert r.exit_code == 0, r.stderr

    job_id = re.search(r"Added job\s+(\S+)", r.stdout).group(1)

    r = client.invoke(["remove", job_id, "--store", f"durable={sqlite_url}"])

    assert r.exit_code == 0, r.stderr

    jobs = _list_json(client, f"durable={sqlite_url}")

    assert all(j["id"] != job_id for j in jobs)
