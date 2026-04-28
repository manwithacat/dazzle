"""Regression test for #909 — scope predicate columns must be
qualified with the source entity table.

Pre-fix, `compile_predicate` for ColumnCheck / UserAttrCheck /
ColumnRefCheck emitted unqualified column references like
`"school" = %s`. When the QueryBuilder later applied a source-table
alias to user-authored filters (because FK display joins introduced
table ambiguity), the scope predicate stayed unqualified — so
`"school"` could bind to a JOINed table's `school` column instead
of the source entity's.

AegisMark hit this with StudentProfile (joined User + School both
have `school` columns). The teacher-scope filter
`school = current_user.school` ANDed with the user's
`id = current_context` PK filter returned 0 rows because the
unqualified `"school"` bound to `User.school` (from the FK display
join), and most pupils' user accounts didn't have a school value
matching the teacher's school.

Post-fix every leaf comparison column is qualified with the source
entity table, eliminating the JOIN-induced ambiguity.

#910 follow-up: pure qualification was too aggressive — the DSL
sometimes uses the relation name (`school`) as shorthand for the FK
column (`school_id`). When the bare name doesn't exist on the
source entity but the `_id` form does, resolve to the `_id` column
(mirrors the PathCheck heuristic). When neither exists, fall back
to the bare ref so legitimate edge cases (entity not in FK graph,
e.g. tests) don't 500.
"""

from __future__ import annotations

from dazzle.core.ir.domain import EntitySpec
from dazzle.core.ir.fields import FieldSpec, FieldType, FieldTypeKind
from dazzle.core.ir.fk_graph import FKGraph
from dazzle.core.ir.predicates import (
    BoolComposite,
    BoolOp,
    ColumnCheck,
    ColumnRefCheck,
    CompOp,
    UserAttrCheck,
    ValueRef,
)
from dazzle_back.runtime.predicate_compiler import compile_predicate


def _make_fk_graph_with_entity(
    entity_name: str,
    fields: list[tuple[str, str, str | None]],
) -> FKGraph:
    """Build an FKGraph from a single entity with given fields.

    Each field is ``(name, kind, ref_entity_or_None)``. Kind is one of
    ``"str" | "uuid" | "ref"``.
    """
    entity_fields = []
    for fname, kind, ref in fields:
        if kind == "ref" and ref:
            ftype = FieldType(kind=FieldTypeKind.REF, ref_entity=ref)
        else:
            ftype = FieldType(kind=FieldTypeKind(kind))
        entity_fields.append(FieldSpec(name=fname, type=ftype))
    entity = EntitySpec(name=entity_name, fields=entity_fields)
    return FKGraph.from_entities([entity])


class TestUserAttrCheckQualifiesColumn:
    """The exact failure mode from #909 — `school = current_user.school`
    on StudentProfile must produce `"StudentProfile"."school" = %s`,
    not `"school" = %s`."""

    def test_school_eq_current_user_school_qualified(self) -> None:
        predicate = UserAttrCheck(field="school", op=CompOp.EQ, user_attr="school")
        sql, _ = compile_predicate(predicate, "StudentProfile", FKGraph())
        assert sql == '"StudentProfile"."school" = %s'

    def test_qualifies_with_explicit_schema(self) -> None:
        predicate = UserAttrCheck(field="school", op=CompOp.EQ, user_attr="school")
        sql, _ = compile_predicate(predicate, "StudentProfile", FKGraph(), schema="tenant_oakwood")
        assert sql == '"tenant_oakwood"."StudentProfile"."school" = %s'

    def test_no_entity_name_falls_back_to_unqualified(self) -> None:
        """The fallback for callers that don't pass entity_name keeps
        the bare-column behaviour. Direct compiler invocations from
        tests / ad-hoc scripts shouldn't break."""
        from dazzle_back.runtime.predicate_compiler import _compile_user_attr_check

        predicate = UserAttrCheck(field="school", op=CompOp.EQ, user_attr="school")
        sql, _ = _compile_user_attr_check(predicate)
        assert sql == '"school" = %s'


class TestColumnCheckQualifiesColumn:
    """The same fix applies to literal-value comparisons used by
    aggregate where-clauses (`count(X where status = active)`)."""

    def test_status_eq_literal_qualified(self) -> None:
        predicate = ColumnCheck(field="status", op=CompOp.EQ, value=ValueRef(literal="active"))
        sql, _ = compile_predicate(predicate, "Order", FKGraph())
        assert sql == '"Order"."status" = %s'

    def test_is_null_qualified(self) -> None:
        predicate = ColumnCheck(
            field="archived_at", op=CompOp.IS, value=ValueRef(literal_null=True)
        )
        sql, _ = compile_predicate(predicate, "Order", FKGraph())
        assert sql == '"Order"."archived_at" IS NULL'


