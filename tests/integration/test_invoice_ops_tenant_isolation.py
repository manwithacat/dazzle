"""Adversarial cross-tenant isolation tests for examples/invoice_ops (SP1).

Boots invoice_ops in-process against a disposable PostgreSQL DB, seeds two
tenants (northwind, contoso), and — acting as a northwind user — attempts
every cross-tenant access vector, asserting denial. Any failure here is a
real isolation leak; the fix is runtime code.

Confirmed route paths (via `dazzle inspect routes --runtime`):
  /invoices           GET POST
  /invoices/{id:uuid} GET DELETE
  /suppliers/{id:uuid} GET DELETE
  /lineitems/{id:uuid} GET DELETE
  /paymentattempts/{id:uuid} GET DELETE

  No PATCH/PUT on invoice surface routes (surface is GET/POST/DELETE only).
  No dedicated audit-export, search, or projection routes — those vectors
  are tested via the internal /_dazzle/ endpoints or skipped with rationale.
"""

from __future__ import annotations

import pytest

from tests.integration.invoice_ops_harness import (
    _csrf_delete,
    _csrf_post,
    booted_invoice_ops,
)

pytestmark = [pytest.mark.e2e, pytest.mark.postgres]


@pytest.fixture
async def app():
    async for a in booted_invoice_ops():
        yield a


# ===========================================================================
# Core isolation tests (Steps 2–3)
# ===========================================================================


async def test_list_excludes_other_tenant(app) -> None:
    """Northwind requester's invoice list must not contain any contoso rows.

    The ``tenant_id = current_user.tenant_id`` scope on Invoice.list must
    filter out all contoso invoices — both by id and by invoice_number."""
    client = await app.client_as("requester", "northwind")
    resp = await client.get("/invoices")
    assert resp.status_code == 200
    body = resp.text
    assert app.contoso_invoice_id not in body, (
        f"cross-tenant leak: contoso invoice id {app.contoso_invoice_id!r} visible in northwind list"
    )
    assert app.contoso_invoice_number not in body, (
        f"cross-tenant leak: contoso invoice number {app.contoso_invoice_number!r} visible in northwind list"
    )


async def test_read_other_tenant_invoice_is_404(app) -> None:
    """Northwind requester fetching a contoso invoice by id -> 404 (IDOR-safe).

    The scope must hide the row entirely; the runtime must return 404 so the
    attacker cannot even confirm the id exists."""
    client = await app.client_as("requester", "northwind")
    resp = await client.get(f"/invoices/{app.contoso_invoice_id}")
    assert resp.status_code == 404, (
        f"IDOR leak: expected 404, got {resp.status_code} — contoso invoice visible to northwind user"
    )


async def test_update_other_tenant_invoice_is_404(app) -> None:
    """Northwind approver attempting to update a contoso invoice is denied.

    The surface only exposes DELETE (not PUT/PATCH) on /invoices/{id}.
    A POST to the detail path is not a valid route (405 Method Not Allowed).
    Either 404 (scope hides row) or 405 (method not routed) are acceptable
    denial signals — the key invariant is that the operation does not succeed."""
    client = await app.client_as("approver", "northwind")
    resp = await _csrf_post(client, f"/invoices/{app.contoso_invoice_id}", {"amount": 1})
    assert resp.status_code in (404, 405), (
        f"cross-tenant update not denied: got {resp.status_code} — "
        f"northwind approver should not be able to update contoso invoice"
    )


async def test_delete_other_tenant_supplier_is_404(app) -> None:
    """Northwind tenant_admin cannot delete a contoso supplier.

    Uses the *childless* contoso supplier so the verdict is unambiguous: a
    supplier with child invoices would 409 on the FK constraint even when the
    scope gate fails to deny — by deleting a childless supplier, a 200/204
    means the row was genuinely deleted cross-tenant.

    DELETE is a state-changing verb behind the double-submit CSRF middleware,
    so the request must carry the CSRF token — otherwise the 403 is a CSRF
    rejection, not a scope verdict."""
    client = await app.client_as("tenant_admin", "northwind")
    resp = await _csrf_delete(client, f"/suppliers/{app.contoso_supplier_childless_id}")
    assert resp.status_code == 404, (
        f"cross-tenant delete not denied: got {resp.status_code} — "
        f"northwind tenant_admin should not be able to delete contoso supplier"
    )


