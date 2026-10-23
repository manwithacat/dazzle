"""Issue #1037 Phase 1.A (v0.67.29): regression tests for the typed-
Fragment auth views — `build_login_magic_link_view` and
`build_login_sent_view`.

First module of the Jinja2 retirement Phase 1 work. The chrome=on
path renders these typed views; chrome=off keeps using the legacy
Jinja templates during the migration.

One table: each row builds a view with some inputs and pins the
substrings the rendered HTML must contain and must not contain.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest

from dazzle.http.runtime.auth.auth_views import (
    build_login_magic_link_view,
    build_login_sent_view,
)
from dazzle.http.runtime.auth.magic_link import EMAIL_MAGIC_LINK_TTL
from dazzle.render.fragment import FragmentRenderer

_LOGIN = build_login_magic_link_view
_SENT = build_login_sent_view
_SIGN_IN: dict[str, Any] = {"page_title": "Sign in", "product_name": "Test"}


@pytest.mark.parametrize(
    ("build", "kwargs", "present", "absent"),
    [
        # ───────────────── login (magic-link) ─────────────────
        pytest.param(
            _LOGIN,
            _SIGN_IN,
            ('type="email"', 'name="email"', "required"),
            # No password field — magic-link is the v1 default flow.
            ('type="password"',),
            id="login-email-only-form",
        ),
        pytest.param(
            _LOGIN,
            _SIGN_IN,
            ('hx-post="/auth/login/magic-link"',),
            (),
            id="login-posts-to-magic-link-issuance-endpoint",
        ),
        pytest.param(
            _LOGIN,
            {"page_title": "Sign in", "product_name": "Acme Co"},
            (">Acme Co<", 'href="/"'),
            (),
            id="login-product-name-links-to-root",
        ),
        pytest.param(
            _LOGIN, _SIGN_IN, ("<h1", ">Sign in</h1>"), (), id="login-page-title-in-heading"
        ),
        pytest.param(_LOGIN, _SIGN_IN, ("Send sign-in link",), (), id="login-submit-button"),
        # The next-URL preserves the originally-requested page so the
        # consumed magic link lands the user there, not the dashboard.
        pytest.param(
            _LOGIN,
            {**_SIGN_IN, "next_url": "/app/tasks"},
            ("next=/app/tasks",),
            (),
            id="login-threads-next-url-through-form-action",
        ),
        # Default next_url='/' shouldn't pollute the form action.
        pytest.param(
            _LOGIN, {**_SIGN_IN, "next_url": "/"}, (), ("?next=",), id="login-omits-next-for-root"
        ),
        # Used when the user just consumed an invalid/expired link.
        pytest.param(
            _LOGIN,
            {**_SIGN_IN, "error_message": "That link is no good."},
            ("That link is no good.",),
            (),
            id="login-renders-error-message",
        ),
        pytest.param(_LOGIN, _SIGN_IN, (), ("dz-text-danger",), id="login-no-error-block"),
        # The typed Page primitive emits a real HTML document shell.
        pytest.param(
            _LOGIN, _SIGN_IN, ("<!DOCTYPE html>", "<html"), (), id="login-typed-chrome-doctype"
        ),
        pytest.param(
            _LOGIN,
            _SIGN_IN,
            ("/static/dist/dazzle.min.css", "/static/dist/dazzle.min.js"),
            (),
            id="login-default-css-and-js",
        ),
        pytest.param(
            _LOGIN,
            {
                **_SIGN_IN,
                "css_links": ("/static/themes/dark.css",),
                "js_scripts": ("/static/themes/dark.js",),
            },
            ("/static/themes/dark.css", "/static/themes/dark.js"),
            ("/static/dist/dazzle.min.css", "/static/dist/dazzle.min.js"),
            id="login-custom-css-and-js-override-defaults",
        ),
        # ───────────────── login/sent (confirmation) ─────────────────
        pytest.param(
            _SENT, {"product_name": "Test"}, ("Check your inbox",), (), id="sent-check-inbox"
        ),
        # Empty email: defensively ambiguous, never confirms the address.
        pytest.param(
            _SENT,
            {"product_name": "Test", "email": ""},
            ("If an account exists",),
            (),
            id="sent-account-enumeration-safe-default",
        ),
        # Some flows (authenticated session) echo the email back.
        pytest.param(
            _SENT,
            {"product_name": "Test", "email": "alice@example.com"},
            ("alice@example.com",),
            ("If an account exists",),
            id="sent-echoes-explicit-email",
        ),
        pytest.param(
            _SENT,
            {"product_name": "Test"},
            ('href="/login"', "try a different email"),
            (),
            id="sent-try-different-email-link",
        ),
        pytest.param(
            _SENT, {"product_name": "Acme Co"}, (">Acme Co<",), (), id="sent-product-name-link"
        ),
        # #1842 (WCAG 2.2.1): the link lifetime is stated, from the TTL constant.
        pytest.param(
            _SENT,
            {"product_name": "Test"},
            (f"The link expires in {int(EMAIL_MAGIC_LINK_TTL.total_seconds() // 60)} minutes.",),
            (),
            id="sent-states-link-expiry",
        ),
        pytest.param(
            _SENT,
            {"product_name": "Test"},
            ("<!DOCTYPE html>",),
            (),
            id="sent-typed-chrome-doctype",
        ),
        # ───────────────── HTML escape safety ─────────────────
        pytest.param(
            _LOGIN,
            {"page_title": "Sign in", "product_name": "<script>alert(1)</script>"},
            ("&lt;script&gt;",),
            ("<script>alert(1)",),
            id="login-escapes-product-name",
        ),
        pytest.param(
            _LOGIN,
            {"page_title": "<img src=x onerror=alert(1)>", "product_name": "Test"},
            (),
            ("<img src=x",),
            id="login-escapes-page-title",
        ),
        pytest.param(
            _LOGIN,
            {**_SIGN_IN, "error_message": "<svg onload=alert(1)>"},
            ("&lt;svg",),
            ("<svg",),
            id="login-escapes-error-message",
        ),
        pytest.param(
            _SENT,
            {"product_name": "Test", "email": "<script>alert(1)</script>"},
            ("&lt;script&gt;",),
            ("<script>",),
            id="sent-escapes-echoed-email",
        ),
    ],
)
def test_auth_view_renders(
    build: Callable[..., object],
    kwargs: dict[str, Any],
    present: tuple[str, ...],
    absent: tuple[str, ...],
) -> None:
    html = FragmentRenderer().render(build(**kwargs))
    for needle in present:
        assert needle in html
    for needle in absent:
        assert needle not in html
