"""Tests for the policy-body (param-free) mode of the predicate compiler (Phase C).

Policy mode renders a ScopePredicate to a self-contained SQL WHERE fragment
with NO bind params — suitable for an RLS ``CREATE POLICY`` body. ``current_user.*``
references become ``current_setting('dazzle.user_<attr>', true)::<type>`` GUC reads,
literals are inlined via the SQL-standard escaping renderer, and casts are derived
from the column's IR field type.

The companion param-mode path (``compile_predicate`` → ``(sql, params)``) MUST stay
byte-for-byte unchanged — covered by ``test_predicate_compiler.py``.
"""

import pytest

from dazzle.core.ir.predicates import (
    BoolComposite,
    BoolOp,
    ColumnCheck,
    CompOp,
    Contradiction,
    PathCheck,
    Tautology,
    UserAttrCheck,
    ValueRef,
)

pytest.importorskip("fastapi")

from dazzle.back.runtime.predicate_compiler import (
    _inline_sql_literal,
    collect_user_attr_refs,
    compile_predicate_policy,
)
from dazzle.core.ir.fk_graph import FKEdge, FKGraph


def _simple_graph() -> FKGraph:
    """Graph: Feedback -manuscript_id-> Manuscript -assessment_event_id-> AssessmentEvent."""
    graph = FKGraph()
    graph._edges = {
        "Feedback": [FKEdge("Feedback", "manuscript_id", "Manuscript")],
        "Manuscript": [
            FKEdge("Manuscript", "assessment_event_id", "AssessmentEvent"),
        ],
        "AssessmentEvent": [FKEdge("AssessmentEvent", "school_id", "School")],
    }
    graph._fields = {
        "Feedback": {"id", "manuscript_id", "content", "status", "school_id"},
        "Manuscript": {"id", "assessment_event_id", "title"},
        "AssessmentEvent": {"id", "school_id", "name"},
        "School": {"id", "name"},
    }
    return graph


# A simple ``(entity, field) -> pgtype`` resolver for the test entities.
_TYPES: dict[tuple[str, str], str] = {
    ("Feedback", "status"): "text",
    ("Feedback", "school_id"): "uuid",
    ("Feedback", "manuscript_id"): "uuid",
    ("Feedback", "content"): "text",
    ("AssessmentEvent", "school_id"): "uuid",
}


def _types(entity: str, field: str) -> str:
    try:
        return _TYPES[(entity, field)]
    except KeyError:  # pragma: no cover - exercised by the unresolvable test
        raise ValueError(f"no pg type for {entity}.{field}")


# ---------------------------------------------------------------------------
# _inline_sql_literal
# ---------------------------------------------------------------------------


class TestInlineLiteral:
    def test_none(self) -> None:
        assert _inline_sql_literal(None) == "NULL"

    def test_bool(self) -> None:
        assert _inline_sql_literal(True) == "true"
        assert _inline_sql_literal(False) == "false"

    def test_int(self) -> None:
        assert _inline_sql_literal(42) == "42"

    def test_float(self) -> None:
        assert _inline_sql_literal(3.5) == "3.5"

    def test_str(self) -> None:
        assert _inline_sql_literal("archived") == "'archived'"

    def test_str_injection_escaped(self) -> None:
        # The single quote is doubled per SQL standard.
        assert _inline_sql_literal("a'b") == "'a''b'"

    def test_bool_is_not_int(self) -> None:
        # bool is a subclass of int — ensure it renders as a SQL boolean.
        assert _inline_sql_literal(True) == "true"


# ---------------------------------------------------------------------------
# Column / literal
# ---------------------------------------------------------------------------


class TestColumnLiteral:
    def test_column_eq_literal(self) -> None:
        p = ColumnCheck(field="status", op=CompOp.EQ, value=ValueRef(literal="archived"))
        sql = compile_predicate_policy(p, "Feedback", _simple_graph(), entity_types=_types)
        assert sql == '"Feedback"."status" = \'archived\''
        assert "%s" not in sql

    def test_literal_injection_inlined_safely(self) -> None:
        p = ColumnCheck(field="status", op=CompOp.EQ, value=ValueRef(literal="a'b"))
        sql = compile_predicate_policy(p, "Feedback", _simple_graph(), entity_types=_types)
        assert "'a''b'" in sql
        assert "%s" not in sql

    def test_null_check(self) -> None:
        p = ColumnCheck(field="status", op=CompOp.IS, value=ValueRef(literal_null=True))
        sql = compile_predicate_policy(p, "Feedback", _simple_graph(), entity_types=_types)
        assert sql == '"Feedback"."status" IS NULL'
        assert "%s" not in sql

    def test_null_check_not(self) -> None:
        p = ColumnCheck(field="status", op=CompOp.IS_NOT, value=ValueRef(literal_null=True))
        sql = compile_predicate_policy(p, "Feedback", _simple_graph(), entity_types=_types)
        assert sql == '"Feedback"."status" IS NOT NULL'


# ---------------------------------------------------------------------------
# UserAttr / CurrentUser GUC casts
# ---------------------------------------------------------------------------


