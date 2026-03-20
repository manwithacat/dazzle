"""
Auto-migration system for DNR Backend.

Detects schema changes between EntitySpec and existing PostgreSQL tables,
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

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from dazzle_back.runtime.query_builder import quote_identifier
from dazzle_back.specs.entity import EntitySpec, FieldSpec

# Type alias: db_manager is PostgresBackend (duck-typed .connection() context manager)
DatabaseBackend = Any  # PostgresBackend

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


# =============================================================================
# Migration Planning
# =============================================================================


class MigrationPlanner:
    """
    Plans migrations by comparing EntitySpec to existing database schema.
    """

    def __init__(self, db_manager: DatabaseBackend, schema: str = "public"):
        self.db = db_manager
        self.schema = schema

    def plan_migrations(self, entities: list[EntitySpec]) -> MigrationPlan:
        """
        Create a migration plan for all entities.

        Tables are ordered topologically by FK dependencies using SQLAlchemy's
        MetaData.sorted_tables so that CREATE TABLE statements for referenced
        tables come before their dependents.

        Circular FK references (e.g. Department ↔ User) are handled by
        creating tables without the circular FK constraints first, then
        adding them via ALTER TABLE ADD CONSTRAINT in a second pass.

        Args:
            entities: List of entity specifications

        Returns:
            Migration plan with steps and warnings
        """
        from dazzle_back.runtime.relation_loader import RelationRegistry
        from dazzle_back.runtime.sa_schema import build_metadata, get_circular_ref_edges

        steps: list[MigrationStep] = []
        warnings: list[str] = []
        registry = RelationRegistry.from_entities(entities)
        circular_edges = get_circular_ref_edges(entities)

        # Build SA metadata for topological ordering
        metadata = build_metadata(entities)
        entity_map = {e.name: e for e in entities}

        # sorted_tables gives us FK-dependency order
        sorted_names = [t.name for t in metadata.sorted_tables]

        # Also include any entities not captured (shouldn't happen, but safe)
        for e in entities:
            if e.name not in sorted_names:
                sorted_names.append(e.name)

        with self.db.connection() as conn:
            for name in sorted_names:
                entity = entity_map.get(name)
                if entity is None:
                    continue
                entity_steps, entity_warnings = self._plan_entity_migration(
                    conn,
                    entity,
                    registry,
                    circular_edges,
                )
                steps.extend(entity_steps)
                warnings.extend(entity_warnings)

        # Add deferred FK constraints for circular references (second pass)
        if circular_edges:
            deferred_steps = self._plan_deferred_fk_constraints(
                entities,
                circular_edges,
                entity_map,
            )
            steps.extend(deferred_steps)

        has_destructive = any(s.is_destructive for s in steps)

        return MigrationPlan(
            steps=steps,
            warnings=warnings,
            has_destructive=has_destructive,
        )

    def _plan_entity_migration(
        self,
        conn: Any,
        entity: EntitySpec,
        registry: Any = None,
        circular_edges: set[tuple[str, str]] | None = None,
    ) -> tuple[list[MigrationStep], list[str]]:
        """Plan migration for a single entity."""
        steps: list[MigrationStep] = []
        warnings: list[str] = []

        # Check if table exists
        cursor = conn.cursor()
        cursor.execute(
            "SELECT tablename FROM pg_tables WHERE schemaname = %s AND tablename = %s",
            (self.schema, entity.name),
        )
        table_exists = cursor.fetchone() is not None

        if not table_exists:
            # New table - create it (circular FKs excluded, added later via ALTER TABLE)
            sql = self._generate_create_table_sql(
                entity,
                registry=registry,
                circular_edges=circular_edges,
            )
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
            # Add FK indexes
            if registry is not None:
                from dazzle_back.runtime.relation_loader import get_foreign_key_indexes

                for fk_idx_sql in get_foreign_key_indexes(entity, registry):
                    steps.append(
                        MigrationStep(
                            action=MigrationAction.ADD_INDEX,
                            table=entity.name,
                            sql=fk_idx_sql,
                        )
                    )
            return steps, warnings

        # Table exists - compare columns
        existing_columns = get_table_schema(conn, entity.name, schema=self.schema)
        existing_column_names = {c.name for c in existing_columns}
        existing_indexes = set(get_table_indexes(conn, entity.name, schema=self.schema))

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

                # If orphaned col "price" has NOT NULL, and expected fields
                # contain "price_minor" + "price_currency", this is a money
                # expansion -> DROP NOT NULL on the old column so INSERTs
                # don't crash.
                if (
                    col.not_null
                    and f"{col.name}_minor" in expected_fields
                    and f"{col.name}_currency" in expected_fields
                ):
                    steps.append(
                        MigrationStep(
                            action=MigrationAction.DROP_NOT_NULL,
                            table=entity.name,
                            column=col.name,
                            sql=self._generate_drop_not_null_sql(entity.name, col.name),
                            is_destructive=False,
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

    def _generate_create_table_sql(
        self,
        entity: EntitySpec,
        registry: Any = None,
        circular_edges: set[tuple[str, str]] | None = None,
    ) -> str:
        """Generate CREATE TABLE SQL.

        FK constraints involved in circular references are excluded — they
        are added later via ALTER TABLE ADD CONSTRAINT.
        """
        columns = []

        # Check if entity has an id field
        has_id = any(f.name == "id" for f in entity.fields)
        if not has_id:
            columns.append('"id" TEXT PRIMARY KEY')

        for field in entity.fields:
            col_def = self._generate_column_def(field)
            columns.append(col_def)

        # Append FK constraints from the relation registry (skip circular ones)
        if registry is not None:
            from dazzle_back.runtime.relation_loader import get_foreign_key_constraints

            fk_clauses = get_foreign_key_constraints(
                entity,
                registry,
                exclude_edges=circular_edges,
            )
            columns.extend(fk_clauses)

        table = self._qualified_table(entity.name)
        return f"CREATE TABLE IF NOT EXISTS {table} ({', '.join(columns)})"

    def _qualified_table(self, table_name: str) -> str:
        """Return schema-qualified table identifier."""
        if self.schema == "public":
            return quote_identifier(table_name)
        return f"{quote_identifier(self.schema)}.{quote_identifier(table_name)}"

    def _plan_deferred_fk_constraints(
        self,
        entities: list[EntitySpec],
        circular_edges: set[tuple[str, str]],
        entity_map: dict[str, EntitySpec],
    ) -> list[MigrationStep]:
        """Generate ALTER TABLE ADD CONSTRAINT steps for circular FK refs.

        These are emitted after all CREATE TABLE steps so that both sides of
        a circular reference exist before the FK constraint is applied.
        """
        steps: list[MigrationStep] = []
        for entity in entities:
            for field in entity.fields:
                if field.type.kind != "ref" or not field.type.ref_entity:
                    continue
                ref_entity = field.type.ref_entity
                if (entity.name, ref_entity) not in circular_edges:
                    continue

                constraint_name = f"fk_{entity.name}_{field.name}_{ref_entity}"
                table = self._qualified_table(entity.name)
                col = quote_identifier(field.name)
                ref_table = self._qualified_table(ref_entity)
                ref_col = quote_identifier("id")
                # Use DO block for idempotency (PG has no ADD CONSTRAINT IF NOT EXISTS)
                sql = (
                    f"DO $$ BEGIN "
                    f"ALTER TABLE {table} ADD CONSTRAINT {quote_identifier(constraint_name)} "
                    f"FOREIGN KEY ({col}) REFERENCES {ref_table}({ref_col}); "
                    f"EXCEPTION WHEN duplicate_object THEN NULL; END $$"
                )
                steps.append(
                    MigrationStep(
                        action=MigrationAction.ADD_CONSTRAINT,
                        table=entity.name,
                        column=field.name,
                        sql=sql,
                    )
                )
        return steps

    def _get_column_type(self, field: FieldSpec) -> str:
        """Get the appropriate PostgreSQL column type."""
        from dazzle_back.runtime.pg_backend import _field_type_to_postgres

        return _field_type_to_postgres(field.type)

    def _generate_column_def(self, field: FieldSpec) -> str:
        """Generate column definition for a field."""
        col_type = self._get_column_type(field)
        col_name = quote_identifier(field.name)
        parts = [col_name, col_type]

        if field.name == "id":
            parts.append("PRIMARY KEY")
        elif field.required:
            parts.append("NOT NULL")

        if field.unique:
            parts.append("UNIQUE")

        if field.default is not None:
            default_val = self._convert_default(field.default, field.type)
            if isinstance(default_val, str):
                parts.append(f"DEFAULT '{default_val}'")
            elif isinstance(default_val, bool):
                parts.append(f"DEFAULT {'TRUE' if default_val else 'FALSE'}")
            else:
                parts.append(f"DEFAULT {default_val}")

        return " ".join(parts)

    def _convert_default(self, value: Any, field_type: Any) -> Any:
        """Convert a default value for PostgreSQL."""
        from dazzle_back.runtime.pg_backend import _python_to_postgres

        return _python_to_postgres(value, field_type)

    def _generate_add_column_sql(self, table_name: str, field: FieldSpec) -> str:
        """Generate ALTER TABLE ADD COLUMN SQL."""
        col_type = self._get_column_type(field)
        table = self._qualified_table(table_name)
        col_name = quote_identifier(field.name)
        parts = [f"ALTER TABLE {table} ADD COLUMN {col_name} {col_type}"]

        if field.default is not None:
            default_val = self._convert_default(field.default, field.type)
            if isinstance(default_val, str):
                parts.append(f"DEFAULT '{default_val}'")
            elif isinstance(default_val, bool):
                parts.append(f"DEFAULT {'TRUE' if default_val else 'FALSE'}")
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
            from dazzle_back.specs.entity import ScalarType

            defaults: dict[ScalarType, Any] = {
                ScalarType.STR: "",
                ScalarType.TEXT: "",
                ScalarType.INT: 0,
                ScalarType.DECIMAL: 0.0,
                ScalarType.BOOL: False,
                ScalarType.UUID: "",
                ScalarType.EMAIL: "",
                ScalarType.URL: "",
                ScalarType.JSON: "{}",
            }
            return defaults.get(field.type.scalar_type)
        elif field.type.kind == "enum" and field.type.enum_values:
            return field.type.enum_values[0]
        return None

    def _generate_drop_not_null_sql(self, table_name: str, column_name: str) -> str:
        """Generate ALTER TABLE ... ALTER COLUMN ... DROP NOT NULL SQL."""
        table = self._qualified_table(table_name)
        col = quote_identifier(column_name)
        return f"ALTER TABLE {table} ALTER COLUMN {col} DROP NOT NULL"

    def _generate_index_sql(self, table_name: str, column_name: str) -> str:
        """Generate CREATE INDEX SQL."""
        schema_prefix = f"{self.schema}_" if self.schema != "public" else ""
        index_name = f"idx_{schema_prefix}{table_name}_{column_name}"
        table = self._qualified_table(table_name)
        col = quote_identifier(column_name)
        return f"CREATE INDEX IF NOT EXISTS {index_name} ON {table}({col})"


# =============================================================================
# Migration Executor
# =============================================================================


class MigrationExecutor:
    """
    Executes migration plans against the database.
    """

    def __init__(self, db_manager: DatabaseBackend):
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
                        cursor = conn.cursor()
                        cursor.execute(step.sql)
                        executed.append(step)
                    except Exception as e:
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
# Migration History
# =============================================================================


class MigrationHistory:
    """
    Tracks migration history in the database.

    Creates a _migrations table to track applied migrations.
    """

    TABLE_NAME = "_dazzle_migrations"

    def __init__(self, db_manager: DatabaseBackend):
        self.db = db_manager
        self._ensure_table()

    def _ensure_table(self) -> None:
        """Ensure migrations table exists."""
        sql = f"""
        CREATE TABLE IF NOT EXISTS {self.TABLE_NAME} (
            id SERIAL PRIMARY KEY,
            applied_at TEXT NOT NULL,
            action TEXT NOT NULL,
            table_name TEXT NOT NULL,
            column_name TEXT,
            sql_executed TEXT,
            details TEXT
        )
        """
        with self.db.connection() as conn:
            cursor = conn.cursor()
            cursor.execute(sql)

    def record_migration(self, step: MigrationStep) -> None:
        """Record an executed migration step."""
        import json

        sql = f"""
        INSERT INTO {self.TABLE_NAME}
        (applied_at, action, table_name, column_name, sql_executed, details)
        VALUES (%s, %s, %s, %s, %s, %s)
        """
        params = (
            datetime.now(UTC).isoformat(),
            step.action.value,
            step.table,
            step.column,
            step.sql,
            json.dumps(step.details) if step.details else None,
        )
        with self.db.connection() as conn:
            cursor = conn.cursor()
            cursor.execute(sql, params)

    def get_history(self) -> list[dict[str, Any]]:
        """Get migration history."""
        sql = f"SELECT * FROM {self.TABLE_NAME} ORDER BY id DESC"
        with self.db.connection() as conn:
            cursor = conn.cursor()
            cursor.execute(sql)
            return [dict(row) for row in cursor.fetchall()]


# =============================================================================
# High-Level API
# =============================================================================


_MIGRATION_LOCK_ID = 8_370_291_746  # arbitrary advisory lock id for Dazzle migrations


def auto_migrate(
    db_manager: DatabaseBackend,
    entities: list[EntitySpec],
    record_history: bool = True,
    schema: str = "public",
) -> MigrationPlan:
    """
    Automatically migrate database to match entity specifications.

    This is the main entry point for auto-migration. Uses a PostgreSQL
    advisory lock so that only one worker runs migrations concurrently
    (safe for multi-worker deployments).

    Args:
        db_manager: Database manager instance (PostgresBackend)
        entities: List of entity specifications
        record_history: Whether to record migration history
        schema: PostgreSQL schema to operate on (default: "public")

    Returns:
        The executed migration plan
    """
    with db_manager.connection() as conn:
        conn.execute("SELECT pg_advisory_lock(%s)", (_MIGRATION_LOCK_ID,))
        try:
            planner = MigrationPlanner(db_manager, schema=schema)
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
        finally:
            conn.execute("SELECT pg_advisory_unlock(%s)", (_MIGRATION_LOCK_ID,))


def plan_migrations(
    db_manager: DatabaseBackend,
    entities: list[EntitySpec],
    schema: str = "public",
) -> MigrationPlan:
    """
    Plan migrations without executing them.

    Useful for previewing what would happen.

    Args:
        db_manager: Database manager instance (PostgresBackend)
        entities: List of entity specifications
        schema: PostgreSQL schema to operate on (default: "public")

    Returns:
        Migration plan
    """
    planner = MigrationPlanner(db_manager, schema=schema)
    return planner.plan_migrations(entities)


# =============================================================================
# Framework Table: _dazzle_params (#572)
# =============================================================================


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
