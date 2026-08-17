"""SCIM leftover ?filter= must not invent an unfiltered list (cycle 2227).

leftover-honest REST filter[key] already exists (oral #74 / #85). SCIM
GET ``/scim/v2/Groups`` still missed leftover ``?filter=zzz`` /
``ghost`` (displayName-eq regex) and invented the unfiltered Groups
list. Users ``?filter=zzz`` invented the same for userName. Valid
``displayName eq "…"`` / ``userName eq "…"`` ride; leftover stays
put (400 invalidFilter, no invented catalog). Live SCIM Groups +
Users. Oral #99 — not leftover REST filter VALUES (oral #85).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from dazzle.http.runtime.auth.scim_routes import leftover_honest_scim_eq_value

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
    ("raw", "attr", "expected"),
    [
        ('userName eq "jane@acme.test"', "userName", "jane@acme.test"),
        ('displayName eq "Eng"', "displayName", "Eng"),
        ('DISPLAYNAME eq "Eng"', "displayName", "Eng"),
        ("", "displayName", ""),
        (None, "displayName", ""),
        ("   ", "userName", ""),
        ("zzz", "displayName", None),
        ("ghost", "displayName", None),
        ("filter", "userName", None),
        ("displayName eq Eng", "displayName", None),
        ('userName eq "jane@acme.test"', "displayName", None),
        ('displayName eq "Eng"', "userName", None),
        ('displayName eq ""', "displayName", None),
        ('garbage displayName eq "Eng"', "displayName", None),
        ('displayName eq "Eng" leftover', "displayName", None),
        ('  displayName eq "Eng"  ', "displayName", "Eng"),
    ],
    ids=[
        "valid-username",
        "valid-displayname",
        "valid-attr-case",
        "empty-default",
        "none-default",
        "blank-default",
        "leftover-zzz",
        "leftover-ghost",
        "leftover-bare",
        "leftover-unquoted",
        "leftover-wrong-attr-groups",
        "leftover-wrong-attr-users",
        "leftover-empty-quoted",
        "leftover-prefix",
        "leftover-suffix",
        "valid-strip",
    ],
)
def test_leftover_honest_scim_eq_value_does_not_invent(
    raw: object, attr: str, expected: str | None
) -> None:
    assert leftover_honest_scim_eq_value(raw, attr=attr) == expected


def test_leftover_groups_filter_does_not_invent_unfiltered_list() -> None:
    from tests.integration.test_scim_routes import _auth, _client, _group_store

    store, _m = _group_store()
    client = _client(store)
    client.post("/scim/v2/Groups", json={"displayName": "Eng"}, headers=_auth("tok1"))
    resp = client.get("/scim/v2/Groups?filter=zzz", headers=_auth("tok1"))
    assert resp.status_code == 400
    body = resp.json()
    assert body.get("scimType") == "invalidFilter"
    assert body.get("status") == "400"
    assert "Resources" not in body


def test_leftover_groups_filter_ghost_does_not_invent_unfiltered_list() -> None:
    from tests.integration.test_scim_routes import _auth, _client, _group_store

    store, _m = _group_store()
    client = _client(store)
    client.post("/scim/v2/Groups", json={"displayName": "Eng"}, headers=_auth("tok1"))
    resp = client.get("/scim/v2/Groups?filter=ghost", headers=_auth("tok1"))
    assert resp.status_code == 400
    assert resp.json().get("scimType") == "invalidFilter"


def test_absent_groups_filter_still_lists_all() -> None:
    from tests.integration.test_scim_routes import _auth, _client, _group_store

    store, _m = _group_store()
    client = _client(store)
    client.post("/scim/v2/Groups", json={"displayName": "Eng"}, headers=_auth("tok1"))
    resp = client.get("/scim/v2/Groups", headers=_auth("tok1"))
    assert resp.status_code == 200
    assert resp.json()["totalResults"] == 1
    assert resp.json()["Resources"][0]["displayName"] == "Eng"


def test_valid_groups_display_name_filter_rides() -> None:
    from tests.integration.test_scim_routes import _auth, _client, _group_store

    store, _m = _group_store()
    client = _client(store)
    client.post("/scim/v2/Groups", json={"displayName": "Eng"}, headers=_auth("tok1"))
    client.post("/scim/v2/Groups", json={"displayName": "Sales"}, headers=_auth("tok1"))
    resp = client.get('/scim/v2/Groups?filter=displayName eq "Eng"', headers=_auth("tok1"))
    assert resp.status_code == 200
    body = resp.json()
    assert body["totalResults"] == 1
    assert body["Resources"][0]["displayName"] == "Eng"


def test_leftover_users_filter_does_not_invent_unfiltered_list() -> None:
    from tests.integration.test_scim_routes import _auth, _client, _conn, _Store

    store = _Store([_conn("c1", "org-1", "tok1")])
    client = _client(store)
    client.post("/scim/v2/Users", json={"userName": "jane@acme.test"}, headers=_auth("tok1"))
    resp = client.get("/scim/v2/Users?filter=zzz", headers=_auth("tok1"))
    assert resp.status_code == 400
    assert resp.json().get("scimType") == "invalidFilter"
    assert "Resources" not in resp.json()


def test_valid_users_username_filter_rides() -> None:
    from tests.integration.test_scim_routes import _auth, _client, _conn, _Store

    store = _Store([_conn("c1", "org-1", "tok1")])
    client = _client(store)
    client.post("/scim/v2/Users", json={"userName": "jane@acme.test"}, headers=_auth("tok1"))
    resp = client.get('/scim/v2/Users?filter=userName eq "jane@acme.test"', headers=_auth("tok1"))
    assert resp.status_code == 200
    body = resp.json()
    assert body["totalResults"] == 1
    assert body["Resources"][0]["userName"] == "jane@acme.test"


def test_helper_source_pins_scim_filter_leftover() -> None:
    src = _ROUTES.read_text()
    assert "def leftover_honest_scim_eq_value" in src
    assert "_SCIM_EQ_FILTER" in src
    assert 'scim_type="invalidFilter"' in src
    assert "JSONResponse" in src
    assert 'attr="displayName"' in src or "attr='displayName'" in src
    assert 'attr="userName"' in src or "attr='userName'" in src


def test_live_simple_task_declares_auth() -> None:
    src = _LIVE.read_text()
    assert "[auth]" in src
