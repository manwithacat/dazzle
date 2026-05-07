"""WorkspaceRegion → Fragment primitive adapter (Phase 4A).

Parallel to `FragmentSurfaceAdapter` but for `WorkspaceRegion` — the
multi-region dashboard layout uses a different render shape than
single-surface pages. Each region declares a `display:` mode that
determines which primitive renders the data.

The integration with `workspace_renderer.py` is a separate plan; this
module is the substrate piece that maps `(region_spec, ctx) →
Fragment`. Currently covers `kanban`; subsequent plans add `timeline`,
`grid`, `metrics`, `bar_chart`, etc. one at a time, driven by the
audit's aggregated_blockers report.
"""

from __future__ import annotations

from typing import Any

from dazzle.render.fragment import (
    EmptyState,
    Fragment,
    Heading,
    KanbanBoard,
    Region,
    Surface,
    Text,
)


def _coerce_columns(
    group_keys: list[str], items_by_group: dict[str, list[Any]]
) -> tuple[tuple[str, tuple[object, ...]], ...]:
    """Build the KanbanBoard.columns tuple from a group→items mapping.

    `group_keys` carries declared order (e.g. enum value order); any
    items grouped under a key not in the list go into a synthetic
    "Other" column at the end. Columns with zero items still render
    (empty column = "no items in this status yet" UX).
    """
    columns: list[tuple[str, tuple[object, ...]]] = []
    seen: set[str] = set()
    for key in group_keys:
        seen.add(key)
        items = tuple(_format_card(item) for item in items_by_group.get(key, []))
        columns.append((key, items))
    leftover_items: list[object] = []
    for key, items in items_by_group.items():
        if key in seen:
            continue
        leftover_items.extend(_format_card(item) for item in items)
    if leftover_items:
        columns.append(("Other", tuple(leftover_items)))
    return tuple(columns)


def _format_card(item: Any) -> object:
    """Item → card body. Items are usually dicts (from the runtime's
    aggregate result); render as plain Text of the display title for
    now. Future plans introduce a typed Card primitive that carries
    title + supplementary fields (assignee avatar, due date, etc.)."""
    if isinstance(item, dict):
        title = (
            item.get("display_title")
            or item.get("title")
            or item.get("name")
            or item.get("id")
            or ""
        )
        return Text(str(title))
    return Text(str(item))


class WorkspaceRegionAdapter:
    """Translate a WorkspaceRegion + ctx into a Fragment tree."""

    def build(self, region: Any, ctx: dict[str, Any]) -> Fragment:
        """Dispatch on `region.display` to the right primitive.

        Phase 4A starter — only `kanban` is wired. Other displays
        raise NotImplementedError so the audit's flag stays honest:
        if the runtime tries to render an unsupported display through
        this adapter, the failure is loud, not silent.
        """
        display_obj = getattr(region, "display", None)
        display_value = (
            display_obj.value if hasattr(display_obj, "value") else str(display_obj or "")
        ).strip()

        if display_value in ("", "list"):
            return self._build_list(region, ctx)
        if display_value == "kanban":
            return self._build_kanban(region, ctx)

        raise NotImplementedError(
            f"WorkspaceRegionAdapter does not yet support display={display_value!r}; "
            f"audit `unsupported_display={display_value}` blockers tell you which to "
            f"close next. KanbanBoard, Timeline, KPI, BarChart, PivotTable primitives "
            f"already exist (Plan 1); the work is wiring them here."
        )

    def _build_list(self, region: Any, ctx: dict[str, Any]) -> Surface:
        """`display: list` regions render as a Region(kind=list) with
        the same Table primitive used for surface lists. Identical
        ctx shape (items + columns) so the surface-list adapter could
        be lifted out of FragmentSurfaceAdapter for shared use later."""
        from dazzle.render.fragment import Table

        title = (
            getattr(region, "title", None) or getattr(region, "name", "").replace("_", " ").title()
        )
        items = ctx.get("items", []) or []
        columns = ctx.get("columns", []) or []

        body: Fragment
        if not items:
            body = EmptyState(
                title="No items",
                description=getattr(region, "empty_message", None) or "No data in this region.",
            )
        else:
            column_labels = tuple(col.get("label", col.get("key", "")) for col in columns)
            rows = tuple(tuple(str(item.get(col["key"], "")) for col in columns) for item in items)
            body = Table(columns=column_labels, rows=rows)

        return Surface(
            header=Heading(title, level=2),
            body=Region(kind="list", body=body),
        )

    def _build_kanban(self, region: Any, ctx: dict[str, Any]) -> Surface:
        """`display: kanban` regions render as a KanbanBoard.

        ctx shape:
            items: list of dicts (rows from the source entity)
            group_keys: list[str] — declared status/state values in
                order (typically from an enum field's enum_values)
            group_by_field: str — the field name to bucket items by
                (the region's `group_by` clause)
        """
        title = (
            getattr(region, "title", None) or getattr(region, "name", "").replace("_", " ").title()
        )
        items: list[dict[str, Any]] = ctx.get("items", []) or []
        group_keys: list[str] = list(ctx.get("group_keys") or [])
        group_by_field: str = str(ctx.get("group_by_field") or "")

        body: Fragment
        if not items and not group_keys:
            body = EmptyState(
                title="No items",
                description=getattr(region, "empty_message", None) or "No data in this region.",
            )
        else:
            # Bucket items by group_by_field
            buckets: dict[str, list[Any]] = {k: [] for k in group_keys}
            for item in items:
                if not isinstance(item, dict):
                    continue
                key = str(item.get(group_by_field, "") or "")
                buckets.setdefault(key, []).append(item)
            columns = _coerce_columns(group_keys, buckets)
            if not columns:
                # KanbanBoard requires at least one column — synthesize
                # an empty placeholder if we have neither items nor keys.
                columns = (("All", ()),)
            body = KanbanBoard(columns=columns)

        return Surface(
            header=Heading(title, level=2),
            body=Region(kind="kanban", body=body),
        )
