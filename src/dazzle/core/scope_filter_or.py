"""Lower workspace-region OR filters to SQL-friendly shapes (#1630).

``status = held or status = confirmed`` becomes ``status__in``. Mixed-field
OR cannot be expressed in the flat filter dict and must fail closed.
"""

from __future__ import annotations

from typing import Any


def equality_leaf(condition: Any) -> tuple[str, Any] | None:
    """Return (field, literal) for a simple equality ConditionExpr leaf."""
    if condition is None:
        return None
    if getattr(condition, "operator", None) is not None:
        return None
    comp = getattr(condition, "comparison", None)
    if comp is None:
        return None
    field = getattr(comp, "field", None)
    if not field:
        return None
    op = getattr(comp, "operator", None)
    op_val = getattr(op, "value", None) or (str(op) if op else "=")
    if op_val not in ("=", "eq", "equals"):
        return None
    cond_value = getattr(comp, "value", None)
    if cond_value is not None and hasattr(cond_value, "literal"):
        raw = getattr(cond_value, "literal", cond_value)
    else:
        raw = cond_value
    if raw in ("current_user", "current_context") or (
        isinstance(raw, str) and raw.startswith("current_user.")
    ):
        return None
    if not isinstance(raw, str | int | float | bool):
        return None
    return str(field), raw


def or_tree_to_in_filters(condition: Any) -> dict[str, list[Any]] | None:
    """If *condition* is an OR-tree of equality leaves on one field → {field: [vals]}."""
    leaves: list[tuple[str, Any]] = []

    def walk(node: Any) -> bool:
        leaf = equality_leaf(node)
        if leaf is not None:
            leaves.append(leaf)
            return True
        op = getattr(node, "operator", None)
        if op is None:
            return False
        op_val = op.value if hasattr(op, "value") else str(op)
        if op_val != "or":
            return False
        return walk(getattr(node, "left", None)) and walk(getattr(node, "right", None))

    if not walk(condition) or not leaves:
        return None
    fields = {f for f, _ in leaves}
    if len(fields) != 1:
        return None
    field = next(iter(fields))
    vals = list(dict.fromkeys(v for f, v in leaves if f == field))
    return {field: vals}


def region_or_is_same_field_equality(condition: Any) -> bool | None:
    """True if OR is same-field equality; False if unsupported OR; None if no OR."""
    if condition is None:
        return None
    op = getattr(condition, "operator", None)
    if op is None:
        return None
    op_val = op.value if hasattr(op, "value") else str(op)
    if op_val == "and":
        left = region_or_is_same_field_equality(getattr(condition, "left", None))
        right = region_or_is_same_field_equality(getattr(condition, "right", None))
        if left is False or right is False:
            return False
        return None
    if op_val != "or":
        return None
    return or_tree_to_in_filters(condition) is not None


def warn_unsupported_region_or(condition: Any, workspace_name: str, region_id: str) -> str | None:
    """Validate warning text when region OR cannot lower to field__in."""
    if region_or_is_same_field_equality(condition) is not False:
        return None
    return (
        f"Workspace '{workspace_name}' region '{region_id}': filter uses "
        f"`or` that is not same-field equality (e.g. "
        f"`status = held or status = confirmed`). Split into two regions "
        f"or use one field with OR of equalities — mixed-field OR is "
        f"fail-closed empty at runtime (#1630)."
    )
