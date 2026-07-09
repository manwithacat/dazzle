"""Tests for actionable Postgres connection-error guidance (#1570).

The common local-Postgres traps (role missing / password auth / database
missing — the Debian/Ubuntu divergence documented in #1564) now get an
actionable hint appended, while unrelated OperationalErrors pass through
unchanged and the original exception stays chained.
"""

import psycopg
import pytest

from dazzle.http.runtime.pg_backend import (
    _connect_with_guidance,
    _connection_error_hint,
)


class TestConnectionErrorHint:
    def test_role_missing(self) -> None:
        hint = _connection_error_hint('connection failed: FATAL:  role "james" does not exist')
        assert hint is not None
        assert "createuser" in hint
        assert "databases.md" in hint

    def test_password_auth_failed(self) -> None:
        hint = _connection_error_hint('FATAL:  password authentication failed for user "dazzle"')
        assert hint is not None
        assert "password" in hint.lower()
        assert "127.0.0.1" in hint

    def test_no_password_supplied(self) -> None:
        hint = _connection_error_hint("fe_sendauth: no password supplied")
        assert hint is not None
        assert "password" in hint.lower()

    def test_database_missing(self) -> None:
        hint = _connection_error_hint('FATAL:  database "test" does not exist')
        assert hint is not None
        assert "createdb" in hint

    def test_unrecognised_returns_none(self) -> None:
        assert _connection_error_hint("could not connect to server: Connection refused") is None
        assert _connection_error_hint("some totally unrelated error") is None


class TestConnectWithGuidance:
    def test_augments_recognised_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def _boom(*a: object, **k: object) -> object:
            raise psycopg.OperationalError('FATAL:  role "james" does not exist')

        monkeypatch.setattr(psycopg, "connect", _boom)
        with pytest.raises(psycopg.OperationalError) as ei:
            _connect_with_guidance("postgresql://james@localhost/db")
        msg = str(ei.value)
        assert 'role "james" does not exist' in msg  # original preserved
        assert "createuser" in msg  # hint appended
        assert ei.value.__cause__ is not None  # chained

    def test_passes_through_unrecognised(self, monkeypatch: pytest.MonkeyPatch) -> None:
        orig = psycopg.OperationalError("connection refused")

        def _boom(*a: object, **k: object) -> object:
            raise orig

        monkeypatch.setattr(psycopg, "connect", _boom)
        with pytest.raises(psycopg.OperationalError) as ei:
            _connect_with_guidance("postgresql://localhost/db")
        # unchanged: same instance re-raised, no hint appended
        assert ei.value is orig
        assert "createuser" not in str(ei.value)

    def test_success_returns_connection(self, monkeypatch: pytest.MonkeyPatch) -> None:
        sentinel = object()
        monkeypatch.setattr(psycopg, "connect", lambda *a, **k: sentinel)
        assert _connect_with_guidance("postgresql://localhost/db") is sentinel
