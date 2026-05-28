"""Tests for the tenant middleware + default templates (#1289 slice 3)."""

from __future__ import annotations

from dazzle.back.runtime.tenant.templates import (
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

from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from dazzle.back.runtime.tenant.cache import TenantCache
from dazzle.back.runtime.tenant.middleware import (
    TenantHostBinding,
    TenantResolutionMiddleware,
)
from dazzle.back.runtime.tenant.resolver import EntityProbe, Resolver


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
    )


def test_canonical_host_passes_through_with_no_tenant():
    binding = _binding({}, canonical=["www.example.com"])
    client = TestClient(_app_with_binding(binding))
    resp = client.get("/whoami", headers={"host": "www.example.com"})
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
    )
    client = TestClient(_app_with_binding(binding))
    client.get("/whoami", headers={"host": "ghost.example.com"})
    client.get("/whoami", headers={"host": "ghost.example.com"})
    assert calls == ["ghost"]  # second request hit NEGATIVE
