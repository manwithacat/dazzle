"""Tests for state machine runtime validation."""

from __future__ import annotations

from dazzle_back.runtime.state_machine import (
    GuardNotSatisfiedError,
    InvalidTransitionError,
    TransitionValidator,
    evaluate_guard_expr,
    validate_status_update,
)
from dazzle_back.specs.entity import (
    AutoTransitionSpec,
    StateMachineSpec,
    StateTransitionSpec,
    TimeUnit,
    TransitionGuardSpec,
)


class TestTransitionValidator:
    """Tests for TransitionValidator."""

    def test_valid_transition(self) -> None:
        """Test that valid transitions pass validation."""
        sm = StateMachineSpec(
            status_field="status",
            states=["open", "assigned", "resolved", "closed"],
            transitions=[
                StateTransitionSpec(from_state="open", to_state="assigned"),
                StateTransitionSpec(from_state="assigned", to_state="resolved"),
                StateTransitionSpec(from_state="resolved", to_state="closed"),
            ],
        )

        validator = TransitionValidator(sm)
        result = validator.validate_transition("open", "assigned", {})

        assert result.is_valid
        assert result.error is None
        assert result.transition is not None
        assert result.transition.from_state == "open"
        assert result.transition.to_state == "assigned"

    def test_invalid_transition(self) -> None:
        """Test that invalid transitions fail validation."""
        sm = StateMachineSpec(
            status_field="status",
            states=["open", "assigned", "resolved", "closed"],
            transitions=[
                StateTransitionSpec(from_state="open", to_state="assigned"),
                StateTransitionSpec(from_state="assigned", to_state="resolved"),
            ],
        )

        validator = TransitionValidator(sm)
        result = validator.validate_transition("open", "resolved", {})

        assert not result.is_valid
        assert isinstance(result.error, InvalidTransitionError)
        assert result.error.from_state == "open"
        assert result.error.to_state == "resolved"
        assert "assigned" in result.error.allowed_states

    def test_wildcard_transition(self) -> None:
        """Test that wildcard transitions work from any state."""
        sm = StateMachineSpec(
            status_field="status",
            states=["draft", "published", "archived"],
            transitions=[
                StateTransitionSpec(from_state="draft", to_state="published"),
                StateTransitionSpec(from_state="*", to_state="draft"),  # Reset from any state
            ],
        )

        validator = TransitionValidator(sm)

        # Wildcard allows draft from published
        result = validator.validate_transition("published", "draft", {})
        assert result.is_valid

        # Wildcard allows draft from archived
        result = validator.validate_transition("archived", "draft", {})
        assert result.is_valid

    def test_requires_field_guard_satisfied(self) -> None:
        """Test that field guard passes when field has value."""
        sm = StateMachineSpec(
            status_field="status",
            states=["open", "assigned"],
            transitions=[
                StateTransitionSpec(
                    from_state="open",
                    to_state="assigned",
                    guards=[TransitionGuardSpec(requires_field="assignee")],
                ),
            ],
        )

        validator = TransitionValidator(sm)
        result = validator.validate_transition("open", "assigned", {"assignee": "john@example.com"})

        assert result.is_valid

    def test_requires_field_guard_not_satisfied(self) -> None:
        """Test that field guard fails when field is empty."""
        sm = StateMachineSpec(
            status_field="status",
            states=["open", "assigned"],
            transitions=[
                StateTransitionSpec(
                    from_state="open",
                    to_state="assigned",
                    guards=[TransitionGuardSpec(requires_field="assignee")],
                ),
            ],
        )

        validator = TransitionValidator(sm)
        result = validator.validate_transition("open", "assigned", {"assignee": None})

        assert not result.is_valid
        assert isinstance(result.error, GuardNotSatisfiedError)
        assert result.error.guard_type == "requires"
        assert result.error.guard_value == "assignee"

    def test_requires_field_guard_empty_string(self) -> None:
        """Test that field guard fails when field is empty string."""
        sm = StateMachineSpec(
            status_field="status",
            states=["open", "assigned"],
            transitions=[
                StateTransitionSpec(
                    from_state="open",
                    to_state="assigned",
                    guards=[TransitionGuardSpec(requires_field="assignee")],
                ),
            ],
        )

        validator = TransitionValidator(sm)
        result = validator.validate_transition("open", "assigned", {"assignee": ""})

        assert not result.is_valid
        assert isinstance(result.error, GuardNotSatisfiedError)

    def test_role_guard_satisfied(self) -> None:
        """Test that role guard passes when user has role."""
        sm = StateMachineSpec(
            status_field="status",
            states=["draft", "published"],
            transitions=[
                StateTransitionSpec(
                    from_state="draft",
                    to_state="published",
                    guards=[TransitionGuardSpec(requires_role="editor")],
                ),
            ],
        )

        validator = TransitionValidator(sm)
        result = validator.validate_transition("draft", "published", {}, user_roles=["editor"])

        assert result.is_valid

    def test_role_guard_not_satisfied(self) -> None:
        """Test that role guard fails when user lacks role."""
        sm = StateMachineSpec(
            status_field="status",
            states=["draft", "published"],
            transitions=[
                StateTransitionSpec(
                    from_state="draft",
                    to_state="published",
                    guards=[TransitionGuardSpec(requires_role="editor")],
                ),
            ],
        )

        validator = TransitionValidator(sm)
        result = validator.validate_transition("draft", "published", {}, user_roles=["viewer"])

        assert not result.is_valid
        assert isinstance(result.error, GuardNotSatisfiedError)
        assert result.error.guard_type == "role"
        assert result.error.guard_value == "editor"

    def test_no_transition_when_state_unchanged(self) -> None:
        """Test that same state is allowed (no-op)."""
        sm = StateMachineSpec(
            status_field="status",
            states=["open", "closed"],
            transitions=[StateTransitionSpec(from_state="open", to_state="closed")],
        )

        validator = TransitionValidator(sm)
        result = validator.validate_transition("open", "open", {})

        # Same state should be valid (no actual transition)
        assert result.is_valid


