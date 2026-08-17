"""Membership leftover roles must not invent undeclared personas (cycle 2209).

leftover-honest catalog id already exists (oral #69). Member-admin
and invite still persisted leftover ``roles=zzz`` as a grant.
Valid declared persona names ride; leftover omitted. All leftover
stays put (400, no write). No declared catalog is pass-through.
Live domain_join_co ``admin`` / ``member``. Oral #89 — not leftover
onboarding guide/step (oral #88), not leftover catalog picker (oral #69).
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from dazzle.http.runtime.auth.invitation_routes import create_invitation_routes
from dazzle.http.runtime.auth.member_admin import (
    declared_persona_ids,
    leftover_honest_persona_roles,
    leftover_persona_roles_stay_put,
)
from dazzle.http.runtime.auth.member_admin_routes import create_member_admin_routes

_MEMBER_ADMIN = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "dazzle"
    / "http"
    / "runtime"
    / "auth"
    / "member_admin.py"
)
_MEMBER_ROUTES = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "dazzle"
    / "http"
    / "runtime"
    / "auth"
    / "member_admin_routes.py"
)
_INVITE_ROUTES = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "dazzle"
    / "http"
    / "runtime"
    / "auth"
    / "invitation_routes.py"
)
_LIVE = Path(__file__).resolve().parents[2] / "examples" / "domain_join_co" / "dsl" / "domain.dsl"


def _appspec(*ids: str) -> SimpleNamespace:
    return SimpleNamespace(personas=[SimpleNamespace(id=pid, name=pid) for pid in ids])


@pytest.mark.parametrize(
    ("raw", "declared", "expected"),
    [
        ("zzz", ("admin", "member"), ()),
        ("ghost,admin", ("admin", "member"), ("admin",)),
        ("admin, member", ("admin", "member"), ("admin", "member")),
        ("member", ("admin", "member"), ("member",)),
        ("ADMIN", ("admin", "member"), ()),
        ("", ("admin", "member"), ()),
        (None, ("admin", "member"), ()),
        (["member", "zzz"], ("admin", "member"), ("member",)),
        ("zzz", (), ("zzz",)),
        ("member, approver", (), ("member", "approver")),
    ],
    ids=[
        "leftover-only",
        "mixed-omit",
        "valid-pair",
        "valid-one",
        "leftover-case",
        "empty",
        "none",
        "list-mixed",
        "no-catalog-leftover",
        "no-catalog-pair",
    ],
)
def test_leftover_honest_persona_roles_do_not_invent(
    raw: object, declared: tuple[str, ...], expected: tuple[str, ...]
) -> None:
    assert leftover_honest_persona_roles(raw, declared) == expected


def test_leftover_persona_roles_stay_put_when_all_junk() -> None:
    assert leftover_persona_roles_stay_put("zzz", ("admin", "member")) is True
    assert leftover_persona_roles_stay_put("ghost,admin", ("admin", "member")) is False
    assert leftover_persona_roles_stay_put("zzz", ()) is False
    assert leftover_persona_roles_stay_put("", ("admin", "member")) is False


def test_declared_persona_ids_from_appspec() -> None:
    assert declared_persona_ids(_appspec("admin", "member")) == ("admin", "member")
    assert declared_persona_ids(None) == ()
    assert declared_persona_ids(SimpleNamespace()) == ()


def _member_app(store: MagicMock) -> FastAPI:
    app = FastAPI()
    app.state.auth_store = store
    app.state.org_admin_roles = ["admin"]
    app.state.appspec = _appspec("admin", "member")
    app.state.sitespec = {}
    app.include_router(create_member_admin_routes())
    return app


def _gated_store(*, target_roles: list[str] | None = None) -> MagicMock:
    admin_m = SimpleNamespace(
        id="m-admin",
        tenant_id="org1",
        identity_id="u1",
        roles=["admin"],
        status="active",
    )
    target = SimpleNamespace(
        id="m-bob",
        tenant_id="org1",
        identity_id="u2",
        roles=target_roles or ["member"],
        status="active",
    )
    user = SimpleNamespace(id="u1", email="admin@acme.test")
    ctx = SimpleNamespace(is_authenticated=True, user=user, active_membership=admin_m)
    store = MagicMock()
    store.validate_session.return_value = ctx
    store.get_memberships_for_tenant.return_value = [admin_m, target]
    store.get_membership.side_effect = lambda mid: {"m-admin": admin_m, "m-bob": target}.get(mid)
    return store


def test_leftover_change_roles_does_not_write() -> None:
    store = _gated_store()
    client = TestClient(_member_app(store), follow_redirects=False)
    client.cookies.set("dazzle_session", "sid")
    resp = client.post("/auth/members/roles?membership_id=m-bob", data={"roles": "zzz"})
    assert resp.status_code == 400
    store.update_membership_roles.assert_not_called()


def test_mixed_leftover_change_roles_omits_junk() -> None:
    store = _gated_store()
    client = TestClient(_member_app(store), follow_redirects=False)
    client.cookies.set("dazzle_session", "sid")
    resp = client.post(
        "/auth/members/roles?membership_id=m-bob", data={"roles": "member,zzz,admin"}
    )
    assert resp.status_code in (204, 303)
    store.update_membership_roles.assert_called_once()
    args, kwargs = store.update_membership_roles.call_args
    written = args[1] if len(args) > 1 else kwargs.get("new_roles") or kwargs.get("roles")
    assert list(written) == ["member", "admin"]


def test_valid_change_roles_still_writes() -> None:
    store = _gated_store()
    client = TestClient(_member_app(store), follow_redirects=False)
    client.cookies.set("dazzle_session", "sid")
    resp = client.post("/auth/members/roles?membership_id=m-bob", data={"roles": "admin"})
    assert resp.status_code in (204, 303)
    store.update_membership_roles.assert_called_once()


def _invite_app(store: MagicMock) -> FastAPI:
    app = FastAPI()
    app.state.auth_store = store
    app.state.org_admin_roles = ["admin"]
    app.state.appspec = _appspec("admin", "member")
    app.state.sitespec = {}
    app.include_router(create_invitation_routes())
    return app


def test_leftover_invite_roles_do_not_write(monkeypatch: pytest.MonkeyPatch) -> None:
    created: list[object] = []

    def _create(*_a: object, **_k: object) -> str:
        created.append(_k)
        return "tok"

    monkeypatch.setattr(
        "dazzle.http.runtime.auth.invitations.create_invitation",
        _create,
    )
    store = _gated_store()
    store.get_organization.return_value = SimpleNamespace(name="Acme")
    client = TestClient(_invite_app(store), follow_redirects=False)
    client.cookies.set("dazzle_session", "sid")
    resp = client.post("/auth/invite", data={"email": "bob@acme.test", "roles": "zzz"})
    assert resp.status_code == 400
    assert created == []


def test_helper_source_pins_persona_role_leftover() -> None:
    helper = _MEMBER_ADMIN.read_text()
    assert "def leftover_honest_persona_roles" in helper
    assert "def leftover_persona_roles_stay_put" in helper
    assert "leftover_honest_catalog_id" in helper
    routes = _MEMBER_ROUTES.read_text()
    assert "leftover_persona_roles_stay_put" in routes
    assert "leftover_honest_persona_roles" in routes
    invite = _INVITE_ROUTES.read_text()
    assert "leftover_persona_roles_stay_put" in invite
    assert "leftover_honest_persona_roles" in invite


def test_live_domain_join_co_declares_admin_and_member() -> None:
    src = _LIVE.read_text()
    assert "persona admin " in src
    assert "persona member " in src
