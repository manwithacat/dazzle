"""SCIM leftover displayName must not invent a group / str() rename (cycle 2232).

leftover-honest SCIM Operations already exists (oral #103). POST/PUT
``/scim/v2/Groups`` still missed leftover ``displayName: ["zzz"]`` /
dict / int / True and invented a group persist. Leftover PATCH
``value`` invented a rename via ``str()`` (``None`` → ``"None"``).
Valid non-empty strings ride (``zzz`` is a legal name); leftover
stays put (400 invalidValue, no write). Absent / blank still 400
required. Live SCIM Groups. Oral #104 — not leftover SCIM
Operations (oral #103) / not leftover ``members`` (oral #101).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from dazzle.http.runtime.auth.scim_provisioning import (
    leftover_honest_scim_body_display_name,
    leftover_honest_scim_display_name,
    leftover_scim_display_name_stay_put,
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
        ("Eng", "Eng"),
        ("  Platform  ", "Platform"),
        ("zzz", "zzz"),
        ("ghost", "ghost"),
        ("", ""),
        ("   ", ""),
        (None, ""),
        (["zzz"], None),
        ({"value": "Eng"}, None),
        (1, None),
        (True, None),
        (["Eng"], None),
    ],
    ids=[
        "valid",
        "strip",
        "zzz-is-a-name",
        "ghost-is-a-name",
        "blank",
        "whitespace",
        "none-absent",
        "leftover-list-zzz",
        "leftover-dict",
        "leftover-int",
        "leftover-true",
        "leftover-list-eng",
    ],
)
def test_leftover_honest_scim_display_name_does_not_invent(
    raw: object, expected: str | None
) -> None:
    assert leftover_honest_scim_display_name(raw) == expected


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        ({}, ""),
        ({"displayName": "Eng"}, "Eng"),
        ({"displayName": "zzz"}, "zzz"),
        ({"displayName": ""}, ""),
        ({"displayName": ["zzz"]}, None),
        ({"displayName": {"value": "Eng"}}, None),
        ({"displayName": 1}, None),
        ({"displayName": True}, None),
    ],
    ids=[
        "absent-default",
        "valid",
        "zzz-is-a-name",
        "blank",
        "leftover-list",
        "leftover-dict",
        "leftover-int",
        "leftover-true",
    ],
)
def test_leftover_honest_scim_body_display_name_does_not_invent(
    body: dict[str, object], expected: str | None
) -> None:
    assert leftover_honest_scim_body_display_name(body) == expected


def test_leftover_display_name_stay_put_detects_junk() -> None:
    assert leftover_scim_display_name_stay_put(
        {"Operations": [{"op": "replace", "path": "displayName", "value": ["zzz"]}]}
    )
    assert leftover_scim_display_name_stay_put(
        {"Operations": [{"op": "replace", "path": "displayName", "value": {"v": 1}}]}
    )
    assert leftover_scim_display_name_stay_put(
        {"Operations": [{"op": "replace", "path": "displayName", "value": 1}]}
    )
    assert leftover_scim_display_name_stay_put(
        {"Operations": [{"op": "replace", "path": "displayName", "value": None}]}
    )
    assert leftover_scim_display_name_stay_put(
        {"Operations": [{"op": "replace", "value": {"displayName": ["zzz"]}}]}
    )
    assert not leftover_scim_display_name_stay_put({})
    assert not leftover_scim_display_name_stay_put({"Operations": []})
    assert not leftover_scim_display_name_stay_put(
        {"Operations": [{"op": "replace", "path": "displayName", "value": "Platform"}]}
    )


def test_leftover_create_displayname_list_does_not_invent_group() -> None:
    from tests.integration.test_scim_routes import _auth, _client, _group_store

    store, _m = _group_store()
    client = _client(store)
    resp = client.post(
        "/scim/v2/Groups",
        json={"displayName": ["zzz"]},
        headers=_auth("tok1"),
    )
    assert resp.status_code == 400
    body = resp.json()
    assert body.get("scimType") == "invalidValue"
    assert body.get("detail") == "invalid displayName"
    assert store.list_scim_groups("c1") == []


def test_leftover_create_displayname_dict_does_not_invent_group() -> None:
    from tests.integration.test_scim_routes import _auth, _client, _group_store

    store, _m = _group_store()
    client = _client(store)
    resp = client.post(
        "/scim/v2/Groups",
        json={"displayName": {"value": "Eng"}},
        headers=_auth("tok1"),
    )
    assert resp.status_code == 400
    assert resp.json().get("scimType") == "invalidValue"
    assert store.list_scim_groups("c1") == []


def test_leftover_create_displayname_int_does_not_invent_group() -> None:
    from tests.integration.test_scim_routes import _auth, _client, _group_store

    store, _m = _group_store()
    client = _client(store)
    resp = client.post(
        "/scim/v2/Groups",
        json={"displayName": 1},
        headers=_auth("tok1"),
    )
    assert resp.status_code == 400
    assert resp.json().get("scimType") == "invalidValue"
    assert store.list_scim_groups("c1") == []


def test_valid_create_displayname_rides() -> None:
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
    groups = store.list_scim_groups("c1")
    assert len(groups) == 1
    assert groups[0].display_name == "Eng"


def test_valid_create_zzz_displayname_rides() -> None:
    from tests.integration.test_scim_routes import _auth, _client, _group_store

    store, _m = _group_store()
    client = _client(store)
    resp = client.post(
        "/scim/v2/Groups",
        json={"displayName": "zzz"},
        headers=_auth("tok1"),
    )
    assert resp.status_code == 201
    assert resp.json()["displayName"] == "zzz"


def test_absent_create_displayname_still_required() -> None:
    from tests.integration.test_scim_routes import _auth, _client, _group_store

    store, _m = _group_store()
    client = _client(store)
    resp = client.post(
        "/scim/v2/Groups",
        json={"members": []},
        headers=_auth("tok1"),
    )
    assert resp.status_code == 400
    assert store.list_scim_groups("c1") == []


def test_leftover_put_displayname_does_not_invent_rename() -> None:
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
        json={"displayName": ["zzz"], "members": [{"value": m.id}]},
        headers=_auth("tok1"),
    )
    assert resp.status_code == 400
    assert resp.json().get("scimType") == "invalidValue"
    group = store.get_scim_group(gid, "c1")
    assert group is not None
    assert group.display_name == "Eng"
    assert store.get_group_member_ids(gid) == [m.id]


def test_valid_put_displayname_rides() -> None:
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
        json={"displayName": "Platform", "members": [{"value": m.id}]},
        headers=_auth("tok1"),
    )
    assert resp.status_code == 200
    assert resp.json()["displayName"] == "Platform"
    assert store.get_scim_group(gid, "c1").display_name == "Platform"


def test_leftover_patch_displayname_list_does_not_invent_rename() -> None:
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
        json={"Operations": [{"op": "replace", "path": "displayName", "value": ["zzz"]}]},
        headers=_auth("tok1"),
    )
    assert resp.status_code == 400
    assert resp.json().get("scimType") == "invalidValue"
    assert resp.json().get("detail") == "invalid displayName"
    group = store.get_scim_group(gid, "c1")
    assert group is not None
    assert group.display_name == "Eng"


def test_leftover_patch_displayname_null_does_not_invent_none_string() -> None:
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
        json={"Operations": [{"op": "replace", "path": "displayName", "value": None}]},
        headers=_auth("tok1"),
    )
    assert resp.status_code == 400
    assert resp.json().get("scimType") == "invalidValue"
    assert store.get_scim_group(gid, "c1").display_name == "Eng"


def test_leftover_patch_displayname_dict_form_does_not_invent_rename() -> None:
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
        json={"Operations": [{"op": "replace", "value": {"displayName": ["zzz"]}}]},
        headers=_auth("tok1"),
    )
    assert resp.status_code == 400
    assert resp.json().get("scimType") == "invalidValue"
    assert store.get_scim_group(gid, "c1").display_name == "Eng"


def test_valid_patch_displayname_rides() -> None:
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
        json={"Operations": [{"op": "replace", "path": "displayName", "value": "Platform"}]},
        headers=_auth("tok1"),
    )
    assert resp.status_code == 200
    assert resp.json()["displayName"] == "Platform"


def test_helper_source_pins_scim_displayname_leftover() -> None:
    src = _PROV.read_text()
    routes = _ROUTES.read_text()
    assert "def leftover_honest_scim_display_name" in src
    assert "def leftover_honest_scim_body_display_name" in src
    assert "def leftover_scim_display_name_stay_put" in src
    assert "leftover_honest_scim_body_display_name" in routes
    assert "leftover_scim_display_name_stay_put" in routes
    assert 'return _error(400, "invalid displayName", scim_type="invalidValue")' in routes
    assert "JSONResponse" in routes


def test_live_simple_task_declares_auth() -> None:
    src = _LIVE.read_text()
    assert "[auth]" in src
