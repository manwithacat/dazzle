"""Tests for the reporting predicate algebra parser (#888 Phase 1).

Verifies the parser at ``src/dazzle_back/runtime/aggregate_where_parser.py``
correctly translates aggregate where-clause text into ``ScopePredicate``
trees that the existing ``compile_predicate`` then emits as parameterised
SQL — closing the three #888 gaps:

1. Column-vs-column comparisons
2. OR clauses
3. Range (handled at the algebra level via AND of two ColumnChecks)

Plus the integration: malformed input produces an explicit error path
(caller emits a sentinel always-false filter so the metric resolves to
0 instead of running unfiltered).

Architecture: see ``dev_docs/2026-04-27-reporting-predicate-algebra.md``.
"""

from __future__ import annotations

import pytest

from dazzle.core.ir.fk_graph import FKGraph
from dazzle.core.ir.predicates import (
    BoolComposite,
    BoolOp,
    ColumnCheck,
    ColumnRefCheck,
    CompOp,
    Tautology,
    ValueRef,
)
from dazzle_back.runtime.aggregate_where_parser import parse_aggregate_where
from dazzle_back.runtime.predicate_compiler import compile_predicate


def _compile(pred):  # type: ignore[no-untyped-def]
    """Convenience: compile a predicate against an empty FK graph."""
    return compile_predicate(pred, "X", FKGraph())


# ───────────────────────── algebra emission ─────────────────────────


