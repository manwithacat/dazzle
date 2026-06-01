"""#1319 / ADR-0032 Slice B — transition→atomic shared-transaction atomicity (real PG).

A status transition carrying `invoke <flow>` runs the named atomic flow in the
SAME transaction as the status write:

* **commit together** — the status changes AND the flow's effect row is created;
* **roll back together** — if the flow fails, the status stays unchanged and no
  effect row is left behind.

The `transition_atomic` fixture: an `Order` whose `submitted -> fulfilled`
transition invokes `fulfil_order(order: self, warehouse: input.warehouse)`, which
creates a `Shipment`. `Shipment.order` is `unique`, so pre-seeding a shipment
forces a deterministic flow failure to prove the rollback.

Marked ``postgres`` (+ ``e2e``): skipped without ``TEST_DATABASE_URL`` /
``DATABASE_URL``; CI's ``postgres-tests`` job runs it against real Postgres.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

if TYPE_CHECKING:
    import httpx

pytestmark = [pytest.mark.e2e, pytest.mark.postgres]

_PG_URL = os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL")
_ROOT = Path("fixtures/transition_atomic")
_BASE_URL = "http://transition-atomic.local"
_ADMIN_EMAIL = "admin@ta.test"
_PASSWORD = "ta-test-password"  # nosec B105 — disposable scratch DB only


def _mk_id() -> str:
    return str(uuid.uuid4())


class _App:
    def __init__(self, transport: Any, db_url: str) -> None:
        self.transport = transport
        self.db_url = db_url

    async def admin_client(self) -> httpx.AsyncClient:
        import httpx

        from dazzle.cli.rbac import _login

        client = httpx.AsyncClient(
            transport=self.transport, base_url=_BASE_URL, follow_redirects=True
        )
        await _login(client, _BASE_URL, _ADMIN_EMAIL, _PASSWORD)
        return client


async def _booted() -> AsyncIterator[_App]:
    if not _PG_URL:
        pytest.skip("no TEST_DATABASE_URL / DATABASE_URL — needs real Postgres")

    import httpx

    from dazzle.rbac.verifier import _build_asgi_app, _DisposableDatabase, _probe_transport

    async with _DisposableDatabase(_PG_URL) as db_url:
        built = _build_asgi_app(_ROOT, db_url)
        auth_store = built.builder.auth_store
        assert auth_store is not None, "transition_atomic has auth enabled"
        if auth_store.get_user_by_email(_ADMIN_EMAIL) is None:
            auth_store.create_user(_ADMIN_EMAIL, _PASSWORD, roles=["admin"])
        transport = _probe_transport(httpx.ASGITransport(app=built.app))
        try:
            yield _App(transport, db_url)
        finally:
            db_manager = getattr(built.builder, "_db_manager", None)
            if db_manager is not None:
                db_manager.close_pool()


@pytest.fixture
async def app() -> AsyncIterator[_App]:
    async for a in _booted():
        yield a


async def _csrf_put(client: httpx.AsyncClient, url: str, body: dict[str, Any]) -> httpx.Response:
    token = client.cookies.get("dazzle_csrf")
    headers = {"X-CSRF-Token": token} if token else {}
    return await client.put(url, json=body, headers=headers)


def _seed_order(db_url: str) -> str:
    import psycopg

    oid = _mk_id()
    with psycopg.connect(db_url) as conn:
        conn.execute(
            'INSERT INTO "Order" (id, status, warehouse) VALUES (%s, %s, %s)',
            [oid, "submitted", None],
        )
        conn.commit()
    return oid


def _shipment_count(db_url: str, order_id: str) -> int:
    import psycopg

    with psycopg.connect(db_url) as conn:
        cur = conn.cursor()
        cur.execute('SELECT count(*) FROM "Shipment" WHERE "order" = %s', [order_id])
        return int(cur.fetchone()[0])


def _order_status(db_url: str, order_id: str) -> str:
    import psycopg

    with psycopg.connect(db_url) as conn:
        cur = conn.cursor()
        cur.execute('SELECT status FROM "Order" WHERE id = %s', [order_id])
        return str(cur.fetchone()[0])


async def test_transition_invoke_commits_status_and_effect_together(app: _App) -> None:
    """submitted -> fulfilled commits the status AND the invoked flow's Shipment."""
    oid = _seed_order(app.db_url)
    client = await app.admin_client()
    resp = await _csrf_put(client, f"/orders/{oid}", {"status": "fulfilled", "warehouse": "W1"})
    assert resp.status_code < 400, (
        f"transition should succeed, got {resp.status_code}: {resp.text[:400]}"
    )
    assert _order_status(app.db_url, oid) == "fulfilled"
    assert _shipment_count(app.db_url, oid) == 1, "the invoked flow must have created the Shipment"


async def test_transition_invoke_failure_rolls_back_the_transition(app: _App) -> None:
    """When the invoked flow fails, the status write rolls back too (atomic)."""
    import psycopg

    oid = _seed_order(app.db_url)
    # Pre-seed a Shipment for this order → the flow's create violates the unique
    # constraint on Shipment.order → AtomicFlowError → the WHOLE transition rolls back.
    with psycopg.connect(app.db_url) as conn:
        conn.execute(
            'INSERT INTO "Shipment" (id, "order", warehouse) VALUES (%s, %s, %s)',
            [_mk_id(), oid, "pre-existing"],
        )
        conn.commit()

    client = await app.admin_client()
    resp = await _csrf_put(client, f"/orders/{oid}", {"status": "fulfilled", "warehouse": "W1"})
    # A clean 400 (transition_invoke_failed), NOT a 404 (route missing) or 500
    # (unhandled) — so this assertion can't pass vacuously.
    assert resp.status_code == 400, (
        f"flow failure should be a clean 400, got {resp.status_code}: {resp.text[:300]}"
    )
    assert "transition_invoke_failed" in resp.text

    # Atomicity: the status did NOT advance, and no second Shipment was created.
    assert _order_status(app.db_url, oid) == "submitted", (
        "status must roll back with the failed flow"
    )
    assert _shipment_count(app.db_url, oid) == 1, "only the pre-seeded Shipment should exist"
