"""WorkspaceRegion → Fragment primitive adapter (Phase 4A).

Parallel to `FragmentSurfaceAdapter` but for `WorkspaceRegion` — the
multi-region dashboard layout uses a different render shape than
single-surface pages. Each region declares a `display:` mode that
determines which primitive renders the data.

The integration with `workspace_renderer.py` is a separate plan; this
module is the substrate piece that maps `(region_spec, ctx) →
Fragment`. Currently covers `list`, `kanban`, `timeline`, `grid`,
`metrics`/`summary`, `bar_chart`. Subsequent plans add `pivot_table`,
`heatmap`, `funnel_chart`, `diagram` driven by the audit's
aggregated_blockers report.
"""

from __future__ import annotations

from typing import Any

from dazzle.render.fragment import (
    KPI,
    Badge,
    BarChart,
    Card,
    EmptyState,
    Fragment,
    Grid,
    Heading,
    KanbanBoard,
    PivotTable,
    Region,
    Row,
    Stack,
    Surface,
    Tabs,
    Text,
    Timeline,
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
    for key, raw_items in items_by_group.items():
        if key in seen:
            continue
        leftover_items.extend(_format_card(item) for item in raw_items)
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
        raw_display = getattr(display_obj, "value", None)
        if raw_display is None:
            raw_display = "" if display_obj is None else str(display_obj)
        display_value = raw_display.strip()

        if display_value in ("", "list"):
            return self._build_list(region, ctx)
        if display_value == "kanban":
            return self._build_kanban(region, ctx)
        if display_value == "timeline":
            return self._build_timeline(region, ctx)
        if display_value == "grid":
            return self._build_grid(region, ctx)
        if display_value in ("metrics", "summary"):
            return self._build_metrics(region, ctx)
        if display_value == "bar_chart":
            return self._build_bar_chart(region, ctx)
        if display_value == "pivot_table":
            return self._build_pivot_table(region, ctx)
        if display_value == "tabbed_list":
            return self._build_tabbed_list(region, ctx)
        if display_value == "activity_feed":
            return self._build_timeline(region, ctx)
        if display_value == "detail":
            return self._build_detail(region, ctx)
        if display_value == "queue":
            return self._build_list(region, ctx)
        if display_value == "histogram":
            return self._build_bar_chart(region, ctx)
        if display_value == "funnel_chart":
            return self._build_funnel_chart(region, ctx)
        if display_value == "status_list":
            return self._build_status_list(region, ctx)
        if display_value == "profile_card":
            return self._build_detail(region, ctx)
        if display_value == "action_grid":
            return self._build_grid(region, ctx)
        if display_value == "tree":
            return self._build_tree(region, ctx)
        if display_value == "pipeline_steps":
            return self._build_pipeline_steps(region, ctx)
        if display_value == "progress":
            return self._build_progress(region, ctx)
        if display_value == "heatmap":
            return self._build_pivot_table(region, ctx)
        if display_value == "confirm_action_panel":
            return self._build_confirm_action_panel(region, ctx)
        if display_value == "search_box":
            return self._build_search_box(region, ctx)
        if display_value == "bar_track":
            return self._build_bar_track(region, ctx)
        if display_value == "bullet":
            return self._build_bullet(region, ctx)

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

    def _build_timeline(self, region: Any, ctx: dict[str, Any]) -> Surface:
        """`display: timeline` regions render as a Timeline primitive
        — chronological list of (label, iso-date) events.

        ctx shape:
            items: list of dicts (rows from the source entity)
            label_field: str — which field carries the event label
                (defaults to 'title' / 'name' / 'id')
            date_field: str — which field carries the event date
                (typically the region's `date_field` clause; falls
                back to `created_at` then any iso-date-shaped field)
        """
        title = (
            getattr(region, "title", None) or getattr(region, "name", "").replace("_", " ").title()
        )
        items: list[dict[str, Any]] = ctx.get("items", []) or []
        label_field = str(ctx.get("label_field") or "")
        date_field = str(ctx.get("date_field") or getattr(region, "date_field", "") or "")

        body: Fragment
        if not items:
            body = EmptyState(
                title="No events",
                description=getattr(region, "empty_message", None) or "No data in this region.",
            )
        else:
            events: list[tuple[str, str]] = []
            for item in items:
                if not isinstance(item, dict):
                    continue
                label = ""
                if label_field and label_field in item:
                    label = str(item.get(label_field) or "")
                else:
                    for cand in ("title", "name", "id"):
                        if cand in item:
                            label = str(item.get(cand) or "")
                            break
                date = ""
                if date_field and date_field in item:
                    date = str(item.get(date_field) or "")
                else:
                    for cand in ("date", "created_at", "occurred_at", "timestamp"):
                        if cand in item:
                            date = str(item.get(cand) or "")
                            break
                if label and date:
                    events.append((label, date))
            if events:
                body = Timeline(events=tuple(events))
            else:
                body = EmptyState(
                    title="No events",
                    description=getattr(region, "empty_message", None)
                    or "No items had a label and date.",
                )

        return Surface(
            header=Heading(title, level=2),
            body=Region(kind="report", body=body),
        )

    def _build_pivot_table(self, region: Any, ctx: dict[str, Any]) -> Surface:
        """`display: pivot_table` regions render as a PivotTable primitive
        — a 2-D matrix indexed by row + column dimensions.

        ctx shape:
            rows: list[str] — row dimension labels (e.g. enum values)
            columns: list[str] — column dimension labels
            cells: dict[(row, col) → int] — pre-aggregated counts
            chart_label: optional override
        """
        title = (
            getattr(region, "title", None) or getattr(region, "name", "").replace("_", " ").title()
        )
        chart_label = str(ctx.get("chart_label") or title or "Pivot")
        rows = tuple(str(r) for r in (ctx.get("rows") or []))
        columns = tuple(str(c) for c in (ctx.get("columns") or []))
        raw_cells = ctx.get("cells") or {}
        cells: dict[tuple[str, str], int] = {}
        if isinstance(raw_cells, dict):
            for key, val in raw_cells.items():
                if isinstance(key, (list, tuple)) and len(key) == 2:
                    r, c = str(key[0]), str(key[1])
                    if r in rows and c in columns:
                        try:
                            cells[(r, c)] = int(val)
                        except (TypeError, ValueError):
                            continue

        body: Fragment
        if not rows or not columns:
            body = EmptyState(
                title="No data",
                description=getattr(region, "empty_message", None)
                or "No row or column dimensions to pivot.",
            )
        else:
            body = PivotTable(label=chart_label, rows=rows, columns=columns, cells=cells)

        return Surface(
            header=Heading(title, level=2),
            body=Region(kind="report", body=body),
        )

    def _build_confirm_action_panel(self, region: Any, ctx: dict[str, Any]) -> Surface:
        """`display: confirm_action_panel` renders a Card with the
        action's title and a description prompt. Without a Button
        primitive wired here, the actual confirm UI is deferred to
        a later plan; this just closes the audit gap.

        ctx shape:
            title: optional override
            prompt / description / message: prompt text
            action_label: optional button text shown as plain Text below
        """
        heading = (
            getattr(region, "title", None) or getattr(region, "name", "").replace("_", " ").title()
        )
        prompt = str(ctx.get("prompt") or ctx.get("description") or ctx.get("message") or "")
        action_label = str(ctx.get("action_label") or "")

        rows: list[object] = [Heading(heading or "(no title)", level=3)]
        if prompt:
            rows.append(Text(prompt))
        if action_label:
            rows.append(Text(f"[ {action_label} ]"))

        body = Card(body=Stack(children=tuple(rows), gap="sm"))
        return Surface(
            header=Heading(heading or "Confirm", level=2),
            body=Region(kind="dashboard", body=body),
        )

    def _build_search_box(self, region: Any, ctx: dict[str, Any]) -> Surface:
        """`display: search_box` renders a Card with a search Field.

        ctx shape:
            field_name: optional, defaults to 'q'
            placeholder: optional
            label: optional, defaults to "Search"
        """
        from dazzle.render.fragment import Field

        title = (
            getattr(region, "title", None) or getattr(region, "name", "").replace("_", " ").title()
        )
        field_name = str(ctx.get("field_name") or "q")
        label = str(ctx.get("label") or "Search")
        placeholder = str(ctx.get("placeholder") or "")

        body = Card(
            body=Field(
                name=field_name,
                label=label,
                kind="text",
                placeholder=placeholder,
            )
        )
        return Surface(
            header=Heading(title, level=2),
            body=Region(kind="form", body=body),
        )

    def _build_bar_track(self, region: Any, ctx: dict[str, Any]) -> Surface:
        """`display: bar_track` renders one labelled, filled progress
        track per row — same shape as `progress`, structurally. Phase 4A
        treats them as variants of each other; a richer rendering can
        come once a dedicated BarTrack primitive ships.

        ctx shape:
            items: list of dicts {"label": str, "percent": int 0..100}
                — values clamped to [0, 100]
        """
        return self._build_progress(region, ctx)

    def _build_bullet(self, region: Any, ctx: dict[str, Any]) -> Surface:
        """`display: bullet` renders rows showing actual-vs-target.
        Each row: label + actual Badge + "/ target" Text + target Badge.

        ctx shape:
            items: list of dicts {"label": str, "actual": int|str,
                                  "target": int|str}
        """
        title = (
            getattr(region, "title", None) or getattr(region, "name", "").replace("_", " ").title()
        )
        items = ctx.get("items") or []

        rows: list[object] = []
        if isinstance(items, list):
            for item in items:
                if not isinstance(item, dict):
                    continue
                label = str(item.get("label") or item.get("name") or "")
                actual = item.get("actual", "—")
                target = item.get("target", "—")
                # Map "actual >= target" → success, "<half" → danger, else warning.
                variant: str = "info"
                try:
                    a, t = float(actual), float(target)
                    if t > 0:
                        ratio = a / t
                        if ratio >= 1.0:
                            variant = "success"
                        elif ratio < 0.5:
                            variant = "danger"
                        else:
                            variant = "warning"
                except (TypeError, ValueError):
                    variant = "info"
                rows.append(
                    Row(
                        children=(
                            Text(label or "(no label)"),
                            Badge(label=str(actual), variant=variant),  # type: ignore[arg-type]
                            Text("/"),
                            Badge(label=str(target), variant="default"),
                        ),
                        gap="sm",
                        align="center",
                    )
                )

        body: Fragment
        if not rows:
            body = EmptyState(
                title="No data",
                description=getattr(region, "empty_message", None) or "No bullet rows.",
            )
        else:
            body = Stack(children=tuple(rows), gap="sm")

        return Surface(
            header=Heading(title, level=2),
            body=Region(kind="report", body=body),
        )

    def _build_tree(self, region: Any, ctx: dict[str, Any]) -> Surface:
        """`display: tree` regions render a hierarchical list as a Stack
        of indented Heading rows. Indent is encoded as leading whitespace
        in the label, so depth stays visible in plain HTML without a
        dedicated Tree primitive.

        ctx shape:
            items: list of dicts; each may carry a `children` list with
                the same shape (recursive tree)
            label_field: optional, defaults to title/name/id auto-pick
        """
        title = (
            getattr(region, "title", None) or getattr(region, "name", "").replace("_", " ").title()
        )
        items = ctx.get("items") or []
        label_field = str(ctx.get("label_field") or "")

        def _label_for(item: dict[str, Any]) -> str:
            if label_field and label_field in item:
                return str(item.get(label_field) or "")
            for cand in ("title", "name", "id"):
                if cand in item:
                    return str(item.get(cand) or "")
            return "(no label)"

        rows: list[object] = []

        def _walk(node_list: list[Any], depth: int) -> None:
            for node in node_list:
                if not isinstance(node, dict):
                    continue
                indent = "  " * depth
                label = _label_for(node)
                rows.append(Text(f"{indent}{label}"))
                children = node.get("children") or []
                if isinstance(children, list) and children:
                    _walk(children, depth + 1)

        if isinstance(items, list):
            _walk(items, 0)

        body: Fragment
        if not rows:
            body = EmptyState(
                title="No items",
                description=getattr(region, "empty_message", None) or "No data in this region.",
            )
        else:
            body = Stack(children=tuple(rows), gap="sm")

        return Surface(
            header=Heading(title, level=2),
            body=Region(kind="list", body=body),
        )

    def _build_pipeline_steps(self, region: Any, ctx: dict[str, Any]) -> Surface:
        """`display: pipeline_steps` renders a sequence of steps as a
        horizontal Row of Cards — one Card per step with a Heading and
        descriptive Text.

        ctx shape:
            steps: list of dicts {"label": str, "description": str (optional),
                                  "status": str (optional)}
        """
        title = (
            getattr(region, "title", None) or getattr(region, "name", "").replace("_", " ").title()
        )
        steps = ctx.get("steps") or ctx.get("items") or []

        cards: list[object] = []
        if isinstance(steps, list):
            for step in steps:
                if not isinstance(step, dict):
                    continue
                label = str(step.get("label") or step.get("name") or step.get("title") or "")
                description = str(step.get("description") or step.get("status") or "")
                inner: list[object] = [Heading(label or "(no step)", level=4)]
                if description:
                    inner.append(Text(description))
                cards.append(Card(body=Stack(children=tuple(inner), gap="sm")))

        body: Fragment
        if not cards:
            body = EmptyState(
                title="No steps",
                description=getattr(region, "empty_message", None) or "No steps declared.",
            )
        else:
            body = Row(children=tuple(cards), gap="md", align="stretch")

        return Surface(
            header=Heading(title, level=2),
            body=Region(kind="dashboard", body=body),
        )

    def _build_progress(self, region: Any, ctx: dict[str, Any]) -> Surface:
        """`display: progress` renders a Stack of label / percentage
        rows. Without a dedicated ProgressBar primitive we use the
        existing Text+Badge pair: label on the left, "<n>%" on the right.

        ctx shape:
            items: list of dicts {"label": str, "percent": int 0..100}
                — values outside [0, 100] are clamped
        """
        title = (
            getattr(region, "title", None) or getattr(region, "name", "").replace("_", " ").title()
        )
        items = ctx.get("items") or []

        rows: list[object] = []
        if isinstance(items, list):
            for item in items:
                if not isinstance(item, dict):
                    continue
                label = str(item.get("label") or item.get("name") or item.get("title") or "")
                try:
                    percent = int(item.get("percent") or item.get("value") or 0)
                except (TypeError, ValueError):
                    percent = 0
                percent = max(0, min(100, percent))
                # Map ranges to badge variants for at-a-glance reading.
                variant: str = "info"
                if percent >= 90:
                    variant = "success"
                elif percent >= 50:
                    variant = "info"
                elif percent >= 25:
                    variant = "warning"
                else:
                    variant = "danger"
                rows.append(
                    Row(
                        children=(
                            Text(label or "(no label)"),
                            Badge(label=f"{percent}%", variant=variant),  # type: ignore[arg-type]
                        ),
                        gap="md",
                        align="center",
                    )
                )

        body: Fragment
        if not rows:
            body = EmptyState(
                title="No progress",
                description=getattr(region, "empty_message", None) or "No data in this region.",
            )
        else:
            body = Stack(children=tuple(rows), gap="sm")

        return Surface(
            header=Heading(title, level=2),
            body=Region(kind="list", body=body),
        )

    def _build_status_list(self, region: Any, ctx: dict[str, Any]) -> Surface:
        """`display: status_list` regions render as a Stack of rows
        where each row shows a label and a status Badge.

        ctx shape:
            items: list of dicts (rows from the source entity)
            label_field: optional, defaults to title/name/id auto-pick
            status_field: which field carries the status value
                (defaults to 'status' / 'state' / 'stage')
            status_variants: optional dict[status_value → Badge.variant]
                for severity colouring (e.g. {"failed": "danger"})
        """
        title = (
            getattr(region, "title", None) or getattr(region, "name", "").replace("_", " ").title()
        )
        items: list[dict[str, Any]] = ctx.get("items", []) or []
        label_field = str(ctx.get("label_field") or "")
        status_field = str(ctx.get("status_field") or "")
        variants = ctx.get("status_variants") or {}
        if not isinstance(variants, dict):
            variants = {}

        body: Fragment
        if not items:
            body = EmptyState(
                title="No items",
                description=getattr(region, "empty_message", None) or "No data in this region.",
            )
        else:
            rows: list[object] = []
            for item in items:
                if not isinstance(item, dict):
                    continue
                label = ""
                if label_field and label_field in item:
                    label = str(item.get(label_field) or "")
                else:
                    for cand in ("title", "name", "id"):
                        if cand in item:
                            label = str(item.get(cand) or "")
                            break
                status_val = ""
                if status_field and status_field in item:
                    status_val = str(item.get(status_field) or "")
                else:
                    for cand in ("status", "state", "stage"):
                        if cand in item:
                            status_val = str(item.get(cand) or "")
                            break
                variant_raw = str(variants.get(status_val) or "default")
                variant = (
                    variant_raw
                    if variant_raw in ("default", "info", "success", "warning", "danger")
                    else "default"
                )
                rows.append(
                    Row(
                        children=(
                            Text(label or "(no label)"),
                            Badge(label=status_val or "—", variant=variant),  # type: ignore[arg-type]
                        ),
                        gap="md",
                        align="center",
                    )
                )
            if rows:
                body = Stack(children=tuple(rows), gap="sm")
            else:
                body = EmptyState(title="No items", description="No items had a label.")

        return Surface(
            header=Heading(title, level=2),
            body=Region(kind="list", body=body),
        )

    def _build_funnel_chart(self, region: Any, ctx: dict[str, Any]) -> Surface:
        """`display: funnel_chart` is a BarChart with buckets sorted in
        descending order — funnels narrow from a wide top stage to a
        narrow conversion at the bottom.

        ctx shape:
            buckets: list[(str, int)] — pre-aggregated stages
            chart_label: optional override
        """
        # Reuse bar_chart's parsing, then sort descending. Caller can
        # pre-sort if a non-monotonic visualisation is intended; the
        # default funnel rendering is "biggest stage first".
        raw_buckets = ctx.get("buckets") or []
        parsed: list[tuple[str, int]] = []
        for entry in raw_buckets:
            if isinstance(entry, (list, tuple)) and len(entry) >= 2:
                try:
                    parsed.append((str(entry[0]), int(entry[1])))
                except (TypeError, ValueError):
                    continue
            elif isinstance(entry, dict):
                key = str(entry.get("label") or entry.get("key") or "")
                try:
                    val = int(entry.get("value") or entry.get("count") or 0)
                except (TypeError, ValueError):
                    val = 0
                if key:
                    parsed.append((key, val))
        parsed.sort(key=lambda kv: kv[1], reverse=True)
        # Hand off to bar_chart's render path with the sorted buckets.
        return self._build_bar_chart(region, {**ctx, "buckets": parsed})

    def _build_detail(self, region: Any, ctx: dict[str, Any]) -> Surface:
        """`display: detail` regions render a single item's fields as a
        labelled Card. One Stack child per (label, value) pair.

        ctx shape:
            item: dict (single record)
            fields: list of {"key": str, "label": str (optional)} pairs
                — declared field order from the region's `fields:` clause
            (legacy) `columns` is accepted as alias for `fields`
        """
        title = (
            getattr(region, "title", None) or getattr(region, "name", "").replace("_", " ").title()
        )
        item = ctx.get("item")
        fields = ctx.get("fields") or ctx.get("columns") or []

        body: Fragment
        if not isinstance(item, dict) or not item:
            body = EmptyState(
                title="No item",
                description=getattr(region, "empty_message", None) or "No item to display.",
            )
        elif not fields:
            # Without an explicit field list, fall back to all keys
            # in declared dict order — preserves DSL author's choice
            # when ctx omits the fields list (e.g. early prototypes).
            fields = [{"key": k} for k in item.keys()]

        if isinstance(item, dict) and item and fields:
            rows: list[object] = []
            for f in fields:
                if not isinstance(f, dict):
                    continue
                key = str(f.get("key") or "")
                if not key:
                    continue
                label = str(f.get("label") or key.replace("_", " ").title())
                value = item.get(key, "")
                rows.append(Heading(label, level=4))
                rows.append(Text(str(value) if value not in (None, "") else "—"))
            if rows:
                body = Card(body=Stack(children=tuple(rows), gap="sm"))
            else:
                body = EmptyState(title="No fields", description="")

        return Surface(
            header=Heading(title, level=2),
            body=Region(kind="dashboard", body=body),
        )

    def _build_tabbed_list(self, region: Any, ctx: dict[str, Any]) -> Surface:
        """`display: tabbed_list` regions render as a Tabs container, one
        tab per source-or-filter slice. Each tab body is a Table.

        ctx shape:
            tabs: list of dicts with shape:
                {"key": str, "label": str (optional), "items": list[dict],
                 "columns": list[{"key": str, "label": str}]}
            (legacy) `slices` is accepted as alias for `tabs`
        """
        from dazzle.render.fragment import Table

        title = (
            getattr(region, "title", None) or getattr(region, "name", "").replace("_", " ").title()
        )
        raw_tabs = ctx.get("tabs") or ctx.get("slices") or []

        body: Fragment
        if not raw_tabs:
            body = EmptyState(
                title="No tabs",
                description=getattr(region, "empty_message", None) or "No data slices declared.",
            )
            return Surface(
                header=Heading(title, level=2),
                body=Region(kind="list", body=body),
            )

        built: list[tuple[str, object]] = []
        seen_keys: set[str] = set()
        for tab in raw_tabs:
            if not isinstance(tab, dict):
                continue
            key = str(tab.get("key") or tab.get("label") or f"tab_{len(built)}")
            if key in seen_keys:
                continue
            seen_keys.add(key)
            items = tab.get("items") or []
            cols = tab.get("columns") or []
            tab_body: Fragment
            if not items:
                tab_body = EmptyState(title="No items", description="")
            elif not cols:
                tab_body = EmptyState(title="No columns", description="")
            else:
                column_labels = tuple(c.get("label", c.get("key", "")) for c in cols)
                rows_data = tuple(
                    tuple(str(item.get(c["key"], "")) for c in cols) for item in items
                )
                tab_body = Table(columns=column_labels, rows=rows_data)
            built.append((key, tab_body))

        if not built:
            body = EmptyState(title="No tabs", description="")
        else:
            body = Tabs(tabs=tuple(built))

        return Surface(
            header=Heading(title, level=2),
            body=Region(kind="list", body=body),
        )

    def _build_grid(self, region: Any, ctx: dict[str, Any]) -> Surface:
        """`display: grid` regions render items as cards in an N-column
        Grid. Columns default to 3; ctx can override via `columns`.

        ctx shape:
            items: list of dicts (rows from the source entity)
            label_field: optional, defaults to title/name/id auto-pick
            columns: int (default 3, max 12)
        """
        title = (
            getattr(region, "title", None) or getattr(region, "name", "").replace("_", " ").title()
        )
        items: list[dict[str, Any]] = ctx.get("items", []) or []
        columns = int(ctx.get("columns") or 3)
        columns = max(1, min(12, columns))
        label_field = str(ctx.get("label_field") or "")

        body: Fragment
        if not items:
            body = EmptyState(
                title="No items",
                description=getattr(region, "empty_message", None) or "No data in this region.",
            )
        else:
            cards: list[object] = []
            for item in items:
                if not isinstance(item, dict):
                    continue
                label = ""
                if label_field and label_field in item:
                    label = str(item.get(label_field) or "")
                else:
                    for cand in ("title", "name", "id"):
                        if cand in item:
                            label = str(item.get(cand) or "")
                            break
                cards.append(Card(body=Text(label or "(no label)")))
            if cards:
                body = Grid(children=tuple(cards), columns=columns)
            else:
                body = EmptyState(title="No items", description="No data in this region.")

        return Surface(
            header=Heading(title, level=2),
            body=Region(kind="dashboard", body=body),
        )

    def _build_metrics(self, region: Any, ctx: dict[str, Any]) -> Surface:
        """`display: metrics` (and `summary`) regions render a row of
        KPI tiles — one per declared aggregate.

        ctx shape:
            metrics: list of dicts with label/value/trend/delta keys
                — pre-computed by the runtime's aggregate evaluator
            (legacy) aggregates: dict[name → resolved value], used as
                fallback when metrics list isn't supplied
        """
        title = (
            getattr(region, "title", None) or getattr(region, "name", "").replace("_", " ").title()
        )
        metrics_list: list[dict[str, Any]] = ctx.get("metrics", []) or []
        if not metrics_list:
            agg = ctx.get("aggregates") or getattr(region, "aggregates", {}) or {}
            if isinstance(agg, dict):
                metrics_list = [
                    {"label": str(name).replace("_", " ").title(), "value": str(val or "—")}
                    for name, val in agg.items()
                ]

        body: Fragment
        if not metrics_list:
            body = EmptyState(
                title="No metrics",
                description=getattr(region, "empty_message", None) or "No metrics declared.",
            )
        else:
            kpis: list[object] = []
            for m in metrics_list:
                if not isinstance(m, dict):
                    continue
                trend = str(m.get("trend") or "flat")
                if trend not in ("up", "down", "flat"):
                    trend = "flat"
                kpis.append(
                    KPI(
                        label=str(m.get("label") or m.get("name") or ""),
                        value=str(m.get("value") or "—"),
                        trend=trend,  # type: ignore[arg-type]
                        delta=str(m.get("delta") or ""),
                    )
                )
            if not kpis:
                body = EmptyState(title="No metrics", description="No metric tiles produced.")
            else:
                cols = max(1, min(12, len(kpis)))
                body = Grid(children=tuple(kpis), columns=cols)

        return Surface(
            header=Heading(title, level=2),
            body=Region(kind="dashboard", body=body),
        )

    def _build_bar_chart(self, region: Any, ctx: dict[str, Any]) -> Surface:
        """`display: bar_chart` regions render as a BarChart primitive
        — list of (label, count) tuples derived from the region's
        group_by aggregation.

        ctx shape:
            buckets: list[(str, int)] — pre-aggregated by the runtime
            (legacy) items + group_by_field as fallback
            chart_label: optional override for the BarChart label
        """
        title = (
            getattr(region, "title", None) or getattr(region, "name", "").replace("_", " ").title()
        )
        chart_label = str(ctx.get("chart_label") or title or "Chart")
        raw_buckets = ctx.get("buckets") or []
        buckets: list[tuple[str, int]] = []
        for entry in raw_buckets:
            if isinstance(entry, (list, tuple)) and len(entry) >= 2:
                try:
                    buckets.append((str(entry[0]), int(entry[1])))
                except (TypeError, ValueError):
                    continue
            elif isinstance(entry, dict):
                key = str(entry.get("label") or entry.get("key") or "")
                try:
                    val = int(entry.get("value") or entry.get("count") or 0)
                except (TypeError, ValueError):
                    val = 0
                if key:
                    buckets.append((key, val))

        body: Fragment
        if not buckets:
            body = EmptyState(
                title="No data",
                description=getattr(region, "empty_message", None) or "No buckets to chart.",
            )
        else:
            body = BarChart(label=chart_label, buckets=tuple(buckets))

        return Surface(
            header=Heading(title, level=2),
            body=Region(kind="report", body=body),
        )
