"""TDD tests for POST /auth/connections/create?type=domain (Task 4.2 — #1424).

Covers:
  (a) creating a domain-only connection requires NO DAZZLE_CONNECTION_SECRET
  (b) the store receives type="domain", config={}, secrets={}, domains=[]
  (c) creation is org-fenced (tenant_id = caller's active membership, never input)
  (d) the connections page lists a "Verify a domain (no SSO)" affordance / link
  (e) ?new=domain renders the domain create form
  (f) capability gating: non-manage_connections callers get 403
"""

from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from dazzle.http.runtime.auth.connection_admin_routes import create_connection_admin_routes
from dazzle.http.runtime.auth.connections import ConnectionRecord

# ---------------------------------------------------------------------------
# Helpers: fake store + test-client builders (mirrors policy/integration tests)
# ---------------------------------------------------------------------------


def _conn(cid: str = "conn-1", tenant: str = "org-1", **over) -> ConnectionRecord:
    base = {
        "id": cid,
        "tenant_id": tenant,
        "type": "domain",
        "provider": "native",
        "domains": [],
        "verified_domains": [],
        "config": {},
        "secrets": {},
        "group_mapping": {},
        "status": "active",
        "created_at": datetime(2026, 6, 21),
        "updated_at": datetime(2026, 6, 21),
    }
    base.update(over)
    return ConnectionRecord(**base)


class _Store:
    """Minimal fake AuthStore covering every method called by the connection routes."""

    def __init__(self, *, connections: list | None = None, roles: tuple = ("admin",)) -> None:
        self._connections = {c.id: c for c in (connections or [])}
        self._roles = list(roles)
        self._org_settings: dict[str, dict] = {}
        self.created: dict | None = None  # captures create_connection kwargs

    def validate_session(self, session_id: str) -> SimpleNamespace | None:
        if session_id != "good-sid":
            return None
        return SimpleNamespace(
            is_authenticated=True,
            user=SimpleNamespace(id="u1"),
            active_membership=SimpleNamespace(
                tenant_id="org-1", roles=self._roles, status="active"
            ),
        )

    def get_connections_for_tenant(self, tenant_id: str) -> list:
        return [c for c in self._connections.values() if c.tenant_id == tenant_id]

    def get_connection(self, connection_id: str, *, tenant_id: str | None = None):
        c = self._connections.get(connection_id)
        if c is None:
            return None
        if tenant_id is not None and c.tenant_id != tenant_id:
            return None
        return c

    def get_org_settings(self, org_id: str) -> dict:
        return self._org_settings.get(org_id, {})

    def set_org_settings(self, org_id: str, settings: dict) -> None:
        self._org_settings[org_id] = settings

    def get_organization(self, org_id: str) -> SimpleNamespace:
        return SimpleNamespace(name="Acme Inc")

    def get_connection_secret_events(
        self, connection_id: str, *, tenant_id: str | None = None
    ) -> list:
        return []

    def get_connection_grace_status(
        self, connection_id: str, *, tenant_id: str | None = None
    ) -> tuple:
        return (False, None)

    def create_connection(self, **kw) -> ConnectionRecord:
        self.created = kw
        return _conn("conn-new", kw.get("tenant_id", "org-1"), type=kw.get("type", "domain"))

    def set_connection_domains(self, connection_id: str, domains: list) -> None:
        pass

    def get_connection_by_verified_domain(self, domain: str):
        return None


def _client(store: _Store, *, authed: bool = True) -> TestClient:
    app = FastAPI()
    app.include_router(create_connection_admin_routes())
    app.state.auth_store = store
    app.state.org_admin_roles = ["admin"]
    app.state.sitespec = {"brand": {"product_name": "Acme"}}
    client = TestClient(app)
    if authed:
        client.cookies.set("dazzle_session", "good-sid")
    return client


# ---------------------------------------------------------------------------
# (a) Creating a domain connection does NOT require DAZZLE_CONNECTION_SECRET
# ---------------------------------------------------------------------------


