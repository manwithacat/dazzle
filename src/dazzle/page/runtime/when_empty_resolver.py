"""Right-by-default resolution for a region's `when_empty:` mode (#1494, 3d).

The negative-space primitive (UX-maturity criterion 3d): an empty *supporting*
region renders dead scaffolding by default — an empty card with a placeholder.
`when_empty:` lets a region instead self-demote when it resolves to no rows.

Mirrors the `peek:` (`peek_resolver`) and `display: auto` (`auto_display`) pattern:
an explicit author value is authoritative; an *unset* region (`when_empty is None`)
routes through the render-time default-flip.

**The default-flip (the #1494 3d level-4 move):** an empty region adapts its
presence to the data —
- an author-declared `empty_message:` is honoured (`message` — they opted into a
  visible empty-state);
- a **supporting widget** (a chart/metric/summary, or any region with declared
  `aggregates`) **collapses** to header-only when empty — the dead body
  scaffolding disappears, but the card (and its title, for context) stays in the
  grid. Full **suppression** (removing the whole card) stays explicit opt-in
  (`when_empty: suppress`), since silently removing a grid card is more
  disruptive than collapsing its body;
- a **primary content** region (list/grid/kanban/queue/timeline/… — the thing a
  user navigated to) keeps its `message` — an empty primary surface deserves a
  helpful "nothing here yet" guide, not a silent disappearance.

Fully traceable: the choice is a pure function of the region's declared
`display` + `aggregates` + `empty_message` — no runtime/usage signal, no bespoke
JS. The render seam (`workspace_region_handler._build_region_response`) turns the
resolved mode into a native htmx OOB-delete (`suppress`) / `HX-Reswap: delete`
(`collapse`) when the fetched region has no rows.
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
      `when_empty: message` and `when_empty: suppress` (full card removal).
    - Unset → the default-flip: `message` when the author declared an
      `empty_message` or the region is primary content; `collapse` (header-only,
      card stays in the grid) for an empty supporting widget (chart/metric/
      aggregate). Full `suppress` is never the default — it's explicit opt-in.
    """
    explicit = getattr(region, "when_empty", None)
    if explicit is not None:
        return WhenEmpty(explicit)
    if getattr(region, "empty_message", None):
        return WhenEmpty.MESSAGE
    if _is_supporting_widget(region):
        return WhenEmpty.COLLAPSE
    return WhenEmpty.MESSAGE
