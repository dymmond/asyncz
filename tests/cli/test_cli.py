import re
from pathlib import Path

import pytest
from sayer.testing import SayerTestClient  # <- Sayer’s test runner

from asyncz.cli.app import asyncz_cli  # the Sayer app defined in app.py


@pytest.fixture()
def client() -> SayerTestClient:
    return SayerTestClient(asyncz_cli)


@pytest.fixture()
def sqlite_url(tmp_path: Path) -> str:
    db = tmp_path / "asyncz_test.db"
    return f"sqlite:///{db}"


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
