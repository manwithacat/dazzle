"""Stage labels must not dump snake_case stage tokens (oral #144)."""

from __future__ import annotations

from pathlib import Path

from dazzle.core.project import load_project
from dazzle.render.filters import clerk_stage_label


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
    assert clerk_stage_label("true") == "Yes"
    assert clerk_stage_label("False") == "No"
    assert clerk_stage_label("TRUE") == "Yes"


def test_clerk_stage_label_leftover_stays_put() -> None:
    assert clerk_stage_label("zzz") == "zzz"
    assert clerk_stage_label("2abc") == "2abc"
    assert clerk_stage_label("1e2") == "1e2"
    assert clerk_stage_label("ghost") == "ghost"
    assert clerk_stage_label("2026-08") == "2026-08"
