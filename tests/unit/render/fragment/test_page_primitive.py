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


@pytest.mark.parametrize(
    ("kwargs", "match"),
    [
        pytest.param({"title": ""}, "non-empty title", id="empty-title"),
        pytest.param({"title": "X", "lang": ""}, "non-empty lang", id="empty-lang"),
    ],
)
def test_page_rejects(kwargs: dict, match: str) -> None:
    with pytest.raises(ValueError, match=match):
        Page(body=Text("x"), **kwargs)


def test_page_is_frozen() -> None:
    p = Page(title="X", body=Text("x"))
    with pytest.raises((FrozenInstanceError, AttributeError, TypeError)):
        p.title = "Y"  # type: ignore[misc]


@pytest.mark.parametrize(
    ("page", "present", "absent"),
    [
        # Defaults: lang=en, no theme, toast/modal/announcer slots on.
        pytest.param(
            Page(title="My Title", body=Text("x")),
            (
                '<html lang="en">',
                '<meta charset="UTF-8">',
                "viewport",
                "<title>My Title</title>",
                '<link rel="icon"',
                'id="dz-toast"',
                'id="dz-modal-slot"',
                'id="dz-page-announcer"',
            ),
            ("data-theme",),
            id="default-head-and-body-slots",
        ),
        # #1280: project theme identity lives on data-theme-name; data-theme is
        # JS-owned (site.js applyTheme writes light/dark on first paint), so SSR
        # writing the project name there was clobbered and selectors never matched.
        pytest.param(
            Page(title="X", body=Text("x"), lang="en", theme="dark"),
            ('<html lang="en" data-theme-name="dark">',),
            ('data-theme="dark"',),
            id="theme-on-data-theme-name-not-data-theme-1280",
        ),
        pytest.param(
            Page(title="<script>alert(1)</script>", body=Text("x")),
            ("&lt;script&gt;",),
            ("<script>alert",),
            id="title-escaped",
        ),
        # #1279: the default cascade_layer_order includes every layer the bundled
        # dazzle.min.css declares, in canonical order — reset/vendor/tokens
        # lowest, framework/app after components, overrides last. The old
        # 4-name list let framework component rules win over project overrides.
        pytest.param(
            Page(title="X", body=Text("x")),
            (
                "<style>@layer reset, vendor, tokens, base, utilities, components, "
                "framework, app, overrides;</style>",
            ),
            (),
            id="default-cascade-layer-order-1279",
        ),
        pytest.param(
            Page(title="X", body=Text("x"), js_scripts=("/static/dazzle.min.js",)),
            ('<script defer src="/static/dazzle.min.js"></script>',),
            (),
            id="deferred-js-scripts",
        ),
        pytest.param(
            Page(title="X", body=Text("x"), meta=(("dz-haptic", "on"), ("description", "test"))),
            ('<meta name="dz-haptic" content="on">', '<meta name="description" content="test">'),
            (),
            id="custom-meta-tags",
        ),
        # Cycle 2140: search-select leftover form owner (Nu rejects form="").
        pytest.param(
            Page(title="X", body=Heading("Welcome", level=1)),
            ('<body class="dz-page">', "Welcome", '<form id="hm-detached-q" hidden></form>'),
            (),
            id="body-class-and-body-fragment",
        ),
        pytest.param(
            Page(
                title="X",
                body=Text("x"),
                toast_container=False,
                modal_slot=False,
                page_announcer=False,
            ),
            (),
            ("dz-toast", "dz-modal-slot", "dz-page-announcer"),
            id="optional-body-slots-disabled",
        ),
        pytest.param(
            Page(
                title="Tasks",
                theme="dark",
                css_links=("/static/dazzle.min.css",),
                js_scripts=("/static/dazzle.min.js",),
                body=Surface(header=Heading("Tasks", level=1), body=Text("Empty")),
            ),
            ('<html lang="en" data-theme-name="dark">', '<section class="dz-surface">', "Tasks"),
            (),
            id="surface-body-composition",
        ),
    ],
)
def test_page_renders(page: Page, present: tuple[str, ...], absent: tuple[str, ...]) -> None:
    html = _render(page)
    assert html.startswith("<!DOCTYPE html>")
    assert html.endswith("</body></html>")
    assert [s for s in present if s not in html] == []
    assert [s for s in absent if s in html] == []


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


# #1854: page-context data attributes on <body>.
def test_page_body_attrs_are_emitted_and_escaped() -> None:
    page = Page(
        title="X",
        body=Text("x"),
        body_attrs=(("data-dz-surface", "tasks"), ("data-dz-record", 'a"b'), ("data-dz-empty", "")),
    )
    html = _render(page)
    assert '<body class="dz-page" data-dz-surface="tasks" data-dz-record="a&quot;b">' in html
    assert "data-dz-empty" not in html


@pytest.mark.parametrize("name", ["onload", "data-", "data-Dz-x", "class"])
def test_page_body_attrs_names_are_restricted(name: str) -> None:
    with pytest.raises(ValueError, match="body_attrs names"):
        Page(title="X", body=Text("x"), body_attrs=((name, "v"),))
