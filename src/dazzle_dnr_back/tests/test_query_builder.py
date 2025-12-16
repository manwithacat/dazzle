"""
Tests for query builder.

Tests filter parsing, SQL generation, and sorting.
"""

from uuid import UUID

import pytest

from dazzle_dnr_back.runtime.query_builder import (
    FilterCondition,
    FilterOperator,
    QueryBuilder,
    SortField,
    parse_filter_string,
    parse_sort_string,
)

# =============================================================================
# FilterCondition Tests
# =============================================================================


class TestFilterCondition:
    """Tests for FilterCondition parsing and SQL generation."""

    def test_parse_simple_equality(self):
        """Test parsing simple equality filter."""
        cond = FilterCondition.parse("status", "active")

        assert cond.field == "status"
        assert cond.operator == FilterOperator.EQ
        assert cond.value == "active"
        assert cond.relation_path == []

    def test_parse_gt_operator(self):
        """Test parsing greater than operator."""
        cond = FilterCondition.parse("priority__gt", 5)

        assert cond.field == "priority"
        assert cond.operator == FilterOperator.GT
        assert cond.value == 5

    def test_parse_gte_operator(self):
        """Test parsing greater than or equal operator."""
        cond = FilterCondition.parse("count__gte", 10)

        assert cond.field == "count"
        assert cond.operator == FilterOperator.GTE
        assert cond.value == 10

    def test_parse_lt_operator(self):
        """Test parsing less than operator."""
        cond = FilterCondition.parse("age__lt", 30)

        assert cond.field == "age"
        assert cond.operator == FilterOperator.LT
        assert cond.value == 30

    def test_parse_lte_operator(self):
        """Test parsing less than or equal operator."""
        cond = FilterCondition.parse("score__lte", 100)

        assert cond.field == "score"
        assert cond.operator == FilterOperator.LTE
        assert cond.value == 100

    def test_parse_ne_operator(self):
        """Test parsing not equal operator."""
        cond = FilterCondition.parse("status__ne", "deleted")

        assert cond.field == "status"
        assert cond.operator == FilterOperator.NE
        assert cond.value == "deleted"

    def test_parse_contains_operator(self):
        """Test parsing contains operator."""
        cond = FilterCondition.parse("title__contains", "urgent")

        assert cond.field == "title"
        assert cond.operator == FilterOperator.CONTAINS
        assert cond.value == "urgent"

    def test_parse_icontains_operator(self):
        """Test parsing case-insensitive contains operator."""
        cond = FilterCondition.parse("title__icontains", "URGENT")

        assert cond.field == "title"
        assert cond.operator == FilterOperator.ICONTAINS
        assert cond.value == "URGENT"

    def test_parse_startswith_operator(self):
        """Test parsing starts with operator."""
        cond = FilterCondition.parse("name__startswith", "Bug:")

        assert cond.field == "name"
        assert cond.operator == FilterOperator.STARTSWITH
        assert cond.value == "Bug:"

    def test_parse_endswith_operator(self):
        """Test parsing ends with operator."""
        cond = FilterCondition.parse("email__endswith", "@example.com")

        assert cond.field == "email"
        assert cond.operator == FilterOperator.ENDSWITH
        assert cond.value == "@example.com"

    def test_parse_in_operator(self):
        """Test parsing in operator."""
        cond = FilterCondition.parse("status__in", ["active", "pending"])

        assert cond.field == "status"
        assert cond.operator == FilterOperator.IN
        assert cond.value == ["active", "pending"]

    def test_parse_not_in_operator(self):
        """Test parsing not in operator."""
        cond = FilterCondition.parse("status__not_in", ["deleted", "archived"])

        assert cond.field == "status"
        assert cond.operator == FilterOperator.NOT_IN
        assert cond.value == ["deleted", "archived"]

    def test_parse_isnull_operator(self):
        """Test parsing is null operator."""
        cond = FilterCondition.parse("deleted_at__isnull", True)

        assert cond.field == "deleted_at"
        assert cond.operator == FilterOperator.ISNULL
        assert cond.value is True

    def test_parse_relation_filter(self):
        """Test parsing relation filter."""
        cond = FilterCondition.parse("owner__name", "John")

        assert cond.field == "name"
        assert cond.operator == FilterOperator.EQ
        assert cond.value == "John"
        assert cond.relation_path == ["owner"]

    def test_parse_deep_relation_filter(self):
        """Test parsing deep relation filter."""
        cond = FilterCondition.parse("owner__department__name__contains", "Sales")

        assert cond.field == "name"
        assert cond.operator == FilterOperator.CONTAINS
        assert cond.value == "Sales"
        assert cond.relation_path == ["owner", "department"]

    def test_to_sql_equality(self):
        """Test SQL generation for equality."""
        cond = FilterCondition(field="status", operator=FilterOperator.EQ, value="active")
        sql, params = cond.to_sql()

        assert sql == '"status" = ?'
        assert params == ["active"]

    def test_to_sql_contains(self):
        """Test SQL generation for contains."""
        cond = FilterCondition(field="title", operator=FilterOperator.CONTAINS, value="urgent")
        sql, params = cond.to_sql()

        assert sql == '"title" LIKE ?'
        assert params == ["%urgent%"]

    def test_to_sql_startswith(self):
        """Test SQL generation for starts with."""
        cond = FilterCondition(field="name", operator=FilterOperator.STARTSWITH, value="Bug:")
        sql, params = cond.to_sql()

        assert sql == '"name" LIKE ?'
        assert params == ["Bug:%"]

    def test_to_sql_endswith(self):
        """Test SQL generation for ends with."""
        cond = FilterCondition(field="email", operator=FilterOperator.ENDSWITH, value="@test.com")
        sql, params = cond.to_sql()

        assert sql == '"email" LIKE ?'
        assert params == ["%@test.com"]

    def test_to_sql_in(self):
        """Test SQL generation for in."""
        cond = FilterCondition(field="status", operator=FilterOperator.IN, value=["a", "b", "c"])
        sql, params = cond.to_sql()

        assert sql == '"status" IN (?, ?, ?)'
        assert params == ["a", "b", "c"]

    def test_to_sql_isnull_true(self):
        """Test SQL generation for is null."""
        cond = FilterCondition(field="deleted_at", operator=FilterOperator.ISNULL, value=True)
        sql, params = cond.to_sql()

        assert sql == '"deleted_at" IS NULL'
        assert params == []

    def test_to_sql_isnull_false(self):
        """Test SQL generation for is not null."""
        cond = FilterCondition(field="deleted_at", operator=FilterOperator.ISNULL, value=False)
        sql, params = cond.to_sql()

        assert sql == '"deleted_at" IS NOT NULL'
        assert params == []

    def test_to_sql_with_table_alias(self):
        """Test SQL generation with table alias."""
        cond = FilterCondition(field="status", operator=FilterOperator.EQ, value="active")
        sql, params = cond.to_sql(table_alias="t")

        assert sql == 't."status" = ?'
        assert params == ["active"]

    def test_to_sql_uuid_conversion(self):
        """Test UUID value conversion."""
        uuid_val = UUID("12345678-1234-5678-1234-567812345678")
        cond = FilterCondition(field="user_id", operator=FilterOperator.EQ, value=uuid_val)
        sql, params = cond.to_sql()

        assert sql == '"user_id" = ?'
        assert params == [str(uuid_val)]


