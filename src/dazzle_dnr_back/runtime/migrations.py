"""
Auto-migration system for DNR Backend.

Detects schema changes between EntitySpec and existing SQLite tables,
and applies migrations automatically.

Supported operations:
- Add new tables
- Add new columns (with defaults)
- Add new indexes

Not supported (requires manual migration):
- Remove columns (data loss)
- Change column types (data loss)
- Rename columns (ambiguous)
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from dazzle_dnr_back.runtime.repository import (
    DatabaseManager,
    _field_type_to_sqlite,
    _python_to_sqlite,
)
from dazzle_dnr_back.specs.entity import EntitySpec, FieldSpec

# =============================================================================
# Migration Types
# =============================================================================


class MigrationAction(str, Enum):
    """Types of migration actions."""

    CREATE_TABLE = "create_table"
    ADD_COLUMN = "add_column"
    ADD_INDEX = "add_index"
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


def get_table_schema(conn: sqlite3.Connection, table_name: str) -> list[ColumnInfo]:
    """Get column information for a table."""
    cursor = conn.execute(f"PRAGMA table_info({table_name})")
    columns = []
    for row in cursor.fetchall():
        columns.append(
            ColumnInfo(
                name=row[1],
                type=row[2],
                not_null=bool(row[3]),
                default=row[4],
                is_pk=bool(row[5]),
            )
        )
    return columns


def get_table_indexes(conn: sqlite3.Connection, table_name: str) -> list[str]:
    """Get index names for a table."""
    cursor = conn.execute(f"PRAGMA index_list({table_name})")
    return [row[1] for row in cursor.fetchall()]


# =============================================================================
# Migration Planning
# =============================================================================


class MigrationPlanner:
    """
    Plans migrations by comparing EntitySpec to existing database schema.
    """

    def __init__(self, db_manager: DatabaseManager):
        self.db = db_manager

    def plan_migrations(self, entities: list[EntitySpec]) -> MigrationPlan:
        """
        Create a migration plan for all entities.

        Args:
            entities: List of entity specifications

        Returns:
            Migration plan with steps and warnings
        """
        steps: list[MigrationStep] = []
        warnings: list[str] = []

        with self.db.connection() as conn:
            for entity in entities:
                entity_steps, entity_warnings = self._plan_entity_migration(conn, entity)
                steps.extend(entity_steps)
                warnings.extend(entity_warnings)

        has_destructive = any(s.is_destructive for s in steps)

        return MigrationPlan(
            steps=steps,
            warnings=warnings,
            has_destructive=has_destructive,
        )

    def _plan_entity_migration(
        self, conn: sqlite3.Connection, entity: EntitySpec
    ) -> tuple[list[MigrationStep], list[str]]:
        """Plan migration for a single entity."""
        steps: list[MigrationStep] = []
        warnings: list[str] = []

        # Check if table exists
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            (entity.name,),
        )
        table_exists = cursor.fetchone() is not None

        if not table_exists:
            # New table - create it
            sql = self._generate_create_table_sql(entity)
            steps.append(
                MigrationStep(
                    action=MigrationAction.CREATE_TABLE,
                    table=entity.name,
                    sql=sql,
                )
            )
            # Also add indexes for new table
            for field in entity.fields:
                if field.indexed:
                    index_sql = self._generate_index_sql(entity.name, field.name)
                    steps.append(
                        MigrationStep(
                            action=MigrationAction.ADD_INDEX,
                            table=entity.name,
                            column=field.name,
                            sql=index_sql,
                        )
                    )
            return steps, warnings

        # Table exists - compare columns
        existing_columns = get_table_schema(conn, entity.name)
        existing_column_names = {c.name for c in existing_columns}
        existing_indexes = set(get_table_indexes(conn, entity.name))

        # Build expected columns from entity
        expected_fields = {f.name: f for f in entity.fields}

        # Check if entity has id field, if not we add one
        if "id" not in expected_fields:
            expected_fields["id"] = FieldSpec(
                name="id",
                type=entity.fields[0].type if entity.fields else None,  # type: ignore
                required=True,
            )

        # Find new columns
        for field_name, field in expected_fields.items():
            if field_name not in existing_column_names:
                sql = self._generate_add_column_sql(entity.name, field)
                steps.append(
                    MigrationStep(
                        action=MigrationAction.ADD_COLUMN,
                        table=entity.name,
                        column=field_name,
                        sql=sql,
                        details={"field": field.model_dump()},
                    )
                )

        # Find removed columns (warning only - not auto-applied)
        for col in existing_columns:
            if col.name not in expected_fields:
                warnings.append(
                    f"Column '{col.name}' in table '{entity.name}' is not in entity spec. "
                    f"Consider removing it manually if no longer needed."
                )
                steps.append(
                    MigrationStep(
                        action=MigrationAction.DROP_COLUMN,
                        table=entity.name,
                        column=col.name,
                        is_destructive=True,
                    )
                )

        # Find new indexes
        for field in entity.fields:
            if field.indexed:
                index_name = f"idx_{entity.name}_{field.name}"
                if index_name not in existing_indexes:
                    sql = self._generate_index_sql(entity.name, field.name)
                    steps.append(
                        MigrationStep(
                            action=MigrationAction.ADD_INDEX,
                            table=entity.name,
                            column=field.name,
                            sql=sql,
                        )
                    )

        return steps, warnings

    def _generate_create_table_sql(self, entity: EntitySpec) -> str:
        """Generate CREATE TABLE SQL."""
        columns = []

        # Check if entity has an id field
        has_id = any(f.name == "id" for f in entity.fields)
        if not has_id:
            columns.append("id TEXT PRIMARY KEY")

        for field in entity.fields:
            col_def = self._generate_column_def(field)
            columns.append(col_def)

        return f"CREATE TABLE IF NOT EXISTS {entity.name} ({', '.join(columns)})"

    def _generate_column_def(self, field: FieldSpec) -> str:
        """Generate column definition for a field."""
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

    def _generate_add_column_sql(self, table_name: str, field: FieldSpec) -> str:
        """Generate ALTER TABLE ADD COLUMN SQL."""
        sqlite_type = _field_type_to_sqlite(field.type)
        parts = [f"ALTER TABLE {table_name} ADD COLUMN {field.name} {sqlite_type}"]

        # SQLite has restrictions on ALTER TABLE:
        # - Cannot add NOT NULL without default
        # - Cannot add PRIMARY KEY
        # So we make new columns nullable or provide defaults

        if field.default is not None:
            default_val = _python_to_sqlite(field.default, field.type)
            if isinstance(default_val, str):
                parts.append(f"DEFAULT '{default_val}'")
            else:
                parts.append(f"DEFAULT {default_val}")
        elif field.required:
            # For required fields without default, use type-appropriate default
            default = self._get_type_default(field)
            if default is not None:
                if isinstance(default, str):
                    parts.append(f"DEFAULT '{default}'")
                else:
                    parts.append(f"DEFAULT {default}")

        return " ".join(parts)

    def _get_type_default(self, field: FieldSpec) -> Any:
        """Get a sensible default for a field type."""
        if field.type.kind == "scalar" and field.type.scalar_type:
            from dazzle_dnr_back.specs.entity import ScalarType

            defaults = {
                ScalarType.STR: "",
                ScalarType.TEXT: "",
                ScalarType.INT: 0,
                ScalarType.DECIMAL: 0.0,
                ScalarType.BOOL: 0,
                ScalarType.UUID: "",
                ScalarType.EMAIL: "",
                ScalarType.URL: "",
                ScalarType.JSON: "{}",
            }
            return defaults.get(field.type.scalar_type)
        elif field.type.kind == "enum" and field.type.enum_values:
            return field.type.enum_values[0]
        return None

    def _generate_index_sql(self, table_name: str, column_name: str) -> str:
        """Generate CREATE INDEX SQL."""
        index_name = f"idx_{table_name}_{column_name}"
        return f"CREATE INDEX IF NOT EXISTS {index_name} ON {table_name}({column_name})"


# =============================================================================
# Migration Executor
# =============================================================================


class MigrationExecutor:
    """
    Executes migration plans against the database.
    """

    def __init__(self, db_manager: DatabaseManager):
        self.db = db_manager

    def execute(self, plan: MigrationPlan, skip_destructive: bool = True) -> list[MigrationStep]:
        """
        Execute a migration plan.

        Args:
            plan: Migration plan to execute
            skip_destructive: If True, skip destructive operations

        Returns:
            List of executed steps
        """
        executed: list[MigrationStep] = []

        with self.db.connection() as conn:
            for step in plan.steps:
                if step.is_destructive and skip_destructive:
                    continue

                if step.sql:
                    try:
                        conn.execute(step.sql)
                        executed.append(step)
                    except sqlite3.Error as e:
                        raise MigrationError(
                            f"Failed to execute migration step: {step.action.value} "
                            f"on {step.table}.{step.column or ''}: {e}"
                        ) from e

        return executed

    def execute_safe(self, plan: MigrationPlan) -> list[MigrationStep]:
        """Execute only non-destructive migration steps."""
        return self.execute(plan, skip_destructive=True)


class MigrationError(Exception):
    """Error during migration execution."""

    pass


# =============================================================================
# Migration History (Optional)
# =============================================================================


class MigrationHistory:
    """
    Tracks migration history in the database.

    Creates a _migrations table to track applied migrations.
    """

    TABLE_NAME = "_dazzle_migrations"

    def __init__(self, db_manager: DatabaseManager):
        self.db = db_manager
        self._ensure_table()

    def _ensure_table(self) -> None:
        """Ensure migrations table exists."""
        sql = f"""
        CREATE TABLE IF NOT EXISTS {self.TABLE_NAME} (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            applied_at TEXT NOT NULL,
            action TEXT NOT NULL,
            table_name TEXT NOT NULL,
            column_name TEXT,
            sql_executed TEXT,
            details TEXT
        )
        """
        with self.db.connection() as conn:
            conn.execute(sql)

    def record_migration(self, step: MigrationStep) -> None:
        """Record an executed migration step."""
        import json

        sql = f"""
        INSERT INTO {self.TABLE_NAME}
        (applied_at, action, table_name, column_name, sql_executed, details)
        VALUES (?, ?, ?, ?, ?, ?)
        """
        with self.db.connection() as conn:
            conn.execute(
                sql,
                (
                    datetime.now(UTC).isoformat(),
                    step.action.value,
                    step.table,
                    step.column,
                    step.sql,
                    json.dumps(step.details) if step.details else None,
                ),
            )

    def get_history(self) -> list[dict[str, Any]]:
        """Get migration history."""
        sql = f"SELECT * FROM {self.TABLE_NAME} ORDER BY id DESC"
        with self.db.connection() as conn:
            cursor = conn.execute(sql)
            columns = [desc[0] for desc in cursor.description]
            return [dict(zip(columns, row, strict=False)) for row in cursor.fetchall()]


# =============================================================================
# High-Level API
# =============================================================================


def auto_migrate(
    db_manager: DatabaseManager,
    entities: list[EntitySpec],
    record_history: bool = True,
) -> MigrationPlan:
    """
    Automatically migrate database to match entity specifications.

    This is the main entry point for auto-migration.

    Args:
        db_manager: Database manager instance
        entities: List of entity specifications
        record_history: Whether to record migration history

    Returns:
        The executed migration plan
    """
    planner = MigrationPlanner(db_manager)
    plan = planner.plan_migrations(entities)

    if plan.is_empty:
        return plan

    executor = MigrationExecutor(db_manager)
    executed = executor.execute_safe(plan)

    if record_history and executed:
        history = MigrationHistory(db_manager)
        for step in executed:
            history.record_migration(step)

    return plan


def plan_migrations(
    db_manager: DatabaseManager,
    entities: list[EntitySpec],
) -> MigrationPlan:
    """
    Plan migrations without executing them.

    Useful for previewing what would happen.

    Args:
        db_manager: Database manager instance
        entities: List of entity specifications

    Returns:
        Migration plan
    """
    planner = MigrationPlanner(db_manager)
    return planner.plan_migrations(entities)
