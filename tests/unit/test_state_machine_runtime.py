"""Tests for state machine runtime validation (issue #403).

Verifies that TransitionValidator correctly handles:
- Role normalization (role_ prefix stripping)
- Superuser bypass of role guards
- validate_status_update integration
"""

from __future__ import annotations

from dazzle_back.runtime.state_machine import (
    GuardNotSatisfiedError,
    InvalidTransitionError,
    TransitionValidator,
    validate_status_update,
)
from dazzle_back.specs.entity import (
    StateMachineSpec,
    StateTransitionSpec,
    TransitionGuardSpec,
)


def _make_sm(
    transitions: list[StateTransitionSpec],
    states: list[str] | None = None,
) -> StateMachineSpec:
    """Build a StateMachineSpec for testing."""
    if states is None:
        states = ["open", "approved", "closed"]
    return StateMachineSpec(
        status_field="status",
        states=states,
        transitions=transitions,
    )


def _role_guard(role: str) -> TransitionGuardSpec:
    return TransitionGuardSpec(requires_role=role)


def _field_guard(field: str) -> TransitionGuardSpec:
    return TransitionGuardSpec(requires_field=field)


# =============================================================================
# Role Normalization
# =============================================================================


class TestRoleNormalization:
    """Role guards should match regardless of role_ prefix."""

    def _sm(self) -> StateMachineSpec:
        return _make_sm(
            [
                StateTransitionSpec(
                    from_state="open",
                    to_state="approved",
                    guards=[_role_guard("school_admin")],
                ),
            ]
        )

    def test_bare_role_matches(self) -> None:
        """User with bare role name should pass the guard."""
        v = TransitionValidator(self._sm())
        result = v.validate_transition("open", "approved", {}, user_roles=["school_admin"])
        assert result.is_valid

    def test_prefixed_role_matches(self) -> None:
        """User with role_ prefixed role should pass the guard."""
        v = TransitionValidator(self._sm())
        result = v.validate_transition("open", "approved", {}, user_roles=["role_school_admin"])
        assert result.is_valid

    def test_wrong_role_rejected(self) -> None:
        """User with the wrong role should be rejected."""
        v = TransitionValidator(self._sm())
        result = v.validate_transition("open", "approved", {}, user_roles=["role_teacher"])
        assert not result.is_valid
        assert isinstance(result.error, GuardNotSatisfiedError)
        assert result.error.guard_type == "role"

    def test_no_roles_rejected(self) -> None:
        """User with no roles should be rejected."""
        v = TransitionValidator(self._sm())
        result = v.validate_transition("open", "approved", {}, user_roles=[])
        assert not result.is_valid

    def test_none_roles_rejected(self) -> None:
        """None user_roles should be rejected."""
        v = TransitionValidator(self._sm())
        result = v.validate_transition("open", "approved", {}, user_roles=None)
        assert not result.is_valid


# =============================================================================
# Superuser Bypass
# =============================================================================


class TestSuperuserBypass:
    """Superusers should bypass role guards."""

    def _sm(self) -> StateMachineSpec:
        return _make_sm(
            [
                StateTransitionSpec(
                    from_state="open",
                    to_state="approved",
                    guards=[_role_guard("admin")],
                ),
            ]
        )

    def test_superuser_bypasses_role_guard(self) -> None:
        """Superuser with no matching role should still pass."""
        v = TransitionValidator(self._sm())
        result = v.validate_transition("open", "approved", {}, user_roles=[], is_superuser=True)
        assert result.is_valid

    def test_superuser_does_not_bypass_field_guard(self) -> None:
        """Superuser should NOT bypass field requirement guards."""
        sm = _make_sm(
            [
                StateTransitionSpec(
                    from_state="open",
                    to_state="approved",
                    guards=[_field_guard("reviewer")],
                ),
            ]
        )
        v = TransitionValidator(sm)
        result = v.validate_transition("open", "approved", {}, user_roles=[], is_superuser=True)
        assert not result.is_valid
        assert isinstance(result.error, GuardNotSatisfiedError)
        assert result.error.guard_type == "requires"


# =============================================================================
# validate_status_update integration
# =============================================================================


class TestValidateStatusUpdate:
    """Integration tests for validate_status_update."""

    def _sm(self) -> StateMachineSpec:
        return _make_sm(
            [
                StateTransitionSpec(
                    from_state="open",
                    to_state="approved",
                    guards=[_role_guard("manager")],
                ),
                StateTransitionSpec(
                    from_state="approved",
                    to_state="closed",
                ),
            ]
        )

    def test_no_state_machine_returns_none(self) -> None:
        result = validate_status_update(None, {}, {"status": "open"})
        assert result is None

    def test_no_status_change_returns_none(self) -> None:
        result = validate_status_update(self._sm(), {"status": "open"}, {"title": "foo"})
        assert result is None

    def test_role_guard_with_prefixed_roles(self) -> None:
        """Roles with role_ prefix should work through validate_status_update."""
        result = validate_status_update(
            self._sm(),
            {"status": "open"},
            {"status": "approved"},
            user_roles=["role_manager"],
        )
        assert result is not None
        assert result.is_valid

    def test_role_guard_rejection(self) -> None:
        result = validate_status_update(
            self._sm(),
            {"status": "open"},
            {"status": "approved"},
            user_roles=["role_viewer"],
        )
        assert result is not None
        assert not result.is_valid

    def test_superuser_passes_role_guard(self) -> None:
        result = validate_status_update(
            self._sm(),
            {"status": "open"},
            {"status": "approved"},
            user_roles=[],
            is_superuser=True,
        )
        assert result is not None
        assert result.is_valid

    def test_invalid_transition_rejected(self) -> None:
        result = validate_status_update(
            self._sm(),
            {"status": "open"},
            {"status": "closed"},
        )
        assert result is not None
        assert not result.is_valid
        assert isinstance(result.error, InvalidTransitionError)

    def test_same_state_is_valid(self) -> None:
        result = validate_status_update(
            self._sm(),
            {"status": "open"},
            {"status": "open"},
        )
        assert result is not None
        assert result.is_valid
