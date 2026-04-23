"""
Unit tests for the aggregate SQL builder (Strategy C, #851 follow-up).

Covers ``build_aggregate_sql`` + ``measure_to_sql`` + ``rows_to_buckets``
and ``resolve_fk_display_field``. These are the pieces the future
``Repository.aggregate`` method composes — each tested in isolation so a
broken SQL composition or a wrong FK display probe surfaces with a
narrow failure.

DB-level integration coverage (real round-trip through a Postgres or
SQLite engine) lives in ``tests/integration/test_repo_aggregate.py``.
"""

from __future__ import annotations

from types import SimpleNamespace

from dazzle_back.runtime.aggregate import (
    AggregateBucket,
    build_aggregate_sql,
    measure_to_sql,
    resolve_fk_display_field,
    rows_to_buckets,
)

# ---------------------------------------------------------------------------
# measure_to_sql
# ---------------------------------------------------------------------------


class TestMeasureToSQL:
    def test_count_is_count_star(self) -> None:
        assert measure_to_sql("count") == "COUNT(*)"

    def test_unary_measures_quote_column(self) -> None:
        assert measure_to_sql("sum:score") == 'SUM("score")'
        assert measure_to_sql("avg:score") == 'AVG("score")'
        assert measure_to_sql("min:score") == 'MIN("score")'
        assert measure_to_sql("max:score") == 'MAX("score")'

    def test_unsupported_returns_none(self) -> None:
        assert measure_to_sql("median:score") is None
        assert measure_to_sql("count:score") is None  # `count` doesn't take arg
        assert measure_to_sql("sum:") is None  # missing column
        assert measure_to_sql("") is None

    def test_column_name_is_quoted_against_injection(self) -> None:
        # quote_identifier doubles up embedded quotes — `score"; DROP` becomes
        # `"score""; DROP"` which is a valid (if useless) identifier.
        assert measure_to_sql('sum:score"; DROP TABLE x; --') == (
            'SUM("score""; DROP TABLE x; --")'
        )


# ---------------------------------------------------------------------------
# resolve_fk_display_field
# ---------------------------------------------------------------------------


def _entity_with_fields(*field_names: str) -> SimpleNamespace:
    return SimpleNamespace(fields=[SimpleNamespace(name=n) for n in field_names])


class TestResolveFKDisplayField:
    def test_probe_order_display_name_wins(self) -> None:
        e = _entity_with_fields("id", "display_name", "name", "code")
        assert resolve_fk_display_field(e) == "display_name"

    def test_falls_back_to_name(self) -> None:
        e = _entity_with_fields("id", "name", "title")
        assert resolve_fk_display_field(e) == "name"

    def test_falls_back_to_code(self) -> None:
        e = _entity_with_fields("id", "code")
        assert resolve_fk_display_field(e) == "code"

    def test_returns_none_when_no_probe_matches(self) -> None:
        e = _entity_with_fields("id", "email", "ssn")
        assert resolve_fk_display_field(e) is None

    def test_none_entity_returns_none(self) -> None:
        assert resolve_fk_display_field(None) is None


# ---------------------------------------------------------------------------
# build_aggregate_sql
# ---------------------------------------------------------------------------


