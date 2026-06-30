"""Right-by-default column economy for auto-generated list/table columns (2d).

UX-maturity criterion **2d — field economy** (epic #1491). When a list surface
declares no field projection, Dazzle auto-derives the columns from the entity and
showed up to a magic cap of 8 in declaration order — a wide entity dumps a sprawl
of low-signal columns (timestamps, long text) with no hierarchy. The L3 default is
to keep the top-N *most salient* columns and let the rest be recovered through the
already-default row drill (2b) / `peek:` (2c), which surface every field — that is
the "reveal" with no htmx-4 dependency.

Same default-flip shape as the sibling resolvers (`action_prominence_resolver` /
`comparison_resolver` / `peek_resolver` / `when_empty_resolver`): a pure function
of the declared columns, no runtime/usage signal, no JS, no schema change.

**Scope (James 2026-06-30, via the #1491 2d decision gate): auto-columns only.**
An explicit surface field projection is authoritative and rendered in full (the
"explicit author value wins" discriminator every other resolver uses) — this
resolver is applied ONLY to the entity-fallback column builder. **Budget: top 6.**

Salience (declared-signal, no usage): an identifying/title field ranks highest;
status badges and relationships next; auto-timestamps (`*_at`) rank lowest. Ties
keep declaration order, and the kept columns are re-emitted in declaration order
(truncation by salience, not a reorder — so a narrow table is byte-identical and a
wide one just sheds its lowest-signal tail). L4 follow-on: an explicit `priority:`
field modifier as the author override, and a live in-table "show all columns"
reveal.
"""

from __future__ import annotations

from typing import Any

# Keep at most this many auto-derived columns; the salience tail is dropped
# (recovered via the default drill/peek).
_DEFAULT_COLUMN_BUDGET = 6

# Field names that identify a row at a glance — always worth a column.
_IDENTIFYING_KEYS = frozenset(
    {
        "name",
        "title",
        "label",
        "display_name",
        "code",
        "slug",
        "email",
        "reference",
        "subject",
        "summary",
    }
)

# Auto-timestamp-ish names — low scan value in a dense list (the row's drill
# shows them). `*_at` is caught separately.
_TIMESTAMP_KEYS = frozenset({"created_at", "updated_at", "created", "updated", "modified"})

# Column render-type → base salience. Badges (status) and refs are the scannable
# signal; plain text is the floor. (Keys from `field_kind_to_col_type`.)
_TYPE_SALIENCE: dict[str, int] = {
    "badge": 80,
    "currency": 70,
    "ref": 60,
    "bool": 50,
    "date": 45,
    "text": 30,
}


def _salience(column: dict[str, Any]) -> int:
    """Declared-signal salience for a column dict (higher = keep)."""
    key = str(column.get("key", "")).lower()
    if key in _IDENTIFYING_KEYS:
        return 100
    if key in _TIMESTAMP_KEYS or key.endswith("_at"):
        return 10
    return _TYPE_SALIENCE.get(str(column.get("type", "")), 30)


def resolve_column_economy(
    columns: list[dict[str, Any]],
    budget: int = _DEFAULT_COLUMN_BUDGET,
) -> list[dict[str, Any]]:
    """Keep the top-``budget`` most salient columns, re-emitted in declaration order.

    A no-op (returns the list unchanged) when the column count is within budget,
    so a narrow auto-table is byte-identical. Over budget, the lowest-salience
    tail is dropped — ties keep declaration order, and the survivors stay in their
    original order (truncation, not reorder).
    """
    if budget < 0:
        budget = 0
    if len(columns) <= budget:
        return list(columns)
    # Stable sort by descending salience keeps declaration order among ties;
    # take the top `budget` indices, then re-emit in original order.
    ranked = sorted(range(len(columns)), key=lambda i: -_salience(columns[i]))
    keep = set(ranked[:budget])
    return [c for i, c in enumerate(columns) if i in keep]
