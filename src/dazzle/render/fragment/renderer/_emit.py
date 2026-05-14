"""FragmentRenderer — emits HTML from Fragment trees.

Single-class renderer. The `render` method match-dispatches on the Fragment
union; per-primitive emit methods produce HTML strings. The match block is
the runtime exhaustiveness check — adding a new primitive without adding a
match arm causes mypy to flag the unreachable case (with `--strict`) and
the test_fragment_exhaustiveness test to fail.
"""

from dazzle.render.fragment.context import RenderContext
from dazzle.render.fragment.errors import FragmentError
from dazzle.render.fragment.escape import RawHTML, Slot
from dazzle.render.fragment.primitives import (
    KPI,
    ActionCard,
    ActionGrid,
    ActivityFeed,
    AddCardRow,
    AppShell,
    Badge,
    BarChart,
    BarTrack,
    BoxPlot,
    BulkActionToolbar,
    Bullet,
    Button,
    CalendarGrid,
    Card,
    CardPicker,
    CohortStripRegion,
    Combobox,
    ConfirmGate,
    CreateButton,
    CsvExportButton,
    DashboardCard,
    DashboardGrid,
    DateRangePicker,
    DayTimelineRegion,
    DetailGrid,
    Diagram,
    Drawer,
    EmptyState,
    EntityCardRegion,
    ErrorPage,
    Field,
    FileUpload,
    FilterBar,
    FormSection,
    FormStack,
    Fragment,
    Funnel,
    Grid,
    GridRegion,
    Heading,
    Heatmap,
    Histogram,
    Icon,
    InlineEdit,
    Interactive,
    KanbanBoard,
    KanbanRegion,
    LazyTabPanel,
    Link,
    ListRegion,
    MetricsGrid,
    MetricTile,
    Modal,
    NavGroup,
    NavItem,
    Page,
    Pagination,
    PipelineSteps,
    PivotTable,
    PivotTableRegion,
    ProfileCard,
    QueueRegion,
    Radar,
    RefPicker,
    Region,
    Row,
    SearchBox,
    Sequence,
    Sidebar,
    Skeleton,
    SkipLink,
    SortHeader,
    Sparkline,
    Split,
    Stack,
    StageBar,
    StatusList,
    Submit,
    Surface,
    Table,
    Tabs,
    TaskInboxRegion,
    Text,
    Timeline,
    TimelineEvent,
    TimeSeries,
    Toolbar,
    Topbar,
    Tree,
    TreeNode,
    WorkspaceContextSelector,
    WorkspaceDrawer,
    WorkspaceShell,
    WorkspaceToolbar,
)

# Cross-arm helpers extracted to ._helpers in #1064 PR 2 (v0.67.137).
# Internal `self._hx_attrs(...)` / `self._pagination_pages(...)` /
# `self._render_references(...)` call sites updated to call the
# module-level forms directly — they never used `self`.
from dazzle.render.fragment.renderer._helpers import (
    _render_references,
)
from dazzle.render.fragment.renderer._render_dashboard import _RenderDashboardMixin
from dazzle.render.fragment.renderer._render_forms import _RenderFormsMixin
from dazzle.render.fragment.renderer._render_interactive import (
    _BULK_ACTION_TOOLBAR_HTML,
    _RenderInteractiveMixin,
)
from dazzle.render.fragment.renderer._render_layout import _RenderLayoutMixin

# `_load_static` lives in `_render_shell.py` (alongside the workspace
# HTML constants that use it). Re-imported here so external callers
# via the package facade still resolve `_load_static`.
from dazzle.render.fragment.renderer._render_shell import (
    _load_static,  # noqa: F401, E402
    _RenderShellMixin,
)

_DIAGRAM_MERMAID_SCRIPT = (
    "<script>\n"
    '    if (typeof mermaid === "undefined") {\n'
    '      var s = document.createElement("script");\n'
    "      // Pinned version + SRI hash (#830 Phase 1 of external-resource hardening).\n"
    "      // Hash regenerated when the pinned version is bumped — `curl -sL <url> |\n"
    "      // openssl dgst -sha384 -binary | openssl base64 -A`.\n"
    '      s.src = "https://cdn.jsdelivr.net/npm/mermaid@11.14.0/dist/mermaid.min.js";\n'
    '      s.integrity = "sha384-1CMXl090wj8Dd6YfnzSQUOgWbE6suWCaenYG7pox5AX7apTpY3PmJMeS2oPql4Gk";\n'
    '      s.crossOrigin = "anonymous";\n'
    "      s.onload = function () {\n"
    '        mermaid.initialize({ startOnLoad: true, theme: "neutral" });\n'
    "        mermaid.run();\n"
    "      };\n"
    "      document.head.appendChild(s);\n"
    "    } else {\n"
    "      mermaid.run();\n"
    "    }\n"
    "  </script>"
)


