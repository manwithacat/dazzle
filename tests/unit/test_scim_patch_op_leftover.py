"""SCIM leftover PATCH op must not invent a 200 no-op (cycle 2246).

leftover-honest SCIM Operations already exist (oral #103). PATCH
``/scim/v2/Users/{id}`` still skipped leftover ``op: "zzz"`` /
``ghost`` / int / missing and invented a 200 no-op (current
resource). The same leftover on Groups PATCH invented the same
theater (``parse_group_patch`` unknown-op skip). Valid
``add`` / ``remove`` / ``replace`` ride (RFC 7644 §3.5.2
case-insensitive); leftover stays put (400 invalidSyntax, no
write). Absent / empty Operations still no-op (first-visit).
Live SCIM Users + Groups. Oral #116 — not leftover Operations
(oral #103) / not leftover User.groups (oral #115).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from dazzle.http.runtime.auth.scim_routes import (
    leftover_honest_scim_patch_op,
    leftover_scim_patch_op_stay_put,
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
        ("add", "add"),
        ("remove", "remove"),
        ("replace", "replace"),
        ("Add", "add"),
        ("REPLACE", "replace"),
        ("  remove  ", "remove"),
        ("zzz", None),
        ("ghost", None),
        ("purge", None),
        ("", None),
        ("   ", None),
        (None, None),
        (1, None),
        (True, None),
        (["replace"], None),
        ({"op": "replace"}, None),
    ],
    ids=[
        "add-rides",
        "remove-rides",
        "replace-rides",
        "add-casefold",
        "replace-casefold",
        "strip",
        "leftover-zzz",
        "leftover-ghost",
        "leftover-purge",
        "leftover-blank",
        "leftover-ws",
        "leftover-none",
        "leftover-int",
        "leftover-true",
        "leftover-list",
        "leftover-dict",
    ],
)
def test_leftover_honest_scim_patch_op_does_not_invent(raw: object, expected: str | None) -> None:
    assert leftover_honest_scim_patch_op(raw) == expected


def test_leftover_patch_op_stay_put_detects_noop() -> None:
    assert leftover_scim_patch_op_stay_put(
        {"Operations": [{"op": "zzz", "path": "active", "value": False}]}
    )
    assert leftover_scim_patch_op_stay_put(
        {"Operations": [{"op": "ghost", "path": "members", "value": []}]}
    )
    assert leftover_scim_patch_op_stay_put(
        {"Operations": [{"op": 1, "path": "active", "value": False}]}
    )
    assert leftover_scim_patch_op_stay_put({"Operations": [{"path": "active", "value": False}]})
    assert leftover_scim_patch_op_stay_put(
        {"Operations": [{"op": "replace", "path": "active", "value": False}, {"op": "zzz"}]}
    )
    assert not leftover_scim_patch_op_stay_put({})
    assert not leftover_scim_patch_op_stay_put({"Operations": []})
    assert not leftover_scim_patch_op_stay_put(
        {"Operations": [{"op": "replace", "path": "active", "value": False}]}
    )
    assert not leftover_scim_patch_op_stay_put(
        {"Operations": [{"op": "Add", "path": "members", "value": []}]}
    )


def test_leftover_patch_user_op_zzz_does_not_invent_noop() -> None:
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
        json={"Operations": [{"op": "zzz", "path": "active", "value": False}]},
        headers=_auth("tok1"),
    )
    assert resp.status_code == 400
    body = resp.json()
    assert body.get("scimType") == "invalidSyntax"
    assert body.get("detail") == "invalid op"
    assert store.get_membership(mid).status == "active"


def test_leftover_patch_user_op_int_does_not_invent_noop() -> None:
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
        json={"Operations": [{"op": 1, "path": "active", "value": False}]},
        headers=_auth("tok1"),
    )
    assert resp.status_code == 400
    assert resp.json().get("scimType") == "invalidSyntax"
    assert store.get_membership(mid).status == "active"


def test_leftover_patch_user_missing_op_does_not_invent_noop() -> None:
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
        json={"Operations": [{"path": "active", "value": False}]},
        headers=_auth("tok1"),
    )
    assert resp.status_code == 400
    assert resp.json().get("scimType") == "invalidSyntax"
    assert store.get_membership(mid).status == "active"


def test_valid_patch_user_replace_op_rides() -> None:
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
        json={"Operations": [{"op": "Replace", "path": "active", "value": False}]},
        headers=_auth("tok1"),
    )
    assert resp.status_code == 200
    assert resp.json()["active"] is False
    assert store.get_membership(mid).status == "suspended"


def test_leftover_patch_group_op_zzz_does_not_invent_noop() -> None:
    from tests.integration.test_scim_routes import _auth, _client, _group_store

    store, member = _group_store()
    client = _client(store)
    gid = client.post(
        "/scim/v2/Groups",
        json={"displayName": "Eng", "members": [{"value": member.id}]},
        headers=_auth("tok1"),
    ).json()["id"]
    resp = client.patch(
        f"/scim/v2/Groups/{gid}",
        json={"Operations": [{"op": "zzz", "path": "members", "value": []}]},
        headers=_auth("tok1"),
    )
    assert resp.status_code == 400
    assert resp.json().get("scimType") == "invalidSyntax"
    assert resp.json().get("detail") == "invalid op"
    assert store.get_group_member_ids(gid) == [member.id]


def test_valid_patch_group_remove_op_rides() -> None:
    from tests.integration.test_scim_routes import _auth, _client, _group_store

    store, member = _group_store()
    client = _client(store)
    gid = client.post(
        "/scim/v2/Groups",
        json={"displayName": "Eng", "members": [{"value": member.id}]},
        headers=_auth("tok1"),
    ).json()["id"]
    resp = client.patch(
        f"/scim/v2/Groups/{gid}",
        json={"Operations": [{"op": "remove", "path": f'members[value eq "{member.id}"]'}]},
        headers=_auth("tok1"),
    )
    assert resp.status_code == 200
    assert store.get_group_member_ids(gid) == []


def test_helper_source_pins_scim_patch_op_leftover() -> None:
    routes = _ROUTES.read_text()
    assert "def leftover_honest_scim_patch_op" in routes
    assert "def leftover_scim_patch_op_stay_put" in routes
    assert 'return _error(400, "invalid op", scim_type="invalidSyntax")' in routes
    assert "JSONResponse" in routes
    assert "Response(\n            status_code=400,\n            content=" not in routes


def test_live_simple_task_declares_auth() -> None:
    src = _LIVE.read_text()
    assert "[auth]" in src
