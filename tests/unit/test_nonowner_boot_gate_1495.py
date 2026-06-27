"""#1495: events + process-consumer subsystems skip boot schema DDL in production.

Same class as #1462, for two subsystems that fix didn't cover. Under split-ownership
RLS the runtime/consumer serves as a non-owner role (dazzle_app, NOSUPERUSER
NOBYPASSRLS) that owns no tables. The event inbox/outbox and the process state
store used to run owner-only `CREATE INDEX` DDL at boot/first-use, which raises
InsufficientPrivilege for a non-owner — halting the event framework and spamming
the process consumer loop every ~5s. The three tables (_dazzle_event_inbox,
_dazzle_event_outbox, process_runs/process_tasks) are all migration-managed
(ensure_framework_schema + the ADR-0044 parity gate), so gating loses nothing.
"""

from __future__ import annotations

import asyncio

import pytest

from dazzle.http.events.inbox import EventInbox
from dazzle.http.events.outbox import EventOutbox

pytestmark = pytest.mark.gate


class _BoomConn:
    """Any DB call on this conn fails — proves create_table ran no DDL."""

    async def execute(self, *args: object, **kwargs: object) -> None:
        raise AssertionError("create_table issued DDL — boot DDL was NOT gated (#1495)")

    async def commit(self) -> None:
        raise AssertionError("create_table committed — boot DDL was NOT gated (#1495)")

    async def rollback(self) -> None:  # pragma: no cover - defensive
        raise AssertionError("create_table rolled back — boot DDL was NOT gated (#1495)")


@pytest.mark.parametrize("store_cls", [EventInbox, EventOutbox])
def test_event_create_table_runs_no_ddl_in_production(
    store_cls: type, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DAZZLE_ENV", "production")
    store = store_cls()
    # Must return cleanly without touching the (boom) connection.
    asyncio.run(store.create_table(_BoomConn()))


def test_event_inbox_create_table_runs_ddl_in_development(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Outside production the gate is open — create_table DOES try to run DDL."""
    monkeypatch.setenv("DAZZLE_ENV", "development")
    store = EventInbox()
    with pytest.raises(AssertionError, match="issued DDL"):
        asyncio.run(store.create_table(_BoomConn()))


def test_process_state_ensure_runs_no_ddl_in_production(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """PgProcessStateStore._ensure must short-circuit in production before opening
    a connection — proven by making psycopg.connect fail."""
    monkeypatch.setenv("DAZZLE_ENV", "production")
    from dazzle.core.process import pg_state

    def _boom_connect(*args: object, **kwargs: object) -> None:
        raise AssertionError("_ensure opened a connection — process boot DDL was NOT gated (#1495)")

    monkeypatch.setattr(pg_state.psycopg, "connect", _boom_connect)
    store = pg_state.PgProcessStateStore.__new__(pg_state.PgProcessStateStore)
    store._tables_ensured = False
    store._dsn = "postgresql://unused"
    store._ensure()  # must return cleanly without connecting
    assert store._tables_ensured is True
