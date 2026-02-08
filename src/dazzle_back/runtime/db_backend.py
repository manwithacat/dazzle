"""
Dual-backend database mixin for SQLite and PostgreSQL support.

Provides shared infrastructure for subsystems that need to support both
SQLite (zero-dependency dev fallback) and PostgreSQL (production).

Extracted from the proven AuthStore inline pattern.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any


class DualBackendMixin:
    """
    Mixin for subsystems supporting both SQLite and PostgreSQL.

    Usage:
        class MyStore(DualBackendMixin):
            def __init__(self, db_path=None, database_url=None):
                self._init_backend(db_path, database_url, default_path=".dazzle/my.db")
                self._init_db()
    """

    _use_postgres: bool
    _pg_url: str | None
    _db_path: Path | None

    def _init_backend(
        self,
        db_path: str | Path | None,
        database_url: str | None,
        *,
        default_path: str = ".dazzle/data.db",
    ) -> None:
        """
        Initialize backend selection.

        Args:
            db_path: Path to SQLite database file
            database_url: PostgreSQL connection URL (takes precedence over db_path)
            default_path: Default SQLite path when neither is provided
        """
        self._use_postgres = bool(database_url)

        if self._use_postgres:
            pg_url = database_url
            # Normalize Heroku's postgres:// to postgresql://
            if pg_url and pg_url.startswith("postgres://"):
                pg_url = pg_url.replace("postgres://", "postgresql://", 1)
            self._pg_url = pg_url
            self._db_path = None
        else:
            self._pg_url = None
            self._db_path = Path(db_path) if db_path else Path(default_path)
            self._db_path.parent.mkdir(parents=True, exist_ok=True)

    def _get_sync_connection(self) -> sqlite3.Connection | Any:
        """Get a database connection (SQLite or PostgreSQL)."""
        if self._use_postgres:
            import psycopg2
            import psycopg2.extras

            conn = psycopg2.connect(self._pg_url)
            conn.cursor_factory = psycopg2.extras.RealDictCursor
            return conn
        else:
            conn = sqlite3.connect(str(self._db_path))
            conn.row_factory = sqlite3.Row
            return conn

    @property
    def _ph(self) -> str:
        """Get the parameter placeholder for the current backend."""
        return "%s" if self._use_postgres else "?"

    @property
    def backend_type(self) -> str:
        """Get the backend type identifier."""
        return "postgres" if self._use_postgres else "sqlite"

    def _bool_to_db(self, value: bool) -> int | bool:
        """Convert boolean to database-native value."""
        return value if self._use_postgres else (1 if value else 0)

    def _db_to_bool(self, value: object) -> bool:
        """Convert database value to Python boolean."""
        return bool(value)

    def _execute_script(self, conn: Any, sql: str) -> None:
        """
        Execute a multi-statement SQL script.

        SQLite uses executescript(); PostgreSQL uses execute() per statement.
        """
        if self._use_postgres:
            cursor = conn.cursor()
            cursor.execute(sql)
        else:
            conn.executescript(sql)

    def _execute(self, query: str, params: tuple[object, ...] = ()) -> list[dict[str, Any]]:
        """Execute a query and return results as list of dicts."""
        if self._use_postgres:
            query = query.replace("?", "%s")

        conn = self._get_sync_connection()
        try:
            if self._use_postgres:
                cursor = conn.cursor()
                cursor.execute(query, params)
                if cursor.description:
                    return [dict(row) for row in cursor.fetchall()]
                conn.commit()
                return []
            else:
                cursor = conn.execute(query, params)
                if cursor.description:
                    return [dict(row) for row in cursor.fetchall()]
                conn.commit()
                return []
        finally:
            conn.close()

    def _execute_modify(self, query: str, params: tuple[object, ...] = ()) -> int:
        """Execute a modification query and return rowcount."""
        if self._use_postgres:
            query = query.replace("?", "%s")

        conn = self._get_sync_connection()
        try:
            if self._use_postgres:
                cursor = conn.cursor()
                cursor.execute(query, params)
                rowcount: int = cursor.rowcount
                conn.commit()
                return rowcount
            else:
                cursor = conn.execute(query, params)
                rowcount_s: int = cursor.rowcount
                conn.commit()
                return rowcount_s
        finally:
            conn.close()


class AsyncDualBackendMixin:
    """
    Async mixin for subsystems supporting both aiosqlite and asyncpg.

    Usage:
        class MyAdapter(AsyncDualBackendMixin):
            def __init__(self, db_path=":memory:", database_url=None):
                self._init_async_backend(db_path, database_url)
    """

    _use_postgres: bool
    _pg_url: str | None
    _async_db_path: str | None

    def _init_async_backend(
        self,
        db_path: str | Path | None,
        database_url: str | None,
    ) -> None:
        """
        Initialize async backend selection.

        Args:
            db_path: Path to SQLite database, or ":memory:"
            database_url: PostgreSQL connection URL (takes precedence)
        """
        self._use_postgres = bool(database_url)

        if self._use_postgres:
            pg_url = database_url
            if pg_url and pg_url.startswith("postgres://"):
                pg_url = pg_url.replace("postgres://", "postgresql://", 1)
            self._pg_url = pg_url
            self._async_db_path = None
        else:
            self._pg_url = None
            self._async_db_path = str(db_path) if db_path else ":memory:"

    async def _get_async_connection(self) -> Any:
        """Get an async database connection (aiosqlite or asyncpg)."""
        if self._use_postgres:
            import asyncpg

            return await asyncpg.connect(self._pg_url)
        else:
            import aiosqlite

            conn = await aiosqlite.connect(self._async_db_path)
            conn.row_factory = aiosqlite.Row
            return conn

    def _async_ph(self, index: int) -> str:
        """
        Get async parameter placeholder.

        asyncpg uses $1, $2, $3, etc. aiosqlite uses ?.
        """
        return f"${index}" if self._use_postgres else "?"

    @property
    def _async_backend_type(self) -> str:
        """Get the async backend type identifier."""
        return "postgres" if self._use_postgres else "sqlite"
