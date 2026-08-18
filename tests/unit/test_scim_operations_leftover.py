"""SCIM leftover PATCH Operations must not invent a 500 / 200 no-op (cycle 2231).

leftover-honest SCIM userName already exists (oral #102). PATCH
``/scim/v2/Users/{id}`` still missed leftover ``Operations: "zzz"``
/ ``ghost`` / dict / ``[1]`` and invented a crash (``str.get`` →
500). Groups PATCH invented a 200 no-op (``parse_group_patch``
treated non-list as empty). Valid ``[{"op": "replace", ...}]``
ride; leftover stays put (400 invalidSyntax, no write). Absent /
empty list still no-op. Live SCIM Users + Groups. Oral #103 —
not leftover SCIM userName (oral #102) / not leftover ``members``
(oral #101) / not leftover ``active`` (oral #100).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from dazzle.http.runtime.auth.scim_routes import (
    leftover_honest_scim_body_operations,
    leftover_honest_scim_operations,
    leftover_scim_operations_stay_put,
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
        (
            [{"op": "replace", "path": "active", "value": True}],
            [{"op": "replace", "path": "active", "value": True}],
        ),
        (
            [{"op": "add", "path": "members", "value": []}],
            [{"op": "add", "path": "members", "value": []}],
        ),
        ([{}], [{}]),
        (None, []),
        ("zzz", None),
        ("ghost", None),
        ("x", None),
        ({"op": "replace"}, None),
        (1, None),
        (["zzz"], None),
        ([1], None),
        ([{"op": "replace"}, "zzz"], None),
    ],
    ids=[
        "empty-list",
        "one-replace",
        "one-add",
        "empty-dict-op",
        "none",
        "leftover-zzz",
        "leftover-ghost",
        "leftover-x",
        "leftover-dict",
        "leftover-int",
        "leftover-string-item",
        "leftover-int-item",
        "leftover-mixed-item",
    ],
)
def test_leftover_honest_scim_operations_does_not_invent(
    raw: object, expected: list[dict[str, object]] | None
) -> None:
    assert leftover_honest_scim_operations(raw) == expected


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        ({}, []),
        ({"Operations": []}, []),
        (
            {"Operations": [{"op": "replace", "path": "active", "value": False}]},
            [{"op": "replace", "path": "active", "value": False}],
        ),
        ({"Operations": "zzz"}, None),
        ({"Operations": "ghost"}, None),
        ({"Operations": {"op": "replace"}}, None),
        ({"Operations": [1]}, None),
    ],
    ids=[
        "absent-default",
        "empty-list",
        "valid",
        "leftover-zzz",
        "leftover-ghost",
        "leftover-dict",
        "leftover-int-item",
    ],
)
def test_leftover_honest_scim_body_operations_does_not_invent(
    body: dict[str, object], expected: list[dict[str, object]] | None
) -> None:
    assert leftover_honest_scim_body_operations(body) == expected


def test_leftover_operations_stay_put_detects_junk() -> None:
    assert leftover_scim_operations_stay_put({"Operations": "zzz"})
    assert leftover_scim_operations_stay_put({"Operations": "ghost"})
    assert leftover_scim_operations_stay_put({"Operations": {"op": "replace"}})
    assert leftover_scim_operations_stay_put({"Operations": [1]})
    assert not leftover_scim_operations_stay_put({})
    assert not leftover_scim_operations_stay_put({"Operations": []})
    assert not leftover_scim_operations_stay_put(
        {"Operations": [{"op": "replace", "path": "active", "value": False}]}
    )


def test_leftover_patch_operations_does_not_invent_500() -> None:
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
        json={"Operations": "zzz"},
        headers=_auth("tok1"),
    )
    assert resp.status_code == 400
    body = resp.json()
    assert body.get("scimType") == "invalidSyntax"
    assert body.get("detail") == "invalid Operations"
    assert store._memberships[0].status == "active"
    assert store.revoked == []


def test_leftover_patch_operations_ghost_does_not_invent_500() -> None:
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
        json={"Operations": "ghost"},
        headers=_auth("tok1"),
    )
    assert resp.status_code == 400
    assert resp.json().get("scimType") == "invalidSyntax"
    assert store.revoked == []


def test_leftover_patch_operations_dict_does_not_invent_500() -> None:
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
        json={"Operations": {"op": "replace", "path": "active", "value": False}},
        headers=_auth("tok1"),
    )
    assert resp.status_code == 400
    assert resp.json().get("scimType") == "invalidSyntax"
    assert store._memberships[0].status == "active"
    assert store.revoked == []


def test_leftover_patch_operations_int_item_does_not_invent_500() -> None:
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
        json={"Operations": [1]},
        headers=_auth("tok1"),
    )
    assert resp.status_code == 400
    assert resp.json().get("scimType") == "invalidSyntax"
    assert store.revoked == []


def test_valid_patch_operations_ride() -> None:
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
        json={"Operations": [{"op": "replace", "path": "active", "value": False}]},
        headers=_auth("tok1"),
    )
    assert resp.status_code == 200
    assert resp.json()["active"] is False
    assert store._memberships[0].status == "suspended"
    assert store.revoked == [mid]


def test_absent_patch_operations_still_noop() -> None:
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
        json={"schemas": ["urn:ietf:params:scim:api:messages:2.0:PatchOp"]},
        headers=_auth("tok1"),
    )
    assert resp.status_code == 200
    assert resp.json()["active"] is True
    assert store._memberships[0].status == "active"
    assert store.revoked == []


def test_empty_patch_operations_still_noop() -> None:
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
        json={"Operations": []},
        headers=_auth("tok1"),
    )
    assert resp.status_code == 200
    assert resp.json()["active"] is True
    assert store.revoked == []


def test_leftover_group_patch_operations_does_not_invent_noop() -> None:
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
        json={"Operations": "zzz"},
        headers=_auth("tok1"),
    )
    assert resp.status_code == 400
    assert resp.json().get("scimType") == "invalidSyntax"
    assert resp.json().get("detail") == "invalid Operations"
    assert store.get_group_member_ids(gid) == [m.id]
    assert store.get_membership(m.id).roles == ["engineer"]


def test_leftover_group_patch_operations_dict_does_not_invent_noop() -> None:
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
        json={"Operations": {"op": "replace", "path": "displayName", "value": "zzz"}},
        headers=_auth("tok1"),
    )
    assert resp.status_code == 400
    assert resp.json().get("scimType") == "invalidSyntax"
    group = store.get_scim_group(gid, "c1")
    assert group is not None
    assert group.display_name == "Eng"


def test_valid_group_patch_operations_ride() -> None:
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


def test_helper_source_pins_scim_operations_leftover() -> None:
    src = _ROUTES.read_text()
    assert "def leftover_honest_scim_operations" in src
    assert "def leftover_honest_scim_body_operations" in src
    assert "def leftover_scim_operations_stay_put" in src
    assert 'scim_type="invalidSyntax"' in src
    assert "JSONResponse" in src
    assert "leftover_scim_operations_stay_put" in src
    assert 'return _error(400, "invalid Operations", scim_type="invalidSyntax")' in src


def test_live_simple_task_declares_auth() -> None:
    src = _LIVE.read_text()
    assert "[auth]" in src
