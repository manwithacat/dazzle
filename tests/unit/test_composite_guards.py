"""Tests for composite transition guards (issue #332).

Covers:
- all_true() checklist enforcement
- Field comparison guards (field != field)
- current_user pseudo-field in guards
- Clear error messages listing unchecked items
- Existing simple guards unchanged
"""

from __future__ import annotations

from typing import Any

from dazzle_back.runtime.state_machine import (
    GuardNotSatisfiedError,
    TransitionValidator,
    evaluate_guard_expr,
    validate_status_update,
)
from dazzle_back.specs.entity import (
    StateMachineSpec,
    StateTransitionSpec,
    TransitionGuardSpec,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _sm(
    transitions: list[StateTransitionSpec],
    states: list[str] | None = None,
) -> StateMachineSpec:
    """Build a minimal state machine spec."""
    if states is None:
        s: set[str] = set()
        for t in transitions:
            if t.from_state != "*":
                s.add(t.from_state)
            s.add(t.to_state)
        states = sorted(s)
    return StateMachineSpec(
        status_field="status",
        states=states,
        transitions=transitions,
    )


def _all_true_expr(*fields: str) -> dict[str, Any]:
    """Build an all_true() function call AST node."""
    return {
        "name": "all_true",
        "args": [{"path": [f]} for f in fields],
    }


def _ne_expr(left_field: str, right_field: str) -> dict[str, Any]:
    """Build a field != field binary expression AST node."""
    return {
        "op": "!=",
        "left": {"path": [left_field]},
        "right": {"path": [right_field]},
    }


# ---------------------------------------------------------------------------
# all_true() checklist enforcement
# ---------------------------------------------------------------------------


class TestAllTrueGuard:
    """Verify all_true() composite boolean guard."""

    def test_all_true_passes_when_all_fields_true(self) -> None:
        """all_true(a, b, c) passes when all fields are True."""
        expr = _all_true_expr("check_a", "check_b", "check_c")
        data = {"check_a": True, "check_b": True, "check_c": True}
        assert evaluate_guard_expr(expr, data) is True

    def test_all_true_fails_when_one_field_false(self) -> None:
        """all_true(a, b, c) fails when any field is False."""
        expr = _all_true_expr("check_a", "check_b", "check_c")
        data = {"check_a": True, "check_b": False, "check_c": True}
        assert evaluate_guard_expr(expr, data) is False

    def test_all_true_fails_when_field_missing(self) -> None:
        """all_true(a, b) fails when a field is missing (None)."""
        expr = _all_true_expr("check_a", "check_b")
        data = {"check_a": True}  # check_b missing → None → falsy
        assert evaluate_guard_expr(expr, data) is False

    def test_all_true_fails_when_all_false(self) -> None:
        """all_true(a, b) fails when all fields are False."""
        expr = _all_true_expr("check_a", "check_b")
        data = {"check_a": False, "check_b": False}
        assert evaluate_guard_expr(expr, data) is False

    def test_all_true_with_empty_args(self) -> None:
        """all_true() with no arguments passes (vacuous truth)."""
        expr: dict[str, Any] = {"name": "all_true", "args": []}
        assert evaluate_guard_expr(expr, {}) is True

    def test_all_true_transition_blocked_with_clear_message(self) -> None:
        """When all_true guard fails, error message lists unchecked items."""
        sm = _sm(
            [
                StateTransitionSpec(
                    from_state="in_review",
                    to_state="approved",
                    guards=[
                        TransitionGuardSpec(
                            guard_expr=_all_true_expr(
                                "check_figures", "check_references", "check_calculations"
                            ),
                        ),
                    ],
                ),
            ]
        )

        validator = TransitionValidator(sm)
        result = validator.validate_transition(
            "in_review",
            "approved",
            {
                "status": "in_review",
                "check_figures": True,
                "check_references": False,
                "check_calculations": False,
            },
        )

        assert not result.is_valid
        assert isinstance(result.error, GuardNotSatisfiedError)
        # Error message should list which items are unchecked
        msg = str(result.error)
        assert "check_references" in msg
        assert "check_calculations" in msg
        # check_figures is True, should NOT appear in the message
        assert "check_figures" not in msg

    def test_all_true_with_custom_message(self) -> None:
        """When guard_message is provided, it overrides the auto-generated message."""
        sm = _sm(
            [
                StateTransitionSpec(
                    from_state="in_review",
                    to_state="approved",
                    guards=[
                        TransitionGuardSpec(
                            guard_expr=_all_true_expr("check_a"),
                            guard_message="All checklist items must be confirmed",
                        ),
                    ],
                ),
            ]
        )

        validator = TransitionValidator(sm)
        result = validator.validate_transition(
            "in_review",
            "approved",
            {"status": "in_review", "check_a": False},
        )

        assert not result.is_valid
        assert "All checklist items must be confirmed" in str(result.error)


# ---------------------------------------------------------------------------
# Field comparison guards
# ---------------------------------------------------------------------------


class TestFieldComparisonGuard:
    """Verify field != field comparison in expression guards."""

    def test_field_ne_field_passes_when_different(self) -> None:
        """reviewer != preparer passes when values differ."""
        expr = _ne_expr("reviewer", "preparer")
        data = {"reviewer": "alice", "preparer": "bob"}
        assert evaluate_guard_expr(expr, data) is True

    def test_field_ne_field_fails_when_same(self) -> None:
        """reviewer != preparer fails when values are the same."""
        expr = _ne_expr("reviewer", "preparer")
        data = {"reviewer": "alice", "preparer": "alice"}
        assert evaluate_guard_expr(expr, data) is False

    def test_field_comparison_transition_blocked(self) -> None:
        """Transition is blocked when field comparison guard fails."""
        sm = _sm(
            [
                StateTransitionSpec(
                    from_state="in_review",
                    to_state="approved",
                    guards=[
                        TransitionGuardSpec(
                            guard_expr=_ne_expr("reviewer", "preparer"),
                            guard_message="Reviewer must differ from preparer",
                        ),
                    ],
                ),
            ]
        )

        validator = TransitionValidator(sm)

        # Same person — should fail
        result = validator.validate_transition(
            "in_review",
            "approved",
            {"status": "in_review", "reviewer": "alice", "preparer": "alice"},
        )
        assert not result.is_valid
        assert "Reviewer must differ from preparer" in str(result.error)

        # Different people — should pass
        result = validator.validate_transition(
            "in_review",
            "approved",
            {"status": "in_review", "reviewer": "alice", "preparer": "bob"},
        )
        assert result.is_valid


# ---------------------------------------------------------------------------
# current_user pseudo-field
# ---------------------------------------------------------------------------


class TestCurrentUserGuard:
    """Verify current_user pseudo-field in guard expressions."""

    def test_current_user_injected_into_evaluation(self) -> None:
        """current_user is available as a field during guard evaluation."""
        sm = _sm(
            [
                StateTransitionSpec(
                    from_state="in_review",
                    to_state="approved",
                    guards=[
                        TransitionGuardSpec(
                            guard_expr=_ne_expr("reviewer", "current_user"),
                            guard_message="Reviewer cannot approve their own work",
                        ),
                    ],
                ),
            ]
        )

        validator = TransitionValidator(sm)

        # Same user — should fail
        result = validator.validate_transition(
            "in_review",
            "approved",
            {"status": "in_review", "reviewer": "alice"},
            current_user="alice",
        )
        assert not result.is_valid
        assert "Reviewer cannot approve their own work" in str(result.error)

        # Different user — should pass
        result = validator.validate_transition(
            "in_review",
            "approved",
            {"status": "in_review", "reviewer": "alice"},
            current_user="bob",
        )
        assert result.is_valid

    def test_current_user_via_validate_status_update(self) -> None:
        """current_user works through the validate_status_update entry point."""
        sm = _sm(
            [
                StateTransitionSpec(
                    from_state="pending",
                    to_state="approved",
                    guards=[
                        TransitionGuardSpec(
                            guard_expr=_ne_expr("submitted_by", "current_user"),
                        ),
                    ],
                ),
            ],
        )

        # Same user — should fail
        result = validate_status_update(
            sm,
            current_data={"status": "pending", "submitted_by": "eve"},
            update_data={"status": "approved"},
            current_user="eve",
        )
        assert result is not None
        assert not result.is_valid

        # Different user — should pass
        result = validate_status_update(
            sm,
            current_data={"status": "pending", "submitted_by": "eve"},
            update_data={"status": "approved"},
            current_user="frank",
        )
        assert result is not None
        assert result.is_valid

    def test_current_user_none_resolves_to_none(self) -> None:
        """When current_user is None, it's not injected into data."""
        sm = _sm(
            [
                StateTransitionSpec(
                    from_state="open",
                    to_state="closed",
                    guards=[
                        TransitionGuardSpec(
                            guard_expr=_ne_expr("assignee", "current_user"),
                        ),
                    ],
                ),
            ]
        )

        validator = TransitionValidator(sm)

        # current_user=None means current_user field won't be in data
        # assignee != None → True (different types, but != returns True)
        result = validator.validate_transition(
            "open",
            "closed",
            {"status": "open", "assignee": "alice"},
            current_user=None,
        )
        # No current_user injected, so current_user field is missing → None
        # "alice" != None → True
        assert result.is_valid


# ---------------------------------------------------------------------------
# Existing guards unchanged
# ---------------------------------------------------------------------------


class TestExistingGuardsUnchanged:
    """Verify existing simple guards continue to work."""

    def test_requires_field_still_works(self) -> None:
        """Simple requires field guard is not broken."""
        sm = _sm(
            [
                StateTransitionSpec(
                    from_state="open",
                    to_state="assigned",
                    guards=[TransitionGuardSpec(requires_field="assignee")],
                ),
            ]
        )

        validator = TransitionValidator(sm)

        # Missing field — should fail
        result = validator.validate_transition("open", "assigned", {"status": "open"})
        assert not result.is_valid

        # Field set — should pass
        result = validator.validate_transition(
            "open", "assigned", {"status": "open", "assignee": "alice"}
        )
        assert result.is_valid

    def test_role_guard_still_works(self) -> None:
        """Role guard is not broken."""
        sm = _sm(
            [
                StateTransitionSpec(
                    from_state="*",
                    to_state="open",
                    guards=[TransitionGuardSpec(requires_role="admin")],
                ),
            ]
        )

        validator = TransitionValidator(sm)

        # No role — should fail
        result = validator.validate_transition(
            "closed", "open", {"status": "closed"}, user_roles=[]
        )
        assert not result.is_valid

        # Has role — should pass
        result = validator.validate_transition(
            "closed", "open", {"status": "closed"}, user_roles=["admin"]
        )
        assert result.is_valid

    def test_expression_guard_still_works(self) -> None:
        """Expression guard (non-all_true) is not broken."""
        sm = _sm(
            [
                StateTransitionSpec(
                    from_state="draft",
                    to_state="published",
                    guards=[
                        TransitionGuardSpec(
                            guard_expr={
                                "op": "==",
                                "left": {"path": ["approved"]},
                                "right": {"value": True},
                            },
                        ),
                    ],
                ),
            ]
        )

        validator = TransitionValidator(sm)

        # Not approved — should fail
        result = validator.validate_transition(
            "draft", "published", {"status": "draft", "approved": False}
        )
        assert not result.is_valid

        # Approved — should pass
        result = validator.validate_transition(
            "draft", "published", {"status": "draft", "approved": True}
        )
        assert result.is_valid


# ---------------------------------------------------------------------------
# DSL Parsing
# ---------------------------------------------------------------------------


class TestGuardDSLParsing:
    """Verify all_true() parses from DSL."""

    def test_all_true_parses_as_guard_expr(self) -> None:
        """all_true(field1, field2) parses into a FuncCall guard_expr."""
        from pathlib import Path

        from dazzle.core.dsl_parser_impl import parse_dsl

        dsl = """\
module test_app
app test "Test"

entity Return "Return":
  id: uuid pk
  status: enum[draft, in_review, approved]
  check_figures: bool=false
  check_references: bool=false

  transitions:
    draft -> in_review
    in_review -> approved:
      guard: all_true(check_figures, check_references)
        message: "All checklist items must be confirmed"
"""
        _, _, _, _, _, fragment = parse_dsl(dsl, file=Path("test.dsl"))
        entity = fragment.entities[0]
        sm = entity.state_machine
        assert sm is not None

        # Find the in_review -> approved transition
        transition = sm.get_transition("in_review", "approved")
        assert transition is not None
        assert len(transition.guards) == 1

        guard = transition.guards[0]
        assert guard.guard_expr is not None
        assert guard.guard_message == "All checklist items must be confirmed"

        # The guard_expr should be a FuncCall for all_true
        # (IR Expr is a Pydantic model, check its structure)
        from dazzle.core.ir.expressions import FuncCall

        assert isinstance(guard.guard_expr, FuncCall)
        assert guard.guard_expr.name == "all_true"
        assert len(guard.guard_expr.args) == 2
