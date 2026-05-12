"""PageBuilder: PageContext → Page primitive adapter (Plan 17 P2)."""

from __future__ import annotations

from dazzle.back.runtime.renderers.page_builder import build_page, dispatch_render_page
from dazzle.render.fragment import Page


class _FakePageContext:
    """Minimal PageContext stub — only the fields PageBuilder reads."""

    def __init__(self, page_title: str = "Tasks", app_name: str = "Demo App") -> None:
        self.page_title = page_title
        self.app_name = app_name


# ───────────────── build_page ─────────────────────────────────────


def test_build_page_combines_title_with_app_name() -> None:
    ctx = _FakePageContext(page_title="Tasks", app_name="Demo App")
    page = build_page(ctx, inner_html="<p>body</p>")
    assert isinstance(page, Page)
    assert page.title == "Tasks — Demo App"


def test_build_page_falls_back_to_app_name_when_no_page_title() -> None:
    ctx = _FakePageContext(page_title="", app_name="Demo App")
    page = build_page(ctx, inner_html="<p>body</p>")
    assert page.title == "Demo App"


def test_build_page_strips_whitespace_from_title_components() -> None:
    ctx = _FakePageContext(page_title="  Tasks  ", app_name="  Demo  ")
    page = build_page(ctx, inner_html="x")
    assert page.title == "Tasks — Demo"


def test_build_page_defaults_app_name_to_dazzle_when_empty() -> None:
    ctx = _FakePageContext(page_title="", app_name="")
    page = build_page(ctx, inner_html="x")
    assert page.title == "Dazzle"


def test_build_page_threads_inner_html_into_body_via_rawhtml() -> None:
    """Inner HTML is the already-rendered surface body — must compose
    into Page.body as RawHTML so the renderer doesn't re-escape it."""
    from dazzle.render.fragment.escape import RawHTML

    ctx = _FakePageContext()
    page = build_page(ctx, inner_html='<section class="dz-surface"><p>hi</p></section>')
    assert isinstance(page.body, RawHTML)
    # RawHTML stores the html string in some attribute; access generically:
    body_str = str(page.body)
    assert "dz-surface" in body_str or "<p>hi</p>" in body_str


def test_build_page_threads_assets_through() -> None:
    ctx = _FakePageContext()
    page = build_page(
        ctx,
        inner_html="x",
        css_links=("/static/dazzle.min.css",),
        js_scripts=("/static/dazzle.min.js",),
        theme="dark",
        favicon="/img/icon.svg",
        extra_meta=(("dz-haptic", "on"),),
    )
    assert page.css_links == ("/static/dazzle.min.css",)
    assert page.js_scripts == ("/static/dazzle.min.js",)
    assert page.theme == "dark"
    assert page.favicon == "/img/icon.svg"
    assert page.meta == (("dz-haptic", "on"),)


# ───────────────── dispatch_render_page ───────────────────────────


def test_dispatch_render_page_returns_full_html_document() -> None:
    ctx = _FakePageContext(page_title="Tasks", app_name="Demo")
    html = dispatch_render_page(
        ctx,
        inner_html='<section class="dz-surface"><h1>Tasks</h1></section>',
        css_links=("/static/dazzle.min.css",),
        js_scripts=("/static/dazzle.min.js",),
        theme="linear-dark",
    )
    assert html.startswith("<!DOCTYPE html>")
    assert '<html lang="en" data-theme="linear-dark">' in html
    assert "<title>Tasks — Demo</title>" in html
    assert '<link rel="stylesheet" href="/static/dazzle.min.css">' in html
    assert '<script defer src="/static/dazzle.min.js"></script>' in html
    # Inner HTML composed into body unchanged
    assert '<section class="dz-surface"><h1>Tasks</h1></section>' in html
    assert html.endswith("</body></html>")


def test_dispatch_render_page_inner_html_not_escaped() -> None:
    """The inner HTML is pre-rendered — must arrive in the body
    verbatim, not HTML-escaped."""
    ctx = _FakePageContext()
    html = dispatch_render_page(ctx, inner_html='<section class="x">raw &amp; cooked</section>')
    # If the inner_html was re-escaped, we'd see "&amp;amp;" or
    # "&lt;section". Neither should appear.
    assert "&lt;section" not in html
    assert "&amp;amp;" not in html
    assert '<section class="x">raw &amp; cooked</section>' in html
