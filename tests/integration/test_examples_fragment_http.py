"""Plan 12 — Production-path parity for Fragment-rendered example surfaces.

Asserts that GETting each example app's primary list URL through a real
FastAPI TestClient returns 200 with Fragment-chrome CSS classes in the
response body. Catches integration regressions Plan 11's IR-level smoke
test can't see: route-handler context shape, htmx swap headers,
error-response wrapping, dispatch routing through the renderer registry.

Why a stub backend: page routes proxy data fetches to a backend HTTP
service. With no real backend, the data fetch fails into the empty-state
path — which is exactly what a fresh app shows on first boot, and which
exercises the full render stack without needing fixture data.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from dazzle.core.appspec_loader import load_project_appspec

pytest.importorskip("dazzle_ui.runtime.page_routes")
from dazzle_ui.runtime.page_routes import create_page_routes  # noqa: E402

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_EXAMPLES = _REPO_ROOT / "examples"

_APPS: tuple[tuple[str, str], ...] = (
    ("simple_task", "/task"),
    ("contact_manager", "/contact"),
    ("support_tickets", "/user"),
    ("ops_dashboard", "/system"),
    ("fieldtest_hub", "/device"),
)

_FRAGMENT_LIST_MARKERS: tuple[str, ...] = (
    "dz-surface",
    "dz-region--kind-list",
)


def _client_for(app_name: str) -> TestClient:
    """Build a TestClient against a bare FastAPI app with page routes
    mounted and runtime services attached.

    `_maybe_dispatch_inner_html` requires `app.state.services` to route
    through the renderer registry. Without it, the dispatch hook returns
    None and the legacy template path runs — masking what we're trying
    to verify. This mirrors what `DazzleBackendApp.build()` does in
    production (server.py:405-407).
    """
    from dazzle_back.runtime.renderers.init import register_default_renderers
    from dazzle_back.runtime.services import RuntimeServices

    appspec = load_project_appspec(_EXAMPLES / app_name)
    fastapi_app = FastAPI()
    services = RuntimeServices()
    register_default_renderers(services)
    fastapi_app.state.services = services
    router = create_page_routes(appspec, backend_url="http://127.0.0.1:9999")
    fastapi_app.include_router(router)
    return TestClient(fastapi_app)


@pytest.mark.parametrize("app_name,primary_list_url", _APPS)
def test_primary_list_renders_via_fragment_path(app_name: str, primary_list_url: str) -> None:
    """The primary list URL of every example serves a 200 response whose
    body contains the Fragment renderer's chrome classes."""
    client = _client_for(app_name)
    resp = client.get(primary_list_url)
    assert resp.status_code == 200, (
        f"{app_name} GET {primary_list_url}: status {resp.status_code}, "
        f"body[:500]={resp.text[:500]!r}"
    )
    body = resp.text
    for marker in _FRAGMENT_LIST_MARKERS:
        assert marker in body, (
            f"{app_name} GET {primary_list_url}: response body missing "
            f"Fragment chrome class {marker!r}. body[:500]={body[:500]!r}"
        )
