"""Issue #1019: boosted htmx swap into #main-content must return partial.

When an htmx-boosted nav click targets ``#main-content`` and the framework
returns a full HTML document (`<html><head><body>…`), idiomorph tries to
relocate the response's `<main id="main-content">` into the existing one,
causing two errors per nav:

1. ``HierarchyRequestError: insertBefore — new child contains the parent``
2. ``Unexpected duplicate view-transition-name: main-content``

The fix: when the request signals a boosted swap into #main-content, return
only the inner-content fragment.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest
from fastapi import Request
from jinja2 import ChoiceLoader, DictLoader


@pytest.fixture
def stub_template() -> Any:
    """Inject a minimal project-side template that mimics the structure of a
    real shell-extending page: a ``content`` block plus some surrounding
    chrome the partial path must NOT emit."""
    from dazzle_ui.runtime.template_renderer import get_jinja_env

    env = get_jinja_env()
    original_loader = env.loader
    env.loader = ChoiceLoader(
        [
            DictLoader(
                {
                    # A page that "extends" the app shell would produce a full
                    # document. We simulate the relevant bits: the partial
                    # path must extract just the inner content.
                    "_test_boost_page.html": (
                        "<html><head><title>{{ page_title }}</title></head>"
                        "<body><nav>shell-chrome</nav>"
                        '<main id="main-content">'
                        "{% block content %}"
                        "<div class='page-body'>hello {{ user_name }}</div>"
                        "{% endblock %}"
                        "</main></body></html>"
                    )
                }
            ),
            original_loader,
        ]
    )
    yield
    env.loader = original_loader


def _make_request(headers: dict[str, str] | None = None) -> Request:
    """Build a minimal Starlette Request with the given headers and a
    shell_state on app.state."""
    from dazzle_back.runtime.shell import ShellState, register_shell_state

    headers = headers or {}
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/app/workspaces/teacher",
        "headers": [(k.lower().encode(), v.encode()) for k, v in headers.items()],
        "query_string": b"",
    }
    request = Request(scope)
    # Attach a real-ish app with shell state. Request.app is read from scope,
    # so we patch it in via MagicMock since Request() doesn't accept app kw.
    app = MagicMock()
    app.state = MagicMock(spec=[])
    register_shell_state(
        app,
        ShellState(
            app_name="Test App",
            nav_items=[{"label": "Home", "route": "/app"}],
        ),
    )
    # Override the app property by setting on the underlying scope.
    request.scope["app"] = app
    return request


def test_full_document_when_not_boosted(stub_template: Any) -> None:
    """Regression: a normal (non-boosted) request still gets typed chrome.

    Phase 4 (v0.67.55): the chrome is now supplied by the typed `AppShell`
    primitive rather than the legacy Jinja `layouts/app_shell.html`. The
    helper extracts the project template's `content` block and wraps it
    in `Page → AppShell`. Title format is now `"{title} — {app_name}"`.
    Project-template-rendered chrome (the test stub's `<nav>shell-chrome</nav>`)
    is intentionally dropped — chrome is the framework's job."""
    from dazzle_back.runtime.shell import render_in_app_shell

    request = _make_request({})
    response = render_in_app_shell(
        request,
        template="_test_boost_page.html",
        title="Hello",
    )
    body = response.body.decode()
    assert "<html" in body.lower()
    assert "<main" in body.lower()
    assert "<title>Hello — Test App</title>" in body
    assert "page-body" in body


def test_partial_when_boosted_target_main_content(stub_template: Any) -> None:
    """The fix: HX-Boosted + HX-Target=main-content returns inner content only."""
    from dazzle_back.runtime.shell import render_in_app_shell

    request = _make_request({"HX-Boosted": "true", "HX-Target": "main-content"})
    response = render_in_app_shell(
        request,
        template="_test_boost_page.html",
        title="Hello",
    )
    body = response.body.decode()
    # No outer chrome.
    assert "<html" not in body.lower()
    assert "<head" not in body.lower()
    assert "<main" not in body.lower()
    assert "shell-chrome" not in body
    # Inner content is present.
    assert "page-body" in body
    assert "hello" in body


def test_partial_when_boosted_target_main_content_with_hash(
    stub_template: Any,
) -> None:
    """HX-Target may be sent as '#main-content' or 'main-content' — handle both."""
    from dazzle_back.runtime.shell import render_in_app_shell

    request = _make_request({"HX-Boosted": "true", "HX-Target": "#main-content"})
    response = render_in_app_shell(
        request,
        template="_test_boost_page.html",
    )
    body = response.body.decode()
    assert "<html" not in body.lower()
    assert "<main" not in body.lower()
    assert "page-body" in body


def test_full_document_when_boosted_but_target_is_other(
    stub_template: Any,
) -> None:
    """Boosted request targeting something else (e.g. a drawer) still gets
    full document path — the bug is specific to swapping into the main shell."""
    from dazzle_back.runtime.shell import render_in_app_shell

    request = _make_request({"HX-Boosted": "true", "HX-Target": "dz-detail-drawer-content"})
    response = render_in_app_shell(
        request,
        template="_test_boost_page.html",
    )
    body = response.body.decode()
    # Not the boosted+main-content combo, so we keep the full document path.
    assert "<html" in body.lower()


def test_partial_when_target_main_content_without_hx_boosted(
    stub_template: Any,
) -> None:
    """Issue #1021: sidebar nav links use explicit `hx-target="#main-content"`
    but never send `HX-Boosted: true`. The pre-fix `_is_boosted_main_content_swap`
    required both, so the partial path was skipped, the framework returned
    a full document into the swap target, and idiomorph crashed with
    `HierarchyRequestError` + duplicate view-transition-name. After the fix,
    `HX-Target` alone gates the partial path."""
    from dazzle_back.runtime.shell import render_in_app_shell

    request = _make_request({"HX-Target": "main-content"})  # no HX-Boosted
    response = render_in_app_shell(
        request,
        template="_test_boost_page.html",
    )
    body = response.body.decode()
    # Inner content only — outer chrome must not appear.
    assert "<html" not in body.lower()
    assert "<main" not in body.lower()
    assert "shell-chrome" not in body
    # Inner content is present.
    assert "page-body" in body


def test_partial_when_target_hash_main_content_without_hx_boosted(
    stub_template: Any,
) -> None:
    """Same as the previous test but with the leading-hash form
    `HX-Target=#main-content` — should be treated identically."""
    from dazzle_back.runtime.shell import render_in_app_shell

    request = _make_request({"HX-Target": "#main-content"})  # no HX-Boosted
    response = render_in_app_shell(
        request,
        template="_test_boost_page.html",
    )
    body = response.body.decode()
    assert "<html" not in body.lower()
    assert "<main" not in body.lower()
    assert "page-body" in body
