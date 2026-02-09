"""
Tests for full-text search functionality.

Tests PostgreSQL tsvector/GIN index creation, search queries, and snippets.
"""

from __future__ import annotations

import os
from typing import Any
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

_requires_pg = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"),
    reason="FTS tests require PostgreSQL (DATABASE_URL)",
)

# Use a unique table name to avoid collisions with other test files
_FTS_TABLE = "FTSTask"

# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def task_entity() -> Any:
    """Create a Task entity with searchable fields."""
    return EntitySpec(
        name=_FTS_TABLE,
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
def pg_conn() -> Any:
    """Get a PostgreSQL connection with a clean FTSTask table."""
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        pytest.skip("DATABASE_URL not set")

    from dazzle_back.runtime.pg_backend import PostgresBackend

    db = PostgresBackend(database_url)
    with db.connection() as conn:
        cursor = conn.cursor()
        # Drop and recreate table for isolation
        cursor.execute(f'DROP TABLE IF EXISTS "{_FTS_TABLE}" CASCADE')
        cursor.execute(f"""
            CREATE TABLE "{_FTS_TABLE}" (
                "id" TEXT PRIMARY KEY,
                "title" TEXT NOT NULL,
                "description" TEXT,
                "priority" INTEGER
            )
        """)
        yield conn


@pytest.fixture
def populated_conn(pg_conn: Any) -> Any:
    """PostgreSQL connection with test data."""
    test_data = [
        ("Fix urgent bug in login page", "Users cannot login after update"),
        ("Add new dashboard feature", "Create a dashboard with charts and metrics"),
        ("Update documentation", "Review and update API documentation"),
        ("Performance optimization", "Improve query performance for large datasets"),
        ("Bug fix: email validation", "Fix email validation regex pattern"),
    ]

    cursor = pg_conn.cursor()
    for title, desc in test_data:
        task_id = str(uuid4())
        cursor.execute(
            f'INSERT INTO "{_FTS_TABLE}" ("id", "title", "description") VALUES (%s, %s, %s)',
            (task_id, title, desc),
        )

    return pg_conn


# =============================================================================
# FTSConfig Tests
# =============================================================================


class TestFTSConfig:
    """Tests for FTSConfig."""

    def test_default_table_name(self) -> None:
        """Test default FTS table name generation."""
        config = FTSConfig(
            entity_name="Task",
            searchable_fields=["title", "description"],
        )

        assert config.fts_table_name == "Task_fts"

    def test_custom_table_name(self) -> None:
        """Test custom FTS table name."""
        config = FTSConfig(
            entity_name="Task",
            searchable_fields=["title"],
            fts_table_name="custom_fts",
        )

        assert config.fts_table_name == "custom_fts"

    def test_default_tokenizer(self) -> None:
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

    def test_register_entity_explicit_fields(self, task_entity: Any) -> None:
        """Test registering entity with explicit searchable fields."""
        manager = FTSManager()
        config = manager.register_entity(task_entity, searchable_fields=["title"])

        assert config is not None
        assert config.searchable_fields == ["title"]

    def test_register_entity_auto_detect(self, task_entity: Any) -> None:
        """Test auto-detection of searchable fields."""
        manager = FTSManager()
        config = manager.register_entity(task_entity)

        assert config is not None
        assert "title" in config.searchable_fields
        assert "description" in config.searchable_fields
        # priority is INT, should not be included
        assert "priority" not in config.searchable_fields

    def test_register_entity_no_text_fields(self) -> None:
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

    def test_is_enabled(self, task_entity: Any) -> None:
        """Test is_enabled check."""
        manager = FTSManager()
        manager.register_entity(task_entity)

        assert manager.is_enabled(_FTS_TABLE) is True
        assert manager.is_enabled("Unknown") is False

    def test_get_config(self, task_entity: Any) -> None:
        """Test getting config for registered entity."""
        manager = FTSManager()
        manager.register_entity(task_entity, searchable_fields=["title"])

        config = manager.get_config(_FTS_TABLE)
        assert config is not None
        assert config.entity_name == _FTS_TABLE


# =============================================================================
# FTS Index Creation Tests
# =============================================================================


@_requires_pg
class TestFTSIndexCreation:
    """Tests for GIN index creation."""

    def test_create_fts_index(self, task_entity: Any, pg_conn: Any) -> None:
        """Test GIN index creation."""
        manager = FTSManager()
        manager.register_entity(task_entity, searchable_fields=["title", "description"])

        manager.create_fts_table(pg_conn, _FTS_TABLE)

        # Check GIN index exists
        cursor = pg_conn.cursor()
        cursor.execute(
            "SELECT indexname FROM pg_indexes WHERE tablename = %s AND indexname LIKE %s",
            (_FTS_TABLE, f"idx_{_FTS_TABLE}_fts%"),
        )
        assert cursor.fetchone() is not None

    def test_create_fts_index_idempotent(self, task_entity: Any, pg_conn: Any) -> None:
        """Test that creating GIN index twice is safe."""
        manager = FTSManager()
        manager.register_entity(task_entity)

        # Create twice — should not raise
        manager.create_fts_table(pg_conn, _FTS_TABLE)
        # Reset _initialized so it tries again
        manager._initialized.discard(_FTS_TABLE)
        manager.create_fts_table(pg_conn, _FTS_TABLE)


# =============================================================================
# FTS Auto-Sync Tests (GIN indexes auto-maintain on INSERT/UPDATE/DELETE)
# =============================================================================


@_requires_pg
class TestFTSSync:
    """Tests for GIN auto-sync on data changes."""

    def test_insert_searchable(self, task_entity: Any, pg_conn: Any) -> None:
        """Test that inserted data is searchable via tsvector."""
        manager = FTSManager()
        manager.register_entity(task_entity)
        manager.create_fts_table(pg_conn, _FTS_TABLE)

        # Insert a task
        task_id = str(uuid4())
        cursor = pg_conn.cursor()
        cursor.execute(
            f'INSERT INTO "{_FTS_TABLE}" ("id", "title", "description") VALUES (%s, %s, %s)',
            (task_id, "Test Task", "Task description"),
        )

        # Search via FTSManager
        ids, total = manager.search(pg_conn, _FTS_TABLE, "Test Task")

        assert total == 1
        assert task_id in ids

    def test_update_searchable(self, task_entity: Any, pg_conn: Any) -> None:
        """Test that updated data reflects in search results."""
        manager = FTSManager()
        manager.register_entity(task_entity)
        manager.create_fts_table(pg_conn, _FTS_TABLE)

        # Insert
        task_id = str(uuid4())
        cursor = pg_conn.cursor()
        cursor.execute(
            f'INSERT INTO "{_FTS_TABLE}" ("id", "title") VALUES (%s, %s)',
            (task_id, "Original Title"),
        )

        # Update
        cursor.execute(
            f'UPDATE "{_FTS_TABLE}" SET "title" = %s WHERE "id" = %s',
            ("Updated Title", task_id),
        )

        # Search for new title
        ids, total = manager.search(pg_conn, _FTS_TABLE, "Updated")
        assert total == 1

        # Old title should not be found
        ids, total = manager.search(pg_conn, _FTS_TABLE, "Original")
        assert total == 0

    def test_delete_removes_from_search(self, task_entity: Any, pg_conn: Any) -> None:
        """Test that deleted data disappears from search."""
        manager = FTSManager()
        manager.register_entity(task_entity)
        manager.create_fts_table(pg_conn, _FTS_TABLE)

        # Insert
        task_id = str(uuid4())
        cursor = pg_conn.cursor()
        cursor.execute(
            f'INSERT INTO "{_FTS_TABLE}" ("id", "title") VALUES (%s, %s)',
            (task_id, "Delete Me"),
        )

        # Verify findable
        ids, total = manager.search(pg_conn, _FTS_TABLE, "Delete")
        assert total == 1

        # Delete
        cursor.execute(f'DELETE FROM "{_FTS_TABLE}" WHERE "id" = %s', (task_id,))

        # Should not be found
        ids, total = manager.search(pg_conn, _FTS_TABLE, "Delete")
        assert total == 0


# =============================================================================
# Search Tests
# =============================================================================


@_requires_pg
class TestFTSSearch:
    """Tests for FTS search functionality."""

    def test_search_single_word(self, task_entity: Any, populated_conn: Any) -> None:
        """Test searching for a single word."""
        manager = FTSManager()
        manager.register_entity(task_entity)
        manager.create_fts_table(populated_conn, _FTS_TABLE)

        ids, total = manager.search(populated_conn, _FTS_TABLE, "bug")

        assert total == 2  # "urgent bug" and "Bug fix"
        assert len(ids) == 2

    def test_search_multiple_words(self, task_entity: Any, populated_conn: Any) -> None:
        """Test searching for multiple words."""
        manager = FTSManager()
        manager.register_entity(task_entity)
        manager.create_fts_table(populated_conn, _FTS_TABLE)

        ids, total = manager.search(populated_conn, _FTS_TABLE, "dashboard charts")

        assert total >= 1

    def test_search_with_limit(self, task_entity: Any, populated_conn: Any) -> None:
        """Test search with limit."""
        manager = FTSManager()
        manager.register_entity(task_entity)
        manager.create_fts_table(populated_conn, _FTS_TABLE)

        ids, total = manager.search(populated_conn, _FTS_TABLE, "fix", limit=1)

        # Total should reflect all matches
        assert total >= 1
        # But only 1 returned
        assert len(ids) == 1

    def test_search_with_offset(self, task_entity: Any, populated_conn: Any) -> None:
        """Test search with offset."""
        manager = FTSManager()
        manager.register_entity(task_entity)
        manager.create_fts_table(populated_conn, _FTS_TABLE)

        # Get all results
        all_ids, total = manager.search(populated_conn, _FTS_TABLE, "bug")

        # Get with offset
        offset_ids, _ = manager.search(populated_conn, _FTS_TABLE, "bug", offset=1)

        if total > 1:
            assert len(offset_ids) == total - 1

    def test_search_no_results(self, task_entity: Any, populated_conn: Any) -> None:
        """Test search with no matches."""
        manager = FTSManager()
        manager.register_entity(task_entity)
        manager.create_fts_table(populated_conn, _FTS_TABLE)

        ids, total = manager.search(populated_conn, _FTS_TABLE, "nonexistent12345")

        assert total == 0
        assert ids == []

    def test_search_unregistered_entity(self, populated_conn: Any) -> None:
        """Test searching unregistered entity returns empty."""
        manager = FTSManager()

        ids, total = manager.search(populated_conn, "Unknown", "test")

        assert ids == []
        assert total == 0


# =============================================================================
# Rebuild Index Tests
# =============================================================================


@_requires_pg
class TestFTSRebuild:
    """Tests for FTS index rebuilding."""

    def test_rebuild_index(self, task_entity: Any, populated_conn: Any) -> None:
        """Test rebuilding index from main table."""
        manager = FTSManager()
        manager.register_entity(task_entity)
        manager.create_fts_table(populated_conn, _FTS_TABLE)

        count = manager.rebuild_index(populated_conn, _FTS_TABLE)

        assert count == 5  # 5 test records

    def test_rebuild_unregistered_entity(self, populated_conn: Any) -> None:
        """Test rebuilding unregistered entity returns 0."""
        manager = FTSManager()

        count = manager.rebuild_index(populated_conn, "Unknown")

        assert count == 0


# =============================================================================
# Search with Snippets Tests
# =============================================================================


@_requires_pg
class TestFTSSnippets:
    """Tests for search with highlighted snippets."""

    def test_search_with_snippets(self, task_entity: Any, populated_conn: Any) -> None:
        """Test search returning snippets."""
        manager = FTSManager()
        manager.register_entity(task_entity)
        manager.create_fts_table(populated_conn, _FTS_TABLE)

        results = manager.search_with_snippets(populated_conn, _FTS_TABLE, "bug")

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

    def test_create_fts_manager(self, task_entity: Any) -> None:
        """Test create_fts_manager function."""
        manager = create_fts_manager([task_entity])

        assert manager.is_enabled(_FTS_TABLE)

    def test_create_fts_manager_with_explicit_fields(self, task_entity: Any) -> None:
        """Test create_fts_manager with explicit fields."""
        manager = create_fts_manager(
            [task_entity],
            searchable_entities={_FTS_TABLE: ["title"]},
        )

        config = manager.get_config(_FTS_TABLE)
        assert config is not None
        assert config.searchable_fields == ["title"]

    @_requires_pg
    def test_init_fts_tables(self, task_entity: Any, pg_conn: Any) -> None:
        """Test init_fts_tables function."""
        manager = create_fts_manager([task_entity])

        init_fts_tables(pg_conn, manager, [task_entity])

        # Check GIN index exists
        cursor = pg_conn.cursor()
        cursor.execute(
            "SELECT indexname FROM pg_indexes WHERE tablename = %s AND indexname LIKE %s",
            (_FTS_TABLE, f"idx_{_FTS_TABLE}_fts%"),
        )
        assert cursor.fetchone() is not None


# =============================================================================
# Query Escaping Tests
# =============================================================================


@_requires_pg
class TestQueryEscaping:
    """Tests for query escaping."""

    def test_escape_special_characters(self, task_entity: Any, populated_conn: Any) -> None:
        """Test that special characters are escaped."""
        manager = FTSManager()
        manager.register_entity(task_entity)
        manager.create_fts_table(populated_conn, _FTS_TABLE)

        # This should not raise an error (plainto_tsquery handles special chars)
        ids, total = manager.search(populated_conn, _FTS_TABLE, 'test "quoted" text')

        # May or may not have results, but should not error

    def test_escape_operators(self, task_entity: Any, populated_conn: Any) -> None:
        """Test that FTS operators are escaped."""
        manager = FTSManager()
        manager.register_entity(task_entity)
        manager.create_fts_table(populated_conn, _FTS_TABLE)

        # These should not raise errors (plainto_tsquery ignores operators)
        manager.search(populated_conn, _FTS_TABLE, "test AND this")
        manager.search(populated_conn, _FTS_TABLE, "test OR that")
        manager.search(populated_conn, _FTS_TABLE, "NOT something")