# =============================================================================
# SortField Tests
# =============================================================================


class TestSortField:
    """Tests for SortField parsing and SQL generation."""

    def test_parse_ascending(self):
        """Test parsing ascending sort."""
        sort = SortField.parse("created_at")

        assert sort.field == "created_at"
        assert sort.descending is False
        assert sort.relation_path == []

    def test_parse_descending(self):
        """Test parsing descending sort."""
        sort = SortField.parse("-created_at")

        assert sort.field == "created_at"
        assert sort.descending is True
        assert sort.relation_path == []

    def test_parse_relation_sort(self):
        """Test parsing relation sort."""
        sort = SortField.parse("owner__name")

        assert sort.field == "name"
        assert sort.descending is False
        assert sort.relation_path == ["owner"]

    def test_parse_relation_descending(self):
        """Test parsing descending relation sort."""
        sort = SortField.parse("-owner__name")

        assert sort.field == "name"
        assert sort.descending is True
        assert sort.relation_path == ["owner"]

    def test_to_sql_ascending(self):
        """Test SQL generation for ascending sort."""
        sort = SortField(field="created_at", descending=False)
        sql = sort.to_sql()

        assert sql == '"created_at" ASC'

    def test_to_sql_descending(self):
        """Test SQL generation for descending sort."""
        sort = SortField(field="created_at", descending=True)
        sql = sort.to_sql()

        assert sql == '"created_at" DESC'

    def test_to_sql_with_alias(self):
        """Test SQL generation with table alias."""
        sort = SortField(field="name", descending=True)
        sql = sort.to_sql(table_alias="t")

        assert sql == 't."name" DESC'


