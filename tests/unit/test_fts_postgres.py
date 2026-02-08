"""Tests for PostgreSQL FTS backend and FTSManager routing."""

from __future__ import annotations

import sqlite3
from unittest.mock import MagicMock

from dazzle_back.runtime.fts_manager import FTSConfig, FTSManager, create_fts_manager
from dazzle_back.runtime.fts_postgres import PostgresFTSBackend

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mock_conn(fetchone_val=None, fetchall_val=None):
    """Create a mock database connection with cursor."""
    conn = MagicMock()
    cursor = MagicMock()
    conn.cursor.return_value = cursor
    if fetchone_val is not None:
        cursor.fetchone.return_value = fetchone_val
    if fetchall_val is not None:
        cursor.fetchall.return_value = fetchall_val
    return conn, cursor


def _make_entity_spec(name: str, fields: list[str]) -> MagicMock:
    """Create a mock EntitySpec with text fields."""
    from dazzle_back.specs.entity import ScalarType

    spec = MagicMock()
    spec.name = name
    mock_fields = []
    for f in fields:
        mf = MagicMock()
        mf.name = f
        mf.type.kind = "scalar"
        mf.type.scalar_type = ScalarType.STR
        mock_fields.append(mf)
    spec.fields = mock_fields
    return spec


# ===========================================================================
# PostgresFTSBackend tests
# ===========================================================================


class TestPostgresFTSBackendCreateIndex:
    def test_creates_gin_index(self):
        backend = PostgresFTSBackend()
        conn, cursor = _make_mock_conn()

        backend.create_fts_index(conn, "Task", ["title", "description"])

        sql = cursor.execute.call_args[0][0]
        assert "CREATE INDEX IF NOT EXISTS" in sql
        assert '"idx_Task_fts"' in sql
        assert "USING GIN" in sql
        assert "to_tsvector" in sql
        assert '"title"' in sql
        assert '"description"' in sql
        conn.commit.assert_called_once()

    def test_single_field_index(self):
        backend = PostgresFTSBackend()
        conn, cursor = _make_mock_conn()

        backend.create_fts_index(conn, "Note", ["body"])

        sql = cursor.execute.call_args[0][0]
        assert '"body"' in sql
        assert "|| ' ' ||" not in sql  # single field, no concatenation

    def test_custom_language(self):
        backend = PostgresFTSBackend(_language="spanish")
        conn, cursor = _make_mock_conn()

        backend.create_fts_index(conn, "Task", ["title"])

        sql = cursor.execute.call_args[0][0]
        assert "'spanish'" in sql


class TestPostgresFTSBackendSearch:
    def test_search_generates_correct_sql(self):
        backend = PostgresFTSBackend()
        conn, cursor = _make_mock_conn(fetchone_val=(3,), fetchall_val=[])

        ids, total = backend.search(conn, "Task", "hello", ["title", "description"])

        assert total == 3
        assert ids == []
        # Two execute calls: count + search
        assert cursor.execute.call_count == 2

        count_sql = cursor.execute.call_args_list[0][0][0]
        assert "COUNT(*)" in count_sql
        assert "plainto_tsquery" in count_sql
        assert "@@" in count_sql

        search_sql = cursor.execute.call_args_list[1][0][0]
        assert "ts_rank" in search_sql
        assert "ORDER BY rank DESC" in search_sql
        assert "LIMIT %s OFFSET %s" in search_sql

    def test_search_with_field_filter(self):
        backend = PostgresFTSBackend()
        conn, cursor = _make_mock_conn(
            fetchone_val=(1,),
            fetchall_val=[("id-1", 0.5)],
        )

        ids, total = backend.search(
            conn, "Task", "hello", ["title", "description"], fields=["title"]
        )

        assert total == 1
        assert ids == ["id-1"]

        # The count SQL should only use the 'title' tsvector
        count_sql = cursor.execute.call_args_list[0][0][0]
        assert '"title"' in count_sql
        # Description should NOT be in the count query
        assert '"description"' not in count_sql

    def test_search_invalid_fields_falls_back(self):
        backend = PostgresFTSBackend()
        conn, cursor = _make_mock_conn(fetchone_val=(0,), fetchall_val=[])

        backend.search(conn, "Task", "hello", ["title"], fields=["nonexistent"])

        # Should fall back to all searchable_fields
        count_sql = cursor.execute.call_args_list[0][0][0]
        assert '"title"' in count_sql

    def test_search_params_count(self):
        backend = PostgresFTSBackend()
        conn, cursor = _make_mock_conn(fetchone_val=(0,), fetchall_val=[])

        backend.search(conn, "Task", "test", ["title", "body"], limit=10, offset=5)

        # Count query: 1 param (query)
        count_params = cursor.execute.call_args_list[0][0][1]
        assert count_params == ("test",)

        # Search query: 2 params (query for ts_rank tsquery, query for WHERE tsquery) + limit + offset
        search_params = cursor.execute.call_args_list[1][0][1]
        assert search_params == ("test", "test", 10, 5)

    def test_search_dict_row_handling(self):
        backend = PostgresFTSBackend()
        conn, cursor = _make_mock_conn(
            fetchone_val={"count": 2},
            fetchall_val=[{"id": "a"}, {"id": "b"}],
        )

        ids, total = backend.search(conn, "Task", "hello", ["title"])

        assert total == 2
        assert ids == ["a", "b"]


