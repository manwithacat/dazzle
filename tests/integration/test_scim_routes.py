"""SCIM 2.0 route tests (auth Plan 4c.ii).

TestClient over a fake AuthStore backing both bearer-auth and the provisioning
kernel — no Postgres. Pins bearer-auth (401), the User lifecycle, and the
load-bearing cross-org isolation (a bearer for org A can't touch org B by id).
"""

from __future__ import annotations

import uuid
from datetime import datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from dazzle.back.runtime.auth.connections import ConnectionRecord
from dazzle.back.runtime.auth.scim_routes import create_scim_routes


def _conn(cid, tenant, bearer, *, verified=("acme.test",)) -> ConnectionRecord:
    return ConnectionRecord(
        id=cid,
        tenant_id=tenant,
        type="scim",
        provider="native",
        domains=list(verified),
        verified_domains=list(verified),
        config={},
        secrets={"scim_bearer": bearer},
        group_mapping={},
        status="active",
        created_at=datetime(2026, 6, 6),
        updated_at=datetime(2026, 6, 6),
    )


class _User:
    def __init__(self, email):
        self.id = uuid.uuid4()
        self.email = email
        self.email_verified = False


class _Membership:
    def __init__(self, mid, tenant_id, identity_id, *, roles=None, status="active"):
        self.id = mid
        self.tenant_id = tenant_id
        self.identity_id = identity_id
        self.roles = roles or []
        self.status = status


class _Store:
    def __init__(self, connections):
        self._conns = list(connections)
        self._users: dict[str, _User] = {}
        self._by_id: dict[str, _User] = {}
        self._memberships: list[_Membership] = []
        self.revoked: list[str] = []
        self._n = 0

    # bearer auth
    def get_scim_connection_by_bearer(self, token):
        if not token:
            return None
        for c in self._conns:
            if c.secrets.get("scim_bearer") == token:
                return c
        return None

    # identities
    def get_user_by_email(self, email):
        return self._users.get(email)

    def get_user_by_id(self, uid):
        return self._by_id.get(str(uid))

    def create_user(self, *, email, password, username=None):
        u = _User(email)
        self._users[email] = u
        self._by_id[str(u.id)] = u
        return u

    def mark_email_verified(self, user_id):
        return True

    # memberships
    def get_membership(self, membership_id):
        return next((m for m in self._memberships if m.id == membership_id), None)

    def get_memberships_for_identity(self, identity_id):
        return [m for m in self._memberships if m.identity_id == identity_id]

    def get_memberships_for_tenant(self, tenant_id):
        return [m for m in self._memberships if m.tenant_id == tenant_id]

    def create_membership(self, *, tenant_id, identity_id, roles=None, reason=None):
        self._n += 1
        m = _Membership(f"mem-{self._n}", tenant_id, identity_id, roles=roles)
        self._memberships.append(m)
        return m

    def suspend_membership(self, membership_id, *, reason=None):
        m = self.get_membership(membership_id)
        if m:
            m.status = "suspended"
        return m

    def reactivate_membership(self, membership_id, *, reason=None):
        m = self.get_membership(membership_id)
        if m:
            m.status = "active"
        return m

    def remove_membership(self, membership_id, *, reason=None):
        before = len(self._memberships)
        self._memberships = [m for m in self._memberships if m.id != membership_id]
        return len(self._memberships) < before

    def update_membership_roles(self, membership_id, roles, *, reason=None):
        m = self.get_membership(membership_id)
        if m:
            m.roles = roles
        return m

    def delete_sessions_for_membership(self, membership_id):
        self.revoked.append(membership_id)
        return 1


def _client(store) -> TestClient:
    app = FastAPI()
    app.include_router(create_scim_routes())
    app.state.auth_store = store
    return TestClient(app)


def _auth(bearer):
    return {"Authorization": f"Bearer {bearer}"}


@pytest.fixture
def store():
    return _Store([_conn("c1", "org-1", "tok1"), _conn("c2", "org-2", "tok2")])


# ---- bearer auth ----


def test_no_bearer_is_401(store) -> None:
    assert (
        _client(store).post("/scim/v2/Users", json={"userName": "x@acme.test"}).status_code == 401
    )


def test_bad_bearer_is_401(store) -> None:
    r = _client(store).get("/scim/v2/Users", headers=_auth("nope"))
    assert r.status_code == 401


def test_service_provider_config_requires_bearer(store) -> None:
    c = _client(store)
    assert c.get("/scim/v2/ServiceProviderConfig").status_code == 401
    assert c.get("/scim/v2/ServiceProviderConfig", headers=_auth("tok1")).status_code == 200


# ---- create ----


