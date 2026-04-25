"""Tests for the v0.61.25 delta-metric feature on summary/metrics tiles (#884).

Three layers:
  1. Parser: ``delta:`` block produces a ``DeltaSpec`` on ``WorkspaceRegion``.
  2. IR: ``DeltaSpec`` defaults + frozen-model behaviour.
  3. Runtime: ``_compute_aggregate_metrics`` decorates each metric with
     ``delta`` / ``delta_pct`` / ``delta_direction`` / ``delta_sentiment`` /
     ``delta_period_label`` when a delta spec is supplied. The prior-window
     query is mocked — this test exercises the wiring + sign math, not the
     repository.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from dazzle.core.dsl_parser_impl import parse_dsl
from dazzle.core.ir.module import ModuleFragment
from dazzle.core.ir.workspaces import DeltaSpec


def _parse(src: str) -> ModuleFragment:
    return parse_dsl(src, Path("test.dsl"))[5]


# ───────────────────────────── parser ──────────────────────────────


class TestDeltaParser:
    def test_minimal_delta_block(self) -> None:
        src = """module t
app t "Test"
entity Manuscript:
  id: uuid pk
  status: enum[pending,marked]=pending
  created_at: datetime auto_add
workspace dash "Dash":
  marked:
    aggregate:
      count: count(Manuscript where status = marked)
    display: summary
    delta:
      period: 1 day
"""
        mod = _parse(src)
        region = mod.workspaces[0].regions[0]
        assert region.delta is not None
        assert region.delta.period_seconds == 86400
        assert region.delta.sentiment == "positive_up"
        assert region.delta.date_field is None
        assert region.delta.period_label == "yesterday"

    def test_delta_with_all_keys(self) -> None:
        src = """module t
app t "Test"
entity Event:
  id: uuid pk
  occurred_at: datetime auto_add
workspace dash "Dash":
  events:
    aggregate:
      count: count(Event)
    display: summary
    delta:
      period: 7 days
      sentiment: positive_down
      field: occurred_at
"""
        mod = _parse(src)
        d = mod.workspaces[0].regions[0].delta
        assert d.period_seconds == 7 * 86400
        assert d.sentiment == "positive_down"
        assert d.date_field == "occurred_at"
        # `7 days` doesn't auto-collapse to "last week" in v1 — only the
        # canonical singular forms (`1 day` / `1 week` / `1 month`) get
        # human-friendly labels. Plural+N falls back to the spec verbatim.
        assert d.period_label == "prior 7 days"

    def test_delta_supports_week_unit(self) -> None:
        src = """module t
app t "Test"
entity E:
  id: uuid pk
  created_at: datetime auto_add
workspace dash "Dash":
  r:
    aggregate:
      count: count(E)
    display: summary
    delta:
      period: 1 week
"""
        mod = _parse(src)
        d = mod.workspaces[0].regions[0].delta
        assert d.period_seconds == 604800
        assert d.period_label == "last week"

    def test_invalid_period_unit_raises(self) -> None:
        src = """module t
app t "Test"
entity E:
  id: uuid pk
  created_at: datetime auto_add
workspace dash "Dash":
  r:
    aggregate:
      count: count(E)
    display: summary
    delta:
      period: 1 fortnight
"""
        with pytest.raises(Exception, match="delta.period unit"):
            _parse(src)

    def test_invalid_sentiment_raises(self) -> None:
        src = """module t
app t "Test"
entity E:
  id: uuid pk
  created_at: datetime auto_add
workspace dash "Dash":
  r:
    aggregate:
      count: count(E)
    display: summary
    delta:
      period: 1 day
      sentiment: bullish
"""
        with pytest.raises(Exception, match="delta.sentiment"):
            _parse(src)

    def test_period_required(self) -> None:
        src = """module t
app t "Test"
entity E:
  id: uuid pk
  created_at: datetime auto_add
workspace dash "Dash":
  r:
    aggregate:
      count: count(E)
    display: summary
    delta:
      sentiment: positive_up
"""
        with pytest.raises(Exception, match="delta block requires"):
            _parse(src)

    def test_delta_absent_by_default(self) -> None:
        """Existing summary regions without a delta block continue to parse
        with `region.delta is None`."""
        src = """module t
