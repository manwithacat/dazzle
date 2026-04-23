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


# ---------------------------------------------------------------------------
# #850: scope-aware enumeration must not silently fall back to items page
# when source query succeeded with zero rows; FK relation must be loaded
# via include=[group_by] so model_dump produces the expected dict shape.
# ---------------------------------------------------------------------------


def _make_capturing_source_repo(*pages):
    """Source repo that captures every .list call's kwargs.

    Returns ``(repo, captured_kwargs_list)``. The ``include=[group_by]``
    arg from #850 must appear in every captured call.
    """
    repo = MagicMock()
    captured: list[dict] = []
    page_iter = iter(pages)

    async def _list(**kw):
        captured.append(dict(kw))
        try:
            items = next(page_iter)
        except StopIteration:
            items = []
        return {"items": items, "total": 0}

    repo.list = AsyncMock(side_effect=_list)
    return repo, captured


class TestSourceEnumerationSuccessFlag:
    """#850: distinguish 'enumeration succeeded with 0 rows' from 'enumeration raised'."""

    @pytest.mark.asyncio()
    async def test_empty_successful_enumeration_does_not_fall_back(self) -> None:
        """Source returned no rows → render no bars, NOT page-1 stale buckets."""
        agg_repo, _ = _make_capturing_repo()
        source_repo, _ = _make_capturing_source_repo([])  # zero rows, no exception
        result = await _compute_bucketed_aggregates(
            {"count": "count(MarkingResult)"},
            {"MarkingResult": agg_repo, "Source": source_repo},
            "criterion",
            # items has stale data but enum succeeded → must NOT fall back.
            items=[{"criterion": {"id": "STALE", "label": "Stale"}}],
            source_entity="Source",
        )
        assert result == []
        agg_repo.list.assert_not_called()  # no per-bucket queries either

    @pytest.mark.asyncio()
    async def test_exception_falls_back_to_items(self) -> None:
        """Source raised → fall back to items-page derivation as last resort."""
        agg_repo, _ = _make_capturing_repo(8)
        source_repo = MagicMock()
        source_repo.list = AsyncMock(side_effect=RuntimeError("DB down"))
        result = await _compute_bucketed_aggregates(
            {"count": "count(MarkingResult)"},
            {"MarkingResult": agg_repo, "Source": source_repo},
            "criterion",
            items=[{"criterion": {"id": "fallback", "label": "FB"}}],
            source_entity="Source",
        )
        assert result == [{"label": "FB", "value": 8}]


class TestSourceEnumerationFKExpansion:
    """#850: source query must request include=[group_by] so FK expands to dict."""

    @pytest.mark.asyncio()
    async def test_include_passed_to_source_list(self) -> None:
        agg_repo, _ = _make_capturing_repo(0)
        source_repo, captured = _make_capturing_source_repo(
            [{"criterion": {"id": "c-1", "label": "Crit1"}}],
            [],
        )
        await _compute_bucketed_aggregates(
            {"count": "count(Review)"},
            {"Review": agg_repo, "Source": source_repo},
            "criterion",
            items=[],
            source_entity="Source",
        )
        assert len(captured) >= 1
        # Every source query must request the FK relation explicitly,
        # otherwise model_dump returns a raw UUID string instead of the
        # {id, label, ...} dict and the bar renders as a UUID.
        for call_kw in captured:
            assert call_kw.get("include") == ["criterion"]

    @pytest.mark.asyncio()
    async def test_scope_filters_passed_to_source_list(self) -> None:
        """Scope filters must reach source repo (REST/bucketed parity)."""
        agg_repo, _ = _make_capturing_repo(5)
        source_repo, captured = _make_capturing_source_repo(
            [{"criterion": {"id": "c-1", "label": "Crit1"}}],
            [],
        )
        await _compute_bucketed_aggregates(
            {"count": "count(Review)"},
            {"Review": agg_repo, "Source": source_repo},
            "criterion",
            items=[],
            source_entity="Source",
            scope_filters={"__scope_predicate": ("dept = $1", ["d-1"])},
        )
        # First source call must carry the scope filter dict.
        assert captured[0].get("filters") == {"__scope_predicate": ("dept = $1", ["d-1"])}


