"""Tests for the tenant middleware + default templates (#1289 slice 3)."""

from __future__ import annotations

from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from dazzle.http.runtime.tenant.cache import TenantCache
from dazzle.http.runtime.tenant.middleware import (
    TenantHostBinding,
    TenantResolutionMiddleware,
)
from dazzle.http.runtime.tenant.resolver import EntityProbe, ResolvedTenant, Resolver
from dazzle.http.runtime.tenant.templates import (
    render_default_404,
    render_default_410,
)


def test_default_404_includes_host():
    body = render_default_404(app_name="acme", host="missing.acme.com")
    assert "missing.acme.com" in body
    assert "404" in body or "not found" in body.lower()


def test_default_410_includes_new_slug():
    body = render_default_410(
        app_name="acme", old_slug="oldco", new_slug="newco", domain="acme.com"
    )
    assert "newco" in body
    assert "oldco" in body


def test_default_templates_escape_html():
    body = render_default_404(app_name="<script>", host="evil<.com")
    assert "<script>" not in body
    assert "&lt;script&gt;" in body


# ---------------------------------------------------------------------------
# TenantResolutionMiddleware
# ---------------------------------------------------------------------------


def _app_with_binding(binding: TenantHostBinding) -> FastAPI:
    app = FastAPI()

    @app.get("/whoami")
    async def whoami(request: Request) -> dict:
        tenant = getattr(request.state, "tenant", None)
        return {"tenant": None if tenant is None else tenant.slug}

    app.add_middleware(TenantResolutionMiddleware, binding=binding)
    return app


def _binding(
    rows: dict[tuple[str, str], dict],
    *,
    canonical: list[str] | None = None,
    topology: str = "provider_subdomain",
) -> TenantHostBinding:
    cache = TenantCache(max_entries=64, ttl_seconds=60)
    resolver = Resolver(
        probes=[EntityProbe("Trust", "slug")],
        history_probe=None,
        lookup_fn=lambda e, s: rows.get((e, s)),
    )
    return TenantHostBinding(
        app_name="testapp",
        domain="example.com",
        canonical_hosts=tuple(canonical or []),
        cache=cache,
        resolver=resolver,
        not_found_renderer=lambda host: f"<p>404 {host}</p>",
        expired_renderer=lambda old, new, domain: f"<p>410 {old} -> {new}</p>",
        topology=topology,
    )


def test_apex_topology_does_not_parse_leftover_host_as_slug() -> None:
    """ADR-0055: topology A never invents B from a leftover Host label."""
    binding = _binding({}, canonical=["www.example.com"], topology="apex")
    client = TestClient(_app_with_binding(binding))
    resp = client.get("/whoami", headers={"host": "acme.example.com"})
    assert resp.status_code == 400


def test_leftover_topology_does_not_invent_slug_extract() -> None:
    """Leftover / omitted topology stays put — does not invent B."""
    binding = _binding({}, canonical=["www.example.com"], topology="")
    client = TestClient(_app_with_binding(binding))
    resp = client.get("/whoami", headers={"host": "acme.example.com"})
    assert resp.status_code == 400


def test_canonical_host_passes_through_with_no_tenant():
    binding = _binding({}, canonical=["www.example.com"])
    client = TestClient(_app_with_binding(binding))
    resp = client.get("/whoami", headers={"host": "www.example.com"})
    assert resp.status_code == 200
    assert resp.json() == {"tenant": None}


def test_demo_host_tenant_slug_binds_on_canonical_host(monkeypatch):
    """QA/recapture on localhost: DAZZLE_HOST_TENANT_SLUG binds current_tenant."""
    rows = {("Trust", "acme"): {"id": uuid4(), "slug": "acme", "name": "Acme"}}
    binding = _binding(rows, canonical=["localhost"])
    monkeypatch.setenv("DAZZLE_HOST_TENANT_SLUG", "acme")
    client = TestClient(_app_with_binding(binding))
    resp = client.get("/whoami", headers={"host": "localhost"})
    assert resp.status_code == 200
    assert resp.json() == {"tenant": "acme"}


