"""
Condition expression evaluator for access control.

Evaluates ConditionExpr from IR AccessSpec at runtime for:
- Workspace region filters (converting to SQL WHERE clauses)
- Permission checks (evaluating against entity records)

The pure evaluation logic lives in dazzle.page.utils.condition_eval so that
the UI package can evaluate visible_condition without importing dazzle.http.
This module re-exports evaluate_condition from there and adds the SQL
filter generation helpers that are only needed in the backend.
"""

from typing import Any

from dazzle.core.condition_eval import (
    _resolve_value,  # noqa: PLC2701
    evaluate_condition,
)

__all__ = [
    "evaluate_condition",
    "condition_to_sql_filter",
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


def _is_field_condition(condition: Any) -> bool:
    """Return True if condition requires record data to evaluate.

    Role checks need only the user's roles — evaluable at the gate without a record.
    Comparisons and grant checks reference entity fields — need record data.
    Logical nodes recurse: if either branch needs record data, the whole
    condition is a field condition.

    Relocated here from ``handlers/list_handlers`` (#1422) so the transport-
    agnostic ``access.gated.gated_list`` can use it without importing back into the
    FastAPI adapter layer. ``list_handlers`` re-imports it to keep the existing
    ``route_generator`` / ``handlers`` re-export chain resolving.
    """
    if condition is None:
        return False
    kind = getattr(condition, "kind", None)
    if kind == "role_check":
        return False
    if kind in ("comparison", "grant_check", "via_check"):
        return True
    if kind == "logical":
        return _is_field_condition(getattr(condition, "logical_left", None)) or _is_field_condition(
            getattr(condition, "logical_right", None)
        )
    return False