# ---------------------------------------------------------------------------
# #851: per-bucket count call must mirror the items-list call (pass include).
# ---------------------------------------------------------------------------


def _make_capturing_agg_repo(*totals: int):
    """Repo whose .list captures kwargs and returns successive totals."""
    repo = MagicMock()
    captured: list[dict] = []
    iterator = iter(totals)

    async def _list(**kw):
        captured.append(dict(kw))
        return {"total": next(iterator)}

    repo.list = AsyncMock(side_effect=_list)
    return repo, captured


class TestPerBucketIncludesGroupBy:
    """#851: per-bucket repo call must pass include=[group_by] like the items path."""

    @pytest.mark.asyncio()
    async def test_per_bucket_passes_include(self) -> None:
        agg_repo, captured = _make_capturing_agg_repo(7)
        await _compute_bucketed_aggregates(
            {"count": "count(MarkingResult)"},
            {"MarkingResult": agg_repo},
            "assessment_objective",
            items=[{"assessment_objective": {"id": "ao-1", "label": "AO1"}}],
        )
        assert len(captured) == 1
        assert captured[0].get("include") == ["assessment_objective"]

    @pytest.mark.asyncio()
    async def test_per_bucket_filter_shape_unchanged(self) -> None:
        """The new include arg must not perturb the filter dict shape."""
        agg_repo, captured = _make_capturing_agg_repo(42)
        await _compute_bucketed_aggregates(
            {"count": "count(MarkingResult)"},
            {"MarkingResult": agg_repo},
            "assessment_objective",
            items=[{"assessment_objective": {"id": "ao-1"}}],
            scope_filters={"__scope_predicate": ("dept = $1", ["d-1"])},
        )
        f = captured[0].get("filters") or {}
        assert f.get("assessment_objective") == "ao-1"
        assert f.get("__scope_predicate") == ("dept = $1", ["d-1"])


# ---------------------------------------------------------------------------
# Strategy C (Cycle 22): fast GROUP BY path via Repository.aggregate
# ---------------------------------------------------------------------------


def _make_aggregate_repo(buckets_payload):
    """Repo whose .aggregate returns the given list of AggregateBucket objects."""
    from dazzle_back.runtime.aggregate import AggregateBucket

    repo = MagicMock()
    repo.entity_spec = SimpleNamespace(
        name="MarkingResult",
        fields=[
            SimpleNamespace(
                name="assessment_objective",
                type=SimpleNamespace(kind="ref", ref_entity="AssessmentObjective"),
            )
        ],
    )

    async def _aggregate(**kw):
        # Convert dict payloads to AggregateBucket so the function under
        # test sees realistic shapes.
        return [
            b if isinstance(b, AggregateBucket) else AggregateBucket(**b) for b in buckets_payload
        ]

    repo.aggregate = AsyncMock(side_effect=_aggregate)
    return repo


def _make_target_repo_with_label_field():
    """FK target repo with a `label` field (so display-field probe picks it)."""
    repo = MagicMock()
    repo.entity_spec = SimpleNamespace(
        name="AssessmentObjective",
        fields=[
            SimpleNamespace(name="id"),
            SimpleNamespace(name="label"),
            SimpleNamespace(name="code"),
        ],
    )
    return repo


from types import SimpleNamespace  # noqa: E402  (used only by the new tests above)