def test_demo_host_tenant_slug_skips_test_seed_path(monkeypatch):
    """Seed before Workspace exists must not 404 on /__test__."""
    binding = _binding({}, canonical=["localhost"])
    monkeypatch.setenv("DAZZLE_HOST_TENANT_SLUG", "acme")
    app = FastAPI()

    @app.post("/__test__/seed")
    async def seed(request: Request) -> dict:
        tenant = getattr(request.state, "tenant", None)
        return {"tenant": None if tenant is None else tenant.slug}

    app.add_middleware(TenantResolutionMiddleware, binding=binding)
    client = TestClient(app)
    resp = client.post("/__test__/seed", headers={"host": "localhost"})
    assert resp.status_code == 200
    assert resp.json() == {"tenant": None}


def test_tenant_subdomain_resolves():
    rows = {("Trust", "acme"): {"id": uuid4(), "slug": "acme", "name": "Acme"}}
    binding = _binding(rows)
    client = TestClient(_app_with_binding(binding))
    resp = client.get("/whoami", headers={"host": "acme.example.com"})
    assert resp.status_code == 200
    assert resp.json() == {"tenant": "acme"}


def test_unknown_slug_returns_404_with_renderer():
    binding = _binding({})
    client = TestClient(_app_with_binding(binding))
    resp = client.get("/whoami", headers={"host": "nope.example.com"})
    assert resp.status_code == 404
    assert "404" in resp.text


def test_active_alias_resolves_before_slug_parse():
    """PR4: alias hostname binds the aliased tenant even on topology B."""
    tenant_id = uuid4()
    rows = {("Trust", "acme"): {"id": tenant_id, "slug": "acme", "name": "Acme"}}
    binding = _binding(rows)
    resolved = ResolvedTenant(kind="Trust", id=tenant_id, slug="acme", name="Acme")

    async def alias_lookup(host: str) -> ResolvedTenant | None:
        return resolved if host == "app.customer.com" else None

    object.__setattr__(binding, "alias_lookup", alias_lookup)
    client = TestClient(_app_with_binding(binding))
    resp = client.get("/whoami", headers={"host": "app.customer.com"})
    assert resp.status_code == 200
    assert resp.json() == {"tenant": "acme"}


def test_b_slug_host_still_resolves_with_alias_probe_wired():
    rows = {("Trust", "acme"): {"id": uuid4(), "slug": "acme", "name": "Acme"}}
    binding = _binding(rows)

    async def alias_lookup(host: str) -> ResolvedTenant | None:
        return None

    object.__setattr__(binding, "alias_lookup", alias_lookup)
    client = TestClient(_app_with_binding(binding))
    resp = client.get("/whoami", headers={"host": "acme.example.com"})
    assert resp.status_code == 200
    assert resp.json() == {"tenant": "acme"}


def test_leftover_alias_hostname_is_400_on_apex():
    binding = _binding({}, canonical=["www.example.com"], topology="apex")

    async def alias_lookup(host: str) -> ResolvedTenant | None:
        return None

    object.__setattr__(binding, "alias_lookup", alias_lookup)
    client = TestClient(_app_with_binding(binding))
    resp = client.get("/whoami", headers={"host": "app.customer.com"})
    assert resp.status_code == 400


def test_path_does_not_select_a_tenant():
    """D7: no path tenancy. A path segment is not a tenant slug."""
    rows = {("Trust", "acme"): {"id": uuid4(), "slug": "acme", "name": "Acme"}}
    binding = _binding(rows, canonical=["www.example.com"], topology="apex")
    app = FastAPI()

    @app.get("/{rest:path}")
    async def any_path(request: Request) -> dict:
        tenant = getattr(request.state, "tenant", None)
        return {"tenant": None if tenant is None else tenant.slug}

    app.add_middleware(TenantResolutionMiddleware, binding=binding)
    client = TestClient(app)
    resp = client.get("/acme", headers={"host": "www.example.com"})
    assert resp.status_code == 200
    assert resp.json() == {"tenant": None}
    resp = client.get("/acme", headers={"host": "other.example.net"})
    assert resp.status_code == 400


