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
from dazzle.http.runtime.predicate_compiler import (
    _field_type_to_pg,
    collect_user_attr_refs,
    compile_predicate,
    compile_predicate_policy,
)


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
        from dazzle.http.runtime.predicate_compiler import UserAttrRef

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

    def test_outer_fk_column_table_qualified_param_mode(self) -> None:
        """#1449: in param mode the OUTER root FK column is TABLE-qualified with the
        source entity, so it can't collide with a same-named column on an FK-display
        LEFT JOIN target (a list region that joins Manuscript for display would make a
        bare ``"manuscript_id"`` ambiguous). TABLE-, not schema-qualified (#1386)."""
        p = PathCheck(
            path=["manuscript", "student_id"], op=CompOp.EQ, value=ValueRef(current_user=True)
        )
        sql, _ = compile_predicate(p, "Feedback", _simple_graph())
        assert '"Feedback"."manuscript_id" IN' in sql
        # schema-qualification is NOT applied to the outer ref (must match FROM).
        sql_s, _ = compile_predicate(p, "Feedback", _simple_graph(), schema="tenant_x")
        assert '"Feedback"."manuscript_id" IN' in sql_s
        assert 'tenant_x"."Feedback"."manuscript_id" IN' not in sql_s

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


class TestExistsFieldReference:
    """via bindings that reference root entity fields generate column refs (#764).

    #1469: the entity-column binding resolves through the same bare⇄`<field>_id`
    heuristic the rest of the compiler uses — the bare name when it names a real
    column or the source entity isn't in the FK graph (the fallback below), the
    `<field>_id` form when that's the actual FK column on an in-graph entity.
    """

    def test_field_binding_falls_back_to_bare_when_entity_not_in_graph(self) -> None:
        """An entity absent from the FK graph keeps the bare target (safe fallback)."""
        p = ExistsCheck(
            target_entity="ParentContact",
            bindings=[
                ExistsBinding(junction_field="student_id", target="student_profile"),
                ExistsBinding(junction_field="parent_user_id", target="current_user"),
            ],
        )
        # MarkingResult is not in _simple_graph → resolution can't see its columns
        # → bare fallback (let SQL surface a genuine schema error, not fabricate).
        sql, params = compile_predicate(p, "MarkingResult", _simple_graph())
        assert '"MarkingResult"."student_profile"' in sql
        # current_user should be a param, not a column ref
        assert len(params) == 1

    def test_field_binding_bare_name_no_id_appended_when_not_in_graph(self) -> None:
        """No blind `_id` append: an entity absent from the graph keeps the bare name."""
        p = ExistsCheck(
            target_entity="Junction",
            bindings=[
                ExistsBinding(junction_field="fk", target="other_entity"),
            ],
        )
        sql, params = compile_predicate(p, "Root", _simple_graph())
        assert '"Root"."other_entity"' in sql
        assert '"Root"."other_entity_id"' not in sql

    def test_entity_column_binding_resolves_id_suffix(self) -> None:
        """#1469: a bare relation-name target resolves to the real `<name>_id` FK
        column when the source entity IS in the FK graph.

        This is the regression: `Manuscript` has the FK column `student_id`, but the
        binding writes the relation name `student`. Emitting `"Manuscript"."student"`
        raw referenced a non-existent column → the query raised → the region rendered
        empty for every `_id`-suffixed source entity while bare-named ones worked.
        """
        p = ExistsCheck(
            target_entity="ParentContact",
            bindings=[
                ExistsBinding(junction_field="student_id", target="student"),
                ExistsBinding(junction_field="parent_user_id", target="current_user"),
            ],
        )
        sql, _ = compile_predicate(p, "Manuscript", _simple_graph())
        assert '"Manuscript"."student_id"' in sql, "bare `student` must resolve to student_id"
        assert '"Manuscript"."student"' not in sql

    def test_entity_column_binding_keeps_existing_bare_column(self) -> None:
        """A target that already names a real column on an in-graph entity stays bare."""
        p = ExistsCheck(
            target_entity="Junction",
            bindings=[
                ExistsBinding(junction_field="m", target="title"),  # Manuscript.title exists
                ExistsBinding(junction_field="u", target="current_user"),
            ],
        )
        sql, _ = compile_predicate(p, "Manuscript", _simple_graph())
        assert '"Manuscript"."title"' in sql
        assert '"Manuscript"."title_id"' not in sql


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


# ---------------------------------------------------------------------------
# Mutation-audit residuals (2026-06-08): branches the PG suite executed but
# didn't pin. Each asserts a specific SQL/contract effect that a single
# operator/keyword flip in the compiler would break.
# ---------------------------------------------------------------------------

