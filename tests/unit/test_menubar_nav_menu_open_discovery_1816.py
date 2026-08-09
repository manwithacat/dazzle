"""Cycle 1816 — menubar + navigation-menu open-discovery stamps.

Agents attr-read ``/app/<entity>…`` chrome hops from File/Go menubars and
product NavigationMenu links without scraping labels. Marketing paths,
bare ``/app``, and non-app hrefs stay unstamped — same path gate as
workspace primary / Link / breadcrumb VIEW hops.
"""

from __future__ import annotations

from dazzle.render.fragment import (
    FragmentRenderer,
    Menubar,
    MenubarAction,
    MenubarMenu,
    NavigationMenu,
    NavigationMenuBranch,
    NavigationMenuGroup,
    NavigationMenuLink,
)
from dazzle.render.open_discovery import link_open_discovery_attr_suffix, open_hop_label


def test_menubar_entity_action_stamps_open_discovery() -> None:
    html = FragmentRenderer().render(
        Menubar(
            menus=(
                MenubarMenu(
                    label="Studio",
                    actions=(
                        MenubarAction(label="Dashboard", href="/app/studio"),
                        MenubarAction(label="Brands", href="/app/brands"),
                        MenubarAction(label="Export"),  # no href
                    ),
                ),
            )
        )
    )
    assert 'class="dz-menubar"' in html
    assert 'href="/app/studio"' in html
    assert "data-dz-ref-link-drill" in html
    assert 'data-dz-open-entity="Studio"' in html
    assert 'data-dz-open-entity="Brands"' in html
    assert "Open Studio" in html
    assert "Open Brands" in html
    assert 'data-dz-open-chain="/app/studio"' in html
    # Button menuitem (no href) stays free of open attrs
    assert 'role="menuitem">Export</button>' in html


def test_menubar_create_path_stamps_create_drill() -> None:
    html = FragmentRenderer().render(
        Menubar(
            menus=(
                MenubarMenu(
                    label="File",
                    actions=(MenubarAction(label="New task", href="/app/task/create"),),
                ),
            )
        )
    )
    assert "data-dz-create-drill" in html
    assert 'data-dz-open-via="create"' in html
    assert "Create Task" in html


def test_menubar_skips_home_and_non_app() -> None:
    html = FragmentRenderer().render(
        Menubar(
            menus=(
                MenubarMenu(
                    label="Go",
                    actions=(
                        MenubarAction(label="Home", href="/app"),
                        MenubarAction(label="Marketing", href="/pricing"),
                        MenubarAction(label="Fragment", href="#section"),
                    ),
                ),
            )
        )
    )
    assert 'href="/app"' in html
    assert 'href="/pricing"' in html
    assert "data-dz-ref-link-drill" not in html
    assert "data-dz-create-drill" not in html
    assert "data-dz-open-entity" not in html


def test_navigation_menu_app_link_stamps_open_discovery() -> None:
    html = FragmentRenderer().render(
        NavigationMenu(
            items=(
                NavigationMenuLink(label="Home", href="/", current=True),
                NavigationMenuLink(label="Tickets", href="/app/ticket"),
                NavigationMenuBranch(
                    label="Product",
                    mega=True,
                    groups=(
                        NavigationMenuGroup(
                            title="Operate",
                            links=(
                                NavigationMenuLink(
                                    label="Deploy history",
                                    href="/app/deployhistory",
                                    description="Recent releases",
                                ),
                                NavigationMenuLink(label="Docs", href="/docs"),
                            ),
                        ),
                    ),
                ),
            )
        )
    )
    assert 'class="dz-navigation-menu"' in html
    assert "data-dz-ref-link-drill" in html
    assert 'data-dz-open-entity="Ticket"' in html
    assert 'data-dz-open-entity="Deployhistory"' in html
    assert open_hop_label("Ticket") in html
    # Marketing / home stay plain
    home_chunk = html[html.index('href="/"') : html.index('href="/app/ticket"')]
    assert "data-dz-open-entity" not in home_chunk
    assert 'href="/docs"' in html
    docs_idx = html.index('href="/docs"')
    # docs is non-app — no open entity near it
    assert "data-dz-open-entity" not in html[docs_idx : docs_idx + 80]


def test_link_open_discovery_attr_suffix_matches_menubar_gate() -> None:
    assert "data-dz-ref-link-drill" in link_open_discovery_attr_suffix("/app/studio")
    assert link_open_discovery_attr_suffix("/app") == ""
    assert link_open_discovery_attr_suffix("/pricing") == ""
    assert "data-dz-create-drill" in link_open_discovery_attr_suffix("/app/task/new")
