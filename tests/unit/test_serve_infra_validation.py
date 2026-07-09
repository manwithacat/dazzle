"""Tests for serve's infrastructure validation (#1561).

Redis is optional (Postgres event bus is the fallback), but if REDIS_URL is set
without the `redis` extra installed, serve must fail loud rather than boot with a
silently-dead Redis bus.
"""

import pytest
import typer

from dazzle.cli.runtime_impl import serve as serve_mod
from dazzle.cli.runtime_impl.serve import _validate_infrastructure


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DAZZLE_SKIP_INFRA_CHECK", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("REDIS_URL", raising=False)


def test_database_url_required(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(typer.Exit):
        _validate_infrastructure()


def test_redis_optional_when_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    """DATABASE_URL alone is sufficient — REDIS_URL is no longer mandated."""
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@127.0.0.1:5432/db")
    db, redis = _validate_infrastructure()
    assert db.startswith("postgresql://")
    assert redis == ""


def test_redis_url_set_but_extra_missing_fails_loud(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@127.0.0.1:5432/db")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.setattr(serve_mod, "_redis_extra_available", lambda: False)
    with pytest.raises(typer.Exit):
        _validate_infrastructure()


def test_redis_url_set_with_extra_present_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@127.0.0.1:5432/db")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.setattr(serve_mod, "_redis_extra_available", lambda: True)
    db, redis = _validate_infrastructure()
    assert db.startswith("postgresql://")
    assert redis == "redis://localhost:6379/0"


def test_skip_check_bypasses_all(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DAZZLE_SKIP_INFRA_CHECK", "1")
    # No DATABASE_URL, no REDIS_URL — skip mode returns empties without raising.
    db, redis = _validate_infrastructure()
    assert db == ""
    assert redis == ""
