"""SCIM leftover active must not invent inactive / a 200 no-op (cycle 2228).

leftover-honest SCIM ?filter= already exists (oral #99). POST/PUT
``/scim/v2/Users`` still missed leftover ``active: "zzz"`` /
``ghost`` and invented inactive via ``bool(None)``. Leftover PATCH
invented a 200 no-op. Valid bools and Entra ``true``/``false``
strings ride; leftover stays put (400 invalidValue, no write).
Absent key still defaults active (first visit). Live SCIM Users.
Oral #100 — not leftover GET ``?filter=`` (oral #99) / not leftover
consent bool (oral #90).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from dazzle.http.runtime.auth.scim_routes import (
    leftover_honest_scim_active,
    leftover_honest_scim_body_active,
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
        (True, True),
        (False, False),
        ("true", True),
        ("false", False),
        ("TRUE", True),
        ("FALSE", False),
        ("True", True),
        ("False", False),
        ("  true  ", True),
        ("zzz", None),
        ("ghost", None),
        ("yes", None),
        ("1", None),
        ("0", None),
        ("", None),
        (None, None),
        (1, None),
        (0, None),
    ],
    ids=[
        "bool-true",
        "bool-false",
        "str-true",
        "str-false",
        "str-TRUE",
        "str-FALSE",
        "str-True",
        "str-False",
        "str-strip",
        "leftover-zzz",
        "leftover-ghost",
        "leftover-yes",
        "leftover-1",
        "leftover-0",
        "leftover-empty",
        "leftover-none",
        "leftover-int-1",
        "leftover-int-0",
    ],
)
def test_leftover_honest_scim_active_does_not_invent(raw: object, expected: bool | None) -> None:
    assert leftover_honest_scim_active(raw) == expected


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        ({}, True),
        ({"active": True}, True),
        ({"active": False}, False),
        ({"active": "true"}, True),
        ({"active": "False"}, False),
        ({"active": "zzz"}, None),
        ({"active": "ghost"}, None),
    ],
    ids=[
        "absent-default",
        "bool-true",
        "bool-false",
        "entra-true",
        "entra-false",
        "leftover-zzz",
        "leftover-ghost",
    ],
)
def test_leftover_honest_scim_body_active_does_not_invent(
    body: dict[str, object], expected: bool | None
) -> None:
    assert leftover_honest_scim_body_active(body) == expected


def test_leftover_create_active_does_not_invent_inactive() -> None:
    from tests.integration.test_scim_routes import _auth, _client, _conn, _Store

    store = _Store([_conn("c1", "org-1", "tok1")])
    client = _client(store)
    resp = client.post(
        "/scim/v2/Users",
        json={"userName": "jane@acme.test", "active": "zzz"},
        headers=_auth("tok1"),
    )
    assert resp.status_code == 400
    body = resp.json()
    assert body.get("scimType") == "invalidValue"
    assert body.get("status") == "400"
    assert store._memberships == []


def test_leftover_create_active_ghost_does_not_invent_inactive() -> None:
    from tests.integration.test_scim_routes import _auth, _client, _conn, _Store

    store = _Store([_conn("c1", "org-1", "tok1")])
    client = _client(store)
    resp = client.post(
        "/scim/v2/Users",
        json={"userName": "jane@acme.test", "active": "ghost"},
        headers=_auth("tok1"),
    )
    assert resp.status_code == 400
    assert resp.json().get("scimType") == "invalidValue"
    assert store._memberships == []


def test_absent_create_active_still_defaults_true() -> None:
    from tests.integration.test_scim_routes import _auth, _client, _conn, _Store

    store = _Store([_conn("c1", "org-1", "tok1")])
    client = _client(store)
    resp = client.post(
        "/scim/v2/Users",
        json={"userName": "jane@acme.test"},
        headers=_auth("tok1"),
    )
    assert resp.status_code == 201
    assert resp.json()["active"] is True


def test_valid_create_active_string_rides() -> None:
    from tests.integration.test_scim_routes import _auth, _client, _conn, _Store

    store = _Store([_conn("c1", "org-1", "tok1")])
    client = _client(store)
    resp = client.post(
        "/scim/v2/Users",
        json={"userName": "jane@acme.test", "active": "true"},
        headers=_auth("tok1"),
    )
    assert resp.status_code == 201
    assert resp.json()["active"] is True


def test_valid_create_active_false_string_rides() -> None:
    from tests.integration.test_scim_routes import _auth, _client, _conn, _Store

    store = _Store([_conn("c1", "org-1", "tok1")])
    client = _client(store)
    resp = client.post(
        "/scim/v2/Users",
        json={"userName": "jane@acme.test", "active": "False"},
        headers=_auth("tok1"),
    )
    assert resp.status_code == 201
    assert resp.json()["active"] is False


def test_leftover_replace_active_does_not_invent_inactive() -> None:
    from tests.integration.test_scim_routes import _auth, _client, _conn, _Store

    store = _Store([_conn("c1", "org-1", "tok1")])
    client = _client(store)
    created = client.post(
        "/scim/v2/Users",
        json={"userName": "jane@acme.test", "active": True},
        headers=_auth("tok1"),
    )
    mid = created.json()["id"]
    resp = client.put(
        f"/scim/v2/Users/{mid}",
        json={"userName": "jane@acme.test", "active": "zzz"},
        headers=_auth("tok1"),
    )
    assert resp.status_code == 400
    assert resp.json().get("scimType") == "invalidValue"
    assert store._memberships[0].status == "active"


def test_leftover_patch_active_does_not_invent_noop() -> None:
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
        json={"Operations": [{"op": "replace", "path": "active", "value": "zzz"}]},
        headers=_auth("tok1"),
    )
    assert resp.status_code == 400
    assert resp.json().get("scimType") == "invalidValue"
    assert store._memberships[0].status == "active"
    assert store.revoked == []


def test_leftover_patch_entra_active_does_not_invent_noop() -> None:
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
        json={"Operations": [{"op": "Replace", "value": {"active": "zzz"}}]},
        headers=_auth("tok1"),
    )
    assert resp.status_code == 400
    assert resp.json().get("scimType") == "invalidValue"
    assert store.revoked == []


def test_helper_source_pins_scim_active_leftover() -> None:
    src = _ROUTES.read_text()
    assert "def leftover_honest_scim_active" in src
    assert "def leftover_honest_scim_body_active" in src
    assert 'scim_type="invalidValue"' in src
    assert "JSONResponse" in src
    assert "_SCIM_ACTIVE_ABSENT" in src
    assert "bool(None)" in src


def test_live_simple_task_declares_auth() -> None:
    src = _LIVE.read_text()
    assert "[auth]" in src
