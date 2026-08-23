"""State-machine 422 speech must not dump in_progress (oral #199)."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from dazzle.http.runtime.htmx import json_or_htmx_error
from dazzle.http.runtime.state_machine import (
    GuardNotSatisfiedError,
    InvalidTransitionError,
    _build_guard_failure_message,
    clerk_transition_state,
)

SIMPLE = Path("examples/simple_task")
SUPPORT = Path("examples/support_tickets")


def _request(method: str, *, htmx: bool = True) -> SimpleNamespace:
    headers: dict[str, str] = {}
    if htmx:
        headers["HX-Request"] = "true"
        headers["HX-Trigger-Name"] = "status"
    return SimpleNamespace(method=method, headers=headers, query_params={})


def test_simple_task_in_progress_is_live() -> None:
    block = (SIMPLE / "dsl" / "app.dsl").read_text()
    assert 'entity Task "Task":' in block
    assert "status: enum[todo,in_progress,review,done]=todo" in block
    assert "todo -> in_progress: requires assigned_to" in block
    assert "in_progress -> review" in block


def test_support_ticket_in_progress_is_live() -> None:
    block = (SUPPORT / "dsl" / "app.dsl").read_text()
    assert "open -> in_progress: requires assigned_to" in block
    assert clerk_transition_state("in_progress") == "In Progress"


def test_clerk_transition_state_leftover_and_sentinel() -> None:
    assert clerk_transition_state("in_progress") == "In Progress"
    assert clerk_transition_state("todo") == "Todo"
    assert clerk_transition_state("<none>") == "none"
    assert clerk_transition_state("zzz") == "zzz"
    assert clerk_transition_state("ghost") == "ghost"
    assert clerk_transition_state("") == ""
    assert clerk_transition_state(None) == ""


def test_invalid_transition_speech_is_clerk_not_schema() -> None:
    exc = InvalidTransitionError("in_progress", "done", {"review", "todo"})
    speech = str(exc)
    assert "In Progress" in speech
    assert "Done" in speech
    assert "Review" in speech
    assert "in_progress" not in speech
    assert exc.from_state == "in_progress"
    assert exc.to_state == "done"
    assert exc.allowed_states == {"review", "todo"}


def test_leftover_zzz_invents_no_state() -> None:
    exc = InvalidTransitionError("zzz", "ghost", {"2abc"})
    speech = str(exc)
    assert "zzz" in speech
    assert "ghost" in speech
    assert "2abc" in speech
    assert "Zzz" not in speech
    assert "Ghost" not in speech
    assert exc.from_state == "zzz"
    assert exc.to_state == "ghost"


def test_guard_requires_field_is_clerk_not_schema() -> None:
    exc = GuardNotSatisfiedError(
        "todo",
        "in_progress",
        "requires",
        "assigned_to",
        message=None,
    )
    speech = str(exc)
    assert "Assigned To" in speech
    assert "In Progress" in speech
    assert "assigned_to" not in speech
    assert "in_progress" not in speech
    assert exc.guard_value == "assigned_to"
    assert exc.from_state == "todo"


def test_all_true_checklist_speech_is_clerk_not_schema() -> None:
    """all_true 422 lists clerk field labels, not check_references (cycle 2334)."""
    expr = {
        "name": "all_true",
        "args": [
            {"path": ["check_figures"]},
            {"path": ["check_references"]},
            {"path": ["check_calculations"]},
        ],
    }
    speech = _build_guard_failure_message(
        expr,
        {
            "check_figures": True,
            "check_references": False,
            "check_calculations": False,
        },
        "in_review",
        "approved",
    )
    assert "Check References" in speech
    assert "Check Calculations" in speech
    assert "In Review" in speech
    assert "Approved" in speech
    assert "check_references" not in speech
    assert "Check Figures" not in speech
    leftover = _build_guard_failure_message(
        {"name": "all_true", "args": [{"path": ["zzz"]}]},
        {"zzz": False},
        "in_review",
        "approved",
    )
    assert "zzz" in leftover
    assert "Zzz" not in leftover


def test_htmx_transition_error_is_clerk_not_schema() -> None:
    exc = InvalidTransitionError("in_progress", "done", {"review"})
    resp = json_or_htmx_error(
        _request("PATCH"),
        [{"loc": [], "msg": str(exc)}],
        error_type="transition_error",
    )
    body = bytes(resp.body).decode()
    assert "In Progress" in body
    assert "in_progress" not in body


def test_json_api_states_stay_identifiers() -> None:
    exc = InvalidTransitionError("in_progress", "done", {"review"})
    resp = json_or_htmx_error(
        _request("PATCH", htmx=False),
        [{"loc": [], "msg": str(exc)}],
        error_type="transition_error",
    )
    text = bytes(resp.body).decode()
    assert "in_progress" not in text
    assert "In Progress" in text
    assert exc.from_state == "in_progress"
