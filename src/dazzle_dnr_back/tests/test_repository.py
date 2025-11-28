"""
Tests for SQLite repository module.

Tests database creation, CRUD operations, and persistence.
"""

from pathlib import Path
from uuid import uuid4

import pytest

from dazzle_dnr_back.runtime.model_generator import generate_entity_model
from dazzle_dnr_back.runtime.repository import (
    DatabaseManager,
    RepositoryFactory,
    SQLiteRepository,
    _python_to_sqlite,
    _sqlite_to_python,
)
from dazzle_dnr_back.specs.entity import (
    EntitySpec,
    FieldSpec,
    FieldType,
    ScalarType,
)

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def temp_db_path(tmp_path: Path) -> Path:
    """Create a temporary database path."""
    return tmp_path / "test.db"


@pytest.fixture
def task_entity() -> EntitySpec:
    """Create a sample Task entity spec."""
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
                name="description",
                type=FieldType(kind="scalar", scalar_type=ScalarType.TEXT),
                required=False,
            ),
            FieldSpec(
                name="priority",
                type=FieldType(kind="enum", enum_values=["low", "medium", "high"]),
                required=True,
                default="medium",
            ),
            FieldSpec(
                name="completed",
                type=FieldType(kind="scalar", scalar_type=ScalarType.BOOL),
                required=False,
                default=False,
            ),
        ],
    )


@pytest.fixture
def db_manager(temp_db_path: Path) -> DatabaseManager:
    """Create a database manager with temporary database."""
    return DatabaseManager(temp_db_path)


# =============================================================================
# Type Conversion Tests
# =============================================================================


class TestTypeConversion:
    """Test Python to SQLite type conversions."""

    def test_uuid_conversion(self):
        """Test UUID conversion."""
        test_uuid = uuid4()
        sqlite_val = _python_to_sqlite(test_uuid)
        assert sqlite_val == str(test_uuid)

        field_type = FieldType(kind="scalar", scalar_type=ScalarType.UUID)
        python_val = _sqlite_to_python(sqlite_val, field_type)
        assert python_val == test_uuid

    def test_bool_conversion(self):
        """Test boolean conversion."""
        field_type = FieldType(kind="scalar", scalar_type=ScalarType.BOOL)

        assert _python_to_sqlite(True) == 1
        assert _python_to_sqlite(False) == 0

        assert _sqlite_to_python(1, field_type) is True
        assert _sqlite_to_python(0, field_type) is False

    def test_none_conversion(self):
        """Test None handling."""
        assert _python_to_sqlite(None) is None
        assert _sqlite_to_python(None, None) is None

    def test_dict_conversion(self):
        """Test dict/JSON conversion."""
        test_dict = {"key": "value", "nested": {"a": 1}}
        sqlite_val = _python_to_sqlite(test_dict)
        assert isinstance(sqlite_val, str)

        field_type = FieldType(kind="scalar", scalar_type=ScalarType.JSON)
        python_val = _sqlite_to_python(sqlite_val, field_type)
        assert python_val == test_dict


# =============================================================================
# DatabaseManager Tests
# =============================================================================


class TestDatabaseManager:
    """Test database manager functionality."""

    def test_create_database(self, db_manager: DatabaseManager, temp_db_path: Path):
        """Test database file creation."""
        # Initially the file shouldn't exist
        assert not temp_db_path.exists()

        # After connecting and creating a table, it should exist
        with db_manager.connection() as conn:
            conn.execute("SELECT 1")

        assert temp_db_path.exists()

    def test_create_table(self, db_manager: DatabaseManager, task_entity: EntitySpec):
        """Test table creation from EntitySpec."""
        db_manager.create_table(task_entity)

        # Verify table exists
        assert db_manager.table_exists("Task")

        # Verify columns
        columns = db_manager.get_table_columns("Task")
        assert "id" in columns
        assert "title" in columns
        assert "description" in columns
        assert "priority" in columns
        assert "completed" in columns

    def test_create_all_tables(self, db_manager: DatabaseManager, task_entity: EntitySpec):
        """Test creating multiple tables."""
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

        db_manager.create_all_tables([task_entity, user_entity])

        assert db_manager.table_exists("Task")
        assert db_manager.table_exists("User")


# =============================================================================
# SQLiteRepository Tests
# =============================================================================