# =============================================================================
# QueryBuilder Tests
# =============================================================================


class TestQueryBuilder:
    """Tests for QueryBuilder."""

    def test_simple_select(self):
        """Test simple select without filters."""
        builder = QueryBuilder(table_name="Task")
        sql, params = builder.build_select()

        assert 'SELECT * FROM "Task"' in sql
        assert "LIMIT" in sql
        assert "OFFSET" in sql

    def test_with_filters(self):
        """Test select with filters."""
        builder = QueryBuilder(table_name="Task")
        builder.add_filter("status", "active")
        builder.add_filter("priority__gte", 5)

        sql, params = builder.build_select()

        assert "WHERE" in sql
        assert '"status" = ?' in sql
        assert '"priority" >= ?' in sql
        assert "active" in params
        assert 5 in params

    def test_with_sorting(self):
        """Test select with sorting."""
        builder = QueryBuilder(table_name="Task")
        builder.add_sort("-created_at")
        builder.add_sort("priority")

        sql, params = builder.build_select()

        assert "ORDER BY" in sql
        assert '"created_at" DESC' in sql
        assert '"priority" ASC' in sql

    def test_with_pagination(self):
        """Test pagination."""
        builder = QueryBuilder(table_name="Task")
        builder.set_pagination(page=3, page_size=10)

        sql, params = builder.build_select()

        assert "LIMIT ? OFFSET ?" in sql
        assert 10 in params  # page_size
        assert 20 in params  # offset = (3-1) * 10

    def test_count_query(self):
        """Test count query generation."""
        builder = QueryBuilder(table_name="Task")
        builder.add_filter("status", "active")

        sql, params = builder.build_count()

        assert 'SELECT COUNT(*) FROM "Task"' in sql
        assert "WHERE" in sql
        assert "LIMIT" not in sql
        assert "ORDER BY" not in sql

    def test_add_filters_dict(self):
        """Test adding multiple filters from dict."""
        builder = QueryBuilder(table_name="Task")
        builder.add_filters(
            {
                "status": "active",
                "priority__gte": 5,
                "title__contains": "bug",
            }
        )

        assert len(builder.conditions) == 3

    def test_add_sorts_string(self):
        """Test adding sorts from string."""
        builder = QueryBuilder(table_name="Task")
        builder.add_sorts("-created_at")

        assert len(builder.sorts) == 1
        assert builder.sorts[0].descending is True

    def test_add_sorts_list(self):
        """Test adding sorts from list."""
        builder = QueryBuilder(table_name="Task")
        builder.add_sorts(["priority", "-created_at"])

        assert len(builder.sorts) == 2

    def test_pagination_bounds(self):
        """Test pagination bounds enforcement."""
        builder = QueryBuilder(table_name="Task")
        builder.set_pagination(page=-1, page_size=10000)

        assert builder.page == 1  # Min page is 1
        assert builder.page_size == 1000  # Max is 1000


