"""Unit tests for the usage-signal request recorder (ADR-0050 Phase 3, 3a).

Pure logic — no DB. The Postgres round-trip (table + collector + aggregate) is
covered by tests/integration/test_usage_signal_pg.py.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from dazzle.http.runtime.usage_signal import (
    USAGE_KIND_ACTION,
    USAGE_KIND_FIELD,
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


# --- field-engagement beacon endpoint (Phase 5 / 1a) -------------------------


def _beacon_app(collector: object) -> object:
    from fastapi import FastAPI

    from dazzle.http.runtime.usage_routes import create_usage_routes

    app = FastAPI()
    app.state.usage_collector = collector

    @app.middleware("http")
    async def _set_tenant(request, call_next):  # type: ignore[no-untyped-def]
        request.state.tenant = SimpleNamespace(id="t-1")
        return await call_next(request)

    app.include_router(create_usage_routes())
    return app


def test_field_beacon_records_and_returns_204() -> None:
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    c = _StubCollector()
    r = TestClient(_beacon_app(c)).post(
        "/_dz/usage/field", data={"surface": "task_edit", "field": "title"}
    )
    assert r.status_code == 204
    assert c.calls == [
        {"tenant_id": "t-1", "surface": "task_edit", "kind": USAGE_KIND_FIELD, "target": "title"}
    ]


def test_field_beacon_empty_payload_is_noop_still_204() -> None:
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    c = _StubCollector()
    r = TestClient(_beacon_app(c)).post("/_dz/usage/field", data={"surface": "", "field": ""})
    assert r.status_code == 204
    assert c.calls == []


def test_dz_usage_js_bundled() -> None:
    """dz-usage.js must be in the build manifest AND the built dist bundle, or the
    1a field-engagement beacon never loads in a real browser (mirrors the dz-csrf
    manifest guard)."""
    import importlib.util
    from pathlib import Path

    repo = Path(__file__).resolve().parents[2]
    spec = importlib.util.spec_from_file_location("build_dist", repo / "scripts" / "build_dist.py")
    assert spec is not None and spec.loader is not None
    build_dist = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(build_dist)
    assert "dz-usage.js" in {p.name for p in build_dist.JS_SOURCES}

    dist = repo / "src" / "dazzle" / "page" / "runtime" / "static" / "dist" / "dazzle.min.js"
    assert dist.exists(), "dist bundle missing — run scripts/build_dist.py"
    assert "/_dz/usage/field" in dist.read_text(encoding="utf-8"), (
        "dz-usage.js not in the dist bundle — rebuild with scripts/build_dist.py"
    )
