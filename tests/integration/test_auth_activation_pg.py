"""Real-PostgreSQL proof of two-phase activation + org-switch (auth Plan 1b).

Marked e2e + postgres: skipped without TEST_DATABASE_URL/DATABASE_URL.
Mirrors tests/integration/test_auth_membership_pg.py's scratch-DB harness.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator

import psycopg
import pytest

pytestmark = [pytest.mark.e2e, pytest.mark.postgres]

_PG_URL = os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL")


def _admin_url() -> str:
    assert _PG_URL is not None
    return _PG_URL.replace("postgresql+psycopg://", "postgresql://")


@pytest.fixture
def scratch_url() -> Iterator[str]:
    if not _PG_URL:
        pytest.skip("no TEST_DATABASE_URL/DATABASE_URL")
    admin_url = _admin_url()
    base, _, _old = admin_url.rpartition("/")
    scratch = f"dazzle_auth_1b_{uuid.uuid4().hex[:8]}"
    url = f"{base}/{scratch}"
    with psycopg.connect(admin_url, autocommit=True) as admin:
        admin.execute(f'CREATE DATABASE "{scratch}"')  # nosemgrep — uuid-derived
    try:
        yield url
    finally:
        with psycopg.connect(admin_url, autocommit=True) as admin:
            admin.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname = %s AND pid <> pg_backend_pid()",
                (scratch,),
            )
            admin.execute(f'DROP DATABASE IF EXISTS "{scratch}"')  # nosemgrep


# ── Task 3: set_session_active_membership ────────────────────────────────────


def test_set_session_active_membership_happy_path(scratch_url: str) -> None:
    from dazzle.http.runtime.auth.store import AuthStore

    store = AuthStore(database_url=scratch_url)
    store._init_db()
    user = store.create_user(email="a@b.test", password="pw123456")
    uid = str(user.id)
    m = store.create_membership(tenant_id="t-1", identity_id=uid, roles=["admin"])
    session = store.create_session(user)  # no active membership yet

    ok = store.set_session_active_membership(session.id, m.id, identity_id=uid)
    assert ok is True
    ctx = store.validate_session(session.id)
    assert ctx.active_membership is not None
    assert ctx.active_membership.id == m.id


def test_set_session_active_membership_rejects_foreign_membership(scratch_url: str) -> None:
    from dazzle.http.runtime.auth.store import AuthStore

    store = AuthStore(database_url=scratch_url)
    store._init_db()
    user_a = store.create_user(email="a@b.test", password="pw123456")
    user_b = store.create_user(email="b@b.test", password="pw123456")
    m_b = store.create_membership(tenant_id="t-b", identity_id=str(user_b.id), roles=["admin"])
    session_a = store.create_session(user_a)

    # A must not be able to activate B's membership.
    ok = store.set_session_active_membership(session_a.id, m_b.id, identity_id=str(user_a.id))
    assert ok is False
    ctx = store.validate_session(session_a.id)
    assert ctx.active_membership is None


def test_set_session_active_membership_rejects_suspended(scratch_url: str) -> None:
    from dazzle.http.runtime.auth.store import AuthStore

    store = AuthStore(database_url=scratch_url)
    store._init_db()
    user = store.create_user(email="a@b.test", password="pw123456")
    uid = str(user.id)
    m = store.create_membership(
        tenant_id="t-1", identity_id=uid, roles=["admin"], status="suspended"
    )
    session = store.create_session(user)

    ok = store.set_session_active_membership(session.id, m.id, identity_id=uid)
    assert ok is False


# ── Task 4: activation at password login / signup ────────────────────────────


def _app_with_store(store):
    """Minimal FastAPI app wiring the password-login router to `store`."""
    from fastapi import FastAPI

    from dazzle.http.runtime.auth.password_login_routes import (
        create_password_login_routes,
    )

    app = FastAPI()
    app.state.auth_store = store
    app.state.auth_password_mode_enabled = True
    app.include_router(create_password_login_routes())
    return app


def _client(app):
    from fastapi.testclient import TestClient

    return TestClient(app, follow_redirects=False)


def test_password_login_single_membership_auto_activates(scratch_url: str) -> None:
    from dazzle.http.runtime.auth.store import AuthStore

    store = AuthStore(database_url=scratch_url)
    store._init_db()
    user = store.create_user(email="solo@b.test", password="pw123456")
    store.create_membership(tenant_id="t-1", identity_id=str(user.id), roles=["admin"])

    resp = _client(_app_with_store(store)).post(
        "/auth/login/password", data={"email": "solo@b.test", "password": "pw123456"}
    )
    assert resp.status_code == 303
    sid = resp.cookies.get("dazzle_session")
    assert sid is not None
    ctx = store.validate_session(sid)
    assert ctx.active_membership is not None
    assert ctx.active_membership.tenant_id == "t-1"
    assert resp.headers["location"] == "/app"


def test_password_login_multi_membership_redirects_to_picker(scratch_url: str) -> None:
    from dazzle.http.runtime.auth.store import AuthStore

    store = AuthStore(database_url=scratch_url)
    store._init_db()
    user = store.create_user(email="multi@b.test", password="pw123456")
    store.create_membership(tenant_id="t-1", identity_id=str(user.id), roles=["admin"])
    store.create_membership(tenant_id="t-2", identity_id=str(user.id), roles=["member"])

    resp = _client(_app_with_store(store)).post(
        "/auth/login/password", data={"email": "multi@b.test", "password": "pw123456"}
    )
    assert resp.status_code == 303
    assert resp.headers["location"] == "/auth/select-org"
    sid = resp.cookies.get("dazzle_session")
    ctx = store.validate_session(sid)
    assert ctx.active_membership is None  # not yet chosen


def test_password_login_no_membership_proceeds_by_default(scratch_url: str) -> None:
    """Pre-1c transition: a zero-membership identity logs in to a membership-less
    session and proceeds normally (legacy fence). No /auth/no-orgs interception
    until the app opts into the membership model."""
    from dazzle.http.runtime.auth.store import AuthStore

    store = AuthStore(database_url=scratch_url)
    store._init_db()
    store.create_user(email="orphan@b.test", password="pw123456")

    resp = _client(_app_with_store(store)).post(
        "/auth/login/password", data={"email": "orphan@b.test", "password": "pw123456"}
    )
    assert resp.status_code == 303
    assert resp.headers["location"] == "/app"
    sid = resp.cookies.get("dazzle_session")
    ctx = store.validate_session(sid)
    assert ctx.active_membership is None


def test_password_login_no_membership_redirects_to_no_orgs_when_required(scratch_url: str) -> None:
    """When the app opts into memberships (Plan 1c gate), a zero-membership
    identity is routed to the "no orgs yet" page."""
    from dazzle.http.runtime.auth.store import AuthStore

    store = AuthStore(database_url=scratch_url)
    store._init_db()
    store.create_user(email="orphan@b.test", password="pw123456")

    app = _app_with_store(store)
    app.state.memberships_required = True
    resp = _client(app).post(
        "/auth/login/password", data={"email": "orphan@b.test", "password": "pw123456"}
    )
    assert resp.status_code == 303
    assert resp.headers["location"] == "/auth/no-orgs"


# ── Task 7: org-context routes (select / switch / no-orgs) ───────────────────


def _app_with_org_routes(store):
    from fastapi import FastAPI

    from dazzle.http.runtime.auth.org_context_routes import create_org_context_routes

    app = FastAPI()
    app.state.auth_store = store
    app.state.auth_password_mode_enabled = True
    app.include_router(create_org_context_routes())
    return app


def _login_session(store, email: str, n_orgs: int) -> tuple[str, str, list[str]]:
    """Create a user + n memberships + a session with no active membership."""
    user = store.create_user(email=email, password="pw123456")
    mids = [
        store.create_membership(tenant_id=f"t-{i}", identity_id=str(user.id), roles=["member"]).id
        for i in range(n_orgs)
    ]
    session = store.create_session(user)
    return session.id, str(user.id), mids


def test_select_org_post_activates_owned_membership(scratch_url: str) -> None:
    from dazzle.http.runtime.auth.store import AuthStore

    store = AuthStore(database_url=scratch_url)
    store._init_db()
    sid, _uid, mids = _login_session(store, "multi@b.test", 2)
    client = _client(_app_with_org_routes(store))
    client.cookies.set("dazzle_session", sid)

    resp = client.post("/auth/select-org", data={"membership_id": mids[1]})
    assert resp.status_code == 303
    ctx = store.validate_session(sid)
    assert ctx.active_membership is not None
    assert ctx.active_membership.id == mids[1]


def test_switch_org_rotates_active_membership_and_csrf(scratch_url: str) -> None:
    from dazzle.http.runtime.auth.store import AuthStore

    store = AuthStore(database_url=scratch_url)
    store._init_db()
    sid, uid, mids = _login_session(store, "multi@b.test", 2)
    assert store.set_session_active_membership(sid, mids[0], identity_id=uid)
    csrf_before = store.get_session(sid).csrf_secret
    client = _client(_app_with_org_routes(store))
    client.cookies.set("dazzle_session", sid)

    resp = client.post("/auth/switch-org", data={"membership_id": mids[1]})
    assert resp.status_code == 303
    ctx = store.validate_session(sid)
    assert ctx.active_membership.id == mids[1]
    assert store.get_session(sid).csrf_secret != csrf_before  # CSRF rotated


def test_select_org_rejects_unowned_membership(scratch_url: str) -> None:
    from dazzle.http.runtime.auth.store import AuthStore

    store = AuthStore(database_url=scratch_url)
    store._init_db()
    sid_a, _uid_a, _ = _login_session(store, "a@b.test", 1)
    _sid_b, _uid_b, mids_b = _login_session(store, "b@b.test", 1)
    client = _client(_app_with_org_routes(store))
    client.cookies.set("dazzle_session", sid_a)

    # A tries to activate B's membership → rejected, session A unchanged.
    resp = client.post("/auth/select-org", data={"membership_id": mids_b[0]})
    assert resp.status_code in (303, 403)
    ctx = store.validate_session(sid_a)
    assert ctx.active_membership is None


def test_org_context_routes_are_mountable() -> None:
    """The router exposes the four Phase-2 paths (no DB needed)."""
    from dazzle.http.runtime.auth.org_context_routes import create_org_context_routes

    paths = {r.path for r in create_org_context_routes().routes}
    assert {"/auth/select-org", "/auth/switch-org", "/auth/no-orgs"} <= paths


# ── Task 11: host-pin activation keystone ────────────────────────────────────


def test_host_pin_activates_matching_org_and_403s_on_mismatch(scratch_url: str) -> None:
    from types import SimpleNamespace

    from dazzle.http.runtime.auth.org_activation import (
        Activated,
        HostForbidden,
        activate_session_for_login,
    )
    from dazzle.http.runtime.auth.store import AuthStore

    store = AuthStore(database_url=scratch_url)
    store._init_db()
    user = store.create_user(email="multi@b.test", password="pw123456")
    store.create_membership(tenant_id="t-A", identity_id=str(user.id), roles=["admin"])
    store.create_membership(tenant_id="t-B", identity_id=str(user.id), roles=["member"])

    def _req(tenant_id):
        tenant = SimpleNamespace(id=tenant_id, slug=tenant_id) if tenant_id else None
        return SimpleNamespace(state=SimpleNamespace(tenant=tenant))

    # Host-pinned to t-B → activates the t-B membership only.
    out_b = activate_session_for_login(store, user, _req("t-B"))
    assert isinstance(out_b, Activated)
    assert store.get_membership(out_b.membership_id).tenant_id == "t-B"

    # Host-pinned to an org the user isn't in → forbidden.
    assert isinstance(activate_session_for_login(store, user, _req("t-UNKNOWN")), HostForbidden)


def test_host_pin_uuid_discriminator_round_trips(scratch_url: str) -> None:
    """MEDIUM-1 invariant guard (review): the host-pin matches a membership whose
    `tenant_id` is `str(ResolvedTenant.id)` for a real UUID-shaped org id. This
    pins the format contract so Plan 1c can't drift `membership.tenant_id` away
    from `str(tenant_root.id)` undetected."""
    from types import SimpleNamespace
    from uuid import uuid4

    from dazzle.http.runtime.auth.org_activation import (
        Activated,
        activate_session_for_login,
    )
    from dazzle.http.runtime.auth.store import AuthStore

    store = AuthStore(database_url=scratch_url)
    store._init_db()
    org_id = uuid4()  # the tenant-root row id (Organization IS the tenant root)
    user = store.create_user(email="u@b.test", password="pw123456")
    m = store.create_membership(tenant_id=str(org_id), identity_id=str(user.id), roles=["admin"])

    # The host resolver yields ResolvedTenant(id=org_id) — psycopg's str(UUID).
    req = SimpleNamespace(state=SimpleNamespace(tenant=SimpleNamespace(id=org_id, slug="acme")))
    out = activate_session_for_login(store, user, req)
    assert isinstance(out, Activated)
    assert out.membership_id == m.id


# ── #1518: cross-tenant guard reads the REAL active-membership binding ────────


def _guard_request(
    *, app_name: str, tenant_id: object | None, super_admin_role: str = "super_admin"
):
    """Stub request carrying the app's host session cookie + a resolved tenant.

    Mirrors the shape `enforce_cross_tenant` reads: `app.state.tenant_host`
    (marker), the `__Host-<app>` cookie, and `request.state.tenant`.
    """
    from types import SimpleNamespace

    from dazzle.http.runtime.tenant.cookies import host_cookie_name

    tenant = (
        SimpleNamespace(id=tenant_id, slug="acme", ancestor_ids=())
        if tenant_id is not None
        else None
    )
    tenant_state = SimpleNamespace(
        app_name=app_name,
        canonical_hosts=frozenset({"app.example.com"}),
        super_admin_role=super_admin_role,
    )
    return SimpleNamespace(
        cookies={host_cookie_name(app_name): "sid"},
        state=SimpleNamespace(tenant=tenant),
        app=SimpleNamespace(state=SimpleNamespace(tenant_host=tenant_state)),
    )


def test_cross_tenant_guard_reads_real_membership_binding(scratch_url: str) -> None:
    """#1518 end-to-end: a session's tenant binding is its active membership's
    `tenant_id` (as returned by `validate_session`), and `enforce_cross_tenant`
    compares it to the resolved host id. This would FAIL against the old
    `user.tenant_slug` source (always None → fail-closed 403 on the *matching*
    host), so it pins the regression the magic-link QA sessions surfaced."""
    from uuid import uuid4

    from fastapi import HTTPException

    from dazzle.http.runtime.auth.store import AuthStore
    from dazzle.http.runtime.tenant.guard_wiring import enforce_cross_tenant

    store = AuthStore(database_url=scratch_url)
    store._init_db()
    org_id = uuid4()
    user = store.create_user(email="member@b.test", password="pw123456")
    m = store.create_membership(tenant_id=str(org_id), identity_id=str(user.id), roles=["admin"])
    session = store.create_session(user, active_membership_id=m.id)

    ctx = store.validate_session(session.id)
    assert ctx.active_membership is not None
    assert ctx.active_membership.tenant_id == str(org_id)

    # Matching host → PASS (no exception raised).
    enforce_cross_tenant(_guard_request(app_name="AegisMark", tenant_id=org_id), ctx)

    # A different tenant host → 403.
    with pytest.raises(HTTPException) as exc:
        enforce_cross_tenant(_guard_request(app_name="AegisMark", tenant_id=uuid4()), ctx)
    assert exc.value.status_code == 403


def test_cross_tenant_guard_fails_closed_without_membership(scratch_url: str) -> None:
    """#1518: a host-cookie session with no active membership fails closed (403).

    Every membership-gated `tenant_host:` login binds a membership, so this only
    rejects the unexercised `membership_gated: false` path — the deliberate
    fail-closed choice for this security guard."""
    from uuid import uuid4

    from fastapi import HTTPException

    from dazzle.http.runtime.auth.store import AuthStore
    from dazzle.http.runtime.tenant.guard_wiring import enforce_cross_tenant

    store = AuthStore(database_url=scratch_url)
    store._init_db()
    user = store.create_user(email="orphan@b.test", password="pw123456")
    session = store.create_session(user)  # no active membership

    ctx = store.validate_session(session.id)
    assert ctx.active_membership is None

    with pytest.raises(HTTPException) as exc:
        enforce_cross_tenant(_guard_request(app_name="AegisMark", tenant_id=uuid4()), ctx)
    assert exc.value.status_code == 403
