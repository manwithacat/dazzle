"""Unit tests for the usage-signal request recorder (ADR-0050 Phase 3, 3a).

Pure logic — no DB. The Postgres round-trip (table + collector + aggregate) is
covered by tests/integration/test_usage_signal_pg.py.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from dazzle.http.runtime.usage_signal import (
    USAGE_KIND_ACTION,
    UsageSignalMiddleware,
    record_usage_from_request,
)


class _StubCollector:
    def __init__(self) -> None:
        self.calls: list[dict[str, str]] = []

    def record(self, *, tenant_id: str, surface: str, kind: str, target: str) -> None:
        self.calls.append(
            {"tenant_id": tenant_id, "surface": surface, "kind": kind, "target": target}
        )


def _request(
    *, header: str | None, collector: object | None, tenant_id: object | None = None
) -> SimpleNamespace:
    tenant = SimpleNamespace(id=tenant_id) if tenant_id is not None else None
    return SimpleNamespace(
        headers={"X-Dz-Usage-Action": header} if header is not None else {},
        app=SimpleNamespace(state=SimpleNamespace(usage_collector=collector)),
        state=SimpleNamespace(tenant=tenant),
    )


def test_records_action_click_with_resolved_tenant() -> None:
    c = _StubCollector()
    record_usage_from_request(
        _request(header="orders|/app/orders/new", collector=c, tenant_id="t-a")
    )
    assert c.calls == [
        {
            "tenant_id": "t-a",
            "surface": "orders",
            "kind": USAGE_KIND_ACTION,
            "target": "/app/orders/new",
        }
    ]


def test_single_tenant_records_empty_tenant_id() -> None:
    c = _StubCollector()
    record_usage_from_request(_request(header="orders|/x", collector=c, tenant_id=None))
    assert c.calls == [
        {"tenant_id": "", "surface": "orders", "kind": USAGE_KIND_ACTION, "target": "/x"}
    ]


def test_no_header_is_noop() -> None:
    c = _StubCollector()
    record_usage_from_request(_request(header=None, collector=c))
    assert c.calls == []


def test_no_collector_is_noop() -> None:
    # Must not raise when the app has no collector (e.g. no database).
    record_usage_from_request(_request(header="orders|/x", collector=None))


def test_malformed_header_without_separator_is_noop() -> None:
    c = _StubCollector()
    record_usage_from_request(_request(header="no-separator", collector=c, tenant_id="t"))
    assert c.calls == []


def test_empty_surface_or_target_is_noop() -> None:
    c = _StubCollector()
    record_usage_from_request(_request(header="|/x", collector=c, tenant_id="t"))
    record_usage_from_request(_request(header="orders|", collector=c, tenant_id="t"))
    assert c.calls == []


# --- ASGI middleware (raw ASGI, SSE-safe) ------------------------------------


@pytest.mark.asyncio
async def test_middleware_passes_through_and_records_post_response() -> None:
    c = _StubCollector()
    calls: list[str] = []

    async def inner(scope: object, receive: object, send: object) -> None:
        calls.append("inner")

    scope = {
        "type": "http",
        "headers": [(b"x-dz-usage-action", b"orders|/app/orders/new")],
        "state": {"tenant": SimpleNamespace(id="t-a")},
        "app": SimpleNamespace(state=SimpleNamespace(usage_collector=c)),
    }
    await UsageSignalMiddleware(inner)(scope, None, None)

    assert calls == ["inner"]  # inner app ran (pass-through)
    assert c.calls == [
        {
            "tenant_id": "t-a",
            "surface": "orders",
            "kind": USAGE_KIND_ACTION,
            "target": "/app/orders/new",
        }
    ]


@pytest.mark.asyncio
async def test_middleware_skips_non_http_scopes() -> None:
    c = _StubCollector()
    ran: list[str] = []

    async def inner(scope: object, receive: object, send: object) -> None:
        ran.append("inner")

    # A websocket scope must pass straight through with no recording.
    await UsageSignalMiddleware(inner)({"type": "websocket"}, None, None)
    assert ran == ["inner"]
    assert c.calls == []


def test_middleware_sees_resolved_tenant_end_to_end() -> None:
    """Load-bearing: the middleware records AFTER the inner app, so a tenant set by
    an inner middleware (stand-in for TenantResolutionMiddleware) is visible via the
    shared request scope. Proves the post-response ordering assumption end-to-end."""
    pytest.importorskip("fastapi")
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    app = FastAPI()
    c = _StubCollector()
    app.state.usage_collector = c

    @app.middleware("http")
    async def _set_tenant(request, call_next):  # type: ignore[no-untyped-def]
        request.state.tenant = SimpleNamespace(id="t-xyz")
        return await call_next(request)

    app.add_middleware(UsageSignalMiddleware)  # outermost → records post-response

    @app.get("/x")
    def _x() -> dict[str, bool]:
        return {"ok": True}

    TestClient(app).get("/x", headers={"X-Dz-Usage-Action": "orders|/x"})
    assert c.calls == [
        {"tenant_id": "t-xyz", "surface": "orders", "kind": USAGE_KIND_ACTION, "target": "/x"}
    ]
