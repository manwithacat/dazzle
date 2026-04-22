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
    _bucket_key_label,
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


# ---------------------------------------------------------------------------
# FK group_by — buckets derived from {id, display_field, ...} dicts (#848)
# ---------------------------------------------------------------------------


class TestBucketKeyLabel:
    def test_scalar_passes_through(self) -> None:
        assert _bucket_key_label("9") == ("9", "9")
        assert _bucket_key_label(42) == ("42", "42")

    def test_fk_dict_uses_id_for_key_and_display_for_label(self) -> None:
        v = {"id": "uuid-1", "code": "AO1", "label": "Knowledge"}
        # display_name → name → title → label → code probe order.
        # `label` wins over `code` because it appears first in the probe list.
        assert _bucket_key_label(v) == ("uuid-1", "Knowledge")

    def test_fk_dict_falls_back_to_code_when_no_label(self) -> None:
        v = {"id": "uuid-2", "code": "AO2"}
        assert _bucket_key_label(v) == ("uuid-2", "AO2")

    def test_fk_dict_uses_id_as_label_when_no_display_field(self) -> None:
        v = {"id": "uuid-3", "irrelevant_field": "x"}
        assert _bucket_key_label(v) == ("uuid-3", "uuid-3")

    def test_fk_dict_prefers_display_name(self) -> None:
        v = {"id": "uuid-4", "display_name": "Alice", "name": "alice123", "code": "A"}
        assert _bucket_key_label(v) == ("uuid-4", "Alice")


class TestBucketedAggregatesWithFK:
    @pytest.mark.asyncio()
    async def test_fk_buckets_use_id_as_filter_value(self) -> None:
        """Per-bucket filter must use the FK id, not the stringified dict (#848)."""
        repo = _make_repo_returning(7, 4)
        items = [
            {"assessment_objective": {"id": "ao-1", "code": "AO1", "label": "Knowledge"}},
            {"assessment_objective": {"id": "ao-2", "code": "AO2", "label": "Application"}},
        ]
        result = await _compute_bucketed_aggregates(
            {"count": "count(MarkingResult)"},
            {"MarkingResult": repo},
            "assessment_objective",
            items,
        )
        assert result == [
            {"label": "Knowledge", "value": 7},
            {"label": "Application", "value": 4},
        ]
        # The filter passed to repo.list must be `assessment_objective: ao-N`,
        # not the dict-repr Python string.
        calls = repo.list.await_args_list
        seen_filter_values = sorted(
            c.kwargs.get("filters", {}).get("assessment_objective", "") for c in calls
        )
        assert seen_filter_values == ["ao-1", "ao-2"]

    @pytest.mark.asyncio()
    async def test_duplicate_fk_dicts_dedupe_on_id(self) -> None:
        """Two items pointing at the same FK row → one bucket."""
        repo = _make_repo_returning(3)
        items = [
            {"target": {"id": "t-1", "label": "T"}},
            # Same id, slightly different other fields — still one bucket.
            {"target": {"id": "t-1", "label": "T", "extra": "noise"}},
        ]
        result = await _compute_bucketed_aggregates(
            {"count": "count(Other)"},
            {"Other": repo},
            "target",
            items,
        )
        assert len(result) == 1
        assert result[0]["label"] == "T"
        assert result[0]["value"] == 3

    @pytest.mark.asyncio()
    async def test_current_bucket_substituted_with_id(self) -> None:
        """`where x = current_bucket` must substitute the id, not the dict."""
        repo = _make_repo_returning(5)
        items = [{"target": {"id": "t-1", "label": "T"}}]
        await _compute_bucketed_aggregates(
            {"count": "count(Other where target = current_bucket)"},
            {"Other": repo},
            "target",
            items,
        )
        # _parse_simple_where turns `target = t-1` into {"target": "t-1"}.
        call = repo.list.await_args_list[0]
        assert call.kwargs.get("filters", {}).get("target") == "t-1"
