"""SCIM leftover externalId must not invent a 500 / persist (cycle 2241).

leftover-honest SCIM displayName already exists (oral #104). POST/PUT
``/scim/v2/Users`` and ``/scim/v2/Groups`` still missed leftover
``externalId: ["zzz"]`` / dict / int / True and invented a 500 via
``.strip()`` (provision) or persisted leftover as the IdP's stable
id. Leftover PATCH invented a 200 no-op (unknown op skipped). Valid
non-empty strings ride (``zzz`` / Entra GUIDs are legal opaque ids);
leftover stays put (400 invalidValue, no write). Absent / blank
still omit. Live SCIM Users + Groups. Oral #111 — not leftover
displayName (oral #104) / not leftover userName (oral #102).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from dazzle.http.runtime.auth.scim_provisioning import (
    leftover_honest_scim_body_external_id,
    leftover_honest_scim_external_id,
    leftover_scim_external_id_stay_put,
)

_PROV = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "dazzle"
    / "http"
    / "runtime"
    / "auth"
    / "scim_provisioning.py"
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


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("entra-guid-1", "entra-guid-1"),
        ("  guid-1234  ", "guid-1234"),
        ("zzz", "zzz"),
        ("ghost", "ghost"),
        ("", ""),
        ("   ", ""),
        (None, ""),
        (["zzz"], None),
        ({"value": "entra-guid-1"}, None),
        (1, None),
        (True, None),
        (["entra-guid-1"], None),
    ],
    ids=[
        "valid",
        "strip",
        "zzz-is-an-id",
        "ghost-is-an-id",
        "blank",
        "whitespace",
        "none-absent",
        "leftover-list-zzz",
        "leftover-dict",
        "leftover-int",
        "leftover-true",
        "leftover-list-guid",
    ],
)
def test_leftover_honest_scim_external_id_does_not_invent(
    raw: object, expected: str | None
) -> None:
    assert leftover_honest_scim_external_id(raw) == expected


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        ({}, ""),
        ({"externalId": "entra-guid-1"}, "entra-guid-1"),
        ({"externalId": "zzz"}, "zzz"),
        ({"externalId": ""}, ""),
        ({"externalId": ["zzz"]}, None),
        ({"externalId": {"value": "entra-guid-1"}}, None),
        ({"externalId": 1}, None),
        ({"externalId": True}, None),
    ],
    ids=[
        "absent-omit",
        "valid",
        "zzz-is-an-id",
        "blank",
        "leftover-list",
        "leftover-dict",
        "leftover-int",
        "leftover-true",
    ],
)
def test_leftover_honest_scim_body_external_id_does_not_invent(
    body: dict[str, object], expected: str | None
) -> None:
    assert leftover_honest_scim_body_external_id(body) == expected


def test_leftover_external_id_stay_put_detects_junk() -> None:
    assert leftover_scim_external_id_stay_put(
        {"Operations": [{"op": "replace", "path": "externalId", "value": ["zzz"]}]}
    )
    assert leftover_scim_external_id_stay_put(
        {"Operations": [{"op": "replace", "path": "externalId", "value": {"v": 1}}]}
    )
    assert leftover_scim_external_id_stay_put(
        {"Operations": [{"op": "replace", "path": "externalId", "value": 1}]}
    )
    assert leftover_scim_external_id_stay_put(
        {"Operations": [{"op": "replace", "path": "externalId", "value": None}]}
    )
    assert leftover_scim_external_id_stay_put(
        {"Operations": [{"op": "replace", "value": {"externalId": ["zzz"]}}]}
    )
    assert not leftover_scim_external_id_stay_put({})
    assert not leftover_scim_external_id_stay_put({"Operations": []})
    assert not leftover_scim_external_id_stay_put(
        {"Operations": [{"op": "replace", "path": "externalId", "value": "entra-guid-1"}]}
    )


def test_leftover_create_user_external_id_list_does_not_invent_500() -> None:
    from tests.integration.test_scim_routes import _auth, _client, _conn, _Store

    store = _Store([_conn("c1", "org-1", "tok1")])
    client = _client(store)
    resp = client.post(
        "/scim/v2/Users",
        json={"userName": "jane@acme.test", "externalId": ["zzz"]},
        headers=_auth("tok1"),
    )
    assert resp.status_code == 400
    body = resp.json()
    assert body.get("scimType") == "invalidValue"
    assert body.get("detail") == "invalid externalId"
    assert store._memberships == []


def test_leftover_create_user_external_id_dict_does_not_invent_persist() -> None:
    from tests.integration.test_scim_routes import _auth, _client, _conn, _Store

    store = _Store([_conn("c1", "org-1", "tok1")])
    client = _client(store)
    resp = client.post(
        "/scim/v2/Users",
        json={"userName": "jane@acme.test", "externalId": {"value": "entra-guid-1"}},
        headers=_auth("tok1"),
    )
    assert resp.status_code == 400
    assert resp.json().get("scimType") == "invalidValue"
    assert store._memberships == []


def test_leftover_create_user_external_id_int_does_not_invent_persist() -> None:
    from tests.integration.test_scim_routes import _auth, _client, _conn, _Store

    store = _Store([_conn("c1", "org-1", "tok1")])
    client = _client(store)
    resp = client.post(
        "/scim/v2/Users",
        json={"userName": "jane@acme.test", "externalId": 1},
        headers=_auth("tok1"),
    )
    assert resp.status_code == 400
    assert resp.json().get("scimType") == "invalidValue"
    assert store._memberships == []


def test_valid_create_user_external_id_rides() -> None:
    from tests.integration.test_scim_routes import _auth, _client, _conn, _Store

    store = _Store([_conn("c1", "org-1", "tok1")])
    client = _client(store)
    resp = client.post(
        "/scim/v2/Users",
        json={"userName": "jane@acme.test", "externalId": "entra-guid-1"},
        headers=_auth("tok1"),
    )
    assert resp.status_code == 201
    assert resp.json()["externalId"] == "entra-guid-1"
    assert store._memberships[0].external_id == "entra-guid-1"


def test_valid_create_user_zzz_external_id_rides() -> None:
    from tests.integration.test_scim_routes import _auth, _client, _conn, _Store

    store = _Store([_conn("c1", "org-1", "tok1")])
    client = _client(store)
    resp = client.post(
        "/scim/v2/Users",
        json={"userName": "jane@acme.test", "externalId": "zzz"},
        headers=_auth("tok1"),
    )
    assert resp.status_code == 201
    assert resp.json()["externalId"] == "zzz"


def test_absent_create_user_external_id_still_omits() -> None:
    from tests.integration.test_scim_routes import _auth, _client, _conn, _Store

    store = _Store([_conn("c1", "org-1", "tok1")])
    client = _client(store)
    resp = client.post(
        "/scim/v2/Users",
        json={"userName": "jane@acme.test"},
        headers=_auth("tok1"),
    )
    assert resp.status_code == 201
    assert "externalId" not in resp.json()
    assert store._memberships[0].external_id in (None, "")


def test_leftover_create_group_external_id_does_not_invent_group() -> None:
    from tests.integration.test_scim_routes import _auth, _client, _group_store

    store, _m = _group_store()
    client = _client(store)
    resp = client.post(
        "/scim/v2/Groups",
        json={"displayName": "Eng", "externalId": ["zzz"]},
        headers=_auth("tok1"),
    )
    assert resp.status_code == 400
    body = resp.json()
    assert body.get("scimType") == "invalidValue"
    assert body.get("detail") == "invalid externalId"
    assert store.list_scim_groups("c1") == []


def test_valid_create_group_external_id_rides() -> None:
    from tests.integration.test_scim_routes import _auth, _client, _group_store

    store, _m = _group_store()
    client = _client(store)
    resp = client.post(
        "/scim/v2/Groups",
        json={"displayName": "Eng", "externalId": "guid-1234"},
        headers=_auth("tok1"),
    )
    assert resp.status_code == 201
    assert resp.json()["externalId"] == "guid-1234"
    groups = store.list_scim_groups("c1")
    assert len(groups) == 1
    assert groups[0].external_id == "guid-1234"


def test_leftover_put_group_external_id_does_not_invent_persist() -> None:
    from tests.integration.test_scim_routes import _auth, _client, _group_store

    store, m = _group_store()
    client = _client(store)
    gid = client.post(
        "/scim/v2/Groups",
        json={"displayName": "Eng", "members": [{"value": m.id}], "externalId": "guid-1234"},
        headers=_auth("tok1"),
    ).json()["id"]
    resp = client.put(
        f"/scim/v2/Groups/{gid}",
        json={"displayName": "Eng", "members": [{"value": m.id}], "externalId": ["zzz"]},
        headers=_auth("tok1"),
    )
    assert resp.status_code == 400
    assert resp.json().get("scimType") == "invalidValue"
    group = store.get_scim_group(gid, "c1")
    assert group is not None
    assert group.external_id == "guid-1234"
    assert store.get_group_member_ids(gid) == [m.id]


def test_valid_put_group_external_id_rides() -> None:
    from tests.integration.test_scim_routes import _auth, _client, _group_store

    store, m = _group_store()
    client = _client(store)
    gid = client.post(
        "/scim/v2/Groups",
        json={"displayName": "Eng", "members": [{"value": m.id}], "externalId": "guid-1234"},
        headers=_auth("tok1"),
    ).json()["id"]
    resp = client.put(
        f"/scim/v2/Groups/{gid}",
        json={"displayName": "Eng", "members": [{"value": m.id}], "externalId": "guid-5678"},
        headers=_auth("tok1"),
    )
    assert resp.status_code == 200
    assert resp.json()["externalId"] == "guid-5678"
    assert store.get_scim_group(gid, "c1").external_id == "guid-5678"


def test_leftover_patch_user_external_id_does_not_invent_noop() -> None:
    from tests.integration.test_scim_routes import _auth, _client, _conn, _Store

    store = _Store([_conn("c1", "org-1", "tok1")])
    client = _client(store)
    mid = client.post(
        "/scim/v2/Users",
        json={"userName": "jane@acme.test", "externalId": "entra-guid-1"},
        headers=_auth("tok1"),
    ).json()["id"]
    resp = client.patch(
        f"/scim/v2/Users/{mid}",
        json={"Operations": [{"op": "replace", "path": "externalId", "value": ["zzz"]}]},
        headers=_auth("tok1"),
    )
    assert resp.status_code == 400
    assert resp.json().get("scimType") == "invalidValue"
    assert resp.json().get("detail") == "invalid externalId"
    assert store.get_membership(mid).external_id == "entra-guid-1"


def test_leftover_patch_group_external_id_does_not_invent_noop() -> None:
    from tests.integration.test_scim_routes import _auth, _client, _group_store

    store, m = _group_store()
    client = _client(store)
    gid = client.post(
        "/scim/v2/Groups",
        json={"displayName": "Eng", "members": [{"value": m.id}], "externalId": "guid-1234"},
        headers=_auth("tok1"),
    ).json()["id"]
    resp = client.patch(
        f"/scim/v2/Groups/{gid}",
        json={"Operations": [{"op": "replace", "path": "externalId", "value": ["zzz"]}]},
        headers=_auth("tok1"),
    )
    assert resp.status_code == 400
    assert resp.json().get("scimType") == "invalidValue"
    assert store.get_scim_group(gid, "c1").external_id == "guid-1234"
    assert store.get_scim_group(gid, "c1").display_name == "Eng"


def test_helper_source_pins_scim_external_id_leftover() -> None:
    src = _PROV.read_text()
    routes = _ROUTES.read_text()
    assert "def leftover_honest_scim_external_id" in src
    assert "def leftover_honest_scim_body_external_id" in src
    assert "def leftover_scim_external_id_stay_put" in src
    assert "leftover_honest_scim_body_external_id" in routes
    assert "leftover_scim_external_id_stay_put" in routes
    assert 'return _error(400, "invalid externalId", scim_type="invalidValue")' in routes
    assert "JSONResponse" in routes


def test_live_simple_task_declares_auth() -> None:
    src = _LIVE.read_text()
    assert "[auth]" in src
