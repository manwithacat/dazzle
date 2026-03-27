"""Tests for predicate tree → SQL compilation."""

import pytest

from dazzle.core.ir.predicates import (
    BoolComposite,
    BoolOp,
    ColumnCheck,
    CompOp,
    Contradiction,
    ExistsBinding,
    ExistsCheck,
    PathCheck,
    Tautology,
    UserAttrCheck,
    ValueRef,
)

pytest.importorskip("fastapi")

from dazzle.core.ir.fk_graph import FKEdge, FKGraph
from dazzle_back.runtime.predicate_compiler import compile_predicate


def _simple_graph() -> FKGraph:
    """Graph: Feedback -manuscript_id-> Manuscript -student_id-> Student."""
    graph = FKGraph()
    graph._edges = {
        "Feedback": [FKEdge("Feedback", "manuscript_id", "Manuscript")],
        "Manuscript": [
            FKEdge("Manuscript", "student_id", "Student"),
            FKEdge("Manuscript", "assessment_event_id", "AssessmentEvent"),
        ],
        "AssessmentEvent": [FKEdge("AssessmentEvent", "school_id", "School")],
    }
    graph._fields = {
        "Feedback": {"id", "manuscript_id", "content"},
        "Manuscript": {"id", "student_id", "assessment_event_id", "title"},
        "AssessmentEvent": {"id", "school_id", "name"},
        "Student": {"id", "name"},
        "School": {"id", "name"},
    }
    return graph


class TestColumnCheck:
    def test_eq(self) -> None:
        p = ColumnCheck(field="status", op=CompOp.EQ, value=ValueRef(literal="active"))
        sql, params = compile_predicate(p, "Task", _simple_graph())
        assert '"status" = %s' in sql
        assert params == ["active"]

    def test_ne(self) -> None:
        p = ColumnCheck(field="status", op=CompOp.NEQ, value=ValueRef(literal="archived"))
        sql, params = compile_predicate(p, "Task", _simple_graph())
        assert '"status" != %s' in sql

    def test_null(self) -> None:
        p = ColumnCheck(field="deleted_at", op=CompOp.IS, value=ValueRef(literal_null=True))
        sql, params = compile_predicate(p, "Task", _simple_graph())
        assert '"deleted_at" IS NULL' in sql
        assert params == []


class TestUserAttrCheck:
    def test_simple(self) -> None:
        p = UserAttrCheck(field="school_id", op=CompOp.EQ, user_attr="school")
        sql, params = compile_predicate(p, "Teacher", _simple_graph())
        assert '"school_id" = %s' in sql
        # Params contain a UserAttrRef marker that the route handler resolves
        # at request time via _resolve_user_attribute(attr_name, auth_context).
        assert len(params) == 1
        from dazzle_back.runtime.predicate_compiler import UserAttrRef

        assert isinstance(params[0], UserAttrRef)
        assert params[0].attr_name == "school"


class TestPathCheck:
    def test_depth_1(self) -> None:
        """manuscript.student_id = current_user → subquery on Manuscript."""
        p = PathCheck(
            path=["manuscript", "student_id"],
            op=CompOp.EQ,
            value=ValueRef(current_user=True),
        )
        sql, params = compile_predicate(p, "Feedback", _simple_graph())
        assert '"manuscript_id" IN' in sql
        assert 'SELECT "id" FROM "Manuscript"' in sql
        assert '"student_id" = %s' in sql

    def test_depth_2(self) -> None:
        """manuscript.assessment_event.school_id = current_user.school
        Each subquery SELECTs "id" so parent IN matches PKs, not FK values."""
        p = PathCheck(
            path=["manuscript", "assessment_event", "school_id"],
            op=CompOp.EQ,
            value=ValueRef(user_attr="school"),
        )
        sql, params = compile_predicate(p, "Feedback", _simple_graph())
        # Root: manuscript_id IN (...)
        assert '"manuscript_id" IN' in sql
        # Middle layer: SELECT "id" FROM Manuscript WHERE assessment_event_id IN (...)
        assert 'SELECT "id" FROM "Manuscript"' in sql
        assert '"assessment_event_id" IN' in sql
        # Innermost: SELECT "id" FROM AssessmentEvent WHERE school_id = %s
        assert 'SELECT "id" FROM "AssessmentEvent"' in sql
        assert '"school_id" =' in sql


