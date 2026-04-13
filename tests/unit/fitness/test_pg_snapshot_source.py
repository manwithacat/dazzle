"""Tests for PgSnapshotSource — adapts PostgresBackend to fitness's SnapshotSource protocol."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any

import pytest

from dazzle.fitness.pg_snapshot_source import PgSnapshotSource


class _FakeCursor:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows
        self.executed_sql: str | None = None

    def fetchall(self) -> list[dict[str, Any]]:
        return self._rows


class _FakeWrapper:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._cursor = _FakeCursor(rows)
        self.executed: list[Any] = []

    def execute(self, sql: Any, params: Any = None) -> _FakeCursor:
        self.executed.append(sql)
        return self._cursor


class _FakeBackend:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.wrapper = _FakeWrapper(rows)

    @contextmanager
    def connection(self) -> Any:
        yield self.wrapper


def test_fetch_rows_selects_requested_columns() -> None:
    rows = [{"id": 1, "status": "open"}, {"id": 2, "status": "closed"}]
    backend = _FakeBackend(rows)
    source = PgSnapshotSource(backend)

    result = source.fetch_rows(table="ticket", columns=["id", "status"])

    assert result == rows
    assert len(backend.wrapper.executed) == 1
    # The composed SQL must reference the table — psycopg Composed objects
    # stringify to the final SQL under as_string(None) but we just check the
    # repr contains both identifiers.
    sql_text = repr(backend.wrapper.executed[0])
    assert "ticket" in sql_text
    assert "id" in sql_text
    assert "status" in sql_text


def test_fetch_rows_with_empty_table_returns_empty_list() -> None:
    backend = _FakeBackend(rows=[])
    source = PgSnapshotSource(backend)

    result = source.fetch_rows(table="ticket", columns=["id"])

    assert result == []


def test_fetch_rows_rejects_empty_column_list() -> None:
    backend = _FakeBackend(rows=[])
    source = PgSnapshotSource(backend)

    with pytest.raises(ValueError, match="at least one column"):
        source.fetch_rows(table="ticket", columns=[])
