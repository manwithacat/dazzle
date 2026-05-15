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
