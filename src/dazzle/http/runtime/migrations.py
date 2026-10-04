"""
Migration support types and schema introspection for Dazzle.

Migrations are managed by Alembic (see src/dazzle/http/alembic/).
This module retains schema introspection utilities and type definitions
used by the MCP db tools and CLI reporting.
"""

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


class MigrationError(Exception):
    """Error during migration execution."""

    pass


# =============================================================================
# Framework Table: _dazzle_params (#572)
# =============================================================================


# Type alias: db_manager is PostgresBackend (duck-typed .connection() context manager)
DatabaseBackend = Any  # PostgresBackend


def ensure_dazzle_params_table(db_manager: DatabaseBackend) -> None:
    """Create the _dazzle_params framework table if it doesn't exist."""
    with db_manager.connection(platform=True) as conn:
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


def verify_dazzle_params_table(db_manager: DatabaseBackend) -> None:
    """Verify the _dazzle_params framework table exists."""
    with db_manager.connection(platform=True) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT EXISTS (
                SELECT 1
                FROM information_schema.tables
                WHERE table_schema = 'public'
                  AND table_name = '_dazzle_params'
            )
            """
        )
        row = cursor.fetchone()
        exists = row[0] if not isinstance(row, dict) else row.get("exists")
        if not exists:
            raise MigrationError(
                "_dazzle_params table is missing. Run 'dazzle db upgrade' before startup."
            )
