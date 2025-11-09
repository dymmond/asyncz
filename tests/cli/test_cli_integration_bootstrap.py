from __future__ import annotations

import json
import re
from datetime import datetime, timedelta
from pathlib import Path
from textwrap import dedent

import pytest
from sayer.testing import SayerTestClient

from asyncz.cli.app import asyncz_cli
from asyncz.cli.bootstrap_loader import clear_bootstrap_cache


@pytest.fixture()
def client() -> SayerTestClient:
    return SayerTestClient(asyncz_cli)


@pytest.fixture(autouse=True)
def _clear_bootstrap_cache_between_tests():
    clear_bootstrap_cache()
    yield
    clear_bootstrap_cache()


@pytest.fixture()
def bootstrap_spec_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> str:
    """
    Creates a temporary importable package:
        bootstrap_pkg/spec.py
    exposing:
        - AsynczSpec: returns an AsyncIOScheduler with in-memory store
        - noop(): a simple callable
        - echo(a, b=None, flag=False, x=0): for args/kwargs testing
    """
    pkg = tmp_path / "bootstrap_pkg"
    pkg.mkdir(parents=True, exist_ok=True)
    (pkg / "__init__.py").write_text("", encoding="utf-8")

    (pkg / "spec.py").write_text(
        dedent(
            """
            from __future__ import annotations

            from asyncz.schedulers.asyncio import AsyncIOScheduler

            # Simple no-op task
            def noop():
                return None

            # For args/kwargs coverage
            def echo(a, *args, **kwargs):
                return {"a": a, "args": args, "kwargs": kwargs}

            class AsynczSpec:
                def __init__(self) -> None:
                    # In-memory store default
                    self.sched = AsyncIOScheduler(
                        stores={"default": {"type": "memory"}}
                    )
                    # Do NOT start here; CLI will handle start()

                def get_scheduler(self) -> AsyncIOScheduler:
                    return self.sched
            """
        ),
        encoding="utf-8",
    )

    # Ensure import works
    monkeypatch.syspath_prepend(str(tmp_path))
    return "bootstrap_pkg.spec:AsynczSpec"


def _list_json_bootstrap(client: SayerTestClient, bootstrap_path: str):
    result = client.invoke(["list", "--json", "--bootstrap", bootstrap_path])
    assert result.exit_code == 0, result.stderr

    # 1) Prefer structured return_value
    if isinstance(result.return_value, (list, dict)):
        return result.return_value

    # 2) Else parse stdout/stderr JSON
    out = (result.stdout or "").strip() or (result.stderr or "").strip()
    if out.startswith("ℹ"):
        out = out.lstrip("ℹ️ ").lstrip()
    m = re.search(r"(\[.*\]|\{.*\})", out, re.S)

    assert m, f"Expected JSON in output, got: {out!r}"
    return json.loads(m.group(1))


def test_bootstrap_start_quick_lifecycle_no_watch(
    client: SayerTestClient, bootstrap_spec_path: str
):
    # With no --standalone and no --watch, start should start and then cleanly exit.
    result = client.invoke(
        [
            "start",
            "--bootstrap",
            bootstrap_spec_path,
        ]
    )

    assert result.exit_code == 0, result.stderr

    # Depending on your success message; both variants are accepted:
    assert ("Scheduler started via bootstrap." in result.stdout) or (
        "Scheduler started." in result.stdout
    )


def test_bootstrap_add_and_list(client: SayerTestClient, bootstrap_spec_path: str):
    # Add a job with an interval trigger (in bootstrap mode)
    result = client.invoke(
        [
            "add",
            "bootstrap_pkg.spec:noop",
            "--name",
            "test-noop",
            "--interval",
            "5s",
            "--bootstrap",
            bootstrap_spec_path,
        ]
    )
    assert result.exit_code == 0, result.stderr
    assert "Added job" in result.stdout

    # List jobs and ensure it appears
    result = client.invoke(["list", "--bootstrap", bootstrap_spec_path])

    assert result.exit_code == 0, result.stderr

    out = result.stdout

    assert "test-noop" in out
    assert "IntervalTrigger" in out


