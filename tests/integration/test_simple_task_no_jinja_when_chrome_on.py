"""Validates the goal: when chrome=on, Jinja templates aren't rendered
for simple_task routes.

Spies on `jinja2.Template.render` (the bottleneck through which every
template render must pass) and walks every served GET route. Reports
which routes invoke Jinja and which templates were rendered. The
acceptance bar is gradual — currently asserts "no Jinja for the
primary surface routes", with workspace and unsupported-display
routes documented as known gaps until Phase 4 closes them.
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

pytest.importorskip("dazzle.ui.runtime.page_routes")
from dazzle.ui.runtime.page_routes import create_page_routes  # noqa: E402

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_EXAMPLES = _REPO_ROOT / "examples"
_BOGUS_UUID = "00000000-0000-0000-0000-000000000000"


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


def _client_chrome_on() -> tuple[TestClient, FastAPI]:
    from dazzle.back.runtime.renderers.init import register_default_renderers
    from dazzle.back.runtime.services import RuntimeServices

    appspec = load_project_appspec(_EXAMPLES / "simple_task")
    fastapi_app = FastAPI()
    services = RuntimeServices()
    register_default_renderers(services)
    fastapi_app.state.services = services
    fastapi_app.state.fragment_chrome = True
    fastapi_app.include_router(create_page_routes(appspec, backend_url="http://127.0.0.1:9999"))
    return TestClient(fastapi_app), fastapi_app


def _resolve(template: str) -> str:
    return re.sub(r"\{[^}]+\}", _BOGUS_UUID, template)


# ─────────────────── Per-route Jinja accounting ───────────────────


def test_primary_surface_routes_render_zero_jinja_templates() -> None:
    """The four primary surface modes — list, view, create, edit —
    on simple_task's Task entity. When chrome=on AND surface is flipped
    (Plan 11 closure), these routes should produce zero Jinja
    Template.render() invocations.

    This is the canonical "Jinja-free request" check — if it ever
    starts failing, something on the page-route → Fragment-chrome path
    has regressed back to a Jinja fallback.
    """
    client, _ = _client_chrome_on()
    routes = (
        "/task",  # list
        "/task/create",  # create
        f"/task/{_BOGUS_UUID}",  # view (404 acceptable)
        f"/task/{_BOGUS_UUID}/edit",  # edit (404 acceptable)
    )
    failures: list[tuple[str, list[str]]] = []
    for url in routes:
        with _JinjaSpy() as spy:
            resp = client.get(url, follow_redirects=False)
        # 404 is acceptable (bogus UUID); 200 must be Fragment-only.
        # 3xx redirects are auth-related and don't render templates.
        if resp.status_code == 200 and spy.calls:
            failures.append((url, sorted(set(spy.calls))))
    assert not failures, (
        "Jinja templates rendered for primary surface routes "
        "under chrome=on:\n" + "\n".join(f"  {url}: {tmpls!r}" for url, tmpls in failures)
    )


def test_htmx_partial_request_renders_zero_jinja_templates() -> None:
    """htmx requests on chrome=on apps with flipped surfaces use the
    P8 short-circuit path (return inner_html directly). Zero Jinja."""
    client, _ = _client_chrome_on()
    with _JinjaSpy() as spy:
        resp = client.get("/task", headers={"HX-Request": "true"})
    assert resp.status_code == 200
    assert not spy.calls, f"htmx request invoked Jinja templates: {sorted(set(spy.calls))!r}"


def test_taskcomment_routes_render_zero_jinja_templates() -> None:
    """The other DSL-flipped entity in simple_task — TaskComment — also
    routes through Fragment chrome. Same Jinja-zero expectation."""
    client, _ = _client_chrome_on()
    routes = ("/taskcomment", "/taskcomment/create")
    failures: list[tuple[str, list[str]]] = []
    for url in routes:
        with _JinjaSpy() as spy:
            resp = client.get(url, follow_redirects=False)
        if resp.status_code == 200 and spy.calls:
            failures.append((url, sorted(set(spy.calls))))
    assert not failures, "Jinja invoked on flipped TaskComment routes:\n" + "\n".join(
        f"  {url}: {tmpls!r}" for url, tmpls in failures
    )


# ─────────────────── Per-route inventory (categorisation) ───────────


def test_simple_task_chrome_zero_jinja_across_every_route() -> None:
    """The strongest claim — when chrome=on, NO Jinja templates render
    for ANY served GET route in simple_task (regardless of status code).
    Empirically true today: 200/404/403/302 all produce zero Jinja
    template invocations.

    Pins the Jinja-decommissioning state so any regression that
    re-introduces a Jinja fallback fires a clear test failure.
    """
    client, app = _client_chrome_on()
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
    assert not fired, "Jinja templates rendered under chrome=on:\n" + "\n".join(
        f"  {p} (status={code}): {tmpls!r}" for p, (code, tmpls) in fired.items()
    )