app t "Test"
entity E:
  id: uuid pk
workspace dash "Dash":
  r:
    aggregate:
      count: count(E)
    display: summary
"""
        mod = _parse(src)
        assert mod.workspaces[0].regions[0].delta is None


# ───────────────────────────── ir ──────────────────────────────


class TestDeltaSpec:
    def test_defaults(self) -> None:
        d = DeltaSpec(period_seconds=86400)
        assert d.sentiment == "positive_up"
        assert d.date_field is None
        assert d.period_label == "prior period"

    def test_frozen(self) -> None:
        from pydantic import ValidationError

        d = DeltaSpec(period_seconds=86400)
        with pytest.raises(ValidationError):
            d.sentiment = "neutral"  # type: ignore[misc]

    def test_period_seconds_must_be_positive(self) -> None:
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            DeltaSpec(period_seconds=0)


# ─────────────────────────── runtime ────────────────────────────


class TestComputeAggregateMetricsDelta:
    """`_compute_aggregate_metrics` attaches delta keys to each metric when a
    delta spec is supplied. The prior-period repository query is mocked."""

    def _make_repo(self, current_total: int, prior_total: int) -> MagicMock:
        """Return a repo whose `.list()` returns prior_total when the call
        carries a date-range filter, current_total otherwise."""
        repo = MagicMock()

        async def _list(page=1, page_size=1, filters=None):
            filters = filters or {}
            is_prior_window = any(k.endswith("__gte") or k.endswith("__lt") for k in filters)
            return {"total": prior_total if is_prior_window else current_total, "items": []}

        repo.list = AsyncMock(side_effect=_list)
        return repo

    def _run(self, current: int, prior: int, *, sentiment: str = "positive_up") -> dict:
        from dazzle_back.runtime.workspace_rendering import _compute_aggregate_metrics

        repo = self._make_repo(current, prior)
        delta = DeltaSpec(period_seconds=86400, sentiment=sentiment, period_label="yesterday")
        result = asyncio.run(
            _compute_aggregate_metrics(
                aggregates={"manuscripts_marked": "count(Manuscript where status = marked)"},
                repositories={"Manuscript": repo},
                total=0,
                items=[],
                scope_filters=None,
                delta=delta,
            )
        )
        assert len(result) == 1
        return result[0]

    def test_positive_delta_up(self) -> None:
        m = self._run(current=47, prior=35)
        assert m["value"] == 47
        assert m["delta"] == 12
        # Approx (47-35)/35 = 34.3 → rounded to one decimal
        assert m["delta_pct"] == pytest.approx(34.3, abs=0.05)
        assert m["delta_direction"] == "up"
        assert m["delta_sentiment"] == "positive_up"
        assert m["delta_period_label"] == "yesterday"

    def test_negative_delta_down(self) -> None:
        m = self._run(current=20, prior=50)
        assert m["delta"] == -30
        assert m["delta_direction"] == "down"

    def test_flat_delta(self) -> None:
        m = self._run(current=10, prior=10)
        assert m["delta"] == 0
        assert m["delta_direction"] == "flat"
        assert m["delta_pct"] == 0.0

    def test_prior_zero_pct_is_zero_not_div_zero(self) -> None:
        """When prior is 0, pct is set to 0 rather than raising ZeroDivisionError."""
        m = self._run(current=5, prior=0)
        assert m["delta"] == 5
        assert m["delta_pct"] == 0.0
        assert m["delta_direction"] == "up"

    def test_no_delta_keys_when_spec_absent(self) -> None:
        from dazzle_back.runtime.workspace_rendering import _compute_aggregate_metrics

        repo = self._make_repo(current_total=42, prior_total=999)
        result = asyncio.run(
            _compute_aggregate_metrics(
                aggregates={"items": "count(Item)"},
                repositories={"Item": repo},
                total=0,
                items=[],
                scope_filters=None,
                delta=None,
            )
        )
        m = result[0]
        assert m["value"] == 42
        assert "delta" not in m
        assert "delta_direction" not in m

    def test_sentiment_flows_through(self) -> None:
        m = self._run(current=5, prior=10, sentiment="positive_down")
        assert m["delta_sentiment"] == "positive_down"
