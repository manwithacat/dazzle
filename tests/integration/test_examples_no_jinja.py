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
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from jinja2 import Template

from dazzle.core.appspec_loader import load_project_appspec
from dazzle.core.manifest import load_manifest

pytest.importorskip("dazzle_ui.runtime.page_routes")
from dazzle_ui.runtime.page_routes import create_page_routes  # noqa: E402

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_EXAMPLES = _REPO_ROOT / "examples"
_BOGUS_UUID = "00000000-0000-0000-0000-000000000000"

_APPS = ("simple_task", "contact_manager", "support_tickets", "ops_dashboard", "fieldtest_hub")


class _JinjaSpy:
    """Records every Template.render call. Enabled inside a `with` block."""

    def __init__(self) -> None:
        self.calls: list[str] = []
        self._original = Template.render

    def __enter__(self) -> _JinjaSpy:
        spy = self
        original = self._original

        def tracked(self_template: Template, *args: object, **kwargs: object) -> str:
            name = getattr(self_template, "name", None) or "<inline>"
            spy.calls.append(name)
            return original(self_template, *args, **kwargs)

        self._patch = patch.object(Template, "render", tracked)
        self._patch.start()
        return self

    def __exit__(self, *exc: object) -> None:
        self._patch.stop()


def _client_for_example(app_name: str) -> tuple[TestClient, FastAPI]:
    """Build a TestClient with chrome flag read from the example's
    dazzle.toml — same path production uses."""
    from dazzle_back.runtime.renderers.init import register_default_renderers
    from dazzle_back.runtime.services import RuntimeServices

    app_root = _EXAMPLES / app_name
    appspec = load_project_appspec(app_root)
    manifest = load_manifest(app_root / "dazzle.toml")
    fastapi_app = FastAPI()
    services = RuntimeServices()
    register_default_renderers(services)
    fastapi_app.state.services = services
    fastapi_app.state.fragment_chrome = manifest.fragment_chrome
    fastapi_app.include_router(create_page_routes(appspec, backend_url="http://127.0.0.1:9999"))
    return TestClient(fastapi_app), fastapi_app


def _resolve(template: str) -> str:
    return re.sub(r"\{[^}]+\}", _BOGUS_UUID, template)


# ─────────────────── Per-example chrome flag check ───────────────────


@pytest.mark.parametrize("app_name", _APPS)
def test_example_has_fragment_chrome_enabled(app_name: str) -> None:
    """Every example's dazzle.toml must opt into Fragment chrome.
    Pins the rollout state — if this fails, an example regressed
    out of Jinja-free."""
    manifest = load_manifest(_EXAMPLES / app_name / "dazzle.toml")
    assert manifest.fragment_chrome is True, (
        f"{app_name}/dazzle.toml has fragment_chrome={manifest.fragment_chrome}. "
        f"All 5 examples should opt in."
    )


# ─────────────────── Per-example zero-Jinja walk ─────────────────────


@pytest.mark.parametrize("app_name", _APPS)
def test_example_walks_all_routes_with_zero_jinja(app_name: str) -> None:
    """Walk every GET route registered for the example. With chrome
    flag from dazzle.toml AND surfaces flipped (Plan 11), zero Jinja
    template invocations across all served responses.

    Failure mode is informative: lists which routes fired which
    templates so regressions are immediately diagnosable."""
    client, app = _client_for_example(app_name)
    fired: dict[str, tuple[int, list[str]]] = {}
    for route in app.routes:
        path = getattr(route, "path", "") or ""
        methods = getattr(route, "methods", None) or set()
        if "GET" not in methods or path.startswith(("/openapi", "/docs", "/redoc")):
            continue
        url = _resolve(path)
        with _JinjaSpy() as spy:
            resp = client.get(url, follow_redirects=False)
        if spy.calls:
            fired[path] = (resp.status_code, sorted(set(spy.calls)))
    assert not fired, f"{app_name}: Jinja templates rendered under chrome=on:\n" + "\n".join(
        f"  {p} (status={code}): {tmpls!r}" for p, (code, tmpls) in fired.items()
    )