class TestColumnRefCheckQualifiesBothColumns:
    """Same-row column-vs-column comparisons used by reporting
    aggregate where-clauses (`count(X where latest_grade >=
    target_grade)`) — both sides need qualification."""

    def test_both_sides_qualified(self) -> None:
        predicate = ColumnRefCheck(field="latest_grade", op=CompOp.GTE, other_field="target_grade")
        sql, _ = compile_predicate(predicate, "StudentProfile", FKGraph())
        assert sql == '"StudentProfile"."latest_grade" >= "StudentProfile"."target_grade"'


class TestBoolCompositeRecursesQualification:
    """Predicates assembled via AND/OR composites — every leaf
    inside must be qualified."""

    def test_and_of_user_attr_and_column_check(self) -> None:
        predicate = BoolComposite(
            op=BoolOp.AND,
            children=[
                UserAttrCheck(field="school", op=CompOp.EQ, user_attr="school"),
                ColumnCheck(
                    field="status",
                    op=CompOp.EQ,
                    value=ValueRef(literal="enrolled"),
                ),
            ],
        )
        sql, _ = compile_predicate(predicate, "StudentProfile", FKGraph())
        # Both leaves must be qualified
        assert '"StudentProfile"."school"' in sql
        assert '"StudentProfile"."status"' in sql

    def test_or_recurses_qualification(self) -> None:
        predicate = BoolComposite(
            op=BoolOp.OR,
            children=[
                ColumnCheck(field="status", op=CompOp.EQ, value=ValueRef(literal="urgent")),
                ColumnCheck(field="severity", op=CompOp.GT, value=ValueRef(literal=7)),
            ],
        )
        sql, _ = compile_predicate(predicate, "Alert", FKGraph())
        assert '"Alert"."status"' in sql
        assert '"Alert"."severity"' in sql


class TestQualificationSurvivesJoinScenario:
    """The AegisMark scenario: StudentProfile filter `id = current_context`
    plus scope `school = current_user.school`. With FK display joins on
    User + School (which both have `school` columns), the scope predicate
    must bind to StudentProfile.school, not User.school.

    This test exercises the end-to-end SQL: scope-predicate-from-compiler
    + user-filter-via-QueryBuilder, asserting both end up referring to
    `"StudentProfile"."school"` and `"StudentProfile"."id"` respectively."""

    def test_full_where_clause_unambiguous(self) -> None:
        from dazzle_back.runtime.query_builder import QueryBuilder

        # Compile the scope predicate the way RBAC does
        scope_predicate = UserAttrCheck(field="school", op=CompOp.EQ, user_attr="school")
        scope_sql, scope_params = compile_predicate(scope_predicate, "StudentProfile", FKGraph())

        # Build a query as the runtime would:
        #   - source = StudentProfile
        #   - simulated FK display join on User
        #   - scope predicate as raw SQL (__scope_predicate)
        #   - user filter id = <uuid>
        builder = QueryBuilder(table_name="StudentProfile", placeholder_style="%s")
        builder.joins.append('LEFT JOIN "User" ON "User"."id" = "StudentProfile"."user"')
        builder.add_filters(
            {
                "__scope_predicate": (scope_sql, scope_params),
                "id": "517536b5-e9e3-5f9b-8f2a-fd62722438d1",
            }
        )

        where_sql, _ = builder.build_where_clause()

        # Scope predicate now targets the source table explicitly
        assert '"StudentProfile"."school"' in where_sql, (
            "Scope predicate must qualify column with source entity table — "
            "otherwise the JOINed table's `school` column wins. #909."
        )
        # User filter qualified by the QueryBuilder's source_alias logic
        assert '"StudentProfile"."id"' in where_sql


