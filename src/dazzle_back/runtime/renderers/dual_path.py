"""Phase 4B.3 — dual-path validation harness.

Renders a workspace region via both paths (legacy Jinja vs typed-
Fragment adapter) and provides primitives for comparing the outputs.
The harness consumes Phase 4B.2's `legacy_ctx_to_adapter_ctx` so
both paths take the same legacy ctx as input and the diff captures
only the rendering-strategy difference, not ctx-shape gymnastics.

Use cases:
- **Smoke** — assert both paths produce non-empty output for a given
  (display, ctx). Catches structural failures (missing template,
  primitive crash on the typed side) without requiring byte match.
- **Equivalence** — normalise whitespace + extract the region body
  + diff. Phase 4B.4's per-display port uses this to gate display
  migration: a display is "ready to migrate" when its byte-
  equivalence diff is empty for example-app ctx.

The harness deliberately does NOT pull in the workspace handler or
example-app DSL — that's Phase 4B.4's wave structure. This module
gives you a pure (display, legacy_ctx) → (legacy_html, typed_html)
pair you can drive with synthetic or real captured ctx.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from dazzle.render.fragment import FragmentRenderer
from dazzle_back.runtime.renderers.legacy_ctx import legacy_ctx_to_adapter_ctx
from dazzle_back.runtime.renderers.region_adapter import WorkspaceRegionAdapter

# Maps lowercase display name → legacy Jinja template path. Mirrors
# `dazzle_ui.runtime.workspace_renderer.DISPLAY_TEMPLATE_MAP` but
# keyed by the same lowercase form the adapter / translator use.
_LEGACY_TEMPLATE: dict[str, str] = {
    "list": "workspace/regions/list.html",
    "grid": "workspace/regions/grid.html",
    "metrics": "workspace/regions/metrics.html",
    "summary": "workspace/regions/metrics.html",
    "detail": "workspace/regions/detail.html",
    "kanban": "workspace/regions/kanban.html",
    "timeline": "workspace/regions/timeline.html",
    "bar_chart": "workspace/regions/bar_chart.html",
    "funnel_chart": "workspace/regions/funnel_chart.html",
    "queue": "workspace/regions/queue.html",
    "tabbed_list": "workspace/regions/tabbed_list.html",
    "heatmap": "workspace/regions/heatmap.html",
    "progress": "workspace/regions/progress.html",
    "activity_feed": "workspace/regions/activity_feed.html",
    "tree": "workspace/regions/tree.html",
    "pivot_table": "workspace/regions/pivot_table.html",
    "line_chart": "workspace/regions/line_chart.html",
    "area_chart": "workspace/regions/area_chart.html",
    "sparkline": "workspace/regions/sparkline.html",
    "diagram": "workspace/regions/diagram.html",
    "histogram": "workspace/regions/histogram.html",
    "radar": "workspace/regions/radar.html",
    "box_plot": "workspace/regions/box_plot.html",
    "bullet": "workspace/regions/bullet.html",
    "bar_track": "workspace/regions/bar_track.html",
    "action_grid": "workspace/regions/action_grid.html",
    "profile_card": "workspace/regions/profile_card.html",
    "pipeline_steps": "workspace/regions/pipeline_steps.html",
    "status_list": "workspace/regions/status_list.html",
    "confirm_action_panel": "workspace/regions/confirm_action_panel.html",
    "search_box": "workspace/regions/search_box.html",
}


@dataclass
class _StubRegion:
    """Minimal region-shaped object the adapter consumes.

    Real workspace regions carry the full RegionContext spec; the
    harness only needs the fields the adapter's `_build_*` methods
    read (name, display, empty_message). All other attributes get
    AttributeError-via-getattr-default treatment in the adapter, so
    keeping the stub lean is fine.
    """

    name: str
    display: str
    empty_message: str = "No data."


def render_via_legacy(display: str, **legacy_ctx: Any) -> str:
    """Render `display` via the legacy Jinja template path.

    Imports `render_fragment` lazily because the dazzle_ui module
    initialises a Jinja environment on first import; the harness
    should not pay that cost when only the typed path is exercised.
    """
    template = _LEGACY_TEMPLATE.get(display)
    if template is None:
        raise ValueError(f"Unknown display: {display!r}")
    from dazzle_ui.runtime.template_renderer import render_fragment

    return render_fragment(template, **legacy_ctx)


def render_via_typed(
    display: str,
    legacy_ctx: dict[str, Any],
    *,
    region_name: str = "r",
) -> str:
    """Render `display` via the typed-Fragment adapter path.

    Threads through Phase 4B.2's translator so callers can supply the
    same legacy ctx they'd hand to `render_via_legacy`. Returns the
    rendered HTML for the full Surface (header + region body) —
    matches the on-page output, not just the inner primitive.
    """
    adapter_ctx = legacy_ctx_to_adapter_ctx(display, legacy_ctx)
    region = _StubRegion(name=region_name, display=display)
    adapter = WorkspaceRegionAdapter()
    fragment = adapter.build(region, adapter_ctx)
    return FragmentRenderer().render(fragment)


_WHITESPACE = re.compile(r"\s+")
_BETWEEN_TAGS = re.compile(r">\s+<")


def normalise_html(html: str) -> str:
    """Collapse insignificant whitespace for byte-equivalence comparison.

    Steps:
      1. Strip whitespace between tags (`>   <` → `><`).
      2. Collapse internal whitespace runs to a single space.
      3. Trim leading/trailing whitespace.

    Does NOT reorder attributes — Phase 4B.4 may need an
    `attribute-order-insensitive` mode if real-world diffs surface
    flaky orderings. The current FragmentRenderer + Jinja both emit
    deterministic order, so this hasn't been a problem yet.
    """
    s = _BETWEEN_TAGS.sub("><", html)
    s = _WHITESPACE.sub(" ", s)
    return s.strip()


def diff_summary(legacy_html: str, typed_html: str) -> str | None:
    """Return None if the two outputs are equivalent (after normalisation),
    or a short diff-summary string describing the mismatch.

    Useful for parametrised pytest assertions: `assert
    diff_summary(a, b) is None` gives a readable failure message for
    every byte-equivalent display port.
    """
    a = normalise_html(legacy_html)
    b = normalise_html(typed_html)
    if a == b:
        return None
    # Find first divergence position for a useful failure message.
    n = min(len(a), len(b))
    for i in range(n):
        if a[i] != b[i]:
            ctx_start = max(0, i - 30)
            return (
                f"diverged at char {i}: "
                f"legacy=…{a[ctx_start : i + 30]!r} "
                f"typed=…{b[ctx_start : i + 30]!r}"
            )
    return f"length mismatch: legacy={len(a)} typed={len(b)}"


__all__ = [
    "diff_summary",
    "normalise_html",
    "render_via_legacy",
    "render_via_typed",
]