class TestValidateStatusUpdate:
    """Tests for validate_status_update helper function."""

    def test_no_state_machine(self) -> None:
        """Test that None is returned when entity has no state machine."""
        result = validate_status_update(
            state_machine=None,
            current_data={"status": "open"},
            update_data={"status": "closed"},
        )
        assert result is None

    def test_no_status_in_update(self) -> None:
        """Test that None is returned when status is not being updated."""
        sm = StateMachineSpec(
            status_field="status",
            states=["open", "closed"],
            transitions=[StateTransitionSpec(from_state="open", to_state="closed")],
        )

        result = validate_status_update(
            state_machine=sm,
            current_data={"status": "open", "title": "Test"},
            update_data={"title": "Updated Test"},  # No status change
        )
        assert result is None

    def test_valid_status_change(self) -> None:
        """Test valid status change validation."""
        sm = StateMachineSpec(
            status_field="status",
            states=["open", "closed"],
            transitions=[StateTransitionSpec(from_state="open", to_state="closed")],
        )

        result = validate_status_update(
            state_machine=sm,
            current_data={"status": "open"},
            update_data={"status": "closed"},
        )

        assert result is not None
        assert result.is_valid

    def test_invalid_status_change(self) -> None:
        """Test invalid status change validation."""
        sm = StateMachineSpec(
            status_field="status",
            states=["open", "assigned", "closed"],
            transitions=[
                StateTransitionSpec(from_state="open", to_state="assigned"),
                StateTransitionSpec(from_state="assigned", to_state="closed"),
            ],
        )

        result = validate_status_update(
            state_machine=sm,
            current_data={"status": "open"},
            update_data={"status": "closed"},  # Can't skip assigned
        )

        assert result is not None
        assert not result.is_valid
        assert isinstance(result.error, InvalidTransitionError)

    def test_initial_status_valid(self) -> None:
        """Test setting initial status when current is None."""
        sm = StateMachineSpec(
            status_field="status",
            states=["draft", "published"],
            transitions=[StateTransitionSpec(from_state="draft", to_state="published")],
        )

        result = validate_status_update(
            state_machine=sm,
            current_data={"status": None},
            update_data={"status": "draft"},
        )

        assert result is not None
        assert result.is_valid

    def test_initial_status_invalid(self) -> None:
        """Test setting invalid initial status."""
        sm = StateMachineSpec(
            status_field="status",
            states=["draft", "published"],
            transitions=[StateTransitionSpec(from_state="draft", to_state="published")],
        )

        result = validate_status_update(
            state_machine=sm,
            current_data={"status": None},
            update_data={"status": "invalid_state"},
        )

        assert result is not None
        assert not result.is_valid
        assert isinstance(result.error, InvalidTransitionError)

    def test_merged_data_for_guards(self) -> None:
        """Test that update data is merged with current for guard checks."""
        sm = StateMachineSpec(
            status_field="status",
            states=["open", "assigned"],
            transitions=[
                StateTransitionSpec(
                    from_state="open",
                    to_state="assigned",
                    guards=[TransitionGuardSpec(requires_field="assignee")],
                ),
            ],
        )

        # Assignee is in update_data, not current_data
        result = validate_status_update(
            state_machine=sm,
            current_data={"status": "open"},
            update_data={"status": "assigned", "assignee": "john@example.com"},
        )

        assert result is not None
        assert result.is_valid


