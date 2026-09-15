"""#1678: comparison is opt-in — resolve_comparison never infers a DeltaSpec."""

from __future__ import annotations

from types import SimpleNamespace

from dazzle.core.ir import AggregateRef
from dazzle.page.runtime.comparison_resolver import resolve_comparison


def _repos(field_names: list[str], entity: str = "Order") -> dict[str, object]:
    spec = SimpleNamespace(fields=[SimpleNamespace(name=n) for n in field_names])
    return {entity: SimpleNamespace(entity_spec=spec)}


def test_dated_entity_does_not_infer_delta() -> None:
    aggs = {"n": AggregateRef(func="count", entity="Order")}
    assert resolve_comparison(aggs, _repos(["id", "created_at"])) is None


def test_scalar_grain_does_not_infer_delta() -> None:
    for func in ("sum", "avg", "min", "max"):
        aggs = {"m": AggregateRef(func=func, entity="Order", column="amount")}
        assert resolve_comparison(aggs, _repos(["id", "created_at"])) is None, func


def test_empty_or_missing_inputs_return_none() -> None:
    assert resolve_comparison(None, _repos(["created_at"])) is None
    assert resolve_comparison({"n": AggregateRef(func="count", entity="Order")}, None) is None
    assert resolve_comparison({}, {}) is None
