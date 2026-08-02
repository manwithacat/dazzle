"""Cycle 1612 — hub drill dual-open discovery on kanban/activity/timeline/tree."""

from __future__ import annotations

from dazzle.render.fragment.ingest import (
    ActivityRow,
    KanbanCard,
    TimelineEvent,
    render_activity_row,
    render_kanban_card,
    render_timeline_event,
    render_tree_node_label,
)


def test_kanban_drill_stamps_open_discovery() -> None:
    html = render_kanban_card(KanbanCard(title="Refund — Acme", drill_url="/app/ticket/t-9"))
    assert "data-dz-kanban-drill" in html
    assert 'data-dz-open-entity="Ticket"' in html
    assert 'data-dz-open-role="primary"' in html
    assert 'data-dz-open-chain="/app/ticket/t-9"' in html
    assert 'data-dz-open-hops="1"' in html


def test_activity_drill_stamps_open_discovery() -> None:
    html = render_activity_row(
        ActivityRow(
            time_str="2m ago",
            description="Opened ticket",
            drill_url="/app/ticket/t-1",
        )
    )
    assert "data-dz-activity-drill" in html
    assert 'data-dz-open-entity="Ticket"' in html
    assert 'data-dz-open-chain="/app/ticket/t-1"' in html


def test_timeline_drill_stamps_open_discovery() -> None:
    html = render_timeline_event(
        TimelineEvent(
            title="Hired",
            date_label="2024-01",
            drill_url="/app/person/p-1",
        )
    )
    assert "data-dz-timeline-drill" in html
    assert 'data-dz-open-entity="Person"' in html
    assert 'data-dz-open-chain="/app/person/p-1"' in html


def test_tree_drill_stamps_open_discovery_on_link() -> None:
    html = render_tree_node_label("Engineering", drill_url="/app/department/d-1")
    assert "data-dz-tree-drill" in html
    assert 'data-dz-open-entity="Department"' in html
    assert 'data-dz-open-label="Open Department"' in html
    assert "data-dz-open-chain=" not in html  # host chain only on row-like roots


def test_queue_open_alias_still_works() -> None:
    from dazzle.render.fragment.ingest.emit import (
        _hub_open_discovery_attrs,
        _queue_open_discovery_attrs,
    )

    a, b = _hub_open_discovery_attrs("/app/task/1")
    c, d = _queue_open_discovery_attrs("/app/task/1")
    assert a == c and b == d
