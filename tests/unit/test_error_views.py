"""Unit tests for Phase 2.A typed-Fragment error views.

Covers `build_site_404_view` + `build_site_403_view`: shape, copy,
action-link targets, escape safety, and the no-op `forbidden_detail`
kwarg on the 403 marketing variant.
"""

from __future__ import annotations

from dazzle.http.runtime.error_views import (
    build_site_403_view,
    build_site_404_view,
    build_site_500_view,
)
from dazzle.render.fragment.renderer import FragmentRenderer


def _render(page: object) -> str:
    return FragmentRenderer().render(page)  # type: ignore[arg-type]


# ───────────────── build_site_404_view ─────────────────


def test_404_view_announces_404() -> None:
    page = build_site_404_view(product_name="Acme")
    html = _render(page)
    assert "404" in html


def test_404_view_default_message() -> None:
    page = build_site_404_view(product_name="Acme")
    html = _render(page)
    assert "doesn" in html and "exist." in html


def test_404_view_custom_message_overrides_default() -> None:
    page = build_site_404_view(product_name="Acme", message="Custom not-found.")
    html = _render(page)
    assert "Custom not-found." in html


def test_404_view_has_go_home_link() -> None:
    page = build_site_404_view(product_name="Acme")
    html = _render(page)
    assert 'href="/"' in html
    assert "Go Home" in html


def test_404_view_renders_product_name() -> None:
    page = build_site_404_view(product_name="Acme")
    html = _render(page)
    assert "Acme" in html


def test_404_view_escapes_message() -> None:
    page = build_site_404_view(
        product_name="Acme",
        message="<script>alert(1)</script>",
    )
    html = _render(page)
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html


def test_404_view_escapes_product_name() -> None:
    page = build_site_404_view(product_name="<Acme>")
    html = _render(page)
    assert "<Acme>" not in html


def test_404_view_renders_no_form() -> None:
    page = build_site_404_view(product_name="Acme")
    html = _render(page)
    assert "<form" not in html


# ───────────────── build_site_403_view ─────────────────


def test_403_view_announces_403() -> None:
    page = build_site_403_view(product_name="Acme")
    html = _render(page)
    assert "403" in html


def test_403_view_default_message() -> None:
    page = build_site_403_view(product_name="Acme")
    html = _render(page)
    assert "permission" in html


def test_403_view_custom_message_overrides_default() -> None:
    page = build_site_403_view(
        product_name="Acme",
        message="You can't see this.",
    )
    html = _render(page)
    assert "You can" in html and "see this." in html


def test_403_view_has_dashboard_and_home_links() -> None:
    page = build_site_403_view(product_name="Acme")
    html = _render(page)
    assert 'href="/app"' in html
    assert 'href="/"' in html
    assert "Go to Dashboard" in html
    assert "Go Home" in html


def test_403_view_forbidden_detail_is_noop_for_marketing_variant() -> None:
    """The marketing-site 403 doesn't render persona disclosure —
    that lives in the app-shell `app/403.html` variant. Accepting
    the kwarg keeps the handler call site symmetric."""
    page_without = build_site_403_view(product_name="Acme")
    page_with = build_site_403_view(
        product_name="Acme",
        forbidden_detail={
            "entity": "Task",
            "operation": "create",
            "permitted_personas": ["admin"],
            "current_roles": ["viewer"],
        },
    )
    html_without = _render(page_without)
    html_with = _render(page_with)
    # Marketing variant doesn't render the detail — output is identical.
    assert html_with == html_without
    # And specifically, the persona names from the detail dict aren't
    # leaked into the marketing-site HTML.
    assert "admin" not in html_with
    assert "viewer" not in html_with


def test_403_view_escapes_message() -> None:
    page = build_site_403_view(
        product_name="Acme",
        message="<img src=x onerror=alert(1)>",
    )
    html = _render(page)
    assert "<img src=x onerror=alert(1)>" not in html
    assert "&lt;img" in html


def test_403_view_renders_no_form() -> None:
    page = build_site_403_view(product_name="Acme")
    html = _render(page)
    assert "<form" not in html


# ───────────────── build_site_500_view ─────────────────


def test_500_view_announces_500() -> None:
    page = build_site_500_view(product_name="Acme")
    html = _render(page)
    assert "500" in html


def test_500_view_renders_product_name() -> None:
    page = build_site_500_view(product_name="Acme")
    html = _render(page)
    assert "Acme" in html


def test_500_view_offers_two_ctas() -> None:
    page = build_site_500_view(product_name="Acme")
    html = _render(page)
    assert "Try again" in html
    assert "Go Home" in html


def test_500_view_does_not_leak_exception_message() -> None:
    """Surfacing exception details to the user leaks internals
    (CWE-209). The `message=` kwarg is accepted for forward
    symmetry but must NOT render into the page body."""
    page = build_site_500_view(
        product_name="Acme",
        message="<KeyError: 'totally_secret_internal_key'>",
    )
    html = _render(page)
    assert "totally_secret_internal_key" not in html
    assert "KeyError" not in html


def test_500_view_renders_generic_apology_copy() -> None:
    page = build_site_500_view(product_name="Acme")
    html = _render(page)
    assert "Something went wrong" in html or "try again" in html


def test_500_view_renders_no_form() -> None:
    page = build_site_500_view(product_name="Acme")
    html = _render(page)
    assert "<form" not in html


def test_500_view_escapes_product_name() -> None:
    page = build_site_500_view(product_name="<script>alert(1)</script>")
    html = _render(page)
    assert "<script>alert(1)</script>" not in html
