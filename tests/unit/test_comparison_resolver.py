"""Tests for the 1c comparison default-flip resolver (#1491).

`resolve_comparison` infers a default period-over-period `DeltaSpec` for an
unset metrics region whose `count()` aggregate sources an entity with
`created_at`, so a scalar tile shows trend context by default instead of a lone
KPI. An explicit author `delta:` always wins (the caller only invokes the
resolver when `delta is None`).
"""

from __future__ import annotations

from types import SimpleNamespace

from dazzle.core.ir import AggregateRef
from dazzle.page.runtime.comparison_resolver import resolve_comparison


def _repos(field_names: list[str], entity: str = "Order") -> dict[str, object]:
    spec = SimpleNamespace(fields=[SimpleNamespace(name=n) for n in field_names])
    return {entity: SimpleNamespace(entity_spec=spec)}


def test_count_over_dated_entity_infers_30day_neutral_delta() -> None:
    aggs = {"n": AggregateRef(func="count", entity="Order")}
    delta = resolve_comparison(aggs, _repos(["id", "created_at"]))
    assert delta is not None
    assert delta.period_seconds == 30 * 86_400
    assert delta.sentiment == "neutral"  # inferred deltas never assert good/bad
    assert delta.date_field is None  # → created_at via the delta path default
    assert delta.period_label == "prior 30 days"


def test_entity_without_created_at_stays_lone_kpi() -> None:
    aggs = {"n": AggregateRef(func="count", entity="Order")}
    assert resolve_comparison(aggs, _repos(["id", "name"])) is None


def test_non_count_grain_is_not_inferred() -> None:
    # L3 scope is count-only; scalar/sum/avg grains stay lone KPI (L4 follow-on).
    aggs = {"total": AggregateRef(func="sum", entity="Order", column="amount")}
    assert resolve_comparison(aggs, _repos(["id", "created_at"])) is None


def test_first_dated_count_wins_among_mixed_aggregates() -> None:
    aggs = {
        "revenue": AggregateRef(func="sum", entity="Order", column="amount"),
        "orders": AggregateRef(func="count", entity="Order"),
    }
    assert resolve_comparison(aggs, _repos(["id", "created_at"])) is not None


def test_empty_or_missing_inputs_return_none() -> None:
    assert resolve_comparison(None, _repos(["created_at"])) is None
    assert resolve_comparison({"n": AggregateRef(func="count", entity="Order")}, None) is None
    assert resolve_comparison({}, {}) is None


def test_missing_repo_for_entity_returns_none() -> None:
    aggs = {"n": AggregateRef(func="count", entity="Ghost")}
    assert resolve_comparison(aggs, _repos(["created_at"], entity="Order")) is None
