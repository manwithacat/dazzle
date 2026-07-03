"""Navigation primitives — NavItem, NavGroup, Sidebar (P17 Phase 6)."""

import pytest

from dazzle.render.fragment import URL, AppShell, NavGroup, NavItem, Page, Sidebar, Text
from dazzle.render.fragment.renderer import FragmentRenderer


def _render(node: object) -> str:
    return FragmentRenderer().render(node)


# ───────────────── NavItem ─────────────────────────────────────


def test_nav_item_minimal_renders_link_in_li() -> None:
    html = _render(NavItem(label="Home", href=URL("/")))
    assert '<li class="dz-nav-item">' in html
    assert '<a class="dz-nav-link" href="/"' in html
    assert "Home" in html


def test_nav_item_active_emits_aria_current_page() -> None:
    """Active state drives `aria-current="page"` — the contract the
    legacy template's CSS already keys off."""
    html = _render(NavItem(label="Tasks", href=URL("/tasks"), active=True))
    assert 'aria-current="page"' in html


def test_nav_item_inactive_omits_aria_current() -> None:
    html = _render(NavItem(label="Tasks", href=URL("/tasks")))
    assert "aria-current" not in html


def test_nav_item_renders_icon_when_set() -> None:
    # "cog" is not a registry name -> client-hydration fallback keeps the
    # authored value; registry names render inline SVG (see below).
    html = _render(NavItem(label="Settings", href=URL("/settings"), icon="cog"))
    assert 'data-lucide="cog"' in html
    assert 'aria-hidden="true"' in html


def test_nav_item_registry_icon_renders_inline_svg() -> None:
    html = _render(NavItem(label="Settings", href=URL("/settings"), icon="settings"))
    assert '<span class="dz-nav-link__icon" aria-hidden="true"><svg' in html


def test_nav_item_without_icon_gets_inferred_registry_svg() -> None:
    # TASTE-6: every nav item carries an icon — inferred from the label
    # when not authored, always registry-closed (inline SVG, never fallback).
    html = _render(NavItem(label="Dashboard", href=URL("/d")))
    assert '<span class="dz-nav-link__icon" aria-hidden="true"><svg' in html
    assert "data-lucide" not in html


def test_nav_item_label_is_escaped() -> None:
    html = _render(NavItem(label="<script>", href=URL("/x")))
    assert "<script>" not in html
    assert "&lt;script&gt;" in html


def test_nav_item_href_uses_typed_url() -> None:
    """Href is a typed URL so disallowed schemes can't slip through."""
    with pytest.raises(ValueError, match="disallowed scheme"):
        URL("javascript:alert(1)")


def test_nav_item_rejects_empty_label() -> None:
    with pytest.raises(ValueError, match="non-empty label"):
        NavItem(label="", href=URL("/"))


# ───────────────── NavGroup ─────────────────────────────────────


def test_nav_group_renders_as_open_details_by_default() -> None:
    g = NavGroup(label="Workspace", items=(NavItem(label="A", href=URL("/a")),))
    html = _render(g)
    assert '<details class="dz-nav-group" open>' in html
    assert '<summary class="dz-nav-group__header">' in html
    assert "Workspace" in html
    assert "/a" in html


def test_nav_group_collapsed_renders_without_open_attr() -> None:
    g = NavGroup(
        label="W",
        items=(NavItem(label="A", href=URL("/a")),),
        collapsed=True,
    )
    html = _render(g)
    assert '<details class="dz-nav-group">' in html
    assert "open>" not in html


def test_nav_group_renders_icon_when_set() -> None:
    g = NavGroup(
        label="W",
        items=(NavItem(label="A", href=URL("/a")),),
        icon="folder",
    )
    html = _render(g)
    # "folder" is a registry name -> inline SVG in the group header
    assert '<span class="dz-nav-group__icon" aria-hidden="true"><svg' in html


def test_nav_group_rejects_empty_label() -> None:
    with pytest.raises(ValueError, match="non-empty label"):
        NavGroup(label="", items=(NavItem(label="A", href=URL("/a")),))


def test_nav_group_rejects_empty_items() -> None:
    with pytest.raises(ValueError, match="at least one"):
        NavGroup(label="W", items=())


# ───────────────── Sidebar ─────────────────────────────────────


def test_sidebar_minimal_empty_renders_empty_nav() -> None:
    html = _render(Sidebar())
    assert '<nav class="dz-sidebar" aria-label="Primary">' in html
    assert "</nav>" in html


def test_sidebar_renders_header_in_header_slot() -> None:
    html = _render(Sidebar(header=Text("My App")))
    assert '<div class="dz-sidebar__header">' in html
    assert "My App" in html


def test_sidebar_flat_items_render_in_ul() -> None:
    html = _render(
        Sidebar(
            items=(
                NavItem(label="Home", href=URL("/")),
                NavItem(label="Settings", href=URL("/settings")),
            )
        )
    )
    assert '<ul class="dz-sidebar__items">' in html
    # Both items present
    assert "Home" in html
    assert "Settings" in html
    # Order preserved
    assert html.index("Home") < html.index("Settings")


def test_sidebar_groups_render_after_flat_items() -> None:
    html = _render(
        Sidebar(
            items=(NavItem(label="Home", href=URL("/")),),
            groups=(
                NavGroup(
                    label="Workspaces",
                    items=(NavItem(label="W1", href=URL("/w1")),),
                ),
            ),
        )
    )
    home_idx = html.index("Home")
    group_idx = html.index('<details class="dz-nav-group"')
    assert home_idx < group_idx, "flat items must render before groups"


def test_sidebar_inside_app_shell_inside_page_composes_full_chrome() -> None:
    """End-to-end: Page → AppShell.sidebar=Sidebar(...) → real nav structure.
    The canonical full-chrome composition for a Fragment-only app."""
    page = Page(
        title="My App",
        body=AppShell(
            sidebar=Sidebar(
                header=Text("My App"),
                items=(NavItem(label="Home", href=URL("/"), active=True),),
                groups=(
                    NavGroup(
                        label="Tasks",
                        items=(NavItem(label="All Tasks", href=URL("/tasks")),),
                    ),
                ),
            ),
            body=Text("main content"),
        ),
    )
    html = _render(page)
    assert "<!DOCTYPE html>" in html
    assert '<div class="dz-app-shell"' in html
    assert '<aside class="dz-app-sidebar"' in html
    assert '<nav class="dz-sidebar"' in html
    assert "All Tasks" in html
    # Active state propagates
    assert 'aria-current="page"' in html
