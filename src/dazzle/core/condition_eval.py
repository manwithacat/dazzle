"""
Condition expression evaluator for UI-side access control.

Evaluates ConditionExpr from IR AccessSpec at runtime for:
- Role-based field visibility (visible_condition on fields and tabs)
- Grant-based visibility checks

This is the pure evaluation subset of condition_evaluator — it contains
only the runtime evaluation logic and none of the SQL filter generation.
dazzle.http.runtime.condition_evaluator re-exports evaluate_condition from
here so both packages share one implementation.
"""

from datetime import UTC, datetime
from typing import Any

from dazzle.core.comparison import eval_comparison_op as _eval_comparison_op

# =============================================================================
# Condition Expression Evaluator
# =============================================================================

# #1324 FR-4: reference prefix for the per-tenant-config namespace. A
# condition field of the form ``tenant_config.<key>`` resolves from
# ``context["tenant_config"]`` rather than the entity record.
_TENANT_CONFIG_PREFIX = "tenant_config."

# #1394: render-time reference to the host-resolved tenant. `current_tenant`
# binds the tenant id; `current_tenant.<attr>` reads id/slug/kind/name off the
# `current_tenant` context dict (populated from `request.state.tenant`).
_CURRENT_TENANT_PREFIX = "current_tenant."
_CURRENT_TENANT_ATTRS = frozenset({"id", "slug", "kind", "name"})


def _resolve_current_tenant(ref: str, context: dict[str, Any]) -> Any:
    """Resolve ``current_tenant`` / ``current_tenant.<attr>`` from render context.

    Returns the tenant id for the bare reference, the named attribute for a
    dotted reference (only id/slug/kind/name are valid), or ``None`` when no
    host tenant is in context (apex / non-tenant request) — so a gate referencing
    it simply hides rather than erroring.
    """
    tenant = context.get("current_tenant")
    if not isinstance(tenant, dict):
        return None
    # Bare `current_tenant` and `current_tenant.id` both read the id from the
    # SAME dict (single source of truth — no separate `current_tenant_id` key to
    # drift out of sync). Dotted refs are limited to the id/slug/kind/name allowlist.
    attr = "id" if ref == "current_tenant" else ref[len(_CURRENT_TENANT_PREFIX) :]
    if attr not in _CURRENT_TENANT_ATTRS:
        return None
    return tenant.get(attr)


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
        context: Runtime context (current_user, user_roles, etc.)

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

    # Handle role check
    if "role_check" in condition and condition["role_check"] is not None:
        return _evaluate_role_check(condition["role_check"], context)

    # Handle grant check
    if "grant_check" in condition and condition["grant_check"]:
        return _evaluate_grant_check(condition["grant_check"], record, context)

    # Handle simple comparison
    if "comparison" in condition and condition["comparison"]:
        return _evaluate_comparison(condition["comparison"], record, context)

    # Empty condition = always true
    return True


def _evaluate_role_check(
    role_check: dict[str, Any],
    context: dict[str, Any],
) -> bool:
    role_name = role_check.get("role_name")
    if not role_name:
        return False
    user_roles = context.get("user_roles", [])
    return role_name in user_roles


def _evaluate_grant_check(
    grant_check: dict[str, Any],
    record: dict[str, Any],
    context: dict[str, Any],
) -> bool:
    """
    Evaluate a grant check against pre-fetched active grants in context.

    Args:
        grant_check: Serialized GrantCheck dict with 'relation' and 'scope_field'
        record: Entity record data
        context: Runtime context containing 'active_grants' list

    Returns:
        True if user has an active, non-expired grant matching the check
    """
    relation = grant_check.get("relation")
    scope_field = grant_check.get("scope_field")
    if not relation or not scope_field:
        return False

    scope_value = record.get(scope_field)
    if not scope_value:
        return False

    active_grants = context.get("active_grants", [])
    now = datetime.now(UTC).isoformat()

    return any(
        g.get("relation") == relation
        and str(g.get("scope_id", "")) == str(scope_value)
        and (g.get("expires_at") is None or g.get("expires_at", "") > now)
        for g in active_grants
    )


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

    # Resolve the left-hand reference. ``tenant_config.<key>`` (#1324 FR-4)
    # is a context namespace, not a record field: it resolves from
    # ``context["tenant_config"]`` (per-tenant config exposed at render time),
    # NOT from the entity record. Everything else resolves from the record as
    # before, so roles/grants/plain-field comparisons are unchanged.
    if field.startswith(_TENANT_CONFIG_PREFIX):
        key = field[len(_TENANT_CONFIG_PREFIX) :]
        tenant_config = context.get("tenant_config") or {}
        record_value = tenant_config.get(key) if isinstance(tenant_config, dict) else None
    elif field == "current_tenant" or field.startswith(_CURRENT_TENANT_PREFIX):
        # #1394: `current_tenant` / `current_tenant.<attr>` is a context namespace
        # (the host-resolved tenant), not a record field. Drives display gates like
        # `visible_when: current_tenant.kind == trust`.
        record_value = _resolve_current_tenant(field, context)
    else:
        # Get the actual value from the record
        record_value = record.get(field)

    # Resolve the comparison value (handle "current_user" etc.)
    resolved_value = _resolve_value(value, context)

    # Perform comparison
    return _eval_comparison_op(operator, record_value, resolved_value)


def _resolve_dotted_field(entity: dict[str, Any], field_path: str) -> Any:
    """Resolve a dotted field path from an entity dict."""
    parts = field_path.split(".")
    current: Any = entity
    for part in parts:
        if isinstance(current, dict):
            current = current.get(part)
        else:
            return None
    # Ref fields may be stored as {"id": "...", "name": "..."} — return the id
    if isinstance(current, dict) and "id" in current:
        return current["id"]
    return current


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
            if literal_val == "current_context":
                return context.get("current_context")
            # Handle current_user.<field> dot-notation (e.g. current_user.department)
            if isinstance(literal_val, str) and literal_val.startswith("current_user."):
                field_path = literal_val[len("current_user.") :]
                user_entity = context.get("current_user_entity")
                if user_entity and isinstance(user_entity, dict):
                    return _resolve_dotted_field(user_entity, field_path)
                return None
            # #1394: current_tenant / current_tenant.<attr> on the value side
            # (e.g. `trust == current_tenant.kind`).
            if isinstance(literal_val, str) and (
                literal_val == "current_tenant" or literal_val.startswith(_CURRENT_TENANT_PREFIX)
            ):
                return _resolve_current_tenant(literal_val, context)
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
            if ident == "current_context":
                return context.get("current_context")
            if isinstance(ident, str) and ident.startswith("current_user."):
                field_path = ident[len("current_user.") :]
                user_entity = context.get("current_user_entity")
                if user_entity and isinstance(user_entity, dict):
                    return _resolve_dotted_field(user_entity, field_path)
                return None
            return None

        # Handle literal values (alternative format)
        if value.get("kind") == "literal":
            return value.get("value")

    # Simple literal value
    return value
