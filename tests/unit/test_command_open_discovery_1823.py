"""Cycle 1823 — command-palette result open-discovery stamps.

Agents attr-read ⌘K / palette destinations (workspace + record list hops)
without scraping labels. Marketing paths, bare ``/app``, and non-app hrefs
stay unstamped — same path gate as breadcrumb / ref-link VIEW hops.
"""

from __future__ import annotations

from dazzle.page.command_index import CommandEntry
from dazzle.page.command_render import render_command_results
from dazzle.render.open_discovery import command_open_attr_suffix, open_hop_label


def test_command_open_attr_suffix_stamps_app_paths() -> None:
    s = command_open_attr_suffix("/app/invoices")
    assert "data-dz-command-drill" in s
    assert 'data-dz-open-entity="Invoices"' in s
    assert "Open Invoices" in s
    assert 'data-dz-open-chain="/app/invoices"' in s
    assert open_hop_label("Invoices") == "Open Invoices"


def test_command_open_attr_suffix_workspace_path() -> None:
    s = command_open_attr_suffix("/app/workspaces/open_ws")
    assert "data-dz-command-drill" in s
    assert 'data-dz-open-entity="Workspaces"' in s
    assert "Open Workspaces" in s


def test_command_open_attr_suffix_skips_home_and_non_app() -> None:
    assert command_open_attr_suffix("/app") == ""
    assert command_open_attr_suffix("/") == ""
    assert command_open_attr_suffix("/pricing") == ""
    assert command_open_attr_suffix("#results") == ""
    assert command_open_attr_suffix("") == ""


def test_render_command_results_stamps_open_discovery() -> None:
    html = render_command_results(
        [
            CommandEntry("Overview", "/app/workspaces/open_ws", "layout-dashboard", "Workspaces"),
            CommandEntry("Invoice", "/app/invoices", "receipt", "Records"),
        ]
    )
    assert 'class="dz-command__item"' in html
    assert "data-dz-command-drill" in html
    assert 'data-dz-open-entity="Invoices"' in html
    assert 'data-dz-open-entity="Workspaces"' in html
    assert 'href="/app/invoices"' in html
    assert 'href="/app/workspaces/open_ws"' in html
    assert "Open Invoices" in html
    assert "Open Workspaces" in html
    # Groups still present
    assert "Workspaces" in html
    assert "Records" in html


def test_render_command_results_empty_state_unstamped() -> None:
    html = render_command_results([])
    assert "dz-command__empty" in html
    assert "data-dz-command-drill" not in html
    assert "data-dz-open-" not in html