class TestPostgresFTSBackendSearchWithSnippets:
    def test_generates_ts_headline(self):
        backend = PostgresFTSBackend()
        conn, cursor = _make_mock_conn(fetchall_val=[])

        backend.search_with_snippets(conn, "Task", "hello", ["title", "description"])

        sql = cursor.execute.call_args[0][0]
        assert "ts_headline" in sql
        assert "<mark>" in sql
        assert "</mark>" in sql
        assert '"title_snippet"' in sql
        assert '"description_snippet"' in sql

    def test_snippet_params_count(self):
        """Verify correct number of %s placeholders matches params."""
        backend = PostgresFTSBackend()
        conn, cursor = _make_mock_conn(fetchall_val=[])

        backend.search_with_snippets(conn, "Task", "hello", ["title", "body"], limit=50)

        params = cursor.execute.call_args[0][1]
        sql = cursor.execute.call_args[0][0]

        # Count %s in SQL
        placeholder_count = sql.count("%s")
        assert len(params) == placeholder_count

        # For 2 fields: 1 (ts_rank) + 2 (ts_headline) + 1 (WHERE) + 1 (LIMIT) = 5
        assert len(params) == 5
        assert params == ("hello", "hello", "hello", "hello", 50)

    def test_snippet_single_field(self):
        backend = PostgresFTSBackend()
        conn, cursor = _make_mock_conn(fetchall_val=[])

        backend.search_with_snippets(conn, "Task", "test", ["title"], limit=10)

        params = cursor.execute.call_args[0][1]
        # 1 (ts_rank) + 1 (ts_headline) + 1 (WHERE) + 1 (LIMIT) = 4
        assert len(params) == 4

    def test_snippet_tuple_row_parsing(self):
        backend = PostgresFTSBackend()
        conn, cursor = _make_mock_conn(
            fetchall_val=[("id-1", 0.8, "matched <mark>title</mark>")],
        )

        results = backend.search_with_snippets(conn, "Task", "title", ["title"])

        assert len(results) == 1
        assert results[0]["id"] == "id-1"
        assert results[0]["rank"] == 0.8
        assert results[0]["title_snippet"] == "matched <mark>title</mark>"

    def test_snippet_dict_row_parsing(self):
        backend = PostgresFTSBackend()
        conn, cursor = _make_mock_conn(
            fetchall_val=[{"id": "x", "rank": 0.5, "title_snippet": "hi"}],
        )

        results = backend.search_with_snippets(conn, "Task", "hi", ["title"])

        assert len(results) == 1
        assert results[0]["id"] == "x"


class TestPostgresFTSBackendRebuildIndex:
    def test_returns_row_count(self):
        backend = PostgresFTSBackend()
        conn, cursor = _make_mock_conn(fetchone_val=(42,))

        count = backend.rebuild_index(conn, "Task", ["title"])

        assert count == 42
        sql = cursor.execute.call_args[0][0]
        assert "COUNT(*)" in sql

    def test_dict_row_handling(self):
        backend = PostgresFTSBackend()
        conn, cursor = _make_mock_conn(fetchone_val={"count": 7})

        count = backend.rebuild_index(conn, "Task", ["title"])
        assert count == 7


# ===========================================================================
# FTSManager routing tests
# ===========================================================================