class TestSQLiteRepository:
    """Test SQLite repository CRUD operations."""

    @pytest.fixture
    def repository(
        self, db_manager: DatabaseManager, task_entity: EntitySpec
    ) -> SQLiteRepository:
        """Create a Task repository."""
        db_manager.create_table(task_entity)
        model = generate_entity_model(task_entity)
        return SQLiteRepository(
            db_manager=db_manager,
            entity_spec=task_entity,
            model_class=model,
        )

    @pytest.mark.asyncio
    async def test_create(self, repository: SQLiteRepository):
        """Test creating an entity."""
        task_id = uuid4()
        data = {
            "id": task_id,
            "title": "Test Task",
            "description": "A test task",
            "priority": "high",
            "completed": False,
        }

        result = await repository.create(data)

        assert result.id == task_id
        assert result.title == "Test Task"
        assert result.priority == "high"

    @pytest.mark.asyncio
    async def test_read(self, repository: SQLiteRepository):
        """Test reading an entity by ID."""
        task_id = uuid4()
        data = {
            "id": task_id,
            "title": "Read Test",
            "priority": "low",
        }
        await repository.create(data)

        result = await repository.read(task_id)

        assert result is not None
        assert result.id == task_id
        assert result.title == "Read Test"

    @pytest.mark.asyncio
    async def test_read_not_found(self, repository: SQLiteRepository):
        """Test reading a non-existent entity."""
        result = await repository.read(uuid4())
        assert result is None

    @pytest.mark.asyncio
    async def test_update(self, repository: SQLiteRepository):
        """Test updating an entity."""
        task_id = uuid4()
        await repository.create({
            "id": task_id,
            "title": "Original",
            "priority": "low",
        })

        result = await repository.update(task_id, {"title": "Updated"})

        assert result is not None
        assert result.title == "Updated"
        assert result.priority == "low"  # Unchanged

    @pytest.mark.asyncio
    async def test_update_not_found(self, repository: SQLiteRepository):
        """Test updating a non-existent entity."""
        result = await repository.update(uuid4(), {"title": "New"})
        assert result is None

    @pytest.mark.asyncio
    async def test_delete(self, repository: SQLiteRepository):
        """Test deleting an entity."""
        task_id = uuid4()
        await repository.create({
            "id": task_id,
            "title": "To Delete",
            "priority": "medium",
        })

        result = await repository.delete(task_id)
        assert result is True

        # Verify it's gone
        assert await repository.read(task_id) is None

    @pytest.mark.asyncio
    async def test_delete_not_found(self, repository: SQLiteRepository):
        """Test deleting a non-existent entity."""
        result = await repository.delete(uuid4())
        assert result is False

    @pytest.mark.asyncio
    async def test_list(self, repository: SQLiteRepository):
        """Test listing entities with pagination."""
        # Create multiple tasks
        for i in range(5):
            await repository.create({
                "id": uuid4(),
                "title": f"Task {i}",
                "priority": "medium",
            })

        result = await repository.list(page=1, page_size=3)

        assert result["total"] == 5
        assert len(result["items"]) == 3
        assert result["page"] == 1
        assert result["page_size"] == 3

    @pytest.mark.asyncio
    async def test_list_with_filter(self, repository: SQLiteRepository):
        """Test listing entities with filters."""
        await repository.create({
            "id": uuid4(),
            "title": "High Priority",
            "priority": "high",
        })
        await repository.create({
            "id": uuid4(),
            "title": "Low Priority",
            "priority": "low",
        })

        result = await repository.list(filters={"priority": "high"})

        assert result["total"] == 1
        assert result["items"][0].priority == "high"

    @pytest.mark.asyncio
    async def test_exists(self, repository: SQLiteRepository):
        """Test exists check."""
        task_id = uuid4()
        await repository.create({
            "id": task_id,
            "title": "Exists Test",
            "priority": "medium",
        })

        assert await repository.exists(task_id) is True
        assert await repository.exists(uuid4()) is False


# =============================================================================
# RepositoryFactory Tests
# =============================================================================


class TestRepositoryFactory:
    """Test repository factory functionality."""

    def test_create_repository(
        self, db_manager: DatabaseManager, task_entity: EntitySpec
    ):
        """Test creating a repository via factory."""
        db_manager.create_table(task_entity)
        model = generate_entity_model(task_entity)

        factory = RepositoryFactory(db_manager, {"Task": model})
        repo = factory.create_repository(task_entity)

        assert repo is not None
        assert repo.table_name == "Task"

    def test_create_all_repositories(
        self, db_manager: DatabaseManager, task_entity: EntitySpec
    ):
        """Test creating multiple repositories."""
        user_entity = EntitySpec(
            name="User",
            fields=[
                FieldSpec(
                    name="id",
                    type=FieldType(kind="scalar", scalar_type=ScalarType.UUID),
                    required=True,
                ),
                FieldSpec(
                    name="name",
                    type=FieldType(kind="scalar", scalar_type=ScalarType.STR),
                    required=True,
                ),
            ],
        )

        db_manager.create_all_tables([task_entity, user_entity])

        task_model = generate_entity_model(task_entity)
        user_model = generate_entity_model(user_entity)

        factory = RepositoryFactory(
            db_manager, {"Task": task_model, "User": user_model}
        )
        repos = factory.create_all_repositories([task_entity, user_entity])

        assert len(repos) == 2
        assert "Task" in repos
        assert "User" in repos


# =============================================================================
# Persistence Tests
# =============================================================================


class TestPersistence:
    """Test data persistence across database reconnections."""

    @pytest.mark.asyncio
    async def test_data_persists(self, temp_db_path: Path, task_entity: EntitySpec):
        """Test that data persists after closing and reopening the database."""
        task_id = uuid4()

        # Create data with first connection
        db1 = DatabaseManager(temp_db_path)
        db1.create_table(task_entity)
        model = generate_entity_model(task_entity)
        repo1 = SQLiteRepository(db1, task_entity, model)

        await repo1.create({
            "id": task_id,
            "title": "Persistent Task",
            "priority": "high",
        })

        # Reconnect with new manager
        db2 = DatabaseManager(temp_db_path)
        repo2 = SQLiteRepository(db2, task_entity, model)

        # Data should still be there
        result = await repo2.read(task_id)

        assert result is not None
        assert result.id == task_id
        assert result.title == "Persistent Task"