async def test_create_invoice_with_foreign_supplier_rejected(app) -> None:
    """Creating a northwind invoice that references a contoso supplier must fail.

    The FK supplier field must be scoped to the same tenant; a cross-tenant
    FK reference must be rejected (400/403/404/422) before any row is written."""
    client = await app.client_as("requester", "northwind")
    resp = await _csrf_post(
        client,
        "/invoices",
        {
            "invoice_number": "X-CROSS-1",
            "supplier": app.contoso_supplier_id,
            "amount": 100,
            "currency": "GBP",
        },
    )
    assert resp.status_code in (400, 403, 404, 422), (
        f"cross-tenant FK accepted on create: {resp.status_code} {resp.text}"
    )


async def test_read_other_tenant_lineitem_is_404(app) -> None:
    """Northwind requester fetching a contoso line item by id -> 404."""
    client = await app.client_as("requester", "northwind")
    resp = await client.get(f"/lineitems/{app.contoso_lineitem_id}")
    assert resp.status_code == 404, (
        f"IDOR leak: expected 404, got {resp.status_code} — contoso line item visible to northwind user"
    )


async def test_admin_positive_control(app) -> None:
    """Sanity check against false-green: a northwind user CAN see northwind data.

    If the scope is over-filtering (e.g. current_user.tenant_id resolves to
    NULL) every read returns 404 — this test catches that fixture failure mode
    and prevents false-green isolation tests."""
    client = await app.client_as("requester", "northwind")
    resp = await client.get(f"/invoices/{app.northwind_invoice_id}")
    assert resp.status_code == 200, (
        f"positive control failed: northwind requester cannot read own invoice "
        f"({resp.status_code}) — fixture may be broken (tenant_id not resolving)"
    )


# ===========================================================================
# Step 4: Extended vectors (search / export / events / config)
# ===========================================================================


async def test_search_excludes_other_tenant(app) -> None:
    """Northwind user querying invoices with a search param sees no contoso data.

    The /invoices list endpoint is the only query surface (no dedicated search
    route exists per `dazzle inspect routes --runtime`). We pass the contoso
    invoice number as a query parameter; if the list endpoint supports `q=` or
    `search=` filtering, contoso data must not appear. If neither param is
    supported the endpoint ignores them and returns the northwind list — in
    either case the contoso invoice number must be absent."""
    client = await app.client_as("requester", "northwind")
    # Try both common search param conventions
    for param in (f"q={app.contoso_invoice_number}", f"search={app.contoso_invoice_number}"):
        resp = await client.get(f"/invoices?{param}")
        assert resp.status_code == 200, f"GET /invoices?{param} failed: {resp.status_code}"
        assert app.contoso_invoice_number not in resp.text, (
            f"search leak: contoso invoice number visible in northwind search result "
            f"(param={param!r})"
        )
        assert app.contoso_invoice_id not in resp.text, (
            f"search leak: contoso invoice id visible in northwind search result (param={param!r})"
        )


async def test_audit_export_excludes_other_tenant(app) -> None:
    """Northwind auditor's audit/export surface contains no contoso entity ids.

    `dazzle inspect routes --runtime` shows no dedicated audit-export surface
    route (the audit_export surface declaration is a duplicate of /invoices and
    is dropped at boot with a warning). We probe the internal audit log endpoint
    which IS mounted at /_dazzle/audit/logs — as an authenticated northwind
    auditor we expect either:
      a) The endpoint returns only northwind rows (correct isolation), or
      b) The endpoint returns 403/404 (endpoint not accessible to auditor role).
    Either way, contoso entity ids must not appear in the response body."""
    client = await app.client_as("auditor", "northwind")
    resp = await client.get("/_dazzle/audit/logs")
    if resp.status_code in (403, 404):
        pytest.skip("/_dazzle/audit/logs not accessible to auditor role — endpoint gated")
    assert resp.status_code == 200, f"/_dazzle/audit/logs returned {resp.status_code}"
    body = resp.text
    # contoso ids must not appear in northwind auditor's audit view
    assert app.contoso_invoice_id not in body, (
        "audit log leak: contoso invoice id visible to northwind auditor"
    )
    assert app.contoso_supplier_id not in body, (
        "audit log leak: contoso supplier id visible to northwind auditor"
    )