class TestRelationNameResolvesToFkColumn:
    """#910: when the DSL uses the relation name (`school`) but the
    actual column is the FK form (`school_id`), the qualifier must
    resolve to the existing column rather than emit `"X"."school"`
    and 500 with `column "school" does not exist`."""

    def test_user_attr_check_resolves_relation_to_fk_id(self) -> None:
        """`school = current_user.school` on an entity whose `school`
        is a ref field (column = `school_id`) should compile to
        `"X"."school_id" = %s`, not `"X"."school" = %s`."""
        # Entity has `school` as a ref field — the actual column is `school_id`
        graph = _make_fk_graph_with_entity(
            "StudentProfile",
            [
                ("id", "uuid", None),
                ("school_id", "ref", "School"),  # FK column
                # no scalar `school` column
            ],
        )
        # DSL author wrote `school = current_user.school` — predicate's
        # field is "school" (the relation name)
        predicate = UserAttrCheck(field="school", op=CompOp.EQ, user_attr="school")
        sql, _ = compile_predicate(predicate, "StudentProfile", graph)
        assert sql == '"StudentProfile"."school_id" = %s', (
            "Relation name `school` must resolve to FK column `school_id` — "
            'otherwise Postgres errors `column "school" does not exist` '
            "and the region returns 500 (#910)."
        )

    def test_column_check_resolves_relation_to_fk_id(self) -> None:
        graph = _make_fk_graph_with_entity(
            "Order",
            [
                ("id", "uuid", None),
                ("status_id", "ref", "OrderStatus"),
            ],
        )
        predicate = ColumnCheck(field="status", op=CompOp.EQ, value=ValueRef(literal="active"))
        sql, _ = compile_predicate(predicate, "Order", graph)
        assert sql == '"Order"."status_id" = %s'

    def test_field_exists_as_is_keeps_bare_name(self) -> None:
        """When the field exists as-is on the entity, no _id rewrite —
        we don't want to clobber legitimate scalar columns."""
        graph = _make_fk_graph_with_entity(
            "Order",
            [
                ("id", "uuid", None),
                ("status", "str", None),  # scalar `status` exists as-is
            ],
        )
        predicate = ColumnCheck(field="status", op=CompOp.EQ, value=ValueRef(literal="active"))
        sql, _ = compile_predicate(predicate, "Order", graph)
        assert sql == '"Order"."status" = %s'

    def test_neither_form_exists_falls_back_to_bare_ref(self) -> None:
        """When neither `field` nor `field_id` exists on the entity,
        fall through with the bare name. Lets SQL surface a genuine
        schema error rather than fabricating a column name."""
        graph = _make_fk_graph_with_entity(
            "Order",
            [
                ("id", "uuid", None),
                # nothing else — `status` and `status_id` both absent
            ],
        )
        predicate = ColumnCheck(field="status", op=CompOp.EQ, value=ValueRef(literal="active"))
        sql, _ = compile_predicate(predicate, "Order", graph)
        # Still qualified with table — no fallback to unqualified —
        # but field name passes through as-is
        assert sql == '"Order"."status" = %s'

    def test_no_fk_graph_disables_resolution(self) -> None:
        """Callers without an FK graph (rare — direct unit test usage)
        get the original `<entity>.<field>` qualification with no
        relation-name resolution."""
        predicate = UserAttrCheck(field="school", op=CompOp.EQ, user_attr="school")
        # Pass an empty graph — no entities registered, nothing exists
        sql, _ = compile_predicate(predicate, "StudentProfile", FKGraph())
        # Falls through with bare field name — same shape as before #910
        assert sql == '"StudentProfile"."school" = %s'

    def test_bool_composite_threads_fk_graph_to_leaves(self) -> None:
        """The fk_graph plumbing must reach every leaf inside an AND/OR
        composite — otherwise OR-combined scope rules with mixed
        relation-name / scalar-name leaves would still 500."""
        graph = _make_fk_graph_with_entity(
            "StudentProfile",
            [
                ("id", "uuid", None),
                ("school_id", "ref", "School"),
                ("status", "str", None),
            ],
        )
        predicate = BoolComposite(
            op=BoolOp.AND,
            children=[
                UserAttrCheck(field="school", op=CompOp.EQ, user_attr="school"),
                ColumnCheck(field="status", op=CompOp.EQ, value=ValueRef(literal="enrolled")),
            ],
        )
        sql, _ = compile_predicate(predicate, "StudentProfile", graph)
        # Both leaves resolved — relation name → FK col, scalar untouched
        assert '"StudentProfile"."school_id"' in sql
        assert '"StudentProfile"."status"' in sql
        # No bare unqualified `school` snuck in
        assert '"StudentProfile"."school" =' not in sql

    def test_column_ref_check_resolves_both_sides(self) -> None:
        """Same-row column-vs-column comparisons need the heuristic
        applied to both sides."""
        graph = _make_fk_graph_with_entity(
            "StudentProfile",
            [
                ("id", "uuid", None),
                ("tutor_id", "ref", "User"),
                ("class_teacher_id", "ref", "User"),
            ],
        )
        predicate = ColumnRefCheck(field="tutor", op=CompOp.EQ, other_field="class_teacher")
        sql, _ = compile_predicate(predicate, "StudentProfile", graph)
        assert sql == '"StudentProfile"."tutor_id" = "StudentProfile"."class_teacher_id"'
