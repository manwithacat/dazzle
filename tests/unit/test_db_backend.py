"""Tests for DualBackendMixin and AsyncDualBackendMixin."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from dazzle_back.runtime.db_backend import AsyncDualBackendMixin, DualBackendMixin

# ---------------------------------------------------------------------------
# Concrete test classes that use the mixins
# ---------------------------------------------------------------------------


class SyncStore(DualBackendMixin):
    """Concrete class for testing DualBackendMixin."""

    def __init__(
        self,
        db_path: str | Path | None = None,
        database_url: str | None = None,
    ):
        self._init_backend(db_path, database_url, default_path=".dazzle/test.db")


class AsyncStore(AsyncDualBackendMixin):
    """Concrete class for testing AsyncDualBackendMixin."""

    def __init__(
        self,
        db_path: str | Path | None = None,
        database_url: str | None = None,
    ):
        self._init_async_backend(db_path, database_url)


# ---------------------------------------------------------------------------
# DualBackendMixin — SQLite mode
# ---------------------------------------------------------------------------


class TestDualBackendMixinSQLite:
    """Tests for DualBackendMixin in SQLite mode."""

    def test_init_defaults_to_sqlite(self, tmp_path: Path) -> None:
        store = SyncStore(db_path=tmp_path / "test.db")
        assert store._use_postgres is False
        assert store._pg_url is None
        assert store._db_path == tmp_path / "test.db"

    def test_default_path_used_when_no_args(self) -> None:
        store = SyncStore()
        assert store._db_path == Path(".dazzle/test.db")

    def test_placeholder_sqlite(self, tmp_path: Path) -> None:
        store = SyncStore(db_path=tmp_path / "test.db")
        assert store._ph == "?"

    def test_backend_type_sqlite(self, tmp_path: Path) -> None:
        store = SyncStore(db_path=tmp_path / "test.db")
        assert store.backend_type == "sqlite"

    def test_bool_to_db_sqlite(self, tmp_path: Path) -> None:
        store = SyncStore(db_path=tmp_path / "test.db")
        assert store._bool_to_db(True) == 1
        assert store._bool_to_db(False) == 0

    def test_db_to_bool(self, tmp_path: Path) -> None:
        store = SyncStore(db_path=tmp_path / "test.db")
        assert store._db_to_bool(1) is True
        assert store._db_to_bool(0) is False
        assert store._db_to_bool(True) is True
        assert store._db_to_bool(False) is False

    def test_get_sync_connection_sqlite(self, tmp_path: Path) -> None:
        store = SyncStore(db_path=tmp_path / "test.db")
        conn = store._get_sync_connection()
        assert isinstance(conn, sqlite3.Connection)
        conn.close()

    def test_execute_script_sqlite(self, tmp_path: Path) -> None:
        store = SyncStore(db_path=tmp_path / "test.db")
        conn = store._get_sync_connection()
        store._execute_script(conn, "CREATE TABLE t (id TEXT PRIMARY KEY)")
        # Verify table exists
        cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='t'")
        assert cursor.fetchone() is not None
        conn.close()

    def test_execute_returns_rows(self, tmp_path: Path) -> None:
        store = SyncStore(db_path=tmp_path / "test.db")
        conn = store._get_sync_connection()
        conn.execute("CREATE TABLE t (id TEXT, name TEXT)")
        conn.execute("INSERT INTO t VALUES ('1', 'alice')")
        conn.commit()
        conn.close()

        rows = store._execute("SELECT * FROM t WHERE id = ?", ("1",))
        assert len(rows) == 1
        assert rows[0]["name"] == "alice"

    def test_execute_modify_returns_rowcount(self, tmp_path: Path) -> None:
        store = SyncStore(db_path=tmp_path / "test.db")
        conn = store._get_sync_connection()
        conn.execute("CREATE TABLE t (id TEXT, name TEXT)")
        conn.execute("INSERT INTO t VALUES ('1', 'alice')")
        conn.commit()
        conn.close()

        count = store._execute_modify("UPDATE t SET name = ? WHERE id = ?", ("bob", "1"))
        assert count == 1

    def test_parent_dirs_created(self, tmp_path: Path) -> None:
        deep_path = tmp_path / "a" / "b" / "c" / "test.db"
        store = SyncStore(db_path=deep_path)
        assert store._db_path is not None
        assert store._db_path.parent.exists()


# ---------------------------------------------------------------------------
# DualBackendMixin — PostgreSQL mode
# ---------------------------------------------------------------------------


class TestDualBackendMixinPostgres:
    """Tests for DualBackendMixin in PostgreSQL mode."""

    def test_init_with_database_url(self) -> None:
        store = SyncStore(database_url="postgresql://user:pass@localhost/db")
        assert store._use_postgres is True
        assert store._pg_url == "postgresql://user:pass@localhost/db"
        assert store._db_path is None

    def test_heroku_url_normalization(self) -> None:
        store = SyncStore(database_url="postgres://user:pass@host/db")
        assert store._pg_url == "postgresql://user:pass@host/db"

    def test_database_url_takes_precedence(self) -> None:
        store = SyncStore(
            db_path="/tmp/test.db",
            database_url="postgresql://localhost/db",
        )
        assert store._use_postgres is True
        assert store._db_path is None

    def test_placeholder_postgres(self) -> None:
        store = SyncStore(database_url="postgresql://localhost/db")
        assert store._ph == "%s"

    def test_backend_type_postgres(self) -> None:
        store = SyncStore(database_url="postgresql://localhost/db")
        assert store.backend_type == "postgres"

    def test_bool_to_db_postgres(self) -> None:
        store = SyncStore(database_url="postgresql://localhost/db")
        assert store._bool_to_db(True) is True
        assert store._bool_to_db(False) is False

    def test_execute_script_postgres(self) -> None:
        """Verify execute_script uses cursor.execute for Postgres."""
        store = SyncStore(database_url="postgresql://localhost/db")
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor

        store._execute_script(mock_conn, "CREATE TABLE t (id TEXT)")
        mock_cursor.execute.assert_called_once_with("CREATE TABLE t (id TEXT)")


# ---------------------------------------------------------------------------
# AsyncDualBackendMixin
# ---------------------------------------------------------------------------


class TestAsyncDualBackendMixin:
    """Tests for AsyncDualBackendMixin."""

    def test_init_sqlite_mode(self) -> None:
        store = AsyncStore(db_path=":memory:")
        assert store._use_postgres is False
        assert store._async_db_path == ":memory:"
        assert store._pg_url is None

    def test_init_postgres_mode(self) -> None:
        store = AsyncStore(database_url="postgresql://localhost/db")
        assert store._use_postgres is True
        assert store._pg_url == "postgresql://localhost/db"
        assert store._async_db_path is None

    def test_heroku_url_normalization(self) -> None:
        store = AsyncStore(database_url="postgres://user:pass@host/db")
        assert store._pg_url == "postgresql://user:pass@host/db"

    def test_async_ph_sqlite(self) -> None:
        store = AsyncStore(db_path=":memory:")
        assert store._async_ph(1) == "?"
        assert store._async_ph(2) == "?"

    def test_async_ph_postgres(self) -> None:
        store = AsyncStore(database_url="postgresql://localhost/db")
        assert store._async_ph(1) == "%s"
        assert store._async_ph(2) == "%s"
        assert store._async_ph(10) == "%s"

    def test_async_backend_type_sqlite(self) -> None:
        store = AsyncStore(db_path=":memory:")
        assert store._async_backend_type == "sqlite"

    def test_async_backend_type_postgres(self) -> None:
        store = AsyncStore(database_url="postgresql://localhost/db")
        assert store._async_backend_type == "postgres"

    def test_default_path(self) -> None:
        store = AsyncStore()
        assert store._async_db_path == ":memory:"  # None becomes ":memory:"

    @pytest.mark.asyncio
    async def test_get_async_connection_sqlite(self) -> None:
        import aiosqlite

        store = AsyncStore(db_path=":memory:")
        conn = await store._get_async_connection()
        assert isinstance(conn, aiosqlite.Connection)
        await conn.close()
