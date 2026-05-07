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


# ─────────────────────────── Mode coverage ───────────────────────────
#
# Per-mode adapter branches (_build_view, _build_form) pinned at the
# HTTP layer for simple_task — the canonical reference example.

_FRAGMENT_DETAIL_MARKERS: tuple[str, ...] = (
    "dz-surface",
    "dz-region--kind-detail",
)

_FRAGMENT_FORM_MARKERS: tuple[str, ...] = (
    "dz-surface",
    "dz-region--kind-form",
    "dz-form-stack",
)


def test_simple_task_create_url_renders_form_via_fragment() -> None:
    """The CREATE form route returns 200 with Fragment form-chrome
    classes — pins _build_form at the HTTP layer."""
    client = _client_for("simple_task")
    resp = client.get("/task/create")
    assert resp.status_code == 200, (
        f"simple_task GET /task/create: status {resp.status_code}, body[:500]={resp.text[:500]!r}"
    )
    body = resp.text
    for marker in _FRAGMENT_FORM_MARKERS:
        assert marker in body, (
            f"simple_task GET /task/create: missing Fragment form marker "
            f"{marker!r}. body[:500]={body[:500]!r}"
        )


def test_simple_task_detail_url_renders_via_fragment_or_404() -> None:
    """GET /task/<bogus-id> either renders 404 OR a Fragment-chromed
    detail page (depending on how the route handles missing rows).
    What's not acceptable is a 500."""
    client = _client_for("simple_task")
    resp = client.get("/task/00000000-0000-0000-0000-000000000000")
    assert resp.status_code in (200, 404), (
        f"simple_task GET /task/<bogus-id>: status {resp.status_code} "
        f"(expected 200 or 404), body[:500]={resp.text[:500]!r}"
    )
    if resp.status_code == 200:
        body = resp.text
        for marker in _FRAGMENT_DETAIL_MARKERS:
            assert marker in body, (
                f"simple_task GET /task/<bogus-id> returned 200 but "
                f"missing Fragment detail marker {marker!r}. "
                f"body[:500]={body[:500]!r}"
            )


def test_simple_task_create_form_has_ref_picker_for_assigned_to() -> None:
    """The CREATE form for Task includes a RefPicker for `assigned_to:
    ref User`. Plan 14 closure end-to-end: REF field in DSL → adapter
    produces RefPicker → renderer emits dz-ref-picker chrome →
    response body contains it."""
    client = _client_for("simple_task")
    resp = client.get("/task/create")
    assert resp.status_code == 200
    body = resp.text
    assert "dz-ref-picker" in body, (
        f"simple_task /task/create missing RefPicker chrome. body[:500]={body[:500]!r}"
    )
    assert "data-ref-api" in body, (
        f"simple_task /task/create RefPicker missing data-ref-api. body[:500]={body[:500]!r}"
    )


# ─────────────────── Per-widget regression (issue #1026) ───────────────────
#
# Pre-v0.66.45 the adapter expected DSL field-type kinds but the page
# route always passes WIDGET kinds — silently swapping str↔text and
# rendering enum/bool as plain text inputs. These cases pin the correct
# widget per DSL field type at the HTTP layer.


def test_simple_task_create_form_str_field_renders_as_text_input() -> None:
    """`title: str(200)` → <input type="text">, NOT <textarea>."""
    client = _client_for("simple_task")
    resp = client.get("/task/create")
    body = resp.text
    assert 'type="text" name="title"' in body, (
        f"task_create title field is not a text input. body[:500]={body[:500]!r}"
    )


def test_simple_task_create_form_text_field_renders_as_textarea() -> None:
    """`description: text` → <textarea>, NOT <input type="text">."""
    client = _client_for("simple_task")
    resp = client.get("/task/create")
    body = resp.text
    assert '<textarea class="dz-field__input" name="description"' in body, (
        "task_create description field rendered as input, not textarea."
    )


def test_simple_task_create_form_enum_field_renders_as_select() -> None:
    """`priority: enum[low,medium,high,urgent]` → <select> with options."""
    client = _client_for("simple_task")
    resp = client.get("/task/create")
    body = resp.text
    assert '<select class="dz-combobox__select" name="priority">' in body, (
        "task_create priority field is not a Combobox <select>."
    )
    for value in ("low", "medium", "high", "urgent"):
        assert f'<option value="{value}"' in body, (
            f"task_create priority field missing enum option {value!r}."
        )


def test_simple_task_create_form_date_field_renders_as_date_input() -> None:
    """`due_date: date` → <input type="date">."""
    client = _client_for("simple_task")
    resp = client.get("/task/create")
    body = resp.text
    assert 'type="date" name="due_date"' in body, "task_create due_date field is not a date input."


# ─────────────────── Fragment chrome opt-in (P17 P3 + P4) ───────────────────
#
# When app.state.fragment_chrome is True, full-document responses
# bypass Jinja base.html and emit a typed Page primitive instead.
# This is the first non-Jinja chrome — pinned end-to-end.


