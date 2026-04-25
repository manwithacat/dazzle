"""Tests for the v0.61.32 multi-measure aggregate pipeline (#879/#883 enabling).

Two layers:
  1. ``_aggregate_via_groupby`` accepts a ``measures: dict[str, str]``
     mapping (rather than a single ``metric_name``) and returns each
     bucket with both the legacy ``value`` (first measure) AND a
     ``metrics: {<name>: <value>, ...}`` sub-dict for templates that
     want all of them.
  2. ``_compute_bucketed_aggregates`` parses ALL aggregate expressions
     from the DSL block and fires them as one multi-measure GROUP BY
     query when they all qualify for the fast path. ``avg(<col>)`` /
     ``sum(<col>)`` / ``min(<col>)`` / ``max(<col>)`` against a column
     on the source entity now resolve cleanly (#880's investigation
     surfaced the gap; landed here as the foundation for #879
     multi-series radar and #883 overlay_series).
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from dazzle_back.runtime.aggregate import AggregateBucket
from dazzle_back.runtime.workspace_rendering import (
    _aggregate_via_groupby,
    _compute_bucketed_aggregates,
)


def _make_aggregate_repo(buckets: list[dict]) -> MagicMock:
    repo = MagicMock()
    repo.aggregate = AsyncMock(
        return_value=[
            AggregateBucket(dimensions=b["dimensions"], measures=b["measures"]) for b in buckets
        ]
    )
    repo.entity_spec = MagicMock(fields=[], name="MarkingResult")
    return repo


# ───────────────── _aggregate_via_groupby ──────────────────


class TestAggregateViaGroupbyMultiMeasure:
    @pytest.mark.asyncio
    async def test_two_measures_in_one_query(self) -> None:
        """Both measures must be passed to ``agg_repo.aggregate`` in one
        call; result rows carry both values."""
        repo = _make_aggregate_repo(
            [
                {
                    "dimensions": {"ao": "ao-1", "ao_label": "Knowledge"},
                    "measures": {"actual": 65.0, "target": 70.0},
                },
                {
                    "dimensions": {"ao": "ao-2", "ao_label": "Application"},
                    "measures": {"actual": 75.0, "target": 60.0},
                },
            ]
        )
        rows = await _aggregate_via_groupby(
            repo,
            measures={"actual": "avg:scaled_mark", "target": "avg:target_mark"},
            group_by="ao",
            where_clause=None,
            scope_filters=None,
            source_entity_spec=None,
            fk_target_spec=None,
        )
        # One round-trip
        assert repo.aggregate.await_count == 1
        # Measures dict was forwarded verbatim
        passed_measures = repo.aggregate.call_args.kwargs["measures"]
        assert passed_measures == {"actual": "avg:scaled_mark", "target": "avg:target_mark"}
        # Returned rows carry value (first measure) AND metrics dict
        assert rows == [
            {
                "label": "Knowledge",
                "value": 65.0,
                "metrics": {"actual": 65.0, "target": 70.0},
            },
            {
                "label": "Application",
                "value": 75.0,
                "metrics": {"actual": 75.0, "target": 60.0},
            },
        ]

    @pytest.mark.asyncio
    async def test_first_measure_drives_legacy_value(self) -> None:
        """Order matters — `value` is the FIRST measure declared in
        ``measures``. Templates that only know `value` continue working."""
        repo = _make_aggregate_repo(
            [{"dimensions": {"x": "a", "x_label": "A"}, "measures": {"alpha": 1, "beta": 2}}]
        )
        rows = await _aggregate_via_groupby(
            repo,
            measures={"alpha": "count", "beta": "avg:something"},
            group_by="x",
            where_clause=None,
            scope_filters=None,
            source_entity_spec=None,
            fk_target_spec=None,
        )
        assert rows[0]["value"] == 1  # first measure
        assert rows[0]["metrics"] == {"alpha": 1, "beta": 2}

    @pytest.mark.asyncio
    async def test_empty_measures_returns_empty(self) -> None:
        repo = _make_aggregate_repo([])
        rows = await _aggregate_via_groupby(
            repo,
            measures={},
            group_by="x",
            where_clause=None,
            scope_filters=None,
            source_entity_spec=None,
            fk_target_spec=None,
        )
        assert rows == []
        assert repo.aggregate.await_count == 0


# ───────────────── _compute_bucketed_aggregates ──────────────────


class TestComputeBucketedAggregatesMultiMeasure:
    @pytest.mark.asyncio
    async def test_avg_column_aggregate_resolves(self) -> None:
        """``avg(<column>)`` against the source entity now reaches the
        fast path. Previously the func-must-be-count gate dropped it
        silently."""
        repo = _make_aggregate_repo(
            [
                {
                    "dimensions": {"ao": "ao-1", "ao_label": "Knowledge"},
                    "measures": {"avg_mark": 6.5},
                },
            ]
        )
        result = await _compute_bucketed_aggregates(
            {"avg_mark": "avg(scaled_mark)"},
            {"MarkingResult": repo},
            "ao",
            items=[],
            source_entity="MarkingResult",
        )
        assert result == [{"label": "Knowledge", "value": 6.5, "metrics": {"avg_mark": 6.5}}]
        # The avg measure spec was passed through correctly
        passed = repo.aggregate.call_args.kwargs["measures"]
        assert passed == {"avg_mark": "avg:scaled_mark"}

    @pytest.mark.asyncio
    async def test_two_aggregates_same_source_one_query(self) -> None:
        """Two measures over the same source — fired in one query."""
        repo = _make_aggregate_repo(
            [
                {
                    "dimensions": {"ao": "ao-1", "ao_label": "Knowledge"},
                    "measures": {"actual": 6.5, "target": 7.0},
                },
                {
                    "dimensions": {"ao": "ao-2", "ao_label": "Application"},
                    "measures": {"actual": 5.5, "target": 6.0},
                },
            ]
        )
        result = await _compute_bucketed_aggregates(
            {
                "actual": "avg(scaled_mark)",
                "target": "avg(target_mark)",
            },
            {"MarkingResult": repo},
            "ao",
            items=[],
            source_entity="MarkingResult",
        )
        assert repo.aggregate.await_count == 1
        assert result[0]["metrics"] == {"actual": 6.5, "target": 7.0}
        assert result[1]["metrics"] == {"actual": 5.5, "target": 6.0}
        # `value` is the FIRST aggregate — preserves single-series template compat
        assert result[0]["value"] == 6.5

    @pytest.mark.asyncio
    async def test_count_and_avg_mixed(self) -> None:
        """Mixing count + avg in one block both qualify for the fast
        path so long as they target the same source."""
        repo = _make_aggregate_repo(
            [
                {
                    "dimensions": {"ao": "ao-1", "ao_label": "Knowledge"},
                    "measures": {"n": 10, "avg": 6.5},
                },
            ]
        )
        result = await _compute_bucketed_aggregates(
            {"n": "count(MarkingResult)", "avg": "avg(scaled_mark)"},
            {"MarkingResult": repo},
            "ao",
            items=[],
            source_entity="MarkingResult",
        )
        passed = repo.aggregate.call_args.kwargs["measures"]
        assert passed == {"n": "count", "avg": "avg:scaled_mark"}
        assert result[0]["metrics"] == {"n": 10, "avg": 6.5}

    @pytest.mark.asyncio
    async def test_sum_min_max_aggregates(self) -> None:
        repo = _make_aggregate_repo(
            [
                {
                    "dimensions": {"ao": "ao-1", "ao_label": "Knowledge"},
                    "measures": {"total": 65.0, "lo": 30.0, "hi": 90.0},
                },
            ]
        )
        result = await _compute_bucketed_aggregates(
            {
                "total": "sum(scaled_mark)",
                "lo": "min(scaled_mark)",
                "hi": "max(scaled_mark)",
            },
            {"MarkingResult": repo},
            "ao",
            items=[],
            source_entity="MarkingResult",
        )
        passed = repo.aggregate.call_args.kwargs["measures"]
        assert passed == {
            "total": "sum:scaled_mark",
            "lo": "min:scaled_mark",
            "hi": "max:scaled_mark",
        }
        assert result[0]["metrics"]["total"] == 65.0
