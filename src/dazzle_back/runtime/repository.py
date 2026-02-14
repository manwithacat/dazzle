"""
Repository — provides persistence layer for DNR Backend.

This module implements the repository pattern for PostgreSQL database access.
Provides CRUD operations with advanced filtering, sorting, pagination,
and relation loading.
"""

from __future__ import annotations

import json
import re
import time
from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any, Generic, TypeAlias, TypeVar
from uuid import UUID

from pydantic import BaseModel

from dazzle_back.runtime.query_builder import quote_identifier
from dazzle_back.specs.entity import (
    ComputedFieldSpec,
    EntitySpec,
    FieldType,
    ScalarType,
)

# Build a tuple of IntegrityError types for PostgreSQL.
_INTEGRITY_ERRORS: tuple[type[Exception], ...] = ()
try:
    from psycopg import errors as _psycopg_errors

    _INTEGRITY_ERRORS = (_psycopg_errors.IntegrityError,)
except ImportError:
    pass

# =============================================================================
# Constraint Violation Error
# =============================================================================


class ConstraintViolationError(Exception):
    """Raised when a database constraint (unique, FK) is violated."""

    def __init__(
        self,
        message: str,
        field: str | None = None,
        constraint_type: str = "integrity",
    ):
        self.field = field
        self.constraint_type = constraint_type  # "unique" | "foreign_key"
        super().__init__(message)


def _parse_constraint_error(exc: str | Exception, table_name: str) -> tuple[str, str | None]:
    """Parse a constraint error message to extract type and field.

    Accepts either a string or an exception object. For psycopg exceptions,
    uses ``pgerror`` and ``diag.detail`` to extract field-level information
    that may not appear in ``str(exc)``.

    Returns:
        (constraint_type, field_name_or_none)
    """
    # Extract the fullest error text available
    if isinstance(exc, str):
        err = exc
        detail = ""
    else:
        err = getattr(exc, "pgerror", None) or str(exc)
        detail = getattr(getattr(exc, "diag", None), "detail", None) or ""

    # Combine err + detail for matching
    full_text = f"{err} {detail}".strip()

    # PostgreSQL: "duplicate key value violates unique constraint"
    if "duplicate key" in full_text and "unique constraint" in full_text:
        # Try to extract column from detail: Key (slug)=(value)
        detail_match = re.search(r"Key \((\w+)\)", full_text)
        pg_field: str | None = detail_match.group(1) if detail_match else None
        return "unique", pg_field

    # PostgreSQL: "violates foreign key constraint"
    if "foreign key constraint" in full_text:
        # Extract field from DETAIL: Key (assigned_to)=(uuid) is not present in table "User"
        fk_match = re.search(r"Key \((\w+)\)", full_text)
        fk_field: str | None = fk_match.group(1) if fk_match else None
        return "foreign_key", fk_field

    # Legacy SQLite patterns (kept for _parse_constraint_error string-based callers)
    if "UNIQUE constraint failed:" in err:
        parts = err.split("UNIQUE constraint failed:")[-1].strip()
        field_name = parts.split(".")[-1].strip() if parts else None
        return "unique", field_name or None

    if "FOREIGN KEY constraint failed" in err:
        return "foreign_key", None

    return "integrity", None


# Alias to prevent mypy resolving `list` as Repository.list inside the class
_list = list

if TYPE_CHECKING:
    from dazzle_back.metrics.system_collector import SystemMetricsCollector
    from dazzle_back.runtime.relation_loader import RelationLoader


# =============================================================================
# Type Variables
# =============================================================================

T = TypeVar("T", bound=BaseModel)


# =============================================================================
# Database Value Conversion (PostgreSQL)
# =============================================================================


