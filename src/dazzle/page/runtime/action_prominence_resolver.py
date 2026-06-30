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

# Up to this many heading actions stay prominent; the rest overflow.
_DEFAULT_PRIMARY_BUDGET = 3


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