class FragmentRenderer(
    _RenderDashboardMixin,
    _RenderFormsMixin,
    _RenderInteractiveMixin,
    _RenderLayoutMixin,
    _RenderShellMixin,
):
    """Emit HTML from a Fragment tree.

    Stateless — a single instance can be reused across requests. The
    RenderContext is per-render-call and threads tokens through descent.
    """

    def render(self, fragment: Fragment, ctx: RenderContext | None = None) -> str:
        ctx = ctx if ctx is not None else RenderContext()
        return self._emit(fragment, ctx)

    def _emit(self, fragment: Fragment, ctx: RenderContext) -> str:
        match fragment:
            # Escape hatches first — most likely path is RawHTML interop
            case RawHTML(html=html):
                return html
            case Slot(name=name):
                raise FragmentError(
                    f"unfilled slot {name!r} reached the renderer; "
                    f"slots must be substituted before render() is called"
                )
            # Content
            case Text():
                return self._emit_text(fragment, ctx)
            case Heading():
                return self._emit_heading(fragment, ctx)
            # Layout
            case Stack():
                return self._emit_stack(fragment, ctx)
            case Row():
                return self._emit_row(fragment, ctx)
            case Split():
                return self._emit_split(fragment, ctx)
            case Grid():
                return self._emit_grid(fragment, ctx)
            # Containers
            case Page():
                return self._emit_page(fragment, ctx)
            case AppShell():
                return self._emit_app_shell(fragment, ctx)
            case Surface():
                return self._emit_surface(fragment, ctx)
            case Card():
                return self._emit_card(fragment, ctx)
            case Region():
                return self._emit_region(fragment, ctx)
            case Drawer():
                return self._emit_drawer(fragment, ctx)
            case Modal():
                return self._emit_modal(fragment, ctx)
            case Tabs():
                return self._emit_tabs(fragment, ctx)
            case ErrorPage():
                return self._emit_error_page(fragment, ctx)
            # Navigation
            case Sidebar():
                return self._emit_sidebar(fragment, ctx)
            case Topbar():
                return self._emit_topbar(fragment, ctx)
            case NavGroup():
                return self._emit_nav_group(fragment, ctx)
            case NavItem():
                return self._emit_nav_item(fragment, ctx)
            case SkipLink():
                return self._emit_skip_link(fragment, ctx)
            # Content
            case Icon():
                return self._emit_icon(fragment, ctx)
            case Badge():
                return self._emit_badge(fragment, ctx)
            case EmptyState():
                return self._emit_empty_state(fragment, ctx)
            case Skeleton():
                return self._emit_skeleton(fragment, ctx)
            # Interactive
            case Button():
                return self._emit_button(fragment, ctx)
            case Link():
                return self._emit_link(fragment, ctx)
            case Interactive():
                return self._emit_interactive(fragment, ctx)
            case InlineEdit():
                return self._emit_inline_edit(fragment, ctx)
            case Toolbar():
                return self._emit_toolbar(fragment, ctx)
            # Data
            case Table():
                return self._emit_table(fragment, ctx)
            case KPI():
                return self._emit_kpi(fragment, ctx)
            case BarChart():
                return self._emit_bar_chart(fragment, ctx)
            case PivotTable():
                return self._emit_pivot_table(fragment, ctx)
            case Timeline():
                return self._emit_timeline(fragment, ctx)
            case KanbanBoard():
                return self._emit_kanban_board(fragment, ctx)
            case CalendarGrid():
                return self._emit_calendar_grid(fragment, ctx)
            case Diagram():
                return self._emit_diagram(fragment, ctx)
            case TimeSeries():
                return self._emit_time_series(fragment, ctx)
            case Radar():
                return self._emit_radar(fragment, ctx)
            case BoxPlot():
                return self._emit_box_plot(fragment, ctx)
            case Bullet():
                return self._emit_bullet(fragment, ctx)
            case PipelineSteps():
                return self._emit_pipeline_steps(fragment, ctx)
            case Sparkline():
                return self._emit_sparkline(fragment, ctx)
            case Tree():
                return self._emit_tree(fragment, ctx)
            case ActionCard():
                return self._emit_action_card(fragment, ctx)
            case ActionGrid():
                return self._emit_action_grid(fragment, ctx)
            case ProfileCard():
                return self._emit_profile_card(fragment, ctx)
            case MetricTile():
                return self._emit_metric_tile(fragment, ctx)
            case MetricsGrid():
                return self._emit_metrics_grid(fragment, ctx)
            case DetailGrid():
                return self._emit_detail_grid(fragment, ctx)
            case GridRegion():
                return self._emit_grid_region(fragment, ctx)
            case ListRegion():
                return self._emit_list_region(fragment, ctx)
            case Histogram():
                return self._emit_histogram(fragment, ctx)
            case Heatmap():
                return self._emit_heatmap(fragment, ctx)
            case PivotTableRegion():
                return self._emit_pivot_table_region(fragment, ctx)
            case QueueRegion():
                return self._emit_queue_region(fragment, ctx)
            case Funnel():
                return self._emit_funnel(fragment, ctx)
            case KanbanRegion():
                return self._emit_kanban_region(fragment, ctx)
            case ActivityFeed():
                return self._emit_activity_feed(fragment, ctx)
            case StatusList():
                return self._emit_status_list(fragment, ctx)
            case BarTrack():
                return self._emit_bar_track(fragment, ctx)
            case StageBar():
                return self._emit_stage_bar(fragment, ctx)
            case LazyTabPanel():
                return self._emit_lazy_tab_panel(fragment, ctx)
            case SearchBox():
                return self._emit_search_box(fragment, ctx)
            case ConfirmGate():
                return self._emit_confirm_gate(fragment, ctx)
            case CardPicker():
                return self._emit_card_picker(fragment, ctx)
            case WorkspaceShell():
                return self._emit_workspace_shell(fragment, ctx)
            case WorkspaceToolbar():
                return self._emit_workspace_toolbar(fragment, ctx)
            case WorkspaceDrawer():
                return self._emit_workspace_drawer(fragment, ctx)
            case WorkspaceContextSelector():
                return self._emit_workspace_context_selector(fragment, ctx)
            case Sequence():
                return "".join(
                    self._emit(child, ctx)  # type: ignore[arg-type]
                    for child in fragment.children
                )
            case Pagination():
                return self._emit_pagination(fragment, ctx)
            case CreateButton():
                return self._emit_create_button(fragment, ctx)
            case BulkActionToolbar():
                return _BULK_ACTION_TOOLBAR_HTML
            case CohortStripRegion():
                return self._emit_cohort_strip_region(fragment, ctx)
            case DayTimelineRegion():
                return self._emit_day_timeline_region(fragment, ctx)
            case TaskInboxRegion():
                return self._emit_task_inbox_region(fragment, ctx)
            case EntityCardRegion():
                return self._emit_entity_card_region(fragment, ctx)
            case DashboardGrid():
                return self._emit_dashboard_grid(fragment, ctx)
            case DashboardCard():
                return self._emit_dashboard_card(fragment, ctx)
            case AddCardRow():
                return self._emit_add_card_row(fragment, ctx)
            case FilterBar():
                return self._emit_filter_bar(fragment, ctx)
            case SortHeader():
                return self._emit_sort_header(fragment, ctx)
            case CsvExportButton():
                return self._emit_csv_export_button(fragment, ctx)
            case DateRangePicker():
                return self._emit_date_range_picker(fragment, ctx)
            # Forms
            case FormStack():
                return self._emit_form_stack(fragment, ctx)
            case FormSection():
                return self._emit_form_section(fragment, ctx)
            case Field():
                return self._emit_field(fragment, ctx)
            case Combobox():
                return self._emit_combobox(fragment, ctx)
            case RefPicker():
                return self._emit_ref_picker(fragment, ctx)
            case FileUpload():
                return self._emit_file_upload(fragment, ctx)
            case Submit():
                return self._emit_submit(fragment, ctx)
            # Defensive fallback — exhaustiveness is verified by
            # test_fragment_exhaustiveness via property tests.
            case _:
                raise FragmentError(
                    f"renderer has no emit for {type(fragment).__name__!r} yet — "
                    f"add a match arm in FragmentRenderer._emit"
                )

    # --- per-primitive emitters ---

    def _emit_table(self, t: Table, ctx: RenderContext) -> str:
        # Issue #1029 phase 6: columns can be plain strings (legacy
        # static labels) or SortHeader primitives (clickable column
        # headers with aria-sort + hx-get). Per-cell dispatch keeps
        # the legacy string-column shape backwards-compatible.
        head_cells_parts: list[str] = []
        # Issue #1029 phase 7: bulk_select prepends a select-all
        # checkbox header cell. Alpine `dzTable` controller owns
        # bulkCount + toggleSelectAll.
        if t.bulk_select:
            head_cells_parts.append(
                '<th scope="col" class="dz-table-th-select">'
                '<input type="checkbox" class="dz-table-col-menu-checkbox" '
                '@change="toggleSelectAll($event.target.checked)" '
                'aria-label="Select all rows" />'
                "</th>"
            )
        for c in t.columns:
            if isinstance(c, SortHeader):
                head_cells_parts.append(f"<th>{self._emit(c, ctx)}</th>")
            else:
                head_cells_parts.append(f"<th>{ctx.escape(str(c))}</th>")
        head_cells = "".join(head_cells_parts)
        # Issue #1029 phase 1: row_links — when set, each row carries
        # an hx-get on the <tr> so clicking navigates to the detail
        # URL via htmx (full-page swap into <body>). Wrapping each
        # cell in an <a> would break <td> nesting; wrapping the <tr>
        # is the htmx-idiomatic shape for clickable rows.
        body_parts: list[str] = []
        for i, row in enumerate(t.rows):
            row_cells: list[str] = []
            # Phase 7: per-row checkbox cell when bulk_select is on.
            if t.bulk_select:
                row_id = ctx.escape_attr(t.row_ids[i]) if t.row_ids else ""
                row_cells.append(
                    f'<td class="dz-tr-checkbox-cell" '
                    f'onclick="event.stopPropagation()">'
                    f'<input type="checkbox" class="dz-tr-checkbox" '
                    f"@change=\"toggleRow('{row_id}')\" "
                    f":checked=\"selected.has('{row_id}')\" "
                    f'aria-label="Select row" />'
                    f"</td>"
                )
            row_cells.extend(f"<td>{ctx.escape(cell)}</td>" for cell in row)
            cells_html = "".join(row_cells)
            url = t.row_links[i] if t.row_links else None
            row_id_attr = (
                f' data-dz-row-id="{ctx.escape_attr(t.row_ids[i])}"'
                if t.bulk_select and t.row_ids
                else ""
            )
            if url:
                url_attr = ctx.escape_attr(url)
                body_parts.append(
                    f'<tr class="dz-table__row dz-table__row--linked" '
                    f'hx-get="{url_attr}" hx-target="body" hx-swap="innerHTML" '
                    f'hx-push-url="true" tabindex="0"{row_id_attr}>'
                    f"{cells_html}</tr>"
                )
            else:
                body_parts.append(f"<tr{row_id_attr}>{cells_html}</tr>")
        body_rows = "".join(body_parts)
        return (
            f'<table class="dz-table">'
            f"<thead><tr>{head_cells}</tr></thead>"
            f"<tbody>{body_rows}</tbody>"
            f"</table>"
        )

    def _emit_kpi(self, k: KPI, ctx: RenderContext) -> str:
        cls = f"dz-kpi dz-kpi--trend-{k.trend}"
        delta_html = f'<span class="dz-kpi__delta">{ctx.escape(k.delta)}</span>' if k.delta else ""
        return (
            f'<div class="{cls}">'
            f'<div class="dz-kpi__label">{ctx.escape(k.label)}</div>'
            f'<div class="dz-kpi__value">{ctx.escape(k.value)}</div>'
            f"{delta_html}"
            f"</div>"
        )

    def _emit_bar_chart(self, b: BarChart, ctx: RenderContext) -> str:
        """Render a bar chart as label/track/fill/value rows — byte-equivalent
        to the legacy `workspace/regions/bar_chart.html` template's
        `bucketed_metrics` primary branch.

        Phase 4B.4 wave 3: aligned with legacy template:
          - Outer `dz-bar-chart-region` carries no aria-label (label is
            owned by the surrounding region_card chrome)
          - Bucket label wrapped in `render_status_badge(value, size='sm')`
            via `_render_status_badge_html`
          - No summary line (legacy summary appears in the items+group_by
            branch, not the bucketed_metrics branch)
          - No `<dl>` references block (Phase 4B-only addition with no
            legacy equivalent in this branch)
        """
        if not b.buckets:
            return '<div class="dz-bar-chart-region"></div>'

        # Late import to avoid circular dependency between renderer and
        # workspace adapter (the helper lives in adapter for now; could
        # be promoted to a shared module if more renderers need it).
        from dazzle.back.runtime.renderers.region_adapter import (
            _render_status_badge_html,
        )

        max_val = max((c for _, c in b.buckets), default=1) or 1
        rows = "".join(
            f'<div class="dz-bar-chart-row">'
            f'<span class="dz-bar-chart-label">'
            f"{_render_status_badge_html(label, size='sm')}"
            f"</span>"
            f'<div class="dz-bar-chart-track">'
            f'<div class="dz-bar-chart-fill" '
            f'style="width: {int(count / max_val * 100)}%"></div>'
            f"</div>"
            f'<span class="dz-bar-chart-value">{count}</span>'
            f"</div>"
            for label, count in b.buckets
        )
        return f'<div class="dz-bar-chart-region"><div class="dz-bar-chart-bars">{rows}</div></div>'

    def _emit_pivot_table(self, p: PivotTable, ctx: RenderContext) -> str:
        head = "".join(f"<th>{ctx.escape(c)}</th>" for c in p.columns)
        body = "".join(
            "<tr>"
            + f"<th>{ctx.escape(row)}</th>"
            + "".join(f"<td>{p.cells.get((row, col), 0)}</td>" for col in p.columns)
            + "</tr>"
            for row in p.rows
        )
        return (
            f'<table class="dz-pivot-table">'
            f"<caption>{ctx.escape(p.label)}</caption>"
            f"<thead><tr><th></th>{head}</tr></thead>"
            f"<tbody>{body}</tbody>"
            f"</table>"
        )

    def _emit_timeline(self, t: Timeline, ctx: RenderContext) -> str:
        """Render a Timeline matching legacy
        `workspace/regions/timeline.html` byte-for-byte: outer
        `dz-timeline-region`, `<ul class="dz-timeline-list">` of
        `<li class="dz-timeline-item">` rows. Each row carries a bullet
        SVG, formatted date, primary title, and optional secondary
        fields rendered as `<p class="dz-timeline-field">` lines.
        Optional overflow line "Showing N of M" when total exceeds
        the events count. Empty path renders the `dz-empty-dense`
        fallback inside the region wrapper.
        """
        # Coerce Phase 4A `(label, iso-date)` tuples to TimelineEvent
        # for rendering uniformity. New callers construct TimelineEvent
        # instances directly.
        events_norm: list[TimelineEvent] = []
        for evt in t.events:
            if isinstance(evt, TimelineEvent):
                events_norm.append(evt)
            elif isinstance(evt, tuple) and len(evt) == 2:
                label, when = evt
                events_norm.append(TimelineEvent(title=str(label), date_label=str(when)))

        if not events_norm:
            return (
                f'<div class="dz-timeline-region">'
                f'<p class="dz-empty-dense" role="status">'
                f"{ctx.escape(t.empty_message)}</p>"
                f"</div>"
            )

        # Legacy bullet always picks up `attention_classes(attn, 'bullet')`
        # which defaults to `dz-attn-bullet dz-attn-tone-default` when
        # the item has no `_attention` entry. The typed primitive
        # doesn't track per-row attention yet (Phase 4B follow-up); for
        # now, emit the default attention class so the no-attention
        # case is byte-equivalent to legacy.
        bullet_svg = (
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" '
            'fill="currentColor" '
            'class="dz-timeline-bullet dz-attn-bullet dz-attn-tone-default" '
            'aria-hidden="true">'
            '<circle cx="10" cy="10" r="6"/>'
            "</svg>"
        )

        items: list[str] = []
        for evt in events_norm:
            fields_html = ""
            for label, value in evt.fields:
                if isinstance(value, str):
                    value_html = ctx.escape(value)
                else:
                    value_html = self._emit(value, ctx)  # type: ignore[arg-type]
                fields_html += (
                    f'<p class="dz-timeline-field">'
                    f"<span>{ctx.escape(label)}:</span> "
                    f"{value_html}"
                    f"</p>"
                )
            items.append(
                f'<li class="dz-timeline-item">'
                f'<span class="dz-timeline-bullet-wrap">{bullet_svg}</span>'
                f'<div class="dz-timeline-row">'
                f'<div class="dz-timeline-date">{ctx.escape(evt.date_label)}</div>'
                f'<div class="dz-timeline-content">'
                f'<p class="dz-timeline-title">{ctx.escape(evt.title)}</p>'
                f"{fields_html}"
                f"</div>"
                f"</div>"
                f"</li>"
            )

        overflow_html = ""
        if t.total > len(events_norm):
            overflow_html = (
                f'<p class="dz-timeline-overflow">Showing {len(events_norm)} of {t.total}</p>'
            )

        return (
            f'<div class="dz-timeline-region">'
            f'<ul class="dz-timeline-list">{"".join(items)}</ul>'
            f"{overflow_html}"
            f"</div>"
        )

    def _emit_kanban_board(self, k: KanbanBoard, ctx: RenderContext) -> str:
        cols = "".join(
            f'<div class="dz-kanban__column" data-key="{ctx.escape_attr(key)}">'
            + "".join(self._emit(item, ctx) for item in items)  # type: ignore[arg-type]
            + "</div>"
            for key, items in k.columns
        )
        return f'<div class="dz-kanban">{cols}</div>'

    def _emit_calendar_grid(self, c: CalendarGrid, ctx: RenderContext) -> str:
        cls = f"dz-calendar dz-calendar--view-{c.view}"
        events = "".join(
            f'<li class="dz-calendar__event">'
            f'<time datetime="{ctx.escape_attr(when)}">{ctx.escape(when)}</time> '
            f"{ctx.escape(label)}"
            f"</li>"
            for label, when in c.events
        )
        return f'<div class="{cls}"><ul>{events}</ul></div>'

    def _emit_diagram(self, d: Diagram, ctx: RenderContext) -> str:
        """Render an entity-relationship diagram.

        Phase 4B.4 wave 4 (v0.66.118) — two modes:

        Mermaid mode (`mermaid_source` non-empty): emit `<pre class="mermaid">`
        carrying the raw Mermaid syntax + the legacy Mermaid CDN loader
        script. Byte-equivalent to the legacy `diagram.html` template.

        Structural mode (`mermaid_source` empty): nodes as labelled `<li>`
        boxes and edges as `from → to` rows (Phase 4A fallback,
        retained for tests and any consumer that hasn't built Mermaid
        source).
        """
        if d.mermaid_source:
            return (
                f'<div class="dz-diagram-scroll">'
                f'<pre class="mermaid dz-diagram-source">'
                f"{ctx.escape(d.mermaid_source)}"
                f"</pre>"
                f"</div>"
                f"{_DIAGRAM_MERMAID_SCRIPT}"
            )
        nodes_html = "".join(
            f'<li class="dz-diagram__node" data-key="{ctx.escape_attr(name)}">'
            f"{ctx.escape(name)}</li>"
            for name in d.nodes
        )
        edges_html = "".join(
            f'<li class="dz-diagram__edge">'
            f'<span class="dz-diagram__edge-from">{ctx.escape(src)}</span>'
            f'<span class="dz-diagram__edge-arrow">→</span>'
            f'<span class="dz-diagram__edge-to">{ctx.escape(dst)}</span>'
            f"</li>"
            for src, dst in d.edges
        )
        return (
            f'<section class="dz-diagram">'
            f'<ul class="dz-diagram__nodes">{nodes_html}</ul>'
            f'<ul class="dz-diagram__edges">{edges_html}</ul>'
            f"</section>"
        )

    def _emit_time_series(self, t: TimeSeries, ctx: RenderContext) -> str:
        """Render line/area/sparkline as inline SVG plus optional `<dl>`
        annotation lists for reference lines and reference bands.

        Phase 4B.1.c replaced the semantic `<ol>` of points with an
        inline SVG produced by `dazzle.render.svg.time_series_svg` —
        byte-equivalent to the legacy `line_chart.html` template. The
        `<dl class="dz-timeseries__references">` block remains as the
        programmatic-data layer for screen-readers and tests; the SVG
        already carries the same data via `<title>` tooltips and is
        the visual layer.
        """
        from dazzle.render.svg import time_series_svg

        # Phase 4B.4 wave 3: aligned with legacy template — strip the
        # `<section class="dz-timeseries">` chrome + `<h4>` + Phase 4B-
        # only `<dl>` references block. Wrapper class is per-view
        # (`dz-line-chart-region` for line, `dz-area-chart-region` for
        # area). Summary line emits `{count} buckets · peak {max_val}`.
        wrapper_class = "dz-area-chart-region" if t.view == "area" else "dz-line-chart-region"

        if not t.points:
            return f'<div class="{wrapper_class}"></div>'

        max_val = max((v for _, v in t.points), default=1) or 1
        max_val_str = str(int(max_val)) if max_val == int(max_val) else str(max_val)

        svg = time_series_svg(
            t.label,
            t.points,
            view=t.view,
            reference_lines=t.reference_lines,
            reference_bands=t.reference_bands,
        )
        summary = f'<p class="dz-chart-summary">{len(t.points)} buckets · peak {max_val_str}</p>'
        return f'<div class="{wrapper_class}">{svg}{summary}</div>'

    def _emit_radar(self, r: Radar, ctx: RenderContext) -> str:
        """Render a polar/radar profile as inline SVG with concentric
        grid rings, spoke axis lines, data polygon, and spoke labels —
        byte-equivalent to `workspace/regions/radar.html` for the
        single-series case.

        Phase 4B.1.c (SVG arc, radar variant): replaces the prior
        `<ul>` of axes with the SVG produced by
        `dazzle.render.svg.radar_svg`. Outer `<section class="dz-radar">`
        + `<h4 class="dz-radar__label">` wrapper survives so existing
        CSS hooks keep working; the SVG sits in a new
        `<div class="dz-radar-region">` (the legacy class).
        """
        from dazzle.render.svg import radar_svg
        from dazzle.ui.runtime.template_renderer import _metric_number_filter

        # Phase 4B.4 wave 3: aligned with legacy template — strip the
        # `<section class="dz-radar">` + `<h4>` chrome. Summary uses
        # the legacy "N spokes · 1 series · peak {metric_number}" format
        # (single-series — multi-series Radar is a deferred primitive).
        svg = radar_svg(r.label, r.axes)
        max_val = max((v for _, v in r.axes), default=1) or 1
        max_for_filter = int(max_val) if max_val == int(max_val) else max_val
        max_val_str = _metric_number_filter(max_for_filter)
        summary = (
            f'<p class="dz-chart-summary">{len(r.axes)} spokes · 1 series · peak {max_val_str}</p>'
        )
        return f'<div class="dz-radar-region">{svg}{summary}</div>'

    def _emit_box_plot(self, b: BoxPlot, ctx: RenderContext) -> str:
        """Render a box-plot as inline SVG box+whisker glyphs — byte-
        equivalent to `workspace/regions/box_plot.html` for the common
        case (modulo the documented divergence in `box_plot_svg`).

        Phase 4B.4 wave 2: stripped the prior Phase 4B.1.c chrome
        (`<section class="dz-box-plot">` + `<h4>` + summary line +
        `<dl>` references block) for byte-equivalence with the legacy
        template, which emits only `<div class="dz-box-plot-region">`
        wrapping the SVG. The summary referenced legacy's `n` field
        (sum of samples across groups); the typed primitive doesn't
        carry `n`, so the summary can't be reproduced — dropped. The
        `<dl>` references block was a Phase 4B-only addition with no
        legacy counterpart; also dropped to match.

        Empty case renders `<p class="dz-empty-dense">…</p>` inside
        the region wrapper, matching the legacy `{% else %}` branch.
        """
        from dazzle.render.svg import box_plot_svg

        if not b.groups:
            empty_msg = "No data available."
            return (
                f'<div class="dz-box-plot-region">'
                f'<p class="dz-empty-dense" role="status">{empty_msg}</p>'
                f"</div>"
            )

        svg = box_plot_svg(
            b.label,
            b.groups,
            reference_lines=b.reference_lines,
            samples=b.samples,
        )
        # Summary line — matches legacy `{{ count }} groups · {{ sum(n) }} samples`.
        # When samples is empty, sum is 0 (legacy Jinja sum on missing
        # attribute returns 0 too).
        n_total = sum(b.samples) if b.samples else 0
        summary = f'<p class="dz-box-plot-summary">{len(b.groups)} groups · {n_total} samples</p>'
        return f'<div class="dz-box-plot-region">{svg}{summary}</div>'

    def _emit_action_card(self, a: ActionCard, ctx: RenderContext) -> str:
        """Render an ActionCard as the dashboard CTA card shape.

        Mirrors the legacy `workspace/regions/action_grid.html` rendering
        so dual-path validation (Phase 4B.3) compares clean: anchor wrapper
        when `url` is set, plain `<div>` otherwise; tone tint via
        `data-dz-tone`; optional icon (Lucide) and count badge.
        """
        tone = ctx.escape_attr(a.tone)
        label = ctx.escape(a.label)
        icon_html = (
            f'<span class="dz-action-card-icon" data-lucide="{ctx.escape_attr(a.icon)}" '
            f'aria-hidden="true"></span>'
            if a.icon
            else '<span class="dz-action-card-icon-spacer"></span>'
        )
        count_html = (
            f'<span class="dz-action-card-count" data-dz-tone-badge="{tone}">{a.count}</span>'
            if a.count is not None
            else ""
        )
        body = (
            f'<div class="dz-action-card-row">{icon_html}{count_html}</div>'
            f'<span class="dz-action-card-label">{label}</span>'
        )
        if a.url:
            href = ctx.escape_attr(a.url)
            return f'<a href="{href}" class="dz-action-card" data-dz-tone="{tone}">{body}</a>'
        return f'<div class="dz-action-card" data-dz-tone="{tone}">{body}</div>'

    def _emit_profile_card(self, p: ProfileCard, ctx: RenderContext) -> str:
        """Render a ProfileCard matching the legacy
        `workspace/regions/profile_card.html` HTML shape: identity row
        (avatar or initials + name + meta), optional 3-up stats grid,
        optional bulleted facts list.
        """
        # Identity row: avatar wins over initials
        if p.avatar_url:
            avatar_html = (
                f'<img src="{ctx.escape_attr(p.avatar_url)}" '
                f'alt="{ctx.escape_attr(p.primary)}" '
                f'class="dz-profile-avatar" />'
            )
        elif p.initials:
            avatar_html = (
                f'<span class="dz-profile-initials" aria-hidden="true">'
                f"{ctx.escape(p.initials)}</span>"
            )
        else:
            avatar_html = ""

        text_inner = ""
        if p.primary:
            text_inner += f'<h3 class="dz-profile-primary">{ctx.escape(p.primary)}</h3>'
        if p.secondary:
            text_inner += f'<p class="dz-profile-secondary">{ctx.escape(p.secondary)}</p>'
        identity_html = (
            f'<div class="dz-profile-identity">'
            f"{avatar_html}"
            f'<div class="dz-profile-text">{text_inner}</div>'
            f"</div>"
        )

        # Stats grid — em-dash for empty values (matches legacy `stat.value or "—"`)
        stats_html = ""
        if p.stats:
            stat_rows = "".join(
                f'<div class="dz-profile-stat">'
                f'<dt class="dz-profile-stat-label">{ctx.escape(label)}</dt>'
                f'<dd class="dz-profile-stat-value">{ctx.escape(value) if value else "—"}</dd>'
                f"</div>"
                for label, value in p.stats
            )
            stats_html = f'<dl class="dz-profile-stats">{stat_rows}</dl>'

        # Facts list — bullet decoration via CSS, not literal text
        facts_html = ""
        if p.facts:
            fact_items = "".join(
                f'<li class="dz-profile-fact">'
                f'<span class="dz-profile-fact-bullet" aria-hidden="true">·</span>'
                f'<span class="dz-profile-fact-text">{ctx.escape(fact)}</span>'
                f"</li>"
                for fact in p.facts
            )
            facts_html = f'<ul class="dz-profile-facts">{fact_items}</ul>'

        # Phase 4B.4 wave 4: outer dz-profile-card-region wrapper
        # for byte-equivalence with the legacy template.
        return (
            f'<div class="dz-profile-card-region">'
            f'<div class="dz-profile-card">{identity_html}{stats_html}{facts_html}</div>'
            f"</div>"
        )

    def _emit_metric_tile(self, m: MetricTile, ctx: RenderContext) -> str:
        """Render a MetricTile matching the legacy
        `workspace/regions/metrics.html` HTML shape: dz-metric-tile
        wrapper with snake-cased data-dz-metric-key, optional data-dz-tone,
        label + already-formatted value, and a delta block when
        delta_direction is set.

        The delta tone is computed from (direction, sentiment):
            - up + positive_up   = good (positive)
            - down + positive_down = good (positive)
            - down + positive_up = bad (destructive)
            - up + positive_down = bad (destructive)
            - flat or anything else = neutral
        """
        key_attr = m.label.lower().replace(" ", "_")
        tone_attr = f' data-dz-tone="{ctx.escape_attr(m.tone)}"' if m.tone else ""

        delta_html = ""
        if m.delta_direction:
            is_good = (m.delta_direction == "up" and m.delta_sentiment == "positive_up") or (
                m.delta_direction == "down" and m.delta_sentiment == "positive_down"
            )
            is_bad = (m.delta_direction == "down" and m.delta_sentiment == "positive_up") or (
                m.delta_direction == "up" and m.delta_sentiment == "positive_down"
            )
            delta_tone = "positive" if is_good else ("destructive" if is_bad else "neutral")
            arrow = (
                "↑" if m.delta_direction == "up" else ("↓" if m.delta_direction == "down" else "→")
            )
            sign = "+" if m.delta_direction == "up" else ""
            pct_html = (
                f'<span class="dz-metric-delta-pct">({m.delta_pct}%)</span>' if m.delta_pct else ""
            )
            # Legacy always emits the period span when delta_direction
            # is set, even with an empty label (rendered as "vs ").
            period_html = (
                f'<span class="dz-metric-delta-period">vs {ctx.escape(m.delta_period_label)}</span>'
            )
            delta_html = (
                f'<div class="dz-metric-delta" '
                f'data-dz-delta-tone="{delta_tone}" '
                f'data-dz-delta-direction="{ctx.escape_attr(m.delta_direction)}" '
                f'data-dz-delta-sentiment="{ctx.escape_attr(m.delta_sentiment)}">'
                f'<span aria-hidden="true">{arrow}</span>'
                f'<span class="dz-metric-delta-value">{sign}{ctx.escape(m.delta_value)}</span>'
                f"{pct_html}"
                f"{period_html}"
                f"</div>"
            )

        return (
            f'<div class="dz-metric-tile" '
            f'data-dz-metric-key="{ctx.escape_attr(key_attr)}"{tone_attr}>'
            f'<div class="dz-metric-label">{ctx.escape(m.label)}</div>'
            f'<div class="dz-metric-value">{ctx.escape(m.value)}</div>'
            f"{delta_html}"
            f"</div>"
        )

    def _emit_metrics_grid(self, g: MetricsGrid, ctx: RenderContext) -> str:
        """Render a MetricsGrid matching legacy
        `workspace/regions/metrics.html`: outer `dz-metrics-grid`
        wrapper with `data-dz-tile-count="N"` driving the responsive
        1/2/4 column layout via CSS, then the tile children inline.
        """
        tiles_html = "".join(self._emit(t, ctx) for t in g.tiles)  # type: ignore[arg-type]
        return (
            f'<div class="dz-metrics-grid" data-dz-tile-count="{len(g.tiles)}">{tiles_html}</div>'
        )

    def _emit_activity_feed(self, a: ActivityFeed, ctx: RenderContext) -> str:
        """Render an ActivityFeed matching legacy
        `workspace/regions/activity_feed.html` byte-for-byte: outer
        `<ul class="dz-activity-feed">`, per-row dot SVG + time + bubble.

        The dot SVG is identical across rows (constant). The bubble
        renders an optional `<span class="dz-activity-actor">` when an
        actor is present, then the description as raw text. Click-to-
        drawer wiring (legacy `action_url` → hx-get on the bubble) is
        not yet plumbed through — initial port covers the read-only
        feed shape only; clickable rows are a follow-up.
        """
        if not a.items:
            return f'<div class="dz-activity-empty">{ctx.escape(a.empty_message)}</div>'
        rows: list[str] = []
        for time_str, actor, description in a.items:
            actor_html = (
                f'<span class="dz-activity-actor">{ctx.escape(actor)}</span>' if actor else ""
            )
            rows.append(
                f'<li class="dz-activity-row">'
                f'<span class="dz-activity-dot">'
                f'<svg fill="currentColor" viewBox="0 0 20 20" aria-hidden="true">'
                f'<circle cx="10" cy="10" r="6"/>'
                f"</svg>"
                f"</span>"
                f'<div class="dz-activity-row-inner">'
                f'<div class="dz-activity-time">{ctx.escape(time_str)}</div>'
                f'<div class="dz-activity-bubble" >'
                f"{actor_html}{ctx.escape(description)}"
                f"</div>"
                f"</div>"
                f"</li>"
            )
        return f'<ul class="dz-activity-feed">{"".join(rows)}</ul>'

    def _emit_bullet(self, b: Bullet, ctx: RenderContext) -> str:
        """Render a Bullet matching legacy
        `workspace/regions/bullet.html` byte-for-byte: outer
        `dz-bullet-region` wrapper, per-row label + track (bands behind,
        actual bar, optional target tick) + formatted value, summary
        line "N rows · scale 0–MAX".

        Empty path renders the `dz-empty-dense` fallback inside the
        region wrapper. Reference bands use the same colour map as the
        chart-family SVG helpers (`hsl(var(--primary))` for `target`
        etc.); `from`/`to` positions are rendered as percentage of
        max_value.

        Numeric formatting matches the legacy Jinja `{{ value }}`
        rendering — whole-valued floats narrow to int repr (so 75.0
        renders as "75"), fractional values keep the trailing decimal.
        """
        from dazzle.render.svg import _BAND_COLORS

        if not b.rows or b.max_value <= 0:
            return (
                f'<div class="dz-bullet-region">'
                f'<p class="dz-empty-dense" role="status">'
                f"{ctx.escape(b.empty_message)}</p>"
                f"</div>"
            )

        # Match Jinja's `{{ value }}` rendering: whole floats render
        # without trailing `.0`. Used for tooltip numerics where the
        # legacy template did not apply `round()`.
        def _jinja_num(value: float) -> str:
            return str(int(value)) if value == int(value) else str(value)

        rows_html: list[str] = []
        for row in b.rows:
            actual_pct = round(row.actual / b.max_value * 100, 2)
            bands_html = ""
            for band in b.reference_bands:
                band_left = round(band.from_value / b.max_value * 100, 2)
                band_width = round((band.to_value - band.from_value) / b.max_value * 100, 2)
                colour = _BAND_COLORS.get(band.color, _BAND_COLORS["target"])
                bands_html += (
                    f'<span class="dz-bullet-band" '
                    f'style="left: {band_left}%; width: {band_width}%; '
                    f'background: {colour};" '
                    f'title="{ctx.escape_attr(band.label)}: '
                    f'{_jinja_num(band.from_value)}–{_jinja_num(band.to_value)}"></span>'
                )

            target_html = ""
            # `round(1)` for value display matches `{{ value | round(1) }}`;
            # but Jinja's round renders 75.0 as "75.0" only if the value
            # was already non-int. For ints, round(1) gives an int so
            # "75". Mirror that with _jinja_num after round.
            actual_rounded = round(row.actual, 1)
            value_html = _jinja_num(actual_rounded)
            if row.target is not None:
                target_pct = round(row.target / b.max_value * 100, 2)
                target_html = (
                    f'<span class="dz-bullet-target" '
                    f'style="left: {target_pct}%;" '
                    f'title="{ctx.escape_attr(row.label)} target: '
                    f'{_jinja_num(row.target)}"></span>'
                )
                target_rounded = round(row.target, 1)
                value_html += f" / {_jinja_num(target_rounded)}"

            rows_html.append(
                f'<div class="dz-bullet-row">'
                f'<span class="dz-bullet-label">{ctx.escape(row.label)}</span>'
                f'<div class="dz-bullet-track">'
                f"{bands_html}"
                f'<span class="dz-bullet-actual" '
                f'style="width: {actual_pct}%;" '
                f'title="{ctx.escape_attr(row.label)} actual: '
                f'{_jinja_num(row.actual)}"></span>'
                f"{target_html}"
                f"</div>"
                f'<span class="dz-bullet-value">{value_html}</span>'
                f"</div>"
            )

        return (
            f'<div class="dz-bullet-region">'
            f'<div class="dz-bullet-rows">{"".join(rows_html)}</div>'
            f'<p class="dz-bullet-summary">'
            f"{len(b.rows)} rows · scale 0–{_jinja_num(round(b.max_value, 1))}"
            f"</p>"
            f"</div>"
        )

    def _emit_sparkline(self, s: Sparkline, ctx: RenderContext) -> str:
        """Render a Sparkline matching legacy
        `workspace/regions/sparkline.html` byte-for-byte: outer
        `dz-sparkline-region`, headline showing the latest bucket
        (value + label), and a tiny 180×32 SVG with area fill +
        polyline. Single-point series omit the SVG entirely (matches
        legacy `{% if count > 1 %}` guard). Empty series renders the
        `dz-sparkline-empty` div with the empty message.
        """
        if not s.points:
            return (
                f'<div class="dz-sparkline-region">'
                f'<div class="dz-sparkline-empty">{ctx.escape(s.empty_message)}</div>'
                f"</div>"
            )

        last_label, last_value = s.points[-1]
        # Match Jinja's `{{ value }}` rendering — int repr for whole values.
        last_value_str = str(int(last_value)) if last_value == int(last_value) else str(last_value)
        max_val = max(v for _, v in s.points)
        if max_val <= 0:
            max_val = 1
        max_val_str = str(int(max_val)) if max_val == int(max_val) else str(max_val)
        count = len(s.points)

        headline = (
            f'<div class="dz-sparkline-headline">'
            f'<span class="dz-sparkline-value">{ctx.escape(last_value_str)}</span>'
            f'<span class="dz-sparkline-bucket-label">{ctx.escape(last_label)}</span>'
            f"</div>"
        )

        if count <= 1:
            return f'<div class="dz-sparkline-region">{headline}</div>'

        # 180×32 viewBox with 2px top/bottom padding (no left/right padding).
        w = 180
        h = 32
        pt = 2
        pb = 2
        plot_h = h - pt - pb
        step = w / (count - 1)
        pts = []
        for i, (_, v) in enumerate(s.points):
            x = round(i * step, 2)
            y = round(pt + plot_h - (v / max_val * plot_h), 2)
            pts.append(f"{x},{y}")
        pts_str = " ".join(pts)

        svg = (
            f'<svg xmlns="http://www.w3.org/2000/svg" '
            f'viewBox="0 0 {w} {h}" '
            f'class="dz-sparkline-svg" role="img" '
            f'aria-label="Sparkline — {count} points, latest '
            f'{last_value_str}, peak {max_val_str}">'
            f'<polygon points="0,{h} {pts_str} {w},{h}" '
            f'fill="hsl(var(--primary))" fill-opacity="0.15" stroke="none" />'
            f'<polyline points="{pts_str}" fill="none" '
            f'stroke="hsl(var(--primary))" stroke-width="1.25" '
            f'stroke-linejoin="round" stroke-linecap="round" />'
            f"</svg>"
        )
        return f'<div class="dz-sparkline-region">{headline}{svg}</div>'

    def _emit_tree(self, t: Tree, ctx: RenderContext) -> str:
        """Render a Tree matching legacy `workspace/regions/tree.html`
        byte-for-byte: recursive `<details class="dz-tree-node">` with
        chevron SVG + label + optional child count, top-level depth-0
        nodes open by default.
        """
        if not t.nodes:
            return ""
        return "".join(self._emit_tree_node(n, depth=0, ctx=ctx) for n in t.nodes)

    def _emit_tree_node(self, node: TreeNode, *, depth: int, ctx: RenderContext) -> str:
        open_attr = " open" if depth == 0 else ""
        chevron = (
            '<svg class="dz-tree-chevron" fill="none" viewBox="0 0 24 24" '
            'stroke="currentColor" stroke-width="2" aria-hidden="true">'
            '<path stroke-linecap="round" stroke-linejoin="round" d="M9 5l7 7-7 7"/>'
            "</svg>"
        )
        count_html = (
            f'<span class="dz-tree-count">{len(node.children)}</span>' if node.children else ""
        )
        summary = (
            f'<summary class="dz-tree-summary">'
            f"{chevron}"
            f'<span class="dz-tree-label">{ctx.escape(node.label)}</span>'
            f"{count_html}"
            f"</summary>"
        )
        if node.children:
            children_html = "".join(
                self._emit_tree_node(c, depth=depth + 1, ctx=ctx) for c in node.children
            )
            return (
                f'<details class="dz-tree-node"{open_attr}>'
                f"{summary}"
                f'<div class="dz-tree-children">{children_html}</div>'
                f"</details>"
            )
        return f'<details class="dz-tree-node"{open_attr}>{summary}</details>'

    def _emit_pipeline_steps(self, p: PipelineSteps, ctx: RenderContext) -> str:
        """Render a PipelineSteps row matching legacy
        `workspace/regions/pipeline_steps.html` byte-for-byte:
        outer `dz-pipeline-steps-region`, `<ol class="dz-pipeline-stages">`
        of `<li class="dz-pipeline-stage">` rows with kicker label,
        headline value (or "—"), optional caption, optional progress
        block, and per-non-last-stage connector SVGs (desktop arrow
        + mobile chevron).
        """
        if not p.stages:
            return (
                f'<div class="dz-pipeline-steps-region">'
                f'<p class="dz-empty-dense" role="status">'
                f"{ctx.escape(p.empty_message)}</p>"
                f"</div>"
            )

        last_idx = len(p.stages) - 1
        items: list[str] = []
        for i, stage in enumerate(p.stages):
            value_str = str(stage.value) if stage.value is not None else "—"
            caption_html = (
                f'<span class="dz-pipeline-stage-caption">{ctx.escape(stage.caption)}</span>'
                if stage.caption
                else ""
            )

            progress_html = ""
            if stage.progress is not None:
                overshoot_attr = (
                    ' data-dz-progress-overshoot="true"' if stage.progress_overshoot else ""
                )
                progress_html = (
                    f'<div class="dz-pipeline-stage-progress" '
                    f'data-dz-progress="{stage.progress}"{overshoot_attr} '
                    f'role="progressbar" '
                    f'aria-valuemin="0" aria-valuemax="100" '
                    f'aria-valuenow="{stage.progress}" '
                    f'aria-label="{ctx.escape_attr(stage.label)} progress">'
                    f'<div class="dz-pipeline-stage-progress-track">'
                    f'<div class="dz-pipeline-stage-progress-fill" '
                    f'style="width: {stage.progress}%;"></div>'
                    f"</div>"
                    f'<span class="dz-pipeline-stage-progress-label">'
                    f"{stage.progress}%</span>"
                    f"</div>"
                )

            connector_html = ""
            if i < last_idx:
                connector_html = (
                    '<span class="dz-pipeline-connector" aria-hidden="true">'
                    '<svg width="14" height="14" viewBox="0 0 14 14" fill="none" '
                    'xmlns="http://www.w3.org/2000/svg">'
                    '<path d="M3 1.5L9 7l-6 5.5" stroke="currentColor" '
                    'stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>'
                    "</svg>"
                    "</span>"
                    '<span class="dz-pipeline-connector-mobile" aria-hidden="true">'
                    '<svg width="14" height="14" viewBox="0 0 14 14" fill="none" '
                    'xmlns="http://www.w3.org/2000/svg">'
                    '<path d="M1.5 3L7 9l5.5-6" stroke="currentColor" '
                    'stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>'
                    "</svg>"
                    "</span>"
                )

            items.append(
                f'<li class="dz-pipeline-stage">'
                f'<span class="dz-pipeline-stage-label">{ctx.escape(stage.label)}</span>'
                f'<span class="dz-pipeline-stage-value">{value_str}</span>'
                f"{caption_html}"
                f"{progress_html}"
                f"{connector_html}"
                f"</li>"
            )

        return (
            f'<div class="dz-pipeline-steps-region">'
            f'<ol class="dz-pipeline-stages">{"".join(items)}</ol>'
            f"</div>"
        )

    def _emit_action_grid(self, g: "ActionGrid", ctx: RenderContext) -> str:
        """Render an ActionGrid matching legacy
        `workspace/regions/action_grid.html` byte-for-byte: outer
        `dz-action-grid-region` + `dz-action-grid` wrapper. Empty
        path renders the `dz-empty-dense` fallback inside the region
        wrapper.
        """
        if not g.cards:
            return (
                f'<div class="dz-action-grid-region">'
                f'<p class="dz-empty-dense" role="status">'
                f"{ctx.escape(g.empty_message)}</p>"
                f"</div>"
            )
        cards_html = "".join(self._emit(c, ctx) for c in g.cards)  # type: ignore[arg-type]
        return (
            f'<div class="dz-action-grid-region">'
            f'<div class="dz-action-grid">{cards_html}</div>'
            f"</div>"
        )

    def _emit_kanban_region(self, k: "KanbanRegion", ctx: RenderContext) -> str:
        """Render a KanbanRegion matching legacy
        `workspace/regions/kanban.html` byte-for-byte: outer
        `dz-kanban-board`, per-column head with badge + count, stack
        of cards with title + secondary fields + optional attention
        tag, optional overflow row with Load all button.

        Empty path renders the legacy `fragments/empty_state.html` shape.
        """
        from dazzle.back.runtime.renderers.region_adapter import (
            _render_status_badge_html,
        )

        if not k.columns:
            label = k.empty_message or "No items found."
            return (
                f'<div class="dz-empty-state" data-dz-empty-kind="read-only" role="status">'
                f'<svg class="dz-empty-state-icon" fill="none" stroke="currentColor" '
                f'viewBox="0 0 24 24" aria-hidden="true">'
                f'<path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" '
                f'd="M20 13V6a2 2 0 00-2-2H6a2 2 0 00-2 2v7m16 0v5a2 2 0 01-2 2H6a2 2 0 01-2-2v-5m16 0h-2.586a1 1 0 00-.707.293l-2.414 2.414a1 1 0 01-.707.293h-2.172a1 1 0 01-.707-.293l-2.414-2.414A1 1 0 006.586 13H4"/>'
                f"</svg>"
                f'<p class="dz-empty-state-message">{ctx.escape(label)}</p>'
                f"</div>"
            )

        column_html: list[str] = []
        total_cards = 0
        for col in k.columns:
            cards_html: list[str] = []
            for card in col.cards:
                fields_html = ""
                for label, value in card.fields:
                    if isinstance(value, str):
                        value_html = ctx.escape(value)
                    else:
                        value_html = self._emit(value, ctx)  # type: ignore[arg-type]
                    fields_html += (
                        f'<p class="dz-kanban-card-field">'
                        f"<span>{ctx.escape(label)}:</span> "
                        f"{value_html}"
                        f"</p>"
                    )
                attn_html = ""
                if card.attention_level:
                    attn_html = (
                        f'<p class="dz-kanban-card-attn" '
                        f'data-dz-attn="{ctx.escape_attr(card.attention_level)}">'
                        f"{ctx.escape(card.attention_message)}</p>"
                    )
                # Trailing space inside `class="dz-kanban-card "` mirrors
                # legacy `class="dz-kanban-card{% if action_url %} is-clickable{% endif %}"`
                # Jinja whitespace artifact when action_url is empty.
                cards_html.append(
                    f'<div class="dz-kanban-card">'
                    f'<div class="dz-kanban-card-body">'
                    f'<h4 class="dz-kanban-card-title">{ctx.escape(card.title)}</h4>'
                    f"{fields_html}"
                    f"{attn_html}"
                    f"</div>"
                    f"</div>"
                )
            stack_inner = "".join(cards_html)
            if not col.cards:
                stack_inner = '<p class="dz-kanban-empty">No items</p>'
            badge_html = _render_status_badge_html(col.label)
            column_html.append(
                f'<div class="dz-kanban-column">'
                f'<div class="dz-kanban-column-head">'
                f"{badge_html}"
                f'<span class="dz-kanban-column-count">{len(col.cards)}</span>'
                f"</div>"
                f'<div class="dz-kanban-stack">{stack_inner}</div>'
                f"</div>"
            )
            total_cards += len(col.cards)

        overflow_html = ""
        if k.total > total_cards:
            overflow_html = (
                f'<div class="dz-kanban-overflow">'
                f'<p class="dz-kanban-overflow-text">'
                f"Showing {total_cards} of {k.total}"
                f"</p>"
                f'<button type="button" class="dz-kanban-load-all" '
                f'hx-get="{ctx.escape_attr(k.endpoint)}?page_size={k.total}" '
                f'hx-target="closest [data-dz-region]" '
                f'hx-swap="outerHTML">Load all</button>'
                f"</div>"
            )

        return f'<div class="dz-kanban-board">{"".join(column_html)}</div>{overflow_html}'

    def _emit_funnel(self, f: "Funnel", ctx: RenderContext) -> str:
        """Render a Funnel matching legacy
        `workspace/regions/funnel_chart.html` byte-for-byte: outer
        `dz-funnel-chart-region`, `dz-funnel-stages` of `dz-funnel-stage-row`
        items. Width is calculated from the first stage's count and
        clamped to a 20% minimum. `data-dz-funnel-step` is the stage
        index capped at 7.
        """
        if not f.stages:
            return (
                f'<div class="dz-funnel-chart-region">'
                f'<p class="dz-empty-dense" role="status">'
                f"{ctx.escape(f.empty_message)}</p>"
                f"</div>"
            )

        base = f.stages[0].count if f.stages[0].count > 0 else 1
        items: list[str] = []
        for i, stage in enumerate(f.stages):
            pct = int(stage.count / base * 100)
            width = pct if pct >= 20 else 20
            step = i if i < 8 else 7
            items.append(
                f'<div class="dz-funnel-stage-row">'
                f'<div class="dz-funnel-stage" '
                f'data-dz-funnel-step="{step}" '
                f'style="width: {width}%;">'
                f'<span class="dz-funnel-stage-label">{ctx.escape(stage.label)}</span> '
                f'<span class="dz-funnel-stage-count">({stage.count})</span>'
                f"</div>"
                f"</div>"
            )

        return (
            f'<div class="dz-funnel-chart-region">'
            f'<div class="dz-funnel-stages">{"".join(items)}</div>'
            f'<p class="dz-funnel-summary">{f.total} total</p>'
            f"</div>"
        )

    def _emit_queue_region(self, q: "QueueRegion", ctx: RenderContext) -> str:
        """Render a QueueRegion matching legacy
        `workspace/regions/queue.html` byte-for-byte: outer
        `dz-queue-region`, optional count row + metrics row, then
        the queue items list with per-row attention accent +
        headline (title + badges) + optional attn message + date
        secondaries + transition action buttons.

        Empty path renders `<p class="dz-empty-dense dz-queue-empty">`
        — note the legacy template uses BOTH classes.
        """
        from dazzle.back.runtime.renderers.region_adapter import (
            _render_status_badge_html,
        )

        if not q.rows:
            return (
                f'<div class="dz-queue-region">'
                f'<p class="dz-empty-dense dz-queue-empty" role="status">'
                f"{ctx.escape(q.empty_message)}</p>"
                f"</div>"
            )

        count_row = ""
        if q.total > 0:
            count_row = (
                f'<div class="dz-queue-count-row">'
                f'<span class="dz-queue-count">{q.total}</span>'
                f"</div>"
            )

        metrics_row = ""
        if q.metrics:
            metric_items = "".join(
                f'<div class="dz-queue-metric">'
                f'<div class="dz-queue-metric-value">{ctx.escape(m.value)}</div>'
                f'<div class="dz-queue-metric-label">{ctx.escape(m.label)}</div>'
                f"</div>"
                for m in q.metrics
            )
            metrics_row = f'<div class="dz-queue-metrics">{metric_items}</div>'

        rows_html: list[str] = []
        for row in q.rows:
            attn_class = ""
            attn_data_attr = ""
            attn_message_html = ""
            if row.attention_level:
                attn_class = f"dz-attn-both dz-attn-tone-{row.attention_level}"
                attn_data_attr = f' data-dz-attn="{ctx.escape_attr(row.attention_level)}"'
                attn_message_html = (
                    f'<p class="dz-queue-row-attn">{ctx.escape(row.attention_message)}</p>'
                )

            badges_html = "".join(_render_status_badge_html(b.value) for b in row.badges)
            headline_html = (
                f'<div class="dz-queue-row-headline">'
                f'<span class="dz-queue-row-title">{ctx.escape(row.title)}</span>'
                f"{badges_html}"
                f"</div>"
            )

            date_html = "".join(
                f'<span class="dz-queue-row-date">'
                f"{ctx.escape(d.label)}: {ctx.escape(d.timeago_str)}"
                f"</span>"
                for d in row.date_columns
            )

            actions_html = ""
            applicable = [t for t in q.transitions if t.to_state != row.current_status]
            if applicable and q.queue_status_field and q.queue_api_endpoint:
                buttons = "".join(
                    f'<button type="button" '
                    f'class="dz-queue-action" '
                    f'hx-put="{ctx.escape_attr(q.queue_api_endpoint)}/'
                    f'{ctx.escape_attr(row.row_id)}" '
                    f'hx-vals=\'{{"{q.queue_status_field}": '
                    f'"{t.to_state}"}}\' '
                    f'hx-ext="json-enc" '
                    f'hx-target="#region-{ctx.escape_attr(q.region_name)}" '
                    f'hx-swap="innerHTML">'
                    f"{ctx.escape(t.label)}"
                    f"</button>"
                    for t in applicable
                )
                actions_html = (
                    f'<div class="dz-queue-row-actions" '
                    f'onclick="event.stopPropagation()">'
                    f"{buttons}"
                    f"</div>"
                )

            # Trailing space inside `class="dz-queue-row "` mirrors
            # legacy Jinja interpolation when no attn is present.
            row_open_class = f"dz-queue-row {attn_class}" if attn_class else "dz-queue-row "
            # Same artifact for `class="dz-queue-row-main "`.
            rows_html.append(
                f'<div class="{row_open_class}"{attn_data_attr}>'
                f'<div class="dz-queue-row-main ">'
                f"{headline_html}"
                f"{attn_message_html}"
                f"{date_html}"
                f"</div>"
                f"{actions_html}"
                f"</div>"
            )

        rows_block = f'<div class="dz-queue-rows">{"".join(rows_html)}</div>'

        overflow_html = ""
        if q.total > len(q.rows):
            overflow_html = f'<p class="dz-queue-overflow">Showing {len(q.rows)} of {q.total}</p>'

        return (
            f'<div class="dz-queue-region">'
            f"{count_row}"
            f"{metrics_row}"
            f"{rows_block}"
            f"{overflow_html}"
            f"</div>"
        )

    def _emit_pivot_table_region(self, p: "PivotTableRegion", ctx: RenderContext) -> str:
        """Render a PivotTableRegion matching legacy
        `workspace/regions/pivot_table.html` byte-for-byte: outer
        `dz-pivot-region`, `dz-pivot-scroll` + `<table class="dz-pivot-grid">`.
        Header has N dimension `<th>` cells + M measure `<th class="is-measure">`
        cells (humanized from measure_keys). Per-row dimension cells
        use FK label fallback for `is_fk=True` specs and status_badge
        rendering for non-FK specs (em-dash placeholder for None).
        Measure cells render raw values with `.is-measure` class.
        Summary line "{N} row(s)".
        """
        from dazzle.back.runtime.renderers.region_adapter import (
            _render_status_badge_html,
        )

        if not p.rows:
            return (
                f'<div class="dz-pivot-region">'
                f'<p class="dz-empty-dense" role="status">'
                f"{ctx.escape(p.empty_message)}</p>"
                f"</div>"
            )

        # Header — dim columns then measure columns.
        head_dim = "".join(f"<th>{ctx.escape(s.label)}</th>" for s in p.dim_specs)
        head_measure = "".join(
            f'<th class="is-measure">{ctx.escape(k.replace("_", " ").title())}</th>'
            for k in p.measure_keys
        )
        thead = f"<thead><tr>{head_dim}{head_measure}</tr></thead>"

        body_rows: list[str] = []
        for row in p.rows:
            cells_html = ""
            for spec in p.dim_specs:
                if spec.is_fk:
                    fk_label = row.get(f"{spec.name}_label")
                    if fk_label is None:
                        # Fallback: raw spec.name value, em-dash if also None.
                        sval = row.get(spec.name)
                        cells_html += f"<td>{ctx.escape(str(sval)) if sval else '—'}</td>"
                    else:
                        cells_html += f"<td>{ctx.escape(str(fk_label))}</td>"
                else:
                    sval = row.get(spec.name)
                    if sval is None:
                        cells_html += '<td><span class="dz-pivot-null">—</span></td>'
                    else:
                        cells_html += f"<td>{_render_status_badge_html(sval, size='sm')}</td>"
            for k in p.measure_keys:
                v = row.get(k)
                cells_html += f'<td class="is-measure">{ctx.escape(str(v))}</td>'
            body_rows.append(f"<tr>{cells_html}</tr>")
        tbody = f"<tbody>{''.join(body_rows)}</tbody>"

        n = len(p.rows)
        suffix = "" if n == 1 else "s"
        summary = f'<p class="dz-pivot-summary">{n} row{suffix}</p>'

        return (
            f'<div class="dz-pivot-region">'
            f'<div class="dz-pivot-scroll">'
            f'<table class="dz-pivot-grid">{thead}{tbody}</table>'
            f"</div>"
            f"{summary}"
            f"</div>"
        )

    def _emit_heatmap(self, h: "Heatmap", ctx: RenderContext) -> str:
        """Render a Heatmap matching legacy
        `workspace/regions/heatmap.html` byte-for-byte: outer
        `dz-heatmap-region` wrapping a `dz-heatmap-scroll` with a
        `<table class="dz-heatmap-grid">`. Headers row has an empty
        leading `<th></th>` followed by column labels. Each row carries
        a label `<td class="dz-heatmap-row-label">` then per-cell
        `<td class="dz-heatmap-cell">` with `data-dz-heatmap-tone`
        threshold-banded tone (bad / warn / good). Values formatted
        as `%.1f`. Optional overflow line.
        """
        if not h.rows:
            return (
                f'<div class="dz-heatmap-region">'
                f'<p class="dz-empty-dense" role="status">'
                f"{ctx.escape(h.empty_message)}</p>"
                f"</div>"
            )

        head_cols = "".join(f"<th>{ctx.escape(c)}</th>" for c in h.columns)
        thead = f"<thead><tr><th></th>{head_cols}</tr></thead>"

        def _tone_attr(value: float) -> str:
            n = len(h.thresholds)
            if n >= 2:
                if value < h.thresholds[0]:
                    return ' data-dz-heatmap-tone="bad"'
                if value < h.thresholds[1]:
                    return ' data-dz-heatmap-tone="warn"'
                return ' data-dz-heatmap-tone="good"'
            if n == 1:
                if value < h.thresholds[0]:
                    return ' data-dz-heatmap-tone="bad"'
                return ' data-dz-heatmap-tone="good"'
            return ""

        body_rows: list[str] = []
        for row in h.rows:
            cells_html = ""
            for cell in row.cells:
                cells_html += f'<td class="dz-heatmap-cell"{_tone_attr(cell)}> {cell:.1f} </td>'
            body_rows.append(
                f"<tr>"
                f'<td class="dz-heatmap-row-label">{ctx.escape(row.label)}</td>'
                f"{cells_html}"
                f"</tr>"
            )
        tbody = f"<tbody>{''.join(body_rows)}</tbody>"

        overflow_html = ""
        if h.total > len(h.rows):
            overflow_html = f'<p class="dz-heatmap-overflow">Showing {len(h.rows)} of {h.total}</p>'

        return (
            f'<div class="dz-heatmap-region">'
            f'<div class="dz-heatmap-scroll">'
            f'<table class="dz-heatmap-grid">{thead}{tbody}</table>'
            f"</div>"
            f"{overflow_html}"
            f"</div>"
        )

    def _emit_histogram(self, h: "Histogram", ctx: RenderContext) -> str:
        """Render a Histogram matching legacy
        `workspace/regions/histogram.html` byte-for-byte: outer
        `dz-histogram-region` wrapping the SVG (via `histogram_svg`)
        and a `dz-histogram-summary` line "{count} bins · {total}
        samples · peak {max_count}". Empty path renders the
        `dz-empty-dense` fallback inside the region wrapper.
        """
        from dazzle.render.svg import histogram_svg

        if not h.bins:
            return (
                f'<div class="dz-histogram-region">'
                f'<p class="dz-empty-dense" role="status">'
                f"{ctx.escape(h.empty_message)}</p>"
                f"</div>"
            )

        svg_bins = tuple((b.label, b.count, b.low, b.high) for b in h.bins)
        svg = histogram_svg(h.label, svg_bins, reference_lines=h.reference_lines)
        total = sum(b.count for b in h.bins)
        max_count = max(b.count for b in h.bins) or 1
        summary = (
            f'<p class="dz-histogram-summary">'
            f"{len(h.bins)} bins · {total} samples · peak {max_count}"
            f"</p>"
        )
        return f'<div class="dz-histogram-region">{svg}{summary}</div>'

    def _emit_list_region(self, lst: "ListRegion", ctx: RenderContext) -> str:
        """Render a ListRegion matching legacy
        `workspace/regions/list.html` byte-for-byte: outer
        `dz-list-region`, action row with always-emitted CSV button,
        `<div class="dz-list-scroll">` of `<table class="dz-list-table">`,
        optional overflow line. Filter chrome / sortable headers /
        click-through wiring deferred to follow-up — read-only basic
        case here.
        """
        # Action row — CSV button always rendered (legacy behaviour).
        csv_button = (
            f'<button type="button" '
            f'data-dz-csv-endpoint="{ctx.escape_attr(lst.csv_endpoint)}" '
            f'data-dz-csv-filename="{ctx.escape_attr(lst.csv_filename)}" '
            f'onclick="window.dz.downloadCsv(this.dataset.dzCsvEndpoint, this.dataset.dzCsvFilename)" '
            f'class="dz-list-csv-button" title="Export CSV" aria-label="Export CSV">'
            f'<svg fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">'
            f'<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" '
            f'd="M12 10v6m0 0l-3-3m3 3l3-3m2 8H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"/>'
            f"</svg>"
            f"</button>"
        )
        actions_row = (
            f'<div class="dz-list-actions">'
            f'<div class="dz-list-action-group">{csv_button}</div>'
            f"</div>"
        )

        if not lst.rows:
            # Legacy empty state via fragments/empty_state.html — match
            # the read-only shape with the fixed icon + message.
            label = lst.empty_message or "No items found."
            empty_html = (
                f'<div class="dz-empty-state" data-dz-empty-kind="read-only" role="status">'
                f'<svg class="dz-empty-state-icon" fill="none" stroke="currentColor" '
                f'viewBox="0 0 24 24" aria-hidden="true">'
                f'<path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" '
                f'd="M20 13V6a2 2 0 00-2-2H6a2 2 0 00-2 2v7m16 0v5a2 2 0 01-2 2H6a2 2 0 01-2-2v-5m16 0h-2.586a1 1 0 00-.707.293l-2.414 2.414a1 1 0 01-.707.293h-2.172a1 1 0 01-.707-.293l-2.414-2.414A1 1 0 006.586 13H4"/>'
                f"</svg>"
                f'<p class="dz-empty-state-message">{ctx.escape(label)}</p>'
                f"</div>"
            )
            return f'<div class="dz-list-region">{actions_row}{empty_html}</div>'

        thead = (
            "<thead><tr>"
            + "".join(f"<th>{ctx.escape(c.label)}</th>" for c in lst.columns)
            + "</tr></thead>"
        )

        tbody_rows: list[str] = []
        for row in lst.rows:
            cells_html = ""
            for cell in row:
                if isinstance(cell, str):
                    cells_html += f"<td>{ctx.escape(cell)}</td>"
                else:
                    cells_html += f"<td>{self._emit(cell, ctx)}</td>"  # type: ignore[arg-type]
            # Trailing space on `class="dz-list-row "` mirrors legacy
            # `class="dz-list-row {{ attention_classes(...) }}{% if action_url %} is-clickable{% endif %}"`
            # for the no-attention, no-action_url case.
            tbody_rows.append(f'<tr class="dz-list-row ">{cells_html}</tr>')
        tbody = f"<tbody>{''.join(tbody_rows)}</tbody>"

        table = (
            f'<div class="dz-list-scroll"><table class="dz-list-table">{thead}{tbody}</table></div>'
        )

        overflow_html = ""
        if lst.total > len(lst.rows):
            overflow_html = (
                f'<p class="dz-list-overflow">Showing {len(lst.rows)} of {lst.total}</p>'
            )

        return f'<div class="dz-list-region">{actions_row}{table}{overflow_html}</div>'

    def _emit_grid_region(self, g: "GridRegion", ctx: RenderContext) -> str:
        """Render a GridRegion matching legacy
        `workspace/regions/grid.html` byte-for-byte: outer
        `dz-grid-region`, `<div class="dz-grid-list">` with per-cell
        `<div class="dz-grid-cell">` containing `<h4>` title +
        per-field `<p class="dz-grid-cell-field">` lines. Empty path
        renders the legacy empty-state fragment shape.
        """
        if not g.cells:
            # Empty state matches `fragments/empty_state.html` —
            # SVG icon + message + optional CTA. The CTA needs an
            # entity_name + create_url which the primitive doesn't
            # carry yet; for now emit the read-only empty state with
            # the message only. CTA support is a follow-up when the
            # primitive gains the appropriate fields.
            label = g.empty_message or "No items found."
            return (
                f'<div class="dz-grid-region">'
                f'<div class="dz-empty-state" data-dz-empty-kind="read-only" role="status">'
                f'<svg class="dz-empty-state-icon" fill="none" stroke="currentColor" '
                f'viewBox="0 0 24 24" aria-hidden="true">'
                f'<path stroke-linecap="round" stroke-linejoin="round" '
                f'stroke-width="1.5" '
                f'd="M20 13V6a2 2 0 00-2-2H6a2 2 0 00-2 2v7m16 0v5a2 2 0 01-2 2H6a2 2 0 01-2-2v-5m16 0h-2.586a1 1 0 00-.707.293l-2.414 2.414a1 1 0 01-.707.293h-2.172a1 1 0 01-.707-.293l-2.414-2.414A1 1 0 006.586 13H4"/>'
                f"</svg>"
                f'<p class="dz-empty-state-message">{ctx.escape(label)}</p>'
                f"</div>"
                f"</div>"
            )

        cells_html: list[str] = []
        for cell in g.cells:
            fields_html = ""
            for label, value in cell.fields:
                if isinstance(value, str):
                    value_html = ctx.escape(value)
                else:
                    value_html = self._emit(value, ctx)  # type: ignore[arg-type]
                fields_html += (
                    f'<p class="dz-grid-cell-field">'
                    f'<span class="dz-grid-cell-field-label">{ctx.escape(label)}:</span> '
                    f"{value_html}"
                    f"</p>"
                )
            # Trailing space inside `class="dz-grid-cell "` matches the
            # legacy `class="dz-grid-cell {{ attention_classes(...) }}"`
            # rendering when attention is empty — Jinja interpolates ""
            # leaving the space. Preserve it for byte-equivalence.
            cells_html.append(
                f'<div class="dz-grid-cell ">'
                f'<h4 class="dz-grid-cell-title">{ctx.escape(cell.title)}</h4>'
                f"{fields_html}"
                f"</div>"
            )

        return (
            f'<div class="dz-grid-region">'
            f'<div class="dz-grid-list">{"".join(cells_html)}</div>'
            f"</div>"
        )

    def _emit_status_list(self, s: StatusList, ctx: RenderContext) -> str:
        """Render a StatusList matching legacy
        `workspace/regions/status_list.html` byte-for-byte: outer
        `dz-status-list-region` wrapper, `<ul class="dz-status-list"
        data-dz-entry-count="N">` with per-row `data-dz-state` attr,
        icon column (or spacer), title + optional caption, pill for
        non-neutral states.

        Empty state renders the `dz-empty-dense` paragraph inside the
        region wrapper, matching the legacy template's else branch.
        """
        if not s.entries:
            return (
                f'<div class="dz-status-list-region">'
                f'<p class="dz-empty-dense" role="status">'
                f"{ctx.escape(s.empty_message)}</p>"
                f"</div>"
            )

        rows: list[str] = []
        for entry in s.entries:
            if entry.icon:
                icon_html = (
                    f'<span class="dz-status-list-icon" '
                    f'data-lucide="{ctx.escape_attr(entry.icon)}" '
                    f'aria-hidden="true"></span>'
                )
            else:
                icon_html = '<span class="dz-status-list-icon-spacer" aria-hidden="true"></span>'

            caption_html = (
                f'<div class="dz-status-list-caption">{ctx.escape(entry.caption)}</div>'
                if entry.caption
                else ""
            )

            pill_html = (
                f'<span class="dz-status-list-pill">{ctx.escape(entry.state)}</span>'
                if entry.state != "neutral"
                else ""
            )

            rows.append(
                f'<li class="dz-status-list-entry" '
                f'data-dz-state="{ctx.escape_attr(entry.state)}">'
                f"{icon_html}"
                f'<div class="dz-status-list-text">'
                f'<div class="dz-status-list-title">{ctx.escape(entry.title)}</div>'
                f"{caption_html}"
                f"</div>"
                f"{pill_html}"
                f"</li>"
            )

        return (
            f'<div class="dz-status-list-region">'
            f'<ul class="dz-status-list" data-dz-entry-count="{len(s.entries)}">'
            f"{''.join(rows)}"
            f"</ul>"
            f"</div>"
        )

    def _emit_detail_grid(self, g: DetailGrid, ctx: RenderContext) -> str:
        """Render a DetailGrid matching legacy
        `workspace/regions/detail.html`: outer `dz-detail-region`
        wrapper, `dz-detail-region-grid` definition list, and per-row
        `<dt class="dz-detail-label">` / `<dd class="dz-detail-value">`
        pairs.

        The value fragment renders inline inside the `<dd>` — Badge,
        Text, Link, etc. Per-type rendering (badge / bool / date /
        currency / ref) is the adapter's responsibility — this
        primitive just lays out the dt/dd grid structure.
        """
        rows_html = "".join(
            f'<dt class="dz-detail-label">{ctx.escape(label)}</dt>'
            f'<dd class="dz-detail-value">{self._emit(value, ctx)}</dd>'  # type: ignore[arg-type]
            for label, value in g.rows
        )
        return (
            f'<div class="dz-detail-region">'
            f'<dl class="dz-detail-region-grid">{rows_html}</dl>'
            f"</div>"
        )

    def _emit_bar_track(self, b: BarTrack, ctx: RenderContext) -> str:
        """Render a BarTrack matching legacy `workspace/regions/bar_track.html`
        byte-for-byte: outer `dz-bar-track-region` wrapper, per-row track
        with ARIA progressbar semantics, summary line, and optional
        reference annotations.

        Phase 4B.1.c (bar-track variant): added the outer
        `<div class="dz-bar-track-region">` wrapper so the emit matches
        the legacy template structurally — completes the chart family
        port. The references block (BEM `__references`) rides along
        outside the region wrapper, consistent with TimeSeries / BoxPlot
        / BarChart — references are a Phase 4B-only programmatic-data
        layer with no legacy template equivalent.
        """

        # Match Jinja's `{{ value }}` rendering — int repr for whole values.
        def _num(v: float) -> str:
            return str(int(v)) if v == int(v) else str(v)

        max_str = _num(b.max_value)
        rows_html = "".join(
            f'<div class="dz-bar-track-row">'
            f'<span class="dz-bar-track-label" title="{ctx.escape_attr(label)}">'
            f"{ctx.escape(label)}</span>"
            f'<div class="dz-bar-track" role="progressbar" '
            f'aria-valuemin="0" '
            f'aria-valuemax="{max_str}" '
            f'aria-valuenow="{_num(value)}" '
            f'aria-label="{ctx.escape_attr(label)}: {ctx.escape_attr(formatted)}">'
            f'<span class="dz-bar-track-fill" '
            f'style="width: {_num(round(fill_pct, 2))}%;" '
            f'title="{ctx.escape_attr(label)}: {ctx.escape_attr(formatted)}"></span>'
            f"</div>"
            f'<span class="dz-bar-track-value">{ctx.escape(formatted)}</span>'
            f"</div>"
            for label, value, formatted, fill_pct in b.rows
        )
        refs = _render_references("dz-bar-track", b.reference_lines, b.reference_bands, ctx)
        max_rounded = round(b.max_value, 2)
        max_summary = str(int(max_rounded)) if max_rounded == int(max_rounded) else str(max_rounded)
        return (
            f'<div class="dz-bar-track-region">'
            f'<div class="dz-bar-track-rows">{rows_html}</div>'
            f'<p class="dz-bar-track-summary">'
            f"{len(b.rows)} rows · scale 0–{max_summary}"
            f"</p>"
            f"</div>"
            f"{refs}"
        )

    def _emit_stage_bar(self, s: StageBar, ctx: RenderContext) -> str:
        """Render a StageBar matching legacy
        `workspace/regions/progress.html` byte-for-byte: outer
        `dz-progress-region` wrapper, header `<progress>` + percent
        readout, chip list of stages with per-chip tone (complete /
        active / empty), and an optional "N of M complete" summary.
        """
        # Match Jinja's `{{ complete_pct }}` rendering: int values
        # render without trailing `.0`, floats render as-is. The
        # adapter coerces to float for type safety; the renderer
        # narrows back to int when the value is whole so byte-
        # equivalence holds for the common round-percentage case.
        pct = s.complete_pct
        pct_str = str(int(pct)) if pct == int(pct) else str(pct)

        chips_html = "".join(
            f'<span class="dz-progress-chip" '
            f'data-dz-stage-tone="{("complete" if complete else ("active" if count > 0 else "empty"))}">'
            f"{ctx.escape(name)} ({count})"
            f"</span>"
            for name, count, complete in s.stages
        )
        summary_html = (
            f'<p class="dz-progress-summary">{s.complete_count} of {s.total} complete</p>'
            if s.total > 0
            else ""
        )
        return (
            f'<div class="dz-progress-region">'
            f'<div class="dz-progress-header">'
            f'<progress data-dz-progress value="{pct_str}" max="100"></progress>'
            f"<span>{pct_str}%</span>"
            f"</div>"
            f'<div class="dz-progress-stages">{chips_html}</div>'
            f"{summary_html}"
            f"</div>"
        )
