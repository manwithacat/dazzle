"""
State machine validation and transition handling for DNR Backend.

This module provides runtime validation for state machine transitions,
including guard evaluation and error handling.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from dazzle_back.specs.entity import StateMachineSpec, StateTransitionSpec


# =============================================================================
# Exceptions
# =============================================================================


class TransitionError(Exception):
    """Base exception for state machine transition errors."""

    pass


class InvalidTransitionError(TransitionError):
    """Raised when a transition is not allowed by the state machine definition."""

    def __init__(
        self,
        from_state: str,
        to_state: str,
        allowed_states: set[str] | None = None,
        message: str | None = None,
    ):
        self.from_state = from_state
        self.to_state = to_state
        self.allowed_states = allowed_states or set()
        if message:
            super().__init__(message)
        elif allowed_states:
            allowed = ", ".join(sorted(allowed_states))
            super().__init__(
                f"Invalid transition from '{from_state}' to '{to_state}'. Allowed states: {allowed}"
            )
        else:
            super().__init__(f"Invalid transition from '{from_state}' to '{to_state}'")


class GuardNotSatisfiedError(TransitionError):
    """Raised when a transition guard condition is not satisfied."""

    def __init__(
        self,
        from_state: str,
        to_state: str,
        guard_type: str,
        guard_value: str,
        message: str | None = None,
    ):
        self.from_state = from_state
        self.to_state = to_state
        self.guard_type = guard_type
        self.guard_value = guard_value
        if message:
            super().__init__(message)
        else:
            super().__init__(
                f"Guard not satisfied for transition '{from_state}' -> '{to_state}': "
                f"{guard_type} {guard_value}"
            )


# =============================================================================
# Validation Result
# =============================================================================


@dataclass
class TransitionValidationResult:
    """Result of validating a state transition."""

    is_valid: bool
    error: TransitionError | None = None
    transition: StateTransitionSpec | None = None

    @classmethod
    def success(cls, transition: StateTransitionSpec) -> TransitionValidationResult:
        """Create a successful validation result."""
        return cls(is_valid=True, transition=transition)

    @classmethod
    def failure(cls, error: TransitionError) -> TransitionValidationResult:
        """Create a failed validation result."""
        return cls(is_valid=False, error=error)


# =============================================================================
# Transition Validator
# =============================================================================


class TransitionValidator:
    """
    Validates state transitions against a state machine specification.

    Checks:
    1. The transition is defined in the state machine
    2. Required field guards are satisfied (field has a value)
    3. Role guards are satisfied (user has required role)
    """

    def __init__(self, state_machine: StateMachineSpec):
        self.state_machine = state_machine

    def validate_transition(
        self,
        from_state: str,
        to_state: str,
        entity_data: dict[str, Any],
        user_roles: list[str] | None = None,
    ) -> TransitionValidationResult:
        """
        Validate a state transition.

        Args:
            from_state: Current state value
            to_state: Desired new state value
            entity_data: Current entity data (for checking field guards)
            user_roles: List of roles the current user has (for role guards)

        Returns:
            TransitionValidationResult with validation outcome
        """
        # If states are the same, no transition needed
        if from_state == to_state:
            # Return a dummy success - no actual transition
            return TransitionValidationResult(is_valid=True)

        # Check if transition is allowed
        transition = self.state_machine.get_transition(from_state, to_state)
        if transition is None:
            allowed = self.state_machine.get_allowed_targets(from_state)
            return TransitionValidationResult.failure(
                InvalidTransitionError(from_state, to_state, allowed)
            )

        # Check guards
        for guard in transition.guards:
            # Check field requirement guard
            if guard.requires_field:
                field_value = entity_data.get(guard.requires_field)
                if field_value is None or field_value == "":
                    return TransitionValidationResult.failure(
                        GuardNotSatisfiedError(
                            from_state,
                            to_state,
                            "requires",
                            guard.requires_field,
                            f"Field '{guard.requires_field}' must be set "
                            f"for transition '{from_state}' -> '{to_state}'",
                        )
                    )

            # Check role guard
            if guard.requires_role:
                user_roles = user_roles or []
                if guard.requires_role not in user_roles:
                    return TransitionValidationResult.failure(
                        GuardNotSatisfiedError(
                            from_state,
                            to_state,
                            "role",
                            guard.requires_role,
                            f"User must have role '{guard.requires_role}' "
                            f"for transition '{from_state}' -> '{to_state}'",
                        )
                    )

        return TransitionValidationResult.success(transition)


# =============================================================================
# Helper Functions
# =============================================================================


def validate_status_update(
    state_machine: StateMachineSpec | None,
    current_data: dict[str, Any],
    update_data: dict[str, Any],
    user_roles: list[str] | None = None,
) -> TransitionValidationResult | None:
    """
    Validate a status field update against a state machine.

    This is the main entry point for validation during CRUD updates.

    Args:
        state_machine: State machine spec (or None if entity has no state machine)
        current_data: Current entity data
        update_data: Data being updated
        user_roles: User's roles for role guard checks

    Returns:
        TransitionValidationResult if status is changing, None otherwise
    """
    if state_machine is None:
        return None

    status_field = state_machine.status_field
    new_status = update_data.get(status_field)

    # No status change in update
    if new_status is None:
        return None

    current_status = current_data.get(status_field)
    if current_status is None:
        # No current status - allow setting initial state
        if new_status in state_machine.states:
            return TransitionValidationResult(is_valid=True)
        else:
            return TransitionValidationResult.failure(
                InvalidTransitionError(
                    "<none>",
                    new_status,
                    set(state_machine.states),
                    f"Invalid state '{new_status}'. "
                    f"Valid states: {', '.join(state_machine.states)}",
                )
            )

    # Status is changing - validate the transition
    # Merge current and update data for guard checks
    merged_data = {**current_data, **update_data}

    validator = TransitionValidator(state_machine)
    return validator.validate_transition(current_status, new_status, merged_data, user_roles)
