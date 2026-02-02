"""
Computed field evaluator for DNR runtime.

This module evaluates computed expressions at runtime.
Computed fields are derived values calculated from other fields
using aggregate functions and arithmetic operations.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from dazzle_back.specs.entity import (
    AggregateFunctionKind,
    ArithmeticOperatorKind,
    ComputedExprSpec,
    ComputedFieldSpec,
)

if TYPE_CHECKING:
    pass


# =============================================================================
# Expression Evaluation
# =============================================================================


def evaluate_expression(
    expr: ComputedExprSpec,
    record: dict[str, Any],
    related_data: dict[str, list[dict[str, Any]]] | None = None,
) -> int | float | Decimal | None:
    """
    Evaluate a computed expression for a single record.

    Args:
        expr: The computed expression specification
        record: The record data (as a dict)
        related_data: Optional dict of relation_name -> list of related records

    Returns:
        The computed value (int, float, or Decimal) or None if computation fails
    """
    related_data = related_data or {}

    if expr.kind == "literal":
        return expr.value

    elif expr.kind == "field_ref":
        return _evaluate_field_ref(expr.path or [], record, related_data)

    elif expr.kind == "aggregate":
        return _evaluate_aggregate(expr, record, related_data)

    elif expr.kind == "arithmetic":
        return _evaluate_arithmetic(expr, record, related_data)

    else:
        return None


def _evaluate_field_ref(
    path: list[str],
    record: dict[str, Any],
    related_data: dict[str, list[dict[str, Any]]],
) -> int | float | Decimal | None:
    """
    Evaluate a field reference.

    Simple paths like ["amount"] resolve directly from the record.
    Paths like ["line_items", "amount"] are used for aggregates.
    """
    if not path:
        return None

    if len(path) == 1:
        # Simple field reference
        value = record.get(path[0])
        if value is None:
            return None
        # Convert to numeric if possible
        if isinstance(value, int | float | Decimal):
            return value
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    # Multi-segment paths are used for aggregate fields
    # The aggregate evaluator handles this
    return None


def _evaluate_aggregate(
    expr: ComputedExprSpec,
    record: dict[str, Any],
    related_data: dict[str, list[dict[str, Any]]],
) -> int | float | Decimal | None:
    """
    Evaluate an aggregate function.

    Supports: count, sum, avg, min, max, days_until, days_since
    """
    if not expr.field or not expr.field.path or not expr.function:
        return None

    func = expr.function
    path = expr.field.path

    # Date functions operate on single fields
    if func in (AggregateFunctionKind.DAYS_UNTIL, AggregateFunctionKind.DAYS_SINCE):
        return _evaluate_date_function(func, path, record)

    # Collection aggregates operate on related data
    if len(path) == 1:
        # Aggregate on own field (e.g., count(items) where items is a relation)
        relation_name = path[0]
        items = related_data.get(relation_name, [])
        return _aggregate_values(func, items, None)
    else:
        # Aggregate on related field (e.g., sum(line_items.amount))
        relation_name = path[0]
        field_name = path[-1]
        items = related_data.get(relation_name, [])
        return _aggregate_values(func, items, field_name)


def _evaluate_date_function(
    func: AggregateFunctionKind,
    path: list[str],
    record: dict[str, Any],
) -> int | None:
    """Evaluate days_until or days_since functions."""
    if len(path) != 1:
        return None

    field_name = path[0]
    date_value = record.get(field_name)

    if date_value is None:
        return None

    # Convert to date object
    # Note: must check datetime before date since datetime is a subclass of date
    target_date: date | None = None
    if isinstance(date_value, datetime):
        target_date = date_value.date()
    elif isinstance(date_value, date):
        target_date = date_value
    elif isinstance(date_value, str):
        try:
            # Try ISO format
            if "T" in date_value:
                target_date = datetime.fromisoformat(date_value.replace("Z", "+00:00")).date()
            else:
                target_date = date.fromisoformat(date_value)
        except ValueError:
            return None
    else:
        return None

    today = date.today()

    if func == AggregateFunctionKind.DAYS_UNTIL:
        return (target_date - today).days
    else:  # DAYS_SINCE
        return (today - target_date).days


def _aggregate_values(
    func: AggregateFunctionKind,
    items: list[dict[str, Any]],
    field_name: str | None,
) -> int | float | Decimal | None:
    """Apply aggregate function to a list of items."""
    if func == AggregateFunctionKind.COUNT:
        return len(items)

    if not items:
        return None if func not in (AggregateFunctionKind.COUNT,) else 0

    if field_name is None:
        return None

    # Extract numeric values
    values: list[float | Decimal] = []
    for item in items:
        val = item.get(field_name)
        if val is not None:
            if isinstance(val, int | float | Decimal):
                values.append(float(val) if isinstance(val, Decimal) else val)
            else:
                try:
                    values.append(float(val))
                except (TypeError, ValueError):
                    pass

    if not values:
        return None

    if func == AggregateFunctionKind.SUM:
        return sum(values)
    elif func == AggregateFunctionKind.AVG:
        return sum(values) / len(values)
    elif func == AggregateFunctionKind.MIN:
        return min(values)
    elif func == AggregateFunctionKind.MAX:
        return max(values)
    else:
        return None


def _evaluate_arithmetic(
    expr: ComputedExprSpec,
    record: dict[str, Any],
    related_data: dict[str, list[dict[str, Any]]],
) -> int | float | Decimal | None:
    """Evaluate an arithmetic expression."""
    if not expr.left or not expr.right or not expr.operator:
        return None

    left = evaluate_expression(expr.left, record, related_data)
    right = evaluate_expression(expr.right, record, related_data)

    if left is None or right is None:
        return None

    # Convert to float for computation
    left_val = float(left)
    right_val = float(right)

    if expr.operator == ArithmeticOperatorKind.ADD:
        return left_val + right_val
    elif expr.operator == ArithmeticOperatorKind.SUBTRACT:
        return left_val - right_val
    elif expr.operator == ArithmeticOperatorKind.MULTIPLY:
        return left_val * right_val
    elif expr.operator == ArithmeticOperatorKind.DIVIDE:
        if right_val == 0:
            return None
        return left_val / right_val
    else:
        return None


# =============================================================================
# Computed Field Evaluation
# =============================================================================


def evaluate_computed_fields(
    record: dict[str, Any],
    computed_fields: list[ComputedFieldSpec],
    related_data: dict[str, list[dict[str, Any]]] | None = None,
) -> dict[str, Any]:
    """
    Evaluate all computed fields for a record.

    Args:
        record: The record data (as a dict)
        computed_fields: List of computed field specifications
        related_data: Optional dict of relation_name -> list of related records

    Returns:
        Dict of computed field values keyed by field name
    """
    result: dict[str, Any] = {}

    for cf in computed_fields:
        value = evaluate_expression(cf.expression, record, related_data)
        result[cf.name] = value

    return result


def enrich_record_with_computed_fields(
    record: dict[str, Any],
    computed_fields: list[ComputedFieldSpec],
    related_data: dict[str, list[dict[str, Any]]] | None = None,
) -> dict[str, Any]:
    """
    Add computed field values to a record.

    Args:
        record: The record data (as a dict)
        computed_fields: List of computed field specifications
        related_data: Optional dict of relation_name -> list of related records

    Returns:
        Record dict with computed fields added
    """
    computed_values = evaluate_computed_fields(record, computed_fields, related_data)
    return {**record, **computed_values}


def enrich_records_with_computed_fields(
    records: list[dict[str, Any]],
    computed_fields: list[ComputedFieldSpec],
    related_data_map: dict[str, dict[str, list[dict[str, Any]]]] | None = None,
) -> list[dict[str, Any]]:
    """
    Add computed field values to multiple records.

    Args:
        records: List of record dicts
        computed_fields: List of computed field specifications
        related_data_map: Optional dict of record_id -> relation_name -> related records

    Returns:
        List of records with computed fields added
    """
    if not computed_fields:
        return records

    result = []
    for record in records:
        record_id = str(record.get("id", ""))
        related_data = (related_data_map or {}).get(record_id, {})
        enriched = enrich_record_with_computed_fields(record, computed_fields, related_data)
        result.append(enriched)

    return result