def _db_to_python(value: Any, field_type: FieldType | None = None) -> Any:
    """Convert database value to Python type based on field type.

    PostgreSQL with dict_row returns most types correctly, but JSON fields
    come back as strings and UUIDs/dates may need conversion depending on
    column type.
    """
    if value is None:
        return None
    if field_type is None:
        return value

    if field_type.kind == "scalar" and field_type.scalar_type:
        scalar = field_type.scalar_type
        if scalar == ScalarType.UUID:
            return UUID(value) if value and not isinstance(value, UUID) else value
        elif scalar == ScalarType.DATETIME:
            if isinstance(value, datetime):
                return value
            return datetime.fromisoformat(value) if value else None
        elif scalar == ScalarType.DATE:
            if isinstance(value, date):
                return value
            return date.fromisoformat(value) if value else None
        elif scalar == ScalarType.DECIMAL:
            return Decimal(str(value)) if value is not None else None
        elif scalar == ScalarType.BOOL:
            return bool(value)
        elif scalar == ScalarType.JSON:
            if isinstance(value, (dict, list)):
                return value
            return json.loads(value) if value else None
        else:
            return value
    elif field_type.kind == "ref":
        return UUID(value) if value and not isinstance(value, UUID) else value
    else:
        return value


# =============================================================================
# Repository
# =============================================================================


