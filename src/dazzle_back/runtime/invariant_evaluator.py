"""
Invariant evaluator for DNR runtime.

This module evaluates entity invariants at runtime during create/update operations.
Invariants are cross-field constraints that must always hold true.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

from dazzle_back.specs.entity import (
    DurationUnitKind,
    InvariantComparisonKind,
    InvariantExprSpec,
    InvariantLogicalKind,
    InvariantSpec,
)


class InvariantViolationError(Exception):
    """Raised when an invariant constraint is violated."""

    def __init__(self, message: str, invariant: InvariantSpec | None = None):
        self.message = message
        self.invariant = invariant
        super().__init__(message)


# =============================================================================
# Expression Evaluation
# =============================================================================


def evaluate_invariant_expr(
    expr: InvariantExprSpec,
    record: dict[str, Any],
) -> Any:
    """
    Evaluate an invariant expression for a single record.

    Args:
        expr: The invariant expression specification
        record: The record data (as a dict)

    Returns:
        The evaluated value (bool, int, float, date, str, etc.)
    """
    if expr.kind == "literal":
        return expr.value

    elif expr.kind == "field_ref":
        return _evaluate_field_ref(expr.path or [], record)

    elif expr.kind == "duration":
        return _evaluate_duration(expr)

    elif expr.kind == "comparison":
        return _evaluate_comparison(expr, record)

    elif expr.kind == "logical":
        return _evaluate_logical(expr, record)

    elif expr.kind == "not":
        return _evaluate_not(expr, record)

    else:
        return None


def _evaluate_field_ref(
    path: list[str],
    record: dict[str, Any],
) -> Any:
    """
    Evaluate a field reference.

    Simple paths like ["amount"] resolve directly from the record.
    Nested paths like ["address", "city"] traverse nested objects.
    """
    if not path:
        return None

    value: Any = record
    for segment in path:
        if isinstance(value, dict):
            value = value.get(segment)
        else:
            return None
        if value is None:
            return None

    return value


def _evaluate_duration(expr: InvariantExprSpec) -> timedelta:
    """Evaluate a duration expression to a timedelta."""
    value = expr.duration_value or 0
    unit = expr.duration_unit

    if unit == DurationUnitKind.DAYS:
        return timedelta(days=value)
    elif unit == DurationUnitKind.HOURS:
        return timedelta(hours=value)
    elif unit == DurationUnitKind.MINUTES:
        return timedelta(minutes=value)
    else:
        return timedelta(days=value)


def _evaluate_comparison(
    expr: InvariantExprSpec,
    record: dict[str, Any],
) -> bool:
    """Evaluate a comparison expression."""
    if not expr.comparison_left or not expr.comparison_right or not expr.comparison_op:
        return False

    left = evaluate_invariant_expr(expr.comparison_left, record)
    right = evaluate_invariant_expr(expr.comparison_right, record)
    op = expr.comparison_op

    # Handle None comparisons specially for equality operators
    # This allows expressions like: field != null, field == null
    if left is None or right is None:
        if op == InvariantComparisonKind.EQ:
            return left is None and right is None
        elif op == InvariantComparisonKind.NE:
            return not (left is None and right is None)
        else:
            # For ordered comparisons (>, <, >=, <=), None makes no sense
            return False

    # Normalize values for comparison
    left = _normalize_for_comparison(left)
    right = _normalize_for_comparison(right)

    # Handle date/datetime + timedelta arithmetic
    left, right = _handle_date_arithmetic(left, right)

    try:
        result: bool
        if op == InvariantComparisonKind.EQ:
            result = left == right
        elif op == InvariantComparisonKind.NE:
            result = left != right
        elif op == InvariantComparisonKind.GT:
            result = left > right
        elif op == InvariantComparisonKind.LT:
            result = left < right
        elif op == InvariantComparisonKind.GE:
            result = left >= right
        elif op == InvariantComparisonKind.LE:
            result = left <= right
        else:
            return False
        return bool(result)
    except TypeError:
        # Incompatible types for comparison
        return False


def _normalize_for_comparison(value: Any) -> Any:
    """Normalize a value for comparison."""
    # Convert datetime to date for date comparisons
    # Note: must check datetime before date since datetime is a subclass of date
    if isinstance(value, datetime):
        return value.date()
    # Convert ISO date strings to date objects
    if isinstance(value, str):
        try:
            if "T" in value:
                return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
            else:
                return date.fromisoformat(value)
        except ValueError:
            pass
    # Convert Decimal to float for numeric comparisons
    if isinstance(value, Decimal):
        return float(value)
    return value


def _handle_date_arithmetic(left: Any, right: Any) -> tuple[Any, Any]:
    """Handle date + timedelta arithmetic in comparisons."""
    # If comparing date to timedelta, interpret as date offset from today
    # This handles cases like: due_date > 14 days (meaning due_date > today + 14 days)
    if isinstance(left, date) and isinstance(right, timedelta):
        # "field > 14 days" means "field > today + 14 days"
        right = date.today() + right
    elif isinstance(left, timedelta) and isinstance(right, date):
        # "14 days < field" means "today + 14 days < field"
        left = date.today() + left

    return left, right


def _evaluate_logical(
    expr: InvariantExprSpec,
    record: dict[str, Any],
) -> bool:
    """Evaluate a logical (AND/OR) expression."""
    if not expr.logical_left or not expr.logical_right or not expr.logical_op:
        return False

    left = evaluate_invariant_expr(expr.logical_left, record)
    right = evaluate_invariant_expr(expr.logical_right, record)

    # Coerce to bool
    left_bool = bool(left)
    right_bool = bool(right)

    if expr.logical_op == InvariantLogicalKind.AND:
        return left_bool and right_bool
    elif expr.logical_op == InvariantLogicalKind.OR:
        return left_bool or right_bool
    else:
        return False


def _evaluate_not(
    expr: InvariantExprSpec,
    record: dict[str, Any],
) -> bool:
    """Evaluate a NOT expression."""
    if not expr.not_operand:
        return False

    operand = evaluate_invariant_expr(expr.not_operand, record)
    return not bool(operand)


# =============================================================================
# Invariant Validation
# =============================================================================


def validate_invariant(
    invariant: InvariantSpec,
    record: dict[str, Any],
) -> bool:
    """
    Validate a single invariant against a record.

    Args:
        invariant: The invariant specification
        record: The record data

    Returns:
        True if the invariant holds, False otherwise
    """
    result = evaluate_invariant_expr(invariant.expression, record)
    return bool(result)


def validate_invariants(
    invariants: list[InvariantSpec],
    record: dict[str, Any],
    raise_on_violation: bool = False,
) -> list[InvariantSpec]:
    """
    Validate all invariants against a record.

    Args:
        invariants: List of invariant specifications
        record: The record data
        raise_on_violation: If True, raise InvariantViolationError on first violation

    Returns:
        List of violated invariants (empty if all pass)

    Raises:
        InvariantViolationError: If raise_on_violation is True and an invariant fails
    """
    violations: list[InvariantSpec] = []

    for invariant in invariants:
        if not validate_invariant(invariant, record):
            if raise_on_violation:
                message = invariant.message or "Invariant constraint violated"
                raise InvariantViolationError(message, invariant)
            violations.append(invariant)

    return violations


def check_invariants_for_create(
    invariants: list[InvariantSpec],
    record: dict[str, Any],
) -> None:
    """
    Check invariants before creating a record.

    Args:
        invariants: List of invariant specifications
        record: The record data to be created

    Raises:
        InvariantViolationError: If any invariant is violated
    """
    validate_invariants(invariants, record, raise_on_violation=True)


def check_invariants_for_update(
    invariants: list[InvariantSpec],
    current_record: dict[str, Any],
    updates: dict[str, Any],
) -> None:
    """
    Check invariants before updating a record.

    Args:
        invariants: List of invariant specifications
        current_record: The current record data
        updates: The updates to apply

    Raises:
        InvariantViolationError: If any invariant would be violated after update
    """
    # Merge current record with updates to get the post-update state
    merged_record = {**current_record, **updates}
    validate_invariants(invariants, merged_record, raise_on_violation=True)
