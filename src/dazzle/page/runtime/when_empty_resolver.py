"""Right-by-default resolution for a region's `when_empty:` mode (#1494, 3d).

The negative-space primitive (UX-maturity criterion 3d): an empty *supporting*
region renders dead scaffolding by default — an empty card with a placeholder.
`when_empty:` lets a region instead self-demote when it resolves to no rows.

Mirrors the `peek:` (`peek_resolver`) and `display: auto` (`auto_display`) pattern:
an explicit author value is authoritative; an *unset* region (`when_empty is None`)
routes through the render-time default-flip.

**The default is `message` (byte-stable — today's typed empty-state).** Self-
demote is **explicit opt-in** via `when_empty: collapse | suppress`. An earlier
cut auto-collapsed empty *supporting widgets* by default (the 3d level-4
"adaptive" move), but CI's INTERACTION_WALK viewport-geometry gate showed that
auto-removing an empty region's body/card shifts the dashboard grid and trips
the fleet gates that assert on empty-region DOM. Making the auto-default safe
therefore needs those gates updated to tolerate a self-demoting empty region —
a separate effort tracked on #1494; until then the default stays `message` and
`_is_supporting_widget` is retained for when that flip lands.

The render seam (`workspace_region_handler._build_region_response`) turns an
*opted-in* mode into a native htmx OOB-delete (`suppress`) / `HX-Reswap: delete`
(`collapse`) when the fetched region has no rows. Declarative-over-htmx-4, no
bespoke JS.
"""

from __future__ import annotations

from typing import Any

from dazzle.core.ir import WhenEmpty

# Display forms that are *supporting widgets* — an empty one is dead scaffolding
# on a dashboard, so an unset region of this form suppresses when empty. Anything
# not listed here (list/grid/kanban/queue/timeline/tree/map/detail/entity_card/…)
# is treated as *primary content* and keeps its empty-state message by default.
_SUPPORTING_DISPLAYS = frozenset(
    {
        "summary",
        "metrics",
        "bar_chart",
        "funnel_chart",
        "line_chart",
        "area_chart",
        "sparkline",
        "histogram",
        "radar",
        "box_plot",
        "bullet",
        "bar_track",
        "pivot_table",
        "heatmap",
        "comparison",
        "insight_summary",
        "progress",
        "diagram",
    }
)


def _is_supporting_widget(region: Any) -> bool:
    """A region whose empty state is noise rather than a navigable surface —
    declared `aggregates`, or a chart/metric/summary `display` form."""
    if getattr(region, "aggregates", None):
        return True
    raw: Any = getattr(region, "display", None)
    display = (raw.value if hasattr(raw, "value") else str(raw or "")).lower()
    return display in _SUPPORTING_DISPLAYS


def resolve_when_empty(region: Any) -> WhenEmpty:
    """Resolve the effective `when_empty:` mode for a workspace region.

    - Explicit author value (`region.when_empty is not None`) wins — incl.
      `when_empty: collapse` / `when_empty: suppress` (the opt-in self-demote).
    - Unset → `message` (byte-stable; the typed empty-state, unchanged from
      before #1494). The auto self-demote default-flip is deferred (see the
      module docstring) — it needs the fleet's viewport/interaction gates
      updated to tolerate a self-demoting empty region.
    """
    explicit = getattr(region, "when_empty", None)
    if explicit is not None:
        return WhenEmpty(explicit)
    return WhenEmpty.MESSAGE