async def test_event_log_excludes_other_tenant(app) -> None:
    """Northwind user querying the invoice_events topic sees no contoso tenant_id.

    The projection InvoiceStatusView is not exposed as a surface route.
    The internal events endpoint /_dazzle/events/topics/invoice_events IS
    mounted — we probe it as a northwind requester. If the endpoint is
    inaccessible (403/404) we skip. If accessible, contoso tenant_id must
    be absent."""
    client = await app.client_as("requester", "northwind")
    resp = await client.get("/_dazzle/events/topics/invoice_events")
    if resp.status_code in (403, 404, 500):
        # 403/404: endpoint gated. 500: the events subsystem is not functional
        # under the in-process ASGITransport boot — httpx.ASGITransport does
        # not run FastAPI lifespan events, so the event store / process
        # manager (which require REDIS_URL) are never initialised. The
        # endpoint 500s unconditionally regardless of tenant, so it cannot
        # be used as an isolation vector here.
        pytest.skip(
            f"/_dazzle/events/topics/invoice_events not testable "
            f"(status {resp.status_code}) — events subsystem not wired under "
            f"in-process transport (no lifespan, no REDIS_URL)"
        )
    assert resp.status_code == 200, (
        f"/_dazzle/events/topics/invoice_events returned {resp.status_code}"
    )
    body = resp.text
    contoso_tenant_id = app.tenant_ids.get("contoso", "")
    if contoso_tenant_id:
        assert contoso_tenant_id not in body, (
            f"event log leak: contoso tenant_id {contoso_tenant_id!r} visible to northwind user"
        )


async def test_read_other_tenant_bank_account_is_404(app) -> None:
    """A northwind user cannot read a contoso supplier's bank account.

    SupplierBankAccount has a ``tenant_id = current_user.tenant_id`` scope on
    ``read`` — a northwind finance user fetching a contoso bank account row by
    id must receive 404 (the scope gate hides the row entirely, preventing IDOR
    on sensitive bank account data)."""
    client = await app.client_as("finance", "northwind")
    resp = await client.get(f"/supplierbankaccounts/{app.contoso_bank_account_id}")
    assert resp.status_code == 404, (
        f"IDOR leak: expected 404, got {resp.status_code} — "
        f"contoso SupplierBankAccount visible to northwind finance user"
    )


async def test_other_tenant_config_denied(app) -> None:
    """Northwind tenant_admin cannot read or write contoso's per-tenant config.

    The `per_tenant_config` block (approval_threshold, base_currency) is
    declared in the tenancy block of app.dsl. There is no dedicated config
    surface route per `dazzle inspect routes --runtime`; the Tenant entity
    read scope enforces `id = current_user.tenant_id`, so a northwind admin
    reading the contoso Tenant row (which holds the config) must get 404."""
    client = await app.client_as("tenant_admin", "northwind")
    contoso_tenant_id = app.tenant_ids.get("contoso", "")
    if not contoso_tenant_id:
        pytest.skip("contoso tenant_id not seeded — cannot test config isolation")

    # Reading the contoso Tenant row (which is the config container) must 404.
    resp = await client.get(f"/tenants/{contoso_tenant_id}")
    assert resp.status_code == 404, (
        f"config isolation leak: northwind tenant_admin can read contoso Tenant row "
        f"(status {resp.status_code}) — approval_threshold / base_currency exposed"
    )

    # Mutating the contoso Tenant row must also be denied. The Tenant surface
    # exposes no create/edit surface, so the only mutating route on
    # /tenants/{id} is DELETE — a cross-tenant DELETE must 404 (scope hides
    # the row). A POST/PATCH to the same path is simply not routed (405).
    del_resp = await _csrf_delete(client, f"/tenants/{contoso_tenant_id}")
    assert del_resp.status_code in (404, 405), (
        f"config write not denied: northwind tenant_admin got {del_resp.status_code} "
        f"attempting to delete contoso Tenant row"
    )
