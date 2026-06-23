"""Real-PostgreSQL proof of the membership substrate (auth Plan 1a).

Marked e2e + postgres: skipped without TEST_DATABASE_URL/DATABASE_URL; CI's
postgres-tests job runs it. Mirrors tests/integration/test_rls_apply_and_drift_pg.py.

The auth tables (`users`/`sessions`) live in `AuthStore._init_db` (raw SQL), not
the Alembic chain — so the migration test (Task 3) only proves the migration's
own create-path + chain validity, while the column-shape assertions live on the
`_init_db` path (Task 4). The keystone (last test) proves a session's active
membership drives the RLS tenant binding end-to-end.
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
    """A fresh scratch database, dropped after the test."""
    if not _PG_URL:
        pytest.skip("no TEST_DATABASE_URL/DATABASE_URL")
    admin_url = _admin_url()
    base, _, _old = admin_url.rpartition("/")
    scratch = f"dazzle_auth_1a_{uuid.uuid4().hex[:8]}"
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


def _columns(url: str, table: str) -> set[str]:
    with psycopg.connect(url) as conn:
        rows = conn.execute(
            "SELECT column_name FROM information_schema.columns WHERE table_name = %s",
            (table,),
        ).fetchall()
    return {r[0] for r in rows}


def _seed_user(store, email: str = "a@b.test") -> str:
    """Create a user via the real store API and return its id (str)."""
    user = store.create_user(email=email, password="pw-12345")
    return str(user.id)


# -- Task 4: the _init_db dev path -------------------------------------------


def test_init_db_creates_memberships_and_active_membership_col(scratch_url: str) -> None:
    """The dev `_init_db` path creates the full shape (memberships +
    sessions.active_membership_id), interchangeable with migration 0007."""
    from dazzle.http.runtime.auth.store import AuthStore

    store = AuthStore(database_url=scratch_url)
    store._init_db()

    mcols = _columns(scratch_url, "memberships")
    assert {"id", "tenant_id", "identity_id", "roles", "status", "invited_by"} <= mcols
    assert "active_membership_id" in _columns(scratch_url, "sessions")


# -- Task 5: membership CRUD --------------------------------------------------


def test_membership_crud_round_trip(scratch_url: str) -> None:
    from dazzle.http.runtime.auth.store import AuthStore

    store = AuthStore(database_url=scratch_url)
    store._init_db()
    uid = _seed_user(store)

    created = store.create_membership(tenant_id="t-1", identity_id=uid, roles=["admin", "member"])
    assert created.tenant_id == "t-1"
    assert created.roles == ["admin", "member"]
    assert created.status == "active"

    got = store.get_membership(created.id)
    assert got is not None
    assert got.identity_id == uid
    assert got.roles == ["admin", "member"]

    listed = store.get_memberships_for_identity(uid)
    assert [m.id for m in listed] == [created.id]

    # The (tenant_id, identity_id) uniqueness holds.
    with pytest.raises(psycopg.errors.UniqueViolation):
        store.create_membership(tenant_id="t-1", identity_id=uid, roles=[])


# -- Task 6: create_session persists active_membership_id --------------------


def test_create_session_persists_active_membership_id(scratch_url: str) -> None:
    from dazzle.http.runtime.auth.store import AuthStore

    store = AuthStore(database_url=scratch_url)
    store._init_db()
    uid = _seed_user(store)
    user = store.get_user_by_id(uuid.UUID(uid))
    assert user is not None
    m = store.create_membership(tenant_id="t-1", identity_id=uid, roles=["admin"])

    session = store.create_session(user, active_membership_id=m.id)
    assert session.active_membership_id == m.id

    row = store._execute_one(
        "SELECT active_membership_id FROM sessions WHERE id = %s", (session.id,)
    )
    assert row is not None and row["active_membership_id"] == m.id


# -- Task 7: validate_session resolves the active membership -----------------


def test_validate_session_populates_active_membership(scratch_url: str) -> None:
    from dazzle.http.runtime.auth.store import AuthStore

    store = AuthStore(database_url=scratch_url)
    store._init_db()
    uid = _seed_user(store)
    user = store.get_user_by_id(uuid.UUID(uid))
    assert user is not None
    m = store.create_membership(tenant_id="t-1", identity_id=uid, roles=["admin"])
    session = store.create_session(user, active_membership_id=m.id)

    ctx = store.validate_session(session.id)
    assert ctx.is_authenticated
    assert ctx.active_membership is not None
    assert ctx.active_membership.id == m.id
    assert ctx.active_membership.tenant_id == "t-1"
    assert ctx.effective_roles == ["admin"]


def test_suspended_membership_does_not_source_the_fence(scratch_url: str) -> None:
    """A non-active membership must NOT scope the session (security: a suspended
    user stops seeing the org's data). validate_session drops it to None."""
    from dazzle.http.runtime.auth.store import AuthStore

    store = AuthStore(database_url=scratch_url)
    store._init_db()
    uid = _seed_user(store)
    user = store.get_user_by_id(uuid.UUID(uid))
    assert user is not None
    m = store.create_membership(
        tenant_id="t-1", identity_id=uid, roles=["admin"], status="suspended"
    )
    session = store.create_session(user, active_membership_id=m.id)

    ctx = store.validate_session(session.id)
    assert ctx.is_authenticated
    assert ctx.active_membership is None  # suspended → not sourced


def test_create_membership_rejects_unknown_identity(scratch_url: str) -> None:
    """No DB FK to users → create_membership guards against orphan memberships."""
    from dazzle.http.runtime.auth.store import AuthStore

    store = AuthStore(database_url=scratch_url)
    store._init_db()
    with pytest.raises(ValueError, match="no user with id"):
        store.create_membership(tenant_id="t-1", identity_id=str(uuid.uuid4()), roles=[])


def test_validate_session_no_membership_is_backward_compatible(scratch_url: str) -> None:
    """A session with no active membership still authenticates (legacy path)."""
    from dazzle.http.runtime.auth.store import AuthStore

    store = AuthStore(database_url=scratch_url)
    store._init_db()
    uid = _seed_user(store)
    user = store.get_user_by_id(uuid.UUID(uid))
    assert user is not None
    session = store.create_session(user)  # no active_membership_id

    ctx = store.validate_session(session.id)
    assert ctx.is_authenticated
    assert ctx.active_membership is None


# -- Task 9: keystone — membership drives the tenant binding -----------------


def test_membership_drives_tenant_binding_end_to_end(scratch_url: str) -> None:
    """DB membership -> validate_session -> _bind_rls_tenant_id sets the tenant
    contextvar to the membership's tenant_id (which pg_backend reads to set the
    `dazzle.tenant_id` GUC; fence enforcement is proven in test_rls_enforcement_pg)."""
    from dazzle.http.runtime import tenant_isolation
    from dazzle.http.runtime.auth.dependencies import _bind_rls_tenant_id
    from dazzle.http.runtime.auth.store import AuthStore

    store = AuthStore(database_url=scratch_url)
    store._init_db()
    uid = _seed_user(store)
    user = store.get_user_by_id(uuid.UUID(uid))
    assert user is not None
    m = store.create_membership(tenant_id="tenant-A", identity_id=uid, roles=["admin"])
    session = store.create_session(user, active_membership_id=m.id)
    ctx = store.validate_session(session.id)

    set_token = tenant_isolation.set_current_tenant_id("")  # reset to a known value
    try:
        _bind_rls_tenant_id(ctx)
        assert tenant_isolation.get_current_tenant_id() == "tenant-A"
        assert ctx.effective_roles == ["admin"]
    finally:
        tenant_isolation._current_tenant_id.reset(set_token)
