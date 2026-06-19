"""#1421 — the page→REST internal self-fetch must forward the original request Host.

Root cause (confirmed against AegisMark): a `/app/<slug>/{id}` detail page handler does a
server-side fetch back to the app's own `/<plural>/{id}` REST endpoint. Under host tenancy
on Heroku/Railway, `_resolve_backend_url` returns a loopback URL (`127.0.0.1:$PORT`) and the
fetch forwarded only `Cookie`, never `Host` — so the internal request arrived with
`Host: 127.0.0.1`, which `TenantResolutionMiddleware` rejects as 400 "Bad Host". The detail
handler raised that as a 404 (the list handler swallowed it to an empty 200 — the
static-200/dynamic-404 asymmetry). The fix forwards the original Host on the self-call.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from dazzle.ui.runtime import page_routes


class _FakeResp:
    def __init__(self, payload: bytes) -> None:
        self._payload = payload

    def __enter__(self) -> _FakeResp:
        return self

    def __exit__(self, *a: object) -> None:
        return None

    def read(self) -> bytes:
        return self._payload


def _capture_urlopen(captured: dict[str, Any]):
    def _urlopen(req: Any, timeout: int = 5):  # noqa: ANN401
        captured["host"] = req.get_header("Host")
        captured["cookie"] = req.get_header("Cookie")
        return _FakeResp(json.dumps({"id": "x"}).encode())

    return _urlopen


def test_sync_fetch_forwards_host_header(monkeypatch) -> None:
    captured: dict[str, Any] = {}
    monkeypatch.setattr(page_routes.urllib.request, "urlopen", _capture_urlopen(captured))
    page_routes._sync_fetch(
        "http://127.0.0.1:5000/markingresults/abc",
        cookies={"session": "s"},
        host="demo.aegismark.ai",
    )
    # The tenant Host travels on the loopback self-call so TenantResolutionMiddleware
    # re-resolves the SAME tenant instead of rejecting 127.0.0.1 as "Bad Host".
    assert captured["host"] == "demo.aegismark.ai"
    assert captured["cookie"] == "session=s"


def test_sync_fetch_no_host_when_absent(monkeypatch) -> None:
    captured: dict[str, Any] = {}
    monkeypatch.setattr(page_routes.urllib.request, "urlopen", _capture_urlopen(captured))
    page_routes._sync_fetch("http://127.0.0.1:5000/markingresults/abc", cookies=None)
    assert captured["host"] is None  # no override → urllib derives it from the URL


def test_host_forward_gate_loopback_only() -> None:
    # Loopback backend (Heroku/Railway $PORT shape) → forward the tenant Host.
    assert (
        page_routes._resolve_host_to_forward("http://127.0.0.1:5000", "demo.aegismark.ai")
        == "demo.aegismark.ai"
    )
    assert (
        page_routes._resolve_host_to_forward("http://localhost:8000", "demo.x.example")
        == "demo.x.example"
    )
    # External DAZZLE_BACKEND_URL split-service → do NOT override its Host (review #1421).
    assert (
        page_routes._resolve_host_to_forward("https://backend.mycompany.com", "demo.x.example")
        is None
    )
    # No original host → nothing to forward.
    assert page_routes._resolve_host_to_forward("http://127.0.0.1:5000", None) is None


def test_fetch_json_threads_host_through(monkeypatch) -> None:
    captured: dict[str, Any] = {}
    monkeypatch.setattr(page_routes.urllib.request, "urlopen", _capture_urlopen(captured))
    asyncio.run(
        page_routes._fetch_json(
            "http://127.0.0.1:5000",
            "/markingresults/{id}",
            "abc",
            {"session": "s"},
            "demo.aegismark.ai",
        )
    )
    assert captured["host"] == "demo.aegismark.ai"
