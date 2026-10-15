"""
Tests for query builder.

Tests filter parsing, SQL generation, and sorting.
"""

from uuid import UUID

import pytest

from dazzle.http.runtime.query_builder import (
    FilterCondition,
    FilterOperator,
    QueryBuilder,
    SortField,
)

Op = FilterOperator

# =============================================================================
# FilterCondition
# =============================================================================


@pytest.mark.parametrize(
    ("key", "value", "field", "operator", "relation_path"),
    [
        pytest.param("status", "active", "status", Op.EQ, [], id="bare-field-is-eq"),
        pytest.param("priority__gt", 5, "priority", Op.GT, [], id="gt"),
        pytest.param("count__gte", 10, "count", Op.GTE, [], id="gte"),
        pytest.param("age__lt", 30, "age", Op.LT, [], id="lt"),
        pytest.param("score__lte", 100, "score", Op.LTE, [], id="lte"),
        pytest.param("status__ne", "deleted", "status", Op.NE, [], id="ne"),
        pytest.param("title__contains", "urgent", "title", Op.CONTAINS, [], id="contains"),
        pytest.param("title__icontains", "URGENT", "title", Op.ICONTAINS, [], id="icontains"),
        pytest.param("name__startswith", "Bug:", "name", Op.STARTSWITH, [], id="startswith"),
        pytest.param("email__endswith", "@example.com", "email", Op.ENDSWITH, [], id="endswith"),
        pytest.param("status__in", ["active", "pending"], "status", Op.IN, [], id="in"),
        pytest.param(
            "status__not_in", ["deleted", "archived"], "status", Op.NOT_IN, [], id="not-in"
        ),
        pytest.param("deleted_at__isnull", True, "deleted_at", Op.ISNULL, [], id="isnull"),
        pytest.param("owner__name", "John", "name", Op.EQ, ["owner"], id="relation-eq"),
        pytest.param(
            "owner__department__name__contains",
            "Sales",
            "name",
            Op.CONTAINS,
            ["owner", "department"],
            id="deep-relation-with-operator",
        ),
        # "unknown_field" is not an operator, so it is the field and the
        # condition falls back to equality.
        pytest.param(
            "owner__unknown_field",
            "value",
            "unknown_field",
            Op.EQ,
            ["owner"],
            id="unknown-suffix-is-a-field-not-an-operator",
        ),
    ],
)
def test_filter_parse(key, value, field, operator, relation_path) -> None:
    cond = FilterCondition.parse(key, value)
    assert (cond.field, cond.operator, cond.value, cond.relation_path) == (
        field,
        operator,
        value,
        relation_path,
    )


_UUID = UUID("12345678-1234-5678-1234-567812345678")


@pytest.mark.parametrize(
    ("field", "operator", "value", "alias", "sql", "params"),
    [
        pytest.param("status", Op.EQ, "active", None, '"status" = %s', ["active"], id="eq"),
        pytest.param(
            "title", Op.CONTAINS, "urgent", None, '"title" LIKE %s', ["%urgent%"], id="contains"
        ),
        pytest.param(
            "name", Op.STARTSWITH, "Bug:", None, '"name" LIKE %s', ["Bug:%"], id="startswith"
        ),
        pytest.param(
            "email",
            Op.ENDSWITH,
            "@test.com",
            None,
            '"email" LIKE %s',
            ["%@test.com"],
            id="endswith",
        ),
        pytest.param(
            "status",
            Op.IN,
            ["a", "b", "c"],
            None,
            '"status" IN (%s, %s, %s)',
            ["a", "b", "c"],
            id="in-one-placeholder-per-item",
        ),
        pytest.param(
            "deleted_at", Op.ISNULL, True, None, '"deleted_at" IS NULL', [], id="isnull-true"
        ),
        pytest.param(
            "deleted_at",
            Op.ISNULL,
            False,
            None,
            '"deleted_at" IS NOT NULL',
            [],
            id="isnull-false",
        ),
        pytest.param(
            "created_at",
            Op.BETWEEN,
            ["2024-01-01", "2024-12-31"],
            None,
            '"created_at" BETWEEN %s AND %s',
            ["2024-01-01", "2024-12-31"],
            id="between",
        ),
        pytest.param("status", Op.EQ, "active", "t", 't."status" = %s', ["active"], id="alias"),
        pytest.param(
            "user_id", Op.EQ, _UUID, None, '"user_id" = %s', [str(_UUID)], id="uuid-param-is-str"
        ),
    ],
)
def test_filter_to_sql(field, operator, value, alias, sql, params) -> None:
    cond = FilterCondition(field=field, operator=operator, value=value)
    assert cond.to_sql(table_alias=alias) == (sql, params)


