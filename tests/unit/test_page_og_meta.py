"""Unit tests for Page.og_meta (Phase 4, v0.67.42).

Closes the chrome=on OG-tag parity gap. The `Page` typed primitive now
carries both `meta` (rendered as `<meta name="...">`) and `og_meta`
(rendered as `<meta property="...">`) tuples — Twitter cards stay in
`meta` because they use `name="twitter:*"`.
"""

from __future__ import annotations

from dazzle.render.fragment import Page, Text
from dazzle.render.fragment.renderer import FragmentRenderer


def _render_head(page: Page) -> str:
    """Render `page` and return just the `<head>...</head>` slice."""
    html = FragmentRenderer().render(page)
    start = html.index("<head>")
    end = html.index("</head>") + len("</head>")
    return html[start:end]


def test_og_meta_field_defaults_to_empty_tuple() -> None:
    page = Page(title="t", body=Text(body="x"))
    assert page.og_meta == ()


def test_og_meta_emits_property_attribute() -> None:
    page = Page(
        title="t",
        body=Text(body="x"),
        og_meta=(("og:title", "Hello"),),
    )
    head = _render_head(page)
    assert '<meta property="og:title" content="Hello">' in head


def test_meta_field_still_emits_name_attribute() -> None:
    """Regression — adding og_meta must not break the existing `meta`
    rendering."""
    page = Page(
        title="t",
        body=Text(body="x"),
        meta=(("description", "Hello world"),),
    )
    head = _render_head(page)
    assert '<meta name="description" content="Hello world">' in head


def test_og_meta_and_meta_render_separately() -> None:
    page = Page(
        title="t",
        body=Text(body="x"),
        meta=(
            ("description", "D"),
            ("twitter:card", "summary"),
            ("twitter:title", "TT"),
        ),
        og_meta=(
            ("og:title", "OT"),
            ("og:description", "OD"),
            ("og:type", "website"),
        ),
    )
    head = _render_head(page)
    # name= entries
    assert '<meta name="description" content="D">' in head
    assert '<meta name="twitter:card" content="summary">' in head
    assert '<meta name="twitter:title" content="TT">' in head
    # property= entries
    assert '<meta property="og:title" content="OT">' in head
    assert '<meta property="og:description" content="OD">' in head
    assert '<meta property="og:type" content="website">' in head


def test_og_meta_escapes_attribute_values() -> None:
    """User-supplied OG content must escape inside the attribute
    context. A malicious payload must NOT break out of `content="..."`."""
    page = Page(
        title="t",
        body=Text(body="x"),
        og_meta=(("og:title", '"><script>alert(1)</script>'),),
    )
    head = _render_head(page)
    assert "<script>alert(1)</script>" not in head
    # Quote escaped — the payload can't terminate the content attribute.
    assert "&quot;" in head or "&#34;" in head


def test_og_meta_escapes_property_name() -> None:
    """The property key is developer-supplied but still gets escape-
    safety treatment as a defensive measure."""
    page = Page(
        title="t",
        body=Text(body="x"),
        og_meta=(('og:title" data-evil="', "x"),),
    )
    head = _render_head(page)
    # The attribute breakout payload doesn't survive escape_attr.
    assert 'data-evil="' not in head


def test_og_meta_renders_in_order() -> None:
    """Order is preserved (some OG consumers care about the order of
    og:image candidates)."""
    page = Page(
        title="t",
        body=Text(body="x"),
        og_meta=(
            ("og:image", "/img1.png"),
            ("og:image", "/img2.png"),
            ("og:image", "/img3.png"),
        ),
    )
    head = _render_head(page)
    i1 = head.index("/img1.png")
    i2 = head.index("/img2.png")
    i3 = head.index("/img3.png")
    assert i1 < i2 < i3


# ───────────────── build_page integration ─────────────────


def test_build_page_threads_og_meta_kwarg() -> None:
    from dazzle_back.runtime.renderers.page_builder import build_page
    from dazzle_ui.runtime.template_context import PageContext

    ctx = PageContext(page_title="Tasks", app_name="Acme", current_route="/")
    page = build_page(
        ctx,
        "<p>inner</p>",
        og_meta=(("og:title", "Tasks — Acme"),),
    )
    assert page.og_meta == (("og:title", "Tasks — Acme"),)
    head = _render_head(page)
    assert '<meta property="og:title" content="Tasks — Acme">' in head


def test_build_page_default_og_meta_is_empty() -> None:
    from dazzle_back.runtime.renderers.page_builder import build_page
    from dazzle_ui.runtime.template_context import PageContext

    ctx = PageContext(page_title="Tasks", app_name="Acme", current_route="/")
    page = build_page(ctx, "<p>inner</p>")
    assert page.og_meta == ()
