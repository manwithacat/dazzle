"""
Invariant evaluator for Dazzle runtime.

This module evaluates entity invariants at runtime during create/update operations.
Invariants are cross-field constraints that must always hold true.
"""

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

from dazzle.core.date_expr_eval import add_months
from dazzle.http.runtime._comparison import eval_comparison_op
from dazzle.http.specs.entity import (
    DurationUnitKind,
    InvariantComparisonKind,
    InvariantExprSpec,
    InvariantLogicalKind,
    InvariantSpec,
)
from dazzle.i18n.display_locale import calendar_today as _calendar_today
from dazzle.render.filters import clerk_form_error_field_label, clerk_stage_label

_GENERIC_INVARIANT_SPEECH = "Invariant constraint violated"


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
        return ".".join(_authored_path(expr))
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
    if kind == "in":
        return _render_in(expr)
    return str(expr)


def _render_in(expr: Any) -> str:
    op = "not in" if getattr(expr, "in_negated", False) else "in"
    items = ", ".join(render_invariant_expr(i) for i in getattr(expr, "in_items", None) or [])
    return f"{render_invariant_expr(getattr(expr, 'in_value', None))} {op} [{items}]"


def _clerk_invariant_literal(expr: Any) -> str:
    value = getattr(expr, "value", None)
    if value is None:
        return "empty"
    if isinstance(value, (bool, str)):
        return clerk_stage_label(value)
    return str(value)


def _authored_path(expr: Any) -> list[str]:
    """The field path as the author wrote it — a money ref names the field, not ``_minor``."""
    path = list(getattr(expr, "path", None) or [])
    if getattr(expr, "minor_scale", None) is not None and path:
        path[-1] = path[-1].removesuffix("_minor")
    return path


def _clerk_invariant_field_ref(expr: Any) -> str:
    parts = [clerk_form_error_field_label(segment) for segment in _authored_path(expr)]
    return " ".join(p for p in parts if p)


def _clerk_invariant_duration(expr: Any) -> str:
    unit = getattr(getattr(expr, "duration_unit", None), "value", None) or "days"
    return f"{getattr(expr, 'duration_value', '?')} {clerk_stage_label(unit)}"


def _clerk_invariant_binary(expr: Any, prefix: str) -> str:
    op = getattr(getattr(expr, f"{prefix}_op", None), "value", None) or "?"
    left = clerk_invariant_expr(getattr(expr, f"{prefix}_left", None))
    right = clerk_invariant_expr(getattr(expr, f"{prefix}_right", None))
    return f"{left} {op} {right}".strip()


def _clerk_invariant_not(expr: Any) -> str:
    inner = clerk_invariant_expr(getattr(expr, "not_operand", None))
    return f"not {inner}".strip() if inner else "not"


def _clerk_invariant_in(expr: Any) -> str:
    op = "not in" if getattr(expr, "in_negated", False) else "in"
    items = ", ".join(clerk_invariant_expr(i) for i in getattr(expr, "in_items", None) or [])
    return f"{clerk_invariant_expr(getattr(expr, 'in_value', None))} {op} {items}".strip()


_CLERK_INVARIANT_KIND = {
    "literal": _clerk_invariant_literal,
    "field_ref": _clerk_invariant_field_ref,
    "duration": _clerk_invariant_duration,
    "comparison": lambda expr: _clerk_invariant_binary(expr, "comparison"),
    "logical": lambda expr: _clerk_invariant_binary(expr, "logical"),
    "not": _clerk_invariant_not,
    "in": _clerk_invariant_in,
}


def clerk_invariant_expr(expr: Any) -> str:
    """Schema invariant expression → clerk 422 speech (oral #202).

    ``duration_minutes > 0`` dumped as itself (or the generic
    ``Invariant constraint violated``) while the log-session form
    already says ``Duration (min)``. Leftover junk stays put. JSON
    ``invariant`` / ``entity`` stay identifiers.
    """
    if expr is None:
        return ""
    kind = getattr(expr, "kind", None)
    if not isinstance(kind, str):
        return str(expr)
    handler = _CLERK_INVARIANT_KIND.get(kind)
    return handler(expr) if handler is not None else str(expr)