def _client_with_fragment_chrome(app_name: str) -> TestClient:
    """Build a TestClient with `fragment_chrome` flag set on app.state.

    Mirrors `_client_for` but enables the P17 P3 chrome dispatch.
    """
    from dazzle_back.runtime.renderers.init import register_default_renderers
    from dazzle_back.runtime.services import RuntimeServices

    appspec = load_project_appspec(_EXAMPLES / app_name)
    fastapi_app = FastAPI()
    services = RuntimeServices()
    register_default_renderers(services)
    fastapi_app.state.services = services
    fastapi_app.state.fragment_chrome = True  # P17 P3 opt-in
    router = create_page_routes(appspec, backend_url="http://127.0.0.1:9999")
    fastapi_app.include_router(router)
    return TestClient(fastapi_app)


def test_fragment_chrome_emits_page_primitive_doctype() -> None:
    """With the chrome flag on, the response starts with `<!DOCTYPE html>`
    from the Page primitive — unconditional substrate, not Jinja's
    conditional partial-mode block."""
    client = _client_with_fragment_chrome("simple_task")
    resp = client.get("/task")
    assert resp.status_code == 200
    assert resp.text.startswith("<!DOCTYPE html>"), (
        f"expected Fragment-chromed page; got: {resp.text[:200]!r}"
    )


def test_fragment_chrome_emits_dz_page_body_class() -> None:
    """The Page primitive emits `<body class="dz-page">` — the marker
    that distinguishes a Fragment-chromed response from a Jinja one."""
    client = _client_with_fragment_chrome("simple_task")
    resp = client.get("/task")
    body = resp.text
    assert '<body class="dz-page">' in body, (
        f"missing dz-page body class. body[:500]={body[:500]!r}"
    )


def test_fragment_chrome_includes_dazzle_css_and_js_bundles() -> None:
    """The page chrome links the bundled CSS + defers the bundled JS."""
    client = _client_with_fragment_chrome("simple_task")
    resp = client.get("/task")
    body = resp.text
    assert '<link rel="stylesheet" href="/static/dist/dazzle.min.css">' in body
    assert '<script defer src="/static/dist/dazzle.min.js"></script>' in body


def test_fragment_chrome_inner_surface_still_renders() -> None:
    """The Fragment surface body must still appear inside the chrome —
    the chrome wraps, doesn't replace, the inner Fragment dispatch."""
    client = _client_with_fragment_chrome("simple_task")
    resp = client.get("/task")
    body = resp.text
    assert "dz-surface" in body
    assert "dz-region--kind-list" in body


def test_fragment_chrome_emits_body_announcer_slots() -> None:
    """Page emits the toast/modal/announcer slots by default."""
    client = _client_with_fragment_chrome("simple_task")
    resp = client.get("/task")
    body = resp.text
    assert 'id="dz-toast"' in body
    assert 'id="dz-modal-slot"' in body
    assert 'id="dz-page-announcer"' in body


def test_fragment_chrome_default_off_unchanged_behaviour() -> None:
    """Without the flag, responses still go through Jinja base.html —
    confirmed by absence of the `dz-page` body class. Pins backward
    compatibility."""
    client = _client_for("simple_task")  # no fragment_chrome flag
    resp = client.get("/task")
    body = resp.text
    assert '<body class="dz-page">' not in body, (
        f"chrome flag default-off broken; got Fragment chrome unexpectedly. "
        f"body[:500]={body[:500]!r}"
    )


# ─────────────────── Fragment chrome — htmx-partial mode (P17 P8) ───────────────


def test_fragment_chrome_htmx_request_returns_body_only_no_doctype() -> None:
    """htmx requests on chrome-on apps must NOT include the page chrome
    (DOCTYPE, <html>, <head>) — htmx swaps the response into the
    existing page DOM. Sending chrome would produce nested <html>
    elements and break the swap."""
    client = _client_with_fragment_chrome("simple_task")
    resp = client.get("/task", headers={"HX-Request": "true"})
    assert resp.status_code == 200
    body = resp.text
    assert not body.lstrip().startswith("<!DOCTYPE"), (
        f"htmx response unexpectedly includes DOCTYPE — would nest <html>. "
        f"body[:200]={body[:200]!r}"
    )
    assert "<html" not in body
    assert "<head>" not in body
    assert "<body" not in body


def test_fragment_chrome_htmx_request_returns_inner_surface_body() -> None:
    """The htmx response IS the inner Fragment surface body — same
    inner_html that would have been wrapped in chrome for a full
    request, returned bare for htmx swap."""
    client = _client_with_fragment_chrome("simple_task")
    resp = client.get("/task", headers={"HX-Request": "true"})
    body = resp.text
    assert "dz-surface" in body
    assert "dz-region--kind-list" in body