def test_create_user_provisions_and_returns_scim(store) -> None:
    r = _client(store).post(
        "/scim/v2/Users", json={"userName": "jane@acme.test", "active": True}, headers=_auth("tok1")
    )
    assert r.status_code == 201
    body = r.json()
    assert body["userName"] == "jane@acme.test" and body["active"] is True
    assert body["id"] and body["schemas"] == ["urn:ietf:params:scim:schemas:core:2.0:User"]
    # The membership landed in org-1 (the bearer's org).
    assert store._memberships[0].tenant_id == "org-1"


def test_create_user_unverified_domain_is_400(store) -> None:
    r = _client(store).post(
        "/scim/v2/Users", json={"userName": "x@evil.test"}, headers=_auth("tok1")
    )
    assert r.status_code == 400


# ---- read / filter ----


def test_get_user_by_id(store) -> None:
    c = _client(store)
    mid = c.post(
        "/scim/v2/Users", json={"userName": "jane@acme.test"}, headers=_auth("tok1")
    ).json()["id"]
    r = c.get(f"/scim/v2/Users/{mid}", headers=_auth("tok1"))
    assert r.status_code == 200 and r.json()["userName"] == "jane@acme.test"


def test_filter_by_username(store) -> None:
    c = _client(store)
    c.post("/scim/v2/Users", json={"userName": "jane@acme.test"}, headers=_auth("tok1"))
    r = c.get('/scim/v2/Users?filter=userName eq "jane@acme.test"', headers=_auth("tok1"))
    body = r.json()
    assert body["totalResults"] == 1 and body["Resources"][0]["userName"] == "jane@acme.test"


def test_filter_no_match_is_empty_list(store) -> None:
    r = _client(store).get(
        '/scim/v2/Users?filter=userName eq "nobody@acme.test"', headers=_auth("tok1")
    )
    assert r.json()["totalResults"] == 0


# ---- patch (active toggle) ----


def test_patch_deactivate_suspends_and_revokes(store) -> None:
    c = _client(store)
    mid = c.post(
        "/scim/v2/Users", json={"userName": "jane@acme.test"}, headers=_auth("tok1")
    ).json()["id"]
    r = c.patch(
        f"/scim/v2/Users/{mid}",
        json={"Operations": [{"op": "replace", "path": "active", "value": False}]},
        headers=_auth("tok1"),
    )
    assert r.status_code == 200 and r.json()["active"] is False
    assert store.revoked == [mid]  # sessions revoked on deactivate


def test_patch_entra_value_dict_form(store) -> None:
    c = _client(store)
    mid = c.post(
        "/scim/v2/Users", json={"userName": "jane@acme.test"}, headers=_auth("tok1")
    ).json()["id"]
    # Entra sends {"value": {"active": "False"}} (stringified).
    r = c.patch(
        f"/scim/v2/Users/{mid}",
        json={"Operations": [{"op": "Replace", "value": {"active": "False"}}]},
        headers=_auth("tok1"),
    )
    assert r.status_code == 200 and r.json()["active"] is False


# ---- delete ----


def test_delete_user(store) -> None:
    c = _client(store)
    mid = c.post(
        "/scim/v2/Users", json={"userName": "jane@acme.test"}, headers=_auth("tok1")
    ).json()["id"]
    assert c.delete(f"/scim/v2/Users/{mid}", headers=_auth("tok1")).status_code == 204
    assert c.get(f"/scim/v2/Users/{mid}", headers=_auth("tok1")).status_code == 404


# ---- cross-org isolation (load-bearing) ----


def test_cross_org_get_is_404(store) -> None:
    c = _client(store)
    # Provision into org-1 (tok1), then try to read it with org-2's bearer (tok2).
    mid = c.post(
        "/scim/v2/Users", json={"userName": "jane@acme.test"}, headers=_auth("tok1")
    ).json()["id"]
    assert c.get(f"/scim/v2/Users/{mid}", headers=_auth("tok2")).status_code == 404


def test_cross_org_patch_is_404(store) -> None:
    c = _client(store)
    mid = c.post(
        "/scim/v2/Users", json={"userName": "jane@acme.test"}, headers=_auth("tok1")
    ).json()["id"]
    r = c.patch(
        f"/scim/v2/Users/{mid}",
        json={"Operations": [{"op": "replace", "path": "active", "value": False}]},
        headers=_auth("tok2"),
    )
    assert r.status_code == 404
    assert store.revoked == []  # org-2's bearer never acted on org-1's membership


def test_cross_org_delete_is_404(store) -> None:
    c = _client(store)
    mid = c.post(
        "/scim/v2/Users", json={"userName": "jane@acme.test"}, headers=_auth("tok1")
    ).json()["id"]
    assert c.delete(f"/scim/v2/Users/{mid}", headers=_auth("tok2")).status_code == 404
    assert c.get(f"/scim/v2/Users/{mid}", headers=_auth("tok1")).status_code == 200  # still there


def test_malformed_json_body_is_400(store) -> None:
    r = _client(store).post(
        "/scim/v2/Users",
        content="{not json",
        headers={**_auth("tok1"), "Content-Type": "application/json"},
    )
    assert r.status_code == 400
