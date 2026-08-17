"""Consent leftover tokens must not invent granted (cycle 2210).

leftover-honest filter bool already exists (oral #78). Consent POST
still coerced leftover ``analytics=zzz`` / ``"maybe"`` / the string
``"false"`` via ``bool(nonempty)`` and invented granted. Valid bools
and true/false tokens ride; leftover stays put (400, no cookie).
Live simple_task consent banner. Oral #90 — not leftover GET list
bool VALUE (oral #78).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from dazzle.compliance.analytics.consent import CONSENT_COOKIE_NAME
from dazzle.http.runtime.consent_routes import (
    create_consent_routes,
    leftover_consent_stay_put,
    leftover_honest_consent_bool,
    leftover_honest_consent_choices,
)

_ROUTES = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "dazzle"
    / "http"
    / "runtime"
    / "consent_routes.py"
)
_LIVE = (
    Path(__file__).resolve().parents[2]
    / "examples"
    / "simple_task"
    / "docs"
    / "privacy"
    / "cookie_policy.md"
)
_BANNER = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "dazzle"
    / "page"
    / "runtime"
    / "static"
    / "js"
    / "dz-consent.js"
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (True, True),
        (False, False),
        (1, True),
        (0, False),
        ("true", True),
        ("false", False),
        ("TRUE", True),
        ("FALSE", False),
        ("1", True),
        ("0", False),
        ("yes", True),
        ("no", False),
        ("granted", True),
        ("denied", False),
        ("", False),
        (None, False),
        ("zzz", None),
        ("ghost", None),
        ("maybe", None),
        ("falsee", None),
    ],
    ids=[
        "bool-true",
        "bool-false",
        "int-1",
        "int-0",
        "str-true",
        "str-false",
        "str-TRUE",
        "str-FALSE",
        "str-1",
        "str-0",
        "str-yes",
        "str-no",
        "str-granted",
        "str-denied",
        "empty",
        "none",
        "leftover-zzz",
        "leftover-ghost",
        "leftover-maybe",
        "leftover-falsee",
    ],
)
def test_leftover_honest_consent_bool_does_not_invent(raw: object, expected: bool | None) -> None:
    assert leftover_honest_consent_bool(raw) == expected


def test_leftover_consent_stay_put_when_any_junk() -> None:
    assert leftover_consent_stay_put({"analytics": "zzz"}) is True
    assert leftover_consent_stay_put({"analytics": True, "advertising": "maybe"}) is True
    assert leftover_consent_stay_put({"analytics": True, "advertising": False}) is False
    assert leftover_consent_stay_put({}) is False
    assert leftover_consent_stay_put({"analytics": "false"}) is False


def test_leftover_honest_consent_choices_stay_put() -> None:
    assert leftover_honest_consent_choices({"analytics": "zzz"}) is None
    assert leftover_honest_consent_choices({"analytics": True}) == {
        "analytics": True,
        "advertising": False,
        "personalization": False,
    }
    assert leftover_honest_consent_choices({"analytics": "false"}) == {
        "analytics": False,
        "advertising": False,
        "personalization": False,
    }


def _app() -> FastAPI:
    app = FastAPI()
    app.include_router(create_consent_routes(default_jurisdiction="EU"))
    return app


def test_leftover_consent_does_not_write_cookie() -> None:
    client = TestClient(_app())
    resp = client.post("/_dazzle/consent", json={"analytics": "zzz"})
    assert resp.status_code == 400
    assert CONSENT_COOKIE_NAME not in client.cookies
    assert CONSENT_COOKIE_NAME.lower() not in (resp.headers.get("set-cookie") or "").lower()


def test_leftover_string_false_used_to_invent_grant() -> None:
    """bool('false') is True — leftover-honest tokens must ride as deny."""
    client = TestClient(_app())
    resp = client.post("/_dazzle/consent", json={"analytics": "false"})
    assert resp.status_code == 204
    state = client.get("/_dazzle/consent/state").json()
    assert state["analytics"] == "denied"
    assert state["undecided"] is False


def test_mixed_leftover_consent_stays_put() -> None:
    client = TestClient(_app())
    resp = client.post(
        "/_dazzle/consent",
        json={"analytics": True, "advertising": "zzz"},
    )
    assert resp.status_code == 400
    assert CONSENT_COOKIE_NAME not in client.cookies


def test_valid_consent_still_writes() -> None:
    client = TestClient(_app())
    resp = client.post(
        "/_dazzle/consent",
        json={"analytics": True, "advertising": False, "personalization": False},
    )
    assert resp.status_code == 204
    state = client.get("/_dazzle/consent/state").json()
    assert state["analytics"] == "granted"
    assert state["advertising"] == "denied"


def test_helper_source_pins_consent_bool_leftover() -> None:
    src = _ROUTES.read_text()
    assert "def leftover_honest_consent_bool" in src
    assert "def leftover_consent_stay_put" in src
    assert "def leftover_honest_consent_choices" in src
    assert "leftover_honest_consent_choices(body)" in src
    assert "invalid consent choice" in src


def test_live_simple_task_declares_consent_banner() -> None:
    policy = _LIVE.read_text()
    assert "consent banner" in policy.lower()
    banner = _BANNER.read_text()
    assert 'CONSENT_ENDPOINT = "/_dazzle/consent"' in banner
    assert "analytics: true" in banner
