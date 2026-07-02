"""Right-by-default resolution for workspace heading action prominence (3a).

UX-maturity criterion **3a — frequency-weighted prominence** (epic #1491). A
workspace heading renders every declared/inferred action as a prominent button,
so an action-heavy workspace surfaces a long row of competing CTAs with no visual
hierarchy. The L4 target is *usage*-derived prominence (rare actions demote); the
L3 step here is the declared-signal default-flip: keep the top-K actions prominent
by declaration order and demote the tail to a `More ⋯` overflow menu.

Same default-flip shape as the other resolvers (`comparison_resolver` /
`peek_resolver` / `when_empty_resolver` / `auto_display`): a pure function of the
declared AppSpec — no runtime/usage signal, no bespoke JS. The split is applied at
the action-assembly seam (`page_routes`), and the overflow set renders as a native
`<details>` dropdown in the heading (no JS, no client state).

**Default budget (James 2026-06-30, via the #1491 3a decision gate): top 3.**
The first three actions stay prominent buttons; the rest overflow. Most
workspaces declare ≤3 actions, so nothing changes for them — only an action-heavy
heading declutters. Order is preserved: inferred `+ New <Entity>` create-CTAs are
assembled first (the canonical primary action), so they are protected by position;
authored heading CTAs appended beyond the budget are the demotion tail.

L4 follow-on: derive the budget / which actions stay from observed usage
frequency, and extend the inference to row-action / bulk-toolbar / action-grid
placements (this increment is scoped to the workspace heading row only).
"""

from __future__ import annotations

import logging
from collections.abc import Callable

logger = logging.getLogger(__name__)

# Up to this many heading actions stay prominent; the rest overflow.
_DEFAULT_PRIMARY_BUDGET = 3

# ADR-0050 3a: minimum total heading-action clicks on a surface before usage
# reorders its actions. Below this floor the declared order stands (cold-start =
# byte-identical to today), so a thin, noisy signal never thrashes the UI.
_DEFAULT_MIN_SAMPLES = 10


def resolve_action_prominence[T](
    actions: list[T],
    budget: int = _DEFAULT_PRIMARY_BUDGET,
) -> tuple[list[T], list[T]]:
    """Partition heading actions into ``(primary, overflow)`` by declaration order.

    Keeps the first ``budget`` actions prominent and routes the tail to overflow.
    A no-op (empty overflow) when the action count is within budget — so the
    common ``≤3``-action heading is byte-identical to before. The split is purely
    positional: the canonical inferred create-CTAs (assembled first) stay primary;
    the lowest-priority declared tail demotes.
    """
    if budget < 0:
        budget = 0
    if len(actions) <= budget:
        return list(actions), []
    return list(actions[:budget]), list(actions[budget:])


def resolve_action_prominence_by_usage[T](
    actions: list[T],
    usage: dict[str, int],
    *,
    route_of: Callable[[T], str],
    budget: int = _DEFAULT_PRIMARY_BUDGET,
    min_samples: int = _DEFAULT_MIN_SAMPLES,
) -> tuple[list[T], list[T]]:
    """Usage-weighted heading-action prominence (ADR-0050 3a → L4).

    Cold-start-safe: when the surface's total clicks are below ``min_samples`` (a
    fresh app, or a thin/noisy signal), returns exactly
    ``resolve_action_prominence(actions, budget)`` — **byte-identical to today's
    declaration-order split**. Above the floor, the actions are **stable-sorted by
    usage descending** (``usage`` maps an action's route → click count) and then
    split at ``budget``, so a frequently-clicked action stays prominent and a rare
    one demotes to the ``More ⋯`` overflow.

    The sort is *stable*: actions with equal usage keep their declared order, so the
    canonical create-CTA-first ordering is preserved on ties and — critically — for
    every action that has never been clicked (usage 0), which is the whole set at
    cold start. ``route_of`` extracts the usage key (the action's route/target) from
    each action, keeping this decoupled from the action's concrete shape.
    """
    total = sum(usage.values())
    if total < min_samples:
        return resolve_action_prominence(actions, budget)
    ranked = sorted(actions, key=lambda a: -usage.get(route_of(a), 0))
    primary, overflow = resolve_action_prominence(ranked, budget)
    # Traceability (ADR-0050 / model-driven-failure rubric): when usage actually
    # changed the outcome vs the declared-order split, record which signal did it
    # — a usage-driven UI choice must be explainable, never a silent oracle.
    static_primary, _ = resolve_action_prominence(actions, budget)
    if [route_of(a) for a in primary] != [route_of(a) for a in static_primary]:
        logger.debug(
            "usage-weighted action prominence: primary=%s (declared order: %s; "
            "clicks=%s, total=%d >= floor=%d)",
            [route_of(a) for a in primary],
            [route_of(a) for a in static_primary],
            {route_of(a): usage.get(route_of(a), 0) for a in actions},
            total,
            min_samples,
        )
    return primary, overflow