class TestFTSManagerRouting:
    def test_no_database_url_uses_sqlite(self):
        manager = FTSManager()
        assert not manager._use_postgres
        assert manager._pg_backend is None

    def test_postgres_url_creates_backend(self):
        manager = FTSManager(database_url="postgresql://localhost/test")
        assert manager._use_postgres
        assert isinstance(manager._pg_backend, PostgresFTSBackend)

    def test_postgres_scheme_variant(self):
        manager = FTSManager(database_url="postgres://localhost/test")
        assert manager._use_postgres

    def test_sqlite_url_does_not_create_backend(self):
        manager = FTSManager(database_url="sqlite:///test.db")
        assert not manager._use_postgres

    def test_create_fts_table_routes_to_postgres(self):
        manager = FTSManager(database_url="postgresql://localhost/test")
        manager._configs["Task"] = FTSConfig(entity_name="Task", searchable_fields=["title"])
        conn, cursor = _make_mock_conn()

        manager.create_fts_table(conn, "Task")

        # Should have called cursor.execute with CREATE INDEX
        sql = cursor.execute.call_args[0][0]
        assert "USING GIN" in sql
        assert "Task" in manager._initialized

    def test_create_fts_table_routes_to_sqlite(self, tmp_path):
        manager = FTSManager()
        manager._configs["Task"] = FTSConfig(entity_name="Task", searchable_fields=["title"])
        db = tmp_path / "test.db"
        conn = sqlite3.connect(str(db))

        # Need the main table for triggers
        conn.execute('CREATE TABLE "Task" ("id" TEXT, "title" TEXT)')

        manager.create_fts_table(conn, "Task")

        # Verify FTS5 table was created
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='Task_fts'"
        )
        assert cursor.fetchone() is not None
        conn.close()

    def test_search_routes_to_postgres(self):
        manager = FTSManager(database_url="postgresql://localhost/test")
        manager._configs["Task"] = FTSConfig(entity_name="Task", searchable_fields=["title"])
        conn, cursor = _make_mock_conn(fetchone_val=(0,), fetchall_val=[])

        ids, total = manager.search(conn, "Task", "hello")
        assert total == 0
        assert ids == []
        # Should use plainto_tsquery, not FTS5 MATCH
        sql = cursor.execute.call_args_list[0][0][0]
        assert "plainto_tsquery" in sql

    def test_search_with_snippets_routes_to_postgres(self):
        manager = FTSManager(database_url="postgresql://localhost/test")
        manager._configs["Task"] = FTSConfig(entity_name="Task", searchable_fields=["title"])
        conn, cursor = _make_mock_conn(fetchall_val=[])

        results = manager.search_with_snippets(conn, "Task", "hello")
        assert results == []
        sql = cursor.execute.call_args[0][0]
        assert "ts_headline" in sql

    def test_rebuild_index_routes_to_postgres(self):
        manager = FTSManager(database_url="postgresql://localhost/test")
        manager._configs["Task"] = FTSConfig(entity_name="Task", searchable_fields=["title"])
        conn, cursor = _make_mock_conn(fetchone_val=(5,))

        count = manager.rebuild_index(conn, "Task")
        assert count == 5

    def test_unconfigured_entity_returns_empty(self):
        manager = FTSManager(database_url="postgresql://localhost/test")
        conn, _ = _make_mock_conn()

        ids, total = manager.search(conn, "Unknown", "test")
        assert ids == []
        assert total == 0

        results = manager.search_with_snippets(conn, "Unknown", "test")
        assert results == []

        count = manager.rebuild_index(conn, "Unknown")
        assert count == 0


# ===========================================================================
# Convenience function tests
# ===========================================================================


class TestCreateFTSManager:
    def test_with_database_url(self):
        entity = _make_entity_spec("Task", ["title"])
        manager = create_fts_manager([entity], database_url="postgresql://localhost/db")

        assert manager._use_postgres
        assert manager.is_enabled("Task")

    def test_without_database_url(self):
        entity = _make_entity_spec("Task", ["title"])
        manager = create_fts_manager([entity])

        assert not manager._use_postgres
        assert manager.is_enabled("Task")

    def test_with_searchable_entities(self):
        entity = _make_entity_spec("Task", ["title", "body"])
        manager = create_fts_manager(
            [entity],
            searchable_entities={"Task": ["title"]},
            database_url="postgresql://localhost/db",
        )

        config = manager.get_config("Task")
        assert config is not None
        assert config.searchable_fields == ["title"]


# ===========================================================================
# SQLite functional tests (FTSManager, no mocking)
# ===========================================================================


class TestFTSManagerSQLiteFunctional:
    def test_sqlite_search_works(self, tmp_path):
        """Full round-trip: create table, insert, search."""
        db = tmp_path / "test.db"
        conn = sqlite3.connect(str(db))

        # Create main table and insert data
        conn.execute('CREATE TABLE "Task" ("id" TEXT, "title" TEXT)')
        conn.execute('INSERT INTO "Task" VALUES (?, ?)', ("1", "Buy groceries"))
        conn.execute('INSERT INTO "Task" VALUES (?, ?)', ("2", "Walk the dog"))
        conn.execute('INSERT INTO "Task" VALUES (?, ?)', ("3", "Buy milk"))
        conn.commit()

        manager = FTSManager()
        manager._configs["Task"] = FTSConfig(entity_name="Task", searchable_fields=["title"])
        manager.create_fts_table(conn, "Task")

        # Rebuild to populate FTS from existing rows
        count = manager.rebuild_index(conn, "Task")
        assert count == 3

        # Search
        ids, total = manager.search(conn, "Task", "buy")
        assert total == 2
        assert set(ids) == {"1", "3"}

        conn.close()

    def test_sqlite_snippets_work(self, tmp_path):
        db = tmp_path / "test.db"
        conn = sqlite3.connect(str(db))

        conn.execute('CREATE TABLE "Task" ("id" TEXT, "title" TEXT)')
        conn.execute('INSERT INTO "Task" VALUES (?, ?)', ("1", "Buy groceries"))
        conn.commit()

        manager = FTSManager()
        manager._configs["Task"] = FTSConfig(entity_name="Task", searchable_fields=["title"])
        manager.create_fts_table(conn, "Task")
        manager.rebuild_index(conn, "Task")

        results = manager.search_with_snippets(conn, "Task", "buy")
        assert len(results) == 1
        assert "<mark>" in results[0]["title_snippet"]

        conn.close()
