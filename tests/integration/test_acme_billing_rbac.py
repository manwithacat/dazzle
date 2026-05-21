"""Adversarial RBAC tests for examples/acme_billing (#1174).

This suite boots the multi-tenant `examples/acme_billing` app in-process
against a disposable PostgreSQL database and adversarially probes its RBAC
enforcement: cross-tenant IDOR, list isolation, negation/`!=` scope,
junction-table (`via`) scope, read-only roles, the bulk-action gate, and the
audit trail.

How the fixture works
---------------------
`acme_billing`'s scope rules reference ``current_user.org``.  The runtime
resolves a ``current_user.<attr>`` dotted reference by looking up the *domain*
``User`` entity row whose ``email`` matches the authenticated session user, and
merging that row's scalar columns into ``AuthContext.preferences``
(``AuthStore._load_domain_user_attributes``, #532).  ``current_user`` itself in
a ``via`` clause resolves to that domain ``User`` row's id (``entity_id``, #534).

So for ``current_user.org`` to resolve, each seeded role-user needs **two**
rows that share an email:

* an *auth* ``users`` row (created via ``auth_store.create_user``) that carries
  the session + role list, and
* a *domain* ``User`` entity row (created via the generated CRUD API) that
  carries the ``org`` FK.

The fixture seeds both, deterministically, plus 2 orgs, projects, invoices
(with a known ``sensitive`` one) and memberships assigning the Acme
``project_member`` to a *subset* of Acme projects.  The `admin` positive-control
test and the in-scope PASS tests prove the role-users authenticate correctly —
a fixture that left everyone org-less would 404 everything (false green), so
those tests are the deliberate sanity check against that failure mode.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

if TYPE_CHECKING:
    import httpx

pytestmark = [pytest.mark.e2e, pytest.mark.postgres]

_PG_URL = os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL")

# acme_billing's five roles. `admin` is cross-org (break-glass); the rest are
# org-scoped. Every role gets one auth user + one domain User row per org.
_ROLES = ("admin", "org_owner", "auditor", "project_member", "external_contractor")
_ORGS = ("acme", "globex")
_PASSWORD = "rbac-test-password"  # nosec B105 — scratch DB only
_BASE_URL = "http://acme-rbac.local"
_PROJECT_ROOT = Path("examples/acme_billing")


@dataclass
class _RbacApp:
    """Everything the adversarial tests reference: a per-role client factory
    and the deterministic seeded ids."""

    _transport: Any
    _db_url: str
    # The runtime AuditLogger for the booted app. Tests call `drain()` on it
    # to synchronously flush the audit queue instead of racing the 1s timer.
    _audit_logger: Any = None
    org_ids: dict[str, str] = field(default_factory=dict)
    # role -> org -> (email, password)
    _creds: dict[str, dict[str, tuple[str, str]]] = field(default_factory=dict)

    # Deterministic seeded ids referenced by the tests.
    acme_org_id: str = ""
    globex_org_id: str = ""
    acme_invoice_id: str = ""
    globex_invoice_id: str = ""
    sensitive_invoice_id: str = ""
    assigned_project_id: str = ""
    unassigned_project_id: str = ""

    def credentials(self, role: str, org: str) -> tuple[str, str]:
        return self._creds[role][org]

    async def client_as(self, role: str, org: str) -> httpx.AsyncClient:
        """Return an httpx client authenticated as `role` in `org`.

        The caller does not close the client explicitly — every client rides
        the same in-process ASGI transport and is closed when the event loop
        for the test ends. Each call logs in fresh so tests never share a jar.
        """
        import httpx

        from dazzle.cli.rbac import _login

        email, password = self.credentials(role, org)
        client = httpx.AsyncClient(
            transport=self._transport,
            base_url=_BASE_URL,
            follow_redirects=True,
        )
        await _login(client, _BASE_URL, email, password)
        return client

    def drain_audit(self) -> None:
        """Synchronously flush the runtime audit queue to the DB.

        The runtime `AuditLogger` queues decisions and only persists them on a
        1s background timer — observing the trail by sleeping races that timer
        and flakes under CI load. `drain()` writes the queue inline, making the
        audit trail deterministically readable the instant this returns.
        """
        if self._audit_logger is not None:
            self._audit_logger.drain()

    def query_audit(self, **where: str) -> list[dict[str, Any]]:
        """Query `_dazzle_audit_log` on the disposable DB. Keys are column names."""
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


async def _seed(rbac: _RbacApp, auth_store: Any) -> None:
    """Seed orgs, domain User rows, projects, invoices and memberships.

    Domain rows are created through the generated CRUD API as the `admin`
    auth-user (whose scope is `all` for every entity) — so the seed exercises
    the same write path a real authorised request would, never a raw INSERT.
    """
    import httpx

    from dazzle.cli.rbac import _login

    # --- auth users -------------------------------------------------------
    # One auth user per (role, org). The admin auth-user is org-agnostic but
    # we still create one per org slug so `client_as("admin", org)` works for
    # both — they share the `admin` role and `all` scope.
    for role in _ROLES:
        rbac._creds[role] = {}
        for org in _ORGS:
            email = f"{role}.{org}@acme-rbac.test"
            if auth_store.get_user_by_email(email) is None:
                auth_store.create_user(email, _PASSWORD, roles=[role])
            rbac._creds[role][org] = (email, _PASSWORD)

    # --- admin client to drive the seed CRUD ------------------------------
    admin_client = httpx.AsyncClient(
        transport=rbac._transport, base_url=_BASE_URL, follow_redirects=True
    )
    try:
        await _login(admin_client, _BASE_URL, *rbac._creds["admin"]["acme"])

        async def create(plural: str, body: dict[str, Any]) -> str:
            resp = await _csrf_post(admin_client, f"/{plural}", body)
            assert resp.status_code in (200, 201), (
                f"seed POST /{plural} failed ({resp.status_code}): {resp.text}"
            )
            row_id = resp.json().get("id")
            assert row_id, f"seed POST /{plural} returned no id: {resp.text}"
            return str(row_id)

        # --- organizations ------------------------------------------------
        rbac.acme_org_id = await create("organizations", {"name": "Acme Corp"})
        rbac.globex_org_id = await create("organizations", {"name": "Globex Inc"})
        rbac.org_ids = {"acme": rbac.acme_org_id, "globex": rbac.globex_org_id}

        # --- domain User rows (email matches the auth users) --------------
        # This is the row `_load_domain_user_attributes` reads to resolve
        # `current_user.org`. Each role-user in each org gets one.
        domain_user_ids: dict[tuple[str, str], str] = {}
        for role in _ROLES:
            for org in _ORGS:
                email = rbac._creds[role][org][0]
                uid = await create(
                    "users",
                    {
                        "email": email,
                        "name": f"{role} ({org})",
                        "org": rbac.org_ids[org],
                    },
                )
                domain_user_ids[(role, org)] = uid

        # --- projects -----------------------------------------------------
        # Acme gets two projects so a project_member can be assigned to one
        # and not the other. Globex gets one.
        rbac.assigned_project_id = await create(
            "projects", {"name": "Acme Project Alpha", "org": rbac.acme_org_id}
        )
        rbac.unassigned_project_id = await create(
            "projects", {"name": "Acme Project Beta", "org": rbac.acme_org_id}
        )
        globex_project_id = await create(
            "projects", {"name": "Globex Project Gamma", "org": rbac.globex_org_id}
        )

        # --- invoices -----------------------------------------------------
        # Acme: one non-sensitive (assigned project), one sensitive.
        rbac.acme_invoice_id = await create(
            "invoices",
            {
                "number": "ACME-001",
                "amount": 10000,
                "project": rbac.assigned_project_id,
                "sensitive": False,
            },
        )
        rbac.sensitive_invoice_id = await create(
            "invoices",
            {
                "number": "ACME-SENS-002",
                "amount": 99999,
                "project": rbac.assigned_project_id,
                "sensitive": True,
            },
        )
        rbac.globex_invoice_id = await create(
            "invoices",
            {
                "number": "GLOBEX-001",
                "amount": 50000,
                "project": globex_project_id,
                "sensitive": False,
            },
        )

        # --- memberships --------------------------------------------------
        # Assign the Acme project_member ONLY to the "assigned" project, so
        # the via-Membership scope test has a real assigned/unassigned split.
        await create(
            "memberships",
            {
                "user": domain_user_ids[("project_member", "acme")],
                "project": rbac.assigned_project_id,
            },
        )
        # external_contractor is also assigned to the same project so the
        # sensitivity-scope test exercises the `sensitive != true` predicate
        # on a row the contractor would otherwise be able to see.
        await create(
            "memberships",
            {
                "user": domain_user_ids[("external_contractor", "acme")],
                "project": rbac.assigned_project_id,
            },
        )
    finally:
        await admin_client.aclose()


@pytest.fixture
async def rbac_app() -> Any:
    """Boot examples/acme_billing in-process against a disposable DB, seed it,
    and yield an `_RbacApp` exposing `client_as(role, org)` + the seeded ids."""
    if not _PG_URL:
        pytest.skip("no TEST_DATABASE_URL / DATABASE_URL")

    import httpx

    from dazzle.rbac.verifier import (
        _build_asgi_app,
        _DisposableDatabase,
        _probe_transport,
    )

    async with _DisposableDatabase(_PG_URL) as db_url:
        # Build the ASGI app — entity + auth tables are created on boot
        # (enable_test_mode=True). Reuses the proven #1171 builder.
        built = _build_asgi_app(_PROJECT_ROOT, db_url)
        auth_store = built.builder.auth_store
        assert auth_store is not None, "acme_billing has auth enabled"

        # raise_app_exceptions=False so a server-side 500 surfaces as a status
        # code instead of aborting the test (mirrors the verifier's probe
        # transport). All clients ride this single in-process transport.
        transport = _probe_transport(httpx.ASGITransport(app=built.app))

        rbac = _RbacApp(
            _transport=transport,
            _db_url=db_url,
            _audit_logger=built.builder.audit_logger,
        )
        await _seed(rbac, auth_store)
        try:
            yield rbac
        finally:
            db_manager = getattr(built.builder, "_db_manager", None)
            if db_manager is not None:
                db_manager.close_pool()


# ===========================================================================
# Adversarial tests
# ===========================================================================


async def test_idor_foreign_org_invoice_returns_404(rbac_app: _RbacApp) -> None:
    """Acme org_owner fetching a Globex invoice by id -> 404 (IDOR-safe).

    The FK-path scope `project.org = current_user.org` must hide the row, and
    the runtime must return 404 (not 403) so the attacker cannot even confirm
    the id exists."""
    client = await rbac_app.client_as("org_owner", org="acme")
    resp = await client.get(f"/invoices/{rbac_app.globex_invoice_id}")
    assert resp.status_code == 404, resp.text


async def test_cross_tenant_list_isolation(rbac_app: _RbacApp) -> None:
    """Acme org_owner's invoice list contains only Acme invoices."""
    client = await rbac_app.client_as("org_owner", org="acme")
    resp = await client.get("/invoices")
    assert resp.status_code == 200, resp.text
    ids = {r["id"] for r in resp.json()["items"]}
    assert rbac_app.globex_invoice_id not in ids, "cross-tenant leak: Globex invoice visible"
    assert rbac_app.acme_invoice_id in ids, "own-org invoice missing — scope over-filtered"


