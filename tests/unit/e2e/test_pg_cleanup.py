"""Unit tests for `_pg_cleanup.terminate_stale_sessions` (#1072 Bug A)."""

from unittest.mock import MagicMock, patch

import pytest

from dazzle.e2e._pg_cleanup import terminate_stale_sessions


def test_empty_database_url_returns_zero() -> None:
    assert terminate_stale_sessions("") == 0


def test_psycopg_unavailable_returns_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    """If psycopg can't be imported, the cleanup is a no-op (best-effort)."""
    # Force the import to fail
    import builtins

    real_import = builtins.__import__

    def fake_import(name: str, *args: object, **kwargs: object) -> object:
        if name == "psycopg":
            raise ImportError("simulated missing psycopg")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    assert terminate_stale_sessions("postgresql://localhost/x") == 0


def test_connection_error_returns_zero() -> None:
    """A connection failure is best-effort — never raises."""
    with patch("psycopg.connect", side_effect=Exception("connection refused")):
        assert terminate_stale_sessions("postgresql://localhost/x") == 0


def test_terminates_idle_in_transaction_sessions() -> None:
    """When the cleanup query returns N true rows, terminate_stale_sessions returns N."""
    fake_cursor = MagicMock()
    # 3 sessions terminated, 1 failed (False)
    fake_cursor.fetchall.return_value = [(True,), (True,), (False,), (True,)]
    fake_conn = MagicMock()
    fake_conn.execute.return_value = fake_cursor

    fake_connect = MagicMock()
    fake_connect.return_value.__enter__.return_value = fake_conn
    fake_connect.return_value.__exit__.return_value = None

    with patch("psycopg.connect", fake_connect):
        terminated = terminate_stale_sessions("postgresql://localhost/x")

    assert terminated == 3
    # Verify the query parameters target the right states
    call_args = fake_conn.execute.call_args
    assert "state = ANY(%s)" in call_args[0][0]
    assert "current_database()" in call_args[0][0]
    states_passed = call_args[0][1][0]
    assert "idle in transaction" in states_passed
    assert "idle in transaction (aborted)" in states_passed


def test_zero_terminated_returns_zero() -> None:
    """No leaked sessions found → cleanup returns 0, no log noise."""
    fake_cursor = MagicMock()
    fake_cursor.fetchall.return_value = []
    fake_conn = MagicMock()
    fake_conn.execute.return_value = fake_cursor

    fake_connect = MagicMock()
    fake_connect.return_value.__enter__.return_value = fake_conn
    fake_connect.return_value.__exit__.return_value = None

    with patch("psycopg.connect", fake_connect):
        assert terminate_stale_sessions("postgresql://localhost/x") == 0
