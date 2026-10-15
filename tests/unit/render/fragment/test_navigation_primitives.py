"""Navigation primitives — NavItem, NavGroup, Sidebar (P17 Phase 6)."""

from collections.abc import Callable

import pytest

from dazzle.render.fragment import URL, AppShell, NavGroup, NavItem, Page, Sidebar, Text
from dazzle.render.fragment.renderer import FragmentRenderer


def _render(node: object) -> str:
    return FragmentRenderer().render(node)


_ICON_SVG = '<span class="dz-nav-link__icon" aria-hidden="true"><svg'
_GROUP_ITEMS = (NavItem(label="A", href=URL("/a")),)


@pytest.mark.parametrize(
    ("node", "present", "absent"),
    [
        pytest.param(
            NavItem(label="Home", href=URL("/")),
            ('<li class="dz-nav-item">', '<a class="dz-nav-link" href="/"', "Home"),
            ("aria-current",),
            id="item-minimal-link-in-li-inactive",
        ),
        # Active state drives aria-current="page" (the legacy CSS contract).
        pytest.param(
            NavItem(label="Tasks", href=URL("/tasks"), active=True),
            ('aria-current="page"',),
            (),
            id="item-active-aria-current-page",
        ),
        # "cog" is not a registry name → client-hydration fallback keeps it.
        pytest.param(
            NavItem(label="Settings", href=URL("/settings"), icon="cog"),
            ('data-lucide="cog"', 'aria-hidden="true"'),
            (),
            id="item-unknown-icon-hydration-fallback",
        ),
        pytest.param(
            NavItem(label="Settings", href=URL("/settings"), icon="settings"),
            (_ICON_SVG,),
            (),
            id="item-registry-icon-inline-svg",
        ),
        # TASTE-6: every nav item carries an icon, inferred from the label and
        # always registry-closed (inline SVG, never the hydration fallback).
        pytest.param(
            NavItem(label="Dashboard", href=URL("/d")),
            (_ICON_SVG,),
            ("data-lucide",),
            id="item-without-icon-gets-inferred-registry-svg",
        ),
        pytest.param(
            NavItem(label="<script>", href=URL("/x")),
            ("&lt;script&gt;",),
            ("<script>",),
            id="item-label-escaped",
        ),
        # TR-20 / cycle 1818: stable agent hooks; /app/<entity> hops stamp
        # open-discovery, which owns aria-label.
        pytest.param(
            NavItem(label="Systems", href=URL("/app/system")),
            (
                'aria-label="Open System"',
                'data-dz-nav="system"',
                'href="/app/system"',
                "data-dz-ref-link-drill",
                'data-dz-open-entity="System"',
            ),
            (),
            id="item-app-entity-hop-stamps-open-discovery",
        ),
        # Unstamped (home / non-app) paths keep the product-label aria.
        pytest.param(
            NavItem(label="Home", href=URL("/app")),
            ('aria-label="Home"',),
            ("data-dz-ref-link-drill",),
            id="item-home-keeps-product-label-aria",
        ),
        pytest.param(
            NavGroup(label="Workspace", items=_GROUP_ITEMS),
            (
                '<details class="dz-nav-group" open>',
                '<summary class="dz-nav-group__header">',
                "Workspace",
                "/a",
            ),
            (),
            id="group-open-details-by-default",
        ),
        pytest.param(
            NavGroup(label="W", items=_GROUP_ITEMS, collapsed=True),
            ('<details class="dz-nav-group">',),
            ("open>",),
            id="group-collapsed-without-open-attr",
        ),
        pytest.param(
            NavGroup(label="W", items=_GROUP_ITEMS, icon="folder"),
            ('<span class="dz-nav-group__icon" aria-hidden="true"><svg',),
            (),
            id="group-registry-icon-inline-svg",
        ),
        pytest.param(
            Sidebar(),
            ('<nav class="dz-sidebar" aria-label="Primary">', "</nav>"),
            (),
            id="sidebar-minimal-empty-nav",
        ),
        pytest.param(
            Sidebar(header=Text("My App")),
            ('<div class="dz-sidebar__header">', "My App"),
            (),
            id="sidebar-header-slot",
        ),
    ],
)
def test_renders(node: object, present: tuple[str, ...], absent: tuple[str, ...]) -> None:
    html = _render(node)
    assert [s for s in present if s not in html] == []
    assert [s for s in absent if s in html] == []


@pytest.mark.parametrize(
    ("ctor", "match"),
    [
        pytest.param(
            lambda: NavItem(label="", href=URL("/")), "non-empty label", id="item-empty-label"
        ),
        pytest.param(
            lambda: NavGroup(label="", items=_GROUP_ITEMS),
            "non-empty label",
            id="group-empty-label",
        ),
        pytest.param(lambda: NavGroup(label="W", items=()), "at least one", id="group-empty-items"),
    ],
)
def test_rejects(ctor: Callable[[], object], match: str) -> None:
    with pytest.raises(ValueError, match=match):
        ctor()


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
