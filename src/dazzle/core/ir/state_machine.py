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
from typing import TYPE_CHECKING, Protocol

from pydantic import BaseModel, ConfigDict, Field

if TYPE_CHECKING:
    from .expressions import Expr
    from .process import StepEffect

# Time conversion constants
SECONDS_PER_MINUTE = 60
SECONDS_PER_HOUR = 3600
SECONDS_PER_DAY = 86400


def state_name(state: object) -> str:
    """The plain name of a state value.

    ``StateMachineSpec.states`` and transition ``from_state``/``to_state`` are typed
    ``str``, but consumers historically guarded ``s if isinstance(s, str) else s.name``
    defensively. This centralizes that guard so the footgun lives in one place
    (use this instead of re-deriving the ``isinstance`` ternary).
    """
    return state if isinstance(state, str) else getattr(state, "name", str(state))


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


class _TransitionEdge(Protocol):
    from_state: str
    to_state: str


class WildcardTransition:
    """``is_wildcard`` for a transition — shared by :class:`StateTransition`
    and its runtime twin ``dazzle.http.specs.entity.StateTransitionSpec``."""

    if TYPE_CHECKING:
        from_state: str

    @property
    def is_wildcard(self) -> bool:
        """Check if this is a wildcard transition (from any state)."""
        return self.from_state == "*"


class TransitionGraph[EdgeT: _TransitionEdge]:
    """Transition queries over ``states`` + ``transitions``.

    One definition for :class:`StateMachineSpec` and its runtime twin
    ``dazzle.http.specs.entity.StateMachineSpec``. The twin once lacked
    ``terminal_states`` and 500'd every HX-Target region fetch for
    state-machine entities (#1626 R2); sharing the queries makes that drift
    impossible.
    """

    if TYPE_CHECKING:
        states: list[str]
        transitions: list[EdgeT]

    def get_transitions_from(self, state: str) -> list[EdgeT]:
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

    def terminal_states(self) -> set[str]:
        """States with no outgoing transition to a *different* state (#1399).

        A state is terminal when, ignoring self-loops, nothing can leave it —
        the lifecycle is finished there. Self-targets are subtracted so a
        ``* -> archived`` wildcard (which makes ``archived`` reachable from
        every state, including itself) doesn't spuriously mark ``archived``
        non-terminal. With no transitions defined at all, every state is
        terminal. HTMX region poll-stop (``_region_polling_complete``) reads
        it on the runtime twin.
        """
        return {s for s in self.states if not (self.get_allowed_targets(s) - {s})}

    def get_transition(self, from_state: str, to_state: str) -> EdgeT | None:
        """Get the transition definition between two states."""
        for t in self.transitions:
            if (t.from_state == from_state or t.from_state == "*") and t.to_state == to_state:
                return t
        return None


class StateTransition(WildcardTransition, BaseModel):
    """
    A single state transition definition.

    Attributes:
        from_state: State to transition from ("*" means any state)
        to_state: State to transition to
        trigger: How the transition is triggered (manual or auto)
        guards: Conditions that must be met for the transition
        auto_spec: Specification for automatic transitions
        effects: post-commit side-effects (create/update) fired on the transition
    """

    from_state: str
    to_state: str
    trigger: TransitionTrigger = TransitionTrigger.MANUAL
    guards: list[TransitionGuard] = Field(default_factory=list)
    auto_spec: AutoTransitionSpec | None = None
    effects: list[StepEffect] = Field(default_factory=list)

    model_config = ConfigDict(frozen=True)

    @property
    def is_auto(self) -> bool:
        """Check if this is an automatic transition."""
        return self.trigger == TransitionTrigger.AUTO

    @property
    def has_guards(self) -> bool:
        """Check if this transition has any guards."""
        return len(self.guards) > 0


class StateMachineSpec(BaseModel, TransitionGraph[StateTransition]):
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

    def state_names(self) -> list[str]:
        """The states as plain name strings (via :func:`state_name`)."""
        return [state_name(s) for s in self.states]


def _rebuild_transition_guard() -> None:
    """Rebuild TransitionGuard to resolve forward reference to Expr."""
    from .expressions import Expr

    TransitionGuard.model_rebuild(
        _types_namespace={"Expr": Expr},
    )


def _rebuild_state_transition() -> None:
    """Rebuild StateTransition to resolve forward reference to StepEffect."""
    from .process import StepEffect

    StateTransition.model_rebuild(
        _types_namespace={"StepEffect": StepEffect},
    )


_rebuild_transition_guard()
_rebuild_state_transition()
