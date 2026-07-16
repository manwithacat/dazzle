"""Topbar primitive — application top bar (P17 Phase 7)."""

from dazzle.render.fragment import (
    URL,
    AppShell,
    Button,
    NavItem,
    Page,
    Sidebar,
    Text,
    Topbar,
)
from dazzle.render.fragment.renderer import FragmentRenderer


def _render(node: object) -> str:
    return FragmentRenderer().render(node)


# ───────────────── Construction ─────────────────────────


def test_topbar_minimal_construction() -> None:
    t = Topbar()
    assert t.title == ""
    assert t.leading is None
    assert t.trailing is None


def test_topbar_with_title_only() -> None:
    t = Topbar(title="My App")
    assert t.title == "My App"


def test_topbar_with_all_slots() -> None:
    t = Topbar(
        title="My App",
        leading=Text("☰"),
        trailing=Text("user"),
    )
    assert t.leading is not None
    assert t.trailing is not None


# ───────────────── Renderer output ─────────────────────


def test_topbar_emits_root_with_three_subareas() -> None:
    """Three slot containers emit unconditionally so flex layout has
    stable elements to align even when slots are empty."""
    html = _render(Topbar())
    assert '<div class="dz-topbar">' in html
    assert '<div class="dz-topbar-leading">' in html
    assert '<div class="dz-topbar-title">' in html
    assert '<div class="dz-topbar-trailing">' in html


def test_topbar_title_renders_inside_title_text_span() -> None:
    html = _render(Topbar(title="My App"))
    assert '<span class="dz-topbar-title-text">My App</span>' in html


def test_topbar_omits_title_text_span_when_title_empty() -> None:
    html = _render(Topbar())
    # Container present, but no inner span
    assert '<div class="dz-topbar-title"></div>' in html


def test_topbar_title_is_escaped() -> None:
    html = _render(Topbar(title="<script>"))
    assert "<script>" not in html
    assert "&lt;script&gt;" in html


def test_topbar_renders_leading_slot() -> None:
    html = _render(Topbar(leading=Button(label="Menu")))
    assert "<button" in html
    assert "Menu" in html
    # Inside the leading container
    leading_idx = html.index('<div class="dz-topbar-leading">')
    button_idx = html.index("<button")
    title_idx = html.index('<div class="dz-topbar-title">')
    assert leading_idx < button_idx < title_idx


def test_topbar_renders_trailing_slot() -> None:
    html = _render(Topbar(trailing=Text("alice@example.com")))
    assert "alice@example.com" in html
    # Inside the trailing container
    trailing_idx = html.index('<div class="dz-topbar-trailing">')
    text_idx = html.index("alice@example.com")
    assert trailing_idx < text_idx


def test_topbar_slot_order_leading_title_trailing() -> None:
    html = _render(
        Topbar(
            title="MID",
            leading=Text("LEFT"),
            trailing=Text("RIGHT"),
        )
    )
    left_idx = html.index("LEFT")
    mid_idx = html.index("MID")
    right_idx = html.index("RIGHT")
    assert left_idx < mid_idx < right_idx


# ───────────────── Composition ─────────────────────────


def test_topbar_inside_app_shell_inside_page() -> None:
    """End-to-end: Page → AppShell.header=Topbar → Surface body.
    The full chrome composition for a Fragment-only app."""
    page = Page(
        title="My App",
        body=AppShell(
            sidebar=Sidebar(items=(NavItem(label="Home", href=URL("/")),)),
            header=Topbar(title="My App", trailing=Text("alice")),
            body=Text("main content"),
        ),
    )
    html = _render(page)
    assert "<!DOCTYPE html>" in html
    assert '<header class="dz-app-header">' in html
    assert '<div class="dz-topbar">' in html
    assert '<span class="dz-topbar-title-text">My App</span>' in html
    assert "alice" in html


# ──────────── #1294 — sidebar toggle ────────────────────────────────────


def test_topbar_emits_sidebar_toggle_when_enabled() -> None:
    """Regression: with show_sidebar_toggle the topbar emits a
    [data-dz-sidebar-toggle] button targeting the sidebar, so the nav is
    reachable/collapsible at every viewport (#1294)."""
    html = _render(Topbar(title="App", show_sidebar_toggle=True))
    assert "data-dz-sidebar-toggle" in html
    assert "dz-sidebar-toggle--chrome" in html
    assert 'aria-controls="dz-app-sidebar"' in html
    assert 'type="button"' in html


def test_topbar_no_sidebar_toggle_by_default() -> None:
    html = _render(Topbar(title="App"))
    assert "data-dz-sidebar-toggle" not in html


def test_sidebar_rail_toggle_when_enabled() -> None:
    """#1602 — rail placement on sidebar header for desktop-open collapse."""
    from dazzle.render.fragment import Sidebar, Text

    html = _render(Sidebar(header=Text("Brand"), show_sidebar_toggle=True))
    assert "dz-sidebar-toggle--rail" in html
    assert "data-dz-sidebar-toggle" in html
    assert "dz-sidebar__header" in html


def test_app_shell_chrome_and_rail_toggles() -> None:
    """#1602 — chrome page emits both placements; CSS picks one per viewport."""
    from dazzle.render.fragment import AppShell, Sidebar, Text, Topbar

    html = _render(
        AppShell(
            sidebar=Sidebar(header=Text("App"), show_sidebar_toggle=True),
            header=Topbar(title="App", show_sidebar_toggle=True),
            body=Text("main"),
            sidebar_state="open",
        )
    )
    assert html.count("data-dz-sidebar-toggle") == 2
    assert "dz-sidebar-toggle--chrome" in html
    assert "dz-sidebar-toggle--rail" in html
