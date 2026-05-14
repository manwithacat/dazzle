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
from typing import Any, Literal

# Cross-cutting helpers extracted to ._shared in #1065 PR 2 (v0.67.129).
# Re-imported here so the dispatcher's internal call sites keep working
# unchanged. The public re-export of `_render_status_badge_html` for
# external callers (renderer.py × 4 sites) lives in `__init__.py`.
from dazzle.back.runtime.renderers.region_adapter._builders_charts import (
    _BuildersChartsMixin,
)
from dazzle.back.runtime.renderers.region_adapter._builders_metrics import (
    _BuildersMetricsMixin,
)
from dazzle.back.runtime.renderers.region_adapter._builders_misc import (
    _BuildersMiscMixin,
)
from dazzle.back.runtime.renderers.region_adapter._builders_timeline import (
    _BuildersTimelineMixin,
)
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
    CohortStripCell,
    CohortStripLensTab,
    CohortStripRegion,
    CsvExportButton,
    DateRangePicker,
    EmptyState,
    EntityCardRegion,
    EntityCardSection,
    FilterBar,
    FilterColumn,
    Fragment,
    KanbanCard,
    KanbanColumn,
    KanbanRegion,
    LazyTab,
    LazyTabPanel,
    ListColumn,
    ListRegion,
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
    Stack,
    Surface,
    Tabs,
    Text,
)

_log = logging.getLogger(__name__)


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


class WorkspaceRegionAdapter(
    _BuildersChartsMixin,
    _BuildersMetricsMixin,
    _BuildersMiscMixin,
    _BuildersTimelineMixin,
):
    """Translate a WorkspaceRegion + ctx into a Fragment tree.

    Dispatch is table-driven: `_BUILDERS` maps display values to
    methods, `_ALIASES` redirects shared shapes (e.g. `histogram`
    renders the same as `bar_chart`). `_TIMESERIES_VIEWS` is the
    one special case — line/area/sparkline share `_build_time_series`
    but pass a `view` argument that the others don't.

    The 10 chart-family `_build_*` methods come from
    `_BuildersChartsMixin` (extracted in #1065 PR 3). Subsequent PRs
    will pull other families into their own mixins: cards, tables,
    timeline, metrics, misc.
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
