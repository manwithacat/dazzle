"""
PostgreSQL database backend for DNR Backend.

Provides the PostgreSQL database backend — the sole runtime backend.

Requires: psycopg[binary]>=3.2
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from dazzle_back.runtime.query_builder import quote_identifier
from dazzle_back.specs.entity import EntitySpec, FieldSpec, FieldType, ScalarType

logger = logging.getLogger(__name__)


# =============================================================================
# Connection Wrapper
# =============================================================================


class PgConnectionWrapper:
    """Wrapper that adds .execute() convenience method to psycopg connections.

    Proxies execute through cursor().execute(), returning the cursor.
    All other attribute access is forwarded to the underlying connection.
    """

    def __init__(self, conn: Any) -> None:
        self._conn = conn

    def execute(self, sql: str, params: Any = None) -> Any:
        """Execute SQL via a new cursor and return it."""
        cursor = self._conn.cursor()
        cursor.execute(sql, params or ())
        return cursor

    def __getattr__(self, name: str) -> Any:
        return getattr(self._conn, name)


# =============================================================================
# Postgres Type Mapping
# =============================================================================


def _scalar_type_to_postgres(scalar_type: ScalarType) -> str:
    """Map scalar types to PostgreSQL types."""
    mapping: dict[ScalarType, str] = {
        ScalarType.STR: "TEXT",
        ScalarType.TEXT: "TEXT",
        ScalarType.INT: "INTEGER",
        ScalarType.DECIMAL: "DOUBLE PRECISION",
        ScalarType.BOOL: "BOOLEAN",
        ScalarType.DATE: "TEXT",
        ScalarType.DATETIME: "TEXT",
        ScalarType.UUID: "TEXT",
        ScalarType.EMAIL: "TEXT",
        ScalarType.URL: "TEXT",
        ScalarType.JSON: "TEXT",
    }
    return mapping.get(scalar_type, "TEXT")


def _field_type_to_postgres(field_type: FieldType) -> str:
    """Convert FieldType to PostgreSQL column type."""
    if field_type.kind == "scalar" and field_type.scalar_type:
        return _scalar_type_to_postgres(field_type.scalar_type)
    elif field_type.kind == "enum":
        return "TEXT"
    elif field_type.kind == "ref":
        return "TEXT"
    else:
        return "TEXT"


def _python_to_postgres(value: Any, field_type: FieldType | None = None) -> Any:
    """Convert Python value to PostgreSQL-compatible value."""
    import json
    from datetime import date, datetime
    from decimal import Decimal
    from uuid import UUID

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
        return value  # Postgres has native bool
    elif isinstance(value, dict):
        return json.dumps(value)
    elif isinstance(value, list):
        return json.dumps(value)
    else:
        return value


# =============================================================================
# PostgreSQL Backend
# =============================================================================


class PostgresBackend:
    """
    PostgreSQL database backend.

    Drop-in replacement for DatabaseManager that uses PostgreSQL
    instead of SQLite. Parses DATABASE_URL for connection parameters.
    """

    def __init__(self, database_url: str, search_path: str | None = None):
        """
        Initialize the PostgreSQL backend.

        Args:
            database_url: PostgreSQL connection URL
                          (e.g. postgresql://user:pass@host:5432/dbname)
            search_path: Optional schema search path (e.g. 'tenant_abc')
        """
        self.database_url = database_url
        self.search_path = search_path
        self._connection: Any = None

    @property
    def _sa_url(self) -> str:
        """Return a SQLAlchemy-compatible URL using psycopg (v3) driver."""
        url = self.database_url
        if url.startswith("postgresql://"):
            url = url.replace("postgresql://", "postgresql+psycopg://", 1)
        return url

    @contextmanager
    def connection(self) -> Iterator[Any]:
        """
        Get a database connection context manager.

        Yields a wrapped psycopg connection with dict_row factory.
        Rows support string key access (row["col"]).
        The wrapper adds .execute() for sqlite3 API compatibility.
        """
        import psycopg
        from psycopg.rows import dict_row

        conn = psycopg.connect(self.database_url, row_factory=dict_row)
        try:
            if self.search_path:
                conn.execute(f"SET search_path TO {self.search_path}, public")
            yield PgConnectionWrapper(conn)
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def get_persistent_connection(self) -> Any:
        """
        Get a persistent connection for the application lifecycle.

        Returns a wrapped psycopg connection (reuses existing if available).
        """
        import psycopg
        from psycopg.rows import dict_row

        if self._connection is None or self._connection.closed:
            raw = psycopg.connect(self.database_url, row_factory=dict_row)
            if self.search_path:
                raw.execute(f"SET search_path TO {self.search_path}, public")
            self._connection = PgConnectionWrapper(raw)
        return self._connection

    def close(self) -> None:
        """Close the persistent connection."""
        if self._connection and not self._connection.closed:
            self._connection.close()
            self._connection = None

    @property
    def backend_type(self) -> str:
        return "postgres"

    @property
    def placeholder(self) -> str:
        return "%s"

    def create_table(self, entity: EntitySpec, *, registry: Any = None) -> None:
        """Create a table for an entity if it doesn't exist."""
        columns = self._build_columns(entity, registry=registry)
        table = quote_identifier(entity.name)
        sql = f"CREATE TABLE IF NOT EXISTS {table} ({columns})"

        with self.connection() as conn:
            cursor = conn.cursor()
            cursor.execute(sql)

            # Create indexes
            for field in entity.fields:
                if field.indexed:
                    col = quote_identifier(field.name)
                    index_sql = f"CREATE INDEX IF NOT EXISTS idx_{entity.name}_{field.name} ON {table}({col})"
                    cursor.execute(index_sql)

            # Create FK indexes
            if registry is not None:
                from dazzle_back.runtime.relation_loader import get_foreign_key_indexes

                for fk_idx_sql in get_foreign_key_indexes(entity, registry):
                    cursor.execute(fk_idx_sql)

    def _build_columns(self, entity: EntitySpec, *, registry: Any = None) -> str:
        """Build column definitions for CREATE TABLE."""
        columns = []
        has_id = any(f.name == "id" for f in entity.fields)
        if not has_id:
            columns.append('"id" TEXT PRIMARY KEY')

        for field in entity.fields:
            col_def = self._build_column(field)
            columns.append(col_def)

        # Append FK constraints from the relation registry
        if registry is not None:
            from dazzle_back.runtime.relation_loader import get_foreign_key_constraints

            fk_clauses = get_foreign_key_constraints(entity, registry)
            columns.extend(fk_clauses)

        return ", ".join(columns)

    def _build_column(self, field: FieldSpec) -> str:
        """Build a single column definition."""
        pg_type = _field_type_to_postgres(field.type)
        col_name = quote_identifier(field.name)
        parts = [col_name, pg_type]

        if field.name == "id":
            parts.append("PRIMARY KEY")
        elif field.required:
            parts.append("NOT NULL")

        if field.unique:
            parts.append("UNIQUE")

        if field.default is not None:
            default_val = _python_to_postgres(field.default, field.type)
            if isinstance(default_val, str):
                parts.append(f"DEFAULT '{default_val}'")
            elif isinstance(default_val, bool):
                parts.append(f"DEFAULT {'TRUE' if default_val else 'FALSE'}")
            else:
                parts.append(f"DEFAULT {default_val}")

        return " ".join(parts)

    def create_all_tables(self, entities: list[EntitySpec]) -> None:
        """Create tables for all entities in topological (FK-dependency) order.

        Uses SQLAlchemy MetaData.create_all() which internally sorts tables
        by foreign key dependencies, preventing errors when a table references
        another that hasn't been created yet.
        """
        from sqlalchemy import create_engine

        from dazzle_back.runtime.sa_schema import build_metadata

        metadata = build_metadata(entities)
        engine = create_engine(self._sa_url)
        try:
            metadata.create_all(engine, checkfirst=True)
        finally:
            engine.dispose()

        # Create application-level indexes (not in SA schema)
        from dazzle_back.runtime.relation_loader import (
            RelationRegistry,
            get_foreign_key_indexes,
        )

        registry = RelationRegistry.from_entities(entities)
        with self.connection() as conn:
            cursor = conn.cursor()
            for entity in entities:
                for field in entity.fields:
                    if field.indexed:
                        col = quote_identifier(field.name)
                        table = quote_identifier(entity.name)
                        index_sql = f"CREATE INDEX IF NOT EXISTS idx_{entity.name}_{field.name} ON {table}({col})"
                        cursor.execute(index_sql)
                for fk_idx_sql in get_foreign_key_indexes(entity, registry):
                    cursor.execute(fk_idx_sql)

    def table_exists(self, table_name: str) -> bool:
        """Check if a table exists."""
        with self.connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT tablename FROM pg_tables WHERE schemaname = 'public' AND tablename = %s",
                (table_name,),
            )
            return cursor.fetchone() is not None

    def get_table_columns(self, table_name: str) -> list[str]:
        """Get column names for a table."""
        with self.connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema = 'public' AND table_name = %s "
                "ORDER BY ordinal_position",
                (table_name,),
            )
            return [row["column_name"] for row in cursor.fetchall()]

    def get_column_info(self, table_name: str) -> list[dict[str, Any]]:
        """Get detailed column information for a table."""
        with self.connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT column_name, data_type, is_nullable, column_default "
                "FROM information_schema.columns "
                "WHERE table_schema = 'public' AND table_name = %s "
                "ORDER BY ordinal_position",
                (table_name,),
            )
            return [dict(row) for row in cursor.fetchall()]

    def get_table_indexes(self, table_name: str) -> list[str]:
        """Get index names for a table."""
        with self.connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT indexname FROM pg_indexes WHERE tablename = %s",
                (table_name,),
            )
            return [row["indexname"] for row in cursor.fetchall()]
