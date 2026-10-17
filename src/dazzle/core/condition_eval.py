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

from datetime import UTC, date, datetime
from typing import Any

from dazzle.core.comparison import eval_comparison_op as _eval_comparison_op
from dazzle.core.date_expr_eval import evaluate_date_expr
from dazzle.i18n.display_locale import as_calendar_date

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
    operator = condition.get("operator")
    if operator:
        return _evaluate_logical(operator, condition, record, context)

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


def _evaluate_logical(
    operator: Any,
    condition: dict[str, Any],
    record: dict[str, Any],
    context: dict[str, Any],
) -> bool:
    """``and`` / ``or`` / ``not (...)`` — the last is ``{"operator": "not",
    "left": inner, "right": None}`` (#1180 grammar, evaluated since #1787)."""
    left = evaluate_condition(condition.get("left") or {}, record, context)
    if operator == "not":
        return not left
    right = evaluate_condition(condition.get("right") or {}, record, context)
    if operator == "and":
        return left and right
    if operator == "or":
        return left or right
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


def grant_unexpired(expires_at: Any, now: datetime) -> bool:
    """True when a grant's ``expires_at`` is unset or later than ``now`` (aware UTC).

    Accepts the store's ``datetime`` (a naive value is read as UTC) or an
    ISO-8601 string (a serialised row). An unparseable value fails closed.
    """
    if expires_at is None or expires_at == "":
        return True
    if isinstance(expires_at, str):
        try:
            expires_at = datetime.fromisoformat(expires_at)
        except ValueError:
            return False
    if not isinstance(expires_at, datetime):
        return False
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    return bool(expires_at > now)


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
    now = datetime.now(UTC)

    # The store returns ``expires_at`` as a datetime; comparing it with an ISO
    # string raised TypeError (flense ship AC). ``grant_unexpired`` takes either.
    return any(
        g.get("relation") == relation
        and str(g.get("scope_id", "")) == str(scope_value)
        and grant_unexpired(g.get("expires_at"), now)
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
    record_value = _resolve_left_reference(field, record, context)

    # Resolve the comparison value (handle "current_user" etc.)
    resolved_value = _resolve_value(value, context)
    if isinstance(resolved_value, date):
        # Attention ``due_date < today`` must compare calendar days, not
        # date vs leftover dict / ISO string (TypeError invented on-time).
        record_value = _as_compare_date(record_value)

    # Perform comparison
    return _eval_comparison_op(operator, record_value, resolved_value)


def _resolve_left_reference(field: str, record: dict[str, Any], context: dict[str, Any]) -> Any:
    """Resolve a comparison's left-hand reference.

    ``tenant_config.<key>`` (#1324 FR-4) and ``current_tenant[.attr]`` (#1394)
    are context namespaces, not record fields. A dotted path (#1787) walks the
    record's expanded FK dicts — an unexpanded FK (a bare id) resolves to None
    and fails the comparison (fail closed). A plain ref field read from a detail
    record is an expanded ``{"id": ...}`` dict and compares on its id.
    """
    if field.startswith(_TENANT_CONFIG_PREFIX):
        key = field[len(_TENANT_CONFIG_PREFIX) :]
        tenant_config = context.get("tenant_config") or {}
        return tenant_config.get(key) if isinstance(tenant_config, dict) else None
    if field == "current_tenant" or field.startswith(_CURRENT_TENANT_PREFIX):
        return _resolve_current_tenant(field, context)
    if "." in field:
        return _resolve_dotted_field(record, field)
    value = record.get(field)
    if isinstance(value, dict) and "id" in value:
        return value["id"]
    return value


def _as_compare_date(value: Any) -> date | None:
    """Coerce a record field to a calendar date for ``today`` comparisons."""
    return as_calendar_date(value)


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
        if value.get("date_expr") is not None:
            return evaluate_date_expr(value["date_expr"])
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


# =============================================================================
# DSL text of a ConditionExpr (#1787)
# =============================================================================


def _enum_text(value: Any) -> str:
    return str(value.value if hasattr(value, "value") else value or "")


def _value_text(value: Any) -> str:
    if value is None:
        return "null"
    if getattr(value, "values", None) is not None:
        return "[" + ", ".join(str(v) for v in value.values) + "]"
    if getattr(value, "date_expr", None) is not None:
        return str(value.date_expr)
    literal = getattr(value, "literal", None)
    if literal is None:
        return "null"
    if isinstance(literal, bool):
        return "true" if literal else "false"
    return str(literal)


def condition_to_dsl(condition: Any) -> str:
    """Render a ``ConditionExpr`` back to its DSL text (#1787).

    Used where a refusal or a validation error must name the predicate the
    author wrote (``status = draft and role(agent)``) so it traces back to the
    surface line. Covers the shapes ``parse_condition_expr`` produces; a
    compound child is parenthesised when its operator differs from its parent's.
    """
    if condition is None:
        return ""
    op = _enum_text(getattr(condition, "operator", None))
    if op == "not":
        return f"not ({condition_to_dsl(condition.left)})"
    if op in ("and", "or"):
        parts = []
        for child in (condition.left, condition.right):
            text = condition_to_dsl(child)
            child_op = _enum_text(getattr(child, "operator", None))
            if child_op in ("and", "or") and child_op != op:
                text = f"({text})"
            parts.append(text)
        return f" {op} ".join(parts)
    if getattr(condition, "role_check", None) is not None:
        return f"role({condition.role_check.role_name})"
    if getattr(condition, "grant_check", None) is not None:
        grant = condition.grant_check
        return f'has_grant("{grant.relation}", {grant.scope_field})'
    comparison = getattr(condition, "comparison", None)
    if comparison is not None:
        if comparison.function is not None:
            lhs = f"{comparison.function.name}({comparison.function.argument})"
        else:
            lhs = str(comparison.field or "")
        return f"{lhs} {_enum_text(comparison.operator)} {_value_text(comparison.value)}"
    return ""