class TestStateMachineSpec:
    """Tests for StateMachineSpec helper methods."""

    def test_get_transitions_from(self) -> None:
        """Test getting transitions from a state."""
        sm = StateMachineSpec(
            status_field="status",
            states=["a", "b", "c"],
            transitions=[
                StateTransitionSpec(from_state="a", to_state="b"),
                StateTransitionSpec(from_state="a", to_state="c"),
                StateTransitionSpec(from_state="b", to_state="c"),
            ],
        )

        from_a = sm.get_transitions_from("a")
        assert len(from_a) == 2
        assert {t.to_state for t in from_a} == {"b", "c"}

    def test_get_allowed_targets(self) -> None:
        """Test getting allowed target states."""
        sm = StateMachineSpec(
            status_field="status",
            states=["a", "b", "c"],
            transitions=[
                StateTransitionSpec(from_state="a", to_state="b"),
                StateTransitionSpec(from_state="a", to_state="c"),
            ],
        )

        targets = sm.get_allowed_targets("a")
        assert targets == {"b", "c"}

    def test_is_transition_allowed(self) -> None:
        """Test checking if transition is allowed."""
        sm = StateMachineSpec(
            status_field="status",
            states=["a", "b", "c"],
            transitions=[
                StateTransitionSpec(from_state="a", to_state="b"),
            ],
        )

        assert sm.is_transition_allowed("a", "b") is True
        assert sm.is_transition_allowed("a", "c") is False

    def test_get_transition(self) -> None:
        """Test getting specific transition."""
        sm = StateMachineSpec(
            status_field="status",
            states=["a", "b"],
            transitions=[
                StateTransitionSpec(from_state="a", to_state="b"),
            ],
        )

        t = sm.get_transition("a", "b")
        assert t is not None
        assert t.from_state == "a"
        assert t.to_state == "b"

        t_none = sm.get_transition("b", "a")
        assert t_none is None


class TestAutoTransitionSpec:
    """Tests for AutoTransitionSpec."""

    def test_delay_seconds_minutes(self) -> None:
        """Test delay calculation for minutes."""
        auto = AutoTransitionSpec(delay_value=5, delay_unit=TimeUnit.MINUTES)
        assert auto.delay_seconds == 5 * 60

    def test_delay_seconds_hours(self) -> None:
        """Test delay calculation for hours."""
        auto = AutoTransitionSpec(delay_value=2, delay_unit=TimeUnit.HOURS)
        assert auto.delay_seconds == 2 * 3600

    def test_delay_seconds_days(self) -> None:
        """Test delay calculation for days."""
        auto = AutoTransitionSpec(delay_value=7, delay_unit=TimeUnit.DAYS)
        assert auto.delay_seconds == 7 * 86400


# =============================================================================
# Expression Guard Tests
# =============================================================================