def test_create_domain_works_without_at_rest_key(monkeypatch) -> None:
    """type=domain has no secrets → creation succeeds even without DAZZLE_CONNECTION_SECRET."""
    monkeypatch.delenv("DAZZLE_CONNECTION_SECRET", raising=False)
    store = _Store()
    r = _client(store).post(
        "/auth/connections/create?type=domain",
        data={},
        follow_redirects=False,
    )
    assert r.status_code in (204, 303), r.text
    assert store.created is not None


# ---------------------------------------------------------------------------
# (b) The store receives type="domain", config={}, secrets={}, domains=[]
# ---------------------------------------------------------------------------


def test_create_domain_store_shape(monkeypatch) -> None:
    """The store.create_connection call carries empty config/secrets for a domain connection."""
    monkeypatch.delenv("DAZZLE_CONNECTION_SECRET", raising=False)
    store = _Store()
    r = _client(store).post(
        "/auth/connections/create?type=domain",
        data={},
        follow_redirects=False,
    )
    assert r.status_code in (204, 303), r.text
    assert store.created is not None
    assert store.created["type"] == "domain"
    assert store.created["config"] == {}
    assert store.created["secrets"] == {}
    assert store.created["domains"] == []


# ---------------------------------------------------------------------------
# (c) Org-fenced: tenant_id is the caller's active membership, never form input
# ---------------------------------------------------------------------------


def test_create_domain_is_org_fenced(monkeypatch) -> None:
    """The tenant_id written to the store is the authed membership's org, not form input."""
    monkeypatch.delenv("DAZZLE_CONNECTION_SECRET", raising=False)
    store = _Store()
    r = _client(store).post(
        "/auth/connections/create?type=domain",
        data={"tenant_id": "evil-org"},  # should be ignored
        follow_redirects=False,
    )
    assert r.status_code in (204, 303), r.text
    assert store.created is not None
    assert store.created["tenant_id"] == "org-1"


# ---------------------------------------------------------------------------
# (d) The connections page shows a "Verify a domain" affordance
# ---------------------------------------------------------------------------


def test_connections_page_lists_domain_option() -> None:
    """GET /auth/connections includes a link to create a domain connection."""
    store = _Store()
    r = _client(store).get("/auth/connections")
    assert r.status_code == 200
    # Must offer the domain-create option alongside oidc/scim/saml
    assert "domain" in r.text.lower()
    assert "Verify a domain" in r.text or "Add domain" in r.text or "domain" in r.text.lower()


def test_connections_page_has_domain_create_link() -> None:
    """GET /auth/connections has a link whose href includes ?new=domain."""
    store = _Store()
    r = _client(store).get("/auth/connections")
    assert r.status_code == 200
    assert "new=domain" in r.text


# ---------------------------------------------------------------------------
# (e) ?new=domain renders the domain create form
# ---------------------------------------------------------------------------


def test_new_domain_renders_form() -> None:
    """GET /auth/connections?new=domain shows the domain-create form."""
    store = _Store()
    r = _client(store).get("/auth/connections?new=domain")
    assert r.status_code == 200
    # The form posts to /auth/connections/create?type=domain
    assert "/auth/connections/create?type=domain" in r.text


# ---------------------------------------------------------------------------
# (f) Capability gating: non-manage_connections callers get 403
# ---------------------------------------------------------------------------


def test_create_domain_forbidden_without_session() -> None:
    """No session cookie → 403."""
    store = _Store()
    r = _client(store, authed=False).post("/auth/connections/create?type=domain", data={})
    assert r.status_code == 403
    assert store.created is None


def test_create_domain_forbidden_for_non_admin() -> None:
    """Non-admin role → 403."""
    store = _Store(roles=("member",))
    r = _client(store).post("/auth/connections/create?type=domain", data={}, follow_redirects=False)
    assert r.status_code == 403
    assert store.created is None


# ---------------------------------------------------------------------------
# Type registry: "domain" is in CONNECTION_TYPES
# ---------------------------------------------------------------------------


def test_domain_in_connection_types() -> None:
    """'domain' must appear in CONNECTION_TYPES so the gate accepts it."""
    from dazzle.http.runtime.auth.connection_create_form import CONNECTION_TYPES

    assert "domain" in CONNECTION_TYPES
