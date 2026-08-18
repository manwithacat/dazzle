"""Org leftover membership_id must not invent invalid_org theater (cycle 2237).

leftover-honest auth urlsafe token already exists (oral #98). Select /
switch still posted leftover ``membership_id=zzz`` / ``ghost`` into
``set_session_active_membership`` and invented
``303 /auth/select-org?error=invalid_org``. Valid
``secrets.token_urlsafe(24)`` ids ride; leftover stays put (400, no
write / no theater). Absent / blank still first-visit (400 required).
Well-formed ids that fail ownership still bounce invalid_org. Live
simple_task ``/auth/select-org``. Oral #107 — not leftover auth token
echo (oral #98), not leftover entity-id query (oral #71).
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from dazzle.http.runtime.auth.org_context_routes import (
    create_org_context_routes,
    leftover_honest_membership_id,
)

_ORG = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "dazzle"
    / "http"
    / "runtime"
    / "auth"
    / "org_context_routes.py"
)
_LIVE = Path(__file__).resolve().parents[2] / "examples" / "simple_task" / "dazzle.toml"

# secrets.token_urlsafe(24) is 32 urlsafe chars; token_urlsafe(32) is 43.
_VALID = "A" * 32


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (_VALID, _VALID),
        ("b" * 43, "b" * 43),
        ("", ""),
        (None, ""),
        ("   ", ""),
        ("zzz", None),
        ("ghost", None),
        ("m-bob", None),
        ("token:evil", None),
        (f"{_VALID} ", _VALID),
        (["A" * 32], None),
        ({"id": "A" * 32}, None),
        (1, None),
        (True, None),
    ],
    ids=[
        "valid-urlsafe-32",
        "valid-urlsafe-43",
        "empty-default",
        "none-default",
        "blank-default",
        "leftover-zzz",
        "leftover-ghost",
        "leftover-m-bob",
        "leftover-colon",
        "valid-strip",
        "leftover-list",
        "leftover-dict",
        "leftover-int",
        "leftover-true",
    ],
)
def test_leftover_honest_membership_id_does_not_invent(raw: object, expected: str | None) -> None:
    assert leftover_honest_membership_id(raw) == expected


def _org_app(store: MagicMock) -> FastAPI:
    app = FastAPI()
    app.state.auth_store = store
    app.state.sitespec = {}
    app.include_router(create_org_context_routes())
    return app


def _authed_store(*, activate_ok: bool = True) -> MagicMock:
    user = SimpleNamespace(id="u1")
    ctx = SimpleNamespace(is_authenticated=True, user=user)
    store = MagicMock()
    store.validate_session.return_value = ctx
    store.set_session_active_membership.return_value = activate_ok
    store.regenerate_session_csrf.return_value = "csrf-secret"
    return store


def test_leftover_select_org_membership_does_not_invent_invalid_org() -> None:
    store = _authed_store()
    client = TestClient(_org_app(store))
    client.cookies.set("dazzle_session", "sid")
    resp = client.post("/auth/select-org", data={"membership_id": "zzz"}, follow_redirects=False)
    assert resp.status_code == 400
    assert "Unknown membership" in resp.text
    store.set_session_active_membership.assert_not_called()


def test_leftover_switch_org_membership_does_not_invent_invalid_org() -> None:
    store = _authed_store()
    client = TestClient(_org_app(store))
    client.cookies.set("dazzle_session", "sid")
    resp = client.post("/auth/switch-org", data={"membership_id": "ghost"}, follow_redirects=False)
    assert resp.status_code == 400
    assert "Unknown membership" in resp.text
    store.set_session_active_membership.assert_not_called()


def test_absent_membership_still_first_visit() -> None:
    store = _authed_store()
    client = TestClient(_org_app(store))
    client.cookies.set("dazzle_session", "sid")
    resp = client.post("/auth/select-org", data={"membership_id": ""}, follow_redirects=False)
    assert resp.status_code == 400
    assert "Membership required" in resp.text
    assert "invalid_org" not in (resp.headers.get("location") or "")
    store.set_session_active_membership.assert_not_called()


def test_valid_membership_still_activates() -> None:
    store = _authed_store()
    client = TestClient(_org_app(store))
    client.cookies.set("dazzle_session", "sid")
    resp = client.post("/auth/select-org", data={"membership_id": _VALID}, follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"] == "/app"
    store.set_session_active_membership.assert_called_once()
    assert store.set_session_active_membership.call_args.args[1] == _VALID


def test_unowned_wellformed_membership_still_invalid_org() -> None:
    store = _authed_store(activate_ok=False)
    client = TestClient(_org_app(store))
    client.cookies.set("dazzle_session", "sid")
    resp = client.post("/auth/switch-org", data={"membership_id": _VALID}, follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"] == "/auth/select-org?error=invalid_org"
    store.set_session_active_membership.assert_called_once()


def test_helper_source_pins_membership_id_leftover() -> None:
    org = _ORG.read_text()
    assert "def leftover_honest_membership_id" in org
    assert "def leftover_membership_or_400" in org
    assert "leftover_honest_auth_token" in org
    assert "Unknown membership" in org
    assert "Membership required" in org
    assert "HTMLResponse" in org
    assert org.count("_submit_membership(") == 3


def test_live_simple_task_declares_auth_login() -> None:
    src = _LIVE.read_text()
    assert "[auth]" in src
