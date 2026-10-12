"""Right-by-default resolution for a region's `when_empty:` mode (#1494, 3d).

The negative-space primitive (UX-maturity criterion 3d): an empty *supporting*
region renders dead scaffolding by default — an empty card with a placeholder.
`when_empty:` lets a region instead self-demote when it resolves to no rows.

Mirrors the `peek:` (`peek_resolver`) and `display: auto` (`auto_display`) pattern:
an explicit author value is authoritative; an *unset* region (`when_empty is None`)
routes through the render-time default-flip.

**The default-flip (the #1494 3d level-4 adaptive move; James 2026-06-29):** an
empty region adapts its presence to its data + role —
- an author-declared `empty_message:` is honoured (`message`);
- a **supporting widget** (a chart/metric/summary, or any region with declared
  `aggregates`) **collapses** to header-only — the dead body scaffolding goes,
  but the card + its title stay in the grid (context + stable layout). Full
  `suppress` (removing the whole card) is **never** the default — silently
  removing a grid card is too disruptive — it stays explicit opt-in;
- a **primary content** region (list/grid/kanban/queue/timeline/…) keeps its
  `message` — an empty primary surface deserves a "nothing here yet" guide.

Two refinements keep the default safe (the lessons CI taught when this first
shipped as auto-suppress): (1) the geometry gate skips its grid assertions when
a region collapsed (`ViewportAssertion.skip_if_absent` — geometry is N/A for an
absent grid); (2) a **picker-added** card is exempt — a user who explicitly adds
a card sees its empty-state, never an immediate self-demote
(`is_added_card` at the render seam).

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
# not listed here (list/grid/kanban/queue/timeline/entity_card/…)
# is treated as *primary content* and keeps its empty-state message by default.
_SUPPORTING_DISPLAYS = frozenset(
    {
        "summary",
        "metrics",
        "bar_chart",
        "line_chart",
        "radar",
        "pivot_table",
        "comparison",
        "insight_summary",
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
