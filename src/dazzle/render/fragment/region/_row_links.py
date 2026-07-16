"""Per-row drill-down URL resolution (shared list/region helper).

Relocated from ``back.runtime.renderers.fragment_adapter`` into ``render`` by
ADR-0038 so the standalone list path (``back``) and the workspace region path
(``render.fragment.region``) share one pure substitution contract without
``render`` importing ``back``. Pure: stdlib + ``str.format`` only.
"""

from typing import Any
from uuid import UUID


def _format_link_value(value: Any) -> str:
    """Coerce a row field value to a URL path segment (#1603 dogfood).

    List payloads often hydrate refs as nested records
    (``{"id": UUID(...), "name": "..."}``) or UUID objects. ``format_map``
    would otherwise stringify the whole dict into the path. Prefer the
    scalar id when present.
    """
    if value is None:
        raise KeyError("null")
    if isinstance(value, UUID):
        return str(value)
    # Mapping / dict-shaped ref (hydrated FK)
    if isinstance(value, dict):
        inner = value.get("id")
        if inner is None:
            raise KeyError("dict without id")
        return _format_link_value(inner)
    # ORM / simple namespace object with .id
    if not isinstance(value, (str, bytes, int, float, bool)) and hasattr(value, "id"):
        inner = getattr(value, "id", None)
        if inner is not None:
            return _format_link_value(inner)
    return str(value)


def _item_format_map(item: dict[str, Any]) -> dict[str, str]:
    """Build a format mapping for one row (skip null / unwrappable values)."""

    class _NullMap(dict[str, str]):
        def __missing__(self, key: str) -> str:
            raise KeyError(key)

    mapping = _NullMap()
    for k, v in item.items():
        if v is None:
            continue
        try:
            mapping[k] = _format_link_value(v)
        except KeyError:
            continue
    return mapping


def _resolve_row_links(
    items: list[dict[str, Any]],
    detail_url_template: str,
    *,
    fallback_template: str = "",
    candidate_templates: tuple[str, ...] | list[str] = (),
) -> tuple[str | None, ...]:
    """Issue #1029 phase 1: per-row drill-down URL resolution.

    `detail_url_template` is a Python format string carrying named
    placeholders (typically `{id}`, but DSL authors may use `{slug}`,
    `{code}`, etc. — and #1603 `open: Entity via field` uses `{fk_field}`).
    For each item, substitute `{key}` with a URL-safe scalar from
    `item[key]` (unwrapping hydrated ref dicts / UUIDs) and emit the
    resolved URL.

    #1600 P2: ``candidate_templates`` is an ordered first-non-null open-via
    chain (polymorphic client FKs). When non-empty, try each hop before the
    primary template is used alone.

    #1614: when no candidate resolves (null open-via FKs), try
    ``fallback_template`` (typically same-entity ``.../{id}``) so the
    row keeps a drill + ``hx-trigger=click`` — which also shields action
    buttons from inheriting tbody ``load`` (#1613).

    Empty templates → empty tuple.
    """
    templates: list[str] = [t for t in (candidate_templates or ()) if t]
    if not templates and detail_url_template:
        templates = [detail_url_template]
    if not templates:
        return ()
    out: list[str | None] = []
    for item in items:
        mapping = _item_format_map(item)
        url: str | None = None
        for tmpl in templates:
            try:
                # #1603: skip hop when a placeholder is missing or null
                url = tmpl.format_map(mapping)
                break
            except (KeyError, IndexError, ValueError):
                continue
        if not url and fallback_template:
            try:
                url = fallback_template.format_map(mapping)
            except (KeyError, IndexError, ValueError):
                url = None
        out.append(url or None)
    return tuple(out)
