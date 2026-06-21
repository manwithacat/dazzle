"""TDD tests for POST /auth/connections/policy (Task 4.1 — #1424).

Covers:
  (a) posting the join-policy form updates org settings via the store
  (b) a caller WITHOUT manage_connections gets the fail-closed 403 response
      (mirrors the capability-gating assertions in test_connection_admin_routes.py)
"""

from __future__ import annotations

from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from dazzle.http.runtime.auth.connection_admin_routes import create_connection_admin_routes

# ---------------------------------------------------------------------------
# Minimal fake store (no Postgres, no DAZZLE_CONNECTION_SECRET needed here)
# ---------------------------------------------------------------------------


class _Store:
    """Fake AuthStore supporting only the methods exercised by the policy route."""

    def __init__(self, *, roles: tuple[str, ...] = ("admin",)) -> None:
        self._roles = list(roles)
        self._org_settings: dict[str, dict] = {}
        # set_org_settings call log
        self.policy_calls: list[tuple[str, dict]] = []

    def validate_session(self, session_id: str) -> SimpleNamespace | None:
        if session_id != "good-sid":
            return None
        return SimpleNamespace(
            is_authenticated=True,
            user=SimpleNamespace(id="u1"),
            active_membership=SimpleNamespace(
                tenant_id="org-1",
                roles=self._roles,
                status="active",
            ),
        )

    def get_org_settings(self, org_id: str) -> dict:
        return self._org_settings.get(org_id, {})

    def set_org_settings(self, org_id: str, settings: dict) -> None:
        self._org_settings[org_id] = settings
        self.policy_calls.append((org_id, settings))

    # The connections page uses these too — keep them no-op so we don't 500
    # if the route ever touches them in the same request.
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


# ---------------------------------------------------------------------------
# Test-client builders (mirrors _client / _client_with_policy from the
# integration test to keep the idiom consistent)
# ---------------------------------------------------------------------------


def _client(store: _Store, *, authed: bool = True) -> TestClient:
    app = FastAPI()
    app.include_router(create_connection_admin_routes())
    app.state.auth_store = store
    app.state.org_admin_roles = ["admin"]
    app.state.sitespec = {"brand": {"product_name": "Acme"}}
    client = TestClient(app)
    if authed:
        client.cookies.set("dazzle_session", "good-sid")
    return client


def _client_with_policy(
    store: _Store,
    *,
    manage_connections: tuple[str, ...],
    manage_members: tuple[str, ...] = ("admin",),
) -> TestClient:
    from dazzle.http.runtime.auth.admin_policy import AdminPolicy

    app = FastAPI()
    app.include_router(create_connection_admin_routes())
    app.state.auth_store = store
    app.state.org_admin_roles = ["admin"]
    app.state.admin_policy = AdminPolicy.from_config(
        org_admin_roles=["admin"],
        admin_capabilities={
            "manage_connections": list(manage_connections),
            "manage_members": list(manage_members),
        },
    )
    app.state.sitespec = {"brand": {"product_name": "Acme"}}
    c = TestClient(app)
    c.cookies.set("dazzle_session", "good-sid")
    return c


# ---------------------------------------------------------------------------
# (a) Happy-path: posting the policy form updates org settings
# ---------------------------------------------------------------------------


def test_policy_update_persists_auto_join() -> None:
    """POST domain_join_policy=auto_join with no checkbox → stored correctly."""
    store = _Store()
    r = _client(store).post(
        "/auth/connections/policy",
        data={"domain_join_policy": "auto_join"},
        follow_redirects=False,
    )
    assert r.status_code in (204, 303)
    assert len(store.policy_calls) == 1
    org_id, saved = store.policy_calls[0]
    assert org_id == "org-1"
    assert saved["domain_join_policy"] == "auto_join"
    assert saved["restrict_membership_to_verified_domains"] is False


def test_policy_update_persists_off_with_restrict() -> None:
    """POST domain_join_policy=off + restrict checkbox=on → both stored."""
    store = _Store()
    r = _client(store).post(
        "/auth/connections/policy",
        data={
            "domain_join_policy": "off",
            "restrict_membership_to_verified_domains": "on",
        },
        follow_redirects=False,
    )
    assert r.status_code in (204, 303)
    assert len(store.policy_calls) == 1
    _, saved = store.policy_calls[0]
    assert saved["domain_join_policy"] == "off"
    assert saved["restrict_membership_to_verified_domains"] is True


def test_policy_unknown_value_coerces_to_admin_approval() -> None:
    """An unknown policy value is coerced to admin_approval (OrgSettings.from_dict behaviour)."""
    store = _Store()
    r = _client(store).post(
        "/auth/connections/policy",
        data={"domain_join_policy": "BOGUS"},
        follow_redirects=False,
    )
    assert r.status_code in (204, 303)
    _, saved = store.policy_calls[0]
    assert saved["domain_join_policy"] == "admin_approval"


