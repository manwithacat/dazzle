"""Fake psycopg3 async connection for ``dazzle.db`` unit tests (#1341).

After #1341 the ``dazzle db`` CLI talks to Postgres through psycopg3. The read
helpers in :mod:`dazzle.db.connection` (``fetchval`` / ``fetchrow`` /
``fetchall``) all go through the cursor protocol::

    async with conn.cursor() as cur:
        await cur.execute(sql, params)
        row = await cur.fetchone()   # or cur.fetchall()

and DDL goes straight through ``await conn.execute(sql)``. This module fakes
exactly that surface, driven by a ``handler(sql, params)`` callback returning a
list of dict rows (matching the ``dict_row`` row factory). Every executed
statement is recorded on ``.executed`` for assertions.

The real-PG end-to-end proofs live in ``tests/integration`` — these unit fakes
just exercise the impl logic without a database.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from typing import Any

Rows = list[dict[str, Any]]
Handler = Callable[[str, "tuple[Any, ...]"], "Rows | None"]


class _FakeCursor:
    def __init__(self, conn: FakePgConn) -> None:
        self._conn = conn
        self._rows: Rows = []

    async def __aenter__(self) -> _FakeCursor:
        return self

    async def __aexit__(self, *exc: object) -> bool:
        return False

    async def execute(self, sql: str, params: Any = ()) -> _FakeCursor:
        self._rows = self._conn._dispatch(sql, tuple(params or ()))
        return self

    async def fetchone(self) -> dict[str, Any] | None:
        return self._rows[0] if self._rows else None

    async def fetchall(self) -> Rows:
        return list(self._rows)


class FakePgConn:
    """Minimal fake of a psycopg3 ``AsyncConnection`` for the ``dazzle db`` path."""

    def __init__(self, handler: Handler) -> None:
        self._handler = handler
        self.executed: list[tuple[str, tuple[Any, ...]]] = []

    def _dispatch(self, sql: str, params: tuple[Any, ...]) -> Rows:
        self.executed.append((sql, params))
        result = self._handler(sql, params)
        if isinstance(result, BaseException):
            raise result
        return result or []

    def cursor(self) -> _FakeCursor:
        return _FakeCursor(self)

    async def execute(self, sql: str, params: Any = ()) -> _FakeCursor:
        cur = _FakeCursor(self)
        await cur.execute(sql, params)
        return cur

    async def close(self) -> None:
        return None

    def execute_calls(self, needle: str) -> list[tuple[str, tuple[Any, ...]]]:
        """Recorded statements whose SQL contains ``needle``."""
        return [c for c in self.executed if needle in c[0]]


def scalar_conn(values: Any) -> FakePgConn:
    """A conn for ``fetchval``-style reads.

    ``values`` is either a single value returned for every ``SELECT`` read, or a
    list/tuple of values returned in order. A value that is an ``Exception`` is
    raised when reached (to exercise error paths). Each value is wrapped as a
    one-column row so the ``fetchval`` helper's ``next(iter(row.values()))``
    yields it.

    Non-``SELECT`` statements (DDL/DML such as TRUNCATE / DELETE) are recorded on
    ``.executed`` but return no rows and do **not** consume a queued scalar — so
    an interleaved ``execute`` between two counts keeps the ordering intact.
    """
    it: Iterator[Any] | None = iter(values) if isinstance(values, (list, tuple)) else None

    def handler(sql: str, params: tuple[Any, ...]) -> Rows:
        if not sql.lstrip().upper().startswith("SELECT"):
            return []
        value = next(it) if it is not None else values
        if isinstance(value, BaseException):
            raise value
        return [{"v": value}]

    return FakePgConn(handler)