class TestParseToAlgebra:
    """The parser must emit the right node types — verifying via the
    structured tree, not just the SQL output, so future compiler bugs
    can't mask parser bugs."""

    def test_empty_returns_tautology(self) -> None:
        assert isinstance(parse_aggregate_where(""), Tautology)
        assert isinstance(parse_aggregate_where("   "), Tautology)

    def test_column_vs_column_emits_column_ref_check(self) -> None:
        pred = parse_aggregate_where(
            "latest_grade >= target_grade",
            known_columns={"latest_grade", "target_grade"},
        )
        assert isinstance(pred, ColumnRefCheck)
        assert pred.field == "latest_grade"
        assert pred.op is CompOp.GTE
        assert pred.other_field == "target_grade"

    def test_unknown_rhs_identifier_treated_as_string_literal(self) -> None:
        """When RHS isn't a known column, fall through to ColumnCheck
        with a string literal (legacy `_parse_simple_where` behaviour)."""
        pred = parse_aggregate_where("status = open", known_columns={"status"})
        assert isinstance(pred, ColumnCheck)
        assert pred.value == ValueRef(literal="open")

    def test_quoted_string_literal(self) -> None:
        pred = parse_aggregate_where('status = "open"', known_columns={"status"})
        assert isinstance(pred, ColumnCheck)
        assert pred.value == ValueRef(literal="open")

    def test_quoted_string_with_escaped_quote(self) -> None:
        pred = parse_aggregate_where(r'name = "O\"Brien"', known_columns={"name"})
        assert isinstance(pred, ColumnCheck)
        assert pred.value.literal == 'O"Brien'

    def test_int_literal(self) -> None:
        pred = parse_aggregate_where("score = 42", known_columns={"score"})
        assert isinstance(pred, ColumnCheck)
        assert pred.value == ValueRef(literal=42)
        assert isinstance(pred.value.literal, int)

    def test_float_literal(self) -> None:
        pred = parse_aggregate_where("confidence < 0.7", known_columns={"confidence"})
        assert isinstance(pred, ColumnCheck)
        assert pred.value.literal == 0.7
        assert isinstance(pred.value.literal, float)

    def test_negative_number(self) -> None:
        pred = parse_aggregate_where("delta >= -10", known_columns={"delta"})
        assert isinstance(pred, ColumnCheck)
        assert pred.value.literal == -10

    def test_true_false_null(self) -> None:
        ptrue = parse_aggregate_where("flagged = true", known_columns={"flagged"})
        pfalse = parse_aggregate_where("flagged = false", known_columns={"flagged"})
        pnull = parse_aggregate_where("deleted_at = null", known_columns={"deleted_at"})
        assert isinstance(ptrue, ColumnCheck) and ptrue.value.literal is True
        assert isinstance(pfalse, ColumnCheck) and pfalse.value.literal is False
        assert isinstance(pnull, ColumnCheck) and pnull.value.literal_null is True

    def test_and_combination(self) -> None:
        pred = parse_aggregate_where("a = 1 and b = 2", known_columns={"a", "b"})
        assert isinstance(pred, BoolComposite)
        assert pred.op is BoolOp.AND
        assert len(pred.children) == 2

    def test_or_combination(self) -> None:
        pred = parse_aggregate_where("a = 1 or b = 2", known_columns={"a", "b"})
        assert isinstance(pred, BoolComposite)
        assert pred.op is BoolOp.OR
        assert len(pred.children) == 2

    def test_precedence_or_lower_than_and(self) -> None:
        """`a = 1 and b = 2 or c = 3` parses as `(a=1 AND b=2) OR c=3`."""
        pred = parse_aggregate_where("a = 1 and b = 2 or c = 3", known_columns={"a", "b", "c"})
        assert isinstance(pred, BoolComposite)
        assert pred.op is BoolOp.OR
        # First child is the AND group, second is the c=3 ColumnCheck
        assert isinstance(pred.children[0], BoolComposite)
        assert pred.children[0].op is BoolOp.AND
        assert isinstance(pred.children[1], ColumnCheck)
        assert pred.children[1].field == "c"

    def test_parens_override_precedence(self) -> None:
        """`(a = 1 or b = 2) and c = 3` parses as expected."""
        pred = parse_aggregate_where("(a = 1 or b = 2) and c = 3", known_columns={"a", "b", "c"})
        assert isinstance(pred, BoolComposite)
        assert pred.op is BoolOp.AND
        # First child is the OR group, second is c=3
        assert isinstance(pred.children[0], BoolComposite)
        assert pred.children[0].op is BoolOp.OR

    def test_not_operator(self) -> None:
        pred = parse_aggregate_where("not flagged = true", known_columns={"flagged"})
        assert isinstance(pred, BoolComposite)
        assert pred.op is BoolOp.NOT

    # ─── Malformed input ───

    def test_empty_lhs_raises(self) -> None:
        with pytest.raises(ValueError):
            parse_aggregate_where("= 5")

    def test_unbalanced_parens_raises(self) -> None:
        with pytest.raises(ValueError):
            parse_aggregate_where("(a = 1")

    def test_garbage_rhs_raises(self) -> None:
        with pytest.raises(ValueError):
            parse_aggregate_where("a = ()")

    def test_unknown_operator_raises(self) -> None:
        with pytest.raises(ValueError):
            parse_aggregate_where("a ~~ 5")


# ───────────────────────── SQL emission round-trip ─────────────────────────


class TestSqlRoundTrip:
    """End-to-end: parser → compiler → expected SQL fragment + params.
    Pin each #888 sub-feature against its canonical repro."""

    def test_888_repro_column_vs_column(self) -> None:
        """The exact repro from #888: count(StudentProfile where
        latest_grade >= target_grade) — pre-fix produced literal string
        comparison, always-false."""
        pred = parse_aggregate_where(
            "latest_grade >= target_grade",
            known_columns={"latest_grade", "target_grade"},
        )
        sql, params = _compile(pred)
        assert sql == '"latest_grade" >= "target_grade"'
        assert params == []  # both sides are columns — no bound params

    def test_888_repro_or_clause(self) -> None:
        """`flagged = true or confidence < 0.7` — pre-fix the OR was
        silently dropped by `_parse_simple_where`."""
        pred = parse_aggregate_where(
            "flagged = true or confidence < 0.7",
            known_columns={"flagged", "confidence"},
        )
        sql, params = _compile(pred)
        assert sql == '("flagged" = %s) OR ("confidence" < %s)'
        assert params == [True, 0.7]

    def test_888_repro_range(self) -> None:
        """`confidence >= 0.85 and confidence < 0.95` — pre-fix worked
        as two AND clauses but values were strings; algebra path keeps
        them numeric."""
        pred = parse_aggregate_where(
            "confidence >= 0.85 and confidence < 0.95",
            known_columns={"confidence"},
        )
        sql, params = _compile(pred)
        assert sql == '("confidence" >= %s) AND ("confidence" < %s)'
        assert params == [0.85, 0.95]
        assert all(isinstance(p, float) for p in params)

    def test_legacy_count_form_unchanged(self) -> None:
        """The pre-existing `count(X where status = "open")` shape must
        still produce a parameterised single-column comparison."""
        pred = parse_aggregate_where('status = "open"', known_columns={"status"})
        sql, params = _compile(pred)
        assert sql == '"status" = %s'
        assert params == ["open"]


