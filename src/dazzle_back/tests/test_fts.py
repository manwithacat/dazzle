"""
Tests for full-text search functionality.

Tests FTS5 table creation, indexing, and search queries.
"""

import sqlite3
import tempfile
from pathlib import Path
from uuid import uuid4

import pytest

from dazzle_back.runtime.fts_manager import (
    FTSConfig,
    FTSManager,
    create_fts_manager,
    init_fts_tables,
)
from dazzle_back.specs.entity import (
    EntitySpec,
    FieldSpec,
    FieldType,
    ScalarType,
)

# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def task_entity():
    """Create a Task entity with searchable fields."""
    return EntitySpec(
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
                name="description",
                type=FieldType(kind="scalar", scalar_type=ScalarType.TEXT),
            ),
            FieldSpec(
                name="priority",
                type=FieldType(kind="scalar", scalar_type=ScalarType.INT),
            ),
        ],
    )


@pytest.fixture
def test_db(task_entity):
    """Create a test database with Task table."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    # Create Task table
    conn.execute("""
        CREATE TABLE Task (
            rowid INTEGER PRIMARY KEY AUTOINCREMENT,
            id TEXT UNIQUE NOT NULL,
            title TEXT NOT NULL,
            description TEXT,
            priority INTEGER
        )
    """)

    conn.commit()

    yield conn

    conn.close()
    Path(db_path).unlink(missing_ok=True)


@pytest.fixture
def populated_db(test_db):
    """Database with test data."""
    test_data = [
        ("Fix urgent bug in login page", "Users cannot login after update"),
        ("Add new dashboard feature", "Create a dashboard with charts and metrics"),
        ("Update documentation", "Review and update API documentation"),
        ("Performance optimization", "Improve query performance for large datasets"),
        ("Bug fix: email validation", "Fix email validation regex pattern"),
    ]

    for title, desc in test_data:
        task_id = str(uuid4())
        test_db.execute(
            "INSERT INTO Task (id, title, description) VALUES (?, ?, ?)",
            (task_id, title, desc),
        )

    test_db.commit()
    return test_db


# =============================================================================
# FTSConfig Tests
# =============================================================================


class TestFTSConfig:
    """Tests for FTSConfig."""

    def test_default_table_name(self):
        """Test default FTS table name generation."""
        config = FTSConfig(
            entity_name="Task",
            searchable_fields=["title", "description"],
        )

        assert config.fts_table_name == "Task_fts"

    def test_custom_table_name(self):
        """Test custom FTS table name."""
        config = FTSConfig(
            entity_name="Task",
            searchable_fields=["title"],
            fts_table_name="custom_fts",
        )

        assert config.fts_table_name == "custom_fts"

    def test_default_tokenizer(self):
        """Test default tokenizer."""
        config = FTSConfig(
            entity_name="Task",
            searchable_fields=["title"],
        )

        assert config.tokenizer == "porter"


# =============================================================================
# FTSManager Registration Tests
# =============================================================================


class TestFTSManagerRegistration:
    """Tests for FTSManager entity registration."""

    def test_register_entity_explicit_fields(self, task_entity):
        """Test registering entity with explicit searchable fields."""
        manager = FTSManager()
        config = manager.register_entity(task_entity, searchable_fields=["title"])

        assert config is not None
        assert config.searchable_fields == ["title"]

    def test_register_entity_auto_detect(self, task_entity):
        """Test auto-detection of searchable fields."""
        manager = FTSManager()
        config = manager.register_entity(task_entity)

        assert config is not None
        assert "title" in config.searchable_fields
        assert "description" in config.searchable_fields
        # priority is INT, should not be included
        assert "priority" not in config.searchable_fields

    def test_register_entity_no_text_fields(self):
        """Test entity with no text fields returns None."""
        entity = EntitySpec(
            name="Counter",
            fields=[
                FieldSpec(
                    name="id",
                    type=FieldType(kind="scalar", scalar_type=ScalarType.UUID),
                ),
                FieldSpec(
                    name="count",
                    type=FieldType(kind="scalar", scalar_type=ScalarType.INT),
                ),
            ],
        )

        manager = FTSManager()
        config = manager.register_entity(entity)

        assert config is None

    def test_is_enabled(self, task_entity):
        """Test is_enabled check."""
        manager = FTSManager()
        manager.register_entity(task_entity)

        assert manager.is_enabled("Task") is True
        assert manager.is_enabled("Unknown") is False

    def test_get_config(self, task_entity):
        """Test getting config for registered entity."""
        manager = FTSManager()
        manager.register_entity(task_entity, searchable_fields=["title"])

        config = manager.get_config("Task")
        assert config is not None
        assert config.entity_name == "Task"


# =============================================================================
# FTS Table Creation Tests
# =============================================================================


class TestFTSTableCreation:
    """Tests for FTS table creation."""

    def test_create_fts_table(self, task_entity, test_db):
        """Test FTS table creation."""
        manager = FTSManager()
        manager.register_entity(task_entity, searchable_fields=["title", "description"])

        manager.create_fts_table(test_db, "Task")

        # Check FTS table exists
        cursor = test_db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='Task_fts'"
        )
        assert cursor.fetchone() is not None

    def test_create_fts_table_idempotent(self, task_entity, test_db):
        """Test that creating FTS table twice is safe."""
        manager = FTSManager()
        manager.register_entity(task_entity)

        # Create twice
        manager.create_fts_table(test_db, "Task")
        manager.create_fts_table(test_db, "Task")

        # Should not raise error

    def test_create_triggers(self, task_entity, test_db):
        """Test that sync triggers are created."""
        manager = FTSManager()
        manager.register_entity(task_entity)
        manager.create_fts_table(test_db, "Task")

        # Check triggers exist
        cursor = test_db.execute(
            "SELECT name FROM sqlite_master WHERE type='trigger' AND name LIKE 'Task_fts%'"
        )
        triggers = [row[0] for row in cursor.fetchall()]

        assert "Task_fts_insert" in triggers
        assert "Task_fts_update" in triggers
        assert "Task_fts_delete" in triggers


# =============================================================================
# FTS Sync Tests
# =============================================================================


class TestFTSSync:
    """Tests for FTS synchronization with triggers."""

    def test_insert_syncs_to_fts(self, task_entity, test_db):
        """Test that inserts sync to FTS."""
        manager = FTSManager()
        manager.register_entity(task_entity)
        manager.create_fts_table(test_db, "Task")

        # Insert a task
        task_id = str(uuid4())
        test_db.execute(
            "INSERT INTO Task (id, title, description) VALUES (?, ?, ?)",
            (task_id, "Test Task", "Task description"),
        )
        test_db.commit()

        # Check FTS has the entry
        cursor = test_db.execute(
            "SELECT id FROM Task_fts WHERE Task_fts MATCH ?",
            ('"Test Task"',),
        )
        result = cursor.fetchone()
        assert result is not None
        assert result[0] == task_id

    def test_update_syncs_to_fts(self, task_entity, test_db):
        """Test that updates sync to FTS."""
        manager = FTSManager()
        manager.register_entity(task_entity)
        manager.create_fts_table(test_db, "Task")

        # Insert
        task_id = str(uuid4())
        test_db.execute(
            "INSERT INTO Task (id, title) VALUES (?, ?)",
            (task_id, "Original Title"),
        )
        test_db.commit()

        # Update
        test_db.execute(
            "UPDATE Task SET title = ? WHERE id = ?",
            ("Updated Title", task_id),
        )
        test_db.commit()

        # Search for new title
        cursor = test_db.execute(
            "SELECT id FROM Task_fts WHERE Task_fts MATCH ?",
            ('"Updated Title"',),
        )
        assert cursor.fetchone() is not None

        # Old title should not be found
        cursor = test_db.execute(
            "SELECT id FROM Task_fts WHERE Task_fts MATCH ?",
            ('"Original Title"',),
        )
        assert cursor.fetchone() is None

    def test_delete_syncs_to_fts(self, task_entity, test_db):
        """Test that deletes sync to FTS."""
        manager = FTSManager()
        manager.register_entity(task_entity)
        manager.create_fts_table(test_db, "Task")

        # Insert
        task_id = str(uuid4())
        test_db.execute(
            "INSERT INTO Task (id, title) VALUES (?, ?)",
            (task_id, "Delete Me"),
        )
        test_db.commit()

        # Delete
        test_db.execute("DELETE FROM Task WHERE id = ?", (task_id,))
        test_db.commit()

        # Should not be found
        cursor = test_db.execute(
            "SELECT id FROM Task_fts WHERE Task_fts MATCH ?",
            ('"Delete Me"',),
        )
        assert cursor.fetchone() is None


# =============================================================================
# Search Tests
# =============================================================================


class TestFTSSearch:
    """Tests for FTS search functionality."""

    def test_search_single_word(self, task_entity, populated_db):
        """Test searching for a single word."""
        manager = FTSManager()
        manager.register_entity(task_entity)
        manager.create_fts_table(populated_db, "Task")

        # Rebuild index from existing data
        manager.rebuild_index(populated_db, "Task")

        ids, total = manager.search(populated_db, "Task", "bug")

        assert total == 2  # "urgent bug" and "Bug fix"
        assert len(ids) == 2

    def test_search_multiple_words(self, task_entity, populated_db):
        """Test searching for multiple words (OR)."""
        manager = FTSManager()
        manager.register_entity(task_entity)
        manager.create_fts_table(populated_db, "Task")
        manager.rebuild_index(populated_db, "Task")

        ids, total = manager.search(populated_db, "Task", "dashboard charts")

        assert total >= 1

    def test_search_with_limit(self, task_entity, populated_db):
        """Test search with limit."""
        manager = FTSManager()
        manager.register_entity(task_entity)
        manager.create_fts_table(populated_db, "Task")
        manager.rebuild_index(populated_db, "Task")

        ids, total = manager.search(populated_db, "Task", "fix", limit=1)

        # Total should reflect all matches
        assert total >= 1
        # But only 1 returned
        assert len(ids) == 1

    def test_search_with_offset(self, task_entity, populated_db):
        """Test search with offset."""
        manager = FTSManager()
        manager.register_entity(task_entity)
        manager.create_fts_table(populated_db, "Task")
        manager.rebuild_index(populated_db, "Task")

        # Get all results
        all_ids, total = manager.search(populated_db, "Task", "bug")

        # Get with offset
        offset_ids, _ = manager.search(populated_db, "Task", "bug", offset=1)

        if total > 1:
            assert len(offset_ids) == total - 1

    def test_search_no_results(self, task_entity, populated_db):
        """Test search with no matches."""
        manager = FTSManager()
        manager.register_entity(task_entity)
        manager.create_fts_table(populated_db, "Task")
        manager.rebuild_index(populated_db, "Task")

        ids, total = manager.search(populated_db, "Task", "nonexistent12345")

        assert total == 0
        assert ids == []

    def test_search_unregistered_entity(self, populated_db):
        """Test searching unregistered entity returns empty."""
        manager = FTSManager()

        ids, total = manager.search(populated_db, "Unknown", "test")

        assert ids == []
        assert total == 0


# =============================================================================
# Rebuild Index Tests
# =============================================================================


class TestFTSRebuild:
    """Tests for FTS index rebuilding."""

    def test_rebuild_index(self, task_entity, populated_db):
        """Test rebuilding index from main table."""
        manager = FTSManager()
        manager.register_entity(task_entity)
        manager.create_fts_table(populated_db, "Task")

        count = manager.rebuild_index(populated_db, "Task")

        assert count == 5  # 5 test records

    def test_rebuild_unregistered_entity(self, populated_db):
        """Test rebuilding unregistered entity returns 0."""
        manager = FTSManager()

        count = manager.rebuild_index(populated_db, "Unknown")

        assert count == 0


# =============================================================================
# Search with Snippets Tests
# =============================================================================


class TestFTSSnippets:
    """Tests for search with highlighted snippets."""

    def test_search_with_snippets(self, task_entity, populated_db):
        """Test search returning snippets."""
        manager = FTSManager()
        manager.register_entity(task_entity)
        manager.create_fts_table(populated_db, "Task")
        manager.rebuild_index(populated_db, "Task")

        results = manager.search_with_snippets(populated_db, "Task", "bug")

        assert len(results) >= 1
        # Should have snippet columns
        first = results[0]
        assert "id" in first
        assert "rank" in first


# =============================================================================
# Convenience Functions Tests
# =============================================================================


class TestConvenienceFunctions:
    """Tests for convenience functions."""

    def test_create_fts_manager(self, task_entity):
        """Test create_fts_manager function."""
        manager = create_fts_manager([task_entity])

        assert manager.is_enabled("Task")

    def test_create_fts_manager_with_explicit_fields(self, task_entity):
        """Test create_fts_manager with explicit fields."""
        manager = create_fts_manager(
            [task_entity],
            searchable_entities={"Task": ["title"]},
        )

        config = manager.get_config("Task")
        assert config.searchable_fields == ["title"]

    def test_init_fts_tables(self, task_entity, test_db):
        """Test init_fts_tables function."""
        manager = create_fts_manager([task_entity])

        init_fts_tables(test_db, manager, [task_entity])

        # Check table exists
        cursor = test_db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='Task_fts'"
        )
        assert cursor.fetchone() is not None


# =============================================================================
# Query Escaping Tests
# =============================================================================


class TestQueryEscaping:
    """Tests for query escaping."""

    def test_escape_special_characters(self, task_entity, populated_db):
        """Test that special characters are escaped."""
        manager = FTSManager()
        manager.register_entity(task_entity)
        manager.create_fts_table(populated_db, "Task")
        manager.rebuild_index(populated_db, "Task")

        # This should not raise an error
        ids, total = manager.search(populated_db, "Task", 'test "quoted" text')

        # May or may not have results, but should not error

    def test_escape_operators(self, task_entity, populated_db):
        """Test that FTS operators are escaped."""
        manager = FTSManager()
        manager.register_entity(task_entity)
        manager.create_fts_table(populated_db, "Task")
        manager.rebuild_index(populated_db, "Task")

        # These should not raise errors
        manager.search(populated_db, "Task", "test AND this")
        manager.search(populated_db, "Task", "test OR that")
        manager.search(populated_db, "Task", "NOT something")
