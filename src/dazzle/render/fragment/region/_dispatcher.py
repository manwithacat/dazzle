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
from typing import Any, Literal, cast

from dazzle.render.fragment import (
    Fragment,
)

# Cross-cutting helpers extracted to ._shared in #1065 PR 2 (v0.67.129).
# Re-imported here so the dispatcher's internal call sites keep working
# unchanged. The public re-export of `_render_status_badge_html` for
# external callers (renderer.py × 4 sites) lives in `__init__.py`.
from dazzle.render.fragment.region._builders_cards import (
    _BuildersCardsMixin,
)
from dazzle.render.fragment.region._builders_charts import (
    _BuildersChartsMixin,
)
from dazzle.render.fragment.region._builders_metrics import (
    _BuildersMetricsMixin,
)
from dazzle.render.fragment.region._builders_misc import (
    _BuildersMiscMixin,
)
from dazzle.render.fragment.region._builders_tables import (
    _BuildersTablesMixin,
)
from dazzle.render.fragment.region._builders_timeline import (
    _BuildersTimelineMixin,
)
from dazzle.render.fragment.region._context import RegionContext
from dazzle.render.fragment.region._shared import (  # noqa: F401
    _region_title,
    _render_status_badge_html,
    _render_typed_value,
    _wrap_surface,
)

_log = logging.getLogger(__name__)


class WorkspaceRegionAdapter(
    _BuildersCardsMixin,
    _BuildersChartsMixin,
    _BuildersMetricsMixin,
    _BuildersMiscMixin,
    _BuildersTablesMixin,
    _BuildersTimelineMixin,
):
    """Translate a WorkspaceRegion + ctx into a Fragment tree.

    Dispatch is table-driven: `_BUILDERS` maps display values to
    methods, `_ALIASES` redirects shared shapes (e.g. `histogram`
    renders the same as `bar_chart`). `_TIMESERIES_VIEWS` is the
    one special case — line/area/sparkline share `_build_time_series`
    but pass a `view` argument that the others don't.

    Every `_build_*` method lives in a family mixin (`_BuildersCardsMixin`,
    `_BuildersChartsMixin`, `_BuildersMetricsMixin`, `_BuildersMiscMixin`,
    `_BuildersTablesMixin`, `_BuildersTimelineMixin`). The dispatcher only
    owns the dispatch tables (`_BUILDERS`, `_ALIASES`, `_TIMESERIES_VIEWS`)
    and the `build()` method that threads them. Family extraction landed
    across #1065 PRs 3–8; Python's MRO + `getattr(self, method_name)`
    dispatch ties it all back together transparently to external callers.
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
        "comparison": "_build_comparison",  # #1470 ranked league
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

    def build(
        self,
        region: Any,
        ctx: dict[str, Any],
        display_override: str | None = None,
    ) -> Fragment:
        """Dispatch on `region.display` to the right primitive.

        Resolves aliases first, then looks up the canonical builder.
        Adding a new display value is one entry in `_BUILDERS` (or
        `_ALIASES` for a redirect) — no if-chain edits required.

        `display_override` lets the caller force a specific display
        value when post-inference promotion has changed the effective
        display (e.g. EX-047 promotes a region with `aggregate:` from
        LIST → SUMMARY, but `ir_region.display` is still "list" — the
        caller passes the inferred `ctx_region.display` here to route
        correctly). #1082.
        """
        if display_override is not None:
            display_value = display_override.strip()
        else:
            display_obj = getattr(region, "display", None)
            raw_display = getattr(display_obj, "value", None)
            if raw_display is None:
                raw_display = "" if display_obj is None else str(display_obj)
            display_value = raw_display.strip()

        # TimeSeries family — same builder, different view argument.
        view = self._TIMESERIES_VIEWS.get(display_value)
        if view is not None:
            return self._build_time_series(region, cast(RegionContext, ctx), view)

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