def clerk_invariant_speech(invariant: Any = None, message: str | None = None) -> str:
    """Clerk-facing invariant 422 body (oral #202).

    Authored ``message`` wins (including leftover junk). Empty /
    generic message synthesizes field labels from the expression.
    """
    authored = (message or getattr(invariant, "message", None) or "").strip()
    if authored and authored != _GENERIC_INVARIANT_SPEECH:
        return authored
    rendered = clerk_invariant_expr(
        getattr(invariant, "expression", None) if invariant is not None else None
    )
    return rendered or _GENERIC_INVARIANT_SPEECH


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
        value = _evaluate_field_ref(expr.path or [], record)
        if expr.minor_scale is not None and value is not None:
            # Money field (#1823): the _minor column, read in major units.
            return Decimal(value).scaleb(-expr.minor_scale)
        return value

    elif expr.kind == "duration":
        return _evaluate_duration(expr)

    elif expr.kind == "comparison":
        return _evaluate_comparison(expr, record)

    elif expr.kind == "logical":
        return _evaluate_logical(expr, record)

    elif expr.kind == "not":
        return _evaluate_not(expr, record)

    elif expr.kind == "in":
        return _evaluate_in(expr, record)

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


@dataclass(frozen=True)
class DurationOffset:
    """An invariant duration (``14 days``, ``2 weeks``, ``3 months``).

    Not a ``timedelta``: a month or a year has no fixed length, so the offset is
    applied to an anchor date with calendar arithmetic (#1823 — weeks, months and
    years used to fall through to days, so ``2 weeks`` meant two days).
    """

    value: int
    unit: DurationUnitKind

    def apply(self, anchor: date) -> date:
        """``anchor`` moved by this offset (months/years clamp to the month's end)."""
        if self.unit == DurationUnitKind.MONTHS:
            return add_months(anchor, self.value)
        if self.unit == DurationUnitKind.YEARS:
            return add_months(anchor, 12 * self.value)
        return anchor + _FIXED_UNITS[self.unit] * self.value


_FIXED_UNITS = {
    DurationUnitKind.MINUTES: timedelta(minutes=1),
    DurationUnitKind.HOURS: timedelta(hours=1),
    DurationUnitKind.DAYS: timedelta(days=1),
    DurationUnitKind.WEEKS: timedelta(weeks=1),
}


def _evaluate_duration(expr: InvariantExprSpec) -> DurationOffset:
    """Evaluate a duration expression to an offset applied to today when compared."""
    return DurationOffset(expr.duration_value or 0, expr.duration_unit or DurationUnitKind.DAYS)


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

    # A duration compared with a date is anchored on today
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
    """Resolve a duration compared with a date to ``today + duration``.

    ``due_date > 14 days`` means ``due_date > today + 14 days`` (tenant-TZ today);
    ``3 months < due_date`` likewise on the left.
    """
    if isinstance(left, date) and isinstance(right, DurationOffset):
        right = right.apply(_calendar_today())
    elif isinstance(left, DurationOffset) and isinstance(right, date):
        left = left.apply(_calendar_today())
    return left, right


def _evaluate_in(expr: InvariantExprSpec, record: dict[str, Any]) -> bool:
    """``value in [literals]`` / ``not in`` (#1823).

    Plain membership after the same normalisation comparisons use, so a money
    field (major-unit Decimal) matches ``100.50`` and a null value is in the list
    only when ``null`` is listed.
    """
    value = evaluate_invariant_expr(expr.in_value, record) if expr.in_value else None
    items = [evaluate_invariant_expr(i, record) for i in expr.in_items or []]
    member = _normalize_for_comparison(value) in [_normalize_for_comparison(i) for i in items]
    return not member if expr.in_negated else member


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
                message = clerk_invariant_speech(invariant)
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
