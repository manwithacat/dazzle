"""WorkspaceRegion → Fragment primitive adapter (Phase 4A).

Parallel to `FragmentSurfaceAdapter` but for `WorkspaceRegion` — the
multi-region dashboard layout uses a different render shape than
single-surface pages. Each region declares a `display:` mode that
determines which primitive renders the data.

The integration with `workspace_renderer.py` is a separate plan; this
module is the substrate piece that maps `(region_spec, ctx) →
Fragment`. Coverage is driven by `_BUILDERS` (direct dispatches) and
`_ALIASES` (display modes that share a builder). The audit's
`_SUPPORTED_DISPLAYS` derives from these, so adding a new display is
a single dict edit instead of two synced lists across two files.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from html import escape as _html_escape
from typing import Any, Literal

# Cross-cutting helpers extracted to ._shared in #1065 PR 2 (v0.67.129).
# Re-imported here so the dispatcher's internal call sites keep working
# unchanged. The public re-export of `_render_status_badge_html` for
# external callers (renderer.py × 4 sites) lives in `__init__.py`.
from dazzle.back.runtime.renderers.region_adapter._shared import (  # noqa: F401
    _region_title,
    _render_status_badge_html,
    _render_typed_value,
    _wrap_surface,
)
from dazzle.render.fragment import (
    URL,
    ActionCard,
    ActionGrid,
    ActivityFeed,
    BarChart,
    BarTrack,
    BoxPlot,
    Bullet,
    BulletRow,
    CohortStripCell,
    CohortStripLensTab,
    CohortStripRegion,
    ConfirmCheckItem,
    ConfirmGate,
    CsvExportButton,
    DateRangePicker,
    DayTimelineRegion,
    DayTimelineSlot,
    DetailGrid,
    Diagram,
    EmptyState,
    EntityCardRegion,
    EntityCardSection,
    FilterBar,
    FilterColumn,
    Fragment,
    Funnel,
    FunnelStage,
    GridCell,
    GridRegion,
    Heatmap,
    HeatmapRow,
    Histogram,
    HistogramBin,
    KanbanCard,
    KanbanColumn,
    KanbanRegion,
    LazyTab,
    LazyTabPanel,
    ListColumn,
    ListRegion,
    MetricsGrid,
    MetricTile,
    PipelineStage,
    PipelineSteps,
    PivotDimSpec,
    PivotTable,
    PivotTableRegion,
    ProfileCard,
    QueueBadgeColumn,
    QueueDateColumn,
    QueueMetric,
    QueueRegion,
    QueueRow,
    QueueTransition,
    Radar,
    RawHTML,
    ReferenceBand,
    ReferenceLine,
    SearchBox,
    Sparkline,
    Stack,
    StageBar,
    StatusList,
    StatusListEntry,
    Surface,
    Tabs,
    TaskInboxItem,
    TaskInboxRegion,
    TaskInboxSummaryChip,
    Text,
    Timeline,
    TimelineEvent,
    TimeSeries,
    Tree,
    TreeNode,
)

_log = logging.getLogger(__name__)

_LABEL_CANDIDATES: tuple[str, ...] = ("title", "name", "id")
_DATE_CANDIDATES: tuple[str, ...] = ("date", "created_at", "occurred_at", "timestamp")


def _parse_reference_lines(raw: Any) -> tuple[ReferenceLine, ...]:
    """Defensive parser — turn ctx['reference_lines'] into a tuple of
    typed ReferenceLine primitives. Unknown styles fall back to solid;
    non-numeric values silently drop."""
    if not isinstance(raw, list):
        return ()
    out: list[ReferenceLine] = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        try:
            value = float(entry.get("value") or 0)
        except (TypeError, ValueError):
            continue
        style_raw = str(entry.get("style") or "solid")
        style: Literal["solid", "dashed", "dotted"] = (
            style_raw  # type: ignore[assignment]
            if style_raw in ("solid", "dashed", "dotted")
            else "solid"
        )
        out.append(ReferenceLine(value=value, label=str(entry.get("label") or ""), style=style))
    return tuple(out)


def _parse_reference_bands(raw: Any) -> tuple[ReferenceBand, ...]:
    """Defensive parser — accepts both `from`/`to` and `from_value`/
    `to_value` key shapes; bands with from > to silently drop;
    unknown colors fall back to target."""
    if not isinstance(raw, list):
        return ()
    out: list[ReferenceBand] = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        try:
            from_val = float(entry.get("from") or entry.get("from_value") or 0)
            to_val = float(entry.get("to") or entry.get("to_value") or 0)
        except (TypeError, ValueError):
            continue
        if from_val > to_val:
            continue
        color_raw = str(entry.get("color") or "target")
        color: Literal["target", "positive", "warning", "destructive", "muted"] = (
            color_raw  # type: ignore[assignment]
            if color_raw in ("target", "positive", "warning", "destructive", "muted")
            else "target"
        )
        out.append(
            ReferenceBand(
                from_value=from_val,
                to_value=to_val,
                label=str(entry.get("label") or ""),
                color=color,
            )
        )
    return tuple(out)


def _pick_label(
    item: dict[str, Any],
    field_hint: str = "",
    candidates: tuple[str, ...] = _LABEL_CANDIDATES,
) -> str:
    """Pick a display label from a dict item.

    `field_hint` wins if provided and present; otherwise the first
    matching candidate field is returned. Used by every list-style
    builder; consolidating it here removes 5 copies of the same loop.
    """
    if field_hint and field_hint in item:
        return str(item.get(field_hint) or "")
    for cand in candidates:
        if cand in item:
            return str(item.get(cand) or "")
    return ""


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
    """Translate a WorkspaceRegion + ctx into a Fragment tree.

    Dispatch is table-driven: `_BUILDERS` maps display values to
    methods, `_ALIASES` redirects shared shapes (e.g. `histogram`
    renders the same as `bar_chart`). `_TIMESERIES_VIEWS` is the
    one special case — line/area/sparkline share `_build_time_series`
    but pass a `view` argument that the others don't.
    """

    # Direct dispatches — display value → bound method name.
    _BUILDERS: dict[str, str] = {
        "": "_build_list",  # default for missing display
        "list": "_build_list",
        "kanban": "_build_kanban",
        "timeline": "_build_timeline",
        "grid": "_build_grid",
        "metrics": "_build_metrics",
        "bar_chart": "_build_bar_chart",
        "pivot_table": "_build_pivot_table",
        "tabbed_list": "_build_tabbed_list",
        "detail": "_build_detail",
        "funnel_chart": "_build_funnel_chart",
        "status_list": "_build_status_list",
        "tree": "_build_tree",
        "pipeline_steps": "_build_pipeline_steps",
        "progress": "_build_progress",
        "confirm_action_panel": "_build_confirm_action_panel",
        "search_box": "_build_search_box",
        "bar_track": "_build_bar_track",
        "bullet": "_build_bullet",
        "diagram": "_build_diagram",
        "radar": "_build_radar",
        "box_plot": "_build_box_plot",
        "action_grid": "_build_action_grid",
        "profile_card": "_build_profile_card",
        "queue": "_build_queue",
        "activity_feed": "_build_activity_feed",
        "histogram": "_build_histogram",
        "heatmap": "_build_heatmap",
        "cohort_strip": "_build_cohort_strip",  # #1018 (v0.67.7)
        "day_timeline": "_build_day_timeline",  # #1016 (v0.67.8)
        "task_inbox": "_build_task_inbox",  # #1015 (v0.67.8)
        "entity_card": "_build_entity_card",  # #1017 (v0.67.8)
    }

    # Display values that share a builder with another display value.
    # Resolved before _BUILDERS lookup; lets us add an alias without
    # duplicating dispatch code.
    _ALIASES: dict[str, str] = {
        "summary": "metrics",
    }

    # TimeSeries variants — share `_build_time_series` but each passes
    # a different `view` argument. Kept separate from `_BUILDERS` so
    # the table-lookup signature stays uniform.
    _TIMESERIES_VIEWS: dict[str, Literal["line", "area", "sparkline"]] = {
        "line_chart": "line",
        "area_chart": "area",
        "sparkline": "sparkline",
    }

    def build(self, region: Any, ctx: dict[str, Any]) -> Fragment:
        """Dispatch on `region.display` to the right primitive.

        Resolves aliases first, then looks up the canonical builder.
        Adding a new display value is one entry in `_BUILDERS` (or
        `_ALIASES` for a redirect) — no if-chain edits required.
        """
        display_obj = getattr(region, "display", None)
        raw_display = getattr(display_obj, "value", None)
        if raw_display is None:
            raw_display = "" if display_obj is None else str(display_obj)
        display_value = raw_display.strip()

        # TimeSeries family — same builder, different view argument.
        view = self._TIMESERIES_VIEWS.get(display_value)
        if view is not None:
            return self._build_time_series(region, ctx, view)

        # Resolve any alias to its canonical display value.
        canonical = self._ALIASES.get(display_value, display_value)
        method_name = self._BUILDERS.get(canonical)
        if method_name is not None:
            builder: Callable[[Any, dict[str, Any]], Fragment] = getattr(self, method_name)
            return builder(region, ctx)

        raise NotImplementedError(
            f"WorkspaceRegionAdapter does not yet support display={display_value!r}; "
            f"audit `unsupported_display={display_value}` blockers tell you which to "
            f"close next. KanbanBoard, Timeline, KPI, BarChart, PivotTable primitives "
            f"already exist (Plan 1); the work is wiring them here."
        )

    def _build_list(self, region: Any, ctx: dict[str, Any]) -> Surface:
        """`display: list` regions render as a Region(kind=list).

        Phase 4A core: items + columns → Table primitive (basic list).
        Phase 4B.1.e: opt-in chrome — when ctx supplies `endpoint` +
        `region_name`, the adapter composes a Stack of:
          1. FilterBar (when `filter_columns` is present)
          2. DateRangePicker (when `date_range` is True)
          3. CsvExportButton (when `csv_export` is True)
          4. Table with sortable column headers (when `sort_field` is
             tracked in ctx and columns supply `sortable: True`)
          5. CsvExportButton — actually appears in the action row, not
             below; placement is renderer's concern via Stack ordering

        Without chrome ctx, the original simple Table-only behaviour
        is preserved for backward compat with existing tests.

        ctx shape (Phase 4B.1.e additions):
            endpoint: str URL for HTMX-driven chrome (filter bar, sort,
                date range, csv export)
            region_name: str — DOM-id namespace for hx-target
            filter_columns: list of dicts {key, label, options[(value, display)],
                selected} → produces FilterBar
            active_filters: dict[key → value] — currently-selected filters
                (alternative to per-column `selected`)
            date_range: bool — when True, render DateRangePicker
            date_from / date_to: iso-date strings for picker initial values
            csv_export: bool — when True, render CsvExportButton
            sort_field: str — currently-active sort column key
            sort_dir: "asc" | "desc"
            columns[i].sortable: bool — column-level opt-in for sort header
        """

        title = _region_title(region)
        items = ctx.get("items", []) or []
        columns = ctx.get("columns", []) or []

        endpoint = ctx.get("endpoint")
        region_name = str(ctx.get("region_name") or getattr(region, "name", "") or "list")

        # Build chrome elements in declared order.
        chrome_parts: list[Fragment] = []

        # FilterBar — when filter_columns is supplied
        filter_columns_raw = ctx.get("filter_columns") or []
        active_filters = ctx.get("active_filters") or {}
        if endpoint and isinstance(filter_columns_raw, list) and filter_columns_raw:
            cols: list[FilterColumn] = []
            seen: set[str] = set()
            for fc in filter_columns_raw:
                if not isinstance(fc, dict):
                    continue
                key = str(fc.get("key") or "")
                if not key or key in seen:
                    continue
                seen.add(key)
                # Options arrive as either list[str] (legacy) or
                # list[(value, display)] tuples / list[dict].
                raw_options = fc.get("options") or []
                opts: list[tuple[str, str]] = []
                for opt in raw_options:
                    if isinstance(opt, tuple) and len(opt) == 2:
                        opts.append((str(opt[0]), str(opt[1])))
                    elif isinstance(opt, dict):
                        opts.append((str(opt.get("value") or ""), str(opt.get("label") or "")))
                    else:
                        opts.append((str(opt), str(opt)))
                selected = str(
                    fc.get("selected")
                    or (active_filters.get(key) if isinstance(active_filters, dict) else "")
                    or ""
                )
                cols.append(
                    FilterColumn(
                        key=key,
                        label=str(fc.get("label") or key),
                        options=tuple(opts),
                        selected=selected,
                    )
                )
            if cols:
                chrome_parts.append(
                    FilterBar(
                        endpoint=URL(str(endpoint)),
                        region_name=region_name,
                        columns=tuple(cols),
                    )
                )

        # DateRangePicker — when date_range flag is set
        if endpoint and ctx.get("date_range"):
            chrome_parts.append(
                DateRangePicker(
                    endpoint=URL(str(endpoint)),
                    region_name=region_name,
                    date_from=str(ctx.get("date_from") or ""),
                    date_to=str(ctx.get("date_to") or ""),
                )
            )

        # CsvExportButton — when csv_export flag is set
        if endpoint and ctx.get("csv_export"):
            chrome_parts.append(
                CsvExportButton(
                    endpoint=URL(str(endpoint)),
                    filename=str(ctx.get("csv_filename") or f"{region_name}.csv"),
                )
            )

        # Body — ListRegion primitive matching legacy
        # `workspace/regions/list.html` byte-for-byte (Phase 4B.4 wave 2).
        list_columns: list[ListColumn] = []
        list_rows: list[tuple[object, ...]] = []
        for col in columns:
            if not isinstance(col, dict):
                continue
            list_columns.append(
                ListColumn(
                    key=str(col.get("key") or ""),
                    label=str(col.get("label") or col.get("key") or ""),
                )
            )

        for item in items:
            if not isinstance(item, dict):
                continue
            row_cells: list[object] = []
            for col in columns:
                if not isinstance(col, dict):
                    continue
                # Per-cell type-aware rendering via the same helper used
                # by DETAIL/TIMELINE/GRID. LIST passes default badge args
                # (size="md", bordered=False).
                row_cells.append(_render_typed_value(item, col))
            list_rows.append(tuple(row_cells))

        empty_msg = (
            ctx.get("empty_message") or getattr(region, "empty_message", None) or "No items found."
        )
        try:
            total = int(ctx.get("total") or len(list_rows))
        except (TypeError, ValueError):
            total = len(list_rows)

        body: Fragment = ListRegion(
            columns=tuple(list_columns),
            rows=tuple(list_rows),
            csv_endpoint=str(endpoint or ""),
            csv_filename=f"{region_name}.csv",
            total=total,
            empty_message=str(empty_msg),
        )

        # If we have chrome, wrap the body in a Stack that also contains
        # the chrome row(s). The legacy template injects chrome INSIDE
        # the dz-list-region wrapper, so once chrome flows through the
        # ListRegion primitive (follow-up), this Stack wrap can drop.
        if chrome_parts:
            body = Stack(children=(*chrome_parts, body), gap="md")

        return _wrap_surface(title, "list", body)

    def _build_queue(self, region: Any, ctx: dict[str, Any]) -> Surface:
        """`display: queue` regions render as a review queue with inline
        state-transition action buttons.

        Phase 4B.1.d/e — replaces the prior alias to `_build_list`.
        Composes a Stack of:
          1. Total count badge (when total > 0)
          2. Metrics summary tiles (when `metrics` ctx is supplied)
          3. FilterBar / DateRangePicker / CsvExportButton chrome (same
             contract as `_build_list`)
          4. Per-item rows: each item is a Card with main content + a
             Row of transition Buttons (using the extended Button shape
             from v0.66.83 — hx_put + hx_vals + hx_ext)
          5. Overflow text (when `total > len(items)`)

        Note: this is structurally equivalent to the legacy
        `queue.html` but not byte-for-byte (the legacy template uses
        a custom `dz-queue-row` flex layout that the typed-Fragment
        substrate doesn't replicate today). The Phase 4B.3 dual-path
        validation gate will surface this as an accepted divergence
        — the chrome is byte-equivalent, the row interior is not.

        ctx shape (Phase 4B preferred):
            items, columns: same as list
            total: int — full row count for the count badge + overflow
            metrics: list of metric dicts (label, value, etc.)
            endpoint, region_name: HTMX wiring (chrome + transitions)
            filter_columns, active_filters, date_range, csv_export: chrome
            queue_transitions: list of {label, to_state}
            queue_status_field: str — field name carrying current state
            queue_api_endpoint: str URL — base URL for transitions
                (transitions PUT to f"{queue_api_endpoint}/{item.id}")
        """
        from dazzle.ui.runtime.template_renderer import (
            _metric_number_filter,
            _timeago_filter,
        )

        title = _region_title(region)
        items = ctx.get("items", []) or []
        try:
            total = int(ctx.get("total") or 0)
        except (TypeError, ValueError):
            total = 0
        region_name = str(ctx.get("region_name") or getattr(region, "name", "") or "queue")
        queue_status_field = str(ctx.get("queue_status_field") or "")
        queue_api_endpoint = str(ctx.get("queue_api_endpoint") or "")
        display_key = str(ctx.get("display_key") or "")
        columns = ctx.get("columns") or []

        # Metrics row.
        metrics: list[QueueMetric] = []
        for m in ctx.get("metrics") or []:
            if not isinstance(m, dict):
                continue
            label = str(m.get("label") or m.get("name") or "")
            if not label:
                continue
            metrics.append(
                QueueMetric(
                    label=label,
                    value=str(_metric_number_filter(m.get("value"))),
                )
            )

        # Transition definitions (per-region).
        transitions: list[QueueTransition] = []
        for tr in ctx.get("queue_transitions") or []:
            if not isinstance(tr, dict):
                continue
            to_state = str(tr.get("to_state") or "")
            if not to_state:
                continue
            transitions.append(
                QueueTransition(
                    label=str(tr.get("label") or to_state),
                    to_state=to_state,
                )
            )

        # Per-row construction.
        rows: list[QueueRow] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            row_id = str(item.get("id") or "")
            # Title fallback chain mirroring the legacy Jinja:
            #   {% set _display = item[display_key ~ "_display"] %}
            #   {% set _primary = item[display_key] %}
            #   {% if _display is not none %}{{ _display }}{% elif _primary is not none %}{{ _primary }}{% else %}{{ item.id }}{% endif %}
            # Jinja's `dict[missing_key]` returns Undefined (not None);
            # `Undefined is not none` is True and `{{ Undefined }}` renders
            # as empty string. So a MISSING `<display_key>_display` key
            # produces empty title (Undefined-not-None quirk). Present-None
            # falls through to primary; primary missing/None falls to id.
            display_attr = f"{display_key}_display" if display_key else ""
            if display_attr and display_attr not in item:
                row_title = ""
            elif display_attr and item.get(display_attr) is not None:
                row_title = str(item[display_attr])
            elif display_key and item.get(display_key) is not None:
                row_title = str(item[display_key])
            else:
                row_title = row_id

            # Badges = columns with type=="badge" and key != display_key.
            badges: list[QueueBadgeColumn] = []
            for col in columns:
                if not isinstance(col, dict):
                    continue
                key = str(col.get("key") or "")
                if not key or key == display_key:
                    continue
                if col.get("type") == "badge":
                    badges.append(QueueBadgeColumn(key=key, value=item.get(key)))

            # Date secondaries = columns with type=="date" and a non-empty value.
            date_columns: list[QueueDateColumn] = []
            for col in columns:
                if not isinstance(col, dict):
                    continue
                if col.get("type") != "date":
                    continue
                key = str(col.get("key") or "")
                val = item.get(key)
                if not val:
                    continue
                date_columns.append(
                    QueueDateColumn(
                        label=str(col.get("label") or key),
                        timeago_str=_timeago_filter(val),
                    )
                )

            # Attention.
            attn_raw = item.get("_attention") if hasattr(item, "get") else None
            attn_level = ""
            attn_message = ""
            if isinstance(attn_raw, dict):
                attn_level = str(attn_raw.get("level") or "")
                attn_message = str(attn_raw.get("message") or "")

            current_status = str(item.get(queue_status_field) or "") if queue_status_field else ""

            rows.append(
                QueueRow(
                    row_id=row_id,
                    title=row_title,
                    current_status=current_status,
                    badges=tuple(badges),
                    date_columns=tuple(date_columns),
                    attention_level=attn_level,
                    attention_message=attn_message,
                )
            )

        empty_msg = (
            ctx.get("empty_message") or getattr(region, "empty_message", None) or "Queue is empty."
        )
        body: Fragment = QueueRegion(
            rows=tuple(rows),
            total=total,
            metrics=tuple(metrics),
            transitions=tuple(transitions),
            queue_status_field=queue_status_field,
            queue_api_endpoint=queue_api_endpoint,
            region_name=region_name,
            empty_message=str(empty_msg),
        )
        return _wrap_surface(title, "list", body)

    def _build_kanban(self, region: Any, ctx: dict[str, Any]) -> Surface:
        """`display: kanban` regions render as a `KanbanRegion` primitive
        matching `workspace/regions/kanban.html` byte-for-byte.

        Phase 4B.4 wave 4: replaced the simpler `KanbanBoard` primitive
        with the workspace-shaped `KanbanRegion` carrying full per-card
        title + secondary fields + attention tag.

        ctx shape (production runtime):
            items: list of dicts (rows from the source entity)
            kanban_columns: ordered status values (legacy key)
                (alt) group_keys for Phase 4A back-compat
            group_by: str — field name to bucket items by
                (alt) group_by_field for Phase 4A back-compat
            columns: list of column dicts {key, label, type, ref_route}
                — secondary fields rendered per-card (excludes
                display_key and group_by)
            display_key: str — field name for the card title
            entity_name: str — fallback title when display_key is None
            total: int — overflow indicator denominator
            empty_message: optional empty-state fallback
        """
        from dazzle.ui.runtime.template_renderer import _timeago_filter

        title = _region_title(region)
        items: list[dict[str, Any]] = ctx.get("items", []) or []
        # Accept both legacy `kanban_columns`/`group_by` and Phase 4A
        # `group_keys`/`group_by_field` shapes.
        column_keys: list[str] = list(ctx.get("kanban_columns") or ctx.get("group_keys") or [])
        group_by: str = str(ctx.get("group_by") or ctx.get("group_by_field") or "")
        columns_meta = ctx.get("columns") or []
        display_key = str(ctx.get("display_key") or "")
        entity_name = str(ctx.get("entity_name") or "Item")
        try:
            total = int(ctx.get("total") or 0)
        except (TypeError, ValueError):
            total = 0
        endpoint = str(ctx.get("endpoint") or "")

        # Build the per-card secondary-field list once — the same set
        # of meta columns applies to every card.
        meta_columns: list[dict[str, Any]] = []
        for col in columns_meta:
            if not isinstance(col, dict):
                continue
            key = str(col.get("key") or "")
            if not key or key == display_key or key == group_by:
                continue
            meta_columns.append(col)

        def _card_title(item: dict[str, Any]) -> str:
            """Mirror the legacy fallback chain for the card heading."""
            for fallback in ("title", "name", "company_name"):
                v = item.get(fallback)
                if v:
                    return str(v)
            first = str(item.get("first_name", "") or "")
            last = str(item.get("last_name", "") or "")
            joined = f"{first} {last}".strip()
            if joined:
                return joined
            for fallback in ("label", "email"):
                v = item.get(fallback)
                if v:
                    return str(v)
            dk_val = item.get(display_key) if display_key else None
            if dk_val:
                return str(dk_val)
            return entity_name

        kanban_cols: list[KanbanColumn] = []
        if not items and not column_keys:
            body: Fragment = KanbanRegion(
                columns=(),
                empty_message=str(
                    ctx.get("empty_message")
                    or getattr(region, "empty_message", None)
                    or "No items found."
                ),
            )
            return _wrap_surface(title, "kanban", body)

        # Group items by column key.
        buckets: dict[str, list[dict[str, Any]]] = {k: [] for k in column_keys}
        for item in items:
            if not isinstance(item, dict):
                continue
            key = str(item.get(group_by, "") or "")
            buckets.setdefault(key, []).append(item)

        for col_key in column_keys:
            cards: list[KanbanCard] = []
            for item in buckets.get(col_key, []):
                # Per-cell type-aware rendering for secondary fields.
                fields: list[tuple[str, object]] = []
                for col in meta_columns:
                    label = str(col.get("label") or col.get("key") or "")
                    col_type = str(col.get("type") or "")
                    if col_type == "date":
                        # Legacy template does timeago directly on date columns.
                        date_val = item.get(str(col.get("key") or ""))
                        date_str = _timeago_filter(date_val) if date_val else ""
                        from dazzle.render.fragment import RawHTML as _RH

                        fields.append((label, _RH(date_str)))
                    else:
                        # KANBAN renders badges with size='sm' per legacy.
                        fields.append((label, _render_typed_value(item, col, badge_size="sm")))
                attn_raw = item.get("_attention") if hasattr(item, "get") else None
                attn_level = ""
                attn_message = ""
                if isinstance(attn_raw, dict):
                    attn_level = str(attn_raw.get("level") or "")
                    attn_message = str(attn_raw.get("message") or "")
                cards.append(
                    KanbanCard(
                        title=_card_title(item),
                        fields=tuple(fields),
                        attention_level=attn_level,
                        attention_message=attn_message,
                    )
                )
            kanban_cols.append(KanbanColumn(label=col_key, cards=tuple(cards)))

        empty_msg = (
            ctx.get("empty_message") or getattr(region, "empty_message", None) or "No items found."
        )
        body = KanbanRegion(
            columns=tuple(kanban_cols),
            total=total,
            endpoint=endpoint,
            empty_message=str(empty_msg),
        )
        return _wrap_surface(title, "kanban", body)

    def _build_timeline(self, region: Any, ctx: dict[str, Any]) -> Surface:
        """`display: timeline` regions render as a `Timeline` primitive
        matching `workspace/regions/timeline.html` byte-for-byte.

        Phase 4B.4 wave 2: extended to construct rich `TimelineEvent`
        instances carrying per-event date_label (already-formatted via
        `timeago` filter), title (from display_key), and secondary
        fields (per-column type-aware values, omitting the date and
        display_key columns). Click-through (`hx-get` on the content
        div) is not yet plumbed — read-only display only.

        ctx shape:
            items: list of dicts (rows from the source entity)
            columns: list of `{key, label, type, ref_route}` dicts —
                same shape as LIST/DETAIL columns
            display_key: str — column key for the primary title
                (defaults to 'title' / 'name' / 'id' fallback)
            entity_name: str — fallback title when display_key value is None
            total: int — overflow indicator denominator
            empty_message: optional empty-state fallback
        """
        from dazzle.ui.runtime.template_renderer import _timeago_filter

        title = _region_title(region)
        items: list[dict[str, Any]] = ctx.get("items", []) or []
        columns = ctx.get("columns") or []
        display_key = str(ctx.get("display_key") or "")
        entity_name = str(ctx.get("entity_name") or "Event")
        try:
            total = int(ctx.get("total") or 0)
        except (TypeError, ValueError):
            total = 0

        # Identify the date column (first column with type=="date").
        date_col_key = ""
        for col in columns:
            if isinstance(col, dict) and col.get("type") == "date":
                date_col_key = str(col.get("key") or "")
                break

        events: list[TimelineEvent] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            # Date — always rendered via timeago filter for legacy parity.
            date_value = item.get(date_col_key) if date_col_key else None
            date_label = _timeago_filter(date_value) if date_value else ""
            # Title — display_key value, with fallback to name/entity_name.
            primary = item.get(display_key) if display_key else None
            if primary is None:
                primary = item.get("name") or entity_name
            # Secondary fields — every non-date, non-display column.
            fields: list[tuple[str, object]] = []
            for col in columns:
                if not isinstance(col, dict):
                    continue
                key = str(col.get("key") or "")
                if not key or key == display_key or col.get("type") == "date":
                    continue
                label = str(col.get("label") or key)
                # TIMELINE renders badges with `size='sm'` per legacy macro call.
                fields.append((label, _render_typed_value(item, col, badge_size="sm")))
            events.append(
                TimelineEvent(
                    title=str(primary),
                    date_label=date_label,
                    fields=tuple(fields),
                )
            )

        empty_msg = (
            ctx.get("empty_message") or getattr(region, "empty_message", None) or "No events yet."
        )
        body: Fragment = Timeline(events=tuple(events), total=total, empty_message=str(empty_msg))
        return _wrap_surface(title, "report", body)

    def _build_activity_feed(self, region: Any, ctx: dict[str, Any]) -> Surface:
        """`display: activity_feed` regions render as an ActivityFeed
        primitive — chronological feed with per-row dot, time line, and
        bubble carrying actor + description.

        Phase 4B.4 wave 1: dedicated builder (replaced prior alias to
        `_build_timeline`) so the typed-Fragment output matches
        `workspace/regions/activity_feed.html` byte-for-byte. Time
        strings are formatted via the legacy `timeago` filter so both
        paths produce the same relative-time labels.

        ctx shape:
            items: list of dicts with keys:
              - description: action description (required)
              - created_at: datetime (rendered via `timeago` filter)
              - actor or user: optional actor name
              - action / title: fallback description fields
        """
        from dazzle.ui.runtime.template_renderer import _timeago_filter

        title = _region_title(region)
        items: list[dict[str, Any]] = ctx.get("items", []) or []

        body: Fragment
        if not items:
            empty_msg = (
                ctx.get("empty_message")
                or getattr(region, "empty_message", None)
                or "No activity yet"
            )
            body = ActivityFeed(items=(), empty_message=str(empty_msg))
        else:
            rows: list[tuple[str, str, str]] = []
            for item in items:
                if not isinstance(item, dict):
                    continue
                created = item.get("created_at")
                time_str = _timeago_filter(created) if created else ""
                actor_raw = item.get("actor") or item.get("user") or ""
                actor = str(actor_raw) if actor_raw else ""
                description = str(
                    item.get("description") or item.get("action") or item.get("title") or ""
                )
                rows.append((time_str, actor, description))
            body = ActivityFeed(items=tuple(rows))

        return _wrap_surface(title, "report", body)

    def _build_pivot_table(self, region: Any, ctx: dict[str, Any]) -> Surface:
        """`display: pivot_table` regions render as a `PivotTableRegion`
        primitive matching `workspace/regions/pivot_table.html`
        byte-for-byte. Phase 4B.4 wave 4: replaced the simpler
        2-dim PivotTable primitive with the workspace-shape that
        consumes `pivot_buckets` + `pivot_dim_specs` directly.

        ctx shape (production runtime):
            pivot_buckets: list[dict] — one row per dim combination
            pivot_dim_specs: list[{name, label, is_fk}] — dimension columns
            empty_message: optional empty-state fallback
            (legacy alt) rows + columns + cells: 2-dim matrix shape;
              not the production runtime ctx, but kept on a fallback
              path until callers migrate.
        """
        title = _region_title(region)
        raw_buckets = ctx.get("pivot_buckets") or []
        raw_specs = ctx.get("pivot_dim_specs") or []

        # Phase 4A 2-dim fallback: rows + columns + cells.
        if not raw_buckets and (ctx.get("rows") or ctx.get("columns")):
            rows_2d = tuple(str(r) for r in (ctx.get("rows") or []))
            cols_2d = tuple(str(c) for c in (ctx.get("columns") or []))
            raw_cells = ctx.get("cells") or {}
            cells: dict[tuple[str, str], int] = {}
            if isinstance(raw_cells, dict):
                for key, val in raw_cells.items():
                    if isinstance(key, (list, tuple)) and len(key) == 2:
                        r, c = str(key[0]), str(key[1])
                        if r in rows_2d and c in cols_2d:
                            try:
                                cells[(r, c)] = int(val)
                            except (TypeError, ValueError):
                                continue
            chart_label = str(ctx.get("chart_label") or title or "Pivot")
            if rows_2d and cols_2d:
                body: Fragment = PivotTable(
                    label=chart_label,
                    rows=rows_2d,
                    columns=cols_2d,
                    cells=cells,
                )
            else:
                body = EmptyState(
                    title="No data",
                    description=getattr(region, "empty_message", None)
                    or "No row or column dimensions to pivot.",
                )
            return _wrap_surface(title, "report", body)

        # Production path: pivot_buckets + pivot_dim_specs.
        dim_specs: list[PivotDimSpec] = []
        dim_field_names: set[str] = set()
        for spec in raw_specs:
            if not isinstance(spec, dict):
                continue
            name = str(spec.get("name") or "")
            if not name:
                continue
            dim_specs.append(
                PivotDimSpec(
                    name=name,
                    label=str(spec.get("label") or name),
                    is_fk=bool(spec.get("is_fk")),
                )
            )
            dim_field_names.add(name)
            dim_field_names.add(f"{name}_label")

        # Measure keys = ALL first-row keys, NOT filtered. The legacy
        # template intends to filter out dimension fields via an inner
        # `{% set is_dim_field = true %}` mutation inside a nested
        # `{% for spec in pivot_dim_specs %}` loop, but Jinja's set
        # scoping doesn't propagate the mutation out of the inner block,
        # so the filter never applies and EVERY row key (including
        # dim fields like `status`/`severity` and FK label fields like
        # `status_label`) ends up as a measure column. Phase 4B.4 wave
        # 4 (v0.66.116) replicates this scoping bug exactly for
        # byte-equivalence — Jinja-scope quirks of the kind we
        # accumulated in v0.66.106 (pipeline_steps progress) and
        # v0.66.111 (radar tooltip).
        measure_keys: list[str] = []
        if raw_buckets and isinstance(raw_buckets[0], dict):
            measure_keys = [str(k) for k in raw_buckets[0].keys()]

        rows_norm = tuple(b for b in raw_buckets if isinstance(b, dict))

        empty_msg = (
            ctx.get("empty_message")
            or getattr(region, "empty_message", None)
            or "No data to pivot."
        )
        body = PivotTableRegion(
            dim_specs=tuple(dim_specs),
            measure_keys=tuple(measure_keys),
            rows=rows_norm,
            empty_message=str(empty_msg),
        )
        return _wrap_surface(title, "report", body)

    def _build_profile_card(self, region: Any, ctx: dict[str, Any]) -> Surface:
        """`display: profile_card` regions render single-record identity
        panels.

        Phase 4B.1.b — replaces the prior alias to `_build_detail`, which
        rendered a generic key/value Card. The legacy template uses a
        pre-assembled `profile_card_data` dict with avatar/initials/
        primary/secondary/stats/facts; this builder consumes the same
        shape and produces the typed `ProfileCard` primitive.

        ctx shape:
            profile_card_data: dict {
                primary: str (name)
                secondary: str (meta line)
                avatar_url: str
                initials: str
                stats: list[{label, value}]
                facts: list[str]
            }

        Degrades to EmptyState when none of primary/avatar_url/initials
        are populated — matches the legacy template's else branch and
        avoids tripping the strict ProfileCard primitive's invariant.
        """
        title = _region_title(region)
        data = ctx.get("profile_card_data") or {}
        if not isinstance(data, dict):
            data = {}

        primary = str(data.get("primary") or "")
        secondary = str(data.get("secondary") or "")
        avatar_url = str(data.get("avatar_url") or "")
        initials = str(data.get("initials") or "")

        body: Fragment
        if not (primary or avatar_url or initials):
            body = EmptyState(
                title="No profile data",
                description=getattr(region, "empty_message", None) or "No profile data available.",
            )
            return _wrap_surface(title, "dashboard", body)

        # Stats: each entry should be a dict with label + value;
        # silently drop malformed entries so a single bad row doesn't
        # take down the whole panel.
        stats: list[tuple[str, str]] = []
        for entry in data.get("stats") or []:
            if not isinstance(entry, dict):
                continue
            label = str(entry.get("label") or "")
            value = entry.get("value")
            value_str = "" if value is None else str(value)
            if label:
                stats.append((label, value_str))

        # Facts: each entry should be a string.
        facts: list[str] = []
        for entry in data.get("facts") or []:
            text = str(entry or "")
            if text:
                facts.append(text)

        body = ProfileCard(
            primary=primary,
            secondary=secondary,
            avatar_url=avatar_url,
            initials=initials,
            stats=tuple(stats),
            facts=tuple(facts),
        )
        return _wrap_surface(title, "dashboard", body)

    def _build_action_grid(self, region: Any, ctx: dict[str, Any]) -> Surface:
        """`display: action_grid` regions render dashboard CTA cards.

        Phase 4B.1.b — replaces the prior alias to `_build_grid`, which
        rendered plain Card(Text(label)) tiles with no icons, counts,
        tones, or URLs. This builder uses the typed `ActionCard`
        primitive so each card carries the full design contract from the
        legacy template.

        ctx shape:
            action_cards: list of dicts {"label": str, "icon": str (optional),
                "count": int | None, "tone": str (default "neutral"),
                "url": str (optional)}
            (legacy alias: `action_card_data` accepted as alias)
            columns: int (default 3, max 12) for the surrounding Grid

        Cards with empty labels or unknown tones silently drop rather
        than crashing the strict ActionCard primitive.
        """
        title = _region_title(region)
        raw_cards = ctx.get("action_cards") or ctx.get("action_card_data") or []
        columns = int(ctx.get("columns") or 3)
        columns = max(1, min(12, columns))

        cards: list[object] = []
        for entry in raw_cards:
            if not isinstance(entry, dict):
                continue
            label = str(entry.get("label") or "")
            if not label:
                continue
            tone_raw = str(entry.get("tone") or "neutral")
            tone: Literal["neutral", "positive", "warning", "destructive", "accent"] = (
                tone_raw  # type: ignore[assignment]
                if tone_raw in ("neutral", "positive", "warning", "destructive", "accent")
                else "neutral"
            )
            count_raw = entry.get("count")
            count: int | None
            if count_raw is None:
                count = None
            else:
                try:
                    count = int(count_raw)
                except (TypeError, ValueError):
                    count = None
            cards.append(
                ActionCard(
                    label=label,
                    icon=str(entry.get("icon") or ""),
                    count=count,
                    tone=tone,
                    url=str(entry.get("url") or ""),
                )
            )

        empty_msg = getattr(region, "empty_message", None) or "No actions available."
        body: Fragment = ActionGrid(cards=tuple(cards), empty_message=str(empty_msg))
        return _wrap_surface(title, "dashboard", body)

    def _build_cohort_strip(self, region: Any, ctx: dict[str, Any]) -> Surface:
        """`display: cohort_strip` regions render as a horizontal
        member-skim strip with lens toggle (#1018, v0.67.7).

        Reads `region.cohort_strip_config` for the lens definitions
        and active-lens default, plus `ctx` for the data resolution
        upstream (member rows + active lens id + endpoint URL). Pure
        config-to-primitive translation — the row resolution + FK
        join + lens-primary extraction live one layer up in
        `workspace_rendering.py`, which populates the ctx dict.

        ctx shape:
            cohort_cells: list of dicts {"member_id": str, "member_name":
                str, "primary_value": str, "subtitle": str (default ""),
                "avatar_initials": str (default ""), "tone": str
                (default "neutral"), "drill_url": str (default "")}
            cohort_active_lens: id of the lens to mark active. Falls
                back to config.default_lens, then config.lenses[0].id.
            cohort_endpoint: str — the URL the lens-toggle hx-get
                targets. Falls back to ctx["region_url"] then "".
        """
        title = _region_title(region)
        cfg = getattr(region, "cohort_strip_config", None)
        region_name = str(getattr(region, "name", "") or "cohort")

        # Pull config-defined lenses; if no config, render an
        # empty-state surface (defensive: parser should reject this).
        config_lenses = list(getattr(cfg, "lenses", None) or []) if cfg is not None else []
        if not config_lenses:
            return _wrap_surface(
                title,
                "dashboard",
                EmptyState(
                    title="Cohort strip not configured",
                    description="No lenses declared on this region.",
                ),
            )

        # Resolve active lens: explicit ctx → config default → first lens.
        default_lens_id = str(getattr(cfg, "default_lens", "") or "") if cfg is not None else ""
        first_lens_id = str(getattr(config_lenses[0], "id", "") or "")
        active_lens_id = str(ctx.get("cohort_active_lens") or default_lens_id or first_lens_id)
        # If the requested lens isn't in the config, fall back to the
        # first declared lens — defensive against stale URL params.
        known_lens_ids = {str(getattr(lens, "id", "") or "") for lens in config_lenses}
        if active_lens_id not in known_lens_ids:
            active_lens_id = first_lens_id

        lens_tabs: list[CohortStripLensTab] = []
        for lens in config_lenses:
            lens_id = str(getattr(lens, "id", "") or "")
            if not lens_id:
                continue
            lens_tabs.append(
                CohortStripLensTab(
                    id=lens_id,
                    label=str(getattr(lens, "label", "") or lens_id),
                    is_active=(lens_id == active_lens_id),
                )
            )

        # Constructor invariant: exactly one active lens. If our
        # active-id selection produced zero (e.g. all ids empty),
        # promote the first tab.
        if lens_tabs and not any(tab.is_active for tab in lens_tabs):
            head = lens_tabs[0]
            lens_tabs[0] = CohortStripLensTab(id=head.id, label=head.label, is_active=True)

        valid_tones = ("neutral", "good", "warn", "bad")
        cells: list[CohortStripCell] = []
        for entry in ctx.get("cohort_cells") or []:
            if not isinstance(entry, dict):
                continue
            member_id = str(entry.get("member_id") or "")
            if not member_id:
                continue  # primitive's __post_init__ would reject empty id
            tone_raw = str(entry.get("tone") or "neutral")
            tone = tone_raw if tone_raw in valid_tones else "neutral"
            cells.append(
                CohortStripCell(
                    member_id=member_id,
                    member_name=str(entry.get("member_name") or ""),
                    primary_value=str(entry.get("primary_value") or ""),
                    subtitle=str(entry.get("subtitle") or ""),
                    avatar_initials=str(entry.get("avatar_initials") or ""),
                    tone=tone,
                    drill_url=str(entry.get("drill_url") or ""),
                )
            )

        endpoint_str = str(ctx.get("cohort_endpoint") or ctx.get("region_url") or "")
        empty_msg = getattr(region, "empty_message", None) or "No members in this view."

        body: Fragment = CohortStripRegion(
            region_name=region_name,
            endpoint=URL(endpoint_str),
            lenses=tuple(lens_tabs),
            cells=tuple(cells),
            empty_message=str(empty_msg),
        )
        return _wrap_surface(title, "dashboard", body)

    def _build_day_timeline(self, region: Any, ctx: dict[str, Any]) -> Surface:
        """`display: day_timeline` regions render as a vertical
        chronological scroll of slot cards (#1016, v0.67.8).

        Reads `region.day_timeline_config` for the starts_at/ends_at
        field names + composite-card name, plus `ctx` for the resolved
        slots. The data resolution layer compares the now-window
        against each row's [starts_at, ends_at] range to set
        `position` on each slot.

        ctx shape:
            day_timeline_slots: list of dicts {"slot_id": str,
                "label": str, "position": "before"|"active"|"after"
                (default "after"), "body": str (pre-rendered HTML —
                adapter owns escape responsibility), "drill_url":
                str (default "")}.

        At most one slot may carry `position="active"` — the
        primitive enforces this. If the data resolution accidentally
        marks two active, the adapter's _build keeps the first and
        downgrades the rest to "after" rather than crashing.
        """
        title = _region_title(region)
        region_name = str(getattr(region, "name", "") or "day_timeline")
        empty_msg = getattr(region, "empty_message", None) or "No scheduled slots today."

        valid_positions = ("before", "active", "after")
        slots: list[DayTimelineSlot] = []
        active_seen = False
        for entry in ctx.get("day_timeline_slots") or []:
            if not isinstance(entry, dict):
                continue
            slot_id = str(entry.get("slot_id") or "")
            if not slot_id:
                continue
            label = str(entry.get("label") or "")
            position_raw = str(entry.get("position") or "after")
            position = position_raw if position_raw in valid_positions else "after"
            # Defensive: collapse extra "active" rows after the first
            # to "after" so we don't trip the primitive's at-most-one
            # invariant from a buggy upstream resolver.
            if position == "active":
                if active_seen:
                    position = "after"
                else:
                    active_seen = True
            slots.append(
                DayTimelineSlot(
                    slot_id=slot_id,
                    label=label,
                    position=position,  # type: ignore[arg-type]
                    body=str(entry.get("body") or ""),
                    drill_url=str(entry.get("drill_url") or ""),
                )
            )

        body: Fragment = DayTimelineRegion(
            region_name=region_name,
            slots=tuple(slots),
            empty_message=str(empty_msg),
        )
        return _wrap_surface(title, "dashboard", body)

    def _build_task_inbox(self, region: Any, ctx: dict[str, Any]) -> Surface:
        """`display: task_inbox` regions render as a workflow-led
        prioritised list of due actions (#1015, v0.67.8).

        ctx shape:
            task_inbox_items: list of dicts {"item_id": str, "icon":
                str, "title": str, "meta": str (default ""),
                "urgency": "overdue"|"due"|"soon"|"later" (default
                "later"), "drill_url": str (default "")}.
            task_inbox_chips: list of dicts {"chip_id": str, "count":
                int, "label": str, "drill_url": str (default "")} —
                collapsed-summary chips for `count_as` sources.

        The data resolution layer is responsible for resolving
        `as_task` template strings against source rows AND for
        sorting items by the IR's `order` keys (urgency + deadline).
        This adapter just renders the resolved + sorted shape.
        """
        title = _region_title(region)
        region_name = str(getattr(region, "name", "") or "task_inbox")
        empty_msg = getattr(region, "empty_message", None)
        cfg = getattr(region, "task_inbox_config", None)
        # Empty-state copy comes from the IR config when set;
        # region.empty_message overrides if present.
        if empty_msg is None and cfg is not None:
            empty_msg = getattr(cfg, "empty_state", None)
        empty_msg = str(empty_msg or "All caught up.")

        valid_urgencies = ("overdue", "due", "soon", "later")
        items: list[TaskInboxItem] = []
        for entry in ctx.get("task_inbox_items") or []:
            if not isinstance(entry, dict):
                continue
            item_id = str(entry.get("item_id") or "")
            if not item_id:
                continue
            urgency_raw = str(entry.get("urgency") or "later")
            urgency = urgency_raw if urgency_raw in valid_urgencies else "later"
            items.append(
                TaskInboxItem(
                    item_id=item_id,
                    icon=str(entry.get("icon") or ""),
                    title=str(entry.get("title") or ""),
                    meta=str(entry.get("meta") or ""),
                    urgency=urgency,  # type: ignore[arg-type]
                    drill_url=str(entry.get("drill_url") or ""),
                )
            )

        chips: list[TaskInboxSummaryChip] = []
        for entry in ctx.get("task_inbox_chips") or []:
            if not isinstance(entry, dict):
                continue
            chip_id = str(entry.get("chip_id") or "")
            if not chip_id:
                continue
            try:
                count = int(entry.get("count") or 0)
            except (TypeError, ValueError):
                count = 0
            if count < 0:
                count = 0  # primitive rejects negative; defensive coercion
            chips.append(
                TaskInboxSummaryChip(
                    chip_id=chip_id,
                    count=count,
                    label=str(entry.get("label") or ""),
                    drill_url=str(entry.get("drill_url") or ""),
                )
            )

        body: Fragment = TaskInboxRegion(
            region_name=region_name,
            items=tuple(items),
            summary_chips=tuple(chips),
            empty_message=empty_msg,
        )
        return _wrap_surface(title, "dashboard", body)

    def _build_entity_card(self, region: Any, ctx: dict[str, Any]) -> Surface:
        """`display: entity_card` regions render as a composite 360°
        single-entity drill-down (#1017, v0.67.8). Domain-agnostic:
        pupil-360 in MIS, customer-360 in CRM, etc.

        ctx shape:
            entity_card_sections: list of dicts {"section_id": str,
                "label": str, "mode": str (default "halo"), "body":
                str (pre-rendered HTML — adapter owns escape),
                "column": "main"|"sidebar" (default "main"),
                "is_omitted": bool (default False)}.
            entity_card_record_label: optional str for the region's
                heading. Empty string omits the heading.

        The data resolution layer queries each section's source
        independently, applies the mode-specific compact renderer to
        produce `body`, and decides per-section whether to mark
        `is_omitted=True` (optional sections that resolved zero rows).
        """
        title = _region_title(region)
        region_name = str(getattr(region, "name", "") or "entity_card")
        record_label = str(ctx.get("entity_card_record_label") or "")

        valid_modes = (
            "halo",
            "flags",
            "mini_bars",
            "stamps",
            "thread_summary",
            "quick_actions",
        )
        valid_columns = ("main", "sidebar")
        sections: list[EntityCardSection] = []
        for entry in ctx.get("entity_card_sections") or []:
            if not isinstance(entry, dict):
                continue
            section_id = str(entry.get("section_id") or "")
            if not section_id:
                continue
            mode_raw = str(entry.get("mode") or "halo")
            mode = mode_raw if mode_raw in valid_modes else "halo"
            column_raw = str(entry.get("column") or "main")
            column = column_raw if column_raw in valid_columns else "main"
            sections.append(
                EntityCardSection(
                    section_id=section_id,
                    label=str(entry.get("label") or ""),
                    mode=mode,  # type: ignore[arg-type]
                    body=str(entry.get("body") or ""),
                    column=column,  # type: ignore[arg-type]
                    is_omitted=bool(entry.get("is_omitted") or False),
                )
            )

        body: Fragment = EntityCardRegion(
            region_name=region_name,
            sections=tuple(sections),
            record_label=record_label,
        )
        return _wrap_surface(title, "dashboard", body)

    def _build_radar(self, region: Any, ctx: dict[str, Any]) -> Surface:
        """`display: radar` regions render as a Radar polar profile.

        ctx shape:
            axes: list of (label, value) tuples or {axis, value} dicts
            chart_label: optional override
        """
        title = _region_title(region)
        chart_label = str(ctx.get("chart_label") or title or "Radar")
        raw_axes = ctx.get("axes") or []
        axes: list[tuple[str, float]] = []
        for entry in raw_axes:
            if isinstance(entry, (list, tuple)) and len(entry) >= 2:
                try:
                    axes.append((str(entry[0]), float(entry[1])))
                except (TypeError, ValueError):
                    continue
            elif isinstance(entry, dict):
                label = str(entry.get("axis") or entry.get("label") or "")
                try:
                    val = float(entry.get("value") or 0)
                except (TypeError, ValueError):
                    val = 0.0
                if label:
                    axes.append((label, val))

        body: Fragment
        # Radar primitive requires ≥3 axes; fewer collapses to a line.
        # Adapter degrades to EmptyState rather than crashing.
        if len(axes) < 3:
            body = EmptyState(
                title="No data",
                description=getattr(region, "empty_message", None)
                or "Radar requires at least 3 axes.",
            )
        else:
            body = Radar(label=chart_label, axes=tuple(axes))

        return _wrap_surface(title, "report", body)

    def _build_box_plot(self, region: Any, ctx: dict[str, Any]) -> Surface:
        """`display: box_plot` regions render as a BoxPlot quartile table.

        ctx shape:
            groups: list of dicts {"label": str, "min": float, "q1": float,
                                   "median": float, "q3": float, "max": float}
                or 6-tuples (label, min, q1, median, q3, max)
            chart_label: optional override
        """
        title = _region_title(region)
        chart_label = str(ctx.get("chart_label") or title or "Distribution")
        raw_groups = ctx.get("groups") or []
        groups: list[tuple[str, float, float, float, float, float]] = []
        # Phase 4B.4 wave 2: thread per-group sample counts through to
        # the primitive when supplied (legacy `box_plot_stats[i].n`),
        # so the renderer can match the legacy `n=N` tooltip suffix.
        samples: list[int] = []
        any_sample = False
        for entry in raw_groups:
            label = ""
            mn = q1 = med = q3 = mx = 0.0
            n_value = 0
            n_present = False
            if isinstance(entry, (list, tuple)) and len(entry) == 6:
                try:
                    label = str(entry[0])
                    mn, q1, med, q3, mx = (float(v) for v in entry[1:6])
                except (TypeError, ValueError):
                    continue
            elif isinstance(entry, dict):
                label = str(entry.get("label") or "")
                try:
                    mn = float(entry.get("min") or 0)
                    q1 = float(entry.get("q1") or 0)
                    med = float(entry.get("median") or 0)
                    q3 = float(entry.get("q3") or 0)
                    mx = float(entry.get("max") or 0)
                except (TypeError, ValueError):
                    continue
                if "n" in entry:
                    try:
                        n_value = int(entry.get("n") or 0)
                        n_present = True
                    except (TypeError, ValueError):
                        n_present = False
            else:
                continue
            # Drop groups with non-monotonic quartiles — BoxPlot's
            # __post_init__ would raise; the adapter is permissive.
            if label and mn <= q1 <= med <= q3 <= mx:
                groups.append((label, mn, q1, med, q3, mx))
                samples.append(n_value if n_present else 0)
                if n_present:
                    any_sample = True

        body: Fragment
        if not groups:
            body = EmptyState(
                title="No data",
                description=getattr(region, "empty_message", None)
                or "No box-plot groups to render.",
            )
        else:
            body = BoxPlot(
                label=chart_label,
                groups=tuple(groups),
                samples=tuple(samples) if any_sample else (),
                reference_lines=_parse_reference_lines(ctx.get("reference_lines")),
                reference_bands=_parse_reference_bands(ctx.get("reference_bands")),
            )

        return _wrap_surface(title, "report", body)

    def _build_time_series(
        self,
        region: Any,
        ctx: dict[str, Any],
        view: Literal["line", "area", "sparkline"],
    ) -> Surface:
        """Render a TimeSeries primitive (line / area / sparkline).

        ctx shape:
            points: list of (label, value) tuples or {label, value} /
                {x, y} dicts — pre-aggregated by the runtime
            chart_label: optional override
            reference_lines: list of dicts {value, label, style} — Phase
                4B.1.b. Style is one of solid/dashed/dotted; unknown
                styles fall back to solid.
            reference_bands: list of dicts {from, to, label, color}.
                `color` is one of target/positive/warning/destructive/
                muted; unknown colors fall back to target. Bands with
                from > to silently drop.
        """
        title = _region_title(region)
        chart_label = str(ctx.get("chart_label") or title or view.title())
        raw_points = ctx.get("points") or []
        points: list[tuple[str, float]] = []
        for entry in raw_points:
            if isinstance(entry, (list, tuple)) and len(entry) >= 2:
                try:
                    points.append((str(entry[0]), float(entry[1])))
                except (TypeError, ValueError):
                    continue
            elif isinstance(entry, dict):
                label = str(entry.get("label") or entry.get("x") or "")
                try:
                    val = float(entry.get("value") or entry.get("y") or 0)
                except (TypeError, ValueError):
                    val = 0.0
                if label:
                    points.append((label, val))

        body: Fragment

        # Sparkline is a structurally distinct shape (180×32 viewBox,
        # headline + tiny SVG, no axis labels, no reference overlays);
        # Phase 4B.4 wave 2 routes it to a dedicated `Sparkline`
        # primitive rather than overloading TimeSeries' SVG output.
        if view == "sparkline":
            empty_msg = ctx.get("empty_message") or getattr(region, "empty_message", None) or "—"
            body = Sparkline(points=tuple(points), empty_message=str(empty_msg))
            return _wrap_surface(title, "report", body)

        if not points:
            body = EmptyState(
                title="No data",
                description=getattr(region, "empty_message", None) or "No points to plot.",
            )
            return _wrap_surface(title, "report", body)

        ref_lines = _parse_reference_lines(ctx.get("reference_lines"))
        ref_bands = _parse_reference_bands(ctx.get("reference_bands"))

        body = TimeSeries(
            label=chart_label,
            points=tuple(points),
            view=view,
            reference_lines=ref_lines,
            reference_bands=ref_bands,
        )
        return _wrap_surface(title, "report", body)

    def _build_diagram(self, region: Any, ctx: dict[str, Any]) -> Surface:
        """`display: diagram` renders an entity-relationship diagram via
        the Diagram primitive.

        Phase 4B preferred: `ctx['diagram_data']` carries Mermaid syntax
        produced by `_build_diagram_data` in the workspace renderer; we
        forward it as `Diagram.mermaid_source` and the renderer emits
        a `<pre class="mermaid">` + Mermaid CDN loader script matching
        the legacy `workspace/regions/diagram.html` byte-for-byte.

        Phase 4A fallback (no `diagram_data`): construct a structural
        node/edge list from `ctx['nodes']` + `ctx['edges']`. Used by
        tests + any consumer that hasn't built a Mermaid source.
        """
        title = _region_title(region)
        mermaid_source = str(ctx.get("diagram_data") or "")
        # Legacy template hardcodes the empty-state copy — match it
        # verbatim for byte-equivalence rather than reading
        # region.empty_message.
        empty_message = "No entity relationships to display."

        if mermaid_source:
            body: Fragment = Diagram(mermaid_source=mermaid_source)
            return _wrap_surface(title, "report", body)

        nodes = tuple(str(n) for n in (ctx.get("nodes") or []) if n)
        if not nodes:
            # Empty branch matches the legacy template's literal markup
            # (`<p class="dz-diagram-empty">…</p>`) for byte-equivalence;
            # the generic dz-empty-state primitive emits different chrome.
            empty_html = f'<p class="dz-diagram-empty">{_html_escape(empty_message)}</p>'
            return _wrap_surface(title, "report", RawHTML(empty_html))

        raw_edges = ctx.get("edges") or ctx.get("relations") or []
        edges: list[tuple[str, str]] = []
        node_set = set(nodes)
        for entry in raw_edges:
            src: str = ""
            dst: str = ""
            if isinstance(entry, (list, tuple)) and len(entry) >= 2:
                src, dst = str(entry[0]), str(entry[1])
            elif isinstance(entry, dict):
                src = str(entry.get("from") or entry.get("source") or "")
                dst = str(entry.get("to") or entry.get("target") or "")
            if src and dst and src in node_set and dst in node_set:
                edges.append((src, dst))

        return _wrap_surface(title, "report", Diagram(nodes=nodes, edges=tuple(edges)))

    def _build_confirm_action_panel(self, region: Any, ctx: dict[str, Any]) -> Surface:
        """`display: confirm_action_panel` renders a `ConfirmGate`
        primitive — three-state consent panel matching the legacy
        `workspace/regions/confirm_action_panel.html` byte-for-byte.

        Phase 4B.1.d — replaces the prior placeholder rendering (Card
        + Heading + bracketed action label). The ConfirmGate primitive
        carries the full state machine (off/pending/draft, live,
        revoked) plus the checklist with Alpine `dzConfirmGate`
        gating + dual button + audit footer.

        ctx shape (Phase 4B preferred):
            state_value: str — entity field value (resolved at request
                time); branches to live / revoked / off rendering
            confirmations: list of dicts {title, caption?, required?}
            primary_action_url: str (commit / re-enable URL)
            secondary_action_url: str ("Save as draft" URL)
            revoke_url: str (live-state revoke URL)
            audit_enabled: bool (entity has `audit:` block)

        ctx shape (Phase 4A fallback):
            prompt / description / message + action_label — produces
            a minimal ConfirmGate with `state="off"` and the prompt
            text wired into a synthetic single-item checklist. Mainly
            for tests; runtime should use the preferred shape.
        """
        title = _region_title(region)

        # Phase 4B preferred: full state machine
        state = str(ctx.get("state_value") or "off")
        primary_url = str(ctx.get("primary_action_url") or "")
        secondary_url = str(ctx.get("secondary_action_url") or "")
        revoke_url = str(ctx.get("revoke_url") or "")
        audit_enabled = bool(ctx.get("audit_enabled"))

        confirmations: list[ConfirmCheckItem] = []
        for entry in ctx.get("confirmations") or []:
            if not isinstance(entry, dict):
                continue
            entry_title = str(entry.get("title") or "")
            if not entry_title:
                continue
            confirmations.append(
                ConfirmCheckItem(
                    title=entry_title,
                    caption=str(entry.get("caption") or ""),
                    required=bool(entry.get("required")),
                )
            )

        # Phase 4A fallback: synthesise from prompt + action_label
        if (
            not confirmations
            and not primary_url
            and not revoke_url
            and (ctx.get("prompt") or ctx.get("description") or ctx.get("message"))
        ):
            prompt = str(ctx.get("prompt") or ctx.get("description") or ctx.get("message") or "")
            action_label = str(ctx.get("action_label") or "")
            if prompt:
                confirmations.append(ConfirmCheckItem(title=prompt, required=False))
            if action_label:
                # Encode the action label as a synthetic primary URL hint —
                # keeps the rendered panel non-empty without a real action.
                primary_url = primary_url or "#"

        body: Fragment = ConfirmGate(
            state=state,
            confirmations=tuple(confirmations),
            primary_action_url=primary_url,
            secondary_action_url=secondary_url,
            revoke_url=revoke_url,
            audit_enabled=audit_enabled,
            primary_label=str(ctx.get("primary_label") or "Confirm and enable"),
            secondary_label=str(ctx.get("secondary_label") or "Save as draft"),
        )
        return _wrap_surface(title or "Confirm", "dashboard", body)

    def _build_search_box(self, region: Any, ctx: dict[str, Any]) -> Surface:
        """`display: search_box` renders a `SearchBox` primitive — HTMX
        FTS input + lazy-loaded results panel + Alpine coaching toggle.

        Phase 4B.1.d — replaces the prior plain-`Field` rendering, which
        had no HTMX wiring, no result panel, and no coaching message.
        Now byte-equivalent to the legacy `workspace/regions/search_box.html`.

        ctx shape (Phase 4B preferred):
            source_entity: str — entity name for the FTS endpoint URL
                (e.g. "Manuscript" → /api/fts/Manuscript?html=1)
            name: optional results-id slug; defaults to region.name
            placeholder: optional input placeholder
            display_field: optional (for documentation; the endpoint owns
                result-row rendering)
            coaching_message: optional pre-translated string shown until
                the user types (default "Type to search")

        ctx shape (Phase 4A fallback):
            placeholder + label only — produces a SearchBox with a
            self-referential endpoint (`/api/fts/{region.name}?html=1`)
            so existing tests don't crash. The runtime should always
            supply `source_entity` ahead of the Phase 4B.2 translator.
        """
        title = _region_title(region)
        source_entity = str(ctx.get("source_entity") or "")
        name = str(ctx.get("name") or getattr(region, "name", "") or "searchbox")
        placeholder = str(ctx.get("placeholder") or "Search…")
        coaching = str(ctx.get("coaching_message") or "Type to search")
        label = str(ctx.get("label") or title or placeholder)

        if source_entity:
            endpoint = URL(f"/api/fts/{source_entity}?html=1")
        else:
            # Fallback: use the region's own name as the entity hint.
            # Mainly for tests; runtime will supply source_entity.
            endpoint = URL(f"/api/fts/{name}?html=1")

        body: Fragment = SearchBox(
            name=name,
            fts_endpoint=endpoint,
            placeholder=placeholder,
            coaching_message=coaching,
            label=label,
        )
        return _wrap_surface(title, "form", body)

    def _build_bar_track(self, region: Any, ctx: dict[str, Any]) -> Surface:
        """`display: bar_track` renders one labelled, filled track per
        row with ARIA progressbar semantics + a summary line. Phase
        4B.1.b — uses the typed `BarTrack` primitive (replaced the
        prior alias to `_build_progress` which produced the simpler
        Stack-of-Row(Text, Badge) shape).

        ctx shape:
            bar_track_rows: list of dicts {"label": str, "value": float,
                "formatted_value": str, "fill_pct": float (0..100)}
                — pre-computed by the runtime per `track_format` Python
                format spec
            bar_track_max: float — scale endpoint for aria-valuemax
                + summary line
            (legacy fallback) `items` with `{label, percent}` shape from
                Phase 4A is still accepted; `formatted_value` is filled
                in as `"<percent>%"`, `value` mirrors `percent`,
                `bar_track_max` defaults to 100.

        Empty rows degrade to EmptyState; rows with malformed shapes or
        out-of-range fill_pct silently drop rather than tripping the
        BarTrack primitive's invariants.
        """
        title = _region_title(region)
        raw_rows = ctx.get("bar_track_rows") or []
        max_value: float
        try:
            max_value = float(ctx.get("bar_track_max") or 100.0)
        except (TypeError, ValueError):
            max_value = 100.0
        if max_value <= 0:
            max_value = 100.0

        rows: list[tuple[str, float, str, float]] = []
        # Primary path — pre-computed bar_track_rows from the runtime
        for entry in raw_rows:
            if not isinstance(entry, dict):
                continue
            label = str(entry.get("label") or "")
            if not label:
                continue
            try:
                value = float(entry.get("value") or 0)
                fill_pct = float(entry.get("fill_pct") or 0)
            except (TypeError, ValueError):
                continue
            fill_pct = max(0.0, min(100.0, fill_pct))
            formatted = str(entry.get("formatted_value") or value)
            rows.append((label, value, formatted, fill_pct))

        # Legacy fallback — Phase 4A `items` with `{label, percent}` shape
        if not rows:
            for entry in ctx.get("items") or []:
                if not isinstance(entry, dict):
                    continue
                label = str(entry.get("label") or entry.get("name") or "")
                if not label:
                    continue
                try:
                    percent = float(entry.get("percent") or entry.get("value") or 0)
                except (TypeError, ValueError):
                    percent = 0.0
                percent = max(0.0, min(100.0, percent))
                rows.append((label, percent, f"{percent:g}%", percent))

        body: Fragment
        if not rows:
            body = EmptyState(
                title="No data",
                description=getattr(region, "empty_message", None) or "No data available.",
            )
        else:
            body = BarTrack(
                rows=tuple(rows),
                max_value=max_value,
                reference_lines=_parse_reference_lines(ctx.get("reference_lines")),
                reference_bands=_parse_reference_bands(ctx.get("reference_bands")),
            )

        return _wrap_surface(title, "report", body)

    def _build_bullet(self, region: Any, ctx: dict[str, Any]) -> Surface:
        """`display: bullet` renders Stephen Few bullet rows — label +
        track (bands behind, actual bar, optional target tick) +
        formatted value. Phase 4B.4 wave 2: dedicated `Bullet` primitive
        replaces prior Stack+Row+Badge composition for byte-equivalence
        with `workspace/regions/bullet.html`.

        ctx shape (primary):
            bullet_rows: list of dicts {label, actual, target}
            bullet_max_value: float — denominator for percentage scale
            reference_bands: optional list[dict] for comparative zones
            empty_message: optional empty-state fallback
        """
        title = _region_title(region)
        raw_rows = ctx.get("bullet_rows") or []
        try:
            max_value = float(ctx.get("bullet_max_value") or 0)
        except (TypeError, ValueError):
            max_value = 0.0

        rows: list[BulletRow] = []
        if isinstance(raw_rows, list):
            for entry in raw_rows:
                if not isinstance(entry, dict):
                    continue
                label = str(entry.get("label") or entry.get("name") or "")
                if not label:
                    continue
                try:
                    actual = float(entry.get("actual", 0))
                except (TypeError, ValueError):
                    continue
                target_raw = entry.get("target")
                target: float | None = None
                if target_raw is not None:
                    try:
                        target = float(target_raw)
                    except (TypeError, ValueError):
                        target = None
                rows.append(BulletRow(label=label, actual=actual, target=target))

        empty_msg = (
            ctx.get("empty_message")
            or getattr(region, "empty_message", None)
            or "No data available."
        )
        body: Fragment = Bullet(
            rows=tuple(rows),
            max_value=max_value if rows else 1.0,  # invariant guard for empty
            reference_bands=_parse_reference_bands(ctx.get("reference_bands")),
            empty_message=str(empty_msg),
        )
        return _wrap_surface(title, "report", body)

    def _build_tree(self, region: Any, ctx: dict[str, Any]) -> Surface:
        """`display: tree` regions render a recursive hierarchy as
        nested `<details>` nodes. Phase 4B.4 wave 2: dedicated
        `Tree` primitive replacing prior Stack-of-Text composition for
        byte-equivalence with `workspace/regions/tree.html`.

        ctx shape (primary):
            tree_items: list of nested dicts with `_children` (legacy
                key) or `children` (typed-path) lists holding child
                nodes with the same shape; each node carries a label
                under `display_key`, `name`, or `title`.
            display_key: optional field name to pull label from
                (defaults to "name"/"title" auto-pick)
            (legacy) `items` flat list as fallback
        """
        title = _region_title(region)
        raw = ctx.get("tree_items") or ctx.get("items") or []
        label_field = str(ctx.get("display_key") or ctx.get("label_field") or "")

        def _walk(node_list: list[Any]) -> tuple[TreeNode, ...]:
            out: list[TreeNode] = []
            for node in node_list:
                if not isinstance(node, dict):
                    continue
                label = _pick_label(node, label_field) or "(no label)"
                # Accept both legacy `_children` and typed `children`.
                children_raw = node.get("_children") or node.get("children") or []
                children = _walk(children_raw) if isinstance(children_raw, list) else ()
                out.append(TreeNode(label=label, children=children))
            return tuple(out)

        nodes = _walk(raw) if isinstance(raw, list) else ()

        body: Fragment
        if not nodes:
            body = EmptyState(
                title="No items",
                description=getattr(region, "empty_message", None) or "No data in this region.",
            )
        else:
            body = Tree(nodes=nodes)

        return _wrap_surface(title, "list", body)

    def _build_pipeline_steps(self, region: Any, ctx: dict[str, Any]) -> Surface:
        """`display: pipeline_steps` renders a horizontal row of stage
        cards with arrow connectors. Phase 4B.4 wave 2: dedicated
        `PipelineSteps` primitive replacing prior Card+Stack composition
        for byte-equivalence with `workspace/regions/pipeline_steps.html`.

        ctx shape (primary):
            pipeline_stage_data: list of dicts {label, value, caption,
                progress, progress_overshoot}
            empty_message: optional empty-state fallback
        """
        title = _region_title(region)
        raw_stages = ctx.get("pipeline_stage_data") or []

        stages: list[PipelineStage] = []
        if isinstance(raw_stages, list):
            for entry in raw_stages:
                if not isinstance(entry, dict):
                    continue
                label = str(entry.get("label") or entry.get("name") or "")
                if not label:
                    continue
                # value: None preserved (renders as "—"); coerce to int else.
                value: int | None
                value_raw = entry.get("value")
                if value_raw is None:
                    value = None
                else:
                    try:
                        value = int(value_raw)
                    except (TypeError, ValueError):
                        value = None
                # progress: None preserved (omits the bar); coerce to int else.
                progress: int | None
                progress_raw = entry.get("progress")
                if progress_raw is None:
                    progress = None
                else:
                    try:
                        progress = int(progress_raw)
                    except (TypeError, ValueError):
                        progress = None
                stages.append(
                    PipelineStage(
                        label=label,
                        value=value,
                        caption=str(entry.get("caption") or ""),
                        progress=progress,
                        progress_overshoot=bool(entry.get("progress_overshoot")),
                    )
                )

        empty_msg = (
            ctx.get("empty_message")
            or getattr(region, "empty_message", None)
            or "No pipeline data available."
        )
        body: Fragment = PipelineSteps(stages=tuple(stages), empty_message=str(empty_msg))
        return _wrap_surface(title, "dashboard", body)

    def _build_progress(self, region: Any, ctx: dict[str, Any]) -> Surface:
        """`display: progress` renders a `<progress>` header + chip list
        of stages. Phase 4B.1.b uses the typed StageBar primitive
        matching the legacy `workspace/regions/progress.html` shape.

        ctx shape (primary):
            stage_counts: list of dicts {"name": str, "count": int,
                "complete": bool} — pre-computed per-stage rollups
            complete_pct: float (0..100) — percentage for the header bar
            complete_count: int — for the "N of M complete" summary
            progress_total: int — denominator for the summary; 0 omits it

        ctx shape (legacy fallback, Phase 4A):
            items: list of dicts {"label": str, "percent": int 0..100}
                — fallback-rendered as one synthetic stage per row with
                `complete = (percent == 100)`. The Phase 4B.2 translator
                will replace this with the primary path.
        """
        title = _region_title(region)
        stage_counts = ctx.get("stage_counts") or []

        stages: list[tuple[str, int, bool]] = []
        for entry in stage_counts:
            if not isinstance(entry, dict):
                continue
            name = str(entry.get("name") or entry.get("label") or "")
            if not name:
                continue
            try:
                count = int(entry.get("count") or 0)
            except (TypeError, ValueError):
                count = 0
            complete = bool(entry.get("complete"))
            stages.append((name, count, complete))

        # Legacy fallback — items: [{label, percent}]
        if not stages:
            for entry in ctx.get("items") or []:
                if not isinstance(entry, dict):
                    continue
                name = str(entry.get("label") or entry.get("name") or "")
                if not name:
                    continue
                try:
                    percent = int(entry.get("percent") or entry.get("value") or 0)
                except (TypeError, ValueError):
                    percent = 0
                percent = max(0, min(100, percent))
                stages.append((f"{name} ({percent}%)", percent, percent == 100))

        body: Fragment
        if not stages:
            body = EmptyState(
                title="No progress",
                description=getattr(region, "empty_message", None) or "No data in this region.",
            )
            return _wrap_surface(title, "list", body)

        try:
            complete_pct = float(ctx.get("complete_pct") or 0)
        except (TypeError, ValueError):
            complete_pct = 0.0
        complete_pct = max(0.0, min(100.0, complete_pct))
        try:
            complete_count = int(ctx.get("complete_count") or 0)
        except (TypeError, ValueError):
            complete_count = 0
        try:
            total = int(ctx.get("progress_total") or 0)
        except (TypeError, ValueError):
            total = 0

        body = StageBar(
            stages=tuple(stages),
            complete_pct=complete_pct,
            complete_count=complete_count,
            total=total,
        )
        return _wrap_surface(title, "list", body)

    def _build_status_list(self, region: Any, ctx: dict[str, Any]) -> Surface:
        """`display: status_list` regions render as a `StatusList`
        primitive — vertical list of icon + title + caption + state-pill
        rows. Phase 4B.4 wave 1: dedicated primitive replacing the prior
        Stack+Row+Badge composition for byte-equivalence with
        `workspace/regions/status_list.html`.

        ctx shape:
            status_entries: list of dicts with keys
                title (required), state, caption, icon
            empty_message: optional override for the empty-state line
            (legacy items + label_field + status_field shape is no
             longer the primary path — the runtime supplies authored
             `status_entries` per the v0.61.69 design)
        """
        title = _region_title(region)
        raw_entries = ctx.get("status_entries") or []
        entries: list[StatusListEntry] = []
        for raw in raw_entries:
            if not isinstance(raw, dict):
                continue
            entry_title = str(raw.get("title") or "")
            if not entry_title:
                continue
            state_raw = str(raw.get("state") or "neutral") or "neutral"
            state: Literal["neutral", "positive", "warning", "destructive", "accent"] = (
                state_raw  # type: ignore[assignment]
                if state_raw in ("neutral", "positive", "warning", "destructive", "accent")
                else "neutral"
            )
            entries.append(
                StatusListEntry(
                    title=entry_title,
                    state=state,
                    caption=str(raw.get("caption") or ""),
                    icon=str(raw.get("icon") or ""),
                )
            )

        empty_msg = (
            ctx.get("empty_message")
            or getattr(region, "empty_message", None)
            or "No status entries."
        )
        body: Fragment = StatusList(entries=tuple(entries), empty_message=str(empty_msg))
        return _wrap_surface(title, "list", body)

    def _build_funnel_chart(self, region: Any, ctx: dict[str, Any]) -> Surface:
        """`display: funnel_chart` regions render as a `Funnel` primitive.

        Phase 4B.4 wave 3: dedicated builder (replaces prior bar_chart
        routing) for byte-equivalence with `workspace/regions/funnel_chart.html`.
        Width is calculated relative to the FIRST stage's count (not max),
        and clamped to a 20% minimum. Stages are ordered as supplied —
        funnel rendering preserves the declared kanban_columns order.

        ctx shape (production runtime):
            kanban_columns: ordered list of stage keys
            items: source rows (counted per stage via group_by)
            group_by: field name on each item carrying the stage value
            total: pre-computed total item count
            (legacy alt) buckets: pre-sorted [(label, count)] tuples
            (legacy alt) metrics: list[{label, value}] fallback
            empty_message: optional empty-state fallback
        """
        title = _region_title(region)
        items = ctx.get("items") or []
        kanban_columns = ctx.get("kanban_columns") or []
        group_by = ctx.get("group_by")
        try:
            total = int(ctx.get("total") or 0)
        except (TypeError, ValueError):
            total = 0

        stages: list[FunnelStage] = []
        if kanban_columns and items and group_by:
            counts: dict[str, int] = {str(s): 0 for s in kanban_columns}
            for item in items:
                if isinstance(item, dict):
                    key = str(item.get(group_by) or "Unknown")
                    if key in counts:
                        counts[key] += 1
            for stage in kanban_columns:
                key = str(stage)
                stages.append(FunnelStage(label=key, count=counts.get(key, 0)))
        else:
            # Legacy fallbacks: pre-sorted buckets, or metrics list.
            for entry in ctx.get("buckets") or []:
                if isinstance(entry, (list, tuple)) and len(entry) >= 2:
                    try:
                        stages.append(FunnelStage(label=str(entry[0]), count=int(entry[1])))
                    except (TypeError, ValueError):
                        continue
            if not stages:
                for m in ctx.get("metrics") or []:
                    if isinstance(m, dict):
                        try:
                            stages.append(
                                FunnelStage(
                                    label=str(m.get("label") or ""),
                                    count=int(m.get("value") or 0),
                                )
                            )
                        except (TypeError, ValueError):
                            continue

        empty_msg = (
            ctx.get("empty_message")
            or getattr(region, "empty_message", None)
            or "No data available."
        )
        body: Fragment = Funnel(
            stages=tuple(stages),
            total=total,
            empty_message=str(empty_msg),
        )
        return _wrap_surface(title, "report", body)

    def _build_histogram(self, region: Any, ctx: dict[str, Any]) -> Surface:
        """`display: histogram` regions render as a `Histogram` primitive
        — continuous-axis SVG bar chart with optional vertical reference
        lines. Phase 4B.4 wave 3: dedicated builder (replaces prior alias
        to `_build_bar_chart`) for byte-equivalence with
        `workspace/regions/histogram.html`.

        ctx shape:
            histogram_bins: list of `{label, count, low, high}` dicts —
                pre-computed by the runtime's `_compute_histogram_bins`
                from the already-fetched items
            reference_lines: optional list of `{value, label, style}`
                dicts (vertical overlays at x-position)
            empty_message: optional empty-state fallback
        """
        title = _region_title(region)
        chart_label = str(ctx.get("chart_label") or title or "Histogram")
        raw_bins = ctx.get("histogram_bins") or []

        bins: list[HistogramBin] = []
        for entry in raw_bins:
            if not isinstance(entry, dict):
                continue
            label = str(entry.get("label") or "")
            if not label:
                continue
            try:
                count = int(entry.get("count") or 0)
                low = float(entry.get("low", 0))
                high = float(entry.get("high", 0))
            except (TypeError, ValueError):
                continue
            bins.append(HistogramBin(label=label, count=count, low=low, high=high))

        empty_msg = (
            ctx.get("empty_message")
            or getattr(region, "empty_message", None)
            or "No data available."
        )
        body: Fragment = Histogram(
            label=chart_label,
            bins=tuple(bins),
            reference_lines=_parse_reference_lines(ctx.get("reference_lines")),
            empty_message=str(empty_msg),
        )
        return _wrap_surface(title, "report", body)

    def _build_heatmap(self, region: Any, ctx: dict[str, Any]) -> Surface:
        """`display: heatmap` regions render as a `Heatmap` primitive
        — threshold-tinted matrix matching `workspace/regions/heatmap.html`
        byte-for-byte. Phase 4B.4 wave 4: dedicated builder (replaces
        alias to pivot_table).

        ctx shape (production runtime):
            heatmap_matrix: list of dicts {row, row_id, cells:[{col, value}]}
            heatmap_col_values: ordered list of column labels
            heatmap_thresholds: 0/1/2 ascending floats for tone bands
            total: int — overflow indicator denominator
            items: list — for total > items.length overflow check
            empty_message: optional empty-state fallback
        """
        title = _region_title(region)
        matrix = ctx.get("heatmap_matrix") or []
        col_values = ctx.get("heatmap_col_values") or []
        thresholds_raw = ctx.get("heatmap_thresholds") or []
        try:
            total = int(ctx.get("total") or 0)
        except (TypeError, ValueError):
            total = 0
        # Legacy template's overflow check is `total > items|length`,
        # not `total > rows|length` — but typically items==rows count.
        items = ctx.get("items") or []
        if total < len(items):
            total = len(items)

        thresholds: list[float] = []
        for t in thresholds_raw:
            try:
                thresholds.append(float(t))
            except (TypeError, ValueError):
                continue

        rows: list[HeatmapRow] = []
        for row_dict in matrix:
            if not isinstance(row_dict, dict):
                continue
            row_label = str(row_dict.get("row") or "")
            cells_raw = row_dict.get("cells") or []
            cell_values: list[float] = []
            for cell in cells_raw:
                if isinstance(cell, dict):
                    try:
                        cell_values.append(float(cell.get("value") or 0))
                    except (TypeError, ValueError):
                        cell_values.append(0.0)
            rows.append(
                HeatmapRow(
                    label=row_label,
                    cells=tuple(cell_values),
                    row_id=str(row_dict.get("row_id") or ""),
                )
            )

        empty_msg = (
            ctx.get("empty_message")
            or getattr(region, "empty_message", None)
            or "No data available."
        )
        body: Fragment = Heatmap(
            columns=tuple(str(c) for c in col_values),
            rows=tuple(rows),
            thresholds=tuple(thresholds),
            total=total,
            empty_message=str(empty_msg),
        )
        return _wrap_surface(title, "report", body)

    def _build_detail(self, region: Any, ctx: dict[str, Any]) -> Surface:
        """`display: detail` regions render a single item's fields as a
        labelled Card. One Stack child per (label, value) pair, with
        type-aware value rendering matching the legacy template:
        Badge for `type=badge`, ✓/✗ for `type=bool`, formatted strings
        for `type=date`/`type=currency`, Link for `type=ref` (when
        `ref_route` is supplied), Text otherwise.

        ctx shape:
            item: dict (single record)
            fields: list of {"key": str, "label": str (optional),
                "type": str (optional — one of "badge"/"bool"/"date"/
                "currency"/"ref"), "ref_route": str (optional, for ref)}
                — declared field order from the region's `fields:` clause
            (legacy) `columns` is accepted as alias for `fields`
        """
        title = _region_title(region)
        item = ctx.get("item")

        # Single linear path — no conditional reassignment of `fields`.
        if not isinstance(item, dict) or not item:
            body: Fragment = EmptyState(
                title="No item",
                description=getattr(region, "empty_message", None) or "No item to display.",
            )
            return _wrap_surface(title, "dashboard", body)

        # `fields` is materialised once: explicit list, legacy `columns`,
        # or fallback to all keys of the item in declared order (no type info).
        fields = ctx.get("fields") or ctx.get("columns") or [{"key": k} for k in item.keys()]
        rows: list[tuple[str, object]] = []
        for f in fields:
            if not isinstance(f, dict):
                continue
            key = str(f.get("key") or "")
            if not key:
                continue
            label = str(f.get("label") or key.replace("_", " ").title())
            # DETAIL renders badges with `bordered=true` per legacy macro call.
            rows.append((label, _render_typed_value(item, f, badge_bordered=True)))

        body = (
            DetailGrid(rows=tuple(rows)) if rows else EmptyState(title="No fields", description="")
        )
        return _wrap_surface(title, "dashboard", body)

    def _build_tabbed_list(self, region: Any, ctx: dict[str, Any]) -> Surface:
        """`display: tabbed_list` regions render as a tabbed container.

        Phase 4B.1.d preferred path — the runtime supplies `source_tabs`
        with HTMX endpoints, producing a `LazyTabPanel` that lazy-loads
        each tab's content (matches the legacy `workspace/regions/
        tabbed_list.html` HTMX-driven shape byte-for-byte).

        Phase 4A fallback path — the test/migration ctx supplies `tabs`
        with pre-loaded `items` + `columns`, producing the simpler
        eager `Tabs` primitive. This is retained so existing call sites
        and tests don't regress; the runtime should migrate to
        `source_tabs` ahead of the Phase 4B.2 translator.

        ctx shape (Phase 4B preferred):
            region_name: str — DOM-id namespace; required for LazyTabPanel
            source_tabs: list[dict] each with:
              - key: str (slug for tab id)
              - label: str
              - endpoint: str (URL; HTMX hx-get target)
              - eager: bool (optional; first tab is always eager)

        ctx shape (Phase 4A fallback):
            tabs / slices: list[dict] each with:
              - key, label, items, columns (pre-loaded shape)
        """
        from dazzle.render.fragment import Table

        title = _region_title(region)

        # Phase 4B preferred: lazy-loaded tabs via HTMX endpoints
        source_tabs = ctx.get("source_tabs") or []
        if source_tabs:
            region_name = str(ctx.get("region_name") or getattr(region, "name", "") or "tabbed")
            built_lazy: list[LazyTab] = []
            seen_keys: set[str] = set()
            for st in source_tabs:
                if not isinstance(st, dict):
                    continue
                # Legacy template uses `entity_name | lower` for the
                # tab id slug; accept both `key` (Phase 4B preferred)
                # and `entity_name` (production runtime ctx).
                entity_name = str(st.get("entity_name") or "")
                key = str(st.get("key") or entity_name.lower())
                label = str(st.get("label") or key)
                endpoint = str(st.get("endpoint") or "")
                if not key or not endpoint:
                    continue
                if key in seen_keys:
                    continue
                seen_keys.add(key)
                built_lazy.append(
                    LazyTab(
                        key=key,
                        label=label,
                        endpoint=URL(endpoint),
                        eager=bool(st.get("eager")),
                    )
                )
            body: Fragment
            if not built_lazy:
                body = EmptyState(
                    title="No tabs",
                    description=getattr(region, "empty_message", None)
                    or "No data slices declared.",
                )
            else:
                body = LazyTabPanel(
                    region_name=region_name,
                    tabs=tuple(built_lazy),
                    empty_message=getattr(region, "empty_message", None) or "No data available.",
                )
            return _wrap_surface(title, "list", body)

        # Phase 4A fallback: pre-loaded tabs via eager Tabs primitive
        raw_tabs = ctx.get("tabs") or ctx.get("slices") or []
        if not raw_tabs:
            body = EmptyState(
                title="No tabs",
                description=getattr(region, "empty_message", None) or "No data slices declared.",
            )
            return _wrap_surface(title, "list", body)

        built: list[tuple[str, object]] = []
        seen_keys = set()
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

        return _wrap_surface(title, "list", body)

    def _build_grid(self, region: Any, ctx: dict[str, Any]) -> Surface:
        """`display: grid` regions render items as cards in a CSS-driven
        responsive grid layout. Phase 4B.4 wave 2: dedicated `GridRegion`
        primitive replacing prior generic `Grid` composition for byte-
        equivalence with `workspace/regions/grid.html`.

        ctx shape (production runtime):
            items: list of dicts (rows from the source entity)
            columns: list of `{key, label, type}` dicts — same shape
                as LIST/DETAIL columns
            display_key: str — column key for the primary cell title
            entity_name: str — fallback title when display_key value is None
            empty_message: optional empty-state fallback
        """
        title = _region_title(region)
        items: list[dict[str, Any]] = ctx.get("items", []) or []
        # `columns` is the production runtime list-of-dicts shape;
        # earlier Phase 4A tests passed an int (column count) as
        # `columns`. Defend against both.
        columns_raw = ctx.get("columns") or []
        columns: list[dict[str, Any]] = columns_raw if isinstance(columns_raw, list) else []
        display_key = str(ctx.get("display_key") or ctx.get("label_field") or "")
        entity_name = str(ctx.get("entity_name") or "Item")

        cells: list[GridCell] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            primary = item.get(display_key) if display_key else None
            if primary is None:
                primary = item.get("name") or item.get("title") or entity_name
            fields: list[tuple[str, object]] = []
            for col in columns:
                if not isinstance(col, dict):
                    continue
                key = str(col.get("key") or "")
                if not key or key == display_key:
                    continue
                label = str(col.get("label") or key)
                # GRID renders badges with default size (md, no border)
                # per legacy macro call (no kwargs).
                fields.append((label, _render_typed_value(item, col)))
            cells.append(GridCell(title=str(primary), fields=tuple(fields)))

        empty_msg = (
            ctx.get("empty_message") or getattr(region, "empty_message", None) or "No items found."
        )
        body: Fragment = GridRegion(cells=tuple(cells), empty_message=str(empty_msg))
        return _wrap_surface(title, "dashboard", body)

    def _build_metrics(self, region: Any, ctx: dict[str, Any]) -> Surface:
        """`display: metrics` (and `summary`) regions render a row of
        MetricTile primitives — one per declared aggregate. Phase 4B.1.a
        replaced KPI with MetricTile so the legacy template's extended
        delta block (delta_pct, delta_period_label, delta_sentiment,
        per-tile tone) is preserved on the typed-Fragment path.

        Values are passed through `_metric_number_filter` (K/M-suffix
        formatting) before reaching the primitive — same string the
        Jinja path produces.

        ctx shape:
            metrics: list of dicts with keys:
              - label, value (required)
              - tone: one of "", "positive", "warning", "destructive",
                "accent", "neutral"
              - delta_direction: "" | "up" | "down" | "flat"
              - delta_sentiment: "" | "positive_up" | "positive_down"
              - delta: stringified delta value
              - delta_pct: float (rendered as `(N%)` when non-zero)
              - delta_period_label: rendered as `vs <label>`
            (legacy) aggregates: dict[name → resolved value], used as
                fallback when metrics list isn't supplied
        """
        from dazzle.ui.runtime.template_renderer import _metric_number_filter

        title = _region_title(region)
        metrics_list: list[dict[str, Any]] = ctx.get("metrics", []) or []
        if not metrics_list:
            agg = ctx.get("aggregates") or getattr(region, "aggregates", {}) or {}
            if isinstance(agg, dict):
                metrics_list = [
                    {"label": str(name).replace("_", " ").title(), "value": val}
                    for name, val in agg.items()
                ]

        body: Fragment
        if not metrics_list:
            body = EmptyState(
                title="No metrics",
                description=getattr(region, "empty_message", None) or "No metrics declared.",
            )
            return _wrap_surface(title, "dashboard", body)

        tiles: list[object] = []
        for m in metrics_list:
            if not isinstance(m, dict):
                continue
            label = str(m.get("label") or m.get("name") or "")
            if not label:
                continue
            value_str = _metric_number_filter(m.get("value"))

            tone_raw = str(m.get("tone") or "")
            tone: Literal["", "positive", "warning", "destructive", "accent", "neutral"] = (
                tone_raw  # type: ignore[assignment]
                if tone_raw in ("", "positive", "warning", "destructive", "accent", "neutral")
                else ""
            )
            direction_raw = str(m.get("delta_direction") or "")
            direction: Literal["", "up", "down", "flat"] = (
                direction_raw  # type: ignore[assignment]
                if direction_raw in ("", "up", "down", "flat")
                else ""
            )
            sentiment_raw = str(m.get("delta_sentiment") or "")
            sentiment: Literal["", "positive_up", "positive_down"] = (
                sentiment_raw  # type: ignore[assignment]
                if sentiment_raw in ("", "positive_up", "positive_down")
                else ""
            )
            try:
                delta_pct = float(m.get("delta_pct") or 0)
            except (TypeError, ValueError):
                delta_pct = 0.0

            tiles.append(
                MetricTile(
                    label=label,
                    value=value_str,
                    tone=tone,
                    delta_direction=direction,
                    delta_sentiment=sentiment,
                    delta_value=str(m.get("delta") or ""),
                    delta_pct=delta_pct,
                    delta_period_label=str(m.get("delta_period_label") or ""),
                )
            )

        if not tiles:
            body = EmptyState(title="No metrics", description="No metric tiles produced.")
        else:
            body = MetricsGrid(tiles=tuple(tiles))

        return _wrap_surface(title, "dashboard", body)

    def _build_bar_chart(self, region: Any, ctx: dict[str, Any]) -> Surface:
        """`display: bar_chart` regions render as a BarChart primitive
        — list of (label, count) tuples derived from the region's
        group_by aggregation.

        ctx shape:
            buckets: list[(str, int)] — pre-aggregated by the runtime
            (legacy) items + group_by_field as fallback
            chart_label: optional override for the BarChart label
        """
        title = _region_title(region)
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
            body = BarChart(
                label=chart_label,
                buckets=tuple(buckets),
                reference_lines=_parse_reference_lines(ctx.get("reference_lines")),
                reference_bands=_parse_reference_bands(ctx.get("reference_bands")),
            )

        return _wrap_surface(title, "report", body)
