"""FragmentRenderer — emits HTML from Fragment trees.

Single-class renderer. The `render` method match-dispatches on the Fragment
union; per-primitive emit methods produce HTML strings. The match block is
the runtime exhaustiveness check — adding a new primitive without adding a
match arm causes mypy to flag the unreachable case (with `--strict`) and
the test_fragment_exhaustiveness test to fail.
"""

from dazzle.render.fragment.context import RenderContext
from dazzle.render.fragment.errors import FragmentError
from dazzle.render.fragment.escape import (
    RawHTML,
    Script,
    Slot,
    Stylesheet,
    _attr_escape,
    _close_script_tag_safe,
)
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
    ColumnVisibilityMenu,
    Combobox,
    ConfirmGate,
    CreateButton,
    CsvExportButton,
    DashboardCard,
    DashboardGrid,
    DataListScroll,
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
    ListFilterBar,
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
    TimeSeries,
    Toolbar,
    Topbar,
    Tree,
    WorkspaceContextSelector,
    WorkspaceDrawer,
    WorkspaceShell,
    WorkspaceToolbar,
)

# Cross-arm helpers extracted to ._helpers in #1064 PR 2 (v0.67.137).
# Internal `self._hx_attrs(...)` / `self._pagination_pages(...)` /
# `self._render_references(...)` call sites updated to call the
# module-level forms directly — they never used `self`.
from dazzle.render.fragment.renderer._render_charts import _RenderChartsMixin
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
from dazzle.render.fragment.renderer._render_tables import _RenderTablesMixin


class FragmentRenderer(
    _RenderChartsMixin,
    _RenderDashboardMixin,
    _RenderFormsMixin,
    _RenderInteractiveMixin,
    _RenderLayoutMixin,
    _RenderShellMixin,
    _RenderTablesMixin,
):
    """Emit HTML from a Fragment tree.

    Stateless — a single instance can be reused across requests. The
    RenderContext is per-render-call and threads tokens through descent.
    """

    def render(self, fragment: Fragment, ctx: RenderContext | None = None) -> str:
        from dazzle.perf.tracer import dazzle_span

        ctx = ctx if ctx is not None else RenderContext()
        with dazzle_span("fragment.emit", fragment_kind=type(fragment).__name__):
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
            # Assets (#1130)
            case Script():
                return self._emit_script(fragment, ctx)
            case Stylesheet():
                return self._emit_stylesheet(fragment, ctx)
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
            case DataListScroll():
                return self._emit_data_list_scroll(fragment, ctx)
            case ColumnVisibilityMenu():
                return self._emit_column_visibility_menu(fragment, ctx)
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
            case ListFilterBar():
                return self._emit_list_filter_bar(fragment, ctx)
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

    def _emit_script(self, script: Script, ctx: RenderContext) -> str:
        """#1130: render ``<script>`` with optional src/inline-body + CSP nonce.

        ``__post_init__`` already validated mutual exclusivity of
        ``src`` / ``body``, so the branches here are exhaustive.
        Nonce auto-fill from ``ctx.csp_nonce`` when the primitive's own
        ``nonce`` is None — projects that thread a per-request nonce
        through ``RenderContext`` get strict-CSP compliance for free.
        """
        attrs: list[str] = []
        if script.type:
            attrs.append(f'type="{_attr_escape(script.type)}"')
        if script.defer:
            attrs.append("defer")
        if script.async_:
            attrs.append("async")
        nonce = script.nonce if script.nonce is not None else getattr(ctx, "csp_nonce", None)
        if nonce:
            attrs.append(f'nonce="{_attr_escape(nonce)}"')

        if script.src is not None:
            attrs.append(f'src="{_attr_escape(script.src)}"')
            # #1136: SRI + CORS on external scripts only (Script
            # __post_init__ rejects them on inline bodies).
            if script.integrity is not None:
                attrs.append(f'integrity="{_attr_escape(script.integrity)}"')
            if script.crossorigin is not None:
                attrs.append(f'crossorigin="{_attr_escape(script.crossorigin)}"')
            return f"<script {' '.join(attrs)}></script>"

        assert script.body is not None  # by __post_init__
        safe_body = _close_script_tag_safe(script.body)
        return f"<script {' '.join(attrs)}>{safe_body}</script>"

    def _emit_stylesheet(self, sheet: Stylesheet, ctx: RenderContext) -> str:
        """#1130: render ``<link rel="stylesheet">`` (external) or
        ``<style>`` (inline). Media attribute emitted when not the
        default ``"all"``."""
        media_attr = ""
        if sheet.media and sheet.media != "all":
            media_attr = f' media="{_attr_escape(sheet.media)}"'

        if sheet.href is not None:
            return f'<link rel="stylesheet" href="{_attr_escape(sheet.href)}"{media_attr}>'

        assert sheet.body is not None  # by __post_init__
        # Inline CSS: closing-tag injection isn't as load-bearing as
        # </script>, but parallel the defensive replace for consistency.
        safe_body = sheet.body.replace("</style>", "<\\/style>")
        return f"<style{media_attr}>{safe_body}</style>"
