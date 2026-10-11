"""Kanban must not title tasks as snake_case enum tokens (oral #138)."""

from __future__ import annotations

from dazzle.render.fragment.region._dispatcher import WorkspaceRegionAdapter
from dazzle.render.fragment.region._shared import format_primary_display


class _FakeKanban:
    name = "open_work"
    title = "Open work"
    empty_message = "No open tasks"


def test_kanban_title_is_notes_not_debugging() -> None:
    adapter = WorkspaceRegionAdapter()
    notes = "Swap the probe battery after outdoor walk."
    ctx = {
        "items": [
            {
                "id": "t1000000-0000-4000-8000-000000000001",
                "type": "debugging",
                "status": "in_progress",
                "notes": notes,
            }
        ],
        "columns": [
            {"key": "type", "label": "Type", "type": "badge"},
            {"key": "status", "label": "Status", "type": "badge"},
            {"key": "assigned_to", "label": "Assigned To", "type": "ref"},
            {"key": "created_by", "label": "Created By", "type": "ref"},
        ],
        "kanban_columns": ["open", "in_progress"],
        "group_by": "status",
        "display_key": "notes",
        "entity_name": "Task",
    }
    surface = adapter._build_kanban(_FakeKanban(), ctx)  # type: ignore[arg-type]
    cards = [c for col in surface.body.body.columns for c in col.cards]  # type: ignore[union-attr]
    assert len(cards) == 1
    assert cards[0].title == notes
    assert "debugging" not in cards[0].title


def test_kanban_leftover_notes_title_stays_put() -> None:
    adapter = WorkspaceRegionAdapter()
    ctx = {
        "items": [
            {
                "id": "task-zzz",
                "type": "debugging",
                "status": "open",
                "notes": "zzz",
            }
        ],
        "columns": [
            {"key": "type", "label": "Type", "type": "badge"},
            {"key": "status", "label": "Status", "type": "badge"},
        ],
        "kanban_columns": ["open"],
        "group_by": "status",
        "display_key": "notes",
        "entity_name": "Task",
    }
    surface = adapter._build_kanban(_FakeKanban(), ctx)  # type: ignore[arg-type]
    assert surface.body.body.columns[0].cards[0].title == "zzz"  # type: ignore[union-attr]


def test_kanban_badge_title_humanizes_snake_case() -> None:
    """If display_key stays the enum, title-case — do not dump debugging."""
    assert (
        format_primary_display(
            "debugging",
            "type",
            [{"key": "type", "type": "badge"}],
            {"type": "debugging"},
        )
        == "Debugging"
    )
    assert (
        format_primary_display(
            "hardware_replacement",
            "type",
            [{"key": "type", "type": "badge"}],
            {},
        )
        == "Hardware Replacement"
    )
    adapter = WorkspaceRegionAdapter()
    ctx = {
        "items": [
            {
                "id": "task-enum",
                "type": "debugging",
                "status": "open",
            }
        ],
        "columns": [
            {"key": "type", "label": "Type", "type": "badge"},
            {"key": "status", "label": "Status", "type": "badge"},
        ],
        "kanban_columns": ["open"],
        "group_by": "status",
        "display_key": "type",
        "entity_name": "Task",
    }
    surface = adapter._build_kanban(_FakeKanban(), ctx)  # type: ignore[arg-type]
    assert surface.body.body.columns[0].cards[0].title == "Debugging"  # type: ignore[union-attr]