class TestGucCasts:
    def test_user_attr_uuid_cast(self) -> None:
        # school_id (a uuid column) = current_user.school_id
        p = UserAttrCheck(field="school_id", op=CompOp.EQ, user_attr="school_id")
        sql = compile_predicate_policy(p, "Feedback", _simple_graph(), entity_types=_types)
        assert (
            sql == '"Feedback"."school_id" = current_setting(\'dazzle.user_school_id\', true)::uuid'
        )
        assert "%s" not in sql

    def test_current_user_uuid(self) -> None:
        # ColumnCheck with current_user → the user's own PK, cast ::uuid.
        p = ColumnCheck(field="school_id", op=CompOp.EQ, value=ValueRef(current_user=True))
        sql = compile_predicate_policy(p, "Feedback", _simple_graph(), entity_types=_types)
        assert sql == '"Feedback"."school_id" = current_setting(\'dazzle.user_id\', true)::uuid'
        assert "%s" not in sql


# ---------------------------------------------------------------------------
# PathCheck (depth-2 nested IN with GUC terminal)
# ---------------------------------------------------------------------------


class TestPathCheck:
    def test_depth2_path_user_attr_terminal(self) -> None:
        # Feedback.manuscript.assessment_event.school_id ... wait depth-2:
        # Feedback -manuscript-> Manuscript -assessment_event-> AssessmentEvent,
        # terminal school_id compared to current_user.school_id.
        p = PathCheck(
            path=["manuscript", "assessment_event", "school_id"],
            op=CompOp.EQ,
            value=ValueRef(user_attr="school_id"),
        )
        sql = compile_predicate_policy(p, "Feedback", _simple_graph(), entity_types=_types)
        assert "%s" not in sql
        # Nested IN structure with the GUC at the terminal, cast to the
        # *terminal* column's type (AssessmentEvent.school_id → uuid).
        assert sql == (
            '"manuscript_id" IN (SELECT "id" FROM "Manuscript" WHERE '
            '"assessment_event_id" IN (SELECT "id" FROM "AssessmentEvent" '
            "WHERE \"school_id\" = current_setting('dazzle.user_school_id', true)::uuid))"
        )


# ---------------------------------------------------------------------------
# BoolComposite
# ---------------------------------------------------------------------------


class TestBoolComposite:
    def test_and(self) -> None:
        p = BoolComposite.make(
            BoolOp.AND,
            [
                ColumnCheck(field="status", op=CompOp.EQ, value=ValueRef(literal="archived")),
                ColumnCheck(field="school_id", op=CompOp.EQ, value=ValueRef(current_user=True)),
            ],
        )
        sql = compile_predicate_policy(p, "Feedback", _simple_graph(), entity_types=_types)
        assert "%s" not in sql
        assert " AND " in sql
        assert "'archived'" in sql
        assert "current_setting('dazzle.user_id', true)::uuid" in sql

    def test_or(self) -> None:
        p = BoolComposite.make(
            BoolOp.OR,
            [
                ColumnCheck(field="status", op=CompOp.EQ, value=ValueRef(literal="a")),
                ColumnCheck(field="status", op=CompOp.EQ, value=ValueRef(literal="b")),
            ],
        )
        sql = compile_predicate_policy(p, "Feedback", _simple_graph(), entity_types=_types)
        assert " OR " in sql
        assert "%s" not in sql

    def test_not(self) -> None:
        p = BoolComposite(
            op=BoolOp.NOT,
            children=[
                ColumnCheck(field="status", op=CompOp.EQ, value=ValueRef(literal="archived"))
            ],
        )
        sql = compile_predicate_policy(p, "Feedback", _simple_graph(), entity_types=_types)
        assert sql.startswith("NOT (")
        assert "%s" not in sql


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


class TestConstants:
    def test_tautology(self) -> None:
        assert (
            compile_predicate_policy(Tautology(), "Feedback", _simple_graph(), entity_types=_types)
            == "true"
        )

    def test_contradiction(self) -> None:
        assert (
            compile_predicate_policy(
                Contradiction(), "Feedback", _simple_graph(), entity_types=_types
            )
            == "false"
        )


# ---------------------------------------------------------------------------
# Unresolvable cast type → ValueError
# ---------------------------------------------------------------------------


class TestUnresolvableType:
    def test_user_attr_unknown_column_raises(self) -> None:
        # `mystery` is not in the type resolver → must fail loud, not emit
        # an untyped/wrong policy.
        p = UserAttrCheck(field="mystery", op=CompOp.EQ, user_attr="x")
        with pytest.raises(ValueError):
            compile_predicate_policy(p, "Feedback", _simple_graph(), entity_types=_types)


# ---------------------------------------------------------------------------
# collect_user_attr_refs
# ---------------------------------------------------------------------------


class TestCollectUserAttrRefs:
    def test_collects_across_variants(self) -> None:
        p = BoolComposite.make(
            BoolOp.AND,
            [
                # ColumnCheck with current_user → "id"
                ColumnCheck(field="school_id", op=CompOp.EQ, value=ValueRef(current_user=True)),
                # UserAttrCheck → "school_id"
                UserAttrCheck(field="school_id", op=CompOp.EQ, user_attr="school_id"),
                # PathCheck with user_attr terminal → "department"
                PathCheck(
                    path=["manuscript", "assessment_event", "school_id"],
                    op=CompOp.EQ,
                    value=ValueRef(user_attr="department"),
                ),
            ],
        )
        refs = collect_user_attr_refs(p)
        assert refs == {"id", "school_id", "department"}

    def test_empty_for_literal_only(self) -> None:
        p = ColumnCheck(field="status", op=CompOp.EQ, value=ValueRef(literal="archived"))
        assert collect_user_attr_refs(p) == set()
