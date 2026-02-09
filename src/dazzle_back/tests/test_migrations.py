"""
Tests for auto-migration system.

Tests schema change detection and migration execution.
Requires DATABASE_URL (PostgreSQL) for integration tests.
"""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from dazzle_back.runtime.migrations import (
    ColumnInfo,
    MigrationAction,
    MigrationExecutor,
    MigrationHistory,
    MigrationPlanner,
    auto_migrate,
    plan_migrations,
)
from dazzle_back.runtime.repository import DatabaseManager
from dazzle_back.specs.entity import (
    EntitySpec,
    FieldSpec,
    FieldType,
    ScalarType,
)

pytestmark = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"),
    reason="DATABASE_URL not set — skipping migration tests that require DatabaseManager",
)

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def temp_db_path(tmp_path: Path) -> Path:
    """Create a temporary database path."""
    return tmp_path / "test.db"


@pytest.fixture
def db_manager(temp_db_path: Path) -> DatabaseManager:
    """Create a database manager with temporary database."""
    return DatabaseManager(temp_db_path)


@pytest.fixture
def task_entity_v1() -> EntitySpec:
    """Create a sample Task entity (version 1)."""
    return EntitySpec(
        name="Task",
        label="Task",
        fields=[
            FieldSpec(
                name="id",
                type=FieldType(kind="scalar", scalar_type=ScalarType.UUID),
                required=True,
            ),
            FieldSpec(
                name="title",
                type=FieldType(kind="scalar", scalar_type=ScalarType.STR, max_length=200),
                required=True,
            ),
            FieldSpec(
                name="status",
                type=FieldType(kind="enum", enum_values=["pending", "done"]),
                required=True,
                default="pending",
            ),
        ],
    )


@pytest.fixture
def task_entity_v2() -> EntitySpec:
    """Create Task entity with new field (version 2)."""
    return EntitySpec(
        name="Task",
        label="Task",
        fields=[
            FieldSpec(
                name="id",
                type=FieldType(kind="scalar", scalar_type=ScalarType.UUID),
                required=True,
            ),
            FieldSpec(
                name="title",
                type=FieldType(kind="scalar", scalar_type=ScalarType.STR, max_length=200),
                required=True,
            ),
            FieldSpec(
                name="status",
                type=FieldType(kind="enum", enum_values=["pending", "done"]),
                required=True,
                default="pending",
            ),
            FieldSpec(
                name="priority",
                type=FieldType(kind="enum", enum_values=["low", "medium", "high"]),
                required=True,
                default="medium",
            ),
            FieldSpec(
                name="description",
                type=FieldType(kind="scalar", scalar_type=ScalarType.TEXT),
                required=False,
            ),
        ],
    )


# =============================================================================
# MigrationPlanner Tests
# =============================================================================