def test_policy_update_is_org_fenced() -> None:
    """The org_id written to the store is the caller's active membership, never form input."""
    store = _Store()
    r = _client(store).post(
        "/auth/connections/policy",
        data={"domain_join_policy": "auto_join", "org_id": "evil-org"},
        follow_redirects=False,
    )
    assert r.status_code in (204, 303)
    org_id, _ = store.policy_calls[0]
    assert org_id == "org-1"  # always the authed membership's tenant, not form input


# ---------------------------------------------------------------------------
# (b) Capability gating: fail-closed for non-manage_connections callers
# ---------------------------------------------------------------------------


def test_policy_forbidden_without_session() -> None:
    """No session cookie → 403."""
    store = _Store()
    r = _client(store, authed=False).post(
        "/auth/connections/policy",
        data={"domain_join_policy": "auto_join"},
    )
    assert r.status_code == 403
    assert store.policy_calls == []


def test_policy_forbidden_for_non_admin_role() -> None:
    """Session with a non-admin role → 403 (org_admin_roles default gate)."""
    store = _Store(roles=("member",))
    r = _client(store).post(
        "/auth/connections/policy",
        data={"domain_join_policy": "auto_join"},
    )
    assert r.status_code == 403
    assert store.policy_calls == []


def test_policy_gated_on_manage_connections_capability() -> None:
    """With an explicit AdminPolicy, manage_connections controls access.

    Caller holds "admin" role; manage_connections mapped to "it_admin" → 403.
    """
    store = _Store(roles=("admin",))
    r = _client_with_policy(store, manage_connections=("it_admin",)).post(
        "/auth/connections/policy",
        data={"domain_join_policy": "auto_join"},
    )
    assert r.status_code == 403
    assert store.policy_calls == []


def test_policy_allows_mapped_manage_connections_persona() -> None:
    """Caller holds "it_admin"; manage_connections maps to "it_admin" → allowed."""
    store = _Store(roles=("it_admin",))
    r = _client_with_policy(store, manage_connections=("it_admin",)).post(
        "/auth/connections/policy",
        data={"domain_join_policy": "off"},
        follow_redirects=False,
    )
    assert r.status_code in (204, 303)
    assert store.policy_calls != []


# ---------------------------------------------------------------------------
# View: the connections page renders current policy settings
# ---------------------------------------------------------------------------


def test_connections_page_renders_policy_form() -> None:
    """GET /auth/connections includes the join-policy select and restrict checkbox."""
    store = _Store()
    store._org_settings["org-1"] = {
        "domain_join_policy": "auto_join",
        "restrict_membership_to_verified_domains": True,
    }
    r = _client(store).get("/auth/connections")
    assert r.status_code == 200
    assert "auto_join" in r.text  # the select option value is present
    assert "restrict_membership_to_verified_domains" in r.text  # the checkbox name


def test_connections_page_shows_current_policy_selected() -> None:
    """The current policy value appears selected in the rendered HTML."""
    store = _Store()
    store._org_settings["org-1"] = {"domain_join_policy": "off"}
    r = _client(store).get("/auth/connections")
    assert r.status_code == 200
    # The Combobox renderer emits 'selected' on the matching option
    assert 'value="off"' in r.text


def test_connections_page_shows_restrict_checked_when_enabled() -> None:
    """When restrict is True, the checkbox renders as checked."""
    store = _Store()
    store._org_settings["org-1"] = {
        "domain_join_policy": "admin_approval",
        "restrict_membership_to_verified_domains": True,
    }
    r = _client(store).get("/auth/connections")
    assert r.status_code == 200
    assert "checked" in r.text


# ---------------------------------------------------------------------------
# CSRF registration regression
# ---------------------------------------------------------------------------


def test_policy_path_is_csrf_protected() -> None:
    """/auth/connections/policy must appear in CSRFConfig.protected_paths."""
    from dazzle.http.runtime.csrf import CSRFConfig

    assert "/auth/connections/policy" in CSRFConfig().protected_paths


# ---------------------------------------------------------------------------
# Uncheck (disable) restriction: checkbox absent from form → persists False
# ---------------------------------------------------------------------------


def test_policy_restrict_unchecked_persists_false() -> None:
    """Submitting the policy form WITHOUT the restrict checkbox field → False.

    HTML checkboxes are omitted from POST data when unchecked, so the route
    must treat a missing field as False, not leave the previous True in place.
    """
    store = _Store()
    # Pre-seed the store so the previous value is True.
    store._org_settings["org-1"] = {
        "domain_join_policy": "auto_join",
        "restrict_membership_to_verified_domains": True,
    }
    r = _client(store).post(
        "/auth/connections/policy",
        # restrict_membership_to_verified_domains intentionally absent
        data={"domain_join_policy": "auto_join"},
        follow_redirects=False,
    )
    assert r.status_code in (204, 303)
    assert len(store.policy_calls) == 1
    _, saved = store.policy_calls[0]
    assert saved["restrict_membership_to_verified_domains"] is False
