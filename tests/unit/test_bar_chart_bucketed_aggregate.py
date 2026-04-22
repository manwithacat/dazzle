"""
Regression tests for bar_chart bucketed aggregates (#847).

Pre-fix, bar_chart counted source rows per `group_by` value and silently
dropped any `aggregate:` clause — so a `count(Manuscript where ...)`
expression intended to express "manuscripts per grade band" rendered
the wrong number on every bar.

The fix wires `_compute_bucketed_aggregates` to evaluate the aggregate
expression once per bucket, substituting the bucket value into the
where clause.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from dazzle_back.runtime.workspace_rendering import (
    _compute_bucketed_aggregates,
)


def _make_repo_returning(*totals: int) -> MagicMock:
    """Repo whose .list returns successive {'total': T} dicts."""
    repo = MagicMock()
    iterator = iter(totals)
    repo.list = AsyncMock(side_effect=lambda **kw: {"total": next(iterator)})
    return repo


class TestBucketedAggregates:
    @pytest.mark.asyncio()
    async def test_no_aggregates_returns_empty(self) -> None:
        result = await _compute_bucketed_aggregates({}, None, "grade", [])
        assert result == []

    @pytest.mark.asyncio()
    async def test_no_repo_returns_empty(self) -> None:
        result = await _compute_bucketed_aggregates(
            {"students": "count(Manuscript where computed_grade = current_bucket)"},
            None,
            "grade",
            [{"grade": "9"}],
        )
        assert result == []

    @pytest.mark.asyncio()
    async def test_distinct_items_drive_buckets(self) -> None:
        """When no bucket_values supplied, derive from distinct items[group_by]."""
        repo = _make_repo_returning(12, 7, 3)
        result = await _compute_bucketed_aggregates(
            {"students": "count(Manuscript where computed_grade = current_bucket)"},
            {"Manuscript": repo},
            "computed_grade",
            [{"computed_grade": "9"}, {"computed_grade": "8"}, {"computed_grade": "7"}],
        )
        assert result == [
            {"label": "9", "value": 12},
            {"label": "8", "value": 7},
            {"label": "7", "value": 3},
        ]
        # One DB query per bucket.
        assert repo.list.await_count == 3

    @pytest.mark.asyncio()
    async def test_bucket_values_override_items(self) -> None:
        """Pre-supplied buckets (from enum/state-machine) come first."""
        repo = _make_repo_returning(0, 5, 0)
        result = await _compute_bucketed_aggregates(
            {"students": "count(Manuscript where computed_grade = current_bucket)"},
            {"Manuscript": repo},
            "computed_grade",
            [],
            bucket_values=["A", "B", "C"],
        )
        assert [r["label"] for r in result] == ["A", "B", "C"]
        assert [r["value"] for r in result] == [0, 5, 0]

    @pytest.mark.asyncio()
    async def test_no_current_bucket_sentinel_falls_back_to_group_by_filter(self) -> None:
        """Author can omit `current_bucket` — runtime adds `group_by = bucket`."""
        repo = _make_repo_returning(11, 4)
        await _compute_bucketed_aggregates(
            {"students": "count(Manuscript)"},
            {"Manuscript": repo},
            "computed_grade",
            [{"computed_grade": "9"}, {"computed_grade": "8"}],
        )
        # _fetch_count_metric → repo.list with merged filters; verify the
        # group_by field appears in each call's filter dict.
        calls = repo.list.await_args_list
        assert len(calls) == 2
        for call in calls:
            filters = call.kwargs.get("filters") or {}
            assert "computed_grade" in filters

    @pytest.mark.asyncio()
    async def test_non_count_aggregate_ignored(self) -> None:
        """Only count(Entity where ...) expressions are bucketed today."""
        repo = MagicMock()
        result = await _compute_bucketed_aggregates(
            {"avg_score": "avg(Manuscript)"},
            {"Manuscript": repo},
            "computed_grade",
            [{"computed_grade": "9"}],
        )
        assert result == []

    @pytest.mark.asyncio()
    async def test_scope_filters_merged_into_each_bucket_query(self) -> None:
        """Per-bucket queries must include scope filters (security gate, #574)."""
        repo = _make_repo_returning(1, 2)
        await _compute_bucketed_aggregates(
            {"students": "count(Manuscript where computed_grade = current_bucket)"},
            {"Manuscript": repo},
            "computed_grade",
            [{"computed_grade": "9"}, {"computed_grade": "8"}],
            scope_filters={"school_id": "abc"},
        )
        calls = repo.list.await_args_list
        for call in calls:
            filters = call.kwargs.get("filters") or {}
            assert filters.get("school_id") == "abc"
