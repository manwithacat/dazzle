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
    _inline_sql_literal,
    build_entity_type_resolver,
    collect_user_attr_refs,
    compile_predicate_policy,
)
from dazzle.http.specs.entity import EntitySpec, FieldSpec, FieldType, ScalarType


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

    def test_exists_check_bindings(self) -> None:
        # current_user → "id"; current_user.<attr> → "<attr>"; plain entity-side
        # bindings (id / column names) contribute nothing.
        p = ExistsCheck(
            target_entity="TeamMembership",
            bindings=[
                ExistsBinding(junction_field="user_id", target="current_user"),
                ExistsBinding(junction_field="team_id", target="current_user.team"),
                ExistsBinding(junction_field="resource_id", target="id"),
            ],
        )
        assert collect_user_attr_refs(p) == {"id", "team"}

    def test_exists_check_current_user_only(self) -> None:
        p = ExistsCheck(
            target_entity="Membership",
            bindings=[ExistsBinding(junction_field="user_id", target="current_user")],
        )
        assert collect_user_attr_refs(p) == {"id"}


# ---------------------------------------------------------------------------
# build_entity_type_resolver — lazy + complete (review FIX 1)
# ---------------------------------------------------------------------------


def _scalar(st: ScalarType) -> FieldType:
    return FieldType(kind="scalar", scalar_type=st)


class TestEntityTypeResolver:
    def test_resolves_referenced_columns(self) -> None:
        entities = [
            EntitySpec(
                name="Doc",
                fields=[
                    FieldSpec(name="id", type=_scalar(ScalarType.UUID)),
                    FieldSpec(name="status", type=_scalar(ScalarType.STR)),
                    FieldSpec(name="amount", type=_scalar(ScalarType.INT)),
                    FieldSpec(name="owner_id", type=FieldType(kind="ref", ref_entity="User")),
                ],
            ),
        ]
        resolver = build_entity_type_resolver(entities)
        assert resolver("Doc", "status") == "text"
        assert resolver("Doc", "amount") == "integer"
        assert resolver("Doc", "owner_id") == "uuid"
        assert resolver("Doc", "id") == "uuid"

    def test_unreferenced_richtext_does_not_break_construction(self) -> None:
        # A richtext/file/image column on an entity must NOT break resolver
        # construction (it's never resolved unless referenced) — and even when
        # resolved it falls back to text, mirroring the SA bridge.
        entities = [
            EntitySpec(
                name="Article",
                fields=[
                    FieldSpec(name="id", type=_scalar(ScalarType.UUID)),
                    FieldSpec(name="body", type=_scalar(ScalarType.RICHTEXT)),
                    FieldSpec(name="attachment", type=_scalar(ScalarType.FILE)),
                    FieldSpec(name="cover", type=_scalar(ScalarType.IMAGE)),
                    FieldSpec(name="owner_id", type=FieldType(kind="ref", ref_entity="User")),
                ],
            ),
        ]
        # Construction must not raise even though richtext/file/image exist.
        resolver = build_entity_type_resolver(entities)
        # An unrelated, scope-referenced column still resolves correctly.
        assert resolver("Article", "owner_id") == "uuid"
        # And if a richtext/file/image IS referenced, it resolves to text
        # (no raise) — matching sa_schema's Text fallback.
        assert resolver("Article", "body") == "text"
        assert resolver("Article", "attachment") == "text"
        assert resolver("Article", "cover") == "text"

    def test_unreferenced_richtext_compile_unrelated_predicate(self) -> None:
        # Compiling a policy for a predicate that references only `status`
        # must succeed even though the entity also has a richtext column.
        entities = [
            EntitySpec(
                name="Article",
                fields=[
                    FieldSpec(name="id", type=_scalar(ScalarType.UUID)),
                    FieldSpec(name="status", type=_scalar(ScalarType.STR)),
                    FieldSpec(name="body", type=_scalar(ScalarType.RICHTEXT)),
                ],
            ),
        ]
        resolver = build_entity_type_resolver(entities)
        graph = FKGraph()
        graph._edges = {"Article": []}
        graph._fields = {"Article": {"id", "status", "body"}}
        p = ColumnCheck(field="status", op=CompOp.EQ, value=ValueRef(literal="published"))
        sql = compile_predicate_policy(p, "Article", graph, entity_types=resolver)
        assert sql == '"Article"."status" = \'published\''

    def test_unknown_referenced_column_raises(self) -> None:
        resolver = build_entity_type_resolver(
            [EntitySpec(name="Doc", fields=[FieldSpec(name="id", type=_scalar(ScalarType.UUID))])]
        )
        with pytest.raises(ValueError):
            resolver("Doc", "nonexistent")


# ---------------------------------------------------------------------------
# ExistsCheck in policy mode (Phase C final review FIX 2)
# ---------------------------------------------------------------------------


def _junction_graph() -> FKGraph:
    """Graph with a Team junction so ExistsCheck bindings resolve."""
    graph = FKGraph()
    graph._edges = {
        "Project": [FKEdge("Project", "owner_id", "User")],
        "TeamMembership": [
            FKEdge("TeamMembership", "user_id", "User"),
            FKEdge("TeamMembership", "project_id", "Project"),
        ],
    }
    graph._fields = {
        "Project": {"id", "owner_id", "name"},
        "TeamMembership": {"id", "user_id", "project_id", "role"},
        "User": {"id"},
    }
    return graph


def _junction_types(entity: str, field: str) -> str:
    table = {
        ("TeamMembership", "user_id"): "uuid",
        ("TeamMembership", "project_id"): "uuid",
        ("TeamMembership", "role"): "text",
    }
    try:
        return table[(entity, field)]
    except KeyError:
        raise ValueError(f"no pg type for {entity}.{field}")


class TestExistsCheckPolicyMode:
    def test_supported_bindings_compile(self) -> None:
        # current_user + id + null are the supported policy-mode forms.
        p = ExistsCheck(
            target_entity="TeamMembership",
            bindings=[
                ExistsBinding(junction_field="user_id", target="current_user"),
                ExistsBinding(junction_field="project_id", target="id"),
                ExistsBinding(junction_field="role", target="null"),
            ],
        )
        sql = compile_predicate_policy(
            p, "Project", _junction_graph(), entity_types=_junction_types
        )
        assert "%s" not in sql
        assert sql.startswith("EXISTS (SELECT 1 FROM ")
        # current_user → GUC ::uuid cast on the junction column's type
        assert "current_setting('dazzle.user_id', true)::uuid" in sql
        # id → correlated reference to the outer row's PK
        assert '"project_id" = "Project"."id"' in sql
        # null → IS NULL
        assert '"role" IS NULL' in sql

    def test_current_user_attr_binding_compiles(self) -> None:
        p = ExistsCheck(
            target_entity="TeamMembership",
            bindings=[
                ExistsBinding(junction_field="role", target="current_user.role"),
            ],
        )
        sql = compile_predicate_policy(
            p, "Project", _junction_graph(), entity_types=_junction_types
        )
        assert "%s" not in sql
        assert "current_setting('dazzle.user_role', true)::text" in sql

    def test_entity_column_target_raises(self) -> None:
        # A binding target that is an arbitrary entity column (not
        # current_user / current_user.<attr> / id / null) is unsupported in
        # policy mode → fail loud at generation time.
        p = ExistsCheck(
            target_entity="TeamMembership",
            bindings=[
                ExistsBinding(junction_field="project_id", target="owner_id"),
            ],
        )
        with pytest.raises(ValueError, match="entity-column"):
            compile_predicate_policy(p, "Project", _junction_graph(), entity_types=_junction_types)