def test_apex_alias_binds_same_tenant_as_membership_host():
    tenant_id = uuid4()
    rows = {("Trust", "acme"): {"id": tenant_id, "slug": "acme", "name": "Acme"}}
    binding = _binding(rows, canonical=["www.example.com"], topology="apex")
    resolved = ResolvedTenant(kind="Trust", id=tenant_id, slug="acme", name="Acme")

    async def alias_lookup(host: str) -> ResolvedTenant | None:
        return resolved if host == "app.customer.com" else None

    object.__setattr__(binding, "alias_lookup", alias_lookup)
    client = TestClient(_app_with_binding(binding))
    resp = client.get("/whoami", headers={"host": "app.customer.com"})
    assert resp.status_code == 200
    assert resp.json() == {"tenant": "acme"}


def test_host_outside_domain_returns_400():
    binding = _binding({})
    client = TestClient(_app_with_binding(binding))
    resp = client.get("/whoami", headers={"host": "other-site.org"})
    assert resp.status_code == 400


def test_negative_cache_short_circuits_second_request():
    calls: list[str] = []

    def counting_lookup(entity: str, slug: str):
        calls.append(slug)
        return None

    cache = TenantCache(max_entries=64, ttl_seconds=60)
    resolver = Resolver(
        probes=[EntityProbe("Trust", "slug")],
        history_probe=None,
        lookup_fn=counting_lookup,
    )
    binding = TenantHostBinding(
        app_name="testapp",
        domain="example.com",
        canonical_hosts=(),
        cache=cache,
        resolver=resolver,
        not_found_renderer=lambda host: "<p>404</p>",
        expired_renderer=lambda old, new, domain: "<p>410</p>",
        topology="provider_subdomain",
    )
    client = TestClient(_app_with_binding(binding))
    client.get("/whoami", headers={"host": "ghost.example.com"})
    client.get("/whoami", headers={"host": "ghost.example.com"})
    assert calls == ["ghost"]  # second request hit NEGATIVE


def test_mount_tenant_resolution_middleware_is_idempotent():
    """#1407: calling the mount twice on the same app adds the middleware once.

    A custom ASGI wrapper can drive both the create_app_factory mount and the
    combined_server mount on the same `app`. The guard must dedup so we don't
    stack TenantResolutionMiddleware (and a second TenantCache) twice.
    """
    from types import SimpleNamespace

    from dazzle.core import ir
    from dazzle.http.runtime.app_factory import _mount_tenant_resolution_middleware

    entity = SimpleNamespace(
        name="Trust",
        fields=[],
        tenant_host=ir.TenantHostSpec(domain="example.com", slug_field="slug"),
    )
    appspec = SimpleNamespace(name="demo", domain=SimpleNamespace(entities=[entity]))
    builder = SimpleNamespace(repositories={})

    app = FastAPI()

    def _count() -> int:
        return sum(
            1
            for mw in app.user_middleware
            if getattr(mw, "cls", None) is TenantResolutionMiddleware
        )

    _mount_tenant_resolution_middleware(app, appspec, builder)  # type: ignore[arg-type]
    assert _count() == 1
    _mount_tenant_resolution_middleware(app, appspec, builder)  # type: ignore[arg-type]
    assert _count() == 1  # second call is a no-op


def test_mount_tenant_resolution_middleware_dedups_via_stack_when_marker_absent():
    """#1407 belt-and-suspenders: even without the app.state sentinel, an existing
    middleware in the stack is detected and re-mount is skipped."""
    from types import SimpleNamespace

    from dazzle.core import ir
    from dazzle.http.runtime.app_factory import _mount_tenant_resolution_middleware

    entity = SimpleNamespace(
        name="Trust",
        fields=[],
        tenant_host=ir.TenantHostSpec(domain="example.com", slug_field="slug"),
    )
    appspec = SimpleNamespace(name="demo", domain=SimpleNamespace(entities=[entity]))
    builder = SimpleNamespace(repositories={})

    app = FastAPI()
    _mount_tenant_resolution_middleware(app, appspec, builder)  # type: ignore[arg-type]
    # Clear the sentinel so only the stack scan can catch the duplicate.
    app.state._tenant_resolution_mounted = False
    _mount_tenant_resolution_middleware(app, appspec, builder)  # type: ignore[arg-type]
    count = sum(
        1 for mw in app.user_middleware if getattr(mw, "cls", None) is TenantResolutionMiddleware
    )
    assert count == 1
