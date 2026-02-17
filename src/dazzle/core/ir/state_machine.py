"""
State machine types for DAZZLE IR.

This module contains types for defining state transitions within entities,
including guards, auto-transitions, and role-based access control.

Example DSL:
    entity Ticket:
      status: enum(open, assigned, resolved, closed)

      transitions:
        open -> assigned: requires assignee
        assigned -> resolved: requires resolution_note
        resolved -> closed: auto after 7 days OR manual
        * -> open: role(admin)  # reopen from any state
"""

from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict, Field

if TYPE_CHECKING:
    from .expressions import Expr

# Time conversion constants
SECONDS_PER_MINUTE = 60
SECONDS_PER_HOUR = 3600
SECONDS_PER_DAY = 86400


class TimeUnit(StrEnum):
    """Time units for auto-transition delays."""

    MINUTES = "minutes"
    HOURS = "hours"
    DAYS = "days"


class TransitionTrigger(StrEnum):
    """How a transition can be triggered."""

    MANUAL = "manual"  # User explicitly triggers the transition
    AUTO = "auto"  # System triggers automatically (with optional delay)


class TransitionGuard(BaseModel):
    """
    A guard condition that must be satisfied for a transition.

    Guards can be:
    - Field requirements: requires assignee (field must be set)
    - Role requirements: role(admin) (user must have role)
    - Custom conditions: when condition_expr
    - Expression guards (v0.29.0): guard: self->signatory->aml_status == "completed"
    """

    # Field that must be set for the transition
    requires_field: str | None = None

    # Role that user must have for the transition
    requires_role: str | None = None

    # Custom condition expression (string for now, can be ConditionExpr later)
    condition: str | None = None

    # v0.29.0: Typed expression guard (cross-entity predicates)
    guard_expr: Expr | None = None
    # Optional human-readable message for guard failure
    guard_message: str | None = None

    model_config = ConfigDict(frozen=True)

    @property
    def is_field_guard(self) -> bool:
        """Check if this is a field requirement guard."""
        return self.requires_field is not None

    @property
    def is_role_guard(self) -> bool:
        """Check if this is a role-based guard."""
        return self.requires_role is not None

    @property
    def is_expr_guard(self) -> bool:
        """Check if this is a typed expression guard."""
        return self.guard_expr is not None


class AutoTransitionSpec(BaseModel):
    """
    Specification for automatic transitions.

    Example: auto after 7 days
    """

    delay_value: int
    delay_unit: TimeUnit
    # Whether manual transition is also allowed
    allow_manual: bool = False

    model_config = ConfigDict(frozen=True)

    @property
    def delay_seconds(self) -> int:
        """Get delay in seconds."""
        if self.delay_unit == TimeUnit.MINUTES:
            return self.delay_value * SECONDS_PER_MINUTE
        elif self.delay_unit == TimeUnit.HOURS:
            return self.delay_value * SECONDS_PER_HOUR
        else:  # DAYS
            return self.delay_value * SECONDS_PER_DAY


class StateTransition(BaseModel):
    """
    A single state transition definition.

    Attributes:
        from_state: State to transition from ("*" means any state)
        to_state: State to transition to
        trigger: How the transition is triggered (manual or auto)
        guards: Conditions that must be met for the transition
        auto_spec: Specification for automatic transitions
    """

    from_state: str
    to_state: str
    trigger: TransitionTrigger = TransitionTrigger.MANUAL
    guards: list[TransitionGuard] = Field(default_factory=list)
    auto_spec: AutoTransitionSpec | None = None

    model_config = ConfigDict(frozen=True)

    @property
    def is_wildcard(self) -> bool:
        """Check if this is a wildcard transition (from any state)."""
        return self.from_state == "*"

    @property
    def is_auto(self) -> bool:
        """Check if this is an automatic transition."""
        return self.trigger == TransitionTrigger.AUTO

    @property
    def has_guards(self) -> bool:
        """Check if this transition has any guards."""
        return len(self.guards) > 0


class StateMachineSpec(BaseModel):
    """
    Complete state machine specification for an entity.

    Attributes:
        status_field: Name of the field that holds the state
        states: List of valid states (from enum definition)
        transitions: List of allowed state transitions
    """

    status_field: str
    states: list[str] = Field(default_factory=list)
    transitions: list[StateTransition] = Field(default_factory=list)

    model_config = ConfigDict(frozen=True)

    def get_transitions_from(self, state: str) -> list[StateTransition]:
        """Get all transitions from a given state."""
        result = []
        for t in self.transitions:
            if t.from_state == state or t.from_state == "*":
                result.append(t)
        return result

    def get_allowed_targets(self, from_state: str) -> set[str]:
        """Get all states that can be transitioned to from a given state."""
        targets = set()
        for t in self.get_transitions_from(from_state):
            targets.add(t.to_state)
        return targets

    def is_transition_allowed(self, from_state: str, to_state: str) -> bool:
        """Check if a transition is allowed (ignoring guards)."""
        return to_state in self.get_allowed_targets(from_state)

    def get_transition(self, from_state: str, to_state: str) -> StateTransition | None:
        """Get the transition definition between two states."""
        for t in self.transitions:
            if (t.from_state == from_state or t.from_state == "*") and t.to_state == to_state:
                return t
        return None


def _rebuild_transition_guard() -> None:
    """Rebuild TransitionGuard to resolve forward reference to Expr."""
    from .expressions import Expr

    TransitionGuard.model_rebuild(
        _types_namespace={"Expr": Expr},
    )


_rebuild_transition_guard()