class TestBuildAggregateSQL:
    def test_scalar_group_by_no_join(self) -> None:
        sql, params = build_aggregate_sql(
            table_name="Manuscript",
            placeholder_style="%s",
            group_by="status",
            measures={"count": "count"},
            fk_table=None,
            fk_display_field=None,
            filters=None,
        )
        assert sql.startswith('SELECT "Manuscript"."status" AS bucket_id, COUNT(*)')
        assert "LEFT JOIN" not in sql
        assert 'GROUP BY "Manuscript"."status"' in sql
        assert 'ORDER BY "Manuscript"."status" NULLS LAST' in sql
        assert "LIMIT 200" in sql
        assert params == []

    def test_fk_group_by_joins_target(self) -> None:
        sql, params = build_aggregate_sql(
            table_name="MarkingResult",
            placeholder_style="%s",
            group_by="assessment_objective",
            measures={"count": "count"},
            fk_table="AssessmentObjective",
            fk_display_field="label",
            filters=None,
        )
        assert (
            'LEFT JOIN "AssessmentObjective" fk '
            'ON "MarkingResult"."assessment_objective" = fk."id"' in sql
        )
        assert 'fk."label" AS bucket_label' in sql
        # Group by both source col + display so SELECT is well-formed in PG.
        assert 'GROUP BY "MarkingResult"."assessment_objective", fk."label"' in sql
        # Order by the human label for stable chart rendering.
        assert 'ORDER BY fk."label" NULLS LAST' in sql

    def test_filters_threaded_through_query_builder(self) -> None:
        sql, params = build_aggregate_sql(
            table_name="Manuscript",
            placeholder_style="%s",
            group_by="status",
            measures={"count": "count"},
            fk_table=None,
            fk_display_field=None,
            filters={"school_id": "abc-123"},
        )
        assert "WHERE" in sql
        assert "school_id" in sql
        assert "abc-123" in params

    def test_scope_predicate_passes_through(self) -> None:
        """__scope_predicate raw SQL must land in the WHERE clause as-is."""
        sql, params = build_aggregate_sql(
            table_name="Manuscript",
            placeholder_style="%s",
            group_by="status",
            measures={"count": "count"},
            fk_table=None,
            fk_display_field=None,
            filters={
                "__scope_predicate": (
                    '"Manuscript"."department" = %s',
                    ["d-1"],
                )
            },
        )
        assert '"Manuscript"."department" = %s' in sql
        assert params == ["d-1"]

    def test_multiple_measures(self) -> None:
        sql, _ = build_aggregate_sql(
            table_name="Manuscript",
            placeholder_style="%s",
            group_by="status",
            measures={"count": "count", "avg_score": "avg:score"},
            fk_table=None,
            fk_display_field=None,
            filters=None,
        )
        assert 'COUNT(*) AS "count"' in sql
        assert 'AVG("score") AS "avg_score"' in sql

    def test_no_supported_measures_returns_empty(self) -> None:
        sql, params = build_aggregate_sql(
            table_name="Manuscript",
            placeholder_style="%s",
            group_by="status",
            measures={"weird": "median:score"},
            fk_table=None,
            fk_display_field=None,
            filters=None,
        )
        assert sql == ""
        assert params == []

    def test_limit_is_clamped_via_int_coercion(self) -> None:
        """limit is `int`-coerced — string values won't escape the SQL."""
        sql, _ = build_aggregate_sql(
            table_name="Manuscript",
            placeholder_style="%s",
            group_by="status",
            measures={"count": "count"},
            fk_table=None,
            fk_display_field=None,
            filters=None,
            limit=50,
        )
        assert "LIMIT 50" in sql


# ---------------------------------------------------------------------------
# rows_to_buckets
# ---------------------------------------------------------------------------


class TestRowsToBuckets:
    def test_scalar_buckets_no_label(self) -> None:
        rows = [
            {"bucket_id": "draft", "count": 5},
            {"bucket_id": "published", "count": 12},
        ]
        buckets = rows_to_buckets(
            rows,
            group_by="status",
            measures={"count": "count"},
            has_fk_join=False,
        )
        assert len(buckets) == 2
        assert buckets[0].dimensions == {"status": "draft"}
        assert buckets[0].measures == {"count": 5}

    def test_fk_buckets_carry_label(self) -> None:
        rows = [
            {"bucket_id": "ao-1", "bucket_label": "Knowledge", "count": 30},
            {"bucket_id": "ao-2", "bucket_label": "Application", "count": 22},
        ]
        buckets = rows_to_buckets(
            rows,
            group_by="assessment_objective",
            measures={"count": "count"},
            has_fk_join=True,
        )
        assert buckets[0].dimensions == {
            "assessment_objective": "ao-1",
            "assessment_objective_label": "Knowledge",
        }
        assert buckets[1].dimensions["assessment_objective_label"] == "Application"

    def test_fk_label_falls_back_to_id_when_null(self) -> None:
        """Orphan FK rows (target deleted) shouldn't render as null bars."""
        rows = [{"bucket_id": "orphan", "bucket_label": None, "count": 3}]
        buckets = rows_to_buckets(
            rows,
            group_by="criterion",
            measures={"count": "count"},
            has_fk_join=True,
        )
        assert buckets[0].dimensions["criterion_label"] == "orphan"

    def test_unsupported_measures_skipped_in_output(self) -> None:
        rows = [{"bucket_id": "a", "count": 7}]
        buckets = rows_to_buckets(
            rows,
            group_by="status",
            measures={"count": "count", "weird": "median:x"},
            has_fk_join=False,
        )
        # Only `count` survives — `weird` was unsupported by measure_to_sql.
        assert "weird" not in buckets[0].measures
        assert buckets[0].measures == {"count": 7}

    def test_empty_rows_returns_empty_list(self) -> None:
        assert rows_to_buckets([], group_by="x", measures={"c": "count"}, has_fk_join=False) == []


# ---------------------------------------------------------------------------
# AggregateBucket dataclass
# ---------------------------------------------------------------------------


class TestAggregateBucket:
    def test_default_factories(self) -> None:
        b = AggregateBucket()
        assert b.dimensions == {}
        assert b.measures == {}

    def test_explicit_construction(self) -> None:
        b = AggregateBucket(
            dimensions={"status": "draft"},
            measures={"count": 5, "avg_score": 12.4},
        )
        assert b.dimensions["status"] == "draft"
        assert b.measures["avg_score"] == 12.4
