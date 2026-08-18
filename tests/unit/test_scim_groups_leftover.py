"""SCIM leftover User.groups must not invent a 500 / provision (cycle 2245).

leftover-honest SCIM members already exist (oral #101). POST/PUT
``/scim/v2/Users`` still iterated leftover ``groups: "zzz"`` / ``ghost``
/ dict / int and invented a 500 (``int`` / ``True``) or invented empty
(string chars skipped) then provisioned. Leftover PATCH invented a
200 no-op. Valid ``[{"value": "Eng"}]`` / ``[{"display": "Eng"}]``
ride; leftover stays put (400 invalidValue, no write). Absent / empty
still omit (first-visit; User.groups is informational). Live SCIM
Users. Oral #115 — not leftover members (oral #101) / not leftover
schemas (oral #114).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from dazzle.http.runtime.auth.scim_routes import (
    leftover_honest_scim_groups,
    leftover_scim_groups_stay_put,
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
        (None, []),
        ([{"value": "Eng"}], ["Eng"]),
        ([{"display": "Eng"}], ["Eng"]),
        ([{"display": "Engineering", "value": "eng"}], ["Engineering"]),
        ([{"value": "  Eng  "}], ["Eng"]),
        ([{"value": "zzz"}], ["zzz"]),
        ("zzz", None),
        ("ghost", None),
        ("", None),
        ({"value": "Eng"}, None),
        (1, None),
        (True, None),
        ([{"value": 1}], None),
        ([{"value": True}], None),
        ([{}], None),
        ([{"value": ""}], None),
        ([{"value": "   "}], None),
        ([{"value": None}], None),
        (["Eng"], None),
        ([1], None),
    ],
    ids=[
        "empty-list-omit",
        "none-absent",
        "value-rides",
        "display-rides",
        "display-wins",
        "strip",
        "zzz-name-rides",
        "leftover-zzz",
        "leftover-ghost",
        "leftover-blank-str",
        "leftover-dict",
        "leftover-int",
        "leftover-true",
        "leftover-value-int",
        "leftover-value-true",
        "leftover-empty-dict",
        "leftover-empty-value",
        "leftover-blank-value",
        "leftover-none-value",
        "leftover-string-item",
        "leftover-int-item",
    ],
)
def test_leftover_honest_scim_groups_does_not_invent(
    raw: object, expected: list[str] | None
) -> None:
    assert leftover_honest_scim_groups(raw) == expected


def test_leftover_patch_groups_stay_put_detects_noop() -> None:
    assert leftover_scim_groups_stay_put(
        {"Operations": [{"op": "replace", "path": "groups", "value": "zzz"}]}
    )
    assert leftover_scim_groups_stay_put(
        {"Operations": [{"op": "replace", "path": "groups", "value": 1}]}
    )
    assert leftover_scim_groups_stay_put(
        {"Operations": [{"op": "replace", "value": {"groups": "ghost"}}]}
    )
    assert leftover_scim_groups_stay_put(
        {"Operations": [{"op": "add", "path": "groups", "value": ["Eng"]}]}
    )
    assert not leftover_scim_groups_stay_put({})
    assert not leftover_scim_groups_stay_put({"Operations": []})
    assert not leftover_scim_groups_stay_put(
        {"Operations": [{"op": "replace", "path": "groups", "value": [{"value": "Eng"}]}]}
    )
    assert not leftover_scim_groups_stay_put(
        {"Operations": [{"op": "replace", "path": "active", "value": False}]}
    )


def test_leftover_create_user_groups_str_does_not_invent_provision() -> None:
    from tests.integration.test_scim_routes import _auth, _client, _conn, _Store

    store = _Store([_conn("c1", "org-1", "tok1")])
    client = _client(store)
    resp = client.post(
        "/scim/v2/Users",
        json={"userName": "jane@acme.test", "groups": "zzz"},
        headers=_auth("tok1"),
    )
    assert resp.status_code == 400
    body = resp.json()
    assert body.get("scimType") == "invalidValue"
    assert body.get("detail") == "invalid groups"
    assert store._memberships == []


def test_leftover_create_user_groups_int_does_not_invent_500() -> None:
    from tests.integration.test_scim_routes import _auth, _client, _conn, _Store

    store = _Store([_conn("c1", "org-1", "tok1")])
    client = _client(store)
    resp = client.post(
        "/scim/v2/Users",
        json={"userName": "jane@acme.test", "groups": 1},
        headers=_auth("tok1"),
    )
    assert resp.status_code == 400
    assert resp.json().get("scimType") == "invalidValue"
    assert store._memberships == []


def test_leftover_create_user_groups_dict_does_not_invent_provision() -> None:
    from tests.integration.test_scim_routes import _auth, _client, _conn, _Store

    store = _Store([_conn("c1", "org-1", "tok1")])
    client = _client(store)
    resp = client.post(
        "/scim/v2/Users",
        json={"userName": "jane@acme.test", "groups": {"value": "Eng"}},
        headers=_auth("tok1"),
    )
    assert resp.status_code == 400
    assert resp.json().get("scimType") == "invalidValue"
    assert store._memberships == []


def test_valid_create_user_groups_value_rides() -> None:
    from tests.integration.test_scim_routes import _auth, _client, _conn, _Store

    store = _Store([_conn("c1", "org-1", "tok1")])
    client = _client(store)
    resp = client.post(
        "/scim/v2/Users",
        json={"userName": "jane@acme.test", "groups": [{"value": "Eng"}]},
        headers=_auth("tok1"),
    )
    assert resp.status_code == 201
    assert store._memberships[0].id


def test_valid_create_user_groups_display_rides() -> None:
    from tests.integration.test_scim_routes import _auth, _client, _conn, _Store

    store = _Store([_conn("c1", "org-1", "tok1")])
    client = _client(store)
    resp = client.post(
        "/scim/v2/Users",
        json={"userName": "jane@acme.test", "groups": [{"display": "Eng"}]},
        headers=_auth("tok1"),
    )
    assert resp.status_code == 201
    assert store._memberships[0].id


def test_absent_create_user_groups_still_omits() -> None:
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


def test_leftover_put_user_groups_does_not_invent_500() -> None:
    from tests.integration.test_scim_routes import _auth, _client, _conn, _Store

    store = _Store([_conn("c1", "org-1", "tok1")])
    client = _client(store)
    mid = client.post(
        "/scim/v2/Users",
        json={"userName": "jane@acme.test"},
        headers=_auth("tok1"),
    ).json()["id"]
    resp = client.put(
        f"/scim/v2/Users/{mid}",
        json={"userName": "jane@acme.test", "groups": 1, "active": True},
        headers=_auth("tok1"),
    )
    assert resp.status_code == 400
    assert resp.json().get("scimType") == "invalidValue"
    assert store.get_membership(mid).status == "active"


def test_valid_put_user_groups_rides() -> None:
    from tests.integration.test_scim_routes import _auth, _client, _conn, _Store

    store = _Store([_conn("c1", "org-1", "tok1")])
    client = _client(store)
    mid = client.post(
        "/scim/v2/Users",
        json={"userName": "jane@acme.test"},
        headers=_auth("tok1"),
    ).json()["id"]
    resp = client.put(
        f"/scim/v2/Users/{mid}",
        json={
            "userName": "jane@acme.test",
            "groups": [{"value": "Eng"}],
            "active": True,
        },
        headers=_auth("tok1"),
    )
    assert resp.status_code == 200
    assert store.get_membership(mid).status == "active"


def test_leftover_patch_user_groups_does_not_invent_noop() -> None:
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
        json={"Operations": [{"op": "replace", "path": "groups", "value": "zzz"}]},
        headers=_auth("tok1"),
    )
    assert resp.status_code == 400
    assert resp.json().get("scimType") == "invalidValue"
    assert resp.json().get("detail") == "invalid groups"
    assert store.get_membership(mid).status == "active"


def test_leftover_patch_user_groups_int_does_not_invent_noop() -> None:
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
        json={"Operations": [{"op": "replace", "path": "groups", "value": 1}]},
        headers=_auth("tok1"),
    )
    assert resp.status_code == 400
    assert resp.json().get("scimType") == "invalidValue"
    assert store.get_membership(mid).status == "active"


def test_valid_patch_user_groups_rides_as_informational() -> None:
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
        json={"Operations": [{"op": "replace", "path": "groups", "value": [{"value": "Eng"}]}]},
        headers=_auth("tok1"),
    )
    # User.groups is informational / server-managed — valid leftover-honest
    # shape stays put as a no-op write (return current), not a 400.
    assert resp.status_code == 200
    assert store.get_membership(mid).status == "active"


def test_helper_source_pins_scim_groups_leftover() -> None:
    routes = _ROUTES.read_text()
    assert "def leftover_honest_scim_groups" in routes
    assert "def leftover_scim_groups_stay_put" in routes
    assert "leftover_honest_scim_groups" in routes
    assert 'return _error(400, "invalid groups", scim_type="invalidValue")' in routes
    assert "JSONResponse" in routes
    assert "Response(\n            status_code=400,\n            content=" not in routes


def test_live_simple_task_declares_auth() -> None:
    src = _LIVE.read_text()
    assert "[auth]" in src
