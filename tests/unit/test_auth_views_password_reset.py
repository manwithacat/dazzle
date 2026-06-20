"""Unit tests for the Phase 1.B.2 forgot/reset typed views.

Cover view shape, escape safety, error rendering, and the token
threading through `build_reset_password_view` — what the chrome=on
GET handlers in `site_routes.py` rely on.
"""

from __future__ import annotations

from dazzle.http.runtime.auth.auth_views import (
    build_forgot_password_sent_view,
    build_forgot_password_view,
    build_reset_password_done_view,
    build_reset_password_view,
)
from dazzle.render.fragment.renderer import FragmentRenderer


def _render(page: object) -> str:
    return FragmentRenderer().render(page)  # type: ignore[arg-type]


# ───────────────── build_forgot_password_view ─────────────────


def test_forgot_password_view_has_email_field() -> None:
    page = build_forgot_password_view(product_name="Acme")
    html = _render(page)
    assert 'type="email"' in html
    assert 'name="email"' in html


def test_forgot_password_view_posts_to_submit_endpoint() -> None:
    page = build_forgot_password_view(product_name="Acme")
    html = _render(page)
    assert "/auth/forgot-password/submit" in html


def test_forgot_password_view_no_password_field() -> None:
    """Forgot-password is account-recovery — no password field."""
    page = build_forgot_password_view(product_name="Acme")
    html = _render(page)
    assert 'type="password"' not in html


def test_forgot_password_view_uses_product_name_in_brand() -> None:
    page = build_forgot_password_view(product_name="Acme")
    html = _render(page)
    assert "Acme" in html


def test_forgot_password_view_renders_error_block() -> None:
    page = build_forgot_password_view(
        product_name="Acme",
        error_message="That email isn't registered.",
    )
    html = _render(page)
    assert "That email isn" in html and "registered." in html


def test_forgot_password_view_omits_error_block_when_empty() -> None:
    page = build_forgot_password_view(product_name="Acme")
    html = _render(page)
    assert "dz-text--danger" not in html or "tone=" not in html


def test_forgot_password_view_links_back_to_login() -> None:
    page = build_forgot_password_view(product_name="Acme")
    html = _render(page)
    assert 'href="/login"' in html


def test_forgot_password_view_escapes_error_message() -> None:
    page = build_forgot_password_view(
        product_name="Acme",
        error_message="<script>alert(1)</script>",
    )
    html = _render(page)
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html


def test_forgot_password_view_escapes_product_name() -> None:
    page = build_forgot_password_view(product_name="<Acme>")
    html = _render(page)
    assert "<Acme>" not in html.replace("<Acme>", "", 0) or "&lt;Acme&gt;" in html


# ───────────────── build_forgot_password_sent_view ─────────────────


def test_forgot_password_sent_view_account_enumeration_safe() -> None:
    """The default copy must NOT echo the submitted email."""
    page = build_forgot_password_sent_view(product_name="Acme")
    html = _render(page)
    assert "If an account exists" in html


def test_forgot_password_sent_view_offers_retry_link() -> None:
    page = build_forgot_password_sent_view(product_name="Acme")
    html = _render(page)
    assert 'href="/forgot-password"' in html


def test_forgot_password_sent_view_does_not_render_form() -> None:
    page = build_forgot_password_sent_view(product_name="Acme")
    html = _render(page)
    assert "<form" not in html


# ───────────────── build_reset_password_view ─────────────────


def test_reset_password_view_has_two_password_fields() -> None:
    page = build_reset_password_view(product_name="Acme", token="abc123")
    html = _render(page)
    assert html.count('type="password"') == 2


def test_reset_password_view_threads_token_into_form() -> None:
    page = build_reset_password_view(product_name="Acme", token="abc123")
    html = _render(page)
    assert 'value="abc123"' in html
    assert 'name="token"' in html


def test_reset_password_view_token_field_is_readonly() -> None:
    page = build_reset_password_view(product_name="Acme", token="abc123")
    html = _render(page)
    assert "readonly" in html


def test_reset_password_view_posts_to_submit_endpoint() -> None:
    page = build_reset_password_view(product_name="Acme", token="abc123")
    html = _render(page)
    assert "/auth/reset-password/submit" in html


def test_reset_password_view_renders_mismatch_error() -> None:
    page = build_reset_password_view(
        product_name="Acme",
        token="abc",
        error_message="The two password fields didn't match.",
    )
    html = _render(page)
    assert "didn" in html and "match." in html


def test_reset_password_view_escapes_token() -> None:
    """A malicious token value must NOT escape its attribute context."""
    page = build_reset_password_view(
        product_name="Acme",
        token='"><script>alert(1)</script>',
    )
    html = _render(page)
    assert "<script>alert(1)</script>" not in html


# ───────────────── build_reset_password_done_view ─────────────────


def test_reset_password_done_view_links_to_login() -> None:
    page = build_reset_password_done_view(product_name="Acme")
    html = _render(page)
    assert 'href="/login"' in html


def test_reset_password_done_view_no_form() -> None:
    page = build_reset_password_done_view(product_name="Acme")
    html = _render(page)
    assert "<form" not in html


def test_reset_password_done_view_announces_success() -> None:
    page = build_reset_password_done_view(product_name="Acme")
    html = _render(page)
    assert "Password updated" in html
