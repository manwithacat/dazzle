"""
SQLite repository - provides persistence layer for DNR Backend.

This module implements the repository pattern for SQLite database access.
It auto-creates tables from EntitySpec and provides CRUD operations.
Supports advanced filtering, sorting, pagination, and relation loading.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING, Any, Generic, Iterator, TypeVar
from uuid import UUID

from pydantic import BaseModel

from dazzle_dnr_back.specs.entity import (
    EntitySpec,
    FieldSpec,
    FieldType,
    ScalarType,
)

if TYPE_CHECKING:
    from dazzle_dnr_back.runtime.query_builder import QueryBuilder
    from dazzle_dnr_back.runtime.relation_loader import RelationLoader, RelationRegistry


# =============================================================================
# Type Variables
# =============================================================================

T = TypeVar("T", bound=BaseModel)


# =============================================================================
# SQLite Type Mapping
# =============================================================================


def _scalar_type_to_sqlite(scalar_type: ScalarType) -> str:
    """Map scalar types to SQLite types."""
    mapping: dict[ScalarType, str] = {
        ScalarType.STR: "TEXT",
        ScalarType.TEXT: "TEXT",
        ScalarType.INT: "INTEGER",
        ScalarType.DECIMAL: "REAL",
        ScalarType.BOOL: "INTEGER",  # SQLite uses 0/1 for bool
        ScalarType.DATE: "TEXT",  # ISO format
        ScalarType.DATETIME: "TEXT",  # ISO format
        ScalarType.UUID: "TEXT",  # UUID as string
        ScalarType.EMAIL: "TEXT",
        ScalarType.URL: "TEXT",
        ScalarType.JSON: "TEXT",  # JSON as string
    }
    return mapping.get(scalar_type, "TEXT")


def _field_type_to_sqlite(field_type: FieldType) -> str:
    """Convert FieldType to SQLite column type."""
    if field_type.kind == "scalar" and field_type.scalar_type:
        return _scalar_type_to_sqlite(field_type.scalar_type)
    elif field_type.kind == "enum":
        return "TEXT"
    elif field_type.kind == "ref":
        return "TEXT"  # Foreign key as UUID string
    else:
        return "TEXT"


def _python_to_sqlite(value: Any, field_type: FieldType | None = None) -> Any:
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
    elif isinstance(value, dict):
        return json.dumps(value)
    elif isinstance(value, list):
        return json.dumps(value)
    else:
        return value


def _sqlite_to_python(value: Any, field_type: FieldType | None = None) -> Any:
    """Convert SQLite value to Python type based on field type."""
    if value is None:
        return None
    if field_type is None:
        return value

    if field_type.kind == "scalar" and field_type.scalar_type:
        scalar = field_type.scalar_type
        if scalar == ScalarType.UUID:
            return UUID(value) if value else None
        elif scalar == ScalarType.DATETIME:
            return datetime.fromisoformat(value) if value else None
        elif scalar == ScalarType.DATE:
            return date.fromisoformat(value) if value else None
        elif scalar == ScalarType.DECIMAL:
            return Decimal(str(value)) if value is not None else None
        elif scalar == ScalarType.BOOL:
            return bool(value)
        elif scalar == ScalarType.JSON:
            return json.loads(value) if value else None
        else:
            return value
    elif field_type.kind == "ref":
        return UUID(value) if value else None
    else:
        return value


# =============================================================================
# Database Manager
# =============================================================================


class DatabaseManager:
    """
    Manages SQLite database connection and schema.

    Handles database creation, table creation, and migrations.
    """

    def __init__(self, db_path: str | Path = ".dazzle/data.db"):
        """
        Initialize the database manager.

        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = Path(db_path)
        self._ensure_directory()
        self._connection: sqlite3.Connection | None = None

    def _ensure_directory(self) -> None:
        """Ensure the database directory exists."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        """
        Get a database connection context manager.

        Yields:
            SQLite connection
        """
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def get_persistent_connection(self) -> sqlite3.Connection:
        """
        Get a persistent connection for the application lifecycle.

        Returns:
            SQLite connection (reuses existing if available)
        """
        if self._connection is None:
            self._connection = sqlite3.connect(str(self.db_path))
            self._connection.row_factory = sqlite3.Row
        return self._connection

    def close(self) -> None:
        """Close the persistent connection."""
        if self._connection:
            self._connection.close()
            self._connection = None

    def create_table(self, entity: EntitySpec) -> None:
        """
        Create a table for an entity if it doesn't exist.

        Args:
            entity: Entity specification
        """
        columns = self._build_columns(entity)
        sql = f"CREATE TABLE IF NOT EXISTS {entity.name} ({columns})"

        with self.connection() as conn:
            conn.execute(sql)

            # Create indexes
            for field in entity.fields:
                if field.indexed:
                    index_sql = f"CREATE INDEX IF NOT EXISTS idx_{entity.name}_{field.name} ON {entity.name}({field.name})"
                    conn.execute(index_sql)

    def _build_columns(self, entity: EntitySpec) -> str:
        """Build column definitions for CREATE TABLE."""
        columns = []

        # Check if entity has an id field
        has_id = any(f.name == "id" for f in entity.fields)
        if not has_id:
            columns.append("id TEXT PRIMARY KEY")

        for field in entity.fields:
            col_def = self._build_column(field)
            columns.append(col_def)

        return ", ".join(columns)

    def _build_column(self, field: FieldSpec) -> str:
        """Build a single column definition."""
        sqlite_type = _field_type_to_sqlite(field.type)
        parts = [field.name, sqlite_type]

        if field.name == "id":
            parts.append("PRIMARY KEY")
        elif field.required:
            parts.append("NOT NULL")

        if field.unique:
            parts.append("UNIQUE")

        if field.default is not None:
            default_val = _python_to_sqlite(field.default, field.type)
            if isinstance(default_val, str):
                parts.append(f"DEFAULT '{default_val}'")
            else:
                parts.append(f"DEFAULT {default_val}")

        return " ".join(parts)

    def create_all_tables(self, entities: list[EntitySpec]) -> None:
        """
        Create tables for all entities.

        Args:
            entities: List of entity specifications
        """
        for entity in entities:
            self.create_table(entity)

    def table_exists(self, table_name: str) -> bool:
        """Check if a table exists."""
        with self.connection() as conn:
            cursor = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                (table_name,)
            )
            return cursor.fetchone() is not None

    def get_table_columns(self, table_name: str) -> list[str]:
        """Get column names for a table."""
        with self.connection() as conn:
            cursor = conn.execute(f"PRAGMA table_info({table_name})")
            return [row[1] for row in cursor.fetchall()]


# =============================================================================
# Repository
# =============================================================================


class SQLiteRepository(Generic[T]):
    """
    SQLite repository for a single entity type.

    Provides CRUD operations against SQLite database.
    Supports advanced filtering, sorting, and relation loading.
    """

    def __init__(
        self,
        db_manager: DatabaseManager,
        entity_spec: EntitySpec,
        model_class: type[T],
        relation_loader: "RelationLoader | None" = None,
    ):
        """
        Initialize the repository.

        Args:
            db_manager: Database manager instance
            entity_spec: Entity specification
            model_class: Pydantic model class for the entity
            relation_loader: Optional relation loader for nested data fetching
        """
        self.db = db_manager
        self.entity_spec = entity_spec
        self.model_class = model_class
        self.table_name = entity_spec.name
        self._relation_loader = relation_loader

        # Build field type lookup for conversions
        self._field_types: dict[str, FieldType] = {
            f.name: f.type for f in entity_spec.fields
        }

    def _model_to_row(self, model: T) -> dict[str, Any]:
        """Convert Pydantic model to row dict for SQLite."""
        data = model.model_dump()
        return {
            k: _python_to_sqlite(v, self._field_types.get(k))
            for k, v in data.items()
        }

    def _row_to_model(self, row: sqlite3.Row) -> T:
        """Convert SQLite row to Pydantic model."""
        data = dict(row)
        converted = {
            k: _sqlite_to_python(v, self._field_types.get(k))
            for k, v in data.items()
        }
        return self.model_class(**converted)

    async def create(self, data: dict[str, Any]) -> T:
        """
        Create a new entity.

        Args:
            data: Entity data (including id)

        Returns:
            Created entity
        """
        # Convert values for SQLite
        sqlite_data = {
            k: _python_to_sqlite(v, self._field_types.get(k))
            for k, v in data.items()
        }

        columns = ", ".join(sqlite_data.keys())
        placeholders = ", ".join("?" * len(sqlite_data))
        values = list(sqlite_data.values())

        sql = f"INSERT INTO {self.table_name} ({columns}) VALUES ({placeholders})"

        with self.db.connection() as conn:
            conn.execute(sql, values)

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
        sql = f"SELECT * FROM {self.table_name} WHERE id = ?"

        with self.db.connection() as conn:
            cursor = conn.execute(sql, (str(id),))
            row = cursor.fetchone()

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

        return self._row_to_model(row)

    async def update(self, id: UUID, data: dict[str, Any]) -> T | None:
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

        # Convert values for SQLite
        sqlite_data = {
            k: _python_to_sqlite(v, self._field_types.get(k))
            for k, v in update_data.items()
        }

        set_clause = ", ".join(f"{k} = ?" for k in sqlite_data.keys())
        values = list(sqlite_data.values())
        values.append(str(id))

        sql = f"UPDATE {self.table_name} SET {set_clause} WHERE id = ?"

        with self.db.connection() as conn:
            cursor = conn.execute(sql, values)
            if cursor.rowcount == 0:
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
        sql = f"DELETE FROM {self.table_name} WHERE id = ?"

        with self.db.connection() as conn:
            cursor = conn.execute(sql, (str(id),))
            return cursor.rowcount > 0

    async def list(
        self,
        page: int = 1,
        page_size: int = 20,
        filters: dict[str, Any] | None = None,
        sort: str | list[str] | None = None,
        include: list[str] | None = None,
        search: str | None = None,
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
        from dazzle_dnr_back.runtime.query_builder import QueryBuilder

        # Build query using QueryBuilder
        builder = QueryBuilder(table_name=self.table_name)
        builder.set_pagination(page, page_size)

        if filters:
            builder.add_filters(filters)

        if sort:
            builder.add_sorts(sort)

        if search:
            builder.set_search(search)

        # Get total count
        count_sql, count_params = builder.build_count()

        with self.db.connection() as conn:
            cursor = conn.execute(count_sql, count_params)
            total = cursor.fetchone()[0]

        # Get paginated items
        items_sql, items_params = builder.build_select()

        with self.db.connection() as conn:
            cursor = conn.execute(items_sql, items_params)
            rows = cursor.fetchall()

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

        # Convert to models (or return dicts if relations included)
        if include:
            # Return dicts with nested data
            items = [self._convert_row_dict(row) for row in row_dicts]
        else:
            items = [self._row_to_model(row) for row in rows]

        return {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    def _convert_row_dict(self, row: dict[str, Any]) -> dict[str, Any]:
        """Convert a row dict with proper type conversions."""
        result = {}
        for k, v in row.items():
            if isinstance(v, dict):
                # Nested relation - convert recursively
                result[k] = self._convert_row_dict(v) if v else None
            elif isinstance(v, list):
                # To-many relation
                result[k] = [self._convert_row_dict(item) for item in v]
            else:
                # Regular field
                result[k] = _sqlite_to_python(v, self._field_types.get(k))
        return result

    async def exists(self, id: UUID) -> bool:
        """Check if an entity exists."""
        sql = f"SELECT 1 FROM {self.table_name} WHERE id = ? LIMIT 1"

        with self.db.connection() as conn:
            cursor = conn.execute(sql, (str(id),))
            return cursor.fetchone() is not None


# =============================================================================
# Repository Factory
# =============================================================================


class RepositoryFactory:
    """
    Factory for creating repositories from entity specifications.
    """

    def __init__(
        self,
        db_manager: DatabaseManager,
        models: dict[str, type[BaseModel]],
        relation_loader: "RelationLoader | None" = None,
    ):
        """
        Initialize the factory.

        Args:
            db_manager: Database manager
            models: Dictionary mapping entity names to Pydantic models
            relation_loader: Optional relation loader for nested data fetching
        """
        self.db = db_manager
        self.models = models
        self._relation_loader = relation_loader
        self._repositories: dict[str, SQLiteRepository[Any]] = {}

    def create_repository(self, entity: EntitySpec) -> SQLiteRepository[Any]:
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

        repo: SQLiteRepository[Any] = SQLiteRepository(
            db_manager=self.db,
            entity_spec=entity,
            model_class=model,
            relation_loader=self._relation_loader,
        )
        self._repositories[entity.name] = repo
        return repo

    def create_all_repositories(
        self, entities: list[EntitySpec]
    ) -> dict[str, SQLiteRepository[Any]]:
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

    def get_repository(self, entity_name: str) -> SQLiteRepository[Any] | None:
        """Get a repository by entity name."""
        return self._repositories.get(entity_name)
