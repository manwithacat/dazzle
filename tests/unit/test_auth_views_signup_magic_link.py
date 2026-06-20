"""Issue #1037 Phase 1.B (v0.67.30): regression tests for
`build_signup_magic_link_view`.

Mirrors the v0.67.29 login-view test shape — magic-link mode,
account-enumeration safe, no password field. Adds a `name` field
for the new-user creation path.
"""

from __future__ import annotations

from dazzle.http.runtime.auth.auth_views import build_signup_magic_link_view
from dazzle.render.fragment import FragmentRenderer


def _render(page_fragment: object) -> str:
    return FragmentRenderer().render(page_fragment)


def test_signup_renders_name_and_email_fields() -> None:
    page = build_signup_magic_link_view(page_title="Create account", product_name="Test")
    html = _render(page)
    assert 'name="name"' in html
    assert 'type="email"' in html
    assert 'name="email"' in html


def test_signup_renders_no_password_field() -> None:
    """v1 default is passwordless — signup form must not present a
    password input. Password mode is opt-in per deployment."""
    page = build_signup_magic_link_view(page_title="Create account", product_name="Test")
    html = _render(page)
    assert 'type="password"' not in html


def test_signup_renders_no_confirm_password_field() -> None:
    """The legacy Jinja signup template had a confirm_password —
    irrelevant for magic-link flow."""
    page = build_signup_magic_link_view(page_title="Create account", product_name="Test")
    html = _render(page)
    assert 'name="confirm_password"' not in html


def test_signup_form_posts_to_signup_magic_link_endpoint() -> None:
    page = build_signup_magic_link_view(page_title="Create account", product_name="Test")
    html = _render(page)
    assert "/auth/signup/magic-link" in html


def test_signup_emits_submit_button() -> None:
    page = build_signup_magic_link_view(page_title="Create account", product_name="Test")
    html = _render(page)
    assert "Send sign-up link" in html


def test_signup_threads_next_url_through_form_action() -> None:
    page = build_signup_magic_link_view(
        page_title="Create account", product_name="Test", next_url="/onboarding"
    )
    html = _render(page)
    assert "next=/onboarding" in html


def test_signup_omits_next_param_for_root() -> None:
    page = build_signup_magic_link_view(
        page_title="Create account", product_name="Test", next_url="/"
    )
    html = _render(page)
    assert "?next=" not in html


def test_signup_renders_sign_in_link_for_returning_users() -> None:
    """Crosslink to /login so a returning user accidentally on
    /signup can navigate without re-typing their email."""
    page = build_signup_magic_link_view(page_title="Create account", product_name="Test")
    html = _render(page)
    assert 'href="/login"' in html
    assert "Sign in" in html


def test_signup_renders_error_message_when_provided() -> None:
    page = build_signup_magic_link_view(
        page_title="Create account",
        product_name="Test",
        error_message="That email is invalid.",
    )
    html = _render(page)
    assert "That email is invalid." in html


def test_signup_carries_typed_chrome_doctype() -> None:
    page = build_signup_magic_link_view(page_title="Create account", product_name="Test")
    html = _render(page)
    assert "<!DOCTYPE html>" in html or "<!doctype html>" in html


# ───────────────── HTML escape safety ────────────────────


def test_signup_escapes_product_name() -> None:
    page = build_signup_magic_link_view(
        page_title="Create account",
        product_name="<script>alert(1)</script>",
    )
    html = _render(page)
    assert "<script>alert(1)" not in html
    assert "&lt;script&gt;" in html


def test_signup_escapes_error_message() -> None:
    page = build_signup_magic_link_view(
        page_title="Create account",
        product_name="Test",
        error_message="<svg/>",
    )
    html = _render(page)
    assert "<svg/>" not in html