class TestMigrationPlanner:
    """Test migration planning."""

    def test_plan_new_table(self, db_manager: DatabaseManager, task_entity_v1: EntitySpec) -> None:
        """Test planning migration for a new table."""
        planner = MigrationPlanner(db_manager)
        plan = planner.plan_migrations([task_entity_v1])

        assert not plan.is_empty
        assert len(plan.steps) >= 1

        # Should have a CREATE_TABLE step
        create_steps = [s for s in plan.steps if s.action == MigrationAction.CREATE_TABLE]
        assert len(create_steps) == 1
        assert create_steps[0].table == "Task"
        assert create_steps[0].sql is not None and "CREATE TABLE" in create_steps[0].sql

    def test_plan_no_changes(self, db_manager: DatabaseManager, task_entity_v1: EntitySpec) -> None:
        """Test planning with no changes needed."""
        # First, create the table
        db_manager.create_table(task_entity_v1)

        # Now plan - should have no changes
        planner = MigrationPlanner(db_manager)
        plan = planner.plan_migrations([task_entity_v1])

        # Should be empty (no changes needed)
        assert plan.is_empty

    def test_plan_add_column(
        self,
        db_manager: DatabaseManager,
        task_entity_v1: EntitySpec,
        task_entity_v2: EntitySpec,
    ) -> None:
        """Test planning migration to add a column."""
        # Create v1 table
        db_manager.create_table(task_entity_v1)

        # Plan migration to v2
        planner = MigrationPlanner(db_manager)
        plan = planner.plan_migrations([task_entity_v2])

        assert not plan.is_empty

        # Should have ADD_COLUMN steps for priority and description
        add_steps = [s for s in plan.steps if s.action == MigrationAction.ADD_COLUMN]
        column_names = {s.column for s in add_steps}
        assert "priority" in column_names
        assert "description" in column_names

    def test_plan_detects_removed_column(self, db_manager: DatabaseManager) -> None:
        """Test that removed columns are detected but marked as destructive."""
        # Create entity with extra column
        entity_v1 = EntitySpec(
            name="Task",
            fields=[
                FieldSpec(
                    name="id",
                    type=FieldType(kind="scalar", scalar_type=ScalarType.UUID),
                    required=True,
                ),
                FieldSpec(
                    name="title",
                    type=FieldType(kind="scalar", scalar_type=ScalarType.STR),
                    required=True,
                ),
                FieldSpec(
                    name="old_field",
                    type=FieldType(kind="scalar", scalar_type=ScalarType.STR),
                    required=False,
                ),
            ],
        )
        db_manager.create_table(entity_v1)

        # Entity without the old field
        entity_v2 = EntitySpec(
            name="Task",
            fields=[
                FieldSpec(
                    name="id",
                    type=FieldType(kind="scalar", scalar_type=ScalarType.UUID),
                    required=True,
                ),
                FieldSpec(
                    name="title",
                    type=FieldType(kind="scalar", scalar_type=ScalarType.STR),
                    required=True,
                ),
            ],
        )

        planner = MigrationPlanner(db_manager)
        plan = planner.plan_migrations([entity_v2])

        # Should have a warning about the removed column
        assert len(plan.warnings) > 0
        assert any("old_field" in w for w in plan.warnings)

        # Should have a destructive DROP_COLUMN step
        assert plan.has_destructive
        drop_steps = [s for s in plan.steps if s.action == MigrationAction.DROP_COLUMN]
        assert len(drop_steps) == 1
        assert drop_steps[0].column == "old_field"

    def test_plan_add_index(self, db_manager: DatabaseManager) -> None:
        """Test planning migration to add an index."""
        # Create entity without index
        entity_v1 = EntitySpec(
            name="Task",
            fields=[
                FieldSpec(
                    name="id",
                    type=FieldType(kind="scalar", scalar_type=ScalarType.UUID),
                    required=True,
                ),
                FieldSpec(
                    name="title",
                    type=FieldType(kind="scalar", scalar_type=ScalarType.STR),
                    required=True,
                    indexed=False,
                ),
            ],
        )
        db_manager.create_table(entity_v1)

        # Entity with index
        entity_v2 = EntitySpec(
            name="Task",
            fields=[
                FieldSpec(
                    name="id",
                    type=FieldType(kind="scalar", scalar_type=ScalarType.UUID),
                    required=True,
                ),
                FieldSpec(
                    name="title",
                    type=FieldType(kind="scalar", scalar_type=ScalarType.STR),
                    required=True,
                    indexed=True,
                ),
            ],
        )

        planner = MigrationPlanner(db_manager)
        plan = planner.plan_migrations([entity_v2])

        # Should have ADD_INDEX step
        index_steps = [s for s in plan.steps if s.action == MigrationAction.ADD_INDEX]
        assert len(index_steps) == 1
        assert index_steps[0].column == "title"


# =============================================================================
# MigrationExecutor Tests
# =============================================================================