class TestStrategyCGroupByFastPath:
    """Cycle 22 — count(<source>) routes through repo.aggregate, not the loop."""

    @pytest.mark.asyncio()
    async def test_simple_distribution_uses_aggregate_call(self) -> None:
        agg_repo = _make_aggregate_repo(
            [
                {
                    "dimensions": {
                        "assessment_objective": "ao-1",
                        "assessment_objective_label": "Knowledge",
                    },
                    "measures": {"count": 1560},
                },
                {
                    "dimensions": {
                        "assessment_objective": "ao-2",
                        "assessment_objective_label": "Application",
                    },
                    "measures": {"count": 720},
                },
            ]
        )
        target_repo = _make_target_repo_with_label_field()
        result = await _compute_bucketed_aggregates(
            {"count": "count(MarkingResult)"},
            {"MarkingResult": agg_repo, "AssessmentObjective": target_repo},
            "assessment_objective",
            items=[],
            source_entity="MarkingResult",
        )
        assert result == [
            {"label": "Knowledge", "value": 1560},
            {"label": "Application", "value": 720},
        ]
        # The fast path must call .aggregate exactly once — no enumeration,
        # no per-bucket loop.
        agg_repo.aggregate.assert_called_once()
        call_kwargs = agg_repo.aggregate.call_args.kwargs
        # Cycle 25: dimensions is now a list of Dimension objects; one-dim
        # bar chart sends a single-element list with the FK target wired.
        dims = call_kwargs["dimensions"]
        assert len(dims) == 1
        assert dims[0].name == "assessment_objective"
        assert dims[0].fk_table == "AssessmentObjective"
        assert dims[0].fk_display_field == "label"

    @pytest.mark.asyncio()
    async def test_scope_filters_passed_to_aggregate_call(self) -> None:
        agg_repo = _make_aggregate_repo([])
        target_repo = _make_target_repo_with_label_field()
        await _compute_bucketed_aggregates(
            {"count": "count(MarkingResult)"},
            {"MarkingResult": agg_repo, "AssessmentObjective": target_repo},
            "assessment_objective",
            items=[],
            source_entity="MarkingResult",
            scope_filters={"__scope_predicate": ('"MarkingResult"."dept" = %s', ["d-1"])},
        )
        kw = agg_repo.aggregate.call_args.kwargs
        assert "__scope_predicate" in (kw.get("filters") or {})

    @pytest.mark.asyncio()
    async def test_aggregate_failure_falls_back_to_slow_path(self) -> None:
        """If .aggregate raises, the old enumeration loop kicks in as backup."""
        agg_repo = _make_aggregate_repo([])
        agg_repo.aggregate = AsyncMock(side_effect=RuntimeError("no SQL backend"))
        # Equip the repo with a .list method too so the slow path can run.
        list_call_count = {"n": 0}

        async def _list(**kw):
            list_call_count["n"] += 1
            return {"items": [], "total": 0}

        agg_repo.list = AsyncMock(side_effect=_list)
        result = await _compute_bucketed_aggregates(
            {"count": "count(MarkingResult)"},
            {"MarkingResult": agg_repo},
            "assessment_objective",
            items=[],
            source_entity="MarkingResult",
        )
        # Slow-path enumeration ran (called .list at least once for source).
        assert list_call_count["n"] >= 1
        assert result == []  # empty source → empty buckets

    @pytest.mark.asyncio()
    async def test_bucket_values_supplied_skips_fast_path(self) -> None:
        """Pre-supplied buckets (enum/state-machine) keep using the slow loop."""
        agg_repo = _make_aggregate_repo([])
        agg_repo.list = AsyncMock(return_value={"total": 5})
        await _compute_bucketed_aggregates(
            {"count": "count(MarkingResult)"},
            {"MarkingResult": agg_repo},
            "status",
            items=[],
            bucket_values=["draft", "published"],
            source_entity="MarkingResult",
        )
        # Fast-path .aggregate must NOT be called when bucket_values is set.
        agg_repo.aggregate.assert_not_called()
        assert agg_repo.list.await_count == 2  # one per bucket

    @pytest.mark.asyncio()
    async def test_cross_entity_count_skips_fast_path(self) -> None:
        """count(OtherEntity ...) keeps using the per-bucket loop."""
        agg_repo = _make_aggregate_repo([])
        agg_repo.list = AsyncMock(return_value={"total": 7})
        source_repo = _make_aggregate_repo([])
        source_repo.list = AsyncMock(return_value={"items": [], "total": 0})
        await _compute_bucketed_aggregates(
            {"count": "count(Manuscript where assessment_objective = current_bucket)"},
            {"MarkingResult": source_repo, "Manuscript": agg_repo},
            "assessment_objective",
            items=[],
            source_entity="MarkingResult",
        )
        # The aggregate target is Manuscript, not MarkingResult → fast path skipped.
        agg_repo.aggregate.assert_not_called()