class Repository(Generic[T]):
    """
    Repository for a single entity type.

    Provides CRUD operations against PostgreSQL database.
    Supports advanced filtering, sorting, and relation loading.
    Optionally collects query metrics for observability.
    """

    def __init__(
        self,
        db_manager: Any,
        entity_spec: EntitySpec,
        model_class: type[T],
        relation_loader: RelationLoader | None = None,
        metrics_collector: SystemMetricsCollector | None = None,
    ):
        """
        Initialize the repository.

        Args:
            db_manager: Database backend instance (PostgresBackend)
            entity_spec: Entity specification
            model_class: Pydantic model class for the entity
            relation_loader: Optional relation loader for nested data fetching
            metrics_collector: Optional system metrics collector for query timing
        """
        self.db = db_manager
        self.entity_spec = entity_spec
        self.model_class = model_class
        self.table_name = entity_spec.name
        self._relation_loader = relation_loader
        self._metrics = metrics_collector

        # Build field type lookup for conversions
        self._field_types: dict[str, FieldType] = {f.name: f.type for f in entity_spec.fields}

        # Store computed field specs for evaluation
        self._computed_fields: list[ComputedFieldSpec] = entity_spec.computed_fields or []

    def _record_query(self, query_type: str, latency_ms: float, rows: int = 0) -> None:
        """Record a database query metric."""
        if self._metrics:
            self._metrics.record_db_query(
                query_type=query_type,
                table=self.table_name,
                latency_ms=latency_ms,
                rows_affected=rows,
            )

    def _python_to_db(self, value: Any, field_type: FieldType | None = None) -> Any:
        """Convert a Python value for PostgreSQL storage."""
        from dazzle_back.runtime.pg_backend import _python_to_postgres

        return _python_to_postgres(value, field_type)

    def _model_to_row(self, model: T) -> dict[str, Any]:
        """Convert Pydantic model to row dict for the database."""
        data = model.model_dump()
        return {k: self._python_to_db(v, self._field_types.get(k)) for k, v in data.items()}

    def _row_to_model(self, row: Any) -> T:
        """Convert database row to Pydantic model."""
        data = dict(row)
        converted = {k: _db_to_python(v, self._field_types.get(k)) for k, v in data.items()}
        return self.model_class(**converted)

    async def create(self, data: dict[str, Any]) -> T:
        """
        Create a new entity.

        Args:
            data: Entity data (including id)

        Returns:
            Created entity
        """
        # Convert values for database backend
        db_data = {k: self._python_to_db(v, self._field_types.get(k)) for k, v in data.items()}

        columns = ", ".join(quote_identifier(k) for k in db_data.keys())
        ph = self.db.placeholder
        placeholders = ", ".join(ph for _ in db_data)
        values = list(db_data.values())

        table = quote_identifier(self.table_name)
        sql = f"INSERT INTO {table} ({columns}) VALUES ({placeholders})"

        start = time.perf_counter()
        try:
            with self.db.connection() as conn:
                cursor = conn.cursor()
                cursor.execute(sql, values)
        except _INTEGRITY_ERRORS as exc:
            ctype, field = _parse_constraint_error(exc, self.table_name)
            if ctype == "unique":
                msg = (
                    f"A {self.table_name} with this {field} already exists"
                    if field
                    else f"Duplicate value violates unique constraint on {self.table_name}"
                )
            elif ctype == "foreign_key":
                msg = (
                    f"Referenced record not found for field '{field}' on {self.table_name}"
                    if field
                    else f"Referenced record does not exist for {self.table_name}"
                )
            else:
                msg = f"Integrity constraint violated on {self.table_name}: {exc}"
            raise ConstraintViolationError(msg, field=field, constraint_type=ctype) from exc
        latency_ms = (time.perf_counter() - start) * 1000
        self._record_query("insert", latency_ms, rows=1)

        return self.model_class(**data)

    async def read(
        self,
        id: UUID,
        include: list[str] | None = None,
    ) -> T | dict[str, Any] | None:
        """
        Read an entity by ID.

        Args:
            id: Entity ID
            include: List of relation names to include (nested loading)

        Returns:
            Entity (or dict with nested data if include specified), or None if not found
        """
        table = quote_identifier(self.table_name)
        ph = self.db.placeholder
        sql = f'SELECT * FROM {table} WHERE "id" = {ph}'

        start = time.perf_counter()
        with self.db.connection() as conn:
            cursor = conn.cursor()
            cursor.execute(sql, (str(id),))
            row = cursor.fetchone()
        latency_ms = (time.perf_counter() - start) * 1000
        self._record_query("select", latency_ms, rows=1 if row else 0)

        if not row:
            return None

        # If relations requested, load them and return dict
        if include and self._relation_loader:
            row_dict = dict(row)
            row_dicts = self._relation_loader.load_relations(
                self.entity_spec.name,
                [row_dict],
                include,
                conn=self.db.get_persistent_connection(),
            )
            return self._convert_row_dict(row_dicts[0])

        # If computed fields, return dict with computed values
        if self._computed_fields:
            return self._convert_row_dict(dict(row))

        return self._row_to_model(row)

    async def update(self, id: UUID, data: dict[str, Any]) -> T | dict[str, Any] | None:
        """
        Update an existing entity.

        Args:
            id: Entity ID
            data: Fields to update (only non-None values)

        Returns:
            Updated entity or None if not found
        """
        # Filter out None values
        update_data = {k: v for k, v in data.items() if v is not None}

        if not update_data:
            return await self.read(id)

        # Convert values for database backend
        db_data = {
            k: self._python_to_db(v, self._field_types.get(k)) for k, v in update_data.items()
        }

        ph = self.db.placeholder
        set_clause = ", ".join(f"{quote_identifier(k)} = {ph}" for k in db_data.keys())
        values = list(db_data.values())
        values.append(str(id))

        table = quote_identifier(self.table_name)
        sql = f'UPDATE {table} SET {set_clause} WHERE "id" = {ph}'

        start = time.perf_counter()
        try:
            with self.db.connection() as conn:
                cursor = conn.cursor()
                cursor.execute(sql, values)
                rowcount = cursor.rowcount
        except _INTEGRITY_ERRORS as exc:
            ctype, field = _parse_constraint_error(exc, self.table_name)
            if ctype == "unique":
                msg = (
                    f"A {self.table_name} with this {field} already exists"
                    if field
                    else f"Duplicate value violates unique constraint on {self.table_name}"
                )
            elif ctype == "foreign_key":
                msg = (
                    f"Referenced record not found for field '{field}' on {self.table_name}"
                    if field
                    else f"Referenced record does not exist for {self.table_name}"
                )
            else:
                msg = f"Integrity constraint violated on {self.table_name}: {exc}"
            raise ConstraintViolationError(msg, field=field, constraint_type=ctype) from exc
        latency_ms = (time.perf_counter() - start) * 1000
        self._record_query("update", latency_ms, rows=rowcount)

        if rowcount == 0:
            return None

        return await self.read(id)

    async def delete(self, id: UUID) -> bool:
        """
        Delete an entity by ID.

        Args:
            id: Entity ID

        Returns:
            True if deleted, False if not found
        """
        table = quote_identifier(self.table_name)
        ph = self.db.placeholder
        sql = f'DELETE FROM {table} WHERE "id" = {ph}'

        start = time.perf_counter()
        with self.db.connection() as conn:
            cursor = conn.cursor()
            cursor.execute(sql, (str(id),))
            rowcount = cursor.rowcount
        latency_ms = (time.perf_counter() - start) * 1000
        self._record_query("delete", latency_ms, rows=rowcount)

        return bool(rowcount and rowcount > 0)

    async def list(
        self,
        page: int = 1,
        page_size: int = 20,
        filters: dict[str, Any] | None = None,
        sort: str | list[str] | None = None,
        include: list[str] | None = None,
        search: str | None = None,
        select_fields: list[str] | None = None,
    ) -> dict[str, Any]:
        """
        List entities with pagination, filtering, sorting, and relation loading.

        Args:
            page: Page number (1-indexed)
            page_size: Items per page
            filters: Optional filter criteria (supports advanced operators)
                    Examples:
                    - {"status": "active"} - equality
                    - {"priority__gte": 5} - greater than or equal
                    - {"title__contains": "urgent"} - substring match
                    - {"status__in": ["active", "pending"]} - in list
            sort: Sort field(s), prefix with - for descending
                  Examples: "created_at", "-priority", ["priority", "-created_at"]
            include: List of relation names to include (nested loading)
            search: Full-text search query (if FTS is enabled)

        Returns:
            Dictionary with items, total, page, and page_size
        """
        from dazzle_back.runtime.query_builder import QueryBuilder

        # Build query using QueryBuilder
        builder = QueryBuilder(table_name=self.table_name, placeholder_style=self.db.placeholder)
        if select_fields:
            builder.select_fields = list(select_fields)
        builder.set_pagination(page, page_size)

        if filters:
            builder.add_filters(filters)

        if sort:
            builder.add_sorts(sort)

        if search:
            builder.set_search(search)

        # Get total count
        count_sql, count_params = builder.build_count()

        start = time.perf_counter()
        with self.db.connection() as conn:
            cursor = conn.cursor()
            cursor.execute(count_sql, count_params)
            row = cursor.fetchone()
            total = row[0] if isinstance(row, (tuple, list)) else next(iter(row.values()))
        latency_ms = (time.perf_counter() - start) * 1000
        self._record_query("count", latency_ms)

        # Get paginated items
        items_sql, items_params = builder.build_select()

        start = time.perf_counter()
        with self.db.connection() as conn:
            cursor = conn.cursor()
            cursor.execute(items_sql, items_params)
            rows = cursor.fetchall()
        latency_ms = (time.perf_counter() - start) * 1000
        self._record_query("select", latency_ms, rows=len(rows))

        # Convert to dicts first for relation loading
        row_dicts = [dict(row) for row in rows]

        # Load relations if requested
        if include and self._relation_loader:
            row_dicts = self._relation_loader.load_relations(
                self.entity_spec.name,
                row_dicts,
                include,
                conn=self.db.get_persistent_connection(),
            )

        # Convert to models (or return dicts if relations/computed fields included)
        items: list[Any]
        if include or self._computed_fields:
            # Return dicts with nested data and/or computed fields
            items = [self._convert_row_dict(row) for row in row_dicts]
        else:
            items = [self._row_to_model(row) for row in rows]

        return {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    def _convert_row_dict(
        self,
        row: dict[str, Any],
        related_data: dict[str, _list[dict[str, Any]]] | None = None,
    ) -> dict[str, Any]:
        """Convert a row dict with proper type conversions and computed fields."""
        result: dict[str, Any] = {}
        collected_relations: dict[str, _list[dict[str, Any]]] = {}

        for k, v in row.items():
            if isinstance(v, dict):
                # Nested relation - convert recursively
                result[k] = self._convert_row_dict(v) if v else None
            elif isinstance(v, list):
                # To-many relation
                result[k] = [self._convert_row_dict(item) for item in v]
                # Store for computed field evaluation
                collected_relations[k] = [
                    dict(item) if isinstance(item, dict) else item for item in v
                ]
            else:
                # Regular field
                result[k] = _db_to_python(v, self._field_types.get(k))

        # Add computed fields
        if self._computed_fields:
            from dazzle_back.runtime.computed_evaluator import (
                evaluate_computed_fields,
            )

            # Use collected relations or provided related_data
            rel_data = related_data if related_data is not None else collected_relations
            computed_values = evaluate_computed_fields(result, self._computed_fields, rel_data)
            result.update(computed_values)

        return result

    async def exists(self, id: UUID) -> bool:
        """Check if an entity exists."""
        table = quote_identifier(self.table_name)
        ph = self.db.placeholder
        sql = f'SELECT 1 FROM {table} WHERE "id" = {ph} LIMIT 1'

        start = time.perf_counter()
        with self.db.connection() as conn:
            cursor = conn.cursor()
            cursor.execute(sql, (str(id),))
            result = cursor.fetchone()
        latency_ms = (time.perf_counter() - start) * 1000
        self._record_query("select", latency_ms, rows=1 if result else 0)

        return result is not None


# Backward-compatible aliases
SQLiteRepository = Repository
"""Deprecated alias for :class:`Repository`. Use ``Repository`` directly."""

try:
    from dazzle_back.runtime.pg_backend import PostgresBackend

    DatabaseManager: TypeAlias = PostgresBackend
except ImportError:
    PostgresBackend = None  # type: ignore[assignment,misc]
    DatabaseManager: TypeAlias = Any  # type: ignore[no-redef,misc]
"""Deprecated — use :class:`~dazzle_back.runtime.pg_backend.PostgresBackend`."""


# =============================================================================
# Repository Factory
# =============================================================================


class RepositoryFactory:
    """
    Factory for creating repositories from entity specifications.
    """

    def __init__(
        self,
        db_manager: Any,
        models: dict[str, type[BaseModel]],
        relation_loader: RelationLoader | None = None,
        metrics_collector: SystemMetricsCollector | None = None,
    ):
        """
        Initialize the factory.

        Args:
            db_manager: Database backend (PostgresBackend)
            models: Dictionary mapping entity names to Pydantic models
            relation_loader: Optional relation loader for nested data fetching
            metrics_collector: Optional system metrics collector for query timing
        """
        self.db = db_manager
        self.models = models
        self._relation_loader = relation_loader
        self._metrics = metrics_collector
        self._repositories: dict[str, Repository[Any]] = {}

    def create_repository(self, entity: EntitySpec) -> Repository[Any]:
        """
        Create a repository for an entity.

        Args:
            entity: Entity specification

        Returns:
            Repository instance
        """
        model = self.models.get(entity.name)
        if not model:
            raise ValueError(f"No model found for entity: {entity.name}")

        repo: Repository[Any] = Repository(
            db_manager=self.db,
            entity_spec=entity,
            model_class=model,
            relation_loader=self._relation_loader,
            metrics_collector=self._metrics,
        )
        self._repositories[entity.name] = repo
        return repo

    def create_all_repositories(self, entities: list[EntitySpec]) -> dict[str, Repository[Any]]:
        """
        Create repositories for all entities.

        Args:
            entities: List of entity specifications

        Returns:
            Dictionary mapping entity names to repositories
        """
        for entity in entities:
            self.create_repository(entity)
        return self._repositories

    def get_repository(self, entity_name: str) -> Repository[Any] | None:
        """Get a repository by entity name."""
        return self._repositories.get(entity_name)
