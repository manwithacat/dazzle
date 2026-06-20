"""Unit tests for the Phase 1.B.3 password-mode typed views.

Covers `build_login_password_view` + `build_signup_password_view`:
shape, action URLs, escape safety, error rendering, next-URL threading.
"""

from __future__ import annotations

from dazzle.http.runtime.auth.auth_views import (
    build_login_password_view,
    build_signup_password_view,
)
from dazzle.render.fragment.renderer import FragmentRenderer


def _render(page: object) -> str:
    return FragmentRenderer().render(page)  # type: ignore[arg-type]


# ───────────────── build_login_password_view ─────────────────


def test_login_password_view_has_email_and_password_fields() -> None:
    page = build_login_password_view(page_title="Sign in", product_name="Acme")
    html = _render(page)
    assert 'type="email"' in html
    assert 'type="password"' in html


def test_login_password_view_posts_to_password_endpoint() -> None:
    page = build_login_password_view(page_title="Sign in", product_name="Acme")
    html = _render(page)
    assert "/auth/login/password" in html


def test_login_password_view_threads_next_param() -> None:
    page = build_login_password_view(
        page_title="Sign in",
        product_name="Acme",
        next_url="/app/tasks",
    )
    html = _render(page)
    assert "next=/app/tasks" in html


def test_login_password_view_omits_next_when_default() -> None:
    page = build_login_password_view(page_title="Sign in", product_name="Acme")
    html = _render(page)
    assert "?next=" not in html


def test_login_password_view_renders_error_block() -> None:
    page = build_login_password_view(
        page_title="Sign in",
        product_name="Acme",
        error_message="That email and password didn't match.",
    )
    html = _render(page)
    assert "didn" in html and "match." in html


def test_login_password_view_omits_error_block_when_empty() -> None:
    page = build_login_password_view(page_title="Sign in", product_name="Acme")
    html = _render(page)
    # No error block: explicit error tone should not appear in body markup.
    assert "danger" not in html


def test_login_password_view_links_forgot_password() -> None:
    page = build_login_password_view(page_title="Sign in", product_name="Acme")
    html = _render(page)
    assert 'href="/forgot-password"' in html


def test_login_password_view_links_signup_crosslink() -> None:
    page = build_login_password_view(page_title="Sign in", product_name="Acme")
    html = _render(page)
    assert 'href="/signup"' in html


def test_login_password_view_escapes_error_message() -> None:
    page = build_login_password_view(
        page_title="Sign in",
        product_name="Acme",
        error_message="<script>alert(1)</script>",
    )
    html = _render(page)
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html


# ───────────────── build_signup_password_view ─────────────────


def test_signup_password_view_has_all_four_fields() -> None:
    page = build_signup_password_view(page_title="Create account", product_name="Acme")
    html = _render(page)
    assert 'name="name"' in html
    assert 'name="email"' in html
    assert 'name="password"' in html
    assert 'name="confirm_password"' in html


def test_signup_password_view_has_two_password_fields() -> None:
    page = build_signup_password_view(page_title="Create account", product_name="Acme")
    html = _render(page)
    assert html.count('type="password"') == 2


def test_signup_password_view_posts_to_password_endpoint() -> None:
    page = build_signup_password_view(page_title="Create account", product_name="Acme")
    html = _render(page)
    assert "/auth/signup/password" in html


def test_signup_password_view_threads_next_param() -> None:
    page = build_signup_password_view(
        page_title="Create account",
        product_name="Acme",
        next_url="/app/tasks",
    )
    html = _render(page)
    assert "next=/app/tasks" in html


def test_signup_password_view_renders_error_block() -> None:
    page = build_signup_password_view(
        page_title="Create account",
        product_name="Acme",
        error_message="The two password fields didn't match.",
    )
    html = _render(page)
    assert "didn" in html and "match." in html


def test_signup_password_view_links_signin_crosslink() -> None:
    page = build_signup_password_view(page_title="Create account", product_name="Acme")
    html = _render(page)
    assert 'href="/login"' in html


def test_signup_password_view_escapes_error_message() -> None:
    page = build_signup_password_view(
        page_title="Create account",
        product_name="Acme",
        error_message="<img src=x onerror=alert(1)>",
    )
    html = _render(page)
    assert "<img src=x onerror=alert(1)>" not in html
    assert "&lt;img" in html
