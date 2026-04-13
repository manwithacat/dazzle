"""Adapter: ``PostgresBackend`` → fitness ``SnapshotSource`` protocol.

The fitness ledger reads pre/post row snapshots via the tiny ``SnapshotSource``
protocol (``fetch_rows(table, columns) -> list[dict]``). This adapter wraps
the Dazzle runtime's ``PostgresBackend.connection()`` so the fitness engine
can read directly from whatever database the example app is using.

Sync — matches ``PostgresBackend`` and the v1 ledger.
"""

from __future__ import annotations

from typing import Any

from psycopg import sql as pgsql


class PgSnapshotSource:
    """Read-only ``SnapshotSource`` backed by a ``PostgresBackend``."""

    def __init__(self, backend: Any) -> None:
        """Wrap an already-constructed ``PostgresBackend``.

        Args:
            backend: A ``dazzle_back.runtime.pg_backend.PostgresBackend`` or
                any object exposing a ``connection()`` context manager that
                yields a wrapper with ``.execute(sql, params)``.
        """
        self._backend = backend

    def fetch_rows(self, table: str, columns: list[str]) -> list[dict[str, Any]]:
        if not columns:
            raise ValueError("PgSnapshotSource.fetch_rows requires at least one column")

        col_sql = pgsql.SQL(", ").join(pgsql.Identifier(c) for c in columns)
        stmt = pgsql.SQL("SELECT {cols} FROM {table}").format(
            cols=col_sql,
            table=pgsql.Identifier(table),
        )

        with self._backend.connection() as conn:
            cursor = conn.execute(stmt)  # nosemgrep
            rows = cursor.fetchall()

        return list(rows)
