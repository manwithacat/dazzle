"""Display-name resolution for FK relation dicts.

Pure helpers for converting FK-relation dicts into user-facing display
strings. Lifted out of ``back.runtime.workspace_card_data`` in #1094
(parent #1086) so that ``ui/`` page handlers can decorate response
records without crossing the back↔ui boundary.
"""

from typing import Any


def _resolve_display_name(value: Any) -> str:
    """Resolve a field value to a display string.

    FK relations are dicts with an optional ``__display__`` key.
    Falls back to ``name``, ``title``, ``code``, ``label``, then ``id``.
    Scalar values are simply stringified.
    """
    if value is None:
        return ""
    if isinstance(value, dict):
        for key in ("__display__", "name", "title", "code", "label", "id"):
            v = value.get(key)
            if v is not None:
                return str(v)
        # Last resort: first string value in the dict
        for v in value.values():
            if isinstance(v, str) and v:
                return v
        return str(value.get("id", ""))
    return str(value)


def _inject_display_names(item: dict[str, Any]) -> dict[str, Any]:
    """Inject ``{field}_display`` keys for FK dict fields (#571).

    For each field whose value is a dict (FK relation), adds a sibling key
    with the resolved display name. The original dict is preserved for
    templates that need the id for linking.
    """
    extras: dict[str, str] = {}
    for key, value in item.items():
        if isinstance(value, dict) and key != "_attention":
            extras[f"{key}_display"] = _resolve_display_name(value)
    if extras:
        item.update(extras)
    return item


def group_field_key(item: dict[str, Any], field: str) -> str:
    """Stable group/parent id (UUID / scalar — never ``str(dict)``).

    Shared by tree parent-ref nesting and kanban FK columns (oral #169).
    Runtime rows expose refs as a bare UUID, ``{field}_id``, or nested
    ``{id/uuid/pk}``. Leftover ``zzz`` stays a key.
    """
    val: Any = item.get(field)
    if val is None or val == "":
        val = item.get(f"{field}_id")
    if isinstance(val, dict):
        val = val.get("id") or val.get("uuid") or val.get("pk")
    if val is None:
        return ""
    return str(val).strip()


def kanban_group_label(item: dict[str, Any], field: str, key: str) -> str:
    """Clerk-facing kanban column label.

    Prefers ``{field}_display`` / nested name. Bare leftover ``zzz`` /
    UUID without a display name stays put — do not invent a person.
    """
    disp = item.get(f"{field}_display")
    if disp not in (None, ""):
        text = str(disp).strip()
        if text:
            return text
    val = item.get(field)
    if isinstance(val, dict):
        name = _resolve_display_name(val)
        if name and name != key:
            return name
        for nested in ("name", "title", "label", "__display__"):
            inner = val.get(nested)
            if inner not in (None, ""):
                return str(inner).strip()
    return key


def compute_kanban_item_columns(
    items: list[dict[str, Any]],
    field: str,
) -> list[tuple[str, str]]:
    """Distinct ``(bucket_key, label)`` when enum/SM columns are empty.

    ``compute_kanban_columns`` only returns enum / state-machine values,
    so live ``group_by: assigned_to`` boards (simple_task ``by_assignee``
    / ``plate_by_person``) dumped empty chrome while assigned tasks
    existed (oral #169). Empty items invent nothing. Leftover ``zzz``
    stays a column.
    """
    group_field = field if isinstance(field, str) else str(field or "")
    if not group_field or not items:
        return []
    seen: dict[str, str] = {}
    order: list[str] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        key = group_field_key(item, group_field)
        if not key:
            continue
        if key not in seen:
            seen[key] = kanban_group_label(item, group_field, key)
            order.append(key)
    return [(k, seen[k]) for k in order]
