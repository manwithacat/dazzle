"""Connection leftover group_map must not invent a persist (cycle 2249).

leftover-honest membership roles already exist (oral #89 /
leftover_honest_persona_roles). POST ``/auth/connections/create``
still skipped leftover ``zzz`` / ``garbage`` / half-pairs and
invented a connection persist (empty or partial mapping). Valid
``group=persona`` pairs ride; leftover stays put (400, no write).
Absent / blank still first-visit (empty mapping). Live simple_task
``/auth/connections``. Oral #119 — not leftover ``?new=`` (oral
#97), not leftover membership roles (oral #89).
"""

from __future__ import annotations

import base64
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from dazzle.http.runtime.auth.connection_admin_routes import create_connection_admin_routes
from dazzle.http.runtime.auth.connection_create_form import leftover_honest_group_map

_FORM = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "dazzle"
    / "http"
    / "runtime"
    / "auth"
    / "connection_create_form.py"
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
_LIVE = Path(__file__).resolve().parents[2] / "examples" / "simple_task" / "dazzle.toml"
_VIEWS = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "dazzle"
    / "http"
    / "runtime"
    / "auth"
    / "connection_admin_views.py"
)


@pytest.fixture(autouse=True)
def _connection_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DAZZLE_CONNECTION_SECRET", base64.b64encode(b"k" * 32).decode())


@pytest.mark.parametrize(
    ("raw", "declared", "expected"),
    [
        ("eng=engineer", None, {"eng": "engineer"}),
        ("eng=engineer, ops=operator", None, {"eng": "engineer", "ops": "operator"}),
        ("  eng=engineer  ", None, {"eng": "engineer"}),
        ("eng=engineer\nops=operator", None, {"eng": "engineer", "ops": "operator"}),
        ("", None, {}),
        (None, None, {}),
        ("   ", None, {}),
        ("zzz", None, None),
        ("ghost", None, None),
        ("garbage", None, None),
        ("eng=engineer, zzz", None, None),
        ("=role", None, None),
        ("group=", None, None),
        ("eng=zzz", ("engineer", "operator"), None),
        ("eng=engineer", ("engineer", "operator"), {"eng": "engineer"}),
        (["eng=engineer"], None, None),
        ({"eng": "engineer"}, None, None),
        (1, None, None),
        (True, None, None),
    ],
    ids=[
        "valid-pair",
        "valid-two",
        "strip",
        "newline",
        "empty-first-visit",
        "none-first-visit",
        "blank-first-visit",
        "leftover-zzz",
        "leftover-ghost",
        "leftover-garbage",
        "leftover-mixed",
        "leftover-empty-group",
        "leftover-empty-role",
        "leftover-persona",
        "declared-rides",
        "leftover-list",
        "leftover-dict",
        "leftover-int",
        "leftover-true",
    ],
)
def test_leftover_honest_group_map_does_not_invent(
    raw: object, declared: object, expected: dict[str, str] | None
) -> None:
    assert leftover_honest_group_map(raw, declared) == expected


class _Store:
    def validate_session(self, session_id: object) -> object:
        if session_id != "good-sid":
            return None
        return SimpleNamespace(
            is_authenticated=True,
            user=SimpleNamespace(id="u1"),
            active_membership=SimpleNamespace(tenant_id="org-1", roles=("admin",), status="active"),
        )

    def get_connections_for_tenant(self, tenant_id: object) -> list[object]:
        return []

    def get_org_settings(self, org_id: object) -> dict[str, object]:
        return {}

    def get_organization(self, org_id: object) -> object:
        return SimpleNamespace(name="Acme Inc")

    def create_connection(self, **kw: Any) -> object:
        self.created = kw
        return SimpleNamespace(id="conn-new")


def _client(store: _Store) -> TestClient:
    app = FastAPI()
    app.include_router(create_connection_admin_routes())
    app.state.auth_store = store
    app.state.org_admin_roles = ["admin"]
    app.state.sitespec = {"brand": {"product_name": "Acme"}}
    client = TestClient(app)
    client.cookies.set("dazzle_session", "good-sid")
    return client


def test_leftover_group_map_zzz_does_not_invent_persist() -> None:
    store = _Store()
    resp = _client(store).post(
        "/auth/connections/create?type=scim",
        data={"group_map": "zzz"},
        follow_redirects=False,
    )
    assert resp.status_code == 400
    assert resp.text == "Unknown group map"
    assert not hasattr(store, "created")


def test_leftover_group_map_ghost_does_not_invent_persist() -> None:
    store = _Store()
    resp = _client(store).post(
        "/auth/connections/create?type=scim",
        data={"group_map": "ghost"},
        follow_redirects=False,
    )
    assert resp.status_code == 400
    assert "Unknown group map" in resp.text
    assert not hasattr(store, "created")


def test_leftover_group_map_mixed_does_not_invent_partial() -> None:
    store = _Store()
    resp = _client(store).post(
        "/auth/connections/create?type=scim",
        data={"group_map": "eng=engineer, garbage"},
        follow_redirects=False,
    )
    assert resp.status_code == 400
    assert "Unknown group map" in resp.text
    assert not hasattr(store, "created")


def test_valid_group_map_still_creates() -> None:
    store = _Store()
    resp = _client(store).post(
        "/auth/connections/create?type=scim",
        data={"group_map": "eng=engineer"},
        follow_redirects=False,
    )
    assert resp.status_code == 200
    assert store.created["group_mapping"] == {"eng": "engineer"}


def test_blank_group_map_still_first_visit() -> None:
    store = _Store()
    resp = _client(store).post(
        "/auth/connections/create?type=scim",
        data={"group_map": ""},
        follow_redirects=False,
    )
    assert resp.status_code == 200
    assert store.created["group_mapping"] == {}


def test_helper_source_pins_group_map_leftover() -> None:
    form = _FORM.read_text()
    assert "def leftover_honest_group_map" in form
    assert "CreateFormError" in form
    routes = _ROUTES.read_text()
    assert "leftover_honest_group_map" in routes
    assert 'return HTMLResponse("Unknown group map", status_code=400)' in routes
    assert "Response(\n            status_code=400,\n            content=" not in routes


def test_live_simple_task_connections_and_group_map() -> None:
    assert "[auth]" in _LIVE.read_text()
    assert "group_map" in _VIEWS.read_text()
    assert "/auth/connections/create?type=" in _VIEWS.read_text()
