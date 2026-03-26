"""
Migration support types and schema introspection for Dazzle.

Migrations are managed by Alembic (see src/dazzle_back/alembic/).
This module retains schema introspection utilities and type definitions
used by the MCP db tools and CLI reporting.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

# =============================================================================
# Migration Types
# =============================================================================


class MigrationAction(StrEnum):
    """Types of migration actions."""

    CREATE_TABLE = "create_table"
    ADD_COLUMN = "add_column"
    ADD_INDEX = "add_index"
    ADD_CONSTRAINT = "add_constraint"
    DROP_NOT_NULL = "drop_not_null"
    # These are detected but not auto-applied (require manual intervention)
    DROP_COLUMN = "drop_column"
    CHANGE_TYPE = "change_type"


@dataclass
class MigrationStep:
    """A single migration step."""

    action: MigrationAction
    table: str
    column: str | None = None
    sql: str | None = None
    details: dict[str, Any] | None = None
    is_destructive: bool = False


@dataclass
class MigrationPlan:
    """A complete migration plan."""

    steps: list[MigrationStep]
    warnings: list[str]
    has_destructive: bool = False

    @property
    def is_empty(self) -> bool:
        return len(self.steps) == 0

    @property
    def safe_steps(self) -> list[MigrationStep]:
        """Get only non-destructive steps."""
        return [s for s in self.steps if not s.is_destructive]


# =============================================================================
# Schema Introspection
# =============================================================================


@dataclass
class ColumnInfo:
    """Information about a database column."""

    name: str
    type: str
    not_null: bool
    default: Any
    is_pk: bool


def get_table_schema(conn: Any, table_name: str, schema: str = "public") -> list[ColumnInfo]:
    """Get column information for a PostgreSQL table."""
    cursor = conn.cursor()
    cursor.execute(
        "SELECT column_name, data_type, is_nullable, column_default "
        "FROM information_schema.columns "
        "WHERE table_schema = %s AND table_name = %s "
        "ORDER BY ordinal_position",
        (schema, table_name),
    )
    columns = []
    for row in cursor.fetchall():
        r = dict(row)
        columns.append(
            ColumnInfo(
                name=r["column_name"],
                type=r["data_type"].upper(),
                not_null=r["is_nullable"] == "NO",
                default=r["column_default"],
                is_pk=False,  # PK detection via pg_constraint if needed
            )
        )
    return columns


def get_table_indexes(conn: Any, table_name: str, schema: str = "public") -> list[str]:
    """Get index names for a PostgreSQL table."""
    cursor = conn.cursor()
    cursor.execute(
        "SELECT indexname FROM pg_indexes WHERE schemaname = %s AND tablename = %s",
        (schema, table_name),
    )
    return [dict(row)["indexname"] for row in cursor.fetchall()]


class MigrationError(Exception):
    """Error during migration execution."""

    pass


# =============================================================================
# Framework Table: _dazzle_params (#572)
# =============================================================================


# Type alias: db_manager is PostgresBackend (duck-typed .connection() context manager)
DatabaseBackend = Any  # PostgresBackend


# =============================================================================
# Framework Entity Column Sync (#712)
# =============================================================================

# IR FieldTypeKind → PostgreSQL DDL type.
# Only covers types used in auto-generated framework entities
# (FeedbackReport, AIJob, admin platform entities).
_PG_TYPE_MAP: dict[str, str] = {
    "uuid": "UUID",
    "str": "VARCHAR",
    "text": "TEXT",
    "int": "INTEGER",
    "float": "DOUBLE PRECISION",
    "bool": "BOOLEAN",
    "datetime": "TIMESTAMPTZ",
    "enum": "TEXT",
    "decimal": "NUMERIC",
    "money": "NUMERIC",
}


def _field_to_pg_ddl(field: Any) -> str:
    """Return the PostgreSQL column type for an IR FieldSpec."""
    kind = field.type.kind if hasattr(field.type, "kind") else str(field.type)
    pg_type = _PG_TYPE_MAP.get(kind, "TEXT")
    if kind == "str" and field.type.max_length:
        pg_type = f"VARCHAR({field.type.max_length})"
    return pg_type


def ensure_framework_entity_columns(
    db_manager: DatabaseBackend,
    entities: list[Any],
) -> None:
    """Add missing columns to auto-generated framework entity tables.

    ``metadata.create_all()`` only creates missing *tables* — it does not
    add columns to tables that already exist. When we add fields to
    FeedbackReport, AIJob, or admin platform entities, existing deployments
    need the new columns.  This function diffs the live schema against the
    IR fields and runs ``ALTER TABLE ... ADD COLUMN IF NOT EXISTS`` for
    each gap.

    Args:
        db_manager: Database backend (duck-typed ``.connection()`` ctx mgr).
        entities: Full entity list from the AppSpec (filters to
            ``domain="platform"`` automatically).
    """
    import logging

    logger = logging.getLogger(__name__)

    # Only sync framework-managed entities (FeedbackReport, AIJob, admin entities).
    framework_entities = [
        e
        for e in entities
        if getattr(e, "domain", None) == "platform" or e.name in ("FeedbackReport", "AIJob")
    ]
    if not framework_entities:
        return

    with db_manager.connection() as conn:
        cursor = conn.cursor()
        for entity in framework_entities:
            table_name = entity.name
            # Check if table exists at all — if not, create_all handles it.
            existing_cols = {c.name for c in get_table_schema(conn, table_name)}
            if not existing_cols:
                continue

            for field in entity.fields:
                if field.name in existing_cols:
                    continue
                pg_type = _field_to_pg_ddl(field)
                default_clause = ""
                if field.default is not None:
                    if field.default == "now":
                        default_clause = " DEFAULT now()"
                    elif field.default in ("true", "false"):
                        default_clause = f" DEFAULT {field.default.upper()}"
                    else:
                        default_clause = f" DEFAULT '{field.default}'"
                sql = (
                    f'ALTER TABLE "{table_name}" '
                    f"ADD COLUMN IF NOT EXISTS "
                    f'"{field.name}" {pg_type}{default_clause}'
                )
                try:
                    cursor.execute(sql)
                    logger.info("Added column %s.%s (%s)", table_name, field.name, pg_type)
                except Exception:
                    logger.debug("Column %s.%s may already exist", table_name, field.name)


def ensure_dazzle_params_table(db_manager: DatabaseBackend) -> None:
    """Create the _dazzle_params framework table if it doesn't exist."""
    with db_manager.connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS _dazzle_params (
                key TEXT NOT NULL,
                scope TEXT NOT NULL,
                scope_id TEXT NOT NULL DEFAULT '',
                value_json JSONB NOT NULL,
                updated_by TEXT,
                updated_at TIMESTAMPTZ DEFAULT now(),
                PRIMARY KEY (key, scope, scope_id)
            )
        """)
