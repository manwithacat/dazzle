"""
State machine validation and transition handling for DNR Backend.

This module provides runtime validation for state machine transitions,
including guard evaluation and error handling.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from dazzle_back.specs.entity import StateMachineSpec, StateTransitionSpec

logger = logging.getLogger(__name__)


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
# Guard Expression Evaluator
# =============================================================================


def evaluate_guard_expr(expr: dict[str, Any], entity_data: dict[str, Any]) -> bool:
    """Evaluate a serialized Expr AST against entity data.

    The ``expr`` dict is a JSON-serialized form of ``dazzle.core.ir.expressions.Expr``.
    We dispatch on the Pydantic discriminator field to determine the node type.

    Returns True if the guard passes (transition allowed), False otherwise.
    """
    return bool(_eval_node(expr, entity_data))


def _eval_node(node: dict[str, Any], data: dict[str, Any]) -> Any:
    """Recursively evaluate an expression AST node.

    Dispatch order matters: more specific node shapes are checked first
    to avoid ambiguity (e.g. InExpr has "value" but is not a Literal).
    """
    # InExpr — {"value": ..., "items": [...]}  (check before Literal)
    if "items" in node:
        return _eval_in(node, data)

    # IfExpr — {"condition": ..., "then_expr": ..., "else_expr": ...}
    if "condition" in node and "then_expr" in node:
        return _eval_if(node, data)

    # FieldRef — {"path": [...]}
    if "path" in node:
        return _eval_field_ref(node["path"], data)

    # DurationLiteral — {"value": int, "unit": str}
    if "unit" in node:
        return _eval_duration(node.get("value", 0), node["unit"])

    # BinaryExpr — {"op": str, "left": ..., "right": ...}
    if "op" in node and "left" in node and "right" in node:
        return _eval_binary(node, data)

    # UnaryExpr — {"op": str, "operand": ...}
    if "op" in node and "operand" in node:
        return _eval_unary(node, data)

    # FuncCall — {"name": str, "args": [...]}
    if "name" in node and "args" in node:
        return _eval_func(node, data)

    # Literal — {"value": ...}  (catch-all for simple value nodes)
    if "value" in node:
        return node["value"]

    return None


def _eval_field_ref(path: list[str], data: dict[str, Any]) -> Any:
    """Resolve a field path against entity data.

    Strips leading ``self`` since entity_data already represents the entity.
    """
    segments = list(path)
    if segments and segments[0] == "self":
        segments = segments[1:]

    value: Any = data
    for segment in segments:
        if isinstance(value, dict):
            value = value.get(segment)
        else:
            return None
        if value is None:
            return None
    return value


def _eval_duration(value: int, unit: str) -> timedelta:
    """Convert a duration literal to timedelta."""
    if unit == "h":
        return timedelta(hours=value)
    if unit == "min":
        return timedelta(minutes=value)
    if unit == "w":
        return timedelta(weeks=value)
    return timedelta(days=value)  # d, m, y all default to days for simplicity


def _normalize_value(value: Any) -> Any:
    """Normalize a value for comparison."""
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, str):
        try:
            if "T" in value:
                return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
            elif len(value) == 10 and value[4] == "-":
                return date.fromisoformat(value)
        except ValueError:
            pass
    if isinstance(value, Decimal):
        return float(value)
    return value


def _eval_binary(node: dict[str, Any], data: dict[str, Any]) -> Any:
    """Evaluate a binary expression."""
    op = node["op"]
    left = _eval_node(node["left"], data)
    right = _eval_node(node["right"], data)

    # Short-circuit logical operators
    if op == "and":
        return bool(left) and bool(right)
    if op == "or":
        return bool(left) or bool(right)

    # Handle None comparisons
    if left is None or right is None:
        if op == "==":
            return left is None and right is None
        if op == "!=":
            return not (left is None and right is None)
        return False

    left = _normalize_value(left)
    right = _normalize_value(right)

    # Date + timedelta arithmetic
    if isinstance(left, date) and isinstance(right, timedelta):
        right = date.today() + right
    elif isinstance(left, timedelta) and isinstance(right, date):
        left = date.today() + left

    try:
        if op == "==":
            return left == right
        if op == "!=":
            return left != right
        if op == "<":
            return left < right
        if op == ">":
            return left > right
        if op == "<=":
            return left <= right
        if op == ">=":
            return left >= right
        if op == "+":
            return left + right
        if op == "-":
            return left - right
        if op == "*":
            return left * right
        if op == "/":
            return left / right if right != 0 else None
        if op == "%":
            return left % right if right != 0 else None
    except TypeError:
        return False

    return None


def _eval_unary(node: dict[str, Any], data: dict[str, Any]) -> Any:
    """Evaluate a unary expression."""
    operand = _eval_node(node["operand"], data)
    if node["op"] == "not":
        return not bool(operand)
    if node["op"] == "-":
        try:
            return -operand
        except TypeError:
            return None
    return None


def _eval_func(node: dict[str, Any], data: dict[str, Any]) -> Any:
    """Evaluate a function call."""
    name = node["name"]
    args = [_eval_node(a, data) for a in node.get("args", [])]

    if name == "today":
        return date.today()
    if name == "len" and args:
        try:
            return len(args[0])
        except TypeError:
            return 0
    return None


def _eval_in(node: dict[str, Any], data: dict[str, Any]) -> bool:
    """Evaluate a membership test (in / not in)."""
    value = _eval_node(node["value"], data)
    items = [_eval_node(i, data) for i in node.get("items", [])]
    result = value in items
    if node.get("negated", False):
        return not result
    return result


def _eval_if(node: dict[str, Any], data: dict[str, Any]) -> Any:
    """Evaluate a conditional expression."""
    if bool(_eval_node(node["condition"], data)):
        return _eval_node(node["then_expr"], data)
    for cond, val in node.get("elif_branches", []):
        if bool(_eval_node(cond, data)):
            return _eval_node(val, data)
    return _eval_node(node["else_expr"], data)


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
    4. Expression guards are satisfied (typed expression evaluates to true)
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

            # Check expression guard
            if guard.guard_expr:
                try:
                    result = evaluate_guard_expr(guard.guard_expr, entity_data)
                except Exception:
                    logger.warning(
                        "Guard expression evaluation failed for %s -> %s",
                        from_state,
                        to_state,
                        exc_info=True,
                    )
                    result = False

                if not result:
                    message = guard.guard_message or (
                        f"Guard condition not met for transition '{from_state}' -> '{to_state}'"
                    )
                    return TransitionValidationResult.failure(
                        GuardNotSatisfiedError(
                            from_state,
                            to_state,
                            "expression",
                            str(guard.guard_expr),
                            message,
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
