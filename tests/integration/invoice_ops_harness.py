"""Shared harness for adversarial invoice_ops isolation tests.

Boots examples/invoice_ops in-process against a disposable PostgreSQL DB,
seeds two tenants (northwind, contoso) via direct SQL, and exposes an
``_InvoiceOpsApp`` dataclass with per-role/tenant client factories and
deterministic seeded ids.

How the fixture works
---------------------
invoice_ops scope rules reference ``current_user.tenant_id``.  The runtime
resolves a ``current_user.<attr>`` dotted reference by looking up the *domain*
``User`` entity row whose ``email`` matches the authenticated session user, and
merging that row's scalar columns into ``AuthContext.preferences``
(``AuthStore._load_domain_user_attributes``).

So for ``current_user.tenant_id`` to resolve, each seeded role-user needs
**two** rows that share an email:

* an *auth* ``users`` row (created via ``auth_store.create_user``) that carries
  the session + role list, and
* a *domain* ``User`` entity row (inserted directly into the ``User`` table)
  that carries the ``tenant_id`` FK.

Why direct SQL inserts for seeding?
-------------------------------------
invoice_ops surfaces expose only one create route: ``POST /invoices``
(the ``invoice_create`` surface, ``mode: create``).  All other entities
(Tenant, User, Supplier, LineItem, PaymentAttempt) have no create surface,
so there is no ``POST /<plural>`` route.  Direct SQL inserts are therefore
the only way to seed those tables.  The tests themselves use the HTTP read
paths — that is where isolation is exercised.

Table names follow the entity spec ``name`` exactly (``Tenant``, ``User``,
``Supplier``, ``Invoice``, ``LineItem``, ``PaymentAttempt``) — the runtime
Repository uses ``entity_spec.name`` as the table name verbatim.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

if TYPE_CHECKING:
    import httpx

_PG_URL = os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL")

_ROLES = ("requester", "approver", "finance", "auditor", "tenant_admin")
_TENANTS = ("northwind", "contoso")
_PASSWORD = "rbac-test-password"  # nosec B105 — scratch DB only
_BASE_URL = "http://invoice-ops.local"
_PROJECT_ROOT = Path("examples/invoice_ops")


@dataclass
class _InvoiceOpsApp:
    """Everything the adversarial tests reference: a per-role/tenant client
    factory and the deterministic seeded ids."""

    _transport: Any
    _db_url: str
    _audit_logger: Any = None
    tenant_ids: dict[str, str] = field(default_factory=dict)
    # role -> tenant -> (email, password)
    _creds: dict[str, dict[str, tuple[str, str]]] = field(default_factory=dict)

    # Deterministic seeded ids referenced by the tests.
    northwind_invoice_id: str = ""
    contoso_invoice_id: str = ""
    northwind_supplier_id: str = ""
    contoso_supplier_id: str = ""
    # A contoso supplier with NO child invoices — used by the cross-tenant
    # DELETE test so a denial verdict is unambiguous (a supplier with child
    # rows would 409 on the FK constraint even when the scope gate fails).
    contoso_supplier_childless_id: str = ""
    northwind_lineitem_id: str = ""
    contoso_lineitem_id: str = ""
    northwind_invoice_number: str = ""
    contoso_invoice_number: str = ""
    # Invoices in specific states (for later tasks)
    northwind_submitted_invoice_id: str = ""
    northwind_approved_invoice_id: str = ""
    # SupplierBankAccount ids (one per tenant) for isolation coverage.
    northwind_bank_account_id: str = ""
    contoso_bank_account_id: str = ""

    def credentials(self, role: str, tenant: str) -> tuple[str, str]:
        return self._creds[role][tenant]

    async def client_as(self, role: str, tenant: str) -> httpx.AsyncClient:
        """Return an httpx client authenticated as ``role`` in ``tenant``.

        The caller does not close the client explicitly — every client rides
        the same in-process ASGI transport and is closed when the event loop
        for the test ends. Each call logs in fresh so tests never share a jar.
        """
        import httpx

        from dazzle.cli.rbac import _login

        email, password = self.credentials(role, tenant)
        client = httpx.AsyncClient(
            transport=self._transport,
            base_url=_BASE_URL,
            follow_redirects=True,
        )
        await _login(client, _BASE_URL, email, password)
        return client

    def drain_audit(self) -> None:
        """Synchronously flush the runtime audit queue to the DB."""
        if self._audit_logger is not None:
            self._audit_logger.drain()

    def query_audit(self, **where: str) -> list[dict[str, Any]]:
        """Query ``_dazzle_audit_log`` on the disposable DB. Keys are column names."""
        import psycopg
        from psycopg.rows import dict_row

        clause = " AND ".join(f"{k} = %s" for k in where)
        sql = "SELECT * FROM _dazzle_audit_log"
        if clause:
            sql += f" WHERE {clause}"  # nosemgrep — keys are test-controlled column names
        with psycopg.connect(self._db_url, row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                cur.execute(sql, tuple(where.values()))
                return list(cur.fetchall())


async def _csrf_post(
    client: httpx.AsyncClient,
    url: str,
    body: dict[str, Any],
) -> httpx.Response:
    """POST with the double-submit CSRF token echoed from the cookie jar."""
    token = client.cookies.get("dazzle_csrf")
    headers = {"X-CSRF-Token": token} if token else {}
    return await client.post(url, json=body, headers=headers)


async def _csrf_put(
    client: httpx.AsyncClient,
    url: str,
    body: dict[str, Any],
) -> httpx.Response:
    """PUT with the double-submit CSRF token echoed from the cookie jar.

    PUT is a state-changing verb and passes through the double-submit
    CSRF middleware exactly like POST. Omitting the token 403s with a
    ``CSRF token missing or invalid`` body *before* the RBAC/scope gate
    runs — which would mask the real transition-role verdict."""
    token = client.cookies.get("dazzle_csrf")
    headers = {"X-CSRF-Token": token} if token else {}
    return await client.put(url, json=body, headers=headers)


async def _csrf_delete(
    client: httpx.AsyncClient,
    url: str,
) -> httpx.Response:
    """DELETE with the double-submit CSRF token echoed from the cookie jar.

    DELETE is a state-changing verb and passes through the double-submit
    CSRF middleware exactly like POST. Omitting the token 403s with a
    ``CSRF token missing or invalid`` body *before* the RBAC/scope gate
    runs — which would mask the real isolation verdict as a false 403."""
    token = client.cookies.get("dazzle_csrf")
    headers = {"X-CSRF-Token": token} if token else {}
    return await client.delete(url, headers=headers)


def _mk_id() -> str:
    """Return a new random UUID string."""
    return str(uuid.uuid4())


def _sql_insert(
    conn: Any,
    table: str,
    row: dict[str, Any],
) -> None:
    """Insert a single row into ``table``.

    Table name and column names are caller-supplied constants (hardcoded
    entity names and field name literals from the DSL), never user input.
    Values are passed as positional parameters (%s placeholders) so they go
    through psycopg's parameterisation — no string interpolation of values.
    This is the standard pattern used by the Dazzle runtime's own
    Repository._python_to_db path; the nosemgrep suppression acknowledges
    the intentional identifier-level formatting that cannot be parameterised
    in SQL (you cannot bind a table or column name as a value).
    """
    cols = ", ".join(f'"{k}"' for k in row)
    placeholders = ", ".join("%s" for _ in row)
    sql = f'INSERT INTO "{table}" ({cols}) VALUES ({placeholders})'
    # table + column names are hardcoded constants in this module, not user input;
    # values go through %s parameterisation — no SQL injection vector.
    # nosemgrep: python.lang.security.audit.formatted-sql-query.formatted-sql-query,python.sqlalchemy.security.sqlalchemy-execute-raw-query.sqlalchemy-execute-raw-query
    conn.execute(sql, list(row.values()))


async def _seed(app: _InvoiceOpsApp, auth_store: Any, db_url: str) -> None:
    """Seed auth users, domain rows, suppliers, invoices, line items and
    payment attempts directly into the scratch database.

    We bypass the HTTP layer for entity creation because invoice_ops only
    exposes ``POST /invoices`` (the ``invoice_create`` surface).  All other
    entities (Tenant, User, Supplier, LineItem, PaymentAttempt) have no
    create surface, so there is no ``POST /<plural>`` route for them.

    The tests exercise the HTTP *read* paths — that is where isolation is
    tested — so seeding via SQL does not reduce coverage of the isolation
    vectors.
    """
    from datetime import UTC, datetime

    import psycopg

    now = datetime.now(UTC)

    # --- auth users -------------------------------------------------------
    # One auth user per (role, tenant).
    for role in _ROLES:
        app._creds[role] = {}
        for tenant in _TENANTS:
            email = f"{role}.{tenant}@invoice-ops.test"
            if auth_store.get_user_by_email(email) is None:
                auth_store.create_user(email, _PASSWORD, roles=[role])
            app._creds[role][tenant] = (email, _PASSWORD)

    # --- deterministic ids ------------------------------------------------
    nw_tenant_id = _mk_id()
    co_tenant_id = _mk_id()
    app.tenant_ids["northwind"] = nw_tenant_id
    app.tenant_ids["contoso"] = co_tenant_id

    nw_supplier_id = _mk_id()
    nw_supplier2_id = _mk_id()
    co_supplier_id = _mk_id()
    co_supplier2_id = _mk_id()
    app.northwind_supplier_id = nw_supplier_id
    app.contoso_supplier_id = co_supplier_id
    # co_supplier2 has no child invoices — see contoso_supplier_childless_id.
    app.contoso_supplier_childless_id = co_supplier2_id

    nw_invoice_id = _mk_id()
    nw_invoice_submitted_id = _mk_id()
    nw_invoice_approved_id = _mk_id()
    co_invoice_id = _mk_id()
    co_invoice_submitted_id = _mk_id()
    co_invoice_approved_id = _mk_id()
    app.northwind_invoice_id = nw_invoice_id
    app.northwind_invoice_number = "NW-INV-001"
    app.northwind_submitted_invoice_id = nw_invoice_submitted_id
    app.northwind_approved_invoice_id = nw_invoice_approved_id
    app.contoso_invoice_id = co_invoice_id
    app.contoso_invoice_number = "CO-INV-001"

    nw_lineitem_id = _mk_id()
    co_lineitem_id = _mk_id()
    app.northwind_lineitem_id = nw_lineitem_id
    app.contoso_lineitem_id = co_lineitem_id

    nw_bank_account_id = _mk_id()
    co_bank_account_id = _mk_id()
    app.northwind_bank_account_id = nw_bank_account_id
    app.contoso_bank_account_id = co_bank_account_id

    with psycopg.connect(db_url, autocommit=True) as conn:
        # --- Tenant rows ------------------------------------------------
        _sql_insert(
            conn,
            "Tenant",
            {
                "id": nw_tenant_id,
                "name": "Northwind Traders",
                "slug": "northwind",
                "region": "emea",
                "status": "active",
                "created_at": now,
            },
        )
        _sql_insert(
            conn,
            "Tenant",
            {
                "id": co_tenant_id,
                "name": "Contoso Ltd",
                "slug": "contoso",
                "region": "amer",
                "status": "active",
                "created_at": now,
            },
        )

        # --- domain User rows (email must match auth users) ---------------
        for role in _ROLES:
            for tenant, tenant_id in (("northwind", nw_tenant_id), ("contoso", co_tenant_id)):
                email = app._creds[role][tenant][0]
                _sql_insert(
                    conn,
                    "User",
                    {
                        "id": _mk_id(),
                        "email": email,
                        "name": f"{role} ({tenant})",
                        "tenant_id": tenant_id,
                        "created_at": now,
                    },
                )

        # --- Supplier rows -----------------------------------------------
        for row in [
            {
                "id": nw_supplier_id,
                "tenant_id": nw_tenant_id,
                "name": "Northwind Supplier Alpha",
                "contact_email": "alpha@northwind.test",
                "region": "emea",
                "created_at": now,
                "updated_at": now,
            },
            {
                "id": nw_supplier2_id,
                "tenant_id": nw_tenant_id,
                "name": "Northwind Supplier Beta",
                "contact_email": "beta@northwind.test",
                "region": "emea",
                "created_at": now,
                "updated_at": now,
            },
            {
                "id": co_supplier_id,
                "tenant_id": co_tenant_id,
                "name": "Contoso Supplier Gamma",
                "contact_email": "gamma@contoso.test",
                "region": "amer",
                "created_at": now,
                "updated_at": now,
            },
            {
                "id": co_supplier2_id,
                "tenant_id": co_tenant_id,
                "name": "Contoso Supplier Delta",
                "contact_email": "delta@contoso.test",
                "region": "amer",
                "created_at": now,
                "updated_at": now,
            },
        ]:
            _sql_insert(conn, "Supplier", row)

        # --- Invoice rows ------------------------------------------------
        for row in [
            # northwind: draft, submitted, approved
            {
                "id": nw_invoice_id,
                "tenant_id": nw_tenant_id,
                "invoice_number": "NW-INV-001",
                "supplier": nw_supplier_id,
                "amount": "1000.00",
                "currency": "GBP",
                "status": "draft",
                "created_at": now,
                "updated_at": now,
            },
            {
                "id": nw_invoice_submitted_id,
                "tenant_id": nw_tenant_id,
                "invoice_number": "NW-INV-002",
                "supplier": nw_supplier_id,
                "amount": "2500.00",
                "currency": "GBP",
                "status": "submitted",
                "created_at": now,
                "updated_at": now,
            },
            {
                "id": nw_invoice_approved_id,
                "tenant_id": nw_tenant_id,
                "invoice_number": "NW-INV-003",
                "supplier": nw_supplier_id,
                "amount": "500.00",
                "currency": "GBP",
                "status": "approved",
                "created_at": now,
                "updated_at": now,
            },
            # contoso: draft, submitted, approved
            {
                "id": co_invoice_id,
                "tenant_id": co_tenant_id,
                "invoice_number": "CO-INV-001",
                "supplier": co_supplier_id,
                "amount": "9999.00",
                "currency": "USD",
                "status": "draft",
                "created_at": now,
                "updated_at": now,
            },
            {
                "id": co_invoice_submitted_id,
                "tenant_id": co_tenant_id,
                "invoice_number": "CO-INV-002",
                "supplier": co_supplier_id,
                "amount": "4500.00",
                "currency": "USD",
                "status": "submitted",
                "created_at": now,
                "updated_at": now,
            },
            {
                "id": co_invoice_approved_id,
                "tenant_id": co_tenant_id,
                "invoice_number": "CO-INV-003",
                "supplier": co_supplier_id,
                "amount": "750.00",
                "currency": "USD",
                "status": "approved",
                "created_at": now,
                "updated_at": now,
            },
        ]:
            _sql_insert(conn, "Invoice", row)

        # --- LineItem rows -----------------------------------------------
        for row in [
            {
                "id": nw_lineitem_id,
                "tenant_id": nw_tenant_id,
                "invoice": nw_invoice_id,
                "description": "Northwind consulting services",
                "quantity": 5,
                "unit_amount": "200.00",
                "created_at": now,
            },
            {
                "id": _mk_id(),
                "tenant_id": nw_tenant_id,
                "invoice": nw_invoice_submitted_id,
                "description": "Northwind software licences",
                "quantity": 1,
                "unit_amount": "2500.00",
                "created_at": now,
            },
            {
                "id": _mk_id(),
                "tenant_id": nw_tenant_id,
                "invoice": nw_invoice_approved_id,
                "description": "Northwind hardware",
                "quantity": 2,
                "unit_amount": "250.00",
                "created_at": now,
            },
            {
                "id": co_lineitem_id,
                "tenant_id": co_tenant_id,
                "invoice": co_invoice_id,
                "description": "Contoso managed services",
                "quantity": 1,
                "unit_amount": "9999.00",
                "created_at": now,
            },
            {
                "id": _mk_id(),
                "tenant_id": co_tenant_id,
                "invoice": co_invoice_submitted_id,
                "description": "Contoso support",
                "quantity": 3,
                "unit_amount": "1500.00",
                "created_at": now,
            },
            {
                "id": _mk_id(),
                "tenant_id": co_tenant_id,
                "invoice": co_invoice_approved_id,
                "description": "Contoso cloud storage",
                "quantity": 5,
                "unit_amount": "150.00",
                "created_at": now,
            },
        ]:
            _sql_insert(conn, "LineItem", row)

        # --- PaymentAttempt rows (one failed per tenant) -----------------
        for row in [
            {
                "id": _mk_id(),
                "tenant_id": nw_tenant_id,
                "invoice": nw_invoice_approved_id,
                "attempt_number": 1,
                "status": "failed",
                "failure_reason": "Insufficient funds",
                "created_at": now,
            },
            {
                "id": _mk_id(),
                "tenant_id": co_tenant_id,
                "invoice": co_invoice_approved_id,
                "attempt_number": 1,
                "status": "failed",
                "failure_reason": "Card declined",
                "created_at": now,
            },
        ]:
            _sql_insert(conn, "PaymentAttempt", row)

        # --- SupplierBankAccount rows (one per tenant) -------------------
        for row in [
            {
                "id": nw_bank_account_id,
                "tenant_id": nw_tenant_id,
                "supplier": nw_supplier_id,
                "bank_account_ref": "NW-BANK-001",
                "account_name": "Northwind Supplier Alpha Account",
                "created_at": now,
                "updated_at": now,
            },
            {
                "id": co_bank_account_id,
                "tenant_id": co_tenant_id,
                "supplier": co_supplier_id,
                "bank_account_ref": "CO-BANK-001",
                "account_name": "Contoso Supplier Gamma Account",
                "created_at": now,
                "updated_at": now,
            },
        ]:
            _sql_insert(conn, "SupplierBankAccount", row)

    # --- memberships (auth Plan 1d) --------------------------------------
    # The clean break removed the preferences tenant_id fallback, so
    # current_user.tenant_id (and the RLS GUC) now resolve ONLY from an active
    # membership. Backfill exactly as a real deployment would (`dazzle auth
    # migrate`): mirror each Tenant -> organizations at the same id + create a
    # membership per auth user, resolved via the domain User entity by email.
    # Each user ends up with exactly one membership, which login auto-activates
    # (Plan 1b) -> the fence resolves to that tenant.
    from dazzle.core.appspec_loader import load_project_appspec
    from dazzle.db.auth_migrate import migrate_to_memberships

    appspec = load_project_appspec(_PROJECT_ROOT)
    with psycopg.connect(db_url) as mconn:  # non-autocommit: migrate runs in one txn
        migrate_to_memberships(appspec, conn=mconn)


async def booted_invoice_ops() -> AsyncIterator[_InvoiceOpsApp]:
    """Boot examples/invoice_ops in-process against a disposable DB, seed it,
    and yield an ``_InvoiceOpsApp`` exposing ``client_as(role, tenant)`` +
    the seeded ids.

    Usage in a pytest fixture::

        @pytest.fixture
        async def app():
            async for a in booted_invoice_ops():
                yield a
    """
    if not _PG_URL:
        pytest.skip("no TEST_DATABASE_URL / DATABASE_URL")

    import httpx

    from dazzle.rbac.verifier import (
        _build_asgi_app,
        _DisposableDatabase,
        _probe_transport,
    )

    async with _DisposableDatabase(_PG_URL) as db_url:
        built = _build_asgi_app(_PROJECT_ROOT, db_url)
        auth_store = built.builder.auth_store
        assert auth_store is not None, "invoice_ops has auth enabled"

        # raise_app_exceptions=False so a server-side 500 surfaces as a status
        # code instead of aborting the test (mirrors the verifier's probe
        # transport).
        transport = _probe_transport(httpx.ASGITransport(app=built.app))

        invoice_ops_app = _InvoiceOpsApp(
            _transport=transport,
            _db_url=db_url,
            _audit_logger=built.builder.audit_logger,
        )
        await _seed(invoice_ops_app, auth_store, db_url)
        try:
            yield invoice_ops_app
        finally:
            db_manager = getattr(built.builder, "_db_manager", None)
            if db_manager is not None:
                db_manager.close_pool()
