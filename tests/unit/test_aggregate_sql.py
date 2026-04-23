"""
Unit tests for the aggregate SQL builder (Strategy C, multi-dim v2).

Covers ``build_aggregate_sql`` + ``measure_to_sql`` + ``rows_to_buckets``
+ ``resolve_fk_display_field`` + the ``Dimension`` dataclass. These are
the pieces ``Repository.aggregate`` composes — each tested in isolation
so a broken SQL composition or a wrong FK display probe surfaces with a
narrow failure.

Cycle 25: extended to multi-dimension ``GROUP BY`` for cross-tab /
pivot rendering. Single-dim coverage retained as the most common case;
multi-dim coverage exercises FK + scalar combos and indexed alias
correctness.

DB-level integration coverage (real round-trip through a Postgres or
SQLite engine) lives in ``tests/integration/test_repo_aggregate.py``.
"""

from __future__ import annotations

from types import SimpleNamespace

from dazzle_back.runtime.aggregate import (
    AggregateBucket,
    Dimension,
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
# Dimension dataclass
# ---------------------------------------------------------------------------


class TestDimension:
    def test_scalar_dimension_has_no_fk_join(self) -> None:
        dim = Dimension(name="status")
        assert dim.has_fk_join is False
        assert dim.fk_table is None
        assert dim.fk_display_field is None

    def test_fk_dimension_has_join_when_both_set(self) -> None:
        dim = Dimension(name="assessment_objective", fk_table="AO", fk_display_field="label")
        assert dim.has_fk_join is True

    def test_partial_fk_spec_does_not_join(self) -> None:
        """Either both fk_table + fk_display_field, or neither."""
        assert Dimension(name="x", fk_table="X", fk_display_field=None).has_fk_join is False
        assert Dimension(name="x", fk_table=None, fk_display_field="label").has_fk_join is False

    def test_dimension_is_frozen(self) -> None:
        """Frozen so caller can hash / cache safely."""
        import dataclasses

        dim = Dimension(name="status")
        try:
            dim.name = "other"  # type: ignore[misc]
        except dataclasses.FrozenInstanceError:
            return
        raise AssertionError("Dimension should be frozen")


# ---------------------------------------------------------------------------
# build_aggregate_sql — single dimension
# ---------------------------------------------------------------------------


class TestBuildAggregateSQLSingleDim:
    def test_scalar_group_by_no_join(self) -> None:
        sql, params = build_aggregate_sql(
            table_name="Manuscript",
            placeholder_style="%s",
            dimensions=[Dimension(name="status")],
            measures={"count": "count"},
            filters=None,
        )
        assert sql.startswith('SELECT "Manuscript"."status" AS "dim_0_id"')
        assert "LEFT JOIN" not in sql
        assert 'GROUP BY "Manuscript"."status"' in sql
        assert 'ORDER BY "Manuscript"."status" NULLS LAST' in sql
        assert "LIMIT 200" in sql
        assert params == []

    def test_fk_group_by_joins_target(self) -> None:
        sql, params = build_aggregate_sql(
            table_name="MarkingResult",
            placeholder_style="%s",
            dimensions=[
                Dimension(
                    name="assessment_objective",
                    fk_table="AssessmentObjective",
                    fk_display_field="label",
                )
            ],
            measures={"count": "count"},
            filters=None,
        )
        assert (
            'LEFT JOIN "AssessmentObjective" fk_0 '
            'ON "MarkingResult"."assessment_objective" = fk_0."id"' in sql
        )
        assert 'fk_0."label" AS "dim_0_label"' in sql
        assert 'GROUP BY "MarkingResult"."assessment_objective", fk_0."label"' in sql
        assert 'ORDER BY fk_0."label" NULLS LAST' in sql

    def test_filters_threaded_through_query_builder(self) -> None:
        sql, params = build_aggregate_sql(
            table_name="Manuscript",
            placeholder_style="%s",
            dimensions=[Dimension(name="status")],
            measures={"count": "count"},
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
            dimensions=[Dimension(name="status")],
            measures={"count": "count"},
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
            dimensions=[Dimension(name="status")],
            measures={"count": "count", "avg_score": "avg:score"},
            filters=None,
        )
        assert 'COUNT(*) AS "count"' in sql
        assert 'AVG("score") AS "avg_score"' in sql

    def test_no_supported_measures_returns_empty(self) -> None:
        sql, params = build_aggregate_sql(
            table_name="Manuscript",
            placeholder_style="%s",
            dimensions=[Dimension(name="status")],
            measures={"weird": "median:score"},
            filters=None,
        )
        assert sql == ""
        assert params == []

    def test_no_dimensions_returns_empty(self) -> None:
        sql, params = build_aggregate_sql(
            table_name="Manuscript",
            placeholder_style="%s",
            dimensions=[],
            measures={"count": "count"},
            filters=None,
        )
        assert sql == ""
        assert params == []

    def test_limit_is_clamped_via_int_coercion(self) -> None:
        """limit is `int`-coerced — string values won't escape the SQL."""
        sql, _ = build_aggregate_sql(
            table_name="Manuscript",
            placeholder_style="%s",
            dimensions=[Dimension(name="status")],
            measures={"count": "count"},
            filters=None,
            limit=50,
        )
        assert "LIMIT 50" in sql


# ---------------------------------------------------------------------------
# build_aggregate_sql — multi-dimension (cycle 25)
# ---------------------------------------------------------------------------


class TestBuildAggregateSQLMultiDim:
    def test_two_scalar_dimensions(self) -> None:
        sql, _ = build_aggregate_sql(
            table_name="Alert",
            placeholder_style="%s",
            dimensions=[Dimension(name="severity"), Dimension(name="acknowledged")],
            measures={"count": "count"},
            filters=None,
        )
        assert '"Alert"."severity" AS "dim_0_id"' in sql
        assert '"Alert"."acknowledged" AS "dim_1_id"' in sql
        assert "LEFT JOIN" not in sql
        assert 'GROUP BY "Alert"."severity", "Alert"."acknowledged"' in sql
        # ORDER BY mirrors declaration order
        assert 'ORDER BY "Alert"."severity" NULLS LAST, "Alert"."acknowledged" NULLS LAST' in sql

    def test_fk_then_scalar(self) -> None:
        sql, _ = build_aggregate_sql(
            table_name="Alert",
            placeholder_style="%s",
            dimensions=[
                Dimension(name="system", fk_table="System", fk_display_field="name"),
                Dimension(name="severity"),
            ],
            measures={"count": "count"},
            filters=None,
        )
        assert '"Alert"."system" AS "dim_0_id"' in sql
        assert 'fk_0."name" AS "dim_0_label"' in sql
        assert '"Alert"."severity" AS "dim_1_id"' in sql
        # Indexed alias on the fk join
        assert 'LEFT JOIN "System" fk_0 ON "Alert"."system" = fk_0."id"' in sql
        # Group by all four (scalar dim + fk id + fk display + scalar dim)
        assert 'GROUP BY "Alert"."system", fk_0."name", "Alert"."severity"' in sql
        # Order by FK label first (since dim_0 is FK), then scalar
        assert 'ORDER BY fk_0."name" NULLS LAST, "Alert"."severity" NULLS LAST' in sql

    def test_two_fks_get_distinct_aliases(self) -> None:
        """Two FK dims to different tables must alias separately (fk_0, fk_1)."""
        sql, _ = build_aggregate_sql(
            table_name="MarkingResult",
            placeholder_style="%s",
            dimensions=[
                Dimension(
                    name="assessment_objective",
                    fk_table="AssessmentObjective",
                    fk_display_field="label",
                ),
                Dimension(name="manuscript", fk_table="Manuscript", fk_display_field="title"),
            ],
            measures={"count": "count"},
            filters=None,
        )
        assert 'LEFT JOIN "AssessmentObjective" fk_0' in sql
        assert 'LEFT JOIN "Manuscript" fk_1' in sql
        assert 'fk_0."label"' in sql
        assert 'fk_1."title"' in sql

    def test_two_fks_to_same_table_get_distinct_aliases(self) -> None:
        """Self-FK case (e.g. parent + child both ref User) must not alias-collide."""
        sql, _ = build_aggregate_sql(
            table_name="Comment",
            placeholder_style="%s",
            dimensions=[
                Dimension(name="author", fk_table="User", fk_display_field="name"),
                Dimension(name="reviewer", fk_table="User", fk_display_field="name"),
            ],
            measures={"count": "count"},
            filters=None,
        )
        assert 'LEFT JOIN "User" fk_0 ON "Comment"."author" = fk_0."id"' in sql
        assert 'LEFT JOIN "User" fk_1 ON "Comment"."reviewer" = fk_1."id"' in sql
        # Two separate references to User.name with different aliases
        assert 'fk_0."name" AS "dim_0_label"' in sql
        assert 'fk_1."name" AS "dim_1_label"' in sql


# ---------------------------------------------------------------------------
# rows_to_buckets
# ---------------------------------------------------------------------------


class TestRowsToBuckets:
    def test_scalar_single_dim(self) -> None:
        rows = [
            {"dim_0_id": "draft", "count": 5},
            {"dim_0_id": "published", "count": 12},
        ]
        buckets = rows_to_buckets(
            rows,
            dimensions=[Dimension(name="status")],
            measures={"count": "count"},
        )
        assert len(buckets) == 2
        assert buckets[0].dimensions == {"status": "draft"}
        assert buckets[0].measures == {"count": 5}

    def test_fk_single_dim_carries_label(self) -> None:
        rows = [
            {"dim_0_id": "ao-1", "dim_0_label": "Knowledge", "count": 30},
            {"dim_0_id": "ao-2", "dim_0_label": "Application", "count": 22},
        ]
        buckets = rows_to_buckets(
            rows,
            dimensions=[
                Dimension(name="assessment_objective", fk_table="AO", fk_display_field="label")
            ],
            measures={"count": "count"},
        )
        assert buckets[0].dimensions == {
            "assessment_objective": "ao-1",
            "assessment_objective_label": "Knowledge",
        }
        assert buckets[1].dimensions["assessment_objective_label"] == "Application"

    def test_fk_label_falls_back_to_id_when_null(self) -> None:
        """Orphan FK rows (target deleted) shouldn't render as null bars."""
        rows = [{"dim_0_id": "orphan", "dim_0_label": None, "count": 3}]
        buckets = rows_to_buckets(
            rows,
            dimensions=[
                Dimension(name="criterion", fk_table="Criterion", fk_display_field="label")
            ],
            measures={"count": "count"},
        )
        assert buckets[0].dimensions["criterion_label"] == "orphan"

    def test_multi_dim_scalar_plus_fk(self) -> None:
        rows = [
            {
                "dim_0_id": "sys-1",
                "dim_0_label": "Database",
                "dim_1_id": "high",
                "count": 7,
            },
            {
                "dim_0_id": "sys-1",
                "dim_0_label": "Database",
                "dim_1_id": "low",
                "count": 3,
            },
        ]
        buckets = rows_to_buckets(
            rows,
            dimensions=[
                Dimension(name="system", fk_table="System", fk_display_field="name"),
                Dimension(name="severity"),
            ],
            measures={"count": "count"},
        )
        assert len(buckets) == 2
        assert buckets[0].dimensions == {
            "system": "sys-1",
            "system_label": "Database",
            "severity": "high",
        }
        assert buckets[1].dimensions["severity"] == "low"

    def test_unsupported_measures_skipped_in_output(self) -> None:
        rows = [{"dim_0_id": "a", "count": 7}]
        buckets = rows_to_buckets(
            rows,
            dimensions=[Dimension(name="status")],
            measures={"count": "count", "weird": "median:x"},
        )
        # Only `count` survives — `weird` was unsupported by measure_to_sql.
        assert "weird" not in buckets[0].measures
        assert buckets[0].measures == {"count": 7}

    def test_empty_rows_returns_empty_list(self) -> None:
        assert (
            rows_to_buckets(
                [],
                dimensions=[Dimension(name="x")],
                measures={"c": "count"},
            )
            == []
        )

    def test_tuple_rows_use_positional_keys(self) -> None:
        """Repos that return raw tuples (not dict-row) still work."""
        # Order matches build_aggregate_sql SELECT: dim_0_id, dim_0_label,
        # dim_1_id, count
        rows = [("sys-1", "Database", "high", 7)]
        buckets = rows_to_buckets(
            rows,
            dimensions=[
                Dimension(name="system", fk_table="System", fk_display_field="name"),
                Dimension(name="severity"),
            ],
            measures={"count": "count"},
        )
        assert buckets[0].dimensions == {
            "system": "sys-1",
            "system_label": "Database",
            "severity": "high",
        }
        assert buckets[0].measures == {"count": 7}


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