class TestMigrationExecutor:
    """Test migration execution."""

    def test_execute_create_table(
        self, db_manager: DatabaseManager, task_entity_v1: EntitySpec
    ) -> None:
        """Test executing CREATE TABLE migration."""
        planner = MigrationPlanner(db_manager)
        plan = planner.plan_migrations([task_entity_v1])

        executor = MigrationExecutor(db_manager)
        executed = executor.execute(plan)

        # Should have executed the CREATE TABLE
        assert len(executed) >= 1
        assert db_manager.table_exists("Task")

    def test_execute_add_column(
        self,
        db_manager: DatabaseManager,
        task_entity_v1: EntitySpec,
        task_entity_v2: EntitySpec,
    ) -> None:
        """Test executing ADD COLUMN migration."""
        # Create v1 table
        db_manager.create_table(task_entity_v1)

        # Plan and execute migration to v2
        planner = MigrationPlanner(db_manager)
        plan = planner.plan_migrations([task_entity_v2])

        executor = MigrationExecutor(db_manager)
        executor.execute(plan)  # Execute the plan

        # Check new columns exist
        columns = db_manager.get_table_columns("Task")
        assert "priority" in columns
        assert "description" in columns

    def test_execute_safe_skips_destructive(self, db_manager: DatabaseManager) -> None:
        """Test that execute_safe skips destructive operations."""
        # Create entity with extra column
        entity_v1 = EntitySpec(
            name="Task",
            fields=[
                FieldSpec(
                    name="id",
                    type=FieldType(kind="scalar", scalar_type=ScalarType.UUID),
                    required=True,
                ),
                FieldSpec(
                    name="to_remove",
                    type=FieldType(kind="scalar", scalar_type=ScalarType.STR),
                    required=False,
                ),
            ],
        )
        db_manager.create_table(entity_v1)

        # Entity without the column
        entity_v2 = EntitySpec(
            name="Task",
            fields=[
                FieldSpec(
                    name="id",
                    type=FieldType(kind="scalar", scalar_type=ScalarType.UUID),
                    required=True,
                ),
            ],
        )

        planner = MigrationPlanner(db_manager)
        plan = planner.plan_migrations([entity_v2])

        # Execute safe
        executor = MigrationExecutor(db_manager)
        executed = executor.execute_safe(plan)

        # Should not have executed the DROP_COLUMN
        assert len(executed) == 0

        # Column should still exist
        columns = db_manager.get_table_columns("Task")
        assert "to_remove" in columns


# =============================================================================
# MigrationHistory Tests
# =============================================================================


class TestMigrationHistory:
    """Test migration history tracking."""

    def test_record_and_retrieve_history(
        self, db_manager: DatabaseManager, task_entity_v1: EntitySpec
    ) -> None:
        """Test recording and retrieving migration history."""
        # Execute a migration
        planner = MigrationPlanner(db_manager)
        plan = planner.plan_migrations([task_entity_v1])

        executor = MigrationExecutor(db_manager)
        executed = executor.execute(plan)

        # Record history
        history = MigrationHistory(db_manager)
        for step in executed:
            history.record_migration(step)

        # Retrieve history
        records = history.get_history()
        assert len(records) >= 1

        # Check first record
        record = records[0]
        assert record["table_name"] == "Task"
        assert "applied_at" in record


# =============================================================================
# High-Level API Tests
# =============================================================================


class TestAutoMigrate:
    """Test high-level auto_migrate function."""

    def test_auto_migrate_creates_tables(
        self, db_manager: DatabaseManager, task_entity_v1: EntitySpec
    ) -> None:
        """Test auto_migrate creates new tables."""
        plan = auto_migrate(db_manager, [task_entity_v1])

        assert db_manager.table_exists("Task")
        assert not plan.is_empty

    def test_auto_migrate_adds_columns(
        self,
        db_manager: DatabaseManager,
        task_entity_v1: EntitySpec,
        task_entity_v2: EntitySpec,
    ) -> None:
        """Test auto_migrate adds new columns."""
        # First migration - create table
        auto_migrate(db_manager, [task_entity_v1])

        # Second migration - add columns
        auto_migrate(db_manager, [task_entity_v2])

        # Check new columns exist
        columns = db_manager.get_table_columns("Task")
        assert "priority" in columns
        assert "description" in columns

    def test_auto_migrate_idempotent(
        self, db_manager: DatabaseManager, task_entity_v1: EntitySpec
    ) -> None:
        """Test auto_migrate is idempotent."""
        # First migration
        plan1 = auto_migrate(db_manager, [task_entity_v1])
        assert not plan1.is_empty

        # Second migration - should be no-op
        plan2 = auto_migrate(db_manager, [task_entity_v1])
        assert plan2.is_empty

    def test_plan_migrations_preview(
        self, db_manager: DatabaseManager, task_entity_v1: EntitySpec
    ) -> None:
        """Test plan_migrations for preview without execution."""
        plan = plan_migrations(db_manager, [task_entity_v1])

        # Plan should show what would happen
        assert not plan.is_empty

        # But table should not exist yet
        assert not db_manager.table_exists("Task")