def test_between_requires_two_values() -> None:
    cond = FilterCondition(field="created_at", operator=Op.BETWEEN, value="single_value")
    with pytest.raises(ValueError, match="BETWEEN operator requires"):
        cond.to_sql()


# =============================================================================
# SortField
# =============================================================================


@pytest.mark.parametrize(
    ("raw", "field", "descending", "relation_path"),
    [
        pytest.param("created_at", "created_at", False, [], id="ascending"),
        pytest.param("-created_at", "created_at", True, [], id="minus-is-descending"),
        pytest.param("owner__name", "name", False, ["owner"], id="relation"),
        pytest.param("-owner__name", "name", True, ["owner"], id="relation-descending"),
    ],
)
def test_sort_parse(raw, field, descending, relation_path) -> None:
    sort = SortField.parse(raw)
    assert (sort.field, sort.descending, sort.relation_path) == (field, descending, relation_path)


@pytest.mark.parametrize(
    ("field", "descending", "alias", "sql"),
    [
        pytest.param("created_at", False, None, '"created_at" ASC', id="asc"),
        pytest.param("created_at", True, None, '"created_at" DESC', id="desc"),
        pytest.param("name", True, "t", 't."name" DESC', id="alias"),
    ],
)
def test_sort_to_sql(field, descending, alias, sql) -> None:
    assert SortField(field=field, descending=descending).to_sql(table_alias=alias) == sql


# =============================================================================
# QueryBuilder
# =============================================================================


def _no_setup(b: QueryBuilder) -> None:
    pass


def _two_filters(b: QueryBuilder) -> None:
    b.add_filter("status", "active")
    b.add_filter("priority__gte", 5)


def _two_sorts(b: QueryBuilder) -> None:
    b.add_sort("-created_at")
    b.add_sort("priority")


def _page_three(b: QueryBuilder) -> None:
    b.set_pagination(page=3, page_size=10)


def _filters_dict(b: QueryBuilder) -> None:
    b.add_filters({"status": "active", "priority__gte": 5, "title__contains": "bug"})


@pytest.mark.parametrize(
    ("setup", "sql", "params"),
    [
        pytest.param(
            _no_setup,
            'SELECT * FROM "Task" LIMIT %s OFFSET %s',
            [20, 0],
            id="bare-select-default-page",
        ),
        pytest.param(
            _two_filters,
            'SELECT * FROM "Task" WHERE "status" = %s AND "priority" >= %s LIMIT %s OFFSET %s',
            ["active", 5, 20, 0],
            id="filters-anded-in-order",
        ),
        pytest.param(
            _two_sorts,
            'SELECT * FROM "Task" ORDER BY "created_at" DESC, "priority" ASC LIMIT %s OFFSET %s',
            [20, 0],
            id="sorts-in-order",
        ),
        pytest.param(
            _page_three,
            'SELECT * FROM "Task" LIMIT %s OFFSET %s',
            [10, 20],
            id="page-3-offset-20",
        ),
        pytest.param(
            _filters_dict,
            'SELECT * FROM "Task" WHERE "status" = %s AND "priority" >= %s AND "title" LIKE %s'
            " LIMIT %s OFFSET %s",
            ["active", 5, "%bug%", 20, 0],
            id="add-filters-dict-in-order",
        ),
    ],
)
def test_build_select(setup, sql, params) -> None:
    builder = QueryBuilder(table_name="Task")
    setup(builder)
    assert builder.build_select() == (sql, params)


def test_build_count_has_where_but_no_order_or_limit() -> None:
    builder = QueryBuilder(table_name="Task")
    builder.add_filter("status", "active")
    builder.add_sort("-created_at")
    assert builder.build_count() == ('SELECT COUNT(*) FROM "Task" WHERE "status" = %s', ["active"])


@pytest.mark.parametrize(
    ("sorts", "order"),
    [
        pytest.param("-created_at", 'ORDER BY "created_at" DESC', id="string"),
        pytest.param(
            ["priority", "-created_at"], 'ORDER BY "priority" ASC, "created_at" DESC', id="list"
        ),
    ],
)
def test_add_sorts(sorts, order) -> None:
    builder = QueryBuilder(table_name="Task")
    builder.add_sorts(sorts)
    assert builder.build_order_clause() == order


def test_empty_builder_emits_no_where_or_order() -> None:
    builder = QueryBuilder(table_name="Task")
    assert builder.build_where_clause() == ("", [])
    assert builder.build_order_clause() == ""


def test_pagination_bounds() -> None:
    builder = QueryBuilder(table_name="Task")
    builder.set_pagination(page=-1, page_size=10000)
    assert (builder.page, builder.page_size) == (1, 1000)
