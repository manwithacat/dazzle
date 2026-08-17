"""SCIM leftover members must not invent a wipe / empty group (cycle 2229).

leftover-honest SCIM active already exists (oral #100). PATCH/PUT
``/scim/v2/Groups`` still missed leftover ``members: "zzz"`` /
``ghost`` / ``[{}]`` and invented replace-with-empty (wipe every
member). Leftover create invented an empty group. Valid
``[{"value": "<id>"}]`` ride; leftover stays put (400 invalidValue,
no write). Absent key still creates empty. Live SCIM Groups.
Oral #101 — not leftover SCIM active (oral #100) / not leftover
GET ``?filter=`` (oral #99).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from dazzle.http.runtime.auth.scim_provisioning import (
    leftover_honest_scim_body_members,
    leftover_honest_scim_member_ids,
    leftover_scim_members_stay_put,
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
        ([], []),
        ([{"value": "m1"}], ["m1"]),
        ([{"value": "m1"}, {"value": "m2"}], ["m1", "m2"]),
        ([{"value": "  m1  "}], ["m1"]),
        ("zzz", None),
        ("ghost", None),
        ("x", None),
        ({"value": "m1"}, None),
        (None, None),
        (1, None),
        ([{"display": "Eng"}], None),
        ([{}], None),
        ([{"value": ""}], None),
        ([{"value": "   "}], None),
        ([{"value": None}], None),
        (["m1"], None),
        ([1], None),
    ],
    ids=[
        "empty-list",
        "one-member",
        "two-members",
        "strip",
        "leftover-zzz",
        "leftover-ghost",
        "leftover-x",
        "leftover-dict",
        "leftover-none",
        "leftover-int",
        "leftover-display-only",
        "leftover-empty-dict",
        "leftover-empty-value",
        "leftover-blank-value",
        "leftover-none-value",
        "leftover-string-item",
        "leftover-int-item",
    ],
)
def test_leftover_honest_scim_member_ids_does_not_invent(
    raw: object, expected: list[str] | None
) -> None:
    assert leftover_honest_scim_member_ids(raw) == expected


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        ({}, []),
        ({"members": []}, []),
        ({"members": [{"value": "m1"}]}, ["m1"]),
        ({"members": "zzz"}, None),
        ({"members": "ghost"}, None),
        ({"members": [{}]}, None),
    ],
    ids=[
        "absent-default",
        "empty-list",
        "valid",
        "leftover-zzz",
        "leftover-ghost",
        "leftover-empty-dict",
    ],
)
def test_leftover_honest_scim_body_members_does_not_invent(
    body: dict[str, object], expected: list[str] | None
) -> None:
    assert leftover_honest_scim_body_members(body) == expected


def test_leftover_patch_members_stay_put_detects_wipe() -> None:
    assert leftover_scim_members_stay_put(
        {"Operations": [{"op": "replace", "path": "members", "value": "zzz"}]}
    )
    assert leftover_scim_members_stay_put(
        {"Operations": [{"op": "add", "path": "members", "value": "ghost"}]}
    )
    assert leftover_scim_members_stay_put(
        {"Operations": [{"op": "Replace", "value": {"members": [{}]}}]}
    )
    assert not leftover_scim_members_stay_put(
        {"Operations": [{"op": "replace", "path": "members", "value": [{"value": "m1"}]}]}
    )
    assert not leftover_scim_members_stay_put(
        {"Operations": [{"op": "replace", "path": "members", "value": []}]}
    )
    assert not leftover_scim_members_stay_put({"Operations": [{"op": "remove", "path": "members"}]})


def test_leftover_create_members_does_not_invent_empty_group() -> None:
    from tests.integration.test_scim_routes import _auth, _client, _group_store

    store, _m = _group_store()
    client = _client(store)
    resp = client.post(
        "/scim/v2/Groups",
        json={"displayName": "Eng", "members": "zzz"},
        headers=_auth("tok1"),
    )
    assert resp.status_code == 400
    body = resp.json()
    assert body.get("scimType") == "invalidValue"
    assert body.get("status") == "400"
    assert store.list_scim_groups("c1") == []


def test_leftover_create_members_ghost_does_not_invent_empty_group() -> None:
    from tests.integration.test_scim_routes import _auth, _client, _group_store

    store, _m = _group_store()
    client = _client(store)
    resp = client.post(
        "/scim/v2/Groups",
        json={"displayName": "Eng", "members": "ghost"},
        headers=_auth("tok1"),
    )
    assert resp.status_code == 400
    assert resp.json().get("scimType") == "invalidValue"
    assert store.list_scim_groups("c1") == []


def test_absent_create_members_still_creates_empty() -> None:
    from tests.integration.test_scim_routes import _auth, _client, _group_store

    store, _m = _group_store()
    client = _client(store)
    resp = client.post(
        "/scim/v2/Groups",
        json={"displayName": "Eng"},
        headers=_auth("tok1"),
    )
    assert resp.status_code == 201
    assert resp.json()["displayName"] == "Eng"
    assert resp.json()["members"] == []


def test_valid_create_members_ride() -> None:
    from tests.integration.test_scim_routes import _auth, _client, _group_store

    store, m = _group_store()
    client = _client(store)
    resp = client.post(
        "/scim/v2/Groups",
        json={"displayName": "Eng", "members": [{"value": m.id}]},
        headers=_auth("tok1"),
    )
    assert resp.status_code == 201
    assert store.get_membership(m.id).roles == ["engineer"]


def test_leftover_replace_members_does_not_invent_wipe() -> None:
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
        json={"displayName": "Eng", "members": "zzz"},
        headers=_auth("tok1"),
    )
    assert resp.status_code == 400
    assert resp.json().get("scimType") == "invalidValue"
    assert store.get_group_member_ids(gid) == [m.id]
    assert store.get_membership(m.id).roles == ["engineer"]


def test_leftover_patch_members_does_not_invent_wipe() -> None:
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
        json={"Operations": [{"op": "replace", "path": "members", "value": "zzz"}]},
        headers=_auth("tok1"),
    )
    assert resp.status_code == 400
    assert resp.json().get("scimType") == "invalidValue"
    assert store.get_group_member_ids(gid) == [m.id]
    assert store.get_membership(m.id).roles == ["engineer"]


def test_leftover_patch_entra_members_does_not_invent_wipe() -> None:
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
        json={"Operations": [{"op": "Replace", "value": {"members": "zzz"}}]},
        headers=_auth("tok1"),
    )
    assert resp.status_code == 400
    assert resp.json().get("scimType") == "invalidValue"
    assert store.get_group_member_ids(gid) == [m.id]


def test_valid_patch_replace_members_empty_still_clears() -> None:
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
        json={"Operations": [{"op": "replace", "path": "members", "value": []}]},
        headers=_auth("tok1"),
    )
    assert resp.status_code == 200
    assert store.get_group_member_ids(gid) == []
    assert store.get_membership(m.id).roles == []


def test_helper_source_pins_scim_members_leftover() -> None:
    prov = _PROV.read_text()
    routes = _ROUTES.read_text()
    assert "def leftover_honest_scim_member_ids" in prov
    assert "def leftover_honest_scim_body_members" in prov
    assert "def leftover_scim_members_stay_put" in prov
    assert 'scim_type="invalidValue"' in routes
    assert "JSONResponse" in routes
    assert "leftover_scim_members_stay_put" in routes
    assert "leftover_honest_scim_body_members" in routes


def test_live_simple_task_declares_auth() -> None:
    src = _LIVE.read_text()
    assert "[auth]" in src
