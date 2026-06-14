"""
Invariant evaluator for Dazzle runtime.

This module evaluates entity invariants at runtime during create/update operations.
Invariants are cross-field constraints that must always hold true.
"""

from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

from dazzle.back.runtime._comparison import eval_comparison_op
from dazzle.back.specs.entity import (
    DurationUnitKind,
    InvariantComparisonKind,
    InvariantExprSpec,
    InvariantLogicalKind,
    InvariantSpec,
)


class InvariantViolationError(Exception):
    """Raised when an invariant constraint is violated."""

    def __init__(
        self,
        message: str,
        invariant: InvariantSpec | None = None,
        entity: str | None = None,
    ):
        self.message = message
        self.invariant = invariant
        self.entity = entity
        super().__init__(message)


def render_invariant_expr(expr: Any) -> str:
    """Render an invariant expression back to a readable source-like string.

    e.g. ``amount >= 0``, ``contact != null or company != null``. Used to name
    the violated invariant in actionable 422 errors (#1387) — the structured
    ``InvariantExprSpec`` has no readable ``__str__`` and no raw source is kept.
    """
    if expr is None:
        return ""
    kind = getattr(expr, "kind", None)
    if kind == "literal":
        value = getattr(expr, "value", None)
        if value is None:
            return "null"
        return f'"{value}"' if isinstance(value, str) else str(value)
    if kind == "field_ref":
        return ".".join(getattr(expr, "path", None) or [])
    if kind == "duration":
        unit = getattr(getattr(expr, "duration_unit", None), "value", None) or "days"
        return f"{getattr(expr, 'duration_value', '?')} {unit}"
    if kind == "comparison":
        op = getattr(getattr(expr, "comparison_op", None), "value", None) or "?"
        left = render_invariant_expr(getattr(expr, "comparison_left", None))
        right = render_invariant_expr(getattr(expr, "comparison_right", None))
        return f"{left} {op} {right}"
    if kind == "logical":
        op = getattr(getattr(expr, "logical_op", None), "value", None) or "?"
        left = render_invariant_expr(getattr(expr, "logical_left", None))
        right = render_invariant_expr(getattr(expr, "logical_right", None))
        return f"{left} {op} {right}"
    if kind == "not":
        return f"not {render_invariant_expr(getattr(expr, 'not_operand', None))}"
    return str(expr)


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

    # Handle None comparisons specially.
    # For equality operators: allow explicit null checks (field != null).
    # For ordered comparisons (>, <, >=, <=): null/absent optional fields
    # should not trigger numeric invariants — follow SQL CHECK semantics
    # where NULL yields UNKNOWN which satisfies the constraint (#491).
    if left is None or right is None:
        if op == InvariantComparisonKind.EQ:
            return left is None and right is None
        elif op == InvariantComparisonKind.NE:
            return not (left is None and right is None)
        else:
            return True

    # Normalize values for comparison (date/datetime/Decimal-aware)
    left = _normalize_for_comparison(left)
    right = _normalize_for_comparison(right)

    # Handle date/datetime + timedelta arithmetic
    left, right = _handle_date_arithmetic(left, right)

    try:
        return bool(eval_comparison_op(op.value, left, right))
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
    entity: str | None = None,
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
                raise InvariantViolationError(message, invariant, entity=entity)
            violations.append(invariant)

    return violations


def check_invariants_for_create(
    invariants: list[InvariantSpec],
    record: dict[str, Any],
    entity: str | None = None,
) -> None:
    """
    Check invariants before creating a record.

    Args:
        invariants: List of invariant specifications
        record: The record data to be created
        entity: Entity name, surfaced on the raised error for actionable messages

    Raises:
        InvariantViolationError: If any invariant is violated
    """
    validate_invariants(invariants, record, raise_on_violation=True, entity=entity)


def check_invariants_for_update(
    invariants: list[InvariantSpec],
    current_record: dict[str, Any],
    updates: dict[str, Any],
    entity: str | None = None,
) -> None:
    """
    Check invariants before updating a record.

    Args:
        invariants: List of invariant specifications
        current_record: The current record data
        updates: The updates to apply
        entity: Entity name, surfaced on the raised error for actionable messages

    Raises:
        InvariantViolationError: If any invariant would be violated after update
    """
    # Merge current record with updates to get the post-update state
    merged_record = {**current_record, **updates}
    validate_invariants(invariants, merged_record, raise_on_violation=True, entity=entity)
