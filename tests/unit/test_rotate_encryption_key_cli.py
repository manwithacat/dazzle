"""`dazzle auth rotate-encryption-key` CLI tests (connection encryption-key rotation).

Mocks the store's rewrap so the CLI wiring + exit codes run without Postgres.
"""

import base64
from types import SimpleNamespace

import pytest
from typer.testing import CliRunner

from dazzle.cli import auth as auth_cli
from dazzle.cli.auth import auth_app

runner = CliRunner()

_KEY = base64.b64encode(b"k" * 32).decode()


def _patch(monkeypatch, result):
    service = SimpleNamespace(_store=SimpleNamespace(rewrap_all_connection_secrets=lambda: result))
    monkeypatch.setattr(auth_cli, "_get_auth_store", lambda database_url=None: service)


def _result(rewrapped, already_current, failed):
    from dazzle.http.runtime.auth.connections import RewrapResult

    return RewrapResult(rewrapped=rewrapped, already_current=already_current, failed=failed)


def test_rotate_happy_path(monkeypatch) -> None:
    monkeypatch.setenv("DAZZLE_CONNECTION_SECRET", _KEY)
    monkeypatch.setenv("DAZZLE_CONNECTION_SECRET_OLD", base64.b64encode(b"o" * 32).decode())
    _patch(monkeypatch, _result(3, 1, []))
    r = runner.invoke(auth_app, ["rotate-encryption-key"])
    assert r.exit_code == 0
    assert "Rewrapped 3" in r.output and "1 already current" in r.output


def test_rotate_reports_failed_and_exits_1(monkeypatch) -> None:
    monkeypatch.setenv("DAZZLE_CONNECTION_SECRET", _KEY)
    _patch(monkeypatch, _result(0, 0, ["conn-x", "conn-y"]))
    r = runner.invoke(auth_app, ["rotate-encryption-key"])
    assert r.exit_code == 1
    assert "DAZZLE_CONNECTION_SECRET_OLD" in r.output and "conn-x" in r.output


def test_rotate_requires_primary_key(monkeypatch) -> None:
    monkeypatch.delenv("DAZZLE_CONNECTION_SECRET", raising=False)
    # Should bail before touching the store.
    called = {"n": 0}

    def _boom():
        called["n"] += 1
        return _result(0, 0, [])

    monkeypatch.setattr(
        auth_cli,
        "_get_auth_store",
        lambda database_url=None: SimpleNamespace(
            _store=SimpleNamespace(rewrap_all_connection_secrets=_boom)
        ),
    )
    r = runner.invoke(auth_app, ["rotate-encryption-key"])
    assert r.exit_code == 1
    assert "DAZZLE_CONNECTION_SECRET" in r.output
    assert called["n"] == 0  # never reached the store


def test_rotate_warns_when_no_old_key_but_rewrapped(monkeypatch) -> None:
    monkeypatch.setenv("DAZZLE_CONNECTION_SECRET", _KEY)
    monkeypatch.delenv("DAZZLE_CONNECTION_SECRET_OLD", raising=False)
    _patch(monkeypatch, _result(2, 0, []))
    r = runner.invoke(auth_app, ["rotate-encryption-key"])
    assert r.exit_code == 0 and "DAZZLE_CONNECTION_SECRET_OLD is not set" in r.output


@pytest.fixture(autouse=True)
def _clean_old(monkeypatch):
    # Ensure no stray rotation key leaks between tests.
    monkeypatch.delenv("DAZZLE_CONNECTION_SECRET_OLD", raising=False)
