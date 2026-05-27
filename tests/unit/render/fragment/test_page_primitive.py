"""Page primitive — typed HTML document chrome.

Plan 17 P1: substrate-only test. The Page primitive wraps the entire
document; tests pin (a) construction invariants, (b) renderer output
structure (DOCTYPE, html/head/body composition), (c) optional slots
(toast, modal, page-announcer)."""

from dataclasses import FrozenInstanceError

import pytest

from dazzle.render.fragment import Heading, Page, Surface, Text
from dazzle.render.fragment.renderer import FragmentRenderer


def _render(node: object) -> str:
    return FragmentRenderer().render(node)


# ───────────────── Construction invariants ─────────────────


def test_page_minimal_construction() -> None:
    p = Page(title="Hello", body=Text("body"))
    assert p.title == "Hello"
    assert p.lang == "en"
    assert p.theme is None
    assert p.css_links == ()
    assert p.js_scripts == ()
    assert p.meta == ()
    assert p.toast_container is True
    assert p.modal_slot is True
    assert p.page_announcer is True


def test_page_rejects_empty_title() -> None:
    with pytest.raises(ValueError, match="non-empty title"):
        Page(title="", body=Text("x"))


def test_page_rejects_empty_lang() -> None:
    with pytest.raises(ValueError, match="non-empty lang"):
        Page(title="X", body=Text("x"), lang="")


def test_page_is_frozen() -> None:
    p = Page(title="X", body=Text("x"))
    with pytest.raises((FrozenInstanceError, AttributeError, TypeError)):
        p.title = "Y"  # type: ignore[misc]


# ───────────────── Renderer output ─────────────────────────


def test_page_emits_doctype() -> None:
    html = _render(Page(title="X", body=Text("x")))
    assert html.startswith("<!DOCTYPE html>")


def test_page_emits_html_with_lang_and_optional_theme() -> None:
    html = _render(Page(title="X", body=Text("x"), lang="en", theme="dark"))
    # #1280: project theme identity moved from `data-theme` to
    # `data-theme-name`. `data-theme` is now JS-owned for colour scheme.
    assert '<html lang="en" data-theme-name="dark">' in html


def test_page_omits_theme_attr_when_none() -> None:
    html = _render(Page(title="X", body=Text("x")))
    assert "<html" in html


def test_page_emits_data_theme_name_not_data_theme_1280() -> None:
    """#1280: SSR sets ONLY `data-theme-name` for project theme identity.
    `data-theme` is left absent so the runtime `static/js/site.js`
    `applyTheme()` call on first paint can write it to `light` or `dark`
    without overwriting the project identity. Pre-fix the renderer
    emitted `data-theme="stripe"` and the JS clobbered it on first
    paint — `[data-theme="stripe"]` CSS selectors never matched in the
    live DOM."""
    html = _render(Page(title="X", body=Text("x"), theme="stripe"))
    assert 'data-theme-name="stripe"' in html, (
        "Project theme identity must be on data-theme-name (#1280)"
    )
    # The bare `data-theme="stripe"` attribute MUST NOT be emitted —
    # it's reserved for the JS-written colour scheme.
    assert 'data-theme="stripe"' not in html, (
        "data-theme is JS-owned for colour scheme; SSR must not write the project name there (#1280)"
    )


def test_page_emits_head_with_charset_viewport_title_favicon() -> None:
    html = _render(Page(title="My Title", body=Text("x")))
    assert '<meta charset="UTF-8">' in html
    assert "<meta" in html and "viewport" in html
    assert "<title>My Title</title>" in html
    assert '<link rel="icon"' in html


def test_page_title_is_escaped() -> None:
    html = _render(Page(title="<script>alert(1)</script>", body=Text("x")))
    # Title text must be escaped, not raw.
    assert "<script>alert" not in html
    assert "&lt;script&gt;" in html


