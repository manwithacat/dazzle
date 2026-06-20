"""Issue #1037 Phase 1.A (v0.67.29): regression tests for the typed-
Fragment auth views — `build_login_magic_link_view` and
`build_login_sent_view`.

First module of the Jinja2 retirement Phase 1 work. The chrome=on
path renders these typed views; chrome=off keeps using the legacy
Jinja templates during the migration.
"""

from __future__ import annotations

from dazzle.http.runtime.auth.auth_views import (
    build_login_magic_link_view,
    build_login_sent_view,
)
from dazzle.render.fragment import FragmentRenderer


def _render(page_fragment: object) -> str:
    return FragmentRenderer().render(page_fragment)


# ───────────────── login (magic-link) ────────────────────


def test_login_renders_email_only_form() -> None:
    page = build_login_magic_link_view(page_title="Sign in", product_name="Test")
    html = _render(page)
    assert 'type="email"' in html
    assert 'name="email"' in html
    assert "required" in html
    # No password field — magic-link is the v1 default flow.
    assert 'type="password"' not in html


def test_login_form_posts_to_magic_link_issuance_endpoint() -> None:
    page = build_login_magic_link_view(page_title="Sign in", product_name="Test")
    html = _render(page)
    # FormStack uses hx-post for typed forms.
    assert "/auth/login/magic-link" in html


def test_login_emits_product_name_link_to_root() -> None:
    page = build_login_magic_link_view(page_title="Sign in", product_name="Acme Co")
    html = _render(page)
    assert ">Acme Co<" in html
    assert 'href="/"' in html


def test_login_renders_page_title_in_heading() -> None:
    page = build_login_magic_link_view(page_title="Sign in", product_name="Test")
    html = _render(page)
    # Heading primitive emits h1 with framework class attrs.
    assert "<h1" in html and ">Sign in</h1>" in html


def test_login_emits_submit_button() -> None:
    page = build_login_magic_link_view(page_title="Sign in", product_name="Test")
    html = _render(page)
    assert "Send sign-in link" in html


def test_login_threads_next_url_through_form_action() -> None:
    """The next-URL preserves the originally-requested page so the
    consumed magic link lands the user there, not the dashboard."""
    page = build_login_magic_link_view(
        page_title="Sign in", product_name="Test", next_url="/app/tasks"
    )
    html = _render(page)
    assert "next=/app/tasks" in html


def test_login_omits_next_param_for_root() -> None:
    """Default next_url='/' shouldn't pollute the form action with
    a noisy `?next=/` query string."""
    page = build_login_magic_link_view(page_title="Sign in", product_name="Test", next_url="/")
    html = _render(page)
    assert "?next=" not in html


def test_login_renders_error_message_when_provided() -> None:
    """Used when the user just consumed an invalid/expired link
    and got bounced back here."""
    page = build_login_magic_link_view(
        page_title="Sign in",
        product_name="Test",
        error_message="That link is no good.",
    )
    html = _render(page)
    assert "That link is no good." in html


def test_login_omits_error_block_when_no_error() -> None:
    page = build_login_magic_link_view(page_title="Sign in", product_name="Test")
    html = _render(page)
    # No danger-tone Text element should fire.
    assert "dz-text-danger" not in html


def test_login_page_carries_typed_chrome_doctype() -> None:
    """Sanity: the typed Page primitive emits a real HTML document
    shell, not just a fragment."""
    page = build_login_magic_link_view(page_title="Sign in", product_name="Test")
    html = _render(page)
    assert "<!DOCTYPE html>" in html or "<!doctype html>" in html
    assert "<html" in html


def test_login_default_css_and_js_links() -> None:
    page = build_login_magic_link_view(page_title="Sign in", product_name="Test")
    html = _render(page)
    assert "/static/dist/dazzle.min.css" in html
    assert "/static/dist/dazzle.min.js" in html


def test_login_custom_css_and_js_overrides_defaults() -> None:
    page = build_login_magic_link_view(
        page_title="Sign in",
        product_name="Test",
        css_links=("/static/themes/dark.css",),
        js_scripts=("/static/themes/dark.js",),
    )
    html = _render(page)
    assert "/static/themes/dark.css" in html
    assert "/static/dist/dazzle.min.css" not in html


# ───────────────── login/sent (confirmation) ────────────────────


def test_sent_view_renders_check_inbox_message() -> None:
    page = build_login_sent_view(product_name="Test")
    html = _render(page)
    assert "Check your inbox" in html


def test_sent_view_uses_account_enumeration_safe_default() -> None:
    """When email is empty, the message must be defensively
    ambiguous — 'if an account exists' rather than confirming the
    address."""
    page = build_login_sent_view(product_name="Test", email="")
    html = _render(page)
    assert "If an account exists" in html


def test_sent_view_echoes_email_when_explicitly_provided() -> None:
    """Some flows are willing to echo the email back (e.g. when
    invoked from an authenticated session). Test both shapes."""
    page = build_login_sent_view(product_name="Test", email="alice@example.com")
    html = _render(page)
    assert "alice@example.com" in html
    assert "If an account exists" not in html


def test_sent_view_has_try_different_email_link() -> None:
    page = build_login_sent_view(product_name="Test")
    html = _render(page)
    assert 'href="/login"' in html
    assert "try a different email" in html


def test_sent_view_emits_product_name_link() -> None:
    page = build_login_sent_view(product_name="Acme Co")
    html = _render(page)
    assert ">Acme Co<" in html


def test_sent_view_carries_typed_chrome_doctype() -> None:
    page = build_login_sent_view(product_name="Test")
    html = _render(page)
    assert "<!DOCTYPE html>" in html or "<!doctype html>" in html


# ───────────────── HTML escape safety ────────────────────


def test_login_escapes_product_name() -> None:
    page = build_login_magic_link_view(
        page_title="Sign in", product_name="<script>alert(1)</script>"
    )
    html = _render(page)
    assert "<script>alert(1)" not in html
    assert "&lt;script&gt;" in html


def test_login_escapes_page_title() -> None:
    page = build_login_magic_link_view(
        page_title="<img src=x onerror=alert(1)>", product_name="Test"
    )
    html = _render(page)
    assert "<img src=x" not in html


def test_login_escapes_error_message() -> None:
    page = build_login_magic_link_view(
        page_title="Sign in",
        product_name="Test",
        error_message="<svg onload=alert(1)>",
    )
    html = _render(page)
    assert "<svg" not in html
    assert "&lt;svg" in html


def test_sent_view_escapes_email_when_echoed() -> None:
    page = build_login_sent_view(product_name="Test", email="<script>alert(1)</script>")
    html = _render(page)
    assert "<script>" not in html
    assert "&lt;script&gt;" in html