class TestExistsCheck:
    def test_exists(self) -> None:
        p = ExistsCheck(
            target_entity="AgentAssignment",
            bindings=[
                ExistsBinding(junction_field="agent", target="current_user"),
                ExistsBinding(junction_field="contact", target="id"),
            ],
        )
        sql, params = compile_predicate(p, "Contact", _simple_graph())
        assert "EXISTS" in sql
        assert "NOT" not in sql

    def test_not_exists(self) -> None:
        p = ExistsCheck(
            target_entity="BlockList",
            bindings=[
                ExistsBinding(junction_field="user", target="current_user"),
                ExistsBinding(junction_field="resource", target="id"),
            ],
            negated=True,
        )
        sql, params = compile_predicate(p, "Resource", _simple_graph())
        assert "NOT EXISTS" in sql


class TestBoolComposite:
    def test_and(self) -> None:
        left = ColumnCheck(field="status", op=CompOp.EQ, value=ValueRef(literal="active"))
        right = ColumnCheck(field="archived", op=CompOp.EQ, value=ValueRef(literal=False))
        p = BoolComposite(op=BoolOp.AND, children=[left, right])
        sql, params = compile_predicate(p, "Task", _simple_graph())
        assert "AND" in sql
        assert len(params) == 2

    def test_or(self) -> None:
        left = UserAttrCheck(field="owner", op=CompOp.EQ, user_attr="entity_id")
        right = UserAttrCheck(field="creator", op=CompOp.EQ, user_attr="entity_id")
        p = BoolComposite(op=BoolOp.OR, children=[left, right])
        sql, params = compile_predicate(p, "Task", _simple_graph())
        assert "OR" in sql

    def test_not(self) -> None:
        inner = ColumnCheck(field="status", op=CompOp.EQ, value=ValueRef(literal="archived"))
        p = BoolComposite(op=BoolOp.NOT, children=[inner])
        sql, params = compile_predicate(p, "Task", _simple_graph())
        assert "NOT" in sql


class TestTerminals:
    def test_tautology(self) -> None:
        sql, params = compile_predicate(Tautology(), "Task", _simple_graph())
        assert sql == ""
        assert params == []

    def test_contradiction(self) -> None:
        sql, params = compile_predicate(Contradiction(), "Task", _simple_graph())
        assert "FALSE" in sql
        assert params == []


class TestSchemaQualification:
    """Test schema-qualified table names for tenant isolation (#621)."""

    def test_exists_check_unqualified_by_default(self) -> None:
        p = ExistsCheck(
            target_entity="CompanyContact",
            bindings=[ExistsBinding(junction_field="contact", target="current_user", operator="=")],
        )
        sql, _ = compile_predicate(p, "Company", _simple_graph())
        assert 'FROM "CompanyContact"' in sql
        assert "tenant" not in sql

    def test_exists_check_schema_qualified(self) -> None:
        p = ExistsCheck(
            target_entity="CompanyContact",
            bindings=[ExistsBinding(junction_field="contact", target="current_user", operator="=")],
        )
        sql, _ = compile_predicate(p, "Company", _simple_graph(), schema="tenant_abc")
        assert 'FROM "tenant_abc"."CompanyContact"' in sql

    def test_path_check_schema_qualified(self) -> None:
        p = PathCheck(
            path=["manuscript", "assessment_event", "school_id"],
            op=CompOp.EQ,
            value=ValueRef(user_attr="school"),
        )
        sql, _ = compile_predicate(p, "Feedback", _simple_graph(), schema="tenant_xyz")
        assert '"tenant_xyz"."AssessmentEvent"' in sql
        assert '"tenant_xyz"."Manuscript"' in sql
        assert 'SELECT "id" FROM "tenant_xyz"."Manuscript"' in sql
        assert 'SELECT "id" FROM "tenant_xyz"."AssessmentEvent"' in sql

    def test_bool_composite_threads_schema(self) -> None:
        left = ExistsCheck(
            target_entity="JunctionA",
            bindings=[ExistsBinding(junction_field="user", target="current_user", operator="=")],
        )
        right = ExistsCheck(
            target_entity="JunctionB",
            bindings=[ExistsBinding(junction_field="user", target="current_user", operator="=")],
        )
        p = BoolComposite(op=BoolOp.OR, children=[left, right])
        sql, _ = compile_predicate(p, "Root", _simple_graph(), schema="tenant_t")
        assert '"tenant_t"."JunctionA"' in sql
        assert '"tenant_t"."JunctionB"' in sql
