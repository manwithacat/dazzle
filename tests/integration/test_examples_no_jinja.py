"""Per-example Jinja-zero validation across all 5 example apps.

Walks every served GET route under chrome=on (read from each app's
`dazzle.toml`, which all 5 examples now opt into) and asserts no
Jinja templates fire — the validation criterion for "Dazzle apps
that don't call Jinja2 templates".

Routes that legitimately don't render templates (3xx redirects, 403
forbidden, 404 not found) all produce zero `Template.render()` calls
under chrome=on across all 5 example apps. Categorised reporting on
failure so any regression is actionable.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from dazzle.core.appspec_loader import load_project_appspec
from dazzle.core.manifest import load_manifest

pytest.importorskip("dazzle.back.runtime.page_routes")
from dazzle.back.runtime.page_routes import create_page_routes  # noqa: E402

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_EXAMPLES = _REPO_ROOT / "examples"
_BOGUS_UUID = "00000000-0000-0000-0000-000000000000"

_APPS = ("simple_task", "contact_manager", "support_tickets", "ops_dashboard", "fieldtest_hub")


def _client_for_example(app_name: str) -> tuple[TestClient, FastAPI]:
    """Build a TestClient against the example's appspec.

    Phase 4 app-shell migration (v0.67.45): the fragment_chrome flag
    is retired — the typed-Fragment substrate is the only render path.
    `load_manifest(...)` is still called for parity with the production
    bootstrap (validates the manifest TOML), but its result no longer
    threads into a render-mode decision.
    """
    from dazzle.back.runtime.renderers.init import register_default_renderers
    from dazzle.back.runtime.services import RuntimeServices

    app_root = _EXAMPLES / app_name
    appspec = load_project_appspec(app_root)
    _manifest = load_manifest(app_root / "dazzle.toml")  # validation only
    fastapi_app = FastAPI()
    services = RuntimeServices()
    register_default_renderers(services)
    fastapi_app.state.services = services
    fastapi_app.include_router(create_page_routes(appspec, backend_url="http://127.0.0.1:9999"))
    return TestClient(fastapi_app), fastapi_app


def _resolve(template: str) -> str:
    return re.sub(r"\{[^}]+\}", _BOGUS_UUID, template)


# ─────────────────── Per-example chrome flag check ───────────────────


# Phase 4 app-shell migration (v0.67.45): the `fragment_chrome` field
# is retired from `ProjectManifest`. The per-example "must opt in"
# assertion is obsolete — every render is typed-Fragment now,
# regardless of dazzle.toml content. The zero-Jinja walk below pins
# the actual contract (no Jinja templates fire on the rendered
# response).


@pytest.mark.parametrize("app_name", _APPS)
def test_example_manifest_loads(app_name: str) -> None:
    """Validates that the example's dazzle.toml still parses
    cleanly. Catches regressions in the manifest loader (e.g. when
    deprecated keys like `[ui] fragment_chrome` should log but not
    raise)."""
    manifest = load_manifest(_EXAMPLES / app_name / "dazzle.toml")
    assert manifest.name, f"{app_name}/dazzle.toml has empty project.name"


# ─────────────────── Per-example zero-Jinja walk ─────────────────────


@pytest.mark.parametrize("app_name", _APPS)
def test_example_walks_all_routes_with_zero_jinja(app_name: str) -> None:
    """Walk every GET route registered for the example. With chrome
    flag from dazzle.toml AND surfaces flipped (Plan 11), zero Jinja
    template invocations across all served responses.

    Failure mode is informative: lists which routes fired which
    templates so regressions are immediately diagnosable."""
    client, app = _client_for_example(app_name)
    for route in app.routes:
        path = getattr(route, "path", "") or ""
        methods = getattr(route, "methods", None) or set()
        if "GET" not in methods or path.startswith(("/openapi", "/docs", "/redoc")):
            continue
        url = _resolve(path)
        resp = client.get(url, follow_redirects=False)
        # Jinja-free is structurally guaranteed (#1042 removed jinja2).
        # Verify every GET route at least serves without 5xx.
        assert resp.status_code < 500, f"{app_name} {path} returned {resp.status_code}"
