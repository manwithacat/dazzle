"""Tests for #957 cycle 8 — TenantMiddleware exposes coerced tenant_config.

Cycle 7 added storage + a coercion helper. Cycle 8 wires them into the
request lifecycle: the middleware reads `record.config` (JSONB),
coerces against the DSL-declared `per_tenant_config` schema, and
exposes the typed dict on `request.state.tenant_config`.

These tests exercise the middleware via Starlette's TestClient with a
fake tenant registry — no real DB required. They verify:

  * `request.state.tenant_config` is always set on non-excluded paths
    (empty dict by default, never absent)
  * Coercion uses the schema passed at construction time
  * Excluded paths (/health, /docs, etc.) skip the resolver entirely
  * Per_tenant_config schema = None / empty produces an empty dict
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import pytest
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from dazzle_back.runtime.tenant_middleware import HeaderResolver, TenantMiddleware


@dataclass
class _FakeRecord:
    id: str = "00000000-0000-0000-0000-000000000001"
    slug: str = "acme"
    display_name: str = "Acme"
    schema_name: str = "tenant_acme"
    status: str = "active"
    created_at: str = "2026-05-01"
    updated_at: str = "2026-05-01"
    config: dict[str, Any] | None = None


class _FakeRegistry:
    """In-memory stand-in for `TenantRegistry`. Implements the single
    method TenantMiddleware's _RegistryCache calls (`get(slug)`)."""

    def __init__(self, records: dict[str, _FakeRecord]) -> None:
        self._records = records

    def get(self, slug: str) -> _FakeRecord | None:
        return self._records.get(slug)


def _make_app(
    *,
    record: _FakeRecord,
    schema: dict[str, str] | None,
) -> Starlette:
    async def read_x(request):  # type: ignore[no-untyped-def]
        return JSONResponse(
            {
                "tenant_slug": getattr(request.state.tenant, "slug", None),
                "tenant_config": dict(getattr(request.state, "tenant_config", {})),
            }
        )

    async def health(request):  # type: ignore[no-untyped-def]
        return JSONResponse(
            {
                "tenant_present": hasattr(request.state, "tenant"),
                "tenant_config_present": hasattr(request.state, "tenant_config"),
            }
        )

    app = Starlette(routes=[Route("/api/x", read_x), Route("/health", health)])
    app.add_middleware(
        TenantMiddleware,
        resolver=HeaderResolver(header_name="X-Tenant-ID"),
        registry=_FakeRegistry({record.slug: record}),
        per_tenant_config_schema=schema,
    )
    return app


@pytest.fixture()
def acme():
    return _FakeRecord(
        config={
            "locale": "en-GB",
            "max_users": "100",  # str → coerced to int
            "feature_billing": "true",  # str → coerced to bool
            "stale_key": "should-be-dropped",
        }
    )


def test_request_state_tenant_config_populated(acme):
    app = _make_app(
        record=acme,
        schema={"locale": "str", "max_users": "int", "feature_billing": "bool"},
    )
    client = TestClient(app)
    resp = client.get("/api/x", headers={"X-Tenant-ID": "acme"})
    assert resp.status_code == 200
    body = json.loads(resp.text)
    assert body["tenant_slug"] == "acme"
    assert body["tenant_config"] == {
        "locale": "en-GB",
        "max_users": 100,
        "feature_billing": True,
    }
    # Forward-compat: stale_key not in schema → dropped.
    assert "stale_key" not in body["tenant_config"]


def test_empty_schema_produces_empty_dict(acme):
    # Apps without a per_tenant_config block — request.state.tenant_config
    # must still exist (empty dict) so callers don't trip on getattr.
    app = _make_app(record=acme, schema=None)
    client = TestClient(app)
    resp = client.get("/api/x", headers={"X-Tenant-ID": "acme"})
    assert resp.status_code == 200
    assert json.loads(resp.text)["tenant_config"] == {}


def test_missing_keys_get_zero_values():
    # Tenant exists but config is empty / missing keys — the schema's
    # zero values fill in.
    record = _FakeRecord(config={})
    app = _make_app(
        record=record,
        schema={"locale": "str", "max_users": "int", "feature_billing": "bool"},
    )
    client = TestClient(app)
    resp = client.get("/api/x", headers={"X-Tenant-ID": "acme"})
    assert json.loads(resp.text)["tenant_config"] == {
        "locale": "",
        "max_users": 0,
        "feature_billing": False,
    }


def test_excluded_path_skips_middleware(acme):
    # /health is in the default excluded prefixes — the middleware
    # short-circuits before touching resolver/registry, and
    # request.state.tenant_config is never set.
    app = _make_app(record=acme, schema={"locale": "str"})
    client = TestClient(app)
    resp = client.get("/health")  # no X-Tenant-ID header
    assert resp.status_code == 200
    body = json.loads(resp.text)
    assert body["tenant_present"] is False
    assert body["tenant_config_present"] is False


def test_unknown_tenant_returns_404(acme):
    app = _make_app(record=acme, schema={"locale": "str"})
    client = TestClient(app)
    resp = client.get("/api/x", headers={"X-Tenant-ID": "unknown"})
    assert resp.status_code == 404


def test_missing_header_returns_400(acme):
    app = _make_app(record=acme, schema={"locale": "str"})
    client = TestClient(app)
    resp = client.get("/api/x")  # no X-Tenant-ID header
    assert resp.status_code == 400


def test_record_with_none_config_uses_zero_values():
    # TenantRecord.config has a default of {}; defending against
    # legacy / hand-constructed records with config=None.
    record = _FakeRecord(config=None)
    app = _make_app(record=record, schema={"locale": "str"})
    client = TestClient(app)
    resp = client.get("/api/x", headers={"X-Tenant-ID": "acme"})
    assert json.loads(resp.text)["tenant_config"] == {"locale": ""}
