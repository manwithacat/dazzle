"""
Unit tests for action purity (v0.5.0 feature).

Tests ActionPurity enum and purity-based action classification.
"""

import pytest

from dazzle.page.specs.actions import (
    ActionPurity,
    ActionSpec,
    FetchEffect,
    NavigateEffect,
    PatchOp,
    PatchSpec,
    TransitionSpec,
)


class TestActionPurityEnum:
    """Tests for ActionPurity enum values."""

    def test_pure_value(self):
        """Test pure purity value."""
        assert ActionPurity.PURE == "pure"

    def test_impure_value(self):
        """Test impure purity value."""
        assert ActionPurity.IMPURE == "impure"


class TestExplicitPurity:
    """Tests for explicitly set action purity."""

    def test_explicit_pure(self):
        """Test action explicitly marked as pure."""
        action = ActionSpec(
            name="increment",
            purity=ActionPurity.PURE,
            transitions=[
                TransitionSpec(
                    target_state="count",
                    update=PatchSpec(op=PatchOp.SET, path="count", value=1),
                )
            ],
        )
        assert action.purity == ActionPurity.PURE
        assert action.is_pure is True
        assert action.is_impure is False

    def test_explicit_impure(self):
        """Test action explicitly marked as impure."""
        action = ActionSpec(
            name="loadData",
            purity=ActionPurity.IMPURE,
            effect=FetchEffect(backend_service="get_data"),
        )
        assert action.purity == ActionPurity.IMPURE
        assert action.is_pure is False
        assert action.is_impure is True

    def test_explicit_pure_overrides_effect(self):
        """Test that explicit pure overrides presence of effect."""
        # This is a bit strange (marking action with effect as pure),
        # but explicit setting should win
        action = ActionSpec(
            name="logAndSet",
            purity=ActionPurity.PURE,  # Explicitly pure
            effect=FetchEffect(backend_service="log_event"),  # Has effect
        )
        assert action.is_pure is True
        assert action.is_impure is False

    def test_explicit_impure_overrides_no_effect(self):
        """Test that explicit impure overrides lack of effect."""
        # Marking action without effect as impure (maybe it has hidden side effects)
        action = ActionSpec(
            name="resetWithSideEffect",
            purity=ActionPurity.IMPURE,  # Explicitly impure
            # No effect field
        )
        assert action.is_pure is False
        assert action.is_impure is True


class TestInferredPurity:
    """Tests for automatic purity inference when purity is None."""

    @pytest.mark.parametrize(
        ("action", "expected_pure"),
        [
            (
                ActionSpec(
                    name="selectItem",
                    transitions=[
                        TransitionSpec(
                            target_state="selectedId",
                            update=PatchSpec(op=PatchOp.SET, path="selectedId", value="123"),
                        )
                    ],
                ),
                True,
            ),
            (ActionSpec(name="noop"), True),
            (ActionSpec(name="loadUsers", effect=FetchEffect(backend_service="list_users")), False),
            (ActionSpec(name="goToDetails", effect=NavigateEffect(route="/details/:id")), False),
        ],
        ids=[
            "test_inferred_pure_no_effect",
            "test_inferred_pure_empty_action",
            "test_inferred_impure_fetch_effect",
            "test_inferred_impure_navigate_effect",
        ],
    )
    def test_inferred_purity(self, action: ActionSpec, expected_pure: bool) -> None:
        """Purity is inferred as pure when no effect is present, impure otherwise."""
        assert action.purity is None
        assert action.is_pure is expected_pure
        assert action.is_impure is not expected_pure

    def test_inferred_impure_with_transitions(self):
        """Test action inferred as impure even with transitions."""
        action = ActionSpec(
            name="submitForm",
            transitions=[
                TransitionSpec(
                    target_state="isSubmitting",
                    update=PatchSpec(op=PatchOp.SET, path="isSubmitting", value=True),
                )
            ],
            effect=FetchEffect(backend_service="submit_form"),
        )
        # Has effect -> impure, regardless of transitions
        assert action.is_pure is False
        assert action.is_impure is True


class TestPurityIntegration:
    """Tests for purity in practical scenarios."""

    def test_state_update_action_is_pure(self):
        """Test typical state update action is pure."""
        action = ActionSpec(
            name="setFilter",
            inputs={"filter": "str"},
            transitions=[
                TransitionSpec(
                    target_state="filter",
                    update=PatchSpec(op=PatchOp.SET, path="filter", value=None),
                )
            ],
        )
        assert action.is_pure is True

    def test_crud_create_action_is_impure(self):
        """Test CRUD create action is impure."""
        action = ActionSpec(
            name="createTask",
            inputs={"title": "str", "description": "str"},
            effect=FetchEffect(backend_service="create_task"),
        )
        assert action.is_impure is True

    def test_navigation_action_is_impure(self):
        """Test navigation action is impure."""
        action = ActionSpec(
            name="viewTask",
            inputs={"taskId": "uuid"},
            effect=NavigateEffect(route="/tasks/:taskId"),
        )
        assert action.is_impure is True
