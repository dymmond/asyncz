from __future__ import annotations

import hashlib
import json
from collections.abc import Iterator
from importlib import resources
from typing import Any

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


def verify(username: str, password: str) -> User | None:
    if username == "admin" and password == "secret":
        return User(id="admin", name="Admin")
    return None


@pytest.fixture()
def client(scheduler: AsyncIOScheduler) -> Iterator[TestClient]:
    app = Lilya()
    admin = AsynczAdmin(url_prefix=DASH_PREFIX, scheduler=scheduler)
    admin.include_in(app)
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def forwarded_prefix_client(scheduler: AsyncIOScheduler) -> Iterator[TestClient]:
    app = Lilya()
    admin = AsynczAdmin(
        url_prefix=DASH_PREFIX,
        scheduler=scheduler,
        enable_forward_middleware=True,
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
    )
    admin.include_in(app)
    with TestClient(app) as c:
        yield c


def package_static_root() -> Any:
    return resources.files("asyncz.contrib.dashboard").joinpath("statics")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def test_static_assets_are_served_locally(client: TestClient) -> None:
    expected_assets: dict[str, bytes | str] = {
        f"{DASH_PREFIX}/static/favicon.ico": b"\x00\x00\x01\x00",
        f"{DASH_PREFIX}/static/css/tailwind-4.3.2.min.css": "tailwindcss v4.3.2",
        f"{DASH_PREFIX}/static/css/toastify.min.css": "Toastify js 1.6.1",
        f"{DASH_PREFIX}/static/js/toastify.min.js": 'toastify:"1.6.1"',
        f"{DASH_PREFIX}/static/vendor/alpinejs/alpine-csp-3.15.12.min.js": 'version:"3.15.12"',
        f"{DASH_PREFIX}/static/vendor/htmx/htmx-1.9.12.min.js": "htmx:load",
        f"{DASH_PREFIX}/static/vendor/manifest.json": '"alpinejs"',
    }

    for path, marker in expected_assets.items():
        response = client.get(path)
        assert response.status_code == 200
        if isinstance(marker, bytes):
            assert response.content.startswith(marker)
        else:
            assert marker in response.text


def test_vendor_manifest_checksums_match_packaged_assets() -> None:
    static_root = package_static_root()
    manifest = json.loads(static_root.joinpath("vendor/manifest.json").read_text())

    for metadata in manifest.values():
        if "artifact" in metadata:
            artifact = static_root.joinpath(metadata["artifact"])
            assert artifact.is_file()
            assert sha256_bytes(artifact.read_bytes()) == metadata["artifact_sha256"]

        for artifact_path in metadata.get("artifacts", []):
            artifact = static_root.joinpath(artifact_path)
            assert artifact.is_file()
            assert (
                sha256_bytes(artifact.read_bytes()) == metadata["artifact_sha256"][artifact_path]
            )

        license_file = static_root.joinpath(metadata["license_file"])
        assert license_file.is_file()


def test_templates_reference_local_assets_without_public_cdns(client: TestClient) -> None:
    disallowed = (
        "cdn.tailwindcss.com",
        "cdn.jsdelivr.net",
        "unpkg.com",
        "tailwind.config",
    )

    for path in (
        f"{DASH_PREFIX}/",
        f"{DASH_PREFIX}/tasks",
        f"{DASH_PREFIX}/runtime",
        f"{DASH_PREFIX}/instances",
        f"{DASH_PREFIX}/timeline",
        f"{DASH_PREFIX}/audit",
        f"{DASH_PREFIX}/logs",
        "/missing-page",
    ):
        response = client.get(path)
        assert response.status_code in {200, 404}
        html = response.text
        for marker in disallowed:
            assert marker not in html
        assert f"{DASH_PREFIX}/static/css/tailwind-4.3.2.min.css" in html
        assert f"{DASH_PREFIX}/static/css/asyncz.css" in html
        if path != "/missing-page":
            assert f"{DASH_PREFIX}/static/vendor/htmx/htmx-1.9.12.min.js" in html
            assert f"{DASH_PREFIX}/static/vendor/alpinejs/alpine-csp-3.15.12.min.js" in html


def test_forwarded_prefix_generates_proxy_aware_dashboard_urls(
    forwarded_prefix_client: TestClient,
) -> None:
    response = forwarded_prefix_client.get(
        f"{DASH_PREFIX}/tasks",
        headers={"x-forwarded-prefix": "/ops/"},
    )

    assert response.status_code == 200
    assert "http://testserver/ops/dashboard/static/css/asyncz.css" in response.text
    assert (
        "http://testserver/ops/dashboard/static/vendor/alpinejs/alpine-csp-3.15.12.min.js"
        in response.text
    )
    assert 'href="http://testserver/ops/dashboard/runtime/"' in response.text
    assert 'hx-get="/ops/dashboard/tasks/partials/table"' in response.text


def test_bundled_login_template_uses_local_assets(client_login: TestClient) -> None:
    response = client_login.get("/login")

    assert response.status_code == 200
    assert f"{DASH_PREFIX}/static/favicon.ico" in response.text
    assert f"{DASH_PREFIX}/static/css/tailwind-4.3.2.min.css" in response.text
    assert f"{DASH_PREFIX}/static/css/toastify.min.css" in response.text
    assert f"{DASH_PREFIX}/static/js/toastify.min.js" in response.text
    assert f"{DASH_PREFIX}/static/vendor/htmx/htmx-1.9.12.min.js" in response.text
    assert f"{DASH_PREFIX}/static/vendor/alpinejs/alpine-csp-3.15.12.min.js" in response.text
    assert "cdn.tailwindcss.com" not in response.text
    assert "unpkg.com" not in response.text
    assert "tailwind.config" not in response.text


def test_login_static_assets_bypass_auth_gate(client_login: TestClient) -> None:
    expected_assets: dict[str, bytes | str] = {
        f"{DASH_PREFIX}/static/favicon.ico": b"\x00\x00\x01\x00",
        f"{DASH_PREFIX}/static/css/asyncz.css": ".az-shell",
        f"{DASH_PREFIX}/static/js/asyncz.js": 'Alpine.data("asynczShell"',
        f"{DASH_PREFIX}/static/vendor/alpinejs/alpine-csp-3.15.12.min.js": 'version:"3.15.12"',
    }

    for path, marker in expected_assets.items():
        response = client_login.get(path, follow_redirects=False)

        assert response.status_code == 200
        if isinstance(marker, bytes):
            assert response.content.startswith(marker)
        else:
            assert marker in response.text
        assert "<!DOCTYPE html>" not in response.text[:80]