async def test_sensitive_invoice_denied_to_contractor(rbac_app: _RbacApp) -> None:
    """external_contractor cannot read a sensitive invoice.

    The contractor IS assigned to the project (so `project.org` passes), but
    the compound scope `... and sensitive != true` must still hide the row."""
    client = await rbac_app.client_as("external_contractor", org="acme")
    resp = await client.get(f"/invoices/{rbac_app.sensitive_invoice_id}")
    assert resp.status_code == 404, resp.text
    # Control: the contractor CAN see the non-sensitive invoice on the same
    # project — proves the 404 above is the `sensitive` predicate, not a
    # blanket org/project denial.
    ok = await client.get(f"/invoices/{rbac_app.acme_invoice_id}")
    assert ok.status_code == 200, (
        f"contractor should see the non-sensitive same-project invoice: {ok.text}"
    )


async def test_bulk_action_denied_for_unpermitted_role(rbac_app: _RbacApp) -> None:
    """A bulk action on invoices as a non-permitted role is denied (#1170).

    The bulk endpoint enforces the Invoice `update` permit gate (admin /
    org_owner only). An `auditor` holds no `update` permit, so the bulk POST
    must 403 before any row is mutated."""
    client = await rbac_app.client_as("auditor", org="acme")
    resp = await _csrf_post(
        client,
        "/api/invoices/bulk",
        {"action": "mark_sensitive", "ids": [rbac_app.acme_invoice_id]},
    )
    assert resp.status_code == 403, resp.text


