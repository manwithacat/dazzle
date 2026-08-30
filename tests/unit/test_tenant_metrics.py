"""CONOPS follow-up counters: resolve, RLS unbound, guard, alias verify."""

from __future__ import annotations

from uuid import uuid4

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from dazzle.http.runtime.tenant.audit import render_tenancy_planes
from dazzle.http.runtime.tenant.cache import TenantCache
from dazzle.http.runtime.tenant.guard import (
    ApexCookieNotSuperAdmin,
    CrossTenantForbidden,
    HostCookieMissingTenant,
    check_cross_tenant,
)
from dazzle.http.runtime.tenant.metrics import (
    alias_verify_counts,
    guard_counts,
    note_rls_unbound,
    reset_tenancy_metrics,
    resolve_counts,
    unbound_counts,
)
from dazzle.http.runtime.tenant.middleware import (
    TenantHostBinding,
    TenantResolutionMiddleware,
)
from dazzle.http.runtime.tenant.resolver import EntityProbe, Resolver

pytestmark = pytest.mark.gate


@pytest.fixture(autouse=True)
def _reset_metrics() -> None:
    reset_tenancy_metrics()
    yield
    reset_tenancy_metrics()


def _app(binding: TenantHostBinding) -> TestClient:
    app = FastAPI()

    @app.get("/whoami")
    async def whoami(request: Request) -> dict:
        tenant = getattr(request.state, "tenant", None)
        return {"tenant": None if tenant is None else tenant.slug}

    app.add_middleware(TenantResolutionMiddleware, binding=binding)
    return TestClient(app)


def _binding(
    rows: dict[tuple[str, str], dict],
    *,
    canonical: list[str] | None = None,
    topology: str = "provider_subdomain",
) -> TenantHostBinding:
    return TenantHostBinding(
        app_name="testapp",
        domain="example.com",
        canonical_hosts=tuple(canonical or []),
        cache=TenantCache(max_entries=64, ttl_seconds=60),
        resolver=Resolver(
            probes=[EntityProbe("Trust", "slug")],
            history_probe=None,
            lookup_fn=lambda e, s: rows.get((e, s)),
        ),
        not_found_renderer=lambda host: f"<p>404 {host}</p>",
        expired_renderer=lambda old, new, domain: f"<p>410 {old} -> {new}</p>",
        topology=topology,
    )


def test_resolve_canonical_and_hit_and_bad_host() -> None:
    rows = {("Trust", "acme"): {"id": uuid4(), "slug": "acme", "name": "Acme"}}
    client = _app(_binding(rows, canonical=["www.example.com"]))
    assert client.get("/whoami", headers={"host": "www.example.com"}).status_code == 200
    assert client.get("/whoami", headers={"host": "acme.example.com"}).status_code == 200
    assert client.get("/whoami", headers={"host": "other.org"}).status_code == 400
    counts = resolve_counts()
    assert counts[("provider_subdomain", "canonical")] == 1
    assert counts[("provider_subdomain", "hit")] == 1
    assert counts[("provider_subdomain", "bad_host")] == 1


def test_resolve_404_and_apex_bad_host() -> None:
    client = _app(_binding({}, canonical=["www.example.com"], topology="apex"))
    assert client.get("/whoami", headers={"host": "ghost.example.com"}).status_code == 400
    assert resolve_counts()[("apex", "bad_host")] == 1
    b_client = _app(_binding({}))
    assert b_client.get("/whoami", headers={"host": "nope.example.com"}).status_code == 404
    assert resolve_counts()[("provider_subdomain", "404")] == 1


def test_rls_unbound_counter() -> None:
    note_rls_unbound()
    note_rls_unbound(path="/sign")
    assert unbound_counts()[""] == 1
    assert unbound_counts()["/sign"] == 1


def test_guard_reasons() -> None:
    check_cross_tenant(
        cookie_kind=None,
        session_tenant_id=None,
        request_tenant_id=None,
        user_role="member",
        super_admin_role="super_admin",
    )
    with pytest.raises(HostCookieMissingTenant):
        check_cross_tenant(
            cookie_kind="host",
            session_tenant_id="t1",
            request_tenant_id=None,
            user_role="member",
            super_admin_role="super_admin",
        )
    with pytest.raises(CrossTenantForbidden):
        check_cross_tenant(
            cookie_kind="host",
            session_tenant_id="t1",
            request_tenant_id="t2",
            user_role="member",
            super_admin_role="super_admin",
        )
    with pytest.raises(ApexCookieNotSuperAdmin):
        check_cross_tenant(
            cookie_kind="apex",
            session_tenant_id=None,
            request_tenant_id="t1",
            user_role="member",
            super_admin_role="super_admin",
        )
    counts = guard_counts()
    assert counts["pass"] == 1
    assert counts["host_cookie_on_apex"] == 1
    assert counts["cross_tenant"] == 1
    assert counts["apex_not_superadmin"] == 1


def test_alias_verify_txt_fail_closed_counts() -> None:
    from dazzle.http.runtime.tenant.aliases import AliasError, claim, verify_step

    class _Mem:
        def __init__(self) -> None:
            self.rows: dict = {}

        def get_by_hostname(self, hostname: str):
            return self.rows.get(hostname)

        def list_live_for_tenant(self, tenant_id: str) -> list:
            return [r for r in self.rows.values() if r.tenant_id == tenant_id]

        def insert(self, **kwargs):
            from dazzle.http.runtime.tenant.aliases import AliasRow

            row = AliasRow(id=uuid4(), state="pending_txt", **kwargs)
            self.rows[kwargs["hostname"]] = row
            return row

        def save(self, row):
            self.rows[row.hostname] = row
            return row

        def delete(self, alias_id) -> None:
            pass

    store = _Mem()
    row = claim(
        store,
        tenant_id="t1",
        hostname="app.customer.com",
        cname_target="customers.example.com",
        provider_domain="example.com",
    )

    class Empty:
        def resolve_txt(self, name: str) -> list[str]:
            return []

        def resolve_cname(self, name: str) -> list[str]:
            return []

    with pytest.raises(AliasError):
        verify_step(store, row.hostname, txt_resolver=Empty(), cname_resolver=Empty())
    assert alias_verify_counts()["txt_not_found"] == 1


def test_auditor_line_names_three_planes() -> None:
    from types import SimpleNamespace

    appspec = SimpleNamespace(
        tenancy=SimpleNamespace(
            isolation=SimpleNamespace(mode=SimpleNamespace(value="shared_schema"))
        ),
        domain=SimpleNamespace(
            entities=[
                SimpleNamespace(
                    name="Practice",
                    is_tenant_root=True,
                    tenant_host=SimpleNamespace(topology="apex"),
                )
            ]
        ),
    )
    assert render_tenancy_planes(appspec) == (
        "shared_schema + membership on Practice + topology apex"
    )
    empty = SimpleNamespace(tenancy=None, domain=SimpleNamespace(entities=[]))
    assert render_tenancy_planes(empty) == "none + no membership root + topology none"
