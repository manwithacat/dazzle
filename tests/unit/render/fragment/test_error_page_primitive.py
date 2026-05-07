"""ErrorPage primitive — standalone error/auth page (P17 Phase 11)."""

import pytest

from dazzle.render.fragment import URL, ErrorPage, Page
from dazzle.render.fragment.renderer import FragmentRenderer


def _render(node: object) -> str:
    return FragmentRenderer().render(node)


# ───────────────── Construction ─────────────────────────


def test_error_page_minimal_construction() -> None:
    e = ErrorPage(code=404, message="Not Found")
    assert e.code == 404
    assert e.message == "Not Found"
    assert e.home_href is None
    assert e.home_label == "Go home"


def test_error_page_with_home_link() -> None:
    e = ErrorPage(
        code=500,
        message="Server error",
        home_href=URL("/"),
        home_label="Back to dashboard",
    )
    assert e.home_label == "Back to dashboard"


def test_error_page_rejects_empty_message() -> None:
    with pytest.raises(ValueError, match="non-empty message"):
        ErrorPage(code=404, message="")


# ───────────────── Renderer output ─────────────────────


def test_error_page_emits_section_with_code_and_message() -> None:
    html = _render(ErrorPage(code=404, message="Not Found"))
    assert '<section class="dz-error-page"' in html
    assert 'data-dz-error-code="404"' in html
    assert '<h1 class="dz-error-page__code">404</h1>' in html
    assert '<p class="dz-error-page__message">Not Found</p>' in html


def test_error_page_omits_home_link_when_no_href() -> None:
    html = _render(ErrorPage(code=404, message="Not Found"))
    assert "dz-error-page__action" not in html


def test_error_page_emits_home_link_when_href_set() -> None:
    html = _render(ErrorPage(code=404, message="Not Found", home_href=URL("/dashboard")))
    assert '<a class="dz-error-page__action" href="/dashboard">Go home</a>' in html


def test_error_page_home_label_customisable() -> None:
    html = _render(
        ErrorPage(
            code=403,
            message="Forbidden",
            home_href=URL("/login"),
            home_label="Sign in",
        )
    )
    assert "Sign in</a>" in html
    assert "Go home" not in html


def test_error_page_message_is_html_escaped() -> None:
    html = _render(ErrorPage(code=500, message="<script>alert(1)</script>"))
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;alert" in html


def test_error_page_home_href_escaped_in_attribute() -> None:
    """home_href is a typed URL — disallowed schemes can't slip through."""
    with pytest.raises(ValueError, match="disallowed scheme"):
        URL("javascript:alert(1)")


def test_error_page_home_href_non_url_value_does_not_render_link() -> None:
    """Defensive: if a caller passes something that isn't a URL
    (raw string, etc.), the link is not rendered. The home_href
    field is typed `object | None` to avoid an import cycle, so
    runtime check is the safety net."""
    # Pass a bare string instead of URL — link should be omitted
    html = _render(ErrorPage(code=404, message="X", home_href="/raw"))  # type: ignore[arg-type]
    assert "dz-error-page__action" not in html


# ───────────────── Composition with Page ──────────────


def test_error_page_inside_page_renders_full_document() -> None:
    """Canonical use: Page chrome wrapping an ErrorPage in body —
    no AppShell needed for error/auth routes."""
    html = _render(
        Page(
            title="Page not found — My App",
            body=ErrorPage(
                code=404,
                message="The page you requested doesn't exist.",
                home_href=URL("/"),
            ),
        )
    )
    assert "<!DOCTYPE html>" in html
    assert "<title>Page not found — My App</title>" in html
    assert '<body class="dz-page">' in html
    assert '<section class="dz-error-page"' in html
    # No AppShell chrome present (no sidebar/topbar/main markup)
    assert "dz-app-shell" not in html
    assert "dz-app-main" not in html