def test_fragment_chrome_htmx_response_no_jinja_chrome_either() -> None:
    """Specifically: the htmx response must NOT have rendered through
    Jinja base.html either (no `dz-toast-stack`, `dz-modal-slot`,
    `dz-page-announcer` from the Jinja layout). The Fragment path
    short-circuits htmx requests to inner_html only."""
    client = _client_with_fragment_chrome("simple_task")
    resp = client.get("/task", headers={"HX-Request": "true"})
    body = resp.text
    # These markers come from base.html's body block in the legacy
    # render_page(partial=True) path — they should not appear in the
    # Fragment-chrome htmx response.
    assert "dz-modal-slot" not in body
    assert "dz-page-announcer" not in body


def _client_with_chrome_assets(
    app_name: str,
    css_links: tuple[str, ...] | None = None,
    js_scripts: tuple[str, ...] | None = None,
    theme: str | None = None,
) -> TestClient:
    """Like `_client_with_fragment_chrome` but lets the test set
    custom asset URLs / theme on app.state. For P17 P10 — proves
    chrome assets are configurable, not hardcoded."""
    from dazzle_back.runtime.renderers.init import register_default_renderers
    from dazzle_back.runtime.services import RuntimeServices

    appspec = load_project_appspec(_EXAMPLES / app_name)
    fastapi_app = FastAPI()
    services = RuntimeServices()
    register_default_renderers(services)
    fastapi_app.state.services = services
    fastapi_app.state.fragment_chrome = True
    if css_links is not None:
        fastapi_app.state.fragment_chrome_css_links = css_links
    if js_scripts is not None:
        fastapi_app.state.fragment_chrome_js_scripts = js_scripts
    if theme is not None:
        fastapi_app.state.fragment_chrome_theme = theme
    router = create_page_routes(appspec, backend_url="http://127.0.0.1:9999")
    fastapi_app.include_router(router)
    return TestClient(fastapi_app)


# ─────────────────── Asset overrides (P17 P10) ───────────────────


def test_fragment_chrome_default_assets_when_state_unset() -> None:
    """Default behaviour: bundled mode CSS+JS, no theme."""
    client = _client_with_fragment_chrome("simple_task")
    body = client.get("/task").text
    assert '<link rel="stylesheet" href="/static/dist/dazzle.min.css">' in body
    assert '<script defer src="/static/dist/dazzle.min.js"></script>' in body
    assert "data-theme=" not in body


def test_fragment_chrome_custom_css_links_override() -> None:
    """Multiple CSS links in declared order — order is cascade-relevant."""
    client = _client_with_chrome_assets(
        "simple_task",
        css_links=(
            "/static/dist/dazzle.min.css",
            "/static/themes/linear-dark.css",
        ),
    )
    body = client.get("/task").text
    assert '<link rel="stylesheet" href="/static/dist/dazzle.min.css">' in body
    assert '<link rel="stylesheet" href="/static/themes/linear-dark.css">' in body
    a = body.index('href="/static/dist/dazzle.min.css"')
    b = body.index('href="/static/themes/linear-dark.css"')
    assert a < b, "cascade order must match declaration order"


def test_fragment_chrome_custom_js_scripts_override() -> None:
    """Individual-script mode (dev environments) — many separate JS URLs."""
    client = _client_with_chrome_assets(
        "simple_task",
        js_scripts=(
            "/static/vendor/htmx.min.js",
            "/static/vendor/htmx-ext-json-enc.js",
            "/static/js/dz-alpine.js",
        ),
    )
    body = client.get("/task").text
    for url in (
        "/static/vendor/htmx.min.js",
        "/static/vendor/htmx-ext-json-enc.js",
        "/static/js/dz-alpine.js",
    ):
        assert f'<script defer src="{url}"></script>' in body


def test_fragment_chrome_theme_override_emits_data_theme_attr() -> None:
    """`fragment_chrome_theme` propagates to `<html data-theme="...">`,
    matching the legacy template's theme attribute."""
    client = _client_with_chrome_assets("simple_task", theme="linear-dark")
    body = client.get("/task").text
    assert '<html lang="en" data-theme="linear-dark">' in body


def test_fragment_chrome_default_off_htmx_still_uses_jinja_partial() -> None:
    """Backward compat: chrome flag off → htmx requests still go through
    `render_page(partial=True, ...)` exactly as before. Pinned because
    P8 is a behaviour change for chrome=on, must not leak to chrome=off."""
    client = _client_for("simple_task")  # no fragment_chrome
    resp = client.get("/task", headers={"HX-Request": "true"})
    body = resp.text
    # The legacy partial path renders the body slot — Jinja layout
    # markers like `dz-toast-stack` should appear, distinguishing
    # from the chrome-on bare-inner-html path.
    assert "dz-modal-slot" in body or "dz-toast-stack" in body, (
        f"chrome-off htmx response missing Jinja layout markers — did "
        f"P8 leak to chrome-off path? body[:500]={body[:500]!r}"
    )