from types import SimpleNamespace  # noqa: E402


class TestResidualBranches:
    def test_scalar_field_type_maps_to_pg_name(self) -> None:
        # `kind == "scalar"` must map (str → text); a `!=` flip would drop scalars to the
        # `raise ValueError` fallback, breaking GUC casts for every str/int scope column.
        ft = SimpleNamespace(kind="scalar", scalar_type=SimpleNamespace(value="str"))
        assert _field_type_to_pg(ft) == "text"

    def test_exists_null_target_emits_is_null(self) -> None:
        # `via J(field = null)` with op "=" → IS NULL; an `op == "="` → `!=` flip would
        # emit IS NOT NULL, inverting the filter.
        p = ExistsCheck(
            target_entity="J",
            bindings=[ExistsBinding(junction_field="field", target="null", operator="=")],
        )
        sql, _ = compile_predicate(p, "Root", _simple_graph())
        assert "IS NULL" in sql
        assert "IS NOT NULL" not in sql

    def test_current_user_binding_requires_id_guc(self) -> None:
        # A binding target of "current_user" means the row's id GUC is needed; a
        # `target == "current_user"` → `!=` flip would drop "id" from the required GUC set
        # (the runtime would then never set it → policy silently denies).
        p = ExistsCheck(
            target_entity="J",
            bindings=[ExistsBinding(junction_field="agent", target="current_user")],
        )
        assert "id" in collect_user_attr_refs(p)

    def test_policy_mode_allows_non_dotted_exists(self) -> None:
        # The dotted-binding guard is `policy is not None AND is_dotted`; an `and`→`or` flip
        # would reject EVERY exists binding in policy mode (RLS scope policies use them).
        p = ExistsCheck(
            target_entity="AgentAssignment",
            bindings=[
                ExistsBinding(junction_field="agent", target="current_user"),
                ExistsBinding(junction_field="contact", target="id"),
            ],
        )
        body = compile_predicate_policy(
            p, "Contact", _simple_graph(), entity_types=lambda e, f: "uuid"
        )
        assert "EXISTS" in body  # must NOT raise

    def test_dotted_junction_two_segments_compiles(self) -> None:
        # A 2-segment dotted path (1 hop + final col) is valid: `assert len(path) >= 2`. A
        # `>= 2` → `> 2` flip would AssertionError on the minimal valid path.
        p = ExistsCheck(
            target_entity="Feedback",
            bindings=[ExistsBinding(junction_field="manuscript.student_id", target="current_user")],
        )
        sql, _ = compile_predicate(p, "Root", _simple_graph())
        assert 'FROM "Manuscript"' in sql

    def test_dotted_junction_three_segments_nests_correctly(self) -> None:
        # A 3-segment path (2 hops) exercises the tail→head wrap loop
        # `range(len(hops) - 1, 0, -1)` + `hops[i - 1]`. An off-by-one in the start, step,
        # or index would IndexError or drop the middle subquery.
        p = ExistsCheck(
            target_entity="Feedback",
            bindings=[
                ExistsBinding(
                    junction_field="manuscript.assessment_event.school_id",
                    target="current_user",
                )
            ],
        )
        sql, _ = compile_predicate(p, "Root", _simple_graph())
        assert 'FROM "Manuscript"' in sql
        assert 'FROM "AssessmentEvent"' in sql

    def test_dotted_junction_null_target_is_rejected(self) -> None:
        # Dotted paths don't support a null target: the guard raises. A flip that lets it
        # through would compile a wrong/incomplete subquery instead of failing loud.
        p = ExistsCheck(
            target_entity="Feedback",
            bindings=[ExistsBinding(junction_field="manuscript.student_id", target="null")],
        )
        with pytest.raises(ValueError):
            compile_predicate(p, "Root", _simple_graph())

    def test_create_probe_binds_id_to_payload_marker(self) -> None:
        # The create-scope probe runs in payload_mode=True: a binding target of "id" must
        # resolve to a PayloadFieldRef param (the root row isn't persisted yet), NOT a
        # `"<entity>"."id"` column ref. A `payload_mode=True`→`False` flip would emit the
        # column ref against a row that doesn't exist.
        from dazzle.http.runtime.predicate_compiler import (
            PayloadFieldRef,
            compile_exists_check_probe,
        )

        p = ExistsCheck(
            target_entity="AgentAssignment",
            bindings=[
                ExistsBinding(junction_field="agent", target="current_user"),
                ExistsBinding(junction_field="contact", target="id"),
            ],
        )
        sql, params = compile_exists_check_probe(p, "Contact", _simple_graph())
        assert any(isinstance(x, PayloadFieldRef) for x in params)
        assert '"Contact"."id"' not in sql