class TestEvaluateGuardExpr:
    """Tests for evaluate_guard_expr — typed expression evaluation."""

    def test_simple_field_equality(self) -> None:
        """reviewer != preparer (four-eye rule)."""
        expr = {
            "op": "!=",
            "left": {"path": ["reviewer"]},
            "right": {"path": ["preparer"]},
        }
        assert evaluate_guard_expr(expr, {"reviewer": "alice", "preparer": "bob"}) is True
        assert evaluate_guard_expr(expr, {"reviewer": "alice", "preparer": "alice"}) is False

    def test_field_equals_literal(self) -> None:
        """status == 'completed'."""
        expr = {
            "op": "==",
            "left": {"path": ["status"]},
            "right": {"value": "completed"},
        }
        assert evaluate_guard_expr(expr, {"status": "completed"}) is True
        assert evaluate_guard_expr(expr, {"status": "pending"}) is False

    def test_self_prefix_stripped(self) -> None:
        """self->reviewer != self->preparer — 'self' prefix ignored."""
        expr = {
            "op": "!=",
            "left": {"path": ["self", "reviewer"]},
            "right": {"path": ["self", "preparer"]},
        }
        assert evaluate_guard_expr(expr, {"reviewer": "alice", "preparer": "bob"}) is True

    def test_nested_field_ref(self) -> None:
        """self->contact->aml_status == 'completed'."""
        expr = {
            "op": "==",
            "left": {"path": ["self", "contact", "aml_status"]},
            "right": {"value": "completed"},
        }
        data = {"contact": {"aml_status": "completed"}}
        assert evaluate_guard_expr(expr, data) is True
        data = {"contact": {"aml_status": "pending"}}
        assert evaluate_guard_expr(expr, data) is False

    def test_and_expression(self) -> None:
        """reviewer != preparer and status == 'review'."""
        expr = {
            "op": "and",
            "left": {
                "op": "!=",
                "left": {"path": ["reviewer"]},
                "right": {"path": ["preparer"]},
            },
            "right": {
                "op": "==",
                "left": {"path": ["status"]},
                "right": {"value": "review"},
            },
        }
        data = {"reviewer": "alice", "preparer": "bob", "status": "review"}
        assert evaluate_guard_expr(expr, data) is True
        data = {"reviewer": "alice", "preparer": "alice", "status": "review"}
        assert evaluate_guard_expr(expr, data) is False

    def test_or_expression(self) -> None:
        """role == 'admin' or role == 'manager'."""
        expr = {
            "op": "or",
            "left": {"op": "==", "left": {"path": ["role"]}, "right": {"value": "admin"}},
            "right": {"op": "==", "left": {"path": ["role"]}, "right": {"value": "manager"}},
        }
        assert evaluate_guard_expr(expr, {"role": "admin"}) is True
        assert evaluate_guard_expr(expr, {"role": "manager"}) is True
        assert evaluate_guard_expr(expr, {"role": "viewer"}) is False

    def test_not_expression(self) -> None:
        """not is_locked."""
        expr = {"op": "not", "operand": {"path": ["is_locked"]}}
        assert evaluate_guard_expr(expr, {"is_locked": False}) is True
        assert evaluate_guard_expr(expr, {"is_locked": True}) is False

    def test_numeric_comparison(self) -> None:
        """amount > 0."""
        expr = {
            "op": ">",
            "left": {"path": ["amount"]},
            "right": {"value": 0},
        }
        assert evaluate_guard_expr(expr, {"amount": 100}) is True
        assert evaluate_guard_expr(expr, {"amount": 0}) is False
        assert evaluate_guard_expr(expr, {"amount": -5}) is False

    def test_null_field_handling(self) -> None:
        """reviewer != null (field must be set)."""
        expr = {
            "op": "!=",
            "left": {"path": ["reviewer"]},
            "right": {"value": None},
        }
        assert evaluate_guard_expr(expr, {"reviewer": "alice"}) is True
        assert evaluate_guard_expr(expr, {"reviewer": None}) is False
        assert evaluate_guard_expr(expr, {}) is False

    def test_in_expression(self) -> None:
        """status in ['approved', 'verified']."""
        expr = {
            "value": {"path": ["status"]},
            "items": [{"value": "approved"}, {"value": "verified"}],
            "negated": False,
        }
        assert evaluate_guard_expr(expr, {"status": "approved"}) is True
        assert evaluate_guard_expr(expr, {"status": "pending"}) is False

    def test_not_in_expression(self) -> None:
        """status not in ['draft', 'cancelled']."""
        expr = {
            "value": {"path": ["status"]},
            "items": [{"value": "draft"}, {"value": "cancelled"}],
            "negated": True,
        }
        assert evaluate_guard_expr(expr, {"status": "active"}) is True
        assert evaluate_guard_expr(expr, {"status": "draft"}) is False

    def test_literal_true(self) -> None:
        """Literal true always passes."""
        assert evaluate_guard_expr({"value": True}, {}) is True

    def test_literal_false(self) -> None:
        """Literal false always fails."""
        assert evaluate_guard_expr({"value": False}, {}) is False