# ---------------------------------------------------------------------------
# Cycle 25: pivot_table multi-dim aggregate
# ---------------------------------------------------------------------------


class TestPivotBuckets:
    """_compute_pivot_buckets routes count(<source>) with a list of dims
    through Repository.aggregate as a single multi-dim GROUP BY query."""

    @pytest.mark.asyncio()
    async def test_two_dim_pivot_returns_rows(self) -> None:
        from dazzle_back.runtime.aggregate import AggregateBucket
        from dazzle_back.runtime.workspace_rendering import _compute_pivot_buckets

        # Source repo with one FK field (system → System) + one scalar (severity).
        source_repo = MagicMock()
        source_repo.entity_spec = SimpleNamespace(
            name="Alert",
            fields=[
                SimpleNamespace(
                    name="system",
                    type=SimpleNamespace(kind="ref", ref_entity="System"),
                ),
                SimpleNamespace(name="severity", type=SimpleNamespace(kind="scalar")),
            ],
        )
        source_repo.aggregate = AsyncMock(
            return_value=[
                AggregateBucket(
                    dimensions={"system": "sys-1", "system_label": "DB", "severity": "high"},
                    measures={"count": 7},
                ),
                AggregateBucket(
                    dimensions={"system": "sys-1", "system_label": "DB", "severity": "low"},
                    measures={"count": 3},
                ),
            ]
        )

        # Target repo for the FK display-field probe.
        target_repo = MagicMock()
        target_repo.entity_spec = SimpleNamespace(
            name="System",
            fields=[
                SimpleNamespace(name="id"),
                SimpleNamespace(name="name"),
            ],
        )

        rows, dim_specs = await _compute_pivot_buckets(
            {"count": "count(Alert)"},
            {"Alert": source_repo, "System": target_repo},
            ["system", "severity"],
            source_entity="Alert",
            source_entity_spec=source_repo.entity_spec,
            scope_filters=None,
        )
        assert len(rows) == 2
        assert rows[0]["system"] == "sys-1"
        assert rows[0]["system_label"] == "DB"
        assert rows[0]["severity"] == "high"
        assert rows[0]["count"] == 7

        # dim_specs carry header metadata for the template.
        assert [d["name"] for d in dim_specs] == ["system", "severity"]
        assert dim_specs[0]["is_fk"] is True
        assert dim_specs[1]["is_fk"] is False

        # The aggregate call must use a list of two Dimension objects with
        # the FK target wired on the first.
        agg_kwargs = source_repo.aggregate.call_args.kwargs
        dims = agg_kwargs["dimensions"]
        assert len(dims) == 2
        assert dims[0].name == "system"
        assert dims[0].fk_table == "System"
        assert dims[0].fk_display_field == "name"
        assert dims[1].name == "severity"
        assert dims[1].fk_table is None

    @pytest.mark.asyncio()
    async def test_no_aggregates_returns_empty(self) -> None:
        from dazzle_back.runtime.workspace_rendering import _compute_pivot_buckets

        rows, specs = await _compute_pivot_buckets(
            {},
            {},
            ["system", "severity"],
            source_entity="Alert",
            source_entity_spec=None,
            scope_filters=None,
        )
        assert rows == []
        assert specs == []

    @pytest.mark.asyncio()
    async def test_cross_entity_count_skips_pivot_path(self) -> None:
        """count(OtherEntity ...) is not a same-entity GROUP BY — skip cleanly."""
        from dazzle_back.runtime.workspace_rendering import _compute_pivot_buckets

        source_repo = MagicMock()
        source_repo.entity_spec = SimpleNamespace(name="Alert", fields=[])
        source_repo.aggregate = AsyncMock()
        rows, specs = await _compute_pivot_buckets(
            {"count": "count(Manuscript)"},
            {"Alert": source_repo},
            ["system", "severity"],
            source_entity="Alert",
            source_entity_spec=source_repo.entity_spec,
            scope_filters=None,
        )
        assert rows == []
        # Aggregate not called — different entity short-circuits.
        source_repo.aggregate.assert_not_called()

    @pytest.mark.asyncio()
    async def test_aggregate_failure_returns_empty_with_dim_specs(self) -> None:
        """Errors during the aggregate call don't crash the region — empty rows + specs preserved."""
        from dazzle_back.runtime.workspace_rendering import _compute_pivot_buckets

        source_repo = MagicMock()
        source_repo.entity_spec = SimpleNamespace(
            name="Alert",
            fields=[SimpleNamespace(name="severity", type=SimpleNamespace(kind="scalar"))],
        )
        source_repo.aggregate = AsyncMock(side_effect=RuntimeError("DB down"))
        rows, specs = await _compute_pivot_buckets(
            {"count": "count(Alert)"},
            {"Alert": source_repo},
            ["severity"],
            source_entity="Alert",
            source_entity_spec=source_repo.entity_spec,
            scope_filters=None,
        )
        assert rows == []
        # dim_specs still produced — header rendering survives the failure.
        assert len(specs) == 1
        assert specs[0]["name"] == "severity"