def test_page_includes_cascade_layer_declaration() -> None:
    """#1279: the default `cascade_layer_order` must include every layer
    the bundled `dazzle.min.css` declares, in canonical order. The 4-name
    list `base, framework, app, overrides` was wrong — it left `components`,
    `utilities`, `reset`, `vendor`, `tokens` to land AFTER `overrides`,
    inverting the cascade and letting framework component rules win over
    project overrides."""
    html = _render(Page(title="X", body=Text("x")))
    assert (
        "<style>@layer reset, vendor, tokens, base, utilities, components, "
        "framework, app, overrides;</style>" in html
    )


def test_default_layer_order_starts_with_framework_layers_1279() -> None:
    """#1279: `reset`, `vendor`, `tokens` MUST come first so they have
    the lowest priority; `overrides` MUST come last so project authors
    can over-ride anything by writing `@layer overrides { ... }`. The
    `framework` and `app` project slots sit between `components` and
    `overrides`."""
    from dazzle.render.fragment.primitives.containers import Page

    order = Page(title="X", body=Text("x")).cascade_layer_order.split(", ")
    assert order[0] == "reset"
    assert order[-1] == "overrides"
    assert "framework" in order
    assert "app" in order
    # framework + app project slots come AFTER components (so project
    # component CSS can target framework component primitives without
    # losing to the framework's own rules).
    assert order.index("components") < order.index("framework") < order.index("overrides")


def test_page_emits_css_links_in_order() -> None:
    html = _render(
        Page(
            title="X",
            body=Text("x"),
            css_links=("/static/dazzle.min.css", "/static/themes/dark.css"),
        )
    )
    a = html.index('href="/static/dazzle.min.css"')
    b = html.index('href="/static/themes/dark.css"')
    assert a < b, "css_links must render in declaration order"


def test_page_emits_deferred_js_scripts() -> None:
    html = _render(
        Page(
            title="X",
            body=Text("x"),
            js_scripts=("/static/dazzle.min.js",),
        )
    )
    assert '<script defer src="/static/dazzle.min.js"></script>' in html


def test_page_emits_custom_meta_tags() -> None:
    html = _render(
        Page(
            title="X",
            body=Text("x"),
            meta=(("dz-haptic", "on"), ("description", "test")),
        )
    )
    assert '<meta name="dz-haptic" content="on">' in html
    assert '<meta name="description" content="test">' in html


def test_page_emits_body_with_dz_page_class_and_renders_body_fragment() -> None:
    html = _render(Page(title="X", body=Heading("Welcome", level=1)))
    assert '<body class="dz-page">' in html
    assert "Welcome" in html


def test_page_default_emits_toast_modal_announcer_slots() -> None:
    html = _render(Page(title="X", body=Text("x")))
    assert 'id="dz-toast"' in html
    assert 'id="dz-modal-slot"' in html
    assert 'id="dz-page-announcer"' in html


def test_page_can_disable_optional_body_slots() -> None:
    html = _render(
        Page(
            title="X",
            body=Text("x"),
            toast_container=False,
            modal_slot=False,
            page_announcer=False,
        )
    )
    assert "dz-toast" not in html
    assert "dz-modal-slot" not in html
    assert "dz-page-announcer" not in html


def test_page_closes_html_and_body_correctly() -> None:
    html = _render(Page(title="X", body=Text("x")))
    assert html.endswith("</body></html>")


def test_page_with_surface_body_composes_correctly() -> None:
    """End-to-end: Page wrapping a Surface (the canonical composition)."""
    page = Page(
        title="Tasks",
        theme="dark",
        css_links=("/static/dazzle.min.css",),
        js_scripts=("/static/dazzle.min.js",),
        body=Surface(header=Heading("Tasks", level=1), body=Text("Empty")),
    )
    html = _render(page)
    # Outer chrome
    assert "<!DOCTYPE html>" in html
    # #1280: project theme identity moved from `data-theme` to
    # `data-theme-name`. `data-theme` is now JS-owned for colour scheme.
    assert '<html lang="en" data-theme-name="dark">' in html
    # Surface inside body
    assert '<section class="dz-surface">' in html
    assert "Tasks" in html