async def test_auditor_is_read_only(rbac_app: _RbacApp) -> None:
    """auditor has no create/update/delete permit -> a write is denied."""
    client = await rbac_app.client_as("auditor", org="acme")
    resp = await _csrf_post(
        client, "/projects", {"name": "Auditor Sneaky Project", "org": rbac_app.acme_org_id}
    )
    assert resp.status_code == 403, resp.text


async def test_project_member_sees_only_assigned_projects(rbac_app: _RbacApp) -> None:
    """project_member's project list is filtered to its Membership rows.

    The `via Membership(user = current_user, project = id)` junction scope
    must show the assigned project and hide the unassigned one."""
    client = await rbac_app.client_as("project_member", org="acme")
    resp = await client.get("/projects")
    assert resp.status_code == 200, resp.text
    ids = {r["id"] for r in resp.json()["items"]}
    assert rbac_app.assigned_project_id in ids, "assigned project missing — via-scope over-filtered"
    assert rbac_app.unassigned_project_id not in ids, (
        "unassigned project visible — via-Membership scope leaked"
    )


async def test_admin_has_cross_org_access(rbac_app: _RbacApp) -> None:
    """Positive control — admin sees both orgs' invoices.

    This proves the fixture genuinely authenticates real role-users: if the
    seed were broken (no org, everything filtered) this would fail too."""
    client = await rbac_app.client_as("admin", org="acme")
    resp = await client.get("/invoices")
    assert resp.status_code == 200, resp.text
    ids = {r["id"] for r in resp.json()["items"]}
    assert {rbac_app.acme_invoice_id, rbac_app.globex_invoice_id} <= ids, (
        f"admin must see both orgs' invoices, saw {ids}"
    )