# =============================================================================
# Parse Functions Tests
# =============================================================================


class TestParseFunctions:
    """Tests for filter and sort parsing functions."""

    def test_parse_filter_string_simple(self):
        """Test parsing simple filter string."""
        filters = parse_filter_string("status=active")

        assert filters == {"status": "active"}

    def test_parse_filter_string_multiple(self):
        """Test parsing multiple filters."""
        filters = parse_filter_string("status=active,priority=5")

        assert filters["status"] == "active"
        assert filters["priority"] == 5

    def test_parse_filter_string_with_operators(self):
        """Test parsing filters with operators."""
        filters = parse_filter_string("priority__gte=5,status__ne=deleted")

        assert filters["priority__gte"] == 5
        assert filters["status__ne"] == "deleted"

    def test_parse_filter_string_boolean(self):
        """Test parsing boolean values."""
        filters = parse_filter_string("active=true,deleted=false")

        assert filters["active"] is True
        assert filters["deleted"] is False

    def test_parse_filter_string_null(self):
        """Test parsing null values."""
        filters = parse_filter_string("deleted_at=null")

        assert filters["deleted_at"] is None

    def test_parse_filter_string_list(self):
        """Test parsing list values."""
        # Note: Current implementation splits on comma first, so list parsing
        # is limited. For complex lists, use the API directly.
        # This tests what the current simple parser can handle.
        from dazzle_dnr_back.runtime.query_builder import _parse_value

        # Direct value parsing works
        result = _parse_value("[active,pending,review]")
        assert result == ["active", "pending", "review"]

    def test_parse_filter_string_uuid(self):
        """Test parsing UUID values."""
        filters = parse_filter_string("id=12345678-1234-5678-1234-567812345678")

        assert isinstance(filters["id"], UUID)

    def test_parse_filter_string_empty(self):
        """Test parsing empty string."""
        filters = parse_filter_string("")

        assert filters == {}

    def test_parse_sort_string_simple(self):
        """Test parsing simple sort string."""
        sorts = parse_sort_string("created_at")

        assert sorts == ["created_at"]

    def test_parse_sort_string_multiple(self):
        """Test parsing multiple sorts."""
        sorts = parse_sort_string("priority,-created_at")

        assert sorts == ["priority", "-created_at"]

    def test_parse_sort_string_empty(self):
        """Test parsing empty sort string."""
        sorts = parse_sort_string("")

        assert sorts == []


# =============================================================================
# Edge Cases
# =============================================================================


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_unknown_operator_treated_as_field(self):
        """Test unknown operator is treated as field path."""
        cond = FilterCondition.parse("owner__unknown_field", "value")

        # "unknown_field" is not an operator, so it's treated as a field
        assert cond.field == "unknown_field"
        assert cond.relation_path == ["owner"]
        assert cond.operator == FilterOperator.EQ

    def test_empty_filters(self):
        """Test builder with no filters."""
        builder = QueryBuilder(table_name="Task")
        where, params = builder.build_where_clause()

        assert where == ""
        assert params == []

    def test_empty_sorts(self):
        """Test builder with no sorts."""
        builder = QueryBuilder(table_name="Task")
        order = builder.build_order_clause()

        assert order == ""

    def test_between_operator(self):
        """Test between operator with two values."""
        cond = FilterCondition(
            field="created_at",
            operator=FilterOperator.BETWEEN,
            value=["2024-01-01", "2024-12-31"],
        )
        sql, params = cond.to_sql()

        assert sql == '"created_at" BETWEEN ? AND ?'
        assert params == ["2024-01-01", "2024-12-31"]

    def test_between_operator_invalid_value(self):
        """Test between operator with invalid value."""
        cond = FilterCondition(
            field="created_at",
            operator=FilterOperator.BETWEEN,
            value="single_value",
        )

        with pytest.raises(ValueError, match="BETWEEN operator requires"):
            cond.to_sql()
