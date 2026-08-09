"""Cycle 1818 — sidebar NavItem open-discovery stamps.

Agents attr-read ``/app/<entity>…`` primary chrome hops from Sidebar /
NavGroup links without scraping labels. Marketing paths, bare ``/app``,
and non-app hrefs stay unstamped — same path gate as menubar / nav-menu /
workspace primary VIEW hops. Product-label ``aria-label`` is kept only
when open-discovery does not stamp (avoids duplicate aria-label).
"""

from __future__ import annotations

from dazzle.render.fragment import FragmentRenderer, NavGroup, NavItem, Sidebar
from dazzle.render.fragment.htmx import URL
from dazzle.render.open_discovery import link_open_discovery_attr_suffix, open_hop_label


def test_sidebar_entity_item_stamps_open_discovery() -> None:
    html = FragmentRenderer().render(
        Sidebar(
            items=(
                NavItem(label="Tasks", href=URL("/app/tasks")),
                NavItem(label="Projects", href=URL("/app/projects"), active=True),
            )
        )
    )
    assert 'class="dz-sidebar"' in html
    assert 'href="/app/tasks"' in html
    assert "data-dz-ref-link-drill" in html
    assert 'data-dz-open-entity="Tasks"' in html
    assert 'data-dz-open-entity="Projects"' in html
    assert "Open Tasks" in html
    assert "Open Projects" in html
    assert 'data-dz-open-chain="/app/tasks"' in html
    assert 'data-dz-nav="tasks"' in html
    assert 'aria-current="page"' in html
    # Open-discovery owns aria-label when stamped
    assert 'aria-label="Open Tasks"' in html
    assert 'aria-label="Open Projects"' in html


def test_sidebar_group_item_stamps_open_discovery() -> None:
    html = FragmentRenderer().render(
        Sidebar(
            groups=(
                NavGroup(
                    label="Work",
                    items=(NavItem(label="Tickets", href=URL("/app/tickets")),),
                ),
            )
        )
    )
    assert "data-dz-ref-link-drill" in html
    assert 'data-dz-open-entity="Tickets"' in html
    assert "Open Tickets" in html
    assert 'data-dz-nav="tickets"' in html


def test_sidebar_create_path_stamps_create_drill() -> None:
    html = FragmentRenderer().render(
        Sidebar(items=(NavItem(label="New task", href=URL("/app/task/create")),))
    )
    assert "data-dz-create-drill" in html
    assert 'data-dz-open-via="create"' in html
    assert "Create Task" in html


def test_sidebar_edit_path_stamps_update_drill() -> None:
    html = FragmentRenderer().render(
        Sidebar(items=(NavItem(label="Edit task", href=URL("/app/task/t-1/edit")),))
    )
    assert "data-dz-update-drill" in html
    assert 'data-dz-open-via="edit"' in html
    assert "Edit Task" in html


def test_sidebar_skips_home_and_non_app() -> None:
    html = FragmentRenderer().render(
        Sidebar(
            items=(
                NavItem(label="Home", href=URL("/app")),
                NavItem(label="Root", href=URL("/")),
                NavItem(label="Marketing", href=URL("/pricing")),
                NavItem(label="Fragment", href=URL("#section")),
            )
        )
    )
    assert "data-dz-ref-link-drill" not in html
    assert "data-dz-create-drill" not in html
    assert "data-dz-update-drill" not in html
    assert "data-dz-open-entity" not in html
    # Unstamped paths keep product-label aria-label (TR-20)
    assert 'aria-label="Home"' in html
    assert 'aria-label="Marketing"' in html


def test_link_open_discovery_suffix_matches_nav_gate() -> None:
    """Sidebar uses the same suffix helper as menubar / workspace primary."""
    assert "data-dz-ref-link-drill" in link_open_discovery_attr_suffix("/app/tasks")
    assert link_open_discovery_attr_suffix("/app") == ""
    assert link_open_discovery_attr_suffix("/pricing") == ""
    assert open_hop_label("Tasks") == "Open Tasks"
