"""SCIM leftover schemas must not invent a provision (cycle 2244).

leftover-honest SCIM Operations already exist (oral #103). POST/PUT
``/scim/v2/Users`` and ``/scim/v2/Groups`` still ignored leftover
``schemas: "zzz"`` / ``ghost`` / ``["zzz"]`` / dict / int and invented
a provision. Leftover PATCH invented a 200 no-op or a write. Valid
lists that include the resource / PatchOp URN ride; leftover stays
put (400 invalidSyntax, no write). Absent / empty still omit
(first-visit). Live SCIM Users + Groups. Oral #114 — not leftover
Operations (oral #103) / not leftover externalId (oral #111).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from dazzle.http.runtime.auth.scim_routes import (
    leftover_honest_scim_body_schemas,
    leftover_honest_scim_schemas,
)

_ROUTES = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "dazzle"
    / "http"
    / "runtime"
    / "auth"
    / "scim_routes.py"
)
_LIVE = Path(__file__).resolve().parents[2] / "examples" / "simple_task" / "dazzle.toml"

_USER = "urn:ietf:params:scim:schemas:core:2.0:User"
_GROUP = "urn:ietf:params:scim:schemas:core:2.0:Group"
_PATCH = "urn:ietf:params:scim:api:messages:2.0:PatchOp"


@pytest.mark.parametrize(
    ("raw", "required", "expected"),
    [
        ([_USER], _USER, [_USER]),
        ([_USER, _PATCH], _USER, [_USER, _PATCH]),
        ([_GROUP], _GROUP, [_GROUP]),
        ([_PATCH], _PATCH, [_PATCH]),
        (None, _USER, []),
        ([], _USER, []),
        ("", _USER, None),
        ("zzz", _USER, None),
        ("ghost", _USER, None),
        (["zzz"], _USER, None),
        (["ghost"], _USER, None),
        ([_GROUP], _USER, None),
        ([_USER], _GROUP, None),
        (["  zzz  "], _USER, None),
        ({"value": _USER}, _USER, None),
        (1, _USER, None),
        (True, _USER, None),
        ([1], _USER, None),
        ([True], _USER, None),
        ([{_USER: True}], _USER, None),
    ],
    ids=[
        "user-rides",
        "user-plus-patch-rides",
        "group-rides",
        "patch-rides",
        "none-absent",
        "empty-list-omit",
        "leftover-blank-str",
        "leftover-zzz",
        "leftover-ghost",
        "leftover-list-zzz",
        "leftover-list-ghost",
        "leftover-wrong-resource",
        "leftover-user-on-group",
        "leftover-stripped-zzz",
        "leftover-dict",
        "leftover-int",
        "leftover-true",
        "leftover-list-int",
        "leftover-list-true",
        "leftover-list-dict",
    ],
)
def test_leftover_honest_scim_schemas_does_not_invent(
    raw: object, required: str, expected: list[str] | None
) -> None:
    assert leftover_honest_scim_schemas(raw, required=required) == expected


@pytest.mark.parametrize(
    ("body", "required", "expected"),
    [
        ({}, _USER, []),
        ({"schemas": [_USER]}, _USER, [_USER]),
        ({"schemas": [_PATCH]}, _PATCH, [_PATCH]),
        ({"schemas": ""}, _USER, None),
        ({"schemas": "zzz"}, _USER, None),
        ({"schemas": ["zzz"]}, _USER, None),
        ({"schemas": [_GROUP]}, _USER, None),
        ({"schemas": 1}, _USER, None),
        ({"schemas": True}, _USER, None),
    ],
    ids=[
        "absent-omit",
        "user-rides",
        "patch-rides",
        "leftover-blank-str",
        "leftover-zzz",
        "leftover-list-zzz",
        "leftover-wrong-resource",
        "leftover-int",
        "leftover-true",
    ],
)
def test_leftover_honest_scim_body_schemas_does_not_invent(
    body: dict[str, object], required: str, expected: list[str] | None
) -> None:
    assert leftover_honest_scim_body_schemas(body, required=required) == expected


def test_leftover_create_user_schemas_str_does_not_invent_provision() -> None:
    from tests.integration.test_scim_routes import _auth, _client, _conn, _Store

    store = _Store([_conn("c1", "org-1", "tok1")])
    client = _client(store)
    resp = client.post(
        "/scim/v2/Users",
        json={"schemas": "zzz", "userName": "jane@acme.test"},
        headers=_auth("tok1"),
    )
    assert resp.status_code == 400
    body = resp.json()
    assert body.get("scimType") == "invalidSyntax"
    assert body.get("detail") == "invalid schemas"
    assert store._memberships == []


def test_leftover_create_user_schemas_ghost_does_not_invent_provision() -> None:
    from tests.integration.test_scim_routes import _auth, _client, _conn, _Store

    store = _Store([_conn("c1", "org-1", "tok1")])
    client = _client(store)
    resp = client.post(
        "/scim/v2/Users",
        json={"schemas": ["zzz"], "userName": "jane@acme.test"},
        headers=_auth("tok1"),
    )
    assert resp.status_code == 400
    assert resp.json().get("scimType") == "invalidSyntax"
    assert store._memberships == []


def test_leftover_create_user_schemas_dict_does_not_invent_provision() -> None:
    from tests.integration.test_scim_routes import _auth, _client, _conn, _Store

    store = _Store([_conn("c1", "org-1", "tok1")])
    client = _client(store)
    resp = client.post(
        "/scim/v2/Users",
        json={"schemas": {"value": _USER}, "userName": "jane@acme.test"},
        headers=_auth("tok1"),
    )
    assert resp.status_code == 400
    assert resp.json().get("scimType") == "invalidSyntax"
    assert store._memberships == []


def test_valid_create_user_schemas_rides() -> None:
    from tests.integration.test_scim_routes import _auth, _client, _conn, _Store

    store = _Store([_conn("c1", "org-1", "tok1")])
    client = _client(store)
    resp = client.post(
        "/scim/v2/Users",
        json={"schemas": [_USER], "userName": "jane@acme.test"},
        headers=_auth("tok1"),
    )
    assert resp.status_code == 201
    assert resp.json()["schemas"] == [_USER]
    assert store._memberships[0].id


def test_absent_create_user_schemas_still_omits() -> None:
    from tests.integration.test_scim_routes import _auth, _client, _conn, _Store

    store = _Store([_conn("c1", "org-1", "tok1")])
    client = _client(store)
    resp = client.post(
        "/scim/v2/Users",
        json={"userName": "jane@acme.test"},
        headers=_auth("tok1"),
    )
    assert resp.status_code == 201
    assert store._memberships[0].id


def test_leftover_create_group_schemas_does_not_invent_group() -> None:
    from tests.integration.test_scim_routes import _auth, _client, _group_store

    store, _m = _group_store()
    client = _client(store)
    resp = client.post(
        "/scim/v2/Groups",
        json={"schemas": "zzz", "displayName": "Eng"},
        headers=_auth("tok1"),
    )
    assert resp.status_code == 400
    body = resp.json()
    assert body.get("scimType") == "invalidSyntax"
    assert body.get("detail") == "invalid schemas"
    assert store.list_scim_groups("c1") == []


def test_valid_create_group_schemas_rides() -> None:
    from tests.integration.test_scim_routes import _auth, _client, _group_store

    store, _m = _group_store()
    client = _client(store)
    resp = client.post(
        "/scim/v2/Groups",
        json={"schemas": [_GROUP], "displayName": "Eng"},
        headers=_auth("tok1"),
    )
    assert resp.status_code == 201
    assert resp.json()["schemas"] == [_GROUP]
    assert len(store.list_scim_groups("c1")) == 1


def test_leftover_put_group_schemas_does_not_invent_persist() -> None:
    from tests.integration.test_scim_routes import _auth, _client, _group_store

    store, m = _group_store()
    client = _client(store)
    gid = client.post(
        "/scim/v2/Groups",
        json={"displayName": "Eng", "members": [{"value": m.id}]},
        headers=_auth("tok1"),
    ).json()["id"]
    resp = client.put(
        f"/scim/v2/Groups/{gid}",
        json={
            "schemas": ["zzz"],
            "displayName": "Renamed",
            "members": [{"value": m.id}],
        },
        headers=_auth("tok1"),
    )
    assert resp.status_code == 400
    assert resp.json().get("scimType") == "invalidSyntax"
    group = store.get_scim_group(gid, "c1")
    assert group is not None
    assert group.display_name == "Eng"
    assert store.get_group_member_ids(gid) == [m.id]


def test_valid_put_group_schemas_rides() -> None:
    from tests.integration.test_scim_routes import _auth, _client, _group_store

    store, m = _group_store()
    client = _client(store)
    gid = client.post(
        "/scim/v2/Groups",
        json={"displayName": "Eng", "members": [{"value": m.id}]},
        headers=_auth("tok1"),
    ).json()["id"]
    resp = client.put(
        f"/scim/v2/Groups/{gid}",
        json={
            "schemas": [_GROUP],
            "displayName": "Renamed",
            "members": [{"value": m.id}],
        },
        headers=_auth("tok1"),
    )
    assert resp.status_code == 200
    assert store.get_scim_group(gid, "c1").display_name == "Renamed"


def test_leftover_patch_user_schemas_does_not_invent_noop() -> None:
    from tests.integration.test_scim_routes import _auth, _client, _conn, _Store

    store = _Store([_conn("c1", "org-1", "tok1")])
    client = _client(store)
    mid = client.post(
        "/scim/v2/Users",
        json={"userName": "jane@acme.test"},
        headers=_auth("tok1"),
    ).json()["id"]
    resp = client.patch(
        f"/scim/v2/Users/{mid}",
        json={
            "schemas": "zzz",
            "Operations": [{"op": "replace", "path": "active", "value": False}],
        },
        headers=_auth("tok1"),
    )
    assert resp.status_code == 400
    assert resp.json().get("scimType") == "invalidSyntax"
    assert resp.json().get("detail") == "invalid schemas"
    assert store.get_membership(mid).status == "active"


def test_leftover_patch_group_schemas_does_not_invent_noop() -> None:
    from tests.integration.test_scim_routes import _auth, _client, _group_store

    store, m = _group_store()
    client = _client(store)
    gid = client.post(
        "/scim/v2/Groups",
        json={"displayName": "Eng", "members": [{"value": m.id}]},
        headers=_auth("tok1"),
    ).json()["id"]
    resp = client.patch(
        f"/scim/v2/Groups/{gid}",
        json={
            "schemas": ["ghost"],
            "Operations": [{"op": "replace", "path": "displayName", "value": "X"}],
        },
        headers=_auth("tok1"),
    )
    assert resp.status_code == 400
    assert resp.json().get("scimType") == "invalidSyntax"
    assert store.get_scim_group(gid, "c1").display_name == "Eng"
    assert store.get_group_member_ids(gid) == [m.id]


def test_valid_patch_user_schemas_rides() -> None:
    from tests.integration.test_scim_routes import _auth, _client, _conn, _Store

    store = _Store([_conn("c1", "org-1", "tok1")])
    client = _client(store)
    mid = client.post(
        "/scim/v2/Users",
        json={"userName": "jane@acme.test"},
        headers=_auth("tok1"),
    ).json()["id"]
    resp = client.patch(
        f"/scim/v2/Users/{mid}",
        json={
            "schemas": [_PATCH],
            "Operations": [{"op": "replace", "path": "active", "value": False}],
        },
        headers=_auth("tok1"),
    )
    assert resp.status_code == 200
    assert store.get_membership(mid).status != "active"


def test_helper_source_pins_scim_schemas_leftover() -> None:
    routes = _ROUTES.read_text()
    assert "def leftover_honest_scim_schemas" in routes
    assert "def leftover_honest_scim_body_schemas" in routes
    assert "_SCIM_SCHEMA_URN" in routes
    assert "leftover_honest_scim_body_schemas" in routes
    assert 'return _error(400, "invalid schemas", scim_type="invalidSyntax")' in routes
    assert "JSONResponse" in routes
    assert "Response(\n            status_code=400,\n            content=" not in routes


def test_live_simple_task_declares_auth() -> None:
    src = _LIVE.read_text()
    assert "[auth]" in src