# =============================================================================
# Multiple Entity Tests
# =============================================================================


class TestMultipleEntities:
    """Test migrations with multiple entities."""

    def test_migrate_multiple_entities(self, db_manager: DatabaseManager) -> None:
        """Test migrating multiple entities at once."""
        task_entity = EntitySpec(
            name="Task",
            fields=[
                FieldSpec(
                    name="id",
                    type=FieldType(kind="scalar", scalar_type=ScalarType.UUID),
                    required=True,
                ),
                FieldSpec(
                    name="title",
                    type=FieldType(kind="scalar", scalar_type=ScalarType.STR),
                    required=True,
                ),
            ],
        )

        user_entity = EntitySpec(
            name="User",
            fields=[
                FieldSpec(
                    name="id",
                    type=FieldType(kind="scalar", scalar_type=ScalarType.UUID),
                    required=True,
                ),
                FieldSpec(
                    name="email",
                    type=FieldType(kind="scalar", scalar_type=ScalarType.EMAIL),
                    required=True,
                ),
            ],
        )

        auto_migrate(db_manager, [task_entity, user_entity])

        assert db_manager.table_exists("Task")
        assert db_manager.table_exists("User")

    def test_migrate_entities_independently(self, db_manager: DatabaseManager) -> None:
        """Test that entity migrations are independent."""
        task_entity_v1 = EntitySpec(
            name="Task",
            fields=[
                FieldSpec(
                    name="id",
                    type=FieldType(kind="scalar", scalar_type=ScalarType.UUID),
                    required=True,
                ),
            ],
        )

        user_entity = EntitySpec(
            name="User",
            fields=[
                FieldSpec(
                    name="id",
                    type=FieldType(kind="scalar", scalar_type=ScalarType.UUID),
                    required=True,
                ),
            ],
        )

        # Create both tables
        auto_migrate(db_manager, [task_entity_v1, user_entity])

        # Add column only to Task
        task_entity_v2 = EntitySpec(
            name="Task",
            fields=[
                FieldSpec(
                    name="id",
                    type=FieldType(kind="scalar", scalar_type=ScalarType.UUID),
                    required=True,
                ),
                FieldSpec(
                    name="title",
                    type=FieldType(kind="scalar", scalar_type=ScalarType.STR),
                    required=True,
                ),
            ],
        )

        auto_migrate(db_manager, [task_entity_v2, user_entity])

        # Only Task should have the new column
        task_columns = db_manager.get_table_columns("Task")
        user_columns = db_manager.get_table_columns("User")

        assert "title" in task_columns
        assert "title" not in user_columns


# =============================================================================
# Money Expansion Migration Tests
# =============================================================================


