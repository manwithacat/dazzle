"""#1404 Phase B — ApexDiscoveryMiddleware gating + redirect wiring."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from starlette.applications import Starlette
from starlette.responses import PlainTextResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from dazzle.back.runtime.auth.models import MembershipRecord
from dazzle.back.runtime.tenant.apex_middleware import ApexDiscoveryMiddleware


class _FakeRepo:
    def __init__(self, rows: dict[str, str]) -> None:
        self._rows = rows  # tenant_id -> slug

    async def list(self, *, filters: dict[str, Any], page_size: int = 1) -> dict[str, Any]:
        tid = filters.get("id")
        slug = self._rows.get(tid)
        return {"items": [SimpleNamespace(slug=slug)] if slug else []}


def _build(monkeypatch, *, uid: str | None, memberships, memberships_required=True, rows=None):
    async def _home(_request):
        return PlainTextResponse("APP")

    app = Starlette(routes=[Route("/", _home), Route("/app", _home)])
    app.add_middleware(
        ApexDiscoveryMiddleware,
        canonical_hosts=("example.com",),
        domain="example.com",
        root_entity="Org",
        root_slug_field="slug",
        repositories={"Org": _FakeRepo(rows or {})},
    )
    app.state.auth_store = SimpleNamespace(get_memberships_for_identity=lambda _id: memberships)
    app.state.memberships_required = memberships_required
    monkeypatch.setattr("dazzle.back.runtime.auth.current.current_user_id", lambda _request: uid)
    return TestClient(app)


def _m(mid: str, tid: str, status: str = "active") -> MembershipRecord:
    return MembershipRecord(id=mid, tenant_id=tid, identity_id="u-1", status=status)


class TestApexDiscoveryMiddleware:
    def test_unauthed_apex_root_passes_through(self, monkeypatch) -> None:
        c = _build(monkeypatch, uid=None, memberships=[])
        r = c.get("/", headers={"host": "example.com"}, follow_redirects=False)
        assert r.status_code == 200 and r.text == "APP"

    def test_authed_single_membership_redirects_to_org_host(self, monkeypatch) -> None:
        c = _build(
            monkeypatch,
            uid="u-1",
            memberships=[_m("m-1", "t-1")],
            rows={"t-1": "acme"},
        )
        r = c.get("/", headers={"host": "example.com"}, follow_redirects=False)
        assert r.status_code == 302
        assert r.headers["location"] == "https://acme.example.com/"

    def test_non_apex_host_passes_through(self, monkeypatch) -> None:
        # A tenant subdomain is not a canonical host → no discovery.
        c = _build(monkeypatch, uid="u-1", memberships=[_m("m-1", "t-1")], rows={"t-1": "acme"})
        r = c.get("/", headers={"host": "acme.example.com"}, follow_redirects=False)
        assert r.status_code == 200 and r.text == "APP"

    def test_non_root_path_passes_through(self, monkeypatch) -> None:
        c = _build(monkeypatch, uid="u-1", memberships=[_m("m-1", "t-1")], rows={"t-1": "acme"})
        # /auth/* is not a tracked root path (would loop) — but we only mounted "/" and
        # "/app"; request a path outside the app-root set.
        r = c.get("/app", headers={"host": "example.com"}, follow_redirects=False)
        assert r.status_code == 302  # /app IS a root path → discovery fires
        # A non-root path is passed through: request "/" is root, "/app" is root; verify
        # a genuinely non-root GET is untouched by hitting a 404 path (middleware passes).
        r2 = c.get("/somewhere", headers={"host": "example.com"}, follow_redirects=False)
        assert r2.status_code == 404  # passed through to routing (no redirect)

    def test_post_method_passes_through(self, monkeypatch) -> None:
        c = _build(monkeypatch, uid="u-1", memberships=[_m("m-1", "t-1")], rows={"t-1": "acme"})
        r = c.post("/", headers={"host": "example.com"}, follow_redirects=False)
        assert r.status_code in (404, 405)  # not a GET → no discovery, falls to routing

    def test_no_memberships_ungated_passes_through(self, monkeypatch) -> None:
        c = _build(monkeypatch, uid="u-1", memberships=[], memberships_required=False)
        r = c.get("/", headers={"host": "example.com"}, follow_redirects=False)
        assert r.status_code == 200 and r.text == "APP"
