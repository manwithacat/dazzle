"""Shared HM↔Dazzle contract registries for dual-lock gates.

**Model-bearing** (schema parity + DOM): one ``CONTRACT_MODELS`` row +
ingest seam copy + DOM fixture.

**Root-only** (DOM only, #1578): one ``DOM_ONLY_CONTRACTS`` row + a fixture
callable in ``test_hm_contract_dom_conformance`` — no fake Pydantic model,
no schema parity. Root-only modules without a stable Dazzle emission path
are listed in ``DOM_ONLY_DEFERRED`` (inventory only).
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
HM = REPO_ROOT / "packages" / "hatchi-maxchi"

# (hm_rel_path, hm_model_name, dazzle_module, dazzle_model_name)
CONTRACT_MODELS: list[tuple[str, str, str, str]] = [
    ("contracts/grid_edit.py", "GridEditCell", "dazzle.render.fragment.ingest", "GridEditCell"),
    ("contracts/combobox.py", "ComboboxField", "dazzle.render.fragment.ingest", "ComboboxField"),
    ("contracts/tags.py", "TagsField", "dazzle.render.fragment.ingest", "TagsField"),
    ("contracts/money.py", "MoneyField", "dazzle.render.fragment.ingest", "MoneyField"),
    (
        "contracts/search_select.py",
        "SearchResultRow",
        "dazzle.render.fragment.ingest",
        "SearchResultRow",
    ),
    (
        "contracts/search_select.py",
        "SearchSelectShell",
        "dazzle.render.fragment.ingest",
        "SearchSelectShell",
    ),
    (
        "contracts/action_grid.py",
        "ActionCard",
        "dazzle.render.fragment.ingest",
        "ActionCard",
    ),
    (
        "contracts/status_list.py",
        "StatusListEntry",
        "dazzle.render.fragment.ingest",
        "StatusListEntry",
    ),
    (
        "contracts/queue.py",
        "QueueRow",
        "dazzle.render.fragment.ingest",
        "QueueRow",
    ),
    (
        "contracts/metrics.py",
        "MetricTile",
        "dazzle.render.fragment.ingest",
        "MetricTile",
    ),
    (
        "contracts/kanban.py",
        "KanbanCard",
        "dazzle.render.fragment.ingest",
        "KanbanCard",
    ),
    (
        "contracts/activity_feed.py",
        "ActivityRow",
        "dazzle.render.fragment.ingest",
        "ActivityRow",
    ),
    (
        "contracts/timeline.py",
        "TimelineEvent",
        "dazzle.render.fragment.ingest",
        "TimelineEvent",
    ),
    (
        "contracts/profile_card.py",
        "ProfileCard",
        "dazzle.render.fragment.ingest",
        "ProfileCard",
    ),
    (
        "contracts/sparkline.py",
        "Sparkline",
        "dazzle.render.fragment.ingest",
        "Sparkline",
    ),
    (
        "contracts/funnel.py",
        "Funnel",
        "dazzle.render.fragment.ingest",
        "Funnel",
    ),
    (
        "contracts/funnel.py",
        "FunnelStage",
        "dazzle.render.fragment.ingest",
        "FunnelStage",
    ),
    (
        "contracts/bar_chart.py",
        "BarChart",
        "dazzle.render.fragment.ingest",
        "BarChart",
    ),
    (
        "contracts/bar_chart.py",
        "BarChartRow",
        "dazzle.render.fragment.ingest",
        "BarChartRow",
    ),
    (
        "contracts/heatmap.py",
        "Heatmap",
        "dazzle.render.fragment.ingest",
        "Heatmap",
    ),
    (
        "contracts/heatmap.py",
        "HeatmapRow",
        "dazzle.render.fragment.ingest",
        "HeatmapRow",
    ),
    (
        "contracts/bullet.py",
        "Bullet",
        "dazzle.render.fragment.ingest",
        "Bullet",
    ),
    (
        "contracts/bullet.py",
        "BulletRow",
        "dazzle.render.fragment.ingest",
        "BulletRow",
    ),
    (
        "contracts/bullet.py",
        "BulletBand",
        "dazzle.render.fragment.ingest",
        "BulletBand",
    ),
    (
        "contracts/bar_track.py",
        "BarTrack",
        "dazzle.render.fragment.ingest",
        "BarTrack",
    ),
    (
        "contracts/bar_track.py",
        "BarTrackRow",
        "dazzle.render.fragment.ingest",
        "BarTrackRow",
    ),
    (
        "contracts/histogram.py",
        "Histogram",
        "dazzle.render.fragment.ingest",
        "Histogram",
    ),
    (
        "contracts/histogram.py",
        "HistogramBin",
        "dazzle.render.fragment.ingest",
        "HistogramBin",
    ),
    (
        "contracts/pivot.py",
        "PivotTable",
        "dazzle.render.fragment.ingest",
        "PivotTable",
    ),
    (
        "contracts/box_plot.py",
        "BoxPlot",
        "dazzle.render.fragment.ingest",
        "BoxPlot",
    ),
    (
        "contracts/box_plot.py",
        "BoxPlotGroup",
        "dazzle.render.fragment.ingest",
        "BoxPlotGroup",
    ),
    (
        "contracts/progress.py",
        "Progress",
        "dazzle.render.fragment.ingest",
        "Progress",
    ),
    (
        "contracts/progress.py",
        "ProgressStage",
        "dazzle.render.fragment.ingest",
        "ProgressStage",
    ),
    (
        "contracts/radar.py",
        "Radar",
        "dazzle.render.fragment.ingest",
        "Radar",
    ),
    (
        "contracts/radar.py",
        "RadarAxis",
        "dazzle.render.fragment.ingest",
        "RadarAxis",
    ),
    (
        "contracts/time_series.py",
        "TimeSeries",
        "dazzle.render.fragment.ingest",
        "TimeSeries",
    ),
    (
        "contracts/time_series.py",
        "TimeSeriesPoint",
        "dazzle.render.fragment.ingest",
        "TimeSeriesPoint",
    ),
    (
        "contracts/time_series.py",
        "TimeSeriesLayer",
        "dazzle.render.fragment.ingest",
        "TimeSeriesLayer",
    ),
    (
        "contracts/pagination.py",
        "Pagination",
        "dazzle.render.fragment.ingest",
        "Pagination",
    ),
    (
        "contracts/search_box.py",
        "SearchBox",
        "dazzle.render.fragment.ingest",
        "SearchBox",
    ),
    (
        "contracts/date_range.py",
        "DateRange",
        "dazzle.render.fragment.ingest",
        "DateRange",
    ),
    (
        "contracts/list_region.py",
        "ListRegion",
        "dazzle.render.fragment.ingest",
        "ListRegion",
    ),
    (
        "contracts/empty_state.py",
        "EmptyState",
        "dazzle.render.fragment.ingest",
        "EmptyState",
    ),
    (
        "contracts/skeleton.py",
        "Skeleton",
        "dazzle.render.fragment.ingest",
        "Skeleton",
    ),
    (
        "contracts/diagram.py",
        "Diagram",
        "dazzle.render.fragment.ingest",
        "Diagram",
    ),
    (
        "contracts/task_inbox.py",
        "TaskInbox",
        "dazzle.render.fragment.ingest",
        "TaskInbox",
    ),
    (
        "contracts/tree.py",
        "Tree",
        "dazzle.render.fragment.ingest",
        "Tree",
    ),
    (
        "contracts/calendar.py",
        "Calendar",
        "dazzle.render.fragment.ingest",
        "Calendar",
    ),
    (
        "contracts/dashboard_card.py",
        "DashboardCard",
        "dazzle.render.fragment.ingest",
        "DashboardCard",
    ),
    (
        "contracts/cohort_strip.py",
        "CohortStrip",
        "dazzle.render.fragment.ingest",
        "CohortStrip",
    ),
    (
        "contracts/day_timeline.py",
        "DayTimeline",
        "dazzle.render.fragment.ingest",
        "DayTimeline",
    ),
    (
        "contracts/entity_card.py",
        "EntityCard",
        "dazzle.render.fragment.ingest",
        "EntityCard",
    ),
    (
        "contracts/grid_region.py",
        "GridRegion",
        "dazzle.render.fragment.ingest",
        "GridRegion",
    ),
    (
        "contracts/pipeline.py",
        "Pipeline",
        "dazzle.render.fragment.ingest",
        "Pipeline",
    ),
]

# Root-only Hyperparts with a stable Dazzle emission path.
# (hm_rel_path, part_id, require_root)
# Fixture builders live in test_hm_contract_dom_conformance (keyed by part_id).
DOM_ONLY_CONTRACTS: list[tuple[str, str, bool]] = [
    ("contracts/slider.py", "slider", True),
    ("contracts/color.py", "color", True),
    ("contracts/app_shell.py", "app_shell", True),
    ("contracts/command.py", "command", True),
    ("contracts/confirm_panel.py", "confirm_panel", True),
    ("contracts/confirm.py", "confirm", True),  # list-row delete hx-confirm (#1582)
    ("contracts/tabs.py", "tabs", True),
    ("contracts/dialog.py", "dialog", True),
    ("contracts/grid.py", "grid", True),
    ("contracts/grid_cols.py", "grid_cols", True),
    ("contracts/grid_resize.py", "grid_resize", True),
    ("contracts/pdf.py", "pdf", True),  # render_pdf_viewer_component (#1582)
    ("contracts/wizard.py", "wizard", True),  # experience form multi-section (#1582)
    ("contracts/master_detail.py", "master_detail", True),  # dual_pane_flow shell (#1580 C)
    ("contracts/menu.py", "menu", True),  # workspace overflow More ⋯ (#1491)
    ("contracts/badge.py", "badge", True),  # FragmentRenderer._emit_badge
    ("contracts/button.py", "button", True),  # FragmentRenderer._emit_button
    ("contracts/card.py", "card", True),  # FragmentRenderer._emit_card
    ("contracts/drawer.py", "drawer", True),  # FragmentRenderer._emit_drawer + slide_over
    ("contracts/toolbar.py", "toolbar", True),  # FragmentRenderer._emit_toolbar
    ("contracts/card_picker.py", "card_picker", True),  # FragmentRenderer._emit_card_picker
    ("contracts/add_card_row.py", "add_card_row", True),  # FragmentRenderer._emit_add_card_row
    (
        "contracts/bulk_actions.py",
        "bulk_actions",
        True,
    ),  # FragmentRenderer._emit_bulk_action_toolbar
    (
        "contracts/workspace_toolbar.py",
        "workspace_toolbar",
        True,
    ),  # FragmentRenderer._emit_workspace_toolbar
    (
        "contracts/filter_bar.py",
        "filter_bar",
        True,
    ),  # FragmentRenderer._emit_list_filter_bar
    (
        "contracts/skip_link.py",
        "skip_link",
        True,
    ),  # FragmentRenderer._emit_skip_link
    (
        "contracts/topbar.py",
        "topbar",
        True,
    ),  # FragmentRenderer._emit_topbar
    (
        "contracts/sidebar.py",
        "sidebar",
        True,
    ),  # FragmentRenderer._emit_sidebar
    (
        "contracts/related_group.py",
        "related_group",
        True,
    ),  # FragmentRenderer._emit_related_cards / _files
    (
        "contracts/surface.py",
        "surface",
        True,
    ),  # FragmentRenderer._emit_surface
    (
        "contracts/stack.py",
        "stack",
        True,
    ),  # FragmentRenderer._emit_stack
    (
        "contracts/cluster.py",
        "cluster",
        True,
    ),  # FragmentRenderer._emit_row → .dz-cluster
    (
        "contracts/heading.py",
        "heading",
        True,
    ),  # FragmentRenderer._emit_heading
    (
        "contracts/split.py",
        "split",
        True,
    ),  # FragmentRenderer._emit_split
    (
        "contracts/text.py",
        "text",
        True,
    ),  # FragmentRenderer._emit_text
    (
        "contracts/icon.py",
        "icon",
        True,
    ),  # FragmentRenderer._emit_icon
    (
        "contracts/link.py",
        "link",
        True,
    ),  # FragmentRenderer._emit_link
    (
        "contracts/inline_edit.py",
        "inline_edit",
        True,
    ),  # FragmentRenderer._emit_inline_edit
]

# Root-only modules without a simple FragmentRenderer / page fixture yet.
# Keep as inventory so the drain is greppable; add a DOM_ONLY_CONTRACTS row
# when a stable emission site exists.
DOM_ONLY_DEFERRED: list[tuple[str, str]] = [
    # Gallery + build-site highlighter (site/highlight.py); fleet-exempt as
    # "HM gallery + agent-pack snippets". Promote to DOM_ONLY_CONTRACTS only
    # when Dazzle gains a stable fenced-code emitter (not invent a fixture).
    ("contracts/code.py", "gallery/docs highlighter only — no FragmentRenderer emit"),
]


def load_hm_module(rel: str):
    """Load an HM contract module by path relative to packages/hatchi-maxchi."""
    pytest.importorskip("fastapi")
    if str(HM) not in sys.path:
        sys.path.insert(0, str(HM))
    spec = importlib.util.spec_from_file_location(f"hm_{Path(rel).stem}", HM / rel)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def canonical_schema(schema: dict) -> object:
    """Structural fields only — strip titles/descriptions/default-ordering noise."""
    keep = {
        "type",
        "required",
        "enum",
        "items",
        "properties",
        "anyOf",
        "prefixItems",
        "additionalProperties",
        "minItems",
        "maxItems",
        "const",
        "$defs",
        "$ref",
    }

    def walk(node: object) -> object:
        if isinstance(node, dict):
            out: dict = {}
            for k, v in sorted(node.items()):
                if k not in keep:
                    continue
                if k == "required":
                    out[k] = sorted(v)
                elif k in ("properties", "$defs"):
                    out[k] = {name: walk(sub) for name, sub in sorted(v.items())}
                else:
                    out[k] = walk(v)
            return out
        if isinstance(node, list):
            return [walk(x) for x in node]
        return node

    return walk(schema)
