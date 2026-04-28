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
"""

from __future__ import annotations

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
