"""
Query builder for advanced filtering and sorting.

Provides SQL generation for filter operators, sorting, and search.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any
from uuid import UUID


# Valid SQL identifier pattern (alphanumeric and underscore, not starting with digit)
_VALID_IDENTIFIER_PATTERN = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")


def validate_sql_identifier(name: str, context: str = "identifier") -> str:
    """
    Validate that a string is a safe SQL identifier.

    Args:
        name: The identifier to validate
        context: Description of what's being validated (for error messages)

    Returns:
        The validated name

    Raises:
        ValueError: If the name contains invalid characters
    """
    if not name:
        raise ValueError(f"SQL {context} cannot be empty")
    if not _VALID_IDENTIFIER_PATTERN.match(name):
        raise ValueError(
            f"Invalid SQL {context} '{name}': must contain only letters, digits, "
            "and underscores, and cannot start with a digit"
        )
    return name


class FilterOperator(str, Enum):
    """Supported filter operators."""

    EQ = "eq"  # Equal (default)
    NE = "ne"  # Not equal
    GT = "gt"  # Greater than
    GTE = "gte"  # Greater than or equal
    LT = "lt"  # Less than
    LTE = "lte"  # Less than or equal
    CONTAINS = "contains"  # Contains substring
    ICONTAINS = "icontains"  # Case-insensitive contains
    STARTSWITH = "startswith"  # Starts with
    ISTARTSWITH = "istartswith"  # Case-insensitive starts with
    ENDSWITH = "endswith"  # Ends with
    IENDSWITH = "iendswith"  # Case-insensitive ends with
    IN = "in"  # In list
    NOT_IN = "not_in"  # Not in list
    ISNULL = "isnull"  # Is null / is not null
    BETWEEN = "between"  # Between two values


# Operator mapping to SQL
OPERATOR_SQL: dict[FilterOperator, str] = {
    FilterOperator.EQ: "{field} = ?",
    FilterOperator.NE: "{field} != ?",
    FilterOperator.GT: "{field} > ?",
    FilterOperator.GTE: "{field} >= ?",
    FilterOperator.LT: "{field} < ?",
    FilterOperator.LTE: "{field} <= ?",
    FilterOperator.CONTAINS: "{field} LIKE ?",
    FilterOperator.ICONTAINS: "LOWER({field}) LIKE LOWER(?)",
    FilterOperator.STARTSWITH: "{field} LIKE ?",
    FilterOperator.ISTARTSWITH: "LOWER({field}) LIKE LOWER(?)",
    FilterOperator.ENDSWITH: "{field} LIKE ?",
    FilterOperator.IENDSWITH: "LOWER({field}) LIKE LOWER(?)",
    FilterOperator.IN: "{field} IN ({placeholders})",
    FilterOperator.NOT_IN: "{field} NOT IN ({placeholders})",
    FilterOperator.ISNULL: "{field} IS NULL",
    FilterOperator.BETWEEN: "{field} BETWEEN ? AND ?",
}


@dataclass
class FilterCondition:
    """A single filter condition."""

    field: str
    operator: FilterOperator
    value: Any
    relation_path: list[str] = field(default_factory=list)

    @classmethod
    def parse(cls, key: str, value: Any) -> FilterCondition:
        """
        Parse a filter key-value pair into a FilterCondition.

        Examples:
            - ("status", "active") -> FilterCondition(field="status", op=EQ, value="active")
            - ("created_at__gt", "2024-01-01") -> FilterCondition(field="created_at", op=GT, value="2024-01-01")
            - ("owner__name", "John") -> FilterCondition(field="name", op=EQ, value="John", relation_path=["owner"])
        """
        # Split by double underscore
        parts = key.split("__")

        # Check for operator suffix
        operator = FilterOperator.EQ
        field_parts = parts

        if len(parts) > 1:
            # Check if last part is an operator
            last_part = parts[-1].lower()
            try:
                operator = FilterOperator(last_part)
                field_parts = parts[:-1]
            except ValueError:
                # Not an operator, treat as field path
                pass

        # Build field name and relation path
        if len(field_parts) > 1:
            # Has relation path: owner__name -> relation_path=["owner"], field="name"
            relation_path = field_parts[:-1]
            field_name = field_parts[-1]
        else:
            relation_path = []
            field_name = field_parts[0]

        return cls(
            field=field_name,
            operator=operator,
            value=value,
            relation_path=relation_path,
        )

    def to_sql(self, table_alias: str | None = None) -> tuple[str, list[Any]]:
        """
        Convert condition to SQL fragment and parameters.

        Args:
            table_alias: Optional table alias for the field

        Returns:
            Tuple of (sql_fragment, parameters)
        """
        # Build field reference
        field_ref = f"{table_alias}.{self.field}" if table_alias else self.field

        # Convert value for SQL
        converted_value = self._convert_value(self.value)

        # Handle special operators
        if self.operator == FilterOperator.ISNULL:
            if self.value:
                return f"{field_ref} IS NULL", []
            else:
                return f"{field_ref} IS NOT NULL", []

        elif self.operator == FilterOperator.IN:
            if not isinstance(converted_value, (list, tuple)):
                converted_value = [converted_value]
            placeholders = ", ".join("?" * len(converted_value))
            sql = OPERATOR_SQL[self.operator].format(field=field_ref, placeholders=placeholders)
            return sql, list(converted_value)

        elif self.operator == FilterOperator.NOT_IN:
            if not isinstance(converted_value, (list, tuple)):
                converted_value = [converted_value]
            placeholders = ", ".join("?" * len(converted_value))
            sql = OPERATOR_SQL[self.operator].format(field=field_ref, placeholders=placeholders)
            return sql, list(converted_value)

        elif self.operator == FilterOperator.BETWEEN:
            if not isinstance(converted_value, (list, tuple)) or len(converted_value) != 2:
                raise ValueError("BETWEEN operator requires a list of two values")
            sql = OPERATOR_SQL[self.operator].format(field=field_ref)
            return sql, list(converted_value)

        elif self.operator in (
            FilterOperator.CONTAINS,
            FilterOperator.ICONTAINS,
        ):
            sql = OPERATOR_SQL[self.operator].format(field=field_ref)
            return sql, [f"%{converted_value}%"]

        elif self.operator in (
            FilterOperator.STARTSWITH,
            FilterOperator.ISTARTSWITH,
        ):
            sql = OPERATOR_SQL[self.operator].format(field=field_ref)
            return sql, [f"{converted_value}%"]

        elif self.operator in (
            FilterOperator.ENDSWITH,
            FilterOperator.IENDSWITH,
        ):
            sql = OPERATOR_SQL[self.operator].format(field=field_ref)
            return sql, [f"%{converted_value}"]

        else:
            # Standard operator
            sql = OPERATOR_SQL[self.operator].format(field=field_ref)
            return sql, [converted_value]

    def _convert_value(self, value: Any) -> Any:
        """Convert Python value to SQLite-compatible value."""
        if value is None:
            return None
        elif isinstance(value, UUID):
            return str(value)
        elif isinstance(value, datetime):
            return value.isoformat()
        elif isinstance(value, date):
            return value.isoformat()
        elif isinstance(value, Decimal):
            return float(value)
        elif isinstance(value, bool):
            return 1 if value else 0
        elif isinstance(value, (list, tuple)):
            return [self._convert_value(v) for v in value]
        else:
            return value


@dataclass
class SortField:
    """A single sort field."""

    field: str
    descending: bool = False
    relation_path: list[str] = field(default_factory=list)

    @classmethod
    def parse(cls, sort_str: str) -> SortField:
        """
        Parse a sort string into a SortField.

        Examples:
            - "created_at" -> SortField(field="created_at", desc=False)
            - "-created_at" -> SortField(field="created_at", desc=True)
            - "owner__name" -> SortField(field="name", relation_path=["owner"])
        """
        descending = sort_str.startswith("-")
        if descending:
            sort_str = sort_str[1:]

        parts = sort_str.split("__")
        if len(parts) > 1:
            return cls(
                field=parts[-1],
                descending=descending,
                relation_path=parts[:-1],
            )
        else:
            return cls(field=sort_str, descending=descending)

    def to_sql(self, table_alias: str | None = None) -> str:
        """Convert to SQL ORDER BY fragment."""
        field_ref = f"{table_alias}.{self.field}" if table_alias else self.field
        direction = "DESC" if self.descending else "ASC"
        return f"{field_ref} {direction}"


@dataclass
class QueryBuilder:
    """
    Builds SQL queries with filters, sorting, and pagination.

    Example:
        builder = QueryBuilder(table_name="Task")
        builder.add_filter("status", "active")
        builder.add_filter("priority__gte", 5)
        builder.add_sort("-created_at")
        builder.set_pagination(page=1, page_size=20)

        sql, params = builder.build_select()
    """

    table_name: str
    conditions: list[FilterCondition] = field(default_factory=list)
    sorts: list[SortField] = field(default_factory=list)
    page: int = 1
    page_size: int = 20
    select_fields: list[str] = field(default_factory=list)
    joins: list[str] = field(default_factory=list)
    search_query: str | None = None
    search_fields: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        """Validate table name on initialization."""
        validate_sql_identifier(self.table_name, "table name")

    def add_filter(self, key: str, value: Any) -> QueryBuilder:
        """Add a filter condition."""
        condition = FilterCondition.parse(key, value)
        self.conditions.append(condition)
        return self

    def add_filters(self, filters: dict[str, Any]) -> QueryBuilder:
        """Add multiple filter conditions."""
        for key, value in filters.items():
            self.add_filter(key, value)
        return self

    def add_sort(self, sort_str: str) -> QueryBuilder:
        """Add a sort field."""
        sort_field = SortField.parse(sort_str)
        self.sorts.append(sort_field)
        return self

    def add_sorts(self, sorts: str | list[str]) -> QueryBuilder:
        """Add multiple sort fields."""
        if isinstance(sorts, str):
            sorts = [sorts]
        for sort_str in sorts:
            self.add_sort(sort_str)
        return self

    def set_pagination(self, page: int, page_size: int) -> QueryBuilder:
        """Set pagination parameters."""
        self.page = max(1, page)
        self.page_size = max(1, min(page_size, 1000))  # Cap at 1000
        return self

    def set_search(self, query: str, fields: list[str] | None = None) -> QueryBuilder:
        """Set full-text search query."""
        self.search_query = query
        self.search_fields = fields or []
        return self

    def build_where_clause(self) -> tuple[str, list[Any]]:
        """
        Build the WHERE clause from conditions.

        Returns:
            Tuple of (where_clause, parameters)
        """
        if not self.conditions:
            return "", []

        fragments = []
        params = []

        for condition in self.conditions:
            sql, condition_params = condition.to_sql()
            fragments.append(sql)
            params.extend(condition_params)

        where_clause = " AND ".join(fragments)
        return f"WHERE {where_clause}", params

    def build_order_clause(self) -> str:
        """Build the ORDER BY clause."""
        if not self.sorts:
            return ""

        order_parts = [sort.to_sql() for sort in self.sorts]
        return f"ORDER BY {', '.join(order_parts)}"

    def build_limit_offset(self) -> tuple[str, list[int]]:
        """Build LIMIT/OFFSET clause."""
        offset = (self.page - 1) * self.page_size
        return "LIMIT ? OFFSET ?", [self.page_size, offset]

    def build_select(self, count_only: bool = False) -> tuple[str, list[Any]]:
        """
        Build complete SELECT query.

        Args:
            count_only: If True, build COUNT(*) query instead

        Returns:
            Tuple of (sql, parameters)
        """
        params: list[Any] = []

        # SELECT clause
        if count_only:
            select = f"SELECT COUNT(*) FROM {self.table_name}"
        else:
            fields = ", ".join(self.select_fields) if self.select_fields else "*"
            select = f"SELECT {fields} FROM {self.table_name}"

        # WHERE clause
        where_clause, where_params = self.build_where_clause()
        params.extend(where_params)

        # Build query
        query_parts = [select]
        if where_clause:
            query_parts.append(where_clause)

        if not count_only:
            # ORDER BY
            order_clause = self.build_order_clause()
            if order_clause:
                query_parts.append(order_clause)

            # LIMIT/OFFSET
            limit_clause, limit_params = self.build_limit_offset()
            query_parts.append(limit_clause)
            params.extend(limit_params)

        return " ".join(query_parts), params

    def build_count(self) -> tuple[str, list[Any]]:
        """Build COUNT query."""
        return self.build_select(count_only=True)


# =============================================================================
# Filter Parser Utilities
# =============================================================================


def parse_filter_string(filter_str: str) -> dict[str, Any]:
    """
    Parse a filter string into a filters dict.

    Format: "field1=value1,field2__op=value2"

    Examples:
        "status=active" -> {"status": "active"}
        "status=active,priority__gte=5" -> {"status": "active", "priority__gte": 5}
    """
    if not filter_str:
        return {}

    filters = {}
    pairs = filter_str.split(",")

    for pair in pairs:
        if "=" not in pair:
            continue

        key, value = pair.split("=", 1)
        key = key.strip()
        value = value.strip()

        # Try to parse value type
        filters[key] = _parse_value(value)

    return filters


def _parse_value(value: str) -> Any:
    """Parse a string value to appropriate Python type."""
    # Boolean
    if value.lower() in ("true", "yes", "1"):
        return True
    if value.lower() in ("false", "no", "0"):
        return False

    # None
    if value.lower() in ("null", "none"):
        return None

    # Integer
    try:
        return int(value)
    except ValueError:
        pass

    # Float
    try:
        return float(value)
    except ValueError:
        pass

    # List (comma-separated in brackets)
    if value.startswith("[") and value.endswith("]"):
        inner = value[1:-1]
        return [_parse_value(v.strip()) for v in inner.split(",")]

    # UUID
    uuid_pattern = re.compile(
        r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I
    )
    if uuid_pattern.match(value):
        return UUID(value)

    # String
    return value


def parse_sort_string(sort_str: str) -> list[str]:
    """
    Parse a sort string into a list of sort fields.

    Format: "field1,-field2" (comma-separated, - for descending)
    """
    if not sort_str:
        return []

    return [s.strip() for s in sort_str.split(",") if s.strip()]