def test_bootstrap_add_run_pause_resume_remove_flow(
    client: SayerTestClient, bootstrap_spec_path: str
):
    # add
    result = client.invoke(
        [
            "add",
            "bootstrap_pkg.spec:noop",
            "--name",
            "flow-noop",
            "--interval",
            "10s",
            "--bootstrap",
            bootstrap_spec_path,
        ]
    )

    assert result.exit_code == 0, result.stderr

    m = re.search(r"Added job\s+(\S+)", result.stdout)

    assert m, f"Could not parse job id from: {result.stdout!r}"

    job_id = m.group(1)

    # run now
    result = client.invoke(["run", job_id, "--bootstrap", bootstrap_spec_path])

    assert result.exit_code == 0, result.stderr
    assert f"Triggered job {job_id}" in result.stdout

    # pause
    result = client.invoke(["pause", job_id, "--bootstrap", bootstrap_spec_path])

    assert result.exit_code == 0, result.stderr
    assert f"Paused job {job_id}" in result.stdout

    # resume
    result = client.invoke(["resume", job_id, "--bootstrap", bootstrap_spec_path])

    assert result.exit_code == 0, result.stderr
    assert f"Resumed job {job_id}" in result.stdout

    # remove
    result = client.invoke(["remove", job_id, "--bootstrap", bootstrap_spec_path])

    assert result.exit_code == 0, result.stderr
    assert f"Removed job {job_id}" in result.stdout


def test_bootstrap_add_with_args_kwargs_and_json_list(
    client: SayerTestClient, bootstrap_spec_path: str
):
    result = client.invoke(
        [
            "add",
            "bootstrap_pkg.spec:echo",
            "--name",
            "echoer",
            "--interval",
            "10s",
            "--args",
            '["a", 123]',
            "--kwargs",
            '{"flag": true, "x": 7}',
            "--bootstrap",
            bootstrap_spec_path,
        ]
    )
    assert result.exit_code == 0, result.stderr

    # List as JSON should parse and include our job
    jobs = _list_json_bootstrap(client, bootstrap_spec_path)

    assert any(j["name"] == "echoer" and j["trigger"] == "IntervalTrigger" for j in jobs)


def test_bootstrap_run_advances_next_run_time(client: SayerTestClient, bootstrap_spec_path: str):
    # Add every-10s job
    result = client.invoke(
        [
            "add",
            "bootstrap_pkg.spec:noop",
            "--name",
            "advance",
            "--interval",
            "10s",
            "--bootstrap",
            bootstrap_spec_path,
        ]
    )

    assert result.exit_code == 0, result.stderr

    m = re.search(r"Added job\s+(\S+)", result.stdout)
    job_id = m.group(1)

    # Capture current next_run_time
    before = _list_json_bootstrap(client, bootstrap_spec_path)
    nrt0 = next(j["next_run_time"] for j in before if j["id"] == job_id)

    assert nrt0 is not None

    # Force a run; this should reschedule forward
    result = client.invoke(["run", job_id, "--bootstrap", bootstrap_spec_path])

    assert result.exit_code == 0, result.stderr

    after = _list_json_bootstrap(client, bootstrap_spec_path)
    nrt1 = next(j["next_run_time"] for j in after if j["id"] == job_id)

    assert nrt1 is not None

    # Should move forward in time (string comparison-safe via ISO)
    assert nrt1 > nrt0


def test_bootstrap_pause_sets_next_run_time_null_and_resume_sets_future(
    client: SayerTestClient, bootstrap_spec_path: str
):
    # Add 10s interval job
    result = client.invoke(
        [
            "add",
            "bootstrap_pkg.spec:noop",
            "--name",
            "pauser",
            "--interval",
            "10s",
            "--bootstrap",
            bootstrap_spec_path,
        ]
    )
    assert result.exit_code == 0, result.stderr

    job_id = re.search(r"Added job\s+(\S+)", result.stdout).group(1)

    # Pause (direct-store update path)
    result = client.invoke(["pause", job_id, "--bootstrap", bootstrap_spec_path])

    assert result.exit_code == 0, result.stderr
    assert f"Paused job {job_id}" in result.stdout

    jobs = _list_json_bootstrap(client, bootstrap_spec_path)
    nxt = next(j["next_run_time"] for j in jobs if j["id"] == job_id)

    assert nxt is None, "pause should clear next_run_time"

    # Resume (compute a new next_run_time via trigger)
    result = client.invoke(["resume", job_id, "--bootstrap", bootstrap_spec_path])

    assert result.exit_code == 0, result.stderr
    assert f"Resumed job {job_id}" in result.stdout

    jobs2 = _list_json_bootstrap(client, bootstrap_spec_path)
    nxt2 = next(j["next_run_time"] for j in jobs2 if j["id"] == job_id)

    assert nxt2 is not None
    assert datetime.fromisoformat(nxt2).replace(tzinfo=None) > datetime.utcnow() - timedelta(
        seconds=1
    )


def test_bootstrap_ignores_store_flag(client: SayerTestClient, bootstrap_spec_path: str):
    # Passing --store together with --bootstrap should be ignored gracefully
    result = client.invoke(
        [
            "list",
            "--bootstrap",
            bootstrap_spec_path,
            "--store",
            "durable=sqlite:///ignored.db",
        ]
    )

    assert result.exit_code == 0, result.stderr
    # Depending on your command's info message; accept either present or absent,
    # but ensure the command runs successfully and prints something.
    assert result.stdout.strip() != ""
