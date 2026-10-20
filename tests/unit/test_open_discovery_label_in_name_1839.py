"""#1839 — open-discovery never overrides a link's visible text as its name.

``hub_open_discovery_attrs`` used to stamp ``aria-label`` / ``title`` with the
hop phrase ("Open Task") on links whose visible text is "Tasks", failing
WCAG 2.5.3 Label in Name. The phrase now lives only in ``data-dz-open-*``;
icon-only controls (the row edit pencil) name themselves.
"""

from __future__ import annotations

import re
from collections.abc import Callable

import pytest

from dazzle.render.fragment import FragmentRenderer, NavItem, Sidebar
from dazzle.render.fragment.htmx import URL
from dazzle.render.fragment.ingest import KanbanCard, QueueRow, render_kanban_card, render_queue_row
from dazzle.render.fragment.primitives import CreateButton, RowCapabilities
from dazzle.render.fragment.renderer._data_row import render_data_row


def _open_tags(html: str) -> list[str]:
    """Every opening ``<a …>`` tag that carries open-discovery attrs."""
    return [t for t in re.findall(r"<a\s[^>]*>", html) if "data-dz-open-label=" in t]


@pytest.mark.parametrize(
    ("render", "visible", "phrase"),
    [
        (
            lambda: FragmentRenderer().render(
                Sidebar(items=(NavItem(label="Tasks", href=URL("/app/task")),))
            ),
            "Tasks",
            "Open Task",
        ),
        (
            lambda: FragmentRenderer().render(
                CreateButton(href=URL("/app/company/create"), entity_name="Company")
            ),
            "New Company",
            "Create Company",
        ),
        (
            lambda: render_queue_row(QueueRow(title="Fix login", drill_url="/app/ticket/t-1")),
            "Fix login",
            "Open Ticket",
        ),
        (
            lambda: render_kanban_card(KanbanCard(title="Draft", drill_url="/app/ticket/t-2")),
            "Draft",
            "Open Ticket",
        ),
    ],
    ids=["sidebar-nav", "create-button", "queue-row", "kanban-card"],
)
def test_open_discovery_keeps_visible_text_as_name(
    render: Callable[[], str], visible: str, phrase: str
) -> None:
    html = render()
    tags = _open_tags(html)
    assert tags, "open-discovery still stamps data-dz-open-*"
    for tag in tags:
        assert f'data-dz-open-label="{phrase}"' in tag
        assert "title=" not in tag
        # An aria-label, if any, is the visible text itself.
        m = re.search(r'aria-label="([^"]*)"', tag)
        assert m is None or m.group(1) == visible
    assert visible in html


def test_icon_only_edit_pencil_keeps_its_name() -> None:
    html = render_data_row(
        [{"key": "title", "type": "str"}],
        {"id": "t-9", "title": "Ship edit open"},
        RowCapabilities(drill=True, update=True),
        detail_url_template="/app/ticket/{id}",
        entity_name="Ticket",
        api_endpoint="/api/tickets",
    )
    pencil = next(t for t in re.findall(r"<a\s[^>]*>", html) if "Ticket.edit" in t)
    assert "data-dz-update-drill" in pencil
    assert 'aria-label="Edit Ship edit open"' in pencil
