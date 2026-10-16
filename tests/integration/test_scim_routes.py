"""SCIM 2.0 route tests (auth Plan 4c.ii; restored by DD-013 plan EA-3).

Most tests run a TestClient over a fake AuthStore backing both bearer-auth and the
provisioning kernel — no Postgres. They pin bearer-auth (401), the User lifecycle,
and the load-bearing cross-org isolation (a bearer for org A can't touch org B by
id). The ``# ---- real Postgres`` section at the end runs the same router over a real
``AuthStore`` (``TEST_DATABASE_URL``) for what the fake cannot prove: the bearer
rotation grace window, the org-scoped session kill, and the ``externalId`` unique
index under a changed-email re-push.
"""

from __future__ import annotations

import base64
import uuid
from datetime import datetime, timedelta
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from dazzle.http.runtime.auth.connections import ConnectionRecord
from dazzle.http.runtime.auth.scim_routes import create_scim_routes
from dazzle.http.runtime.auth.store import AuthStore
from dazzle.http.runtime.subsystems.auth import AuthSubsystem
from tests.unit._auth_pg import AUTH_TABLES, fresh_url


def _conn(cid, tenant, bearer, *, verified=("acme.test",), group_mapping=None) -> ConnectionRecord:
    return ConnectionRecord(
        id=cid,
        tenant_id=tenant,
        type="scim",
        provider="native",
        domains=list(verified),
        verified_domains=list(verified),
        config={},
        secrets={"scim_bearer": bearer},
        group_mapping=group_mapping or {},
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
    def __init__(
        self, mid, tenant_id, identity_id, *, roles=None, status="active", external_id=None
    ):
        self.id = mid
        self.tenant_id = tenant_id
        self.identity_id = identity_id
        self.roles = roles or []
        self.status = status
        self.external_id = external_id


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

    def get_membership_by_external_id(self, tenant_id, external_id):
        return next(
            (
                m
                for m in self._memberships
                if m.tenant_id == tenant_id and getattr(m, "external_id", None) == external_id
            ),
            None,
        )

    def create_membership(
        self, *, tenant_id, identity_id, roles=None, external_id=None, reason=None
    ):
        self._n += 1
        m = _Membership(
            f"mem-{self._n}", tenant_id, identity_id, roles=roles, external_id=external_id
        )
        self._memberships.append(m)
        return m

    def update_membership_external_id(self, membership_id, external_id):
        m = self.get_membership(membership_id)
        if m:
            m.external_id = external_id
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

    # connection reads

    def get_connections_for_tenant(self, tenant_id):
        return []

    # SCIM groups (#1342) — in-memory
    def _ensure_group_state(self):
        if not hasattr(self, "_groups"):
            self._groups: dict[str, Any] = {}  # gid -> SimpleNamespace
            self._gmembers: dict[str, list[str]] = {}  # gid -> [membership_id]

    def create_scim_group(self, connection_id, display_name, external_id=None):
        self._ensure_group_state()
        gid = str(uuid.uuid4())
        g = SimpleNamespace(
            id=gid,
            connection_id=connection_id,
            display_name=display_name,
            external_id=external_id,
            created_at="t",
            updated_at="t",
        )
        self._groups[gid] = g
        self._gmembers[gid] = []
        return g

    def update_scim_group_external_id(self, group_id, connection_id, external_id):
        self._ensure_group_state()
        g = self._groups.get(group_id)
        if g and g.connection_id == connection_id:
            g.external_id = external_id

    def get_member_group_keys(self, membership_id, connection_id):
        self._ensure_group_state()
        keys = []
        for gid, g in self._groups.items():
            if g.connection_id == connection_id and membership_id in self._gmembers.get(gid, []):
                keys.append(g.display_name)
                if getattr(g, "external_id", None):
                    keys.append(g.external_id)
        return keys

    def get_scim_group(self, group_id, connection_id):
        self._ensure_group_state()
        g = self._groups.get(group_id)
        return g if g and g.connection_id == connection_id else None

    def list_scim_groups(self, connection_id, display_name=None):
        self._ensure_group_state()
        return [
            g
            for g in self._groups.values()
            if g.connection_id == connection_id
            and (display_name is None or g.display_name == display_name)
        ]

    def rename_scim_group(self, group_id, connection_id, display_name):
        self._ensure_group_state()
        g = self._groups.get(group_id)
        if g and g.connection_id == connection_id:
            g.display_name = display_name

    def delete_scim_group(self, group_id, connection_id):
        self._ensure_group_state()
        g = self._groups.get(group_id)
        if g and g.connection_id == connection_id:
            del self._groups[group_id]
            self._gmembers.pop(group_id, None)
            return True
        return False

    def get_group_member_ids(self, group_id):
        self._ensure_group_state()
        return list(self._gmembers.get(group_id, []))

    def add_group_member(self, group_id, membership_id):
        self._ensure_group_state()
        members = self._gmembers.setdefault(group_id, [])
        if membership_id not in members:
            members.append(membership_id)

    def remove_group_member(self, group_id, membership_id):
        self._ensure_group_state()
        members = self._gmembers.get(group_id, [])
        if membership_id in members:
            members.remove(membership_id)

    def replace_group_members(self, group_id, membership_ids):
        self._ensure_group_state()
        self._gmembers[group_id] = list(membership_ids)

    def get_member_group_names(self, membership_id, connection_id):
        self._ensure_group_state()
        return [
            g.display_name
            for gid, g in self._groups.items()
            if g.connection_id == connection_id and membership_id in self._gmembers.get(gid, [])
        ]


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


def test_create_user_captures_and_echoes_external_id(store) -> None:
    # #1342 gap 1: Entra sends externalId (its user objectId GUID) and expects it round-tripped.
    c = _client(store)
    r = c.post(
        "/scim/v2/Users",
        json={"userName": "jane@acme.test", "externalId": "entra-guid-1"},
        headers=_auth("tok1"),
    )
    assert r.status_code == 201 and r.json()["externalId"] == "entra-guid-1"
    mid = r.json()["id"]
    # echoed on subsequent reads too
    assert (
        c.get(f"/scim/v2/Users/{mid}", headers=_auth("tok1")).json()["externalId"] == "entra-guid-1"
    )


def test_repush_under_changed_email_dedupes_by_external_id(store) -> None:
    # The IdP renamed the user's email and re-pushed the same externalId. We must update the
    # existing membership, not fork a duplicate identity.
    c = _client(store)
    first = c.post(
        "/scim/v2/Users",
        json={"userName": "old@acme.test", "externalId": "entra-guid-1"},
        headers=_auth("tok1"),
    ).json()
    second = c.post(
        "/scim/v2/Users",
        json={"userName": "new@acme.test", "externalId": "entra-guid-1"},
        headers=_auth("tok1"),
    )
    assert second.status_code == 201
    assert second.json()["id"] == first["id"]  # same membership
    assert len(store._memberships) == 1  # no duplicate
    # the global identity email is NOT rewritten from the SCIM push (loud-log, no auto-rename)
    assert store.get_user_by_email("old@acme.test") is not None
    assert store.get_user_by_email("new@acme.test") is None


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


def test_leftover_users_filter_is_invalid_filter(store) -> None:
    # Leftover ``?filter=zzz`` used to invent the unfiltered Users list.
    c = _client(store)
    c.post("/scim/v2/Users", json={"userName": "jane@acme.test"}, headers=_auth("tok1"))
    r = c.get("/scim/v2/Users?filter=zzz", headers=_auth("tok1"))
    assert r.status_code == 400
    assert r.json().get("scimType") == "invalidFilter"


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


# ---- Groups (#1342) ----


def _group_store():
    s = _Store([_conn("c1", "org-1", "tok1", group_mapping={"Eng": "engineer"})])
    m = s.create_membership(tenant_id="org-1", identity_id="id-1", roles=[])
    return s, m


def test_group_create_get_list() -> None:
    s, m = _group_store()
    client = _client(s)
    r = client.post(
        "/scim/v2/Groups",
        json={"displayName": "Eng", "members": [{"value": m.id}]},
        headers=_auth("tok1"),
    )
    assert r.status_code == 201
    body = r.json()
    gid = body["id"]
    assert body["displayName"] == "Eng"
    assert s.get_membership(m.id).roles == ["engineer"]  # recompute on create
    assert client.get(f"/scim/v2/Groups/{gid}", headers=_auth("tok1")).status_code == 200
    lr = client.get('/scim/v2/Groups?filter=displayName eq "Eng"', headers=_auth("tok1"))
    assert lr.json()["totalResults"] == 1
    leftover = client.get("/scim/v2/Groups?filter=zzz", headers=_auth("tok1"))
    assert leftover.status_code == 400
    assert leftover.json().get("scimType") == "invalidFilter"


def test_group_create_captures_and_echoes_external_id() -> None:
    # #1342 gap 2: the Entra group objectId GUID is captured + echoed so the IdP reconciles.
    s, m = _group_store()
    client = _client(s)
    r = client.post(
        "/scim/v2/Groups",
        json={"displayName": "Eng", "externalId": "guid-1234"},
        headers=_auth("tok1"),
    )
    assert r.status_code == 201
    body = r.json()
    assert body["externalId"] == "guid-1234"
    got = client.get(f"/scim/v2/Groups/{body['id']}", headers=_auth("tok1")).json()
    assert got["externalId"] == "guid-1234"


def test_group_patch_add_remove_member_recomputes() -> None:
    s, m = _group_store()
    client = _client(s)
    gid = client.post("/scim/v2/Groups", json={"displayName": "Eng"}, headers=_auth("tok1")).json()[
        "id"
    ]
    client.patch(
        f"/scim/v2/Groups/{gid}",
        json={"Operations": [{"op": "add", "path": "members", "value": [{"value": m.id}]}]},
        headers=_auth("tok1"),
    )
    assert s.get_membership(m.id).roles == ["engineer"]
    client.patch(
        f"/scim/v2/Groups/{gid}",
        json={"Operations": [{"op": "remove", "path": f'members[value eq "{m.id}"]'}]},
        headers=_auth("tok1"),
    )
    assert s.get_membership(m.id).roles == []


def test_group_delete_recomputes_and_404() -> None:
    s, m = _group_store()
    client = _client(s)
    gid = client.post(
        "/scim/v2/Groups",
        json={"displayName": "Eng", "members": [{"value": m.id}]},
        headers=_auth("tok1"),
    ).json()["id"]
    assert s.get_membership(m.id).roles == ["engineer"]
    assert client.delete(f"/scim/v2/Groups/{gid}", headers=_auth("tok1")).status_code == 204
    assert s.get_membership(m.id).roles == []
    assert client.get(f"/scim/v2/Groups/{gid}", headers=_auth("tok1")).status_code == 404


def test_group_cross_org_member_400() -> None:
    s, _ = _group_store()
    other_m = s.create_membership(tenant_id="org-2", identity_id="id-2", roles=[])
    r = _client(s).post(
        "/scim/v2/Groups",
        json={"displayName": "Eng", "members": [{"value": other_m.id}]},
        headers=_auth("tok1"),
    )
    assert r.status_code == 400


def test_group_duplicate_name_409() -> None:
    s, _ = _group_store()
    client = _client(s)
    client.post("/scim/v2/Groups", json={"displayName": "Eng"}, headers=_auth("tok1"))
    r = client.post("/scim/v2/Groups", json={"displayName": "Eng"}, headers=_auth("tok1"))
    assert r.status_code == 409


def test_groups_require_bearer() -> None:
    s, _ = _group_store()
    assert _client(s).get("/scim/v2/Groups").status_code == 401


def test_group_patch_remove_foreign_member_cannot_zero_roles() -> None:
    # SECURITY (review #1342): a PATCH `remove` op carries an attacker-chosen
    # membership id in the path filter. recompute must refuse to touch a
    # membership outside the connection's org, so a bearer for org-1 cannot
    # zero an org-2 member's roles. Without the org-containment chokepoint in
    # recompute_membership_roles this drops the victim's roles to [].
    s = _Store(
        [
            _conn("c1", "org-1", "tok1", group_mapping={"Eng": "engineer"}),
            _conn("c2", "org-2", "tok2", group_mapping={"Eng": "engineer"}),
        ]
    )
    victim = s.create_membership(tenant_id="org-2", identity_id="id-victim", roles=["admin"])
    client = _client(s)
    gid = client.post("/scim/v2/Groups", json={"displayName": "Eng"}, headers=_auth("tok1")).json()[
        "id"
    ]
    r = client.patch(
        f"/scim/v2/Groups/{gid}",
        json={"Operations": [{"op": "remove", "path": f'members[value eq "{victim.id}"]'}]},
        headers=_auth("tok1"),
    )
    assert r.status_code == 200
    assert s.get_membership(victim.id).roles == ["admin"]  # untouched


def test_group_put_requires_displayname_400() -> None:
    s, m = _group_store()
    gid = (
        _client(s)
        .post("/scim/v2/Groups", json={"displayName": "Eng"}, headers=_auth("tok1"))
        .json()["id"]
    )
    r = _client(s).put(f"/scim/v2/Groups/{gid}", json={"members": []}, headers=_auth("tok1"))
    assert r.status_code == 400


def test_group_put_replaces_members() -> None:
    s, m = _group_store()
    client = _client(s)
    gid = client.post("/scim/v2/Groups", json={"displayName": "Eng"}, headers=_auth("tok1")).json()[
        "id"
    ]
    r = client.put(
        f"/scim/v2/Groups/{gid}",
        json={"displayName": "Eng", "members": [{"value": m.id}]},
        headers=_auth("tok1"),
    )
    assert r.status_code == 200
    assert s.get_membership(m.id).roles == ["engineer"]


def test_group_routes_malformed_json_is_400() -> None:
    s, _ = _group_store()
    client = _client(s)
    r = client.post(
        "/scim/v2/Groups",
        content="not json",
        headers={**_auth("tok1"), "Content-Type": "application/json"},
    )
    assert r.status_code == 400


def test_resource_types_requires_bearer() -> None:
    s, _ = _group_store()
    assert _client(s).get("/scim/v2/ResourceTypes").status_code == 401
    assert _client(s).get("/scim/v2/Schemas").status_code == 401


def test_resource_types_list_and_single() -> None:
    s, _ = _group_store()
    client = _client(s)
    lr = client.get("/scim/v2/ResourceTypes", headers=_auth("tok1"))
    assert lr.status_code == 200
    body = lr.json()
    assert body["totalResults"] == 2
    ids = {r["id"] for r in body["Resources"]}
    assert ids == {"User", "Group"}
    one = client.get("/scim/v2/ResourceTypes/Group", headers=_auth("tok1"))
    assert one.status_code == 200
    assert one.json()["endpoint"] == "/Groups"
    assert client.get("/scim/v2/ResourceTypes/Nope", headers=_auth("tok1")).status_code == 404


def test_schemas_list_and_single() -> None:
    s, _ = _group_store()
    client = _client(s)
    lr = client.get("/scim/v2/Schemas", headers=_auth("tok1"))
    assert lr.status_code == 200
    ids = {r["id"] for r in lr.json()["Resources"]}
    assert ids == {
        "urn:ietf:params:scim:schemas:core:2.0:User",
        "urn:ietf:params:scim:schemas:core:2.0:Group",
    }
    one = client.get(
        "/scim/v2/Schemas/urn:ietf:params:scim:schemas:core:2.0:User", headers=_auth("tok1")
    )
    assert one.status_code == 200
    assert {a["name"] for a in one.json()["attributes"]} == {
        "userName",
        "active",
        "emails",
        "groups",
    }
    assert client.get("/scim/v2/Schemas/urn:bogus", headers=_auth("tok1")).status_code == 404


def test_user_get_echoes_group_memberships() -> None:
    # #1342: GET /Users/{id} reflects the membership's actual persisted group
    # memberships as a read-only `groups` array (RFC: server-managed).
    s, m = _group_store()
    g = s.create_scim_group("c1", "Eng")
    s.add_group_member(g.id, m.id)
    r = _client(s).get(f"/scim/v2/Users/{m.id}", headers=_auth("tok1"))
    assert r.status_code == 200
    groups = r.json().get("groups", [])
    assert any(grp.get("value") == "Eng" or grp.get("display") == "Eng" for grp in groups)


# ---- mounting (DD-013 plan EA-3) ----


@pytest.mark.parametrize(
    ("protocols", "status"), [(["scim"], 401), ([], 404)], ids=["declared", "undeclared"]
)
def test_scim_routes_mount_only_when_declared(protocols: list[str], status: int) -> None:
    # Declared: the route exists and refuses a bearer-less call. Undeclared: no route.
    app = FastAPI()
    AuthSubsystem()._mount_enterprise(SimpleNamespace(app=app, auth_store=None), protocols)
    assert TestClient(app).get("/scim/v2/ServiceProviderConfig").status_code == status


# ---- real Postgres (DD-013 plan EA-3) ----

_ENTERPRISE_TABLES = (*AUTH_TABLES, "connections", "connection_secret_events")


@pytest.fixture
def pg_store(monkeypatch) -> AuthStore:
    monkeypatch.setenv("DAZZLE_CONNECTION_SECRET", base64.b64encode(b"k" * 32).decode())
    s = AuthStore(database_url=fresh_url(*_ENTERPRISE_TABLES))
    s._init_db()
    return s


def _pg_scim_connection(store: AuthStore, tenant_id: str, bearer: str) -> ConnectionRecord:
    conn = store.create_connection(
        tenant_id=tenant_id,
        type="scim",
        config={},
        secrets={"scim_bearer": bearer},
        domains=["acme.test"],
    )
    store.set_connection_verified_domains(conn.id, ["acme.test"])
    return conn


@pytest.mark.e2e
@pytest.mark.postgres
@pytest.mark.parametrize(
    ("grace", "revoke", "bearer", "expected"),
    [
        (timedelta(hours=1), False, "new-bearer", 200),
        (timedelta(hours=1), False, "old-bearer", 200),
        (timedelta(hours=1), True, "old-bearer", 401),
        (None, False, "old-bearer", 401),
    ],
    ids=["grace-new", "grace-old", "revoked-old", "hard-swap-old"],
)
def test_pg_routes_honour_rotation_grace_window(
    pg_store: AuthStore, grace: timedelta | None, revoke: bool, bearer: str, expected: int
) -> None:
    # A `rotate-secret --grace` overlap keeps the IdP provisioning on the old bearer until
    # the window closes or the operator revokes it; a hard swap cuts it at once.
    conn = _pg_scim_connection(pg_store, "org-1", "old-bearer")
    pg_store.rotate_connection_secret(
        conn.id, {"scim_bearer": "new-bearer"}, grace=grace, actor="test"
    )
    if revoke:
        pg_store.revoke_previous_connection_secret(conn.id, actor="test")
    assert _client(pg_store).get("/scim/v2/Users", headers=_auth(bearer)).status_code == expected


@pytest.mark.e2e
@pytest.mark.postgres
def test_pg_deactivate_kills_only_that_orgs_sessions(pg_store: AuthStore) -> None:
    _pg_scim_connection(pg_store, "org-1", "tok1")
    c = _client(pg_store)
    mid = c.post(
        "/scim/v2/Users", json={"userName": "jane@acme.test"}, headers=_auth("tok1")
    ).json()["id"]
    user = pg_store.get_user_by_email("jane@acme.test")
    other = pg_store.create_membership(tenant_id="org-2", identity_id=str(user.id))
    org1_session = pg_store.create_session(user, active_membership_id=mid)
    org2_session = pg_store.create_session(user, active_membership_id=other.id)

    r = c.patch(
        f"/scim/v2/Users/{mid}",
        json={"Operations": [{"op": "replace", "path": "active", "value": False}]},
        headers=_auth("tok1"),
    )

    assert r.status_code == 200 and r.json()["active"] is False
    assert pg_store.get_session(org1_session.id) is None
    assert pg_store.get_session(org2_session.id) is not None
    assert pg_store.get_membership(other.id).status == "active"


@pytest.mark.e2e
@pytest.mark.postgres
def test_pg_repush_under_changed_email_updates_not_forks(pg_store: AuthStore) -> None:
    _pg_scim_connection(pg_store, "org-1", "tok1")
    c = _client(pg_store)
    first = c.post(
        "/scim/v2/Users",
        json={"userName": "old@acme.test", "externalId": "entra-guid-1"},
        headers=_auth("tok1"),
    ).json()
    second = c.post(
        "/scim/v2/Users",
        json={"userName": "new@acme.test", "externalId": "entra-guid-1"},
        headers=_auth("tok1"),
    )

    assert second.status_code == 201 and second.json()["id"] == first["id"]
    assert len(pg_store.get_memberships_for_tenant("org-1")) == 1
    assert pg_store.get_user_by_email("new@acme.test") is None  # global email not rewritten