class TestMoneyExpansionMigration:
    """Test DROP NOT NULL migration for money(GBP) expansion orphaned columns."""

    def _make_money_entity(self) -> EntitySpec:
        """Entity after money expansion — has price_minor + price_currency but no price."""
        return EntitySpec(
            name="Product",
            label="Product",
            fields=[
                FieldSpec(
                    name="id",
                    type=FieldType(kind="scalar", scalar_type=ScalarType.UUID),
                    required=True,
                ),
                FieldSpec(
                    name="name",
                    type=FieldType(kind="scalar", scalar_type=ScalarType.STR, max_length=200),
                    required=True,
                ),
                FieldSpec(
                    name="price_minor",
                    type=FieldType(kind="scalar", scalar_type=ScalarType.INT),
                    required=True,
                ),
                FieldSpec(
                    name="price_currency",
                    type=FieldType(kind="scalar", scalar_type=ScalarType.STR, max_length=3),
                    required=True,
                    default="GBP",
                ),
            ],
        )

    def test_postgres_detects_drop_not_null(self) -> None:
        """On Postgres, orphaned NOT NULL 'price' column triggers DROP NOT NULL step."""
        db = MagicMock()
        db.backend_type = "postgres"

        # Simulate existing DB schema: table exists with NOT NULL 'price' column
        existing_columns = [
            ColumnInfo(name="id", type="UUID", not_null=True, default=None, is_pk=True),
            ColumnInfo(name="name", type="TEXT", not_null=True, default=None, is_pk=False),
            ColumnInfo(name="price", type="TEXT", not_null=True, default=None, is_pk=False),
        ]

        entity = self._make_money_entity()

        planner = MigrationPlanner(db)

        with (
            patch(
                "dazzle_back.runtime.migrations._get_pg_table_schema",
                return_value=existing_columns,
            ),
            patch(
                "dazzle_back.runtime.migrations._get_pg_table_indexes",
                return_value=[],
            ),
        ):
            # Patch table existence check
            mock_cursor = MagicMock()
            mock_cursor.fetchone.return_value = ("Product",)
            mock_conn = MagicMock()
            mock_conn.cursor.return_value = mock_cursor
            db.connection.return_value.__enter__ = MagicMock(return_value=mock_conn)
            db.connection.return_value.__exit__ = MagicMock(return_value=False)

            plan = planner.plan_migrations([entity])

        drop_null_steps = [s for s in plan.steps if s.action == MigrationAction.DROP_NOT_NULL]
        assert len(drop_null_steps) == 1
        step = drop_null_steps[0]
        assert step.table == "Product"
        assert step.column == "price"
        assert step.is_destructive is False
        assert step.sql is not None
        assert "DROP NOT NULL" in step.sql
        assert '"price"' in step.sql

    def test_nullable_column_skipped(self) -> None:
        """If the orphaned column is already nullable, no DROP NOT NULL step is needed."""
        db = MagicMock()
        db.backend_type = "postgres"

        # price is nullable (not_null=False)
        existing_columns = [
            ColumnInfo(name="id", type="UUID", not_null=True, default=None, is_pk=True),
            ColumnInfo(name="name", type="TEXT", not_null=True, default=None, is_pk=False),
            ColumnInfo(name="price", type="TEXT", not_null=False, default=None, is_pk=False),
        ]

        entity = self._make_money_entity()

        planner = MigrationPlanner(db)

        with (
            patch(
                "dazzle_back.runtime.migrations._get_pg_table_schema",
                return_value=existing_columns,
            ),
            patch(
                "dazzle_back.runtime.migrations._get_pg_table_indexes",
                return_value=[],
            ),
        ):
            mock_cursor = MagicMock()
            mock_cursor.fetchone.return_value = ("Product",)
            mock_conn = MagicMock()
            mock_conn.cursor.return_value = mock_cursor
            db.connection.return_value.__enter__ = MagicMock(return_value=mock_conn)
            db.connection.return_value.__exit__ = MagicMock(return_value=False)

            plan = planner.plan_migrations([entity])

        drop_null_steps = [s for s in plan.steps if s.action == MigrationAction.DROP_NOT_NULL]
        assert len(drop_null_steps) == 0

    def test_sqlite_skipped(self) -> None:
        """On SQLite, no DROP NOT NULL step is emitted (ALTER COLUMN unsupported)."""
        db = MagicMock()
        db.backend_type = "sqlite"

        # Create a real SQLite table with NOT NULL 'price' column
        entity_v1 = EntitySpec(
            name="Product",
            label="Product",
            fields=[
                FieldSpec(
                    name="id",
                    type=FieldType(kind="scalar", scalar_type=ScalarType.UUID),
                    required=True,
                ),
                FieldSpec(
                    name="name",
                    type=FieldType(kind="scalar", scalar_type=ScalarType.STR, max_length=200),
                    required=True,
                ),
                FieldSpec(
                    name="price",
                    type=FieldType(kind="scalar", scalar_type=ScalarType.STR),
                    required=True,
                ),
            ],
        )

        # Use a real SQLite db for this test
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            real_db = DatabaseManager(db_path)
            real_db.create_table(entity_v1)

            entity_v2 = self._make_money_entity()
            planner = MigrationPlanner(real_db)
            plan = planner.plan_migrations([entity_v2])

        drop_null_steps = [s for s in plan.steps if s.action == MigrationAction.DROP_NOT_NULL]
        assert len(drop_null_steps) == 0
