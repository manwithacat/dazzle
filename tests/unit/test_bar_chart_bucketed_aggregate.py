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


# ---------------------------------------------------------------------------
# Source-entity bucket enumeration + UUID-shaped per-bucket filters (#849)
# ---------------------------------------------------------------------------


def _make_capturing_repo(*totals: int):
    """Repo whose .list captures each call's filters and returns successive totals."""
    repo = MagicMock()
    captured: list[dict] = []
    iterator = iter(totals)

    async def _list(**kw):
        captured.append(dict(kw.get("filters") or {}))
        return {"total": next(iterator)}

    repo.list = AsyncMock(side_effect=_list)
    return repo, captured


def _make_source_repo_returning(*pages):
    """Source repo whose .list returns paged result pages.

    Each page: list of dict items. The repo emits the pages in order.
    """
    repo = MagicMock()
    page_iter = iter(pages)

    async def _list(**kw):
        try:
            items = next(page_iter)
        except StopIteration:
            items = []
        return {"items": items, "total": 0}

    repo.list = AsyncMock(side_effect=_list)
    return repo


class TestSourceEntityBucketEnumeration:
    """#849 Bug B: buckets must come from the full source entity, not page 1."""

    @pytest.mark.asyncio()
    async def test_buckets_pulled_from_source_repo_not_items(self) -> None:
        """Items page is short; source repo carries the full bucket set."""
        agg_repo, captured = _make_capturing_repo(10, 5, 3)
        # Source returns A, B, C in a single < page_size page (terminates loop).
        source_repo = _make_source_repo_returning(
            [
                {"target": {"id": "A", "label": "A"}},
                {"target": {"id": "B", "label": "B"}},
                {"target": {"id": "C", "label": "C"}},
            ],
            [],
        )
        result = await _compute_bucketed_aggregates(
            {"count": "count(MarkingResult)"},
            {"MarkingResult": agg_repo, "Source": source_repo},
            "target",
            items=[{"target": {"id": "A", "label": "A"}}],  # only A on first page
            source_entity="Source",
        )
        assert sorted(r["label"] for r in result) == ["A", "B", "C"]

    @pytest.mark.asyncio()
    async def test_pagination_continues_until_short_page(self) -> None:
        """Full page (200) keeps loop alive; short page terminates it."""
        full_page = [{"target": {"id": f"X{i}", "label": f"X{i}"}} for i in range(200)]
        agg_repo = MagicMock()
        agg_repo.list = AsyncMock(return_value={"total": 1})
        source_repo = _make_source_repo_returning(
            full_page,
            [{"target": {"id": "Y", "label": "Y"}}],
            [],
        )
        result = await _compute_bucketed_aggregates(
            {"count": "count(MarkingResult)"},
            {"MarkingResult": agg_repo, "Source": source_repo},
            "target",
            items=[],
            source_entity="Source",
        )
        # 200 X-buckets + Y = 201
        assert len(result) == 201
        assert any(r["label"] == "Y" for r in result)

    @pytest.mark.asyncio()
    async def test_falls_back_to_items_when_no_source_entity(self) -> None:
        """Without source_entity, the items-page fallback still works."""
        agg_repo, _ = _make_capturing_repo(7)
        result = await _compute_bucketed_aggregates(
            {"count": "count(MarkingResult)"},
            {"MarkingResult": agg_repo},
            "computed_grade",
            [{"computed_grade": "9"}],
        )
        assert len(result) == 1
        assert result[0]["label"] == "9"

    @pytest.mark.asyncio()
    async def test_bucket_values_override_source_query(self) -> None:
        """Pre-supplied buckets (enum/state-machine) skip the source query entirely."""
        agg_repo, _ = _make_capturing_repo(0, 0)
        source_repo = _make_source_repo_returning([{"target": {"id": "ignored"}}])
        await _compute_bucketed_aggregates(
            {"count": "count(MarkingResult)"},
            {"MarkingResult": agg_repo, "Source": source_repo},
            "target",
            items=[],
            bucket_values=["A", "B"],
            source_entity="Source",
        )
        # Source repo must not be queried when bucket_values is supplied.
        source_repo.list.assert_not_called()

    @pytest.mark.asyncio()
    async def test_source_query_failure_falls_back_to_items(self) -> None:
        """If the source repo raises, we must not crash — fall back to items."""
        agg_repo, _ = _make_capturing_repo(4)
        source_repo = MagicMock()
        source_repo.list = AsyncMock(side_effect=RuntimeError("DB down"))
        result = await _compute_bucketed_aggregates(
            {"count": "count(MarkingResult)"},
            {"MarkingResult": agg_repo, "Source": source_repo},
            "computed_grade",
            [{"computed_grade": "9"}],
            source_entity="Source",
        )
        # Items fallback yields one bucket "9".
        assert len(result) == 1
        assert result[0]["label"] == "9"


class TestPerBucketFilterShape:
    """#849 Bug A: auto-augmented filter must be `{group_by: bucket_key}` directly."""

    @pytest.mark.asyncio()
    async def test_auto_augment_passes_filter_dict_not_string(self) -> None:
        """The repo must receive {group_by: bucket} as a dict, no parser detour."""
        agg_repo, captured = _make_capturing_repo(1560)
        await _compute_bucketed_aggregates(
            {"count": "count(MarkingResult)"},
            {"MarkingResult": agg_repo},
            "assessment_objective",
            items=[{"assessment_objective": {"id": "55a15a5d-be5e-4abc-9def-aabbccddeeff"}}],
        )
        assert len(captured) == 1
        # Filter dict goes straight to the repo with the FK id as the value.
        assert captured[0] == {"assessment_objective": "55a15a5d-be5e-4abc-9def-aabbccddeeff"}

    @pytest.mark.asyncio()
    async def test_auto_augment_merges_scope_filters(self) -> None:
        agg_repo, captured = _make_capturing_repo(42)
        await _compute_bucketed_aggregates(
            {"count": "count(MarkingResult)"},
            {"MarkingResult": agg_repo},
            "assessment_objective",
            items=[{"assessment_objective": {"id": "ao-1"}}],
            scope_filters={"school_id": "abc"},
        )
        assert captured[0] == {"school_id": "abc", "assessment_objective": "ao-1"}

    @pytest.mark.asyncio()
    async def test_per_bucket_query_failure_returns_zero(self) -> None:
        """A per-bucket query exception must not crash the whole render."""
        agg_repo = MagicMock()
        agg_repo.list = AsyncMock(side_effect=RuntimeError("connection lost"))
        result = await _compute_bucketed_aggregates(
            {"count": "count(MarkingResult)"},
            {"MarkingResult": agg_repo},
            "assessment_objective",
            items=[{"assessment_objective": {"id": "ao-1"}}],
        )
        assert result == [{"label": "ao-1", "value": 0}]
