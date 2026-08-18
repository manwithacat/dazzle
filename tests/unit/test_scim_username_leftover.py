"""SCIM leftover userName / emails must not invent a 500 / provision (cycle 2230).

leftover-honest SCIM members already exists (oral #101). POST
``/scim/v2/Users`` still missed leftover ``userName: "zzz"`` /
``emails: "zzz"`` / list / dict and invented a crash (``.strip()``
/ ``"zzz"[0].get`` / ``IndexError``) or a provision attempt with
leftover as the mailbox (``domain_not_verified`` theater). Valid
emails ride; leftover stays put (400 invalidValue, no write).
Absent / blank still ``no_email``. Live SCIM Users. Oral #102 —
not leftover SCIM members (oral #101) / not leftover ``active``
(oral #100).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from dazzle.http.runtime.auth.scim_routes import (
    leftover_honest_scim_body_username,
    leftover_honest_scim_emails,
    leftover_honest_scim_username,
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
        ("jane@acme.test", "jane@acme.test"),
        ("  jane@acme.test  ", "jane@acme.test"),
        ("", ""),
        ("   ", ""),
        (None, ""),
        ("zzz", None),
        ("ghost", None),
        ("not-an-email", None),
        ("jane@", None),
        (["jane@acme.test"], None),
        ({"value": "jane@acme.test"}, None),
        (1, None),
    ],
    ids=[
        "valid",
        "strip",
        "empty",
        "blank",
        "none",
        "leftover-zzz",
        "leftover-ghost",
        "leftover-not-email",
        "leftover-partial",
        "leftover-list",
        "leftover-dict",
        "leftover-int",
    ],
)
def test_leftover_honest_scim_username_does_not_invent(raw: object, expected: str | None) -> None:
    assert leftover_honest_scim_username(raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ([{"value": "jane@acme.test"}], "jane@acme.test"),
        ([{"value": "  jane@acme.test  "}], "jane@acme.test"),
        ([], ""),
        (None, ""),
        ("zzz", None),
        ("ghost", None),
        ([{}], None),
        ([{"display": "Jane"}], None),
        ([{"value": "zzz"}], None),
        ([{"value": "ghost"}], None),
        (["jane@acme.test"], None),
        (1, None),
    ],
    ids=[
        "valid",
        "strip",
        "empty-list",
        "none",
        "leftover-zzz",
        "leftover-ghost",
        "leftover-empty-dict",
        "leftover-display-only",
        "leftover-value-zzz",
        "leftover-value-ghost",
        "leftover-string-item",
        "leftover-int",
    ],
)
def test_leftover_honest_scim_emails_does_not_invent(raw: object, expected: str | None) -> None:
    assert leftover_honest_scim_emails(raw) == expected


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        ({}, ""),
        ({"userName": "jane@acme.test"}, "jane@acme.test"),
        ({"userName": ""}, ""),
        ({"emails": [{"value": "jane@acme.test"}]}, "jane@acme.test"),
        ({"userName": "", "emails": [{"value": "jane@acme.test"}]}, "jane@acme.test"),
        ({"userName": "zzz"}, None),
        ({"userName": "ghost"}, None),
        ({"userName": ["jane@acme.test"]}, None),
        ({"emails": "zzz"}, None),
        ({"emails": []}, ""),
        ({"emails": [{}]}, None),
        ({"emails": [{"value": "zzz"}]}, None),
    ],
    ids=[
        "absent-default",
        "username-valid",
        "username-blank",
        "emails-valid",
        "blank-username-emails-fallback",
        "leftover-username-zzz",
        "leftover-username-ghost",
        "leftover-username-list",
        "leftover-emails-zzz",
        "emails-empty-list",
        "leftover-emails-empty-dict",
        "leftover-emails-value-zzz",
    ],
)
def test_leftover_honest_scim_body_username_does_not_invent(
    body: dict[str, object], expected: str | None
) -> None:
    assert leftover_honest_scim_body_username(body) == expected


def test_leftover_create_username_does_not_invent_provision() -> None:
    from tests.integration.test_scim_routes import _auth, _client, _conn, _Store

    store = _Store([_conn("c1", "org-1", "tok1")])
    client = _client(store)
    resp = client.post(
        "/scim/v2/Users",
        json={"userName": "zzz"},
        headers=_auth("tok1"),
    )
    assert resp.status_code == 400
    body = resp.json()
    assert body.get("scimType") == "invalidValue"
    assert body.get("detail") == "invalid userName"
    assert store._memberships == []


def test_leftover_create_username_ghost_does_not_invent_provision() -> None:
    from tests.integration.test_scim_routes import _auth, _client, _conn, _Store

    store = _Store([_conn("c1", "org-1", "tok1")])
    client = _client(store)
    resp = client.post(
        "/scim/v2/Users",
        json={"userName": "ghost"},
        headers=_auth("tok1"),
    )
    assert resp.status_code == 400
    assert resp.json().get("scimType") == "invalidValue"
    assert store._memberships == []


def test_leftover_create_username_list_does_not_invent_500() -> None:
    from tests.integration.test_scim_routes import _auth, _client, _conn, _Store

    store = _Store([_conn("c1", "org-1", "tok1")])
    client = _client(store)
    resp = client.post(
        "/scim/v2/Users",
        json={"userName": ["jane@acme.test"]},
        headers=_auth("tok1"),
    )
    assert resp.status_code == 400
    assert resp.json().get("scimType") == "invalidValue"
    assert store._memberships == []


def test_leftover_create_emails_zzz_does_not_invent_500() -> None:
    from tests.integration.test_scim_routes import _auth, _client, _conn, _Store

    store = _Store([_conn("c1", "org-1", "tok1")])
    client = _client(store)
    resp = client.post(
        "/scim/v2/Users",
        json={"emails": "zzz"},
        headers=_auth("tok1"),
    )
    assert resp.status_code == 400
    assert resp.json().get("scimType") == "invalidValue"
    assert store._memberships == []


def test_leftover_create_emails_empty_list_does_not_invent_500() -> None:
    from tests.integration.test_scim_routes import _auth, _client, _conn, _Store

    store = _Store([_conn("c1", "org-1", "tok1")])
    client = _client(store)
    resp = client.post(
        "/scim/v2/Users",
        json={"emails": []},
        headers=_auth("tok1"),
    )
    assert resp.status_code == 400
    body = resp.json()
    assert body.get("scimType") == "invalidValue"
    assert "no email" in body.get("detail", "")
    assert store._memberships == []


def test_leftover_create_emails_empty_dict_does_not_invent_500() -> None:
    from tests.integration.test_scim_routes import _auth, _client, _conn, _Store

    store = _Store([_conn("c1", "org-1", "tok1")])
    client = _client(store)
    resp = client.post(
        "/scim/v2/Users",
        json={"emails": [{}]},
        headers=_auth("tok1"),
    )
    assert resp.status_code == 400
    assert resp.json().get("scimType") == "invalidValue"
    assert resp.json().get("detail") == "invalid userName"
    assert store._memberships == []


def test_valid_create_username_rides() -> None:
    from tests.integration.test_scim_routes import _auth, _client, _conn, _Store

    store = _Store([_conn("c1", "org-1", "tok1")])
    client = _client(store)
    resp = client.post(
        "/scim/v2/Users",
        json={"userName": "jane@acme.test"},
        headers=_auth("tok1"),
    )
    assert resp.status_code == 201
    assert resp.json()["userName"] == "jane@acme.test"
    assert store._memberships


def test_valid_create_emails_ride() -> None:
    from tests.integration.test_scim_routes import _auth, _client, _conn, _Store

    store = _Store([_conn("c1", "org-1", "tok1")])
    client = _client(store)
    resp = client.post(
        "/scim/v2/Users",
        json={"emails": [{"value": "jane@acme.test"}]},
        headers=_auth("tok1"),
    )
    assert resp.status_code == 201
    assert resp.json()["userName"] == "jane@acme.test"
    assert store._memberships


def test_absent_create_username_still_no_email() -> None:
    from tests.integration.test_scim_routes import _auth, _client, _conn, _Store

    store = _Store([_conn("c1", "org-1", "tok1")])
    client = _client(store)
    resp = client.post(
        "/scim/v2/Users",
        json={"active": True},
        headers=_auth("tok1"),
    )
    assert resp.status_code == 400
    assert "no email" in resp.json().get("detail", "")
    assert store._memberships == []


def test_helper_source_pins_scim_username_leftover() -> None:
    src = _ROUTES.read_text()
    assert "def leftover_honest_scim_username" in src
    assert "def leftover_honest_scim_emails" in src
    assert "def leftover_honest_scim_body_username" in src
    assert 'scim_type="invalidValue"' in src
    assert "JSONResponse" in src
    assert "leftover_honest_scim_body_username" in src
    assert 'return _error(400, "invalid userName", scim_type="invalidValue")' in src


def test_live_simple_task_declares_auth() -> None:
    src = _LIVE.read_text()
    assert "[auth]" in src
