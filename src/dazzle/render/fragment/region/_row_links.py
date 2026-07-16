"""Per-row drill-down URL resolution (shared list/region helper).

Relocated from ``back.runtime.renderers.fragment_adapter`` into ``render`` by
ADR-0038 so the standalone list path (``back``) and the workspace region path
(``render.fragment.region``) share one pure substitution contract without
``render`` importing ``back``. Pure: stdlib + ``str.format`` only.
"""

from typing import Any


def _resolve_row_links(
    items: list[dict[str, Any]], detail_url_template: str
) -> tuple[str | None, ...]:
    """Issue #1029 phase 1: per-row drill-down URL resolution.

    `detail_url_template` is a Python format string carrying named
    placeholders (typically `{id}`, but DSL authors may use `{slug}`,
    `{code}`, etc.). For each item, substitute `{key}` with `item[key]`
    and emit the resolved URL. Items missing a required key get `None`
    (no row link) — defensive for partial records or rows that aren't
    really drillable (e.g., summary rows).

    Empty template → empty tuple (caller short-circuits before
    reaching here, but defensive)."""
    if not detail_url_template:
        return ()
    out: list[str | None] = []
    for item in items:
        try:
            # #1603: skip drill when a placeholder is missing or null
            # (e.g. open via assigned_to with no assignee).
            class _NullMap(dict[str, Any]):
                def __missing__(self, key: str) -> str:
                    raise KeyError(key)

            mapping = _NullMap((k, v) for k, v in item.items() if v is not None)
            out.append(detail_url_template.format_map(mapping))
        except (KeyError, IndexError, ValueError):
            # Template referenced a key that's not on this row, or the
            # template has malformed placeholders. Skip the link
            # rather than crash the whole list render.
            out.append(None)
    return tuple(out)
