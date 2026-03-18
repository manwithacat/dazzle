"""
Shared comparison utilities for runtime evaluators.

Provides common value normalization and operator dispatch used by
condition_evaluator, access_evaluator, and invariant_evaluator.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID


def normalize_for_comparison(value: Any) -> str:
    """
    Normalize a value to a string for comparison.

    Handles UUID, bool, and None to produce consistent string representations
    suitable for string-based equality and membership tests.

    Args:
        value: Any value to normalize

    Returns:
        String representation for comparison
    """
    if value is None:
        return "None"
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, bool):
        return str(value).lower()
    return str(value)


def eval_comparison_op(
    op: str,
    record_val: Any,
    resolved_val: Any,
    *,
    value_list: list[Any] | None = None,
) -> bool:
    """
    Evaluate a comparison operation between two values.

    Handles the full operator set shared across runtime evaluators:
    - UUID normalization (UUID → str)
    - None guards (early returns for null comparisons)
    - Bool coercion (SQLite stores bools as 0/1 integers)
    - Operator dispatch: eq, ne, gt, lt, ge, le, in, not_in

    Operator aliases accepted:
    - eq: "eq", "=", "=="
    - ne: "ne", "!=", "<>"
    - gt: "gt", ">"
    - ge: "ge", ">="
    - lt: "lt", "<"
    - le: "le", "<="
    - in: "in"
    - not_in: "not_in", "not in"

    Args:
        op: Comparison operator string (see aliases above)
        record_val: Value from the record (left-hand side)
        resolved_val: Resolved comparison target (right-hand side)
        value_list: Optional explicit list for ``in``/``not_in`` operators.
            When provided, takes precedence over ``resolved_val`` for membership
            tests.

    Returns:
        True if the comparison passes, False otherwise
    """
    # Normalize UUIDs to strings for comparison
    if isinstance(record_val, UUID):
        record_val = str(record_val)
    if isinstance(resolved_val, UUID):
        resolved_val = str(resolved_val)

    # Handle null comparisons — return early before any coercion
    if resolved_val is None:
        if op in ("eq", "=", "=="):
            return record_val is None
        if op in ("ne", "!=", "<>"):
            return record_val is not None
        return False

    if record_val is None:
        if op in ("eq", "=", "=="):
            return resolved_val is None
        if op in ("ne", "!=", "<>"):
            return resolved_val is not None
        return False

    # Bool coercion — SQLite stores bools as 0/1 integers
    if isinstance(resolved_val, bool):
        # Coerce record side to bool for comparison
        if isinstance(record_val, int | float):
            record_val = bool(record_val)
        elif isinstance(record_val, str):
            record_val = record_val.lower() in ("true", "1", "yes")
    elif isinstance(record_val, bool):
        # Coerce resolved side to bool for comparison
        if isinstance(resolved_val, int | float):
            resolved_val = bool(resolved_val)
        elif isinstance(resolved_val, str):
            resolved_val = resolved_val.lower() in ("true", "1", "yes")

    # Operator dispatch
    if op in ("eq", "=", "=="):
        if isinstance(record_val, bool) and isinstance(resolved_val, bool):
            return record_val == resolved_val
        return str(record_val) == str(resolved_val)

    if op in ("ne", "!=", "<>"):
        if isinstance(record_val, bool) and isinstance(resolved_val, bool):
            return record_val != resolved_val
        return str(record_val) != str(resolved_val)

    if op in ("gt", ">"):
        return record_val > resolved_val  # type: ignore[no-any-return]

    if op in ("ge", ">="):
        return record_val >= resolved_val  # type: ignore[no-any-return]

    if op in ("lt", "<"):
        return record_val < resolved_val  # type: ignore[no-any-return]

    if op in ("le", "<="):
        return record_val <= resolved_val  # type: ignore[no-any-return]

    if op == "in":
        items = value_list if value_list is not None else resolved_val
        if isinstance(items, list | tuple):
            return record_val in items
        return False

    if op in ("not_in", "not in"):
        items = value_list if value_list is not None else resolved_val
        if isinstance(items, list | tuple):
            return record_val not in items
        return True

    return False