async def test_denied_access_emits_audit_record(rbac_app: _RbacApp) -> None:
    """A denied cross-tenant access produces a row in `_dazzle_audit_log`.

    Every acme_billing entity declares `audit: all`; the runtime AuditLogger
    queues each decision and persists it to `_dazzle_audit_log`. The denied
    IDOR read must leave a `deny` Invoice record.

    The runtime persists on a 1s background timer; observing the trail by
    sleeping races that timer and flaked under CI's serial postgres run. The
    decision is queued synchronously *before* the 404 response returns, so by
    the time `client.get` resolves the entry is on the queue — `drain_audit()`
    then writes it inline, making this assertion deterministic."""
    client = await rbac_app.client_as("external_contractor", org="acme")
    resp = await client.get(f"/invoices/{rbac_app.globex_invoice_id}")
    assert resp.status_code == 404, resp.text

    # Synchronously flush the audit queue — no timer race, no poll budget.
    rbac_app.drain_audit()
    records = rbac_app.query_audit(entity_name="Invoice")

    assert records, "no _dazzle_audit_log rows for Invoice — audit trail not wired"
    denies = [r for r in records if str(r.get("decision", "")).lower() == "deny"]
    assert denies, (
        "denied cross-tenant Invoice read produced no `deny` audit record: "
        f"{[(r['operation'], r['decision']) for r in records]}"
    )


async def test_org_owner_create_is_scoped_to_own_org(rbac_app: _RbacApp) -> None:
    """org_owner can create a Project in its OWN org but not in another org.

    `Project` declares `scope: create: org = current_user.org as: org_owner`.
    The create-scope walker must resolve `current_user.org` (a domain-User
    attribute merged into `auth_context.preferences`) — before #1174 it built
    its resolver from a hardcoded attribute allowlist that omitted `org`, so
    the RHS resolved to None and org_owner was 403'd even within its own org.

    Two assertions in one test so the negative case (foreign-org create
    denied) and the positive case (own-org create allowed) are pinned
    together — a regression in either direction fails loudly."""
    client = await rbac_app.client_as("org_owner", org="acme")

    # Negative: creating a Project in Globex's org must be denied (403). This
    # is the cross-tenant write the create-scope predicate exists to block.
    foreign = await _csrf_post(
        client,
        "/projects",
        {"name": "Cross-Tenant Project", "org": rbac_app.globex_org_id},
    )
    assert foreign.status_code == 403, (
        f"org_owner created a Project in another org — cross-tenant write hole: {foreign.text}"
    )

    # Positive: creating a Project in the org_owner's OWN org must succeed.
    # This is the assertion the bug broke — `current_user.org` failed to
    # resolve, so even a same-org create was 403'd.
    own = await _csrf_post(
        client,
        "/projects",
        {"name": "Acme Project Delta", "org": rbac_app.acme_org_id},
    )
    assert own.status_code in (200, 201), (
        f"org_owner must be able to create a Project in its own org: {own.text}"
    )