# ---------------------------------------------------------------------------
# Cycle 28: time-bucketing via BucketRef
# ---------------------------------------------------------------------------


class TestTimeBucketedAggregates:
    """BucketRef(field, unit) threads through _aggregate_via_groupby and
    _compute_pivot_buckets, producing ISO bucket ids + formatted labels."""

    @pytest.mark.asyncio()
    async def test_single_dim_time_bucket_formats_labels(self) -> None:
        import datetime as dt

        from dazzle.core.ir import BucketRef
        from dazzle_back.runtime.aggregate import AggregateBucket
        from dazzle_back.runtime.workspace_rendering import _aggregate_via_groupby

        agg_repo = MagicMock()
        agg_repo.aggregate = AsyncMock(
            return_value=[
                AggregateBucket(
                    dimensions={"created_at": dt.datetime(2026, 4, 21, 0, 0)},
                    measures={"count": 3},
                ),
                AggregateBucket(
                    dimensions={"created_at": dt.datetime(2026, 4, 22, 0, 0)},
                    measures={"count": 7},
                ),
            ]
        )

        rows = await _aggregate_via_groupby(
            agg_repo,
            metric_name="count",
            group_by=BucketRef(field="created_at", unit="day"),
            where_clause=None,
            scope_filters=None,
            source_entity_spec=None,
            fk_target_spec=None,
        )
        assert rows == [
            {"label": "2026-04-21", "value": 3, "bucket": "2026-04-21T00:00:00"},
            {"label": "2026-04-22", "value": 7, "bucket": "2026-04-22T00:00:00"},
        ]

        # Aggregate call used a single time-bucket Dimension.
        dims = agg_repo.aggregate.call_args.kwargs["dimensions"]
        assert len(dims) == 1
        assert dims[0].truncate == "day"
        assert dims[0].is_time_bucket is True

    @pytest.mark.asyncio()
    async def test_pivot_multi_dim_with_time_bucket(self) -> None:
        """group_by: [bucket(created_at, week), severity] produces rows with
        both the ISO week id and a human-readable week label."""
        import datetime as dt

        from dazzle.core.ir import BucketRef
        from dazzle_back.runtime.aggregate import AggregateBucket
        from dazzle_back.runtime.workspace_rendering import _compute_pivot_buckets

        source_repo = MagicMock()
        source_repo.entity_spec = SimpleNamespace(
            name="Alert",
            fields=[
                SimpleNamespace(name="created_at", type=SimpleNamespace(kind="scalar")),
                SimpleNamespace(name="severity", type=SimpleNamespace(kind="scalar")),
            ],
        )
        source_repo.aggregate = AsyncMock(
            return_value=[
                AggregateBucket(
                    dimensions={"created_at": dt.datetime(2026, 4, 20), "severity": "high"},
                    measures={"count": 9},
                ),
            ]
        )

        rows, specs = await _compute_pivot_buckets(
            {"count": "count(Alert)"},
            {"Alert": source_repo},
            [BucketRef(field="created_at", unit="week"), "severity"],
            source_entity="Alert",
            source_entity_spec=source_repo.entity_spec,
            scope_filters=None,
        )

        assert len(rows) == 1
        # Time-bucketed dim: raw id is ISO string, companion _label is formatted.
        assert rows[0]["created_at"] == "2026-04-20T00:00:00"
        assert rows[0]["created_at_label"] == "2026-W17"
        assert rows[0]["severity"] == "high"
        assert rows[0]["count"] == 9

        # Specs carry is_time_bucket marker for template routing.
        assert specs[0]["is_time_bucket"] is True
        assert specs[0]["unit"] == "week"
        assert specs[1]["is_time_bucket"] is False

    @pytest.mark.asyncio()
    async def test_pivot_aggregate_error_logged_at_error_level(self, caplog) -> None:
        """Regression guard for #854 — a pivot aggregate failure used to log
        at WARNING level, making the root cause invisible in production. It
        now logs at ERROR with the dim + filter detail needed to reproduce."""
        import logging

        from dazzle_back.runtime.workspace_rendering import _compute_pivot_buckets

        source_repo = MagicMock()
        source_repo.entity_spec = SimpleNamespace(
            name="MarkingResult",
            fields=[SimpleNamespace(name="score", type=SimpleNamespace(kind="scalar"))],
        )
        source_repo.aggregate = AsyncMock(side_effect=RuntimeError("column does not exist"))

        with caplog.at_level(logging.ERROR, logger="dazzle_back.runtime.workspace_rendering"):
            rows, specs = await _compute_pivot_buckets(
                {"count": "count(MarkingResult)"},
                {"MarkingResult": source_repo},
                ["score", "status"],
                source_entity="MarkingResult",
                source_entity_spec=source_repo.entity_spec,
                scope_filters={"__scope_predicate": ('"MarkingResult"."dept" = %s', ["d1"])},
            )

        assert rows == []
        assert any(r.levelno == logging.ERROR and "FAILED" in r.message for r in caplog.records)
        # The reproduction info must be in the log record — dimensions + filters.
        msg = next(r.message for r in caplog.records if r.levelno == logging.ERROR)
        assert "MarkingResult" in msg
        assert "score" in msg
        assert "__scope_predicate" in msg

    def test_format_bucket_label_every_unit(self) -> None:
        import datetime as dt

        from dazzle_back.runtime.workspace_rendering import _format_bucket_label

        d = dt.datetime(2026, 5, 18, 14, 30)  # Monday, week 21
        assert _format_bucket_label(d, "day") == "2026-05-18"
        assert _format_bucket_label(d, "week") == "2026-W21"
        assert _format_bucket_label(d, "month") == "May 2026"
        assert _format_bucket_label(d, "quarter") == "Q2 2026"
        assert _format_bucket_label(d, "year") == "2026"
        assert _format_bucket_label(None, "day") == ""
        # Non-datetime fallback.
        assert _format_bucket_label("not-a-date", "day") == "not-a-date"