# ───────────────────────── _build_aggregate_filters integration ─────────────


class TestBuildAggregateFilters:
    """The runtime helper that wraps the parser + compiler and merges
    with RBAC scope filters at the QueryBuilder boundary."""

    def _make_repo(self, field_names: list[str]):  # type: ignore[no-untyped-def]
        from types import SimpleNamespace

        fields = [SimpleNamespace(name=n) for n in field_names]
        return SimpleNamespace(entity_spec=SimpleNamespace(fields=fields))

    def test_no_where_clause_returns_scope_only(self) -> None:
        from dazzle_back.runtime.workspace_rendering import _build_aggregate_filters

        repo = self._make_repo(["a", "b"])
        scope = {"tenant_id": "t-1"}
        out = _build_aggregate_filters(None, scope, repo, "X")
        assert out == {"tenant_id": "t-1"}

    def test_where_clause_populates_scope_predicate(self) -> None:
        from dazzle_back.runtime.workspace_rendering import _build_aggregate_filters

        repo = self._make_repo(["status"])
        out = _build_aggregate_filters('status = "open"', None, repo, "X")
        assert out is not None
        assert "__scope_predicate" in out
        sql, params = out["__scope_predicate"]
        assert sql == '"status" = %s'
        assert params == ["open"]

    def test_where_and_existing_scope_predicate_combine_with_and(self) -> None:
        """When scope_filters already carries a __scope_predicate (from
        the RBAC compiler), the aggregate where-predicate AND-combines
        with it — single SQL fragment, no QueryBuilder change required."""
        from dazzle_back.runtime.workspace_rendering import _build_aggregate_filters

        repo = self._make_repo(["status"])
        scope = {"__scope_predicate": ('"tenant_id" = %s', ["t-1"])}
        out = _build_aggregate_filters('status = "open"', scope, repo, "X")
        assert out is not None
        sql, params = out["__scope_predicate"]
        assert sql == '("tenant_id" = %s) AND ("status" = %s)'
        assert params == ["t-1", "open"]

    def test_column_vs_column_uses_known_columns(self) -> None:
        """When both RHS and LHS are in `entity_spec.fields`, the parser
        emits ColumnRefCheck and the SQL has no params for the comparison."""
        from dazzle_back.runtime.workspace_rendering import _build_aggregate_filters

        repo = self._make_repo(["latest_grade", "target_grade"])
        out = _build_aggregate_filters("latest_grade >= target_grade", None, repo, "StudentProfile")
        assert out is not None
        sql, params = out["__scope_predicate"]
        assert sql == '"latest_grade" >= "target_grade"'
        assert params == []

    def test_unparseable_clause_falls_back_to_legacy_parser(self) -> None:
        """Clauses the new algebra grammar can't tokenise (e.g. hyphenated
        UUIDs from `current_bucket` substitution like `target = t-1`)
        must fall through to the legacy `_parse_simple_where` so the
        existing bucketed-aggregate path keeps working unchanged."""
        from dazzle_back.runtime.workspace_rendering import _build_aggregate_filters

        repo = self._make_repo(["target"])
        out = _build_aggregate_filters("target = t-1", None, repo, "X")
        # Legacy parser maps `target = t-1` to `{"target": "t-1"}`
        # (string literal RHS). The new parser rejects this because
        # it tokenises `t-1` as IDENT-OP-NUMBER.
        assert out == {"target": "t-1"}
