"""The temporal `latest_one` column fallback must be reachable — proven, not assumed.

Why this exists
---------------
``repository._resolve_latest_one_fields`` probes the temporal end column by
guessing: execute with ``end_date``, catch, re-execute with ``effective_to``.
Nothing in ``pg_backend.py`` passes ``autocommit=``, so psycopg3 leaves the
transaction open and PostgreSQL **aborts** it the instant the first statement
errors. Every later statement on that connection then raises
``InFailedSqlTransaction`` until a rollback.

The existing coverage in ``test_temporal_runtime.py`` mocks ``cursor.execute``
with a ``MagicMock`` that never raises, so the fallback branch had **zero**
coverage and the defect was invisible. This module uses a hand-written fake
that encodes psycopg3's abort semantics, which turns "the retry cannot work"
from a reading of the code into an executable assertion.

This is a *semantic* fake, not an implementation mirror: it models a
third-party invariant (PostgreSQL transaction state), not the code under test.
That distinction is the point — a mock that can only ever pass teaches nothing.

What this does NOT catch
------------------------
Whether the chosen end-column name is the one the schema actually uses. That
needs a live PostgreSQL with a real temporal table; the structural rule that the
fallback must be preceded by a rollback is gated by
``test_no_db_retry_without_recovery.py``.
"""

from __future__ import annotations

import re
from typing import Any

import pytest

from dazzle.core import ir
from dazzle.http.runtime.repository import _resolve_latest_one_fields

_QUOTED_IDENTIFIER = re.compile(r'"([A-Za-z_][A-Za-z0-9_]*)"')


class _InFailedSqlTransaction(Exception):
    """Stands in for psycopg's error when a statement runs on an aborted txn."""


class _UndefinedColumn(Exception):
    """Stands in for psycopg's UndefinedColumn."""


class _AbortingCursor:
    """A cursor that models PostgreSQL's aborted-transaction state.

    ``db.connection()`` never enables autocommit, so the first failing statement
    aborts the transaction; the connection refuses all later statements until
    ``rollback()``. A fake that raises on every call — or never raises at all —
    cannot distinguish a working fallback from an unreachable one.

    Column existence is decided by the connection's ``schema`` set, so the happy
    path is genuinely happy rather than "always raises on the first try".
    """

    def __init__(self, conn: _AbortingConn, rows: list[dict[str, Any]]) -> None:
        self._conn = conn
        self._rows = rows
        self.executed: list[str] = []

    def execute(self, sql: str, params: Any = None) -> None:
        self.executed.append(sql)
        self._conn.statements += 1
        if self._conn.aborted:
            raise _InFailedSqlTransaction("current transaction is aborted")
        for column in _QUOTED_IDENTIFIER.findall(sql):
            if column not in self._conn.schema:
                self._conn.aborted = True
                raise _UndefinedColumn(f'column "{column}" does not exist')

    def fetchall(self) -> list[dict[str, Any]]:
        return list(self._rows)


class _AbortingConn:
    def __init__(
        self,
        rows: list[dict[str, Any]],
        *,
        schema: tuple[str, ...] = ("Employment", "id", "person", "end_date", "role"),
    ) -> None:
        self.aborted = False
        self.schema = set(schema)
        self.rollback_calls = 0
        self.statements = 0
        self._rows = rows

    def cursor(self) -> _AbortingCursor:
        return _AbortingCursor(self, self._rows)

    def rollback(self) -> None:
        self.rollback_calls += 1
        self.aborted = False


class _FakeDb:
    """Minimal `db` surface: `placeholder` + a `connection()` context manager."""

    placeholder = "%s"

    def __init__(self, conn: _AbortingConn) -> None:
        self._conn = conn
        self._ctx = self
        self.entered = False

    def __enter__(self) -> _AbortingConn:
        self.entered = True
        return self._conn

    def __exit__(self, *exc: object) -> bool:
        return False

    def connection(self) -> _FakeDb:
        return self._ctx


def _person_entity() -> ir.EntitySpec:
    return ir.EntitySpec(
        name="Person",
        fields=[
            ir.FieldSpec(name="id", type=ir.FieldType(kind=ir.FieldTypeKind.UUID)),
            ir.FieldSpec(
                name="current_employment",
                type=ir.FieldType(
                    kind=ir.FieldTypeKind.LATEST_ONE,
                    ref_entity="Employment",
                    via_field="person",
                ),
            ),
        ],
    )


def test_end_date_fallback_resolves_after_rollback() -> None:
    """The documented `effective_to` fallback must actually return rows.

    Without the rollback the second execute hits the aborted transaction and
    raises InFailedSqlTransaction, so this is the assertion that was missing.
    """
    rows_for_fallback = [{"id": "e1", "person": "p1", "role": "r1", "effective_to": None}]
    conn = _AbortingConn(
        rows_for_fallback, schema=("Employment", "id", "person", "role", "effective_to")
    )
    db = _FakeDb(conn)

    result = _resolve_latest_one_fields([{"id": "p1"}], _person_entity(), db)

    assert conn.rollback_calls == 1, (
        "the retry must be preceded by a rollback; on a non-autocommit "
        "connection the transaction is already aborted after the first error"
    )
    assert result[0]["current_employment"] == rows_for_fallback[0]


def test_end_date_fallback_needs_no_second_rollback_on_success() -> None:
    """One rollback is enough when the retry succeeds; a second would be noise."""
    conn = _AbortingConn(
        [{"id": "e1", "person": "p1", "effective_to": None}],
        schema=("Employment", "id", "person", "role", "effective_to"),
    )
    _resolve_latest_one_fields([{"id": "p1"}], _person_entity(), _FakeDb(conn))
    assert conn.rollback_calls == 1


def test_both_candidate_columns_missing_raises_named_error() -> None:
    """When neither end column exists, name both — not a raw driver error.

    Previously the second failure propagated as an opaque
    InFailedSqlTransaction, hiding the real cause entirely.
    """
    conn = _AbortingConn([], schema=("Employment", "id", "person", "role"))
    with pytest.raises(RuntimeError) as excinfo:
        _resolve_latest_one_fields([{"id": "p1"}], _person_entity(), _FakeDb(conn))

    message = str(excinfo.value)
    assert "end_date" in message and "effective_to" in message
    assert "Employment" in message
    assert conn.rollback_calls == 2, "both attempts must leave the transaction clean"


def test_first_attempt_success_does_not_roll_back() -> None:
    """The happy path must not roll back — that would be a behaviour change."""
    rows = [{"id": "e1", "person": "p1", "end_date": None}]
    conn = _AbortingConn(rows)
    result = _resolve_latest_one_fields([{"id": "p1"}], _person_entity(), _FakeDb(conn))
    assert conn.rollback_calls == 0
    assert result[0]["current_employment"] == rows[0]
