"""One gate: a SCIM attribute carrying a junk value stays put (DD-013 plan EA-3).

An IdP (or a fuzzer) that sends ``active: "zzz"``, ``members: "ghost"`` or
``Operations: {}`` must get a SCIM 400 naming the attribute and leave every
membership, group, role and session exactly as it was. Before the honesty helpers
those shapes were coerced into a write nobody asked for: ``bool("zzz")`` suspended
a user, a string ``members`` wiped a group, an unknown ``op`` answered 200 having
done nothing, a list ``externalId`` crashed provisioning with a 500.

This file folds the ten per-attribute ``test_scim_*_leftover.py`` files restored
from ``23cf59372`` into one parametrised gate (flense ship AX: one gate per
invariant). Three tables, each derived row by row from those files:

* ``JUNK`` — the route answers ``(status, scimType, detail)`` and the store does
  not move (snapshot before == after).
* ``VALID`` — the same attribute in a legitimate shape still rides.
* ``HELPER_CASES`` — the pure ``leftover_honest_*`` classifiers that the routes call,
  including the normalisations the route rows cannot see (strip, case-fold,
  ``userName`` blank falls through to ``emails``).

Dropped from the originals: the per-file source-text pins (``"def leftover_…" in
src``) and ``test_live_simple_task_declares_auth`` — they asserted spelling, not
behaviour, and every behaviour they stood for is a row below. The tables are kept
one row per line (``fmt: off``) so a row reads as a case.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest

from dazzle.http.runtime.auth.scim_provisioning import (
    leftover_honest_scim_body_display_name,
    leftover_honest_scim_body_external_id,
    leftover_honest_scim_body_members,
    leftover_honest_scim_display_name,
    leftover_honest_scim_external_id,
    leftover_honest_scim_member_ids,
    leftover_scim_display_name_stay_put,
    leftover_scim_external_id_stay_put,
    leftover_scim_members_stay_put,
)
from dazzle.http.runtime.auth.scim_routes import (
    leftover_honest_scim_active,
    leftover_honest_scim_body_active,
    leftover_honest_scim_body_operations,
    leftover_honest_scim_body_schemas,
    leftover_honest_scim_body_username,
    leftover_honest_scim_emails,
    leftover_honest_scim_eq_value,
    leftover_honest_scim_groups,
    leftover_honest_scim_operations,
    leftover_honest_scim_patch_op,
    leftover_honest_scim_schemas,
    leftover_honest_scim_username,
    leftover_scim_groups_stay_put,
    leftover_scim_operations_stay_put,
    leftover_scim_patch_op_stay_put,
)
from tests.integration.test_scim_routes import _auth, _client, _conn, _Store

_USER = "urn:ietf:params:scim:schemas:core:2.0:User"
_GROUP = "urn:ietf:params:scim:schemas:core:2.0:Group"
_PATCH = "urn:ietf:params:scim:api:messages:2.0:PatchOp"
_ABSENT = object()  # VALID expectation: the key must not be in the response


def _ops(*ops: dict[str, Any]) -> dict[str, Any]:
    return {"Operations": list(ops)}


def _set(path: str, value: Any, op: str = "replace") -> dict[str, Any]:
    return _ops({"op": op, "path": path, "value": value})


def _set_nopath(attr: str, value: Any) -> dict[str, Any]:
    """The Entra no-path form: ``{"op": "Replace", "value": {attr: value}}``."""
    return _ops({"op": "Replace", "value": {attr: value}})


@pytest.fixture
def world() -> tuple[Any, _Store, dict[str, str]]:
    """One org: user jane (externalId ``entra-guid-1``) in group Eng (``guid-1234`` → engineer)."""
    store = _Store([_conn("c1", "org-1", "tok1", group_mapping={"Eng": "engineer"})])
    client = _client(store)
    user = client.post(
        "/scim/v2/Users",
        json={"userName": "jane@acme.test", "externalId": "entra-guid-1"},
        headers=_auth("tok1"),
    ).json()["id"]
    group = client.post(
        "/scim/v2/Groups",
        json={"displayName": "Eng", "externalId": "guid-1234", "members": [{"value": user}]},
        headers=_auth("tok1"),
    ).json()["id"]
    assert store.get_membership(user).roles == ["engineer"]
    return client, store, {"user": user, "group": group}


def _snapshot(store: _Store) -> tuple[Any, ...]:
    """Everything a junk request could move: memberships, groups, members, revocations."""
    members = tuple(
        (m.id, m.tenant_id, m.status, tuple(m.roles), m.external_id) for m in store._memberships
    )
    groups = tuple(
        (g.id, g.display_name, g.external_id, tuple(store.get_group_member_ids(g.id)))
        for g in store.list_scim_groups("c1")
    )
    return members, groups, tuple(store.revoked), tuple(store._users)


def _send(client: Any, ids: dict[str, str], request: str, payload: Any) -> Any:
    method, path = request.split(" ", 1)
    url = "/scim/v2" + path.format(**ids)
    if method == "GET":
        return client.get(url, params=payload, headers=_auth("tok1"))
    return client.request(method, url, json=_fill(payload, ids), headers=_auth("tok1"))


def _fill(payload: Any, ids: dict[str, str]) -> Any:
    """Substitute ``{user}`` / ``{group}`` in string leaves (member ids, PATCH filters)."""
    if isinstance(payload, str):
        return payload.format(**ids) if "{" in payload else payload
    if isinstance(payload, list):
        return [_fill(item, ids) for item in payload]
    if isinstance(payload, dict):
        return {key: _fill(value, ids) for key, value in payload.items()}
    return payload


# fmt: off
# (attribute, request, junk_payload, expected_status, scim_type, expected_detail_fragment)
JUNK: list[tuple[str, str, Any, int, str | None, str]] = [
    # active — bool("zzz") used to invent inactive; PATCH used to invent a 200 no-op
    ("active", "POST /Users", {"userName": "ann@acme.test", "active": "zzz"}, 400, "invalidValue", "invalid active"),
    ("active", "POST /Users", {"userName": "ann@acme.test", "active": "ghost"}, 400, "invalidValue", "invalid active"),
    ("active", "PUT /Users/{user}", {"userName": "jane@acme.test", "active": "zzz"}, 400, "invalidValue", "invalid active"),
    ("active", "PATCH /Users/{user}", _set("active", "zzz"), 400, "invalidValue", "invalid active"),
    ("active", "PATCH /Users/{user}", _set_nopath("active", "zzz"), 400, "invalidValue", "invalid active"),
    # displayName — a non-string used to persist a group or str() a rename ("None")
    ("displayName", "POST /Groups", {"displayName": ["zzz"]}, 400, "invalidValue", "invalid displayName"),
    ("displayName", "POST /Groups", {"displayName": {"value": "Eng"}}, 400, "invalidValue", "invalid displayName"),
    ("displayName", "POST /Groups", {"displayName": 1}, 400, "invalidValue", "invalid displayName"),
    ("displayName", "POST /Groups", {"members": []}, 400, None, "displayName is required"),
    ("displayName", "PUT /Groups/{group}", {"displayName": ["zzz"], "members": [{"value": "{user}"}]}, 400, "invalidValue", "invalid displayName"),
    ("displayName", "PATCH /Groups/{group}", _set("displayName", ["zzz"]), 400, "invalidValue", "invalid displayName"),
    ("displayName", "PATCH /Groups/{group}", _set("displayName", None), 400, "invalidValue", "invalid displayName"),
    ("displayName", "PATCH /Groups/{group}", _set_nopath("displayName", ["zzz"]), 400, "invalidValue", "invalid displayName"),
    # externalId — a non-string used to 500 on .strip() or persist as the IdP's stable id
    ("externalId", "POST /Users", {"userName": "ann@acme.test", "externalId": ["zzz"]}, 400, "invalidValue", "invalid externalId"),
    ("externalId", "POST /Users", {"userName": "ann@acme.test", "externalId": {"value": "g"}}, 400, "invalidValue", "invalid externalId"),
    ("externalId", "POST /Users", {"userName": "ann@acme.test", "externalId": 1}, 400, "invalidValue", "invalid externalId"),
    ("externalId", "POST /Groups", {"displayName": "Sales", "externalId": ["zzz"]}, 400, "invalidValue", "invalid externalId"),
    ("externalId", "PUT /Groups/{group}", {"displayName": "Eng", "members": [{"value": "{user}"}], "externalId": ["zzz"]}, 400, "invalidValue", "invalid externalId"),
    ("externalId", "PATCH /Users/{user}", _set("externalId", ["zzz"]), 400, "invalidValue", "invalid externalId"),
    ("externalId", "PATCH /Groups/{group}", _set("externalId", ["zzz"]), 400, "invalidValue", "invalid externalId"),
    # filter — a non-eq filter used to answer the unfiltered list
    ("filter", "GET /Users", {"filter": "zzz"}, 400, "invalidFilter", "invalid filter"),
    ("filter", "GET /Groups", {"filter": "zzz"}, 400, "invalidFilter", "invalid filter"),
    ("filter", "GET /Groups", {"filter": "ghost"}, 400, "invalidFilter", "invalid filter"),
    # groups (User.groups) — a non-list used to 500 or provision as if absent
    ("groups", "POST /Users", {"userName": "ann@acme.test", "groups": "zzz"}, 400, "invalidValue", "invalid groups"),
    ("groups", "POST /Users", {"userName": "ann@acme.test", "groups": 1}, 400, "invalidValue", "invalid groups"),
    ("groups", "POST /Users", {"userName": "ann@acme.test", "groups": {"value": "Eng"}}, 400, "invalidValue", "invalid groups"),
    ("groups", "PUT /Users/{user}", {"userName": "jane@acme.test", "groups": 1, "active": True}, 400, "invalidValue", "invalid groups"),
    ("groups", "PATCH /Users/{user}", _set("groups", "zzz"), 400, "invalidValue", "invalid groups"),
    ("groups", "PATCH /Users/{user}", _set("groups", 1), 400, "invalidValue", "invalid groups"),
    # members — a non-list used to create an empty group or replace-with-empty (wipe)
    ("members", "POST /Groups", {"displayName": "Sales", "members": "zzz"}, 400, "invalidValue", "invalid members"),
    ("members", "POST /Groups", {"displayName": "Sales", "members": "ghost"}, 400, "invalidValue", "invalid members"),
    ("members", "PUT /Groups/{group}", {"displayName": "Eng", "members": "zzz"}, 400, "invalidValue", "invalid members"),
    ("members", "PATCH /Groups/{group}", _set("members", "zzz"), 400, "invalidValue", "invalid members"),
    ("members", "PATCH /Groups/{group}", _set_nopath("members", "zzz"), 400, "invalidValue", "invalid members"),
    # Operations — a non-list used to 500 (Users: str.get) or 200 no-op (Groups)
    ("Operations", "PATCH /Users/{user}", {"Operations": "zzz"}, 400, "invalidSyntax", "invalid Operations"),
    ("Operations", "PATCH /Users/{user}", {"Operations": "ghost"}, 400, "invalidSyntax", "invalid Operations"),
    ("Operations", "PATCH /Users/{user}", {"Operations": {"op": "replace", "path": "active", "value": False}}, 400, "invalidSyntax", "invalid Operations"),
    ("Operations", "PATCH /Users/{user}", {"Operations": [1]}, 400, "invalidSyntax", "invalid Operations"),
    ("Operations", "PATCH /Groups/{group}", {"Operations": "zzz"}, 400, "invalidSyntax", "invalid Operations"),
    ("Operations", "PATCH /Groups/{group}", {"Operations": {"op": "replace", "path": "displayName", "value": "zzz"}}, 400, "invalidSyntax", "invalid Operations"),
    # op — an unknown or missing verb used to be skipped (200, nothing done)
    ("op", "PATCH /Users/{user}", _set("active", False, op="zzz"), 400, "invalidSyntax", "invalid op"),
    ("op", "PATCH /Users/{user}", _ops({"op": 1, "path": "active", "value": False}), 400, "invalidSyntax", "invalid op"),
    ("op", "PATCH /Users/{user}", _ops({"path": "active", "value": False}), 400, "invalidSyntax", "invalid op"),
    ("op", "PATCH /Groups/{group}", _set("members", [], op="zzz"), 400, "invalidSyntax", "invalid op"),
    # schemas — a non-URN or wrong-resource envelope used to be ignored
    ("schemas", "POST /Users", {"schemas": "zzz", "userName": "ann@acme.test"}, 400, "invalidSyntax", "invalid schemas"),
    ("schemas", "POST /Users", {"schemas": ["zzz"], "userName": "ann@acme.test"}, 400, "invalidSyntax", "invalid schemas"),
    ("schemas", "POST /Users", {"schemas": {"value": _USER}, "userName": "ann@acme.test"}, 400, "invalidSyntax", "invalid schemas"),
    ("schemas", "POST /Groups", {"schemas": "zzz", "displayName": "Sales"}, 400, "invalidSyntax", "invalid schemas"),
    ("schemas", "PUT /Groups/{group}", {"schemas": ["zzz"], "displayName": "Renamed", "members": [{"value": "{user}"}]}, 400, "invalidSyntax", "invalid schemas"),
    ("schemas", "PATCH /Users/{user}", {"schemas": "zzz", **_set("active", False)}, 400, "invalidSyntax", "invalid schemas"),
    ("schemas", "PATCH /Groups/{group}", {"schemas": ["ghost"], **_set("displayName", "X")}, 400, "invalidSyntax", "invalid schemas"),
    # userName / emails — a non-mailbox used to 500 or provision "zzz" as a mailbox
    ("userName", "POST /Users", {"userName": "zzz"}, 400, "invalidValue", "invalid userName"),
    ("userName", "POST /Users", {"userName": "ghost"}, 400, "invalidValue", "invalid userName"),
    ("userName", "POST /Users", {"userName": ["jane@acme.test"]}, 400, "invalidValue", "invalid userName"),
    ("userName", "POST /Users", {"emails": "zzz"}, 400, "invalidValue", "invalid userName"),
    ("userName", "POST /Users", {"emails": [{}]}, 400, "invalidValue", "invalid userName"),
    ("userName", "POST /Users", {"emails": []}, 400, "invalidValue", "no email"),
    ("userName", "POST /Users", {"active": True}, 400, "invalidValue", "no email"),
]
# fmt: on


@pytest.mark.parametrize(
    ("attribute", "request_line", "junk_payload", "expected_status", "scim_type", "detail"),
    JUNK,
    ids=[f"{row[0]}-{row[1].split()[0]}-{i}" for i, row in enumerate(JUNK)],
)
def test_junk_attribute_stays_put(
    world: tuple[Any, _Store, dict[str, str]],
    attribute: str,
    request_line: str,
    junk_payload: Any,
    expected_status: int,
    scim_type: str | None,
    detail: str,
) -> None:
    client, store, ids = world
    before = _snapshot(store)

    resp = _send(client, ids, request_line, junk_payload)

    assert resp.status_code == expected_status, attribute
    body = resp.json()
    assert body.get("scimType") == scim_type
    assert body.get("status") == str(expected_status)
    assert detail in body.get("detail", "")
    assert "Resources" not in body
    assert _snapshot(store) == before


# fmt: off
# (attribute, request, valid_payload, expected_status, expected response fields)
VALID: list[tuple[str, str, Any, int, dict[str, Any]]] = [
    ("active", "POST /Users", {"userName": "ann@acme.test"}, 201, {"active": True}),
    ("active", "POST /Users", {"userName": "ann@acme.test", "active": "true"}, 201, {"active": True}),
    ("active", "POST /Users", {"userName": "ann@acme.test", "active": "False"}, 201, {"active": False}),
    ("displayName", "POST /Groups", {"displayName": "zzz"}, 201, {"displayName": "zzz"}),
    ("displayName", "PUT /Groups/{group}", {"displayName": "Platform", "members": [{"value": "{user}"}]}, 200, {"displayName": "Platform"}),
    ("displayName", "PATCH /Groups/{group}", _set("displayName", "Platform"), 200, {"displayName": "Platform"}),
    ("externalId", "POST /Users", {"userName": "ann@acme.test", "externalId": "entra-guid-2"}, 201, {"externalId": "entra-guid-2"}),
    ("externalId", "POST /Users", {"userName": "ann@acme.test", "externalId": "zzz"}, 201, {"externalId": "zzz"}),
    ("externalId", "POST /Users", {"userName": "ann@acme.test"}, 201, {"externalId": _ABSENT}),
    ("externalId", "POST /Groups", {"displayName": "Sales", "externalId": "guid-5678"}, 201, {"externalId": "guid-5678"}),
    ("externalId", "PUT /Groups/{group}", {"displayName": "Eng", "members": [{"value": "{user}"}], "externalId": "guid-5678"}, 200, {"externalId": "guid-5678"}),
    ("filter", "GET /Groups", {}, 200, {"totalResults": 1}),
    ("filter", "GET /Groups", {"filter": 'displayName eq "Eng"'}, 200, {"totalResults": 1}),
    ("filter", "GET /Groups", {"filter": 'displayName eq "Sales"'}, 200, {"totalResults": 0}),
    ("filter", "GET /Users", {"filter": 'userName eq "jane@acme.test"'}, 200, {"totalResults": 1}),
    ("groups", "POST /Users", {"userName": "ann@acme.test", "groups": [{"value": "Eng"}]}, 201, {}),
    ("groups", "POST /Users", {"userName": "ann@acme.test", "groups": [{"display": "Eng"}]}, 201, {}),
    ("groups", "PUT /Users/{user}", {"userName": "jane@acme.test", "groups": [{"value": "Eng"}], "active": True}, 200, {"active": True}),
    ("groups", "PATCH /Users/{user}", _set("groups", [{"value": "Eng"}]), 200, {"active": True}),
    ("members", "POST /Groups", {"displayName": "Sales"}, 201, {"members": []}),
    ("members", "PATCH /Groups/{group}", _set("members", []), 200, {"members": []}),
    ("Operations", "PATCH /Users/{user}", _set("active", False), 200, {"active": False}),
    ("Operations", "PATCH /Users/{user}", {"schemas": [_PATCH]}, 200, {"active": True}),
    ("Operations", "PATCH /Users/{user}", {"Operations": []}, 200, {"active": True}),
    ("op", "PATCH /Users/{user}", _set("active", False, op="Replace"), 200, {"active": False}),
    ("op", "PATCH /Groups/{group}", _ops({"op": "remove", "path": 'members[value eq "{user}"]'}), 200, {"members": []}),
    ("schemas", "POST /Users", {"schemas": [_USER], "userName": "ann@acme.test"}, 201, {"schemas": [_USER]}),
    ("schemas", "POST /Groups", {"schemas": [_GROUP], "displayName": "Sales"}, 201, {"schemas": [_GROUP]}),
    ("schemas", "PUT /Groups/{group}", {"schemas": [_GROUP], "displayName": "Renamed", "members": [{"value": "{user}"}]}, 200, {"displayName": "Renamed"}),
    ("schemas", "PATCH /Users/{user}", {"schemas": [_PATCH], **_set("active", False)}, 200, {"active": False}),
    ("userName", "POST /Users", {"userName": "ann@acme.test"}, 201, {"userName": "ann@acme.test"}),
    ("userName", "POST /Users", {"emails": [{"value": "ann@acme.test"}]}, 201, {"userName": "ann@acme.test"}),
]
# fmt: on


@pytest.mark.parametrize(
    ("attribute", "request_line", "payload", "expected_status", "fields"),
    VALID,
    ids=[f"{row[0]}-{row[1].split()[0]}-{i}" for i, row in enumerate(VALID)],
)
def test_valid_attribute_rides(
    world: tuple[Any, _Store, dict[str, str]],
    attribute: str,
    request_line: str,
    payload: Any,
    expected_status: int,
    fields: dict[str, Any],
) -> None:
    client, _store, ids = world

    resp = _send(client, ids, request_line, payload)

    assert resp.status_code == expected_status, (attribute, resp.text)
    body = resp.json()
    for key, value in fields.items():
        if value is _ABSENT:
            assert key not in body
        else:
            assert body[key] == value


# fmt: off
# Pure classifiers: helper → [(args, kwargs, expected)]. None means "junk: stay put".
_STRING_ATTR = [
    (("Eng",), "Eng"), (("  Platform  ",), "Platform"), (("zzz",), "zzz"), (("ghost",), "ghost"),
    (("",), ""), (("   ",), ""), ((None,), ""), ((["zzz"],), None), (({"value": "Eng"},), None),
    ((1,), None), ((True,), None),
]
_U, _G, _P = _USER, _GROUP, _PATCH
HELPER_CASES: dict[Callable[..., Any], list[tuple[tuple[Any, ...], dict[str, Any], Any]]] = {
    leftover_honest_scim_active: [((raw,), {}, expected) for raw, expected in [
        (True, True), (False, False), ("true", True), ("false", False), ("TRUE", True),
        ("FALSE", False), ("True", True), ("False", False), ("  true  ", True), ("zzz", None),
        ("ghost", None), ("yes", None), ("1", None), ("0", None), ("", None), (None, None),
        (1, None), (0, None),
    ]],
    leftover_honest_scim_body_active: [((body,), {}, expected) for body, expected in [
        ({}, True), ({"active": True}, True), ({"active": False}, False),
        ({"active": "true"}, True), ({"active": "False"}, False),
        ({"active": "zzz"}, None), ({"active": "ghost"}, None),
    ]],
    leftover_honest_scim_display_name: [(args, {}, exp) for args, exp in _STRING_ATTR],
    leftover_honest_scim_external_id: [(args, {}, exp) for args, exp in _STRING_ATTR]
    + [((["entra-guid-1"],), {}, None)],
    leftover_honest_scim_body_display_name: [((body,), {}, expected) for body, expected in [
        ({}, ""), ({"displayName": "Eng"}, "Eng"), ({"displayName": "zzz"}, "zzz"),
        ({"displayName": ""}, ""), ({"displayName": ["zzz"]}, None),
        ({"displayName": {"value": "Eng"}}, None), ({"displayName": 1}, None),
        ({"displayName": True}, None),
    ]],
    leftover_honest_scim_body_external_id: [((body,), {}, expected) for body, expected in [
        ({}, ""), ({"externalId": "entra-guid-1"}, "entra-guid-1"), ({"externalId": "zzz"}, "zzz"),
        ({"externalId": ""}, ""), ({"externalId": ["zzz"]}, None),
        ({"externalId": {"value": "entra-guid-1"}}, None), ({"externalId": 1}, None),
        ({"externalId": True}, None),
    ]],
    leftover_honest_scim_eq_value: [((raw,), {"attr": attr}, expected) for raw, attr, expected in [
        ('userName eq "jane@acme.test"', "userName", "jane@acme.test"),
        ('displayName eq "Eng"', "displayName", "Eng"),
        ('DISPLAYNAME eq "Eng"', "displayName", "Eng"),
        ('  displayName eq "Eng"  ', "displayName", "Eng"),
        ("", "displayName", ""), (None, "displayName", ""), ("   ", "userName", ""),
        ("zzz", "displayName", None), ("ghost", "displayName", None), ("filter", "userName", None),
        ("displayName eq Eng", "displayName", None),
        ('userName eq "jane@acme.test"', "displayName", None),
        ('displayName eq "Eng"', "userName", None),
        ('displayName eq ""', "displayName", None),
        ('garbage displayName eq "Eng"', "displayName", None),
        ('displayName eq "Eng" leftover', "displayName", None),
    ]],
    leftover_honest_scim_groups: [((raw,), {}, expected) for raw, expected in [
        ([], []), (None, []), ([{"value": "Eng"}], ["Eng"]), ([{"display": "Eng"}], ["Eng"]),
        ([{"display": "Engineering", "value": "eng"}], ["Engineering"]),
        ([{"value": "  Eng  "}], ["Eng"]), ([{"value": "zzz"}], ["zzz"]), ("zzz", None),
        ("ghost", None), ("", None), ({"value": "Eng"}, None), (1, None), (True, None),
        ([{"value": 1}], None), ([{"value": True}], None), ([{}], None), ([{"value": ""}], None),
        ([{"value": "   "}], None), ([{"value": None}], None), (["Eng"], None), ([1], None),
    ]],
    leftover_honest_scim_member_ids: [((raw,), {}, expected) for raw, expected in [
        ([], []), ([{"value": "m1"}], ["m1"]), ([{"value": "m1"}, {"value": "m2"}], ["m1", "m2"]),
        ([{"value": "  m1  "}], ["m1"]), ("zzz", None), ("ghost", None), ("x", None),
        ({"value": "m1"}, None), (None, None), (1, None), ([{"display": "Eng"}], None),
        ([{}], None), ([{"value": ""}], None), ([{"value": "   "}], None),
        ([{"value": None}], None), (["m1"], None), ([1], None),
    ]],
    leftover_honest_scim_body_members: [((body,), {}, expected) for body, expected in [
        ({}, []), ({"members": []}, []), ({"members": [{"value": "m1"}]}, ["m1"]),
        ({"members": "zzz"}, None), ({"members": "ghost"}, None), ({"members": [{}]}, None),
    ]],
    leftover_honest_scim_operations: [((raw,), {}, expected) for raw, expected in [
        ([], []),
        ([{"op": "replace", "path": "active", "value": True}], [{"op": "replace", "path": "active", "value": True}]),
        ([{"op": "add", "path": "members", "value": []}], [{"op": "add", "path": "members", "value": []}]),
        ([{}], [{}]), (None, []), ("zzz", None), ("ghost", None), ("x", None),
        ({"op": "replace"}, None), (1, None), (["zzz"], None), ([1], None),
        ([{"op": "replace"}, "zzz"], None),
    ]],
    leftover_honest_scim_body_operations: [((body,), {}, expected) for body, expected in [
        ({}, []), ({"Operations": []}, []),
        ({"Operations": [{"op": "replace", "path": "active", "value": False}]}, [{"op": "replace", "path": "active", "value": False}]),
        ({"Operations": "zzz"}, None), ({"Operations": "ghost"}, None),
        ({"Operations": {"op": "replace"}}, None), ({"Operations": [1]}, None),
    ]],
    leftover_honest_scim_patch_op: [((raw,), {}, expected) for raw, expected in [
        ("add", "add"), ("remove", "remove"), ("replace", "replace"), ("Add", "add"),
        ("REPLACE", "replace"), ("  remove  ", "remove"), ("zzz", None), ("ghost", None),
        ("purge", None), ("", None), ("   ", None), (None, None), (1, None), (True, None),
        (["replace"], None), ({"op": "replace"}, None),
    ]],
    leftover_honest_scim_schemas: [((raw,), {"required": req}, expected) for raw, req, expected in [
        ([_U], _U, [_U]), ([_U, _P], _U, [_U, _P]), ([_G], _G, [_G]), ([_P], _P, [_P]),
        (None, _U, []), ([], _U, []), ("", _U, None), ("zzz", _U, None), ("ghost", _U, None),
        (["zzz"], _U, None), (["ghost"], _U, None), ([_G], _U, None), ([_U], _G, None),
        (["  zzz  "], _U, None), ({"value": _U}, _U, None), (1, _U, None), (True, _U, None),
        ([1], _U, None), ([True], _U, None), ([{_U: True}], _U, None),
    ]],
    leftover_honest_scim_body_schemas: [((body,), {"required": req}, expected) for body, req, expected in [
        ({}, _U, []), ({"schemas": [_U]}, _U, [_U]), ({"schemas": [_P]}, _P, [_P]),
        ({"schemas": ""}, _U, None), ({"schemas": "zzz"}, _U, None),
        ({"schemas": ["zzz"]}, _U, None), ({"schemas": [_G]}, _U, None),
        ({"schemas": 1}, _U, None), ({"schemas": True}, _U, None),
    ]],
    leftover_honest_scim_username: [((raw,), {}, expected) for raw, expected in [
        ("jane@acme.test", "jane@acme.test"), ("  jane@acme.test  ", "jane@acme.test"),
        ("", ""), ("   ", ""), (None, ""), ("zzz", None), ("ghost", None),
        ("not-an-email", None), ("jane@", None), (["jane@acme.test"], None),
        ({"value": "jane@acme.test"}, None), (1, None),
    ]],
    leftover_honest_scim_emails: [((raw,), {}, expected) for raw, expected in [
        ([{"value": "jane@acme.test"}], "jane@acme.test"),
        ([{"value": "  jane@acme.test  "}], "jane@acme.test"), ([], ""), (None, ""),
        ("zzz", None), ("ghost", None), ([{}], None), ([{"display": "Jane"}], None),
        ([{"value": "zzz"}], None), ([{"value": "ghost"}], None), (["jane@acme.test"], None),
        (1, None),
    ]],
    leftover_honest_scim_body_username: [((body,), {}, expected) for body, expected in [
        ({}, ""), ({"userName": "jane@acme.test"}, "jane@acme.test"), ({"userName": ""}, ""),
        ({"emails": [{"value": "jane@acme.test"}]}, "jane@acme.test"),
        ({"userName": "", "emails": [{"value": "jane@acme.test"}]}, "jane@acme.test"),
        ({"userName": "zzz"}, None), ({"userName": "ghost"}, None),
        ({"userName": ["jane@acme.test"]}, None), ({"emails": "zzz"}, None),
        ({"emails": []}, ""), ({"emails": [{}]}, None), ({"emails": [{"value": "zzz"}]}, None),
    ]],
    # PATCH stay-put predicates: True means "this body would have invented a write/no-op".
    leftover_scim_display_name_stay_put: [((body,), {}, expected) for body, expected in [
        (_set("displayName", ["zzz"]), True), (_set("displayName", {"v": 1}), True),
        (_set("displayName", 1), True), (_set("displayName", None), True),
        (_ops({"op": "replace", "value": {"displayName": ["zzz"]}}), True),
        ({}, False), ({"Operations": []}, False), (_set("displayName", "Platform"), False),
    ]],
    leftover_scim_external_id_stay_put: [((body,), {}, expected) for body, expected in [
        (_set("externalId", ["zzz"]), True), (_set("externalId", {"v": 1}), True),
        (_set("externalId", 1), True), (_set("externalId", None), True),
        (_ops({"op": "replace", "value": {"externalId": ["zzz"]}}), True),
        ({}, False), ({"Operations": []}, False), (_set("externalId", "entra-guid-1"), False),
    ]],
    leftover_scim_groups_stay_put: [((body,), {}, expected) for body, expected in [
        (_set("groups", "zzz"), True), (_set("groups", 1), True),
        (_ops({"op": "replace", "value": {"groups": "ghost"}}), True),
        (_set("groups", ["Eng"], op="add"), True),
        ({}, False), ({"Operations": []}, False),
        (_set("groups", [{"value": "Eng"}]), False), (_set("active", False), False),
    ]],
    leftover_scim_members_stay_put: [((body,), {}, expected) for body, expected in [
        (_set("members", "zzz"), True), (_set("members", "ghost", op="add"), True),
        (_set_nopath("members", [{}]), True),
        (_set("members", [{"value": "m1"}]), False), (_set("members", []), False),
        (_ops({"op": "remove", "path": "members"}), False),
    ]],
    leftover_scim_operations_stay_put: [((body,), {}, expected) for body, expected in [
        ({"Operations": "zzz"}, True), ({"Operations": "ghost"}, True),
        ({"Operations": {"op": "replace"}}, True), ({"Operations": [1]}, True),
        ({}, False), ({"Operations": []}, False), (_set("active", False), False),
    ]],
    leftover_scim_patch_op_stay_put: [((body,), {}, expected) for body, expected in [
        (_set("active", False, op="zzz"), True), (_set("members", [], op="ghost"), True),
        (_ops({"op": 1, "path": "active", "value": False}), True),
        (_ops({"path": "active", "value": False}), True),
        (_ops({"op": "replace", "path": "active", "value": False}, {"op": "zzz"}), True),
        ({}, False), ({"Operations": []}, False), (_set("active", False), False),
        (_set("members", [], op="Add"), False),
    ]],
}
# fmt: on
_HELPER_ROWS = [
    (helper, args, kwargs, expected)
    for helper, cases in HELPER_CASES.items()
    for args, kwargs, expected in cases
]


@pytest.mark.parametrize(
    ("helper", "args", "kwargs", "expected"),
    _HELPER_ROWS,
    ids=[f"{row[0].__name__}-{i}" for i, row in enumerate(_HELPER_ROWS)],
)
def test_honesty_helper_classifies(
    helper: Callable[..., Any], args: tuple[Any, ...], kwargs: dict[str, Any], expected: Any
) -> None:
    assert helper(*args, **kwargs) == expected
