"""
Condition expression evaluator for access control.

Evaluates ConditionExpr from IR AccessSpec at runtime for:
- Row-level visibility filtering (converting to SQL WHERE clauses)
- Permission checks (evaluating against entity records)

The pure evaluation logic lives in dazzle_ui.utils.condition_eval so that
the UI package can evaluate visible_condition without importing dazzle_back.
This module re-exports evaluate_condition from there and adds the SQL
filter generation helpers that are only needed in the backend.
"""

from __future__ import annotations

from typing import Any

from dazzle_ui.utils.condition_eval import (
    _resolve_value,  # noqa: PLC2701
    evaluate_condition,
)

__all__ = [
    "evaluate_condition",
    "condition_to_sql_filter",
    "build_visibility_filter",
    "filter_records_by_condition",
]


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

    # Handle role check — evaluate immediately since roles are in context
    if "role_check" in condition and condition["role_check"]:
        role_name = condition["role_check"].get("role_name")
        user_roles = context.get("user_roles", [])
        if role_name and role_name in user_roles:
            return {}  # Role satisfied, no additional SQL filter needed
        return {"_role_denied": True}  # Sentinel that repository interprets as deny-all

    # Handle grant check — generate subquery metadata for repository layer
    if "grant_check" in condition and condition["grant_check"]:
        gc = condition["grant_check"]
        principal_id = context.get("current_user_id")
        if not principal_id:
            return {"_grant_denied": True}
        return {
            "_grant_subquery": {
                "field": gc["scope_field"],
                "relation": gc["relation"],
                "principal_id": principal_id,
            }
        }

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
