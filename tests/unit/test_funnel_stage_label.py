"""Funnel/progress must not dump snake_case stage tokens (oral #144)."""

from __future__ import annotations

from pathlib import Path

from dazzle.core.project import load_project
from dazzle.render.filters import clerk_stage_label
from dazzle.render.fragment.region._dispatcher import WorkspaceRegionAdapter


class _FakeFunnel:
    name = "agent_status_funnel"
    title = "Agent status funnel"
    empty_message = "No tickets for this agent"


class _FakeProgress:
    name = "agent_lifecycle_progress"
    title = "Agent lifecycle"
    empty_message = "No tickets for this agent"


def test_ticket_status_includes_in_progress() -> None:
    spec = load_project(Path("examples/support_tickets"))
    ticket = spec.get_entity("Ticket")
    assert ticket is not None
    status = next(f for f in ticket.fields if f.name == "status")
    assert "in_progress" in list(status.type.enum_values or [])


def test_clerk_stage_label_humanizes_snake_case() -> None:
    assert clerk_stage_label("in_progress") == "In Progress"
    assert clerk_stage_label("annual_review") == "Annual Review"
    assert clerk_stage_label("open") == "Open"
    assert clerk_stage_label("In Progress") == "In Progress"
    assert clerk_stage_label(True) == "Yes"
    assert clerk_stage_label(False) == "No"


def test_clerk_stage_label_leftover_stays_put() -> None:
    assert clerk_stage_label("zzz") == "zzz"
    assert clerk_stage_label("2abc") == "2abc"
    assert clerk_stage_label("1e2") == "1e2"
    assert clerk_stage_label("ghost") == "ghost"
    assert clerk_stage_label("2026-08") == "2026-08"


def test_funnel_stage_is_in_progress_not_token() -> None:
    adapter = WorkspaceRegionAdapter()
    ctx = {
        "kanban_columns": ["open", "in_progress", "resolved"],
        "group_by": "status",
        "items": [
            {"status": "open"},
            {"status": "in_progress"},
            {"status": "in_progress"},
            {"status": "resolved"},
        ],
        "total": 4,
    }
    surface = adapter._build_funnel_chart(_FakeFunnel(), ctx)  # type: ignore[arg-type]
    labels = [s.label for s in surface.body.body.stages]  # type: ignore[union-attr]
    assert labels == ["Open", "In Progress", "Resolved"]
    assert "in_progress" not in labels


def test_funnel_leftover_stage_stays_put() -> None:
    adapter = WorkspaceRegionAdapter()
    ctx = {
        "kanban_columns": ["zzz"],
        "group_by": "status",
        "items": [{"status": "zzz"}],
        "total": 1,
    }
    surface = adapter._build_funnel_chart(_FakeFunnel(), ctx)  # type: ignore[arg-type]
    assert surface.body.body.stages[0].label == "zzz"  # type: ignore[union-attr]


def test_progress_stage_is_in_progress_not_token() -> None:
    adapter = WorkspaceRegionAdapter()
    ctx = {
        "stage_counts": [
            {"name": "open", "count": 2, "complete": False},
            {"name": "in_progress", "count": 3, "complete": False},
            {"name": "resolved", "count": 1, "complete": True},
        ],
        "complete_pct": 16.7,
        "complete_count": 1,
        "progress_total": 6,
    }
    surface = adapter._build_progress(_FakeProgress(), ctx)  # type: ignore[arg-type]
    names = [name for name, _count, _done in surface.body.body.stages]  # type: ignore[union-attr]
    assert names == ["Open", "In Progress", "Resolved"]
    assert "in_progress" not in names


def test_progress_leftover_stage_stays_put() -> None:
    adapter = WorkspaceRegionAdapter()
    ctx = {
        "stage_counts": [{"name": "zzz", "count": 1, "complete": False}],
    }
    surface = adapter._build_progress(_FakeProgress(), ctx)  # type: ignore[arg-type]
    assert surface.body.body.stages[0][0] == "zzz"  # type: ignore[union-attr]
