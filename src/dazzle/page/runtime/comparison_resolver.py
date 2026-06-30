"""Right-by-default resolution for a scalar metric's comparison context (1c).

UX-maturity criterion **1c — comparison context** (epic #1491). The comparison
machinery already ships: a `metrics` / `summary` tile renders a period-over-period
delta arrow whenever a `DeltaSpec` is present (#884), and `_compute_aggregate_metrics`
already runs the prior-window query. But the `DeltaSpec` only ever came from an
explicit author `delta:` block — so an undeclared `count()` tile rendered a lone
KPI number with no context. That is the L2 gap: the capability exists but is opt-in.

This resolver closes it with the same default-flip shape as `display: auto`
(`auto_display`), `peek:` (`peek_resolver`), and `when_empty:` (`when_empty_resolver`):
an explicit author `delta:` is authoritative; an *unset* metrics region routes
through `resolve_comparison`, which synthesises a default `DeltaSpec` when a
`count()` aggregate's source entity carries a `created_at` timestamp (the
canonical comparison source). So a count tile shows a 30-day period-over-period
trend by default instead of a bare number.

**Defaults (James 2026-06-30, via the #1491 1c decision gate):**
- 30-day window (month-over-month — the most common business cadence);
- `neutral` sentiment — an *inferred* delta renders magnitude/direction without
  asserting good/bad (no green/red), since the direction-flip is automatic and
  un-declared. Asserting tone is the declared-`semantic:` 1b path's job; a rising
  open-ticket count must not render green just because it went up.

Scope (L3, good-defaults): count() aggregates over an entity with `created_at`.
A scalar/sum/avg grain, or an entity without `created_at`, gracefully stays a
lone KPI — "right by default *where a comparison source exists*" (roadmap wording).
Extending the inference to other grains is the L4 follow-on.

Fully traceable: the choice is a pure function of the declared aggregates +
the source entity's fields — no runtime/usage signal, no bespoke JS. The flip is
applied at the single shared seam `_compute_aggregate_metrics`, so both the
server-render path and the htmx lazy-fetch path light up from one place.
"""

from __future__ import annotations

from typing import Any

from dazzle.core.ir import AggregateRef, DeltaSpec

# 30 days, in seconds — the default inferred comparison window.
_DEFAULT_PERIOD_SECONDS = 30 * 86_400
_DEFAULT_PERIOD_LABEL = "prior 30 days"
# The canonical comparison source: an entity's creation timestamp. The delta
# path already defaults `date_field` to ``created_at`` (a None date_field), so a
# synthesised DeltaSpec leaves it None and relies on that default.
_COMPARISON_DATE_FIELD = "created_at"


def _entity_has_created_at(entity_spec: Any) -> bool:
    """True when the entity declares a ``created_at`` field — the canonical
    period-over-period comparison source the delta path windows on."""
    for field in getattr(entity_spec, "fields", None) or []:
        if getattr(field, "name", None) == _COMPARISON_DATE_FIELD:
            return True
    return False


def resolve_comparison(
    aggregates: dict[str, Any] | None,
    repositories: dict[str, Any] | None,
) -> DeltaSpec | None:
    """Infer a default period-over-period ``DeltaSpec`` for an unset metrics region.

    Returns a 30-day, ``neutral``-sentiment ``DeltaSpec`` when at least one
    ``count()`` aggregate's source entity has a ``created_at`` field; otherwise
    ``None`` (the tile stays a lone KPI). The caller applies this only when no
    explicit author ``delta:`` was declared, so a declared delta always wins.
    """
    if not aggregates or not repositories:
        return None
    for ref in aggregates.values():
        if not isinstance(ref, AggregateRef) or ref.func != "count":
            continue
        repo = repositories.get(ref.entity or "")
        entity_spec = getattr(repo, "entity_spec", None) if repo else None
        if entity_spec is not None and _entity_has_created_at(entity_spec):
            return DeltaSpec(
                period_seconds=_DEFAULT_PERIOD_SECONDS,
                sentiment="neutral",
                date_field=None,  # → created_at (the delta path's default)
                period_label=_DEFAULT_PERIOD_LABEL,
            )
    return None
