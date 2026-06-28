"""Auth stores construct without I/O — #1504 design-smell follow-up.

`AuthStore`/`TokenStore`/`DeviceRegistry` used to connect to PostgreSQL inside
`__init__` (eager `_init_db()`), so they could not even be *constructed* without a
live database. Construction is now pure: schema init is deferred to first use (or
an explicit `ensure_initialized()` at boot). These are true unit tests — no DB.
"""

from __future__ import annotations

import psycopg
import pytest

from dazzle.http.runtime.auth import AuthStore
from dazzle.http.runtime.device_registry import DeviceRegistry
from dazzle.http.runtime.token_store import TokenStore

# An unresolvable host: connecting would raise, so reaching the DB is observable.
BOGUS_URL = "postgresql://mock/test"


@pytest.mark.parametrize(
    "construct",
    [
        lambda: AuthStore(database_url=BOGUS_URL),
        lambda: TokenStore(database_url=BOGUS_URL),
        lambda: DeviceRegistry(database_url=BOGUS_URL),
    ],
    ids=["AuthStore", "TokenStore", "DeviceRegistry"],
)
def test_construction_does_no_io(construct) -> None:
    """Building a store against an unreachable DB must not raise — no I/O."""
    store = construct()
    assert store._initialized is False


def test_first_use_connects_and_fails_loudly() -> None:
    """The deferred init still runs on first use and surfaces a bad DB loudly —
    laziness must not swallow connection errors."""
    store = AuthStore(database_url=BOGUS_URL)
    with pytest.raises(psycopg.OperationalError):
        store.ensure_initialized()
    # Failure is retryable: the flag was reset, not latched on.
    assert store._initialized is False


def test_ensure_initialized_is_idempotent_after_success(monkeypatch) -> None:
    """Once initialized, ensure_initialized() is a no-op (no repeat DDL)."""
    store = AuthStore(database_url=BOGUS_URL)
    calls = {"n": 0}

    def _fake_init_db() -> None:
        calls["n"] += 1

    monkeypatch.setattr(store, "_init_db", _fake_init_db)
    store.ensure_initialized()
    store.ensure_initialized()
    assert calls["n"] == 1
    assert store._initialized is True


def test_ensure_initialized_is_single_flight_under_concurrency(monkeypatch) -> None:
    """Concurrency regression (#1504 review): under contention, _init_db must run
    EXACTLY once — never letting a second caller proceed against a half-built
    schema. A Barrier releases all threads into ensure_initialized simultaneously."""
    import threading

    store = AuthStore(database_url=BOGUS_URL)
    calls: list[int] = []
    n = 8
    barrier = threading.Barrier(n)

    def _counting_init() -> None:
        calls.append(1)  # list.append is atomic in CPython

    monkeypatch.setattr(store, "_init_db", _counting_init)

    def _worker() -> None:
        barrier.wait()
        store.ensure_initialized()

    threads = [threading.Thread(target=_worker) for _ in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(calls) == 1, f"_init_db ran {len(calls)} times — the init lock is broken"
    assert store._initialized is True
