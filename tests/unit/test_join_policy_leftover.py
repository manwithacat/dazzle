"""Join-policy leftover tokens must not invent admin_approval (cycle 2212).

leftover-honest catalog id already exists (oral #69). Connection-admin
policy POST still coerced leftover ``domain_join_policy=zzz`` via
``OrgSettings.from_dict`` and persisted invented ``admin_approval``.
Valid declared tokens ride; leftover stays put (400, no write).
Live domain_join_co join-policy form. Oral #91 — not leftover
persona roles (oral #89), not leftover catalog picker (oral #69).
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from dazzle.http.runtime.auth.connection_admin_routes import create_connection_admin_routes
from dazzle.http.runtime.auth.org_settings import leftover_honest_join_policy

_ORG_SETTINGS = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "dazzle"
    / "http"
    / "runtime"
    / "auth"
    / "org_settings.py"
)
_ROUTES = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "dazzle"
    / "http"
    / "runtime"
    / "auth"
    / "connection_admin_routes.py"
)
_VIEWS = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "dazzle"
    / "http"
    / "runtime"
    / "auth"
    / "connection_admin_views.py"
)
_LIVE = Path(__file__).resolve().parents[2] / "examples" / "domain_join_co" / "dsl" / "domain.dsl"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("off", "off"),
        ("auto_join", "auto_join"),
        ("admin_approval", "admin_approval"),
        ("zzz", None),
        ("ghost", None),
        ("BOGUS", None),
        ("AUTO_JOIN", None),
        ("", None),
        (None, None),
        ("admin_approval ", "admin_approval"),
    ],
    ids=[
        "off",
        "auto-join",
        "admin-approval",
        "leftover-zzz",
        "leftover-ghost",
        "leftover-bogus",
        "leftover-case",
        "empty",
        "none",
        "valid-strip",
    ],
)
def test_leftover_honest_join_policy_does_not_invent(raw: object, expected: str | None) -> None:
    assert leftover_honest_join_policy(raw) == expected


class _Store:
    def __init__(self) -> None:
        self._org_settings: dict[str, dict] = {}
        self.policy_calls: list[tuple[str, dict]] = []

    def validate_session(self, session_id: str) -> SimpleNamespace | None:
        if session_id != "good-sid":
            return None
        return SimpleNamespace(
            is_authenticated=True,
            user=SimpleNamespace(id="u1"),
            active_membership=SimpleNamespace(
                tenant_id="org-1",
                roles=["admin"],
                status="active",
            ),
        )

    def get_org_settings(self, org_id: str) -> dict:
        return self._org_settings.get(org_id, {})

    def set_org_settings(self, org_id: str, settings: dict) -> None:
        self._org_settings[org_id] = settings
        self.policy_calls.append((org_id, settings))

    def get_connections_for_tenant(self, tenant_id: str) -> list:
        return []

    def get_organization(self, org_id: str) -> SimpleNamespace:
        return SimpleNamespace(name="Acme Inc")

    def get_connection_secret_events(
        self, connection_id: str, *, tenant_id: str | None = None
    ) -> list:
        return []

    def get_connection_grace_status(
        self, connection_id: str, *, tenant_id: str | None = None
    ) -> tuple:
        return (False, None)


def _client(store: _Store) -> TestClient:
    app = FastAPI()
    app.include_router(create_connection_admin_routes())
    app.state.auth_store = store
    app.state.org_admin_roles = ["admin"]
    app.state.sitespec = {"brand": {"product_name": "Acme"}}
    client = TestClient(app)
    client.cookies.set("dazzle_session", "good-sid")
    return client


def test_leftover_policy_does_not_write() -> None:
    store = _Store()
    store._org_settings["org-1"] = {"domain_join_policy": "auto_join"}
    resp = _client(store).post(
        "/auth/connections/policy",
        data={"domain_join_policy": "zzz"},
        follow_redirects=False,
    )
    assert resp.status_code == 400
    assert store.policy_calls == []
    assert store._org_settings["org-1"]["domain_join_policy"] == "auto_join"


def test_empty_policy_stays_put() -> None:
    store = _Store()
    store._org_settings["org-1"] = {"domain_join_policy": "off"}
    resp = _client(store).post(
        "/auth/connections/policy",
        data={"domain_join_policy": ""},
        follow_redirects=False,
    )
    assert resp.status_code == 400
    assert store.policy_calls == []


def test_valid_policy_still_writes() -> None:
    store = _Store()
    resp = _client(store).post(
        "/auth/connections/policy",
        data={"domain_join_policy": "off"},
        follow_redirects=False,
    )
    assert resp.status_code in (204, 303)
    assert len(store.policy_calls) == 1
    _, saved = store.policy_calls[0]
    assert saved["domain_join_policy"] == "off"


def test_helper_source_pins_join_policy_leftover() -> None:
    helper = _ORG_SETTINGS.read_text()
    assert "def leftover_honest_join_policy" in helper
    assert "leftover_honest_catalog_id" in helper
    routes = _ROUTES.read_text()
    assert "leftover_honest_join_policy" in routes
    assert "Unknown join policy" in routes
    views = _VIEWS.read_text()
    assert 'name="domain_join_policy"' in views
    assert '("off",' in views
    assert '("admin_approval",' in views
    assert '("auto_join",' in views


def test_live_domain_join_co_declares_join_policy() -> None:
    src = _LIVE.read_text()
    assert "domain_join_policy" in src
    assert "admin_approval" in src
    assert "sets the join policy" in src
