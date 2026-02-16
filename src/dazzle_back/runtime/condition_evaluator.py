"""
Condition expression evaluator for access control.

Evaluates ConditionExpr from IR AccessSpec at runtime for:
- Row-level visibility filtering (converting to SQL WHERE clauses)
- Permission checks (evaluating against entity records)
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

# =============================================================================
# Condition Expression Evaluator
# =============================================================================


def evaluate_condition(
    condition: dict[str, Any],
    record: dict[str, Any],
    context: dict[str, Any],
) -> bool:
    """
    Evaluate a ConditionExpr against a record and context.

    Args:
        condition: Serialized ConditionExpr dict
        record: Entity record data
        context: Runtime context (current_user, etc.)

    Returns:
        True if condition is satisfied
    """
    # Handle compound conditions (AND/OR)
    if "operator" in condition and condition["operator"]:
        left_result = evaluate_condition(condition.get("left", {}), record, context)
        right_result = evaluate_condition(condition.get("right", {}), record, context)

        if condition["operator"] == "and":
            return left_result and right_result
        elif condition["operator"] == "or":
            return left_result or right_result

    # Handle simple comparison
    if "comparison" in condition and condition["comparison"]:
        return _evaluate_comparison(condition["comparison"], record, context)

    # Empty condition = always true
    return True


def _evaluate_comparison(
    comparison: dict[str, Any],
    record: dict[str, Any],
    context: dict[str, Any],
) -> bool:
    """
    Evaluate a single comparison.

    Args:
        comparison: Serialized Comparison dict
        record: Entity record data
        context: Runtime context

    Returns:
        True if comparison is satisfied
    """
    field = comparison.get("field")
    operator = comparison.get("operator")
    value = comparison.get("value")

    if not field or not operator:
        return True

    # Get the actual value from the record
    record_value = record.get(field)

    # Resolve the comparison value (handle "current_user" etc.)
    resolved_value = _resolve_value(value, context)

    # Perform comparison
    return _compare(record_value, operator, resolved_value)


def _resolve_value(value: Any, context: dict[str, Any]) -> Any:
    """
    Resolve a value, handling special identifiers like current_user.

    Args:
        value: Raw value from condition (could be identifier or literal)
        context: Runtime context

    Returns:
        Resolved value
    """
    if isinstance(value, dict):
        # Handle IR ConditionValue format: {"literal": <value>, "values": null}
        if "literal" in value:
            literal_val = value.get("literal")
            # Check if the literal is a special identifier
            if literal_val == "current_user":
                return context.get("current_user_id")
            # Return the literal value as-is
            return literal_val

        # Handle list values (for 'in' operator)
        if "values" in value and value.get("values"):
            return value.get("values")

        # Handle identifier values (e.g., {"kind": "identifier", "value": "current_user"})
        if value.get("kind") == "identifier":
            ident = value.get("value", "")
            if ident == "current_user":
                return context.get("current_user_id")
            # Could add more special identifiers here
            return None

        # Handle literal values (alternative format)
        if value.get("kind") == "literal":
            return value.get("value")

    # Simple literal value
    return value


def _compare(record_value: Any, operator: str, resolved_value: Any) -> bool:
    """
    Perform a comparison operation.

    Args:
        record_value: Value from the record
        operator: Comparison operator
        resolved_value: Resolved comparison target

    Returns:
        True if comparison passes
    """
    # Normalize UUIDs for comparison
    if isinstance(record_value, UUID):
        record_value = str(record_value)
    if isinstance(resolved_value, UUID):
        resolved_value = str(resolved_value)

    # Handle null comparisons
    if resolved_value is None:
        if operator in ("eq", "=", "=="):
            return record_value is None
        if operator in ("ne", "!=", "<>"):
            return record_value is not None
        return False

    if record_value is None:
        if operator in ("eq", "=", "=="):
            return resolved_value is None
        if operator in ("ne", "!=", "<>"):
            return resolved_value is not None
        return False

    # Handle boolean comparisons (SQLite stores bools as 0/1)
    if isinstance(resolved_value, bool):
        # Convert record value to bool for comparison
        if isinstance(record_value, int | float):
            record_value = bool(record_value)
        elif isinstance(record_value, str):
            record_value = record_value.lower() in ("true", "1", "yes")
    elif isinstance(record_value, bool):
        # Convert resolved value to bool for comparison
        if isinstance(resolved_value, int | float):
            resolved_value = bool(resolved_value)
        elif isinstance(resolved_value, str):
            resolved_value = resolved_value.lower() in ("true", "1", "yes")

    # Perform comparison
    if operator in ("eq", "=", "=="):
        # For boolean comparison after normalization
        if isinstance(record_value, bool) and isinstance(resolved_value, bool):
            return record_value == resolved_value
        return str(record_value) == str(resolved_value)
    if operator in ("ne", "!=", "<>"):
        if isinstance(record_value, bool) and isinstance(resolved_value, bool):
            return record_value != resolved_value
        return str(record_value) != str(resolved_value)
    if operator in ("gt", ">"):
        return record_value > resolved_value  # type: ignore[no-any-return]
    if operator in ("ge", ">="):
        return record_value >= resolved_value  # type: ignore[no-any-return]
    if operator in ("lt", "<"):
        return record_value < resolved_value  # type: ignore[no-any-return]
    if operator in ("le", "<="):
        return record_value <= resolved_value  # type: ignore[no-any-return]
    if operator == "in":
        if isinstance(resolved_value, list | tuple):
            return record_value in resolved_value
        return False
    if operator == "not_in":
        if isinstance(resolved_value, list | tuple):
            return record_value not in resolved_value
        return True

    return False


# =============================================================================
# SQL WHERE Clause Generation
# =============================================================================


def condition_to_sql_filter(
    condition: dict[str, Any],
    context: dict[str, Any],
) -> dict[str, Any]:
    """
    Convert a ConditionExpr to SQL-compatible filter dictionary.

    This generates filters compatible with the repository's filter syntax.
    Note: Complex OR conditions may need to be evaluated post-fetch.

    Args:
        condition: Serialized ConditionExpr dict
        context: Runtime context (current_user, etc.)

    Returns:
        Dictionary of field filters for repository
    """
    filters: dict[str, Any] = {}

    # For simple AND conditions, we can build filters
    if "comparison" in condition and condition["comparison"]:
        comp = condition["comparison"]
        field = comp.get("field")
        operator = comp.get("operator")
        value = comp.get("value")

        if field and operator:
            resolved = _resolve_value(value, context)

            # Map operator to repository filter syntax
            if operator in ("eq", "=", "=="):
                filters[field] = resolved
            elif operator in ("ne", "!=", "<>"):
                filters[f"{field}__ne"] = resolved
            elif operator in ("gt", ">"):
                filters[f"{field}__gt"] = resolved
            elif operator in ("ge", ">="):
                filters[f"{field}__gte"] = resolved
            elif operator in ("lt", "<"):
                filters[f"{field}__lt"] = resolved
            elif operator in ("le", "<="):
                filters[f"{field}__lte"] = resolved
            elif operator == "in":
                filters[f"{field}__in"] = resolved

    # For AND compound conditions, merge filters
    if "operator" in condition and condition["operator"] == "and":
        left_filters = condition_to_sql_filter(condition.get("left", {}), context)
        right_filters = condition_to_sql_filter(condition.get("right", {}), context)
        filters.update(left_filters)
        filters.update(right_filters)

    # OR conditions are more complex - we return empty filters
    # and rely on post-fetch filtering
    # In a real implementation, we'd generate SQL OR clauses

    return filters


def build_visibility_filter(
    access_spec: dict[str, Any] | None,
    is_authenticated: bool,
    user_id: str | None,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    """
    Build visibility filter from access spec.

    Args:
        access_spec: Entity access spec from metadata
        is_authenticated: Whether user is authenticated
        user_id: Current user ID if authenticated

    Returns:
        Tuple of (sql_filters, post_filter_condition)
        - sql_filters: Filters to apply in SQL query
        - post_filter_condition: Condition for post-fetch filtering (for OR)
    """
    if not access_spec:
        return {}, None

    visibility_rules = access_spec.get("visibility", [])
    context = {"current_user_id": user_id}

    # Find the appropriate visibility rule
    target_context = "authenticated" if is_authenticated else "anonymous"
    condition = None

    for rule in visibility_rules:
        if rule.get("context") == target_context:
            condition = rule.get("condition")
            break

    if not condition:
        # No visibility rule = allow all
        return {}, None

    # Check if condition has OR operators (needs post-filtering)
    has_or = _condition_has_or(condition)

    if has_or:
        # Complex condition - need post-fetch filtering
        return {}, condition
    else:
        # Simple AND condition - can convert to SQL filters
        return condition_to_sql_filter(condition, context), None


def _condition_has_or(condition: dict[str, Any] | None) -> bool:
    """Check if condition contains OR operators."""
    if not condition:
        return False
    if "operator" in condition:
        if condition["operator"] == "or":
            return True
        # Check children - use `or {}` to handle explicit None values
        left = condition.get("left") or {}
        right = condition.get("right") or {}
        if _condition_has_or(left):
            return True
        if _condition_has_or(right):
            return True
    return False


def filter_records_by_condition(
    records: list[dict[str, Any]],
    condition: dict[str, Any],
    context: dict[str, Any],
) -> list[dict[str, Any]]:
    """
    Filter records by a condition expression.

    Used for post-fetch filtering when SQL can't handle the full condition.

    Args:
        records: List of entity records
        condition: Condition expression
        context: Runtime context

    Returns:
        Filtered list of records
    """
    return [r for r in records if evaluate_condition(condition, r, context)]
