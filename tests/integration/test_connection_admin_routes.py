"""Org-admin connection surface tests (auth Plan: in-app connection management).

TestClient over a fake AuthStore + a fake auth context. Pins the RBAC gate, org-scoping
(cross-org → 404 via the fenced getter), the secret-free render, and the CSRF-protected
domain actions — without Postgres or real DNS.
"""

from __future__ import annotations

import base64
from datetime import datetime
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from dazzle.back.runtime.auth.connection_admin_routes import create_connection_admin_routes
from dazzle.back.runtime.auth.connections import ConnectionRecord


@pytest.fixture(autouse=True)
def _key(monkeypatch):
    monkeypatch.setenv("DAZZLE_CONNECTION_SECRET", base64.b64encode(b"k" * 32).decode())


def _conn(cid="conn-1", tenant="org-1", **over) -> ConnectionRecord:
    base = {
        "id": cid,
        "tenant_id": tenant,
        "type": "oidc",
        "provider": "native",
        "domains": ["acme.test"],
        "verified_domains": [],
        "config": {"issuer": "https://idp", "client_id": "cid"},
        "secrets": {"client_secret": "SUPER-SECRET"},
        "group_mapping": {},
        "status": "active",
        "created_at": datetime(2026, 6, 6),
        "updated_at": datetime(2026, 6, 6),
    }
    base.update(over)
    return ConnectionRecord(**base)


class _Store:
    def __init__(self, *, connections=None, roles=("admin",)):
        self._connections = {c.id: c for c in (connections or [])}
        self._roles = list(roles)
        self.set_domains_calls: list = []
        self.claimed: list = []

    def validate_session(self, session_id):
        if session_id != "good-sid":
            return None
        return SimpleNamespace(
            is_authenticated=True,
            user=SimpleNamespace(id="u1"),
            active_membership=SimpleNamespace(
                tenant_id="org-1", roles=self._roles, status="active"
            ),
        )

    def get_connections_for_tenant(self, tenant_id):
        return [c for c in self._connections.values() if c.tenant_id == tenant_id]

    def get_connection(self, connection_id, *, tenant_id=None):
        c = self._connections.get(connection_id)
        if c is None:
            return None
        if tenant_id is not None and c.tenant_id != tenant_id:
            return None  # 4a fenced getter — cross-org returns None
        return c

    def set_connection_domains(self, connection_id, domains):
        self.set_domains_calls.append((connection_id, domains))

    def get_connection_by_verified_domain(self, domain):
        return None

    def claim_verified_domain(self, connection_id, domain):
        self.claimed.append((connection_id, domain))
        return True

    def set_connection_verified_domains(self, connection_id, verified):
        pass

    def get_organization(self, org_id):
        return SimpleNamespace(name="Acme Inc")


def _client(store, *, org_admin_roles=("admin",), authed=True) -> TestClient:
    app = FastAPI()
    app.include_router(create_connection_admin_routes())
    app.state.auth_store = store
    app.state.org_admin_roles = list(org_admin_roles)
    app.state.sitespec = {"brand": {"product_name": "Acme"}}
    client = TestClient(app)
    if authed:
        client.cookies.set("dazzle_session", "good-sid")
    return client


# ---- RBAC gate ----


def test_page_forbidden_without_session() -> None:
    r = _client(_Store(connections=[_conn()]), authed=False).get("/auth/connections")
    assert r.status_code == 403


def test_page_forbidden_for_non_admin() -> None:
    # The caller's roles don't intersect org_admin_roles.
    store = _Store(connections=[_conn()], roles=("member",))
    r = _client(store).get("/auth/connections")
    assert r.status_code == 403


def test_page_forbidden_when_no_admin_roles_configured() -> None:
    # Fail-closed: no org_admin_roles configured → nobody may manage.
    store = _Store(connections=[_conn()])
    r = _client(store, org_admin_roles=()).get("/auth/connections")
    assert r.status_code == 403


# ---- page render (secret-free) ----


def test_page_lists_connections_never_leaks_secret() -> None:
    store = _Store(connections=[_conn(domains=["acme.test"], verified_domains=[])])
    r = _client(store).get("/auth/connections")
    assert r.status_code == 200
    assert "SUPER-SECRET" not in r.text  # the client_secret value must never render
    assert "conn-1" in r.text
    assert "dazzle-verify=" in r.text  # the claimed-domain TXT record to publish
    assert "Acme Inc" in r.text


def test_page_only_shows_active_orgs_connections() -> None:
    # A connection in another org must not appear (get_connections_for_tenant is scoped).
    store = _Store(connections=[_conn("c1", "org-1"), _conn("c2", "org-2")])
    r = _client(store).get("/auth/connections")
    assert "c1" in r.text and "c2" not in r.text


# ---- add-domain ----


def test_add_domain_claims() -> None:
    store = _Store(connections=[_conn(domains=[])])
    r = _client(store).post(
        "/auth/connections/add-domain?connection_id=conn-1",
        data={"domain": "ACME.test"},
        follow_redirects=False,
    )
    assert r.status_code in (204, 303)
    assert store.set_domains_calls == [("conn-1", ["acme.test"])]  # normalized + claimed


def test_add_domain_cross_org_is_404() -> None:
    # connection belongs to org-2; the org-1 admin can't touch it.
    store = _Store(connections=[_conn("c2", "org-2")])
    r = _client(store).post(
        "/auth/connections/add-domain?connection_id=c2",
        data={"domain": "x.test"},
        follow_redirects=False,
    )
    assert r.status_code == 404
    assert store.set_domains_calls == []


def test_add_domain_forbidden_for_non_admin() -> None:
    store = _Store(connections=[_conn()], roles=("member",))
    r = _client(store).post(
        "/auth/connections/add-domain?connection_id=conn-1", data={"domain": "x.test"}
    )
    assert r.status_code == 403


# ---- verify-domain ----


def test_verify_domain_success(monkeypatch) -> None:
    from dazzle.back.runtime.auth import domain_verification

    store = _Store(connections=[_conn(domains=["acme.test"])])

    class _FakeResolver:
        def resolve_txt(self, domain):
            return [domain_verification.txt_record("conn-1", "acme.test")]

    monkeypatch.setattr(domain_verification, "DnspythonResolver", _FakeResolver)
    r = _client(store).post(
        "/auth/connections/verify-domain?connection_id=conn-1&domain=acme.test",
        follow_redirects=False,
    )
    assert r.status_code in (204, 303)
    assert store.claimed == [("conn-1", "acme.test")]


def test_verify_domain_cross_org_is_404(monkeypatch) -> None:
    store = _Store(connections=[_conn("c2", "org-2")])
    r = _client(store).post(
        "/auth/connections/verify-domain?connection_id=c2&domain=x.test",
        follow_redirects=False,
    )
    assert r.status_code == 404
    assert store.claimed == []


def test_add_domain_rejects_malformed() -> None:
    # A domain with a colon (or other junk) is rejected — never stored (so it can't
    # wedge the page's URL rendering on the next render).
    store = _Store(connections=[_conn(domains=[])])
    r = _client(store).post(
        "/auth/connections/add-domain?connection_id=conn-1",
        data={"domain": "evil:x"},
        follow_redirects=False,
    )
    assert r.status_code == 400
    assert store.set_domains_calls == []