class TestExpressionGuardInValidator:
    """Tests for expression guards integrated into TransitionValidator."""

    def _four_eye_guard(self) -> TransitionGuardSpec:
        """Create a 'reviewer != preparer' expression guard."""
        return TransitionGuardSpec(
            guard_expr={
                "op": "!=",
                "left": {"path": ["reviewer"]},
                "right": {"path": ["preparer"]},
            },
            guard_message="Reviewer must differ from the preparer (four-eye rule)",
        )

    def test_expr_guard_passes(self) -> None:
        """Expression guard passes when condition is true."""
        sm = StateMachineSpec(
            status_field="status",
            states=["review", "closed"],
            transitions=[
                StateTransitionSpec(
                    from_state="review",
                    to_state="closed",
                    guards=[self._four_eye_guard()],
                ),
            ],
        )
        validator = TransitionValidator(sm)
        result = validator.validate_transition(
            "review", "closed", {"reviewer": "alice", "preparer": "bob"}
        )
        assert result.is_valid

    def test_expr_guard_fails(self) -> None:
        """Expression guard fails when condition is false."""
        sm = StateMachineSpec(
            status_field="status",
            states=["review", "closed"],
            transitions=[
                StateTransitionSpec(
                    from_state="review",
                    to_state="closed",
                    guards=[self._four_eye_guard()],
                ),
            ],
        )
        validator = TransitionValidator(sm)
        result = validator.validate_transition(
            "review", "closed", {"reviewer": "alice", "preparer": "alice"}
        )
        assert not result.is_valid
        assert isinstance(result.error, GuardNotSatisfiedError)
        assert result.error.guard_type == "expression"
        assert "four-eye" in str(result.error)

    def test_expr_guard_uses_custom_message(self) -> None:
        """Guard message is the custom message from DSL."""
        sm = StateMachineSpec(
            status_field="status",
            states=["review", "closed"],
            transitions=[
                StateTransitionSpec(
                    from_state="review",
                    to_state="closed",
                    guards=[self._four_eye_guard()],
                ),
            ],
        )
        validator = TransitionValidator(sm)
        result = validator.validate_transition(
            "review", "closed", {"reviewer": "alice", "preparer": "alice"}
        )
        assert not result.is_valid
        assert "Reviewer must differ from the preparer" in str(result.error)

    def test_expr_guard_combined_with_field_guard(self) -> None:
        """Expression + field guards both checked."""
        sm = StateMachineSpec(
            status_field="status",
            states=["review", "closed"],
            transitions=[
                StateTransitionSpec(
                    from_state="review",
                    to_state="closed",
                    guards=[
                        TransitionGuardSpec(requires_field="reviewer"),
                        self._four_eye_guard(),
                    ],
                ),
            ],
        )
        validator = TransitionValidator(sm)

        # Field guard fails (no reviewer)
        result = validator.validate_transition("review", "closed", {"preparer": "bob"})
        assert not result.is_valid
        assert result.error.guard_type == "requires"  # type: ignore[union-attr]

        # Field guard passes but expr guard fails (same person)
        result = validator.validate_transition(
            "review", "closed", {"reviewer": "alice", "preparer": "alice"}
        )
        assert not result.is_valid
        assert result.error.guard_type == "expression"  # type: ignore[union-attr]

        # Both pass
        result = validator.validate_transition(
            "review", "closed", {"reviewer": "alice", "preparer": "bob"}
        )
        assert result.is_valid

    def test_expr_guard_default_message(self) -> None:
        """Without custom message, a default is used."""
        guard = TransitionGuardSpec(
            guard_expr={
                "op": ">",
                "left": {"path": ["amount"]},
                "right": {"value": 0},
            },
            # No guard_message
        )
        sm = StateMachineSpec(
            status_field="status",
            states=["pending", "approved"],
            transitions=[
                StateTransitionSpec(from_state="pending", to_state="approved", guards=[guard]),
            ],
        )
        validator = TransitionValidator(sm)
        result = validator.validate_transition("pending", "approved", {"amount": 0})
        assert not result.is_valid
        assert "Guard condition not met" in str(result.error)

    def test_validate_status_update_with_expr_guard(self) -> None:
        """Expression guards work through the validate_status_update entry point."""
        sm = StateMachineSpec(
            status_field="status",
            states=["review", "closed"],
            transitions=[
                StateTransitionSpec(
                    from_state="review",
                    to_state="closed",
                    guards=[self._four_eye_guard()],
                ),
            ],
        )
        # Different people — should pass
        result = validate_status_update(
            sm,
            current_data={"status": "review", "reviewer": "alice", "preparer": "bob"},
            update_data={"status": "closed"},
        )
        assert result is not None
        assert result.is_valid

        # Same person — should fail
        result = validate_status_update(
            sm,
            current_data={"status": "review", "reviewer": "alice", "preparer": "alice"},
            update_data={"status": "closed"},
        )
        assert result is not None
        assert not result.is_valid
