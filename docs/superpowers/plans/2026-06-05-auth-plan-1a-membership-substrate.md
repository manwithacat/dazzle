# Auth Plan 1a — Membership Substrate + Fence-from-Membership Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Introduce a framework-owned `memberships` table (user × org × roles) in the auth store and make the RLS tenant fence source its `dazzle.tenant_id` from a session's *active membership* instead of the brittle preferences-copy — the keystone foundation of the new auth/identity model.

**Architecture:** `memberships` lives in the **auth-store** raw-SQL world (alongside `users`/`sessions`), not the IR-entity pipeline, because it must JOIN `users.id` and be read in the per-request `validate_session` hot path. `sessions` gains a nullable `active_membership_id`. `validate_session` resolves the active membership onto `AuthContext`; `_bind_rls_tenant_id` reads `tenant_id` + roles from that membership when present, **falling back to today's preferences path** when absent — so existing apps keep working until later slices (1b–1d) migrate them. RLS *on the memberships table itself* is deferred; its Plan-1a job is to be the **source** of the fence value for the domain tables.

**Tech Stack:** Python 3.12, Pydantic v2 (frozen models), psycopg3 (raw SQL, `%s` params), Alembic (ADR-0017), pytest (+ `pytest.mark.postgres` integration tests against real PostgreSQL).

---

## Scope

**In scope (Plan 1a):** the `memberships` table + `MembershipRecord` + store CRUD; `sessions.active_membership_id`; `validate_session` resolving the active membership; `_bind_rls_tenant_id` + `AuthContext.roles` sourced from the active membership with a preferences fallback; an Alembic migration; a real-PG keystone proof that an active membership binds the fence.

**Out of scope (later slices):** two-phase login/activation + org-context resolution (1b), single-org auto-provision + graceful degradation (1c), repo app/fixture migration + retiring the preferences-indirection (1d), RLS *on* the memberships table, multi-org UX, enterprise connections, compliance-evidence emission.

## File Structure

| File | Responsibility | Change |
|---|---|---|
| `src/dazzle/http/runtime/auth/models.py` | Pydantic records + `AuthContext` | **Modify** — add `MembershipRecord`; add `active_membership` to `AuthContext`; membership-sourced `roles` |
| `src/dazzle/http/runtime/auth/store.py` | Raw-SQL auth store | **Modify** — `memberships` DDL + `sessions.active_membership_id` in `_init_db`; CRUD; `create_session`/`validate_session` |
| `src/dazzle/http/runtime/auth/dependencies.py` | Per-request RLS binding | **Modify** — `_bind_rls_tenant_id` reads active membership first |
| `src/dazzle/http/alembic/versions/0007_memberships.py` | Schema migration | **Create** — `memberships` table + `sessions.active_membership_id` |
| `tests/unit/test_auth_membership_model.py` | Pure-model tests | **Create** |
| `tests/unit/test_bind_rls_from_membership.py` | Bind-logic unit test | **Create** |
| `tests/integration/test_auth_membership_pg.py` | Real-PG store + migration + keystone proof | **Create** |

---

## Task 1: `MembershipRecord` model

**Files:**
- Modify: `src/dazzle/http/runtime/auth/models.py`
- Test: `tests/unit/test_auth_membership_model.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_auth_membership_model.py
"""MembershipRecord model (auth Plan 1a)."""

from dazzle.http.runtime.auth.models import MembershipRecord


class TestMembershipRecord:
    def test_minimal_construction_defaults(self) -> None:
        m = MembershipRecord(
            id="m-1",
            tenant_id="t-1",
            identity_id="u-1",
        )
        assert m.id == "m-1"
        assert m.tenant_id == "t-1"
        assert m.identity_id == "u-1"
        assert m.roles == []
        assert m.status == "active"
        assert m.invited_by is None

    def test_roles_and_status_round_trip(self) -> None:
        m = MembershipRecord(
            id="m-2",
            tenant_id="t-1",
            identity_id="u-1",
            roles=["admin", "member"],
            status="invited",
            invited_by="u-9",
        )
        assert m.roles == ["admin", "member"]
        assert m.status == "invited"
        assert m.invited_by == "u-9"

    def test_is_frozen(self) -> None:
        import pytest
        from pydantic import ValidationError

        m = MembershipRecord(id="m-3", tenant_id="t-1", identity_id="u-1")
        with pytest.raises(ValidationError):
            m.status = "suspended"  # type: ignore[misc]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_auth_membership_model.py -q`
Expected: FAIL — `ImportError: cannot import name 'MembershipRecord'`.

- [ ] **Step 3: Add the model**

In `src/dazzle/http/runtime/auth/models.py`, after the `SessionRecord` class, add:

```python
class MembershipRecord(BaseModel):
    """A user's membership in one organization (auth Plan 1a).

    The fenced join between a global ``Identity`` (``users`` row) and an
    ``Organization`` (tenant root). ``tenant_id`` is the discriminator value the
    RLS fence reads as ``dazzle.tenant_id``; ``roles`` are the personas this
    identity holds *in this org* (replacing the global ``users.roles`` source).
    """

    model_config = ConfigDict(frozen=True)

    id: str
    tenant_id: str
    identity_id: str
    roles: list[str] = Field(default_factory=list)
    status: str = "active"
    invited_by: str | None = None
    joined_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
```

(`BaseModel`, `ConfigDict`, `Field`, `datetime`, `UTC` are already imported at the top of `models.py` — verify; if `UTC`/`datetime` are missing, they are already used by `UserRecord`/`SessionRecord`, so they are present.)

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_auth_membership_model.py -q`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/http/runtime/auth/models.py tests/unit/test_auth_membership_model.py
git commit -m "feat(auth): MembershipRecord model (Plan 1a)"
```

---

## Task 2: `AuthContext.active_membership` + membership-sourced roles

**Files:**
- Modify: `src/dazzle/http/runtime/auth/models.py` (the `AuthContext` class)
- Test: `tests/unit/test_auth_membership_model.py` (append)

- [ ] **Step 1: Write the failing test (append to the existing file)**

```python
# append to tests/unit/test_auth_membership_model.py
from dazzle.http.runtime.auth.models import AuthContext, UserRecord


class TestAuthContextActiveMembership:
    def _user(self) -> UserRecord:
        return UserRecord(email="a@b.test", password_hash="x", roles=["legacy_role"])

    def test_active_membership_defaults_none(self) -> None:
        ctx = AuthContext(user=self._user(), is_authenticated=True, roles=["legacy_role"])
        assert ctx.active_membership is None
        # With no membership, effective roles are whatever was set (legacy path).
        assert ctx.effective_roles == ["legacy_role"]

    def test_effective_roles_prefer_membership(self) -> None:
        m = MembershipRecord(id="m-1", tenant_id="t-1", identity_id="u-1", roles=["admin"])
        ctx = AuthContext(
            user=self._user(),
            is_authenticated=True,
            roles=["legacy_role"],
            active_membership=m,
        )
        # The active membership's roles override the legacy user-sourced roles.
        assert ctx.effective_roles == ["admin"]

    def test_effective_roles_unauthenticated_empty(self) -> None:
        assert AuthContext().effective_roles == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_auth_membership_model.py -q`
Expected: FAIL — `AuthContext` has no `active_membership` / `effective_roles`.

- [ ] **Step 3: Extend `AuthContext`**

In `src/dazzle/http/runtime/auth/models.py`, modify the `AuthContext` class — add the field and property:

```python
class AuthContext(BaseModel):
    """Current authentication context."""

    user: UserRecord | None = None
    session: SessionRecord | None = None
    is_authenticated: bool = False
    roles: list[str] = Field(default_factory=list)
    permissions: list[str] = Field(default_factory=list)
    preferences: dict[str, str] = Field(default_factory=dict)
    active_membership: "MembershipRecord | None" = None  # auth Plan 1a

    @property
    def user_id(self) -> UUID | None:
        """Get the authenticated user's ID, or None if not authenticated."""
        return self.user.id if self.user else None

    @property
    def effective_roles(self) -> list[str]:
        """Roles in effect for this request.

        Sourced from the active membership when present (the new per-org model);
        otherwise the legacy ``roles`` (global user roles) — the transition
        fallback until later slices migrate every app onto memberships.
        """
        if not self.is_authenticated:
            return []
        if self.active_membership is not None:
            return list(self.active_membership.roles)
        return list(self.roles)
```

Note: `MembershipRecord` is defined later in the file, so the annotation is a forward reference string `"MembershipRecord | None"`. If `AuthContext` is defined *before* `MembershipRecord`, add `MembershipRecord` to a `model_rebuild()` call at the end of the module:

```python
# at the very bottom of models.py, after all classes:
AuthContext.model_rebuild()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_auth_membership_model.py -q`
Expected: PASS (6 passed).

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/http/runtime/auth/models.py tests/unit/test_auth_membership_model.py
git commit -m "feat(auth): AuthContext.active_membership + effective_roles (Plan 1a)"
```

---

## Task 3: Alembic migration `0007_memberships`

**Files:**
- Create: `src/dazzle/http/alembic/versions/0007_memberships.py`
- Test: `tests/integration/test_auth_membership_pg.py`

- [ ] **Step 1: Write the failing integration test (with the shared scratch-DB harness)**

```python
# tests/integration/test_auth_membership_pg.py
"""Real-PostgreSQL proof of the membership substrate (auth Plan 1a).

Marked e2e + postgres: skipped without TEST_DATABASE_URL/DATABASE_URL; CI's
postgres-tests job runs it. Mirrors tests/integration/test_rls_apply_and_drift_pg.py.
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


def test_migration_0007_creates_memberships_and_active_membership_col(scratch_url: str) -> None:
    """`alembic upgrade head` creates `memberships` and adds
    `sessions.active_membership_id`."""
    from alembic import command
    from alembic.config import Config

    from dazzle.http.alembic import alembic_ini_path  # existing helper

    # Stand up the prior framework tables (users/sessions) the way the runtime does,
    # then run migrations to head.
    from dazzle.http.runtime.auth.store import AuthStore

    store = AuthStore(database_url=scratch_url)
    store._init_db()  # creates users/sessions baseline so FKs resolve

    cfg = Config(str(alembic_ini_path()))
    cfg.set_main_option("sqlalchemy.url", scratch_url.replace("postgresql://", "postgresql+psycopg://"))
    command.upgrade(cfg, "head")

    assert "memberships" in _columns(scratch_url, "memberships") or _columns(scratch_url, "memberships")
    mcols = _columns(scratch_url, "memberships")
    assert {"id", "tenant_id", "identity_id", "roles", "status"} <= mcols
    assert "active_membership_id" in _columns(scratch_url, "sessions")
```

> If `dazzle.http.alembic.alembic_ini_path` does not exist, replace the Config construction with the project's standard way of locating `alembic.ini` (grep `Config(` under `src/dazzle/cli/db.py` for the canonical pattern and mirror it). The assertion content does not change.

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/integration/test_auth_membership_pg.py -q` (with `DATABASE_URL` set to a reachable Postgres superuser URL)
Expected: FAIL — migration head has no `memberships`/`active_membership_id` (or `KeyError`/empty column set).

- [ ] **Step 3: Write the migration**

```python
# src/dazzle/http/alembic/versions/0007_memberships.py
"""Add memberships table + sessions.active_membership_id (auth Plan 1a).

The framework gains a `memberships` join (identity x org x roles) — the fenced
source of the RLS `dazzle.tenant_id`. `sessions` gains a nullable
`active_membership_id` pinning the session's active org. Idempotent: guards on
table/column presence so the dev `_init_db` create path and this migration are
interchangeable.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect as sa_inspect

revision = "0007_memberships"
down_revision = "0006_tenant_is_test"
branch_labels = None
depends_on = None


def _has_table(table: str) -> bool:
    return sa_inspect(op.get_bind()).has_table(table)


def _has_column(table: str, column: str) -> bool:
    bind = op.get_bind()
    insp = sa_inspect(bind)
    if not insp.has_table(table):
        return False
    return any(c["name"] == column for c in insp.get_columns(table))


def upgrade() -> None:
    if not _has_table("memberships"):
        op.create_table(
            "memberships",
            sa.Column("id", sa.Text(), primary_key=True),
            sa.Column("tenant_id", sa.Text(), nullable=False),
            sa.Column(
                "identity_id",
                sa.Text(),
                sa.ForeignKey("users.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("roles", sa.Text(), nullable=False, server_default=sa.text("'[]'")),
            sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'active'")),
            sa.Column("invited_by", sa.Text(), nullable=True),
            sa.Column("joined_at", sa.Text(), nullable=False),
            sa.Column("created_at", sa.Text(), nullable=False),
            sa.Column("updated_at", sa.Text(), nullable=False),
            sa.UniqueConstraint("tenant_id", "identity_id", name="uq_memberships_tenant_identity"),
        )
        op.create_index("ix_memberships_identity_id", "memberships", ["identity_id"])
        op.create_index("ix_memberships_tenant_id", "memberships", ["tenant_id"])

    if _has_table("sessions") and not _has_column("sessions", "active_membership_id"):
        op.add_column(
            "sessions",
            sa.Column("active_membership_id", sa.Text(), nullable=True),
        )


def downgrade() -> None:
    if _has_column("sessions", "active_membership_id"):
        op.drop_column("sessions", "active_membership_id")
    if _has_table("memberships"):
        op.drop_table("memberships")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/integration/test_auth_membership_pg.py::test_migration_0007_creates_memberships_and_active_membership_col -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/http/alembic/versions/0007_memberships.py tests/integration/test_auth_membership_pg.py
git commit -m "feat(auth): alembic 0007 — memberships + sessions.active_membership_id (Plan 1a)"
```

---

## Task 4: `_init_db` DDL parity (dev create path)

**Files:**
- Modify: `src/dazzle/http/runtime/auth/store.py` (the `_init_db` method)
- Test: `tests/integration/test_auth_membership_pg.py` (append)

- [ ] **Step 1: Write the failing test (append)**

```python
# append to tests/integration/test_auth_membership_pg.py
def test_init_db_creates_memberships_and_active_membership_col(scratch_url: str) -> None:
    """The dev `_init_db` path creates the same shape as migration 0007
    (so create-all and migrate are interchangeable)."""
    from dazzle.http.runtime.auth.store import AuthStore

    store = AuthStore(database_url=scratch_url)
    store._init_db()

    mcols = _columns(scratch_url, "memberships")
    assert {"id", "tenant_id", "identity_id", "roles", "status", "invited_by"} <= mcols
    assert "active_membership_id" in _columns(scratch_url, "sessions")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/integration/test_auth_membership_pg.py::test_init_db_creates_memberships_and_active_membership_col -q`
Expected: FAIL — `memberships` not created by `_init_db`.

- [ ] **Step 3: Add the DDL to `_init_db`**

In `src/dazzle/http/runtime/auth/store.py`, inside `_init_db`, after the `sessions` table creation block (and its `csrf_secret` idempotent ALTER), add:

```python
        # auth Plan 1a: memberships (identity x org x roles) — the fenced source
        # of dazzle.tenant_id. Mirrors alembic 0007_memberships.
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS memberships (
                id TEXT PRIMARY KEY,
                tenant_id TEXT NOT NULL,
                identity_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                roles TEXT NOT NULL DEFAULT '[]',
                status TEXT NOT NULL DEFAULT 'active',
                invited_by TEXT,
                joined_at TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                CONSTRAINT uq_memberships_tenant_identity UNIQUE (tenant_id, identity_id)
            )
        """)
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS ix_memberships_identity_id ON memberships(identity_id)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS ix_memberships_tenant_id ON memberships(tenant_id)"
        )
        # sessions.active_membership_id — pins the active org for the session.
        try:
            cursor.execute(
                "ALTER TABLE sessions ADD COLUMN IF NOT EXISTS active_membership_id TEXT"
            )
        except Exception:
            logger.warning("Could not add sessions.active_membership_id", exc_info=True)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/integration/test_auth_membership_pg.py::test_init_db_creates_memberships_and_active_membership_col -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/http/runtime/auth/store.py tests/integration/test_auth_membership_pg.py
git commit -m "feat(auth): _init_db creates memberships + active_membership_id (Plan 1a)"
```

---

## Task 5: Membership CRUD on `AuthStore`

**Files:**
- Modify: `src/dazzle/http/runtime/auth/store.py`
- Test: `tests/integration/test_auth_membership_pg.py` (append)

- [ ] **Step 1: Write the failing test (append)**

```python
# append to tests/integration/test_auth_membership_pg.py
def _seed_user(store, email: str = "a@b.test") -> str:
    """Create a user row directly and return its id (str)."""
    from dazzle.http.runtime.auth.models import UserRecord

    user = UserRecord(email=email, password_hash="x")
    store.create_user(user)  # existing AuthStore method
    return str(user.id)


def test_membership_crud_round_trip(scratch_url: str) -> None:
    from dazzle.http.runtime.auth.store import AuthStore

    store = AuthStore(database_url=scratch_url)
    store._init_db()
    uid = _seed_user(store)

    created = store.create_membership(
        tenant_id="t-1", identity_id=uid, roles=["admin", "member"]
    )
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
    import pytest

    with pytest.raises(Exception):
        store.create_membership(tenant_id="t-1", identity_id=uid, roles=[])
```

> If `AuthStore.create_user` has a different name, grep `def create_user` / `def register` in `store.py` and use the actual one; the assertions don't change.

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/integration/test_auth_membership_pg.py::test_membership_crud_round_trip -q`
Expected: FAIL — `AuthStore` has no `create_membership`.

- [ ] **Step 3: Add CRUD + row mapper**

In `src/dazzle/http/runtime/auth/store.py`, add (near the session methods). Import `MembershipRecord` from `.models` at the top alongside the other model imports, and ensure `json`/`datetime`/`UTC` are imported (they already are — used by user roles + timestamps):

```python
    def _row_to_membership(self, row: dict[str, Any]) -> "MembershipRecord":
        import json

        return MembershipRecord(
            id=row["id"],
            tenant_id=row["tenant_id"],
            identity_id=row["identity_id"],
            roles=json.loads(row["roles"]) if row.get("roles") else [],
            status=row["status"],
            invited_by=row.get("invited_by"),
            joined_at=datetime.fromisoformat(row["joined_at"]),
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )

    def create_membership(
        self,
        *,
        tenant_id: str,
        identity_id: str,
        roles: list[str] | None = None,
        status: str = "active",
        invited_by: str | None = None,
    ) -> "MembershipRecord":
        """Create a membership (identity x org x roles)."""
        import json

        membership = MembershipRecord(
            id=secrets.token_urlsafe(24),
            tenant_id=tenant_id,
            identity_id=identity_id,
            roles=roles or [],
            status=status,
            invited_by=invited_by,
        )
        self._execute(
            """
            INSERT INTO memberships
                (id, tenant_id, identity_id, roles, status, invited_by,
                 joined_at, created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                membership.id,
                membership.tenant_id,
                membership.identity_id,
                json.dumps(membership.roles),
                membership.status,
                membership.invited_by,
                membership.joined_at.isoformat(),
                membership.created_at.isoformat(),
                membership.updated_at.isoformat(),
            ),
        )
        return membership

    def get_membership(self, membership_id: str) -> "MembershipRecord | None":
        row = self._execute_one("SELECT * FROM memberships WHERE id = %s", (membership_id,))
        return self._row_to_membership(row) if row else None

    def get_memberships_for_identity(self, identity_id: str) -> list["MembershipRecord"]:
        rows = self._execute(
            "SELECT * FROM memberships WHERE identity_id = %s ORDER BY created_at",
            (identity_id,),
        )
        return [self._row_to_membership(r) for r in rows]
```

`secrets` is already imported in `models.py`; in `store.py` confirm `import secrets` at the top (it is used for tokens elsewhere — if not present, add it).

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/integration/test_auth_membership_pg.py::test_membership_crud_round_trip -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/http/runtime/auth/store.py tests/integration/test_auth_membership_pg.py
git commit -m "feat(auth): AuthStore membership CRUD (Plan 1a)"
```

---

## Task 6: `create_session` accepts `active_membership_id`

**Files:**
- Modify: `src/dazzle/http/runtime/auth/models.py` (`SessionRecord`), `src/dazzle/http/runtime/auth/store.py` (`create_session`)
- Test: `tests/integration/test_auth_membership_pg.py` (append)

- [ ] **Step 1: Write the failing test (append)**

```python
# append to tests/integration/test_auth_membership_pg.py
def test_create_session_persists_active_membership_id(scratch_url: str) -> None:
    from dazzle.http.runtime.auth.store import AuthStore

    store = AuthStore(database_url=scratch_url)
    store._init_db()
    uid = _seed_user(store)
    user = store.get_user_by_id(uid)
    assert user is not None
    m = store.create_membership(tenant_id="t-1", identity_id=uid, roles=["admin"])

    session = store.create_session(user, active_membership_id=m.id)
    assert session.active_membership_id == m.id

    row = store._execute_one(
        "SELECT active_membership_id FROM sessions WHERE id = %s", (session.id,)
    )
    assert row["active_membership_id"] == m.id
```

> `get_user_by_id` may take a `UUID` — pass `uuid.UUID(uid)` if the signature requires it (grep `def get_user_by_id`). Adjust the single call; assertions unchanged.

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/integration/test_auth_membership_pg.py::test_create_session_persists_active_membership_id -q`
Expected: FAIL — `create_session` has no `active_membership_id`.

- [ ] **Step 3a: Add the field to `SessionRecord`**

In `src/dazzle/http/runtime/auth/models.py`, add to `SessionRecord`:

```python
    active_membership_id: str | None = None  # auth Plan 1a — pins the active org
```

- [ ] **Step 3b: Thread it through `create_session`**

In `src/dazzle/http/runtime/auth/store.py`, modify `create_session` — add the parameter, the `SessionRecord` field, and the INSERT column:

```python
    def create_session(
        self,
        user: UserRecord,
        expires_in: timedelta = timedelta(days=7),
        ip_address: str | None = None,
        user_agent: str | None = None,
        active_membership_id: str | None = None,  # auth Plan 1a
    ) -> SessionRecord:
        """Create a new session for a user."""
        session = SessionRecord(
            user_id=user.id,
            expires_at=datetime.now(UTC) + expires_in,
            ip_address=ip_address,
            user_agent=user_agent,
            active_membership_id=active_membership_id,
        )

        self._execute(
            """
            INSERT INTO sessions
                (id, user_id, created_at, expires_at, ip_address, user_agent,
                 csrf_secret, active_membership_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                session.id,
                str(session.user_id),
                session.created_at.isoformat(),
                session.expires_at.isoformat(),
                session.ip_address,
                session.user_agent,
                session.csrf_secret,
                session.active_membership_id,
            ),
        )
        return session
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/integration/test_auth_membership_pg.py::test_create_session_persists_active_membership_id -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/http/runtime/auth/models.py src/dazzle/http/runtime/auth/store.py tests/integration/test_auth_membership_pg.py
git commit -m "feat(auth): create_session persists active_membership_id (Plan 1a)"
```

---

## Task 7: `validate_session` resolves the active membership

**Files:**
- Modify: `src/dazzle/http/runtime/auth/store.py` (`validate_session`, and the `get_session`/`SessionRecord` hydration so it reads the new column)
- Test: `tests/integration/test_auth_membership_pg.py` (append)

- [ ] **Step 1: Write the failing test (append)**

```python
# append to tests/integration/test_auth_membership_pg.py
def test_validate_session_populates_active_membership(scratch_url: str) -> None:
    from dazzle.http.runtime.auth.store import AuthStore

    store = AuthStore(database_url=scratch_url)
    store._init_db()
    uid = _seed_user(store)
    user = store.get_user_by_id(uid)
    assert user is not None
    m = store.create_membership(tenant_id="t-1", identity_id=uid, roles=["admin"])
    session = store.create_session(user, active_membership_id=m.id)

    ctx = store.validate_session(session.id)
    assert ctx.is_authenticated
    assert ctx.active_membership is not None
    assert ctx.active_membership.id == m.id
    assert ctx.active_membership.tenant_id == "t-1"
    assert ctx.effective_roles == ["admin"]


def test_validate_session_no_membership_is_backward_compatible(scratch_url: str) -> None:
    """A session with no active membership still authenticates (legacy path)."""
    from dazzle.http.runtime.auth.store import AuthStore

    store = AuthStore(database_url=scratch_url)
    store._init_db()
    uid = _seed_user(store)
    user = store.get_user_by_id(uid)
    assert user is not None
    session = store.create_session(user)  # no active_membership_id

    ctx = store.validate_session(session.id)
    assert ctx.is_authenticated
    assert ctx.active_membership is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/integration/test_auth_membership_pg.py -k validate_session -q`
Expected: FAIL — `active_membership` is `None` even when the session pins one (the session row's `active_membership_id` isn't read / not resolved).

- [ ] **Step 3a: Hydrate `active_membership_id` in `get_session`**

In `src/dazzle/http/runtime/auth/store.py`, find the method that maps a `sessions` row to a `SessionRecord` (inside `get_session`). Add the field to the `SessionRecord(...)` construction:

```python
            active_membership_id=row.get("active_membership_id"),
```

- [ ] **Step 3b: Resolve the membership in `validate_session`**

In `validate_session`, after the user is loaded and before constructing the `AuthContext`, add:

```python
        # auth Plan 1a: resolve the session's active membership (if any).
        active_membership = None
        if session.active_membership_id:
            active_membership = self.get_membership(session.active_membership_id)
```

Then pass it into the returned `AuthContext`:

```python
        return AuthContext(
            user=user,
            session=session,
            is_authenticated=True,
            roles=user.roles,
            preferences=prefs,
            active_membership=active_membership,
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/integration/test_auth_membership_pg.py -k validate_session -q`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/http/runtime/auth/store.py tests/integration/test_auth_membership_pg.py
git commit -m "feat(auth): validate_session resolves active membership (Plan 1a)"
```

---

## Task 8: `_bind_rls_tenant_id` reads the active membership first

**Files:**
- Modify: `src/dazzle/http/runtime/auth/dependencies.py` (`_bind_rls_tenant_id`)
- Test: `tests/unit/test_bind_rls_from_membership.py`

- [ ] **Step 1: Write the failing unit test**

```python
# tests/unit/test_bind_rls_from_membership.py
"""_bind_rls_tenant_id sources the fence from the active membership (Plan 1a)."""

from unittest.mock import patch

from dazzle.http.runtime.auth.dependencies import _bind_rls_tenant_id
from dazzle.http.runtime.auth.models import AuthContext, MembershipRecord, UserRecord


def _ctx(active_membership=None, prefs=None) -> AuthContext:
    return AuthContext(
        user=UserRecord(email="a@b.test", password_hash="x"),
        is_authenticated=True,
        roles=[],
        preferences=prefs or {},
        active_membership=active_membership,
    )


def test_binds_tenant_id_from_active_membership() -> None:
    m = MembershipRecord(id="m-1", tenant_id="tenant-xyz", identity_id="u-1", roles=["admin"])
    with patch(
        "dazzle.http.runtime.tenant_isolation.set_current_tenant_id"
    ) as set_tid, patch(
        "dazzle.http.runtime.tenant_isolation.get_rls_user_attr_names", return_value=set()
    ):
        _bind_rls_tenant_id(_ctx(active_membership=m))
    set_tid.assert_called_once_with("tenant-xyz")


def test_falls_back_to_preferences_when_no_membership() -> None:
    with patch(
        "dazzle.http.runtime.tenant_isolation.set_current_tenant_id"
    ) as set_tid, patch(
        "dazzle.http.runtime.tenant_isolation.get_rls_user_attr_names", return_value=set()
    ):
        _bind_rls_tenant_id(_ctx(prefs={"tenant_id": "tenant-legacy"}))
    set_tid.assert_called_once_with("tenant-legacy")


def test_unauthenticated_binds_nothing() -> None:
    with patch("dazzle.http.runtime.tenant_isolation.set_current_tenant_id") as set_tid:
        _bind_rls_tenant_id(AuthContext())
    set_tid.assert_not_called()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_bind_rls_from_membership.py -q`
Expected: FAIL on `test_binds_tenant_id_from_active_membership` — the current implementation only reads `_resolve_user_attribute("tenant_id")` (preferences), so it would not bind `"tenant-xyz"`.

- [ ] **Step 3: Make the membership the primary source**

In `src/dazzle/http/runtime/auth/dependencies.py`, modify `_bind_rls_tenant_id` — replace the `tenant_id` resolution block (lines ~52-55) with a membership-first resolution:

```python
    # auth Plan 1a: prefer the active membership's tenant_id (the hard FK source);
    # fall back to the preferences-derived attribute for apps not yet on
    # memberships (transition path, removed in a later slice).
    if auth_context.active_membership is not None:
        tenant_id: str = auth_context.active_membership.tenant_id
    else:
        tenant_id = _resolve_user_attribute("tenant_id", auth_context)
    if isinstance(tenant_id, str) and tenant_id and tenant_id != "__RBAC_DENY__":
        set_current_tenant_id(tenant_id)
```

Leave the Phase C `user_attr_names` block below unchanged.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_bind_rls_from_membership.py -q`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/http/runtime/auth/dependencies.py tests/unit/test_bind_rls_from_membership.py
git commit -m "feat(auth): bind RLS tenant from active membership, prefs fallback (Plan 1a)"
```

---

## Task 9: Keystone proof — an active membership fences a domain query

**Files:**
- Test: `tests/integration/test_auth_membership_pg.py` (append)

This is the end-to-end proof that the substrate actually sources the fence: with `dazzle.tenant_id` bound from a membership, a fenced table only returns that tenant's rows.

- [ ] **Step 1: Write the failing test (append)**

```python
# append to tests/integration/test_auth_membership_pg.py
def test_membership_tenant_binds_fence_on_a_scoped_table(scratch_url: str) -> None:
    """With dazzle.tenant_id = membership.tenant_id, a restrictive RLS fence on a
    scoped table returns only that tenant's rows — the substrate's whole purpose."""
    # Build a minimal fenced table + fence policy by hand (mirrors the Phase B
    # fence shape) so this test is self-contained and does not depend on an app.
    ddl = [
        'CREATE TABLE "Note" (tenant_id TEXT NOT NULL, id TEXT PRIMARY KEY, body TEXT)',
        'ALTER TABLE "Note" ENABLE ROW LEVEL SECURITY',
        'ALTER TABLE "Note" FORCE ROW LEVEL SECURITY',
        "CREATE POLICY tenant_fence ON \"Note\" AS RESTRICTIVE FOR ALL "
        "USING (tenant_id = current_setting('dazzle.tenant_id', true)) "
        "WITH CHECK (tenant_id = current_setting('dazzle.tenant_id', true))",
        "INSERT INTO \"Note\" VALUES ('t-A', 'n1', 'a-note'), ('t-B', 'n2', 'b-note')",
    ]
    # Apply as a NON-owner-bypassing role: connect, create a role that is forced
    # by RLS. For simplicity use the current connection but FORCE RLS applies to
    # table owner too, so set the GUC and read.
    with psycopg.connect(scratch_url, autocommit=True) as conn:
        for stmt in ddl:
            conn.execute(stmt)  # nosemgrep — static test DDL

    from dazzle.http.runtime.auth.store import AuthStore

    store = AuthStore(database_url=scratch_url)
    store._init_db()
    uid = _seed_user(store)
    user = store.get_user_by_id(uid)
    assert user is not None
    m = store.create_membership(tenant_id="t-A", identity_id=uid, roles=[])
    session = store.create_session(user, active_membership_id=m.id)
    ctx = store.validate_session(session.id)

    # Simulate the per-request bind: set the GUC to the membership's tenant_id
    # within a transaction, then read the fenced table.
    with psycopg.connect(scratch_url) as conn:
        conn.execute(
            "SELECT set_config('dazzle.tenant_id', %s, true)",
            (ctx.active_membership.tenant_id,),
        )
        rows = conn.execute('SELECT id FROM "Note"').fetchall()
        conn.rollback()

    assert {r[0] for r in rows} == {"n1"}, "fence must return only tenant t-A's row"
```

> Note: `FORCE ROW LEVEL SECURITY` applies the fence to the table owner too, so the read is genuinely fenced even on the test's owner connection. The bind is in the same transaction as the read (`set_config(..., true)` is transaction-local), mirroring `pg_backend.connection()`.

- [ ] **Step 2: Run test to verify it fails (before Tasks 5–8 land) / passes (after)**

Run: `pytest tests/integration/test_auth_membership_pg.py::test_membership_tenant_binds_fence_on_a_scoped_table -q`
Expected after Tasks 5–8: PASS — only `n1` returned. (If run before the membership pipeline exists, it fails at `ctx.active_membership` being `None`.)

- [ ] **Step 3: (no new implementation)** — this task proves the composed behavior; if it fails, the defect is in Tasks 5–8, fix there.

- [ ] **Step 4: Run the whole Plan-1a suite**

Run: `pytest tests/unit/test_auth_membership_model.py tests/unit/test_bind_rls_from_membership.py tests/integration/test_auth_membership_pg.py -q`
Expected: all PASS (integration tests SKIP if no `DATABASE_URL`).

- [ ] **Step 5: Commit**

```bash
git add tests/integration/test_auth_membership_pg.py
git commit -m "test(auth): keystone proof — active membership binds the fence (Plan 1a)"
```

---

## Final verification (run before handing off / shipping)

- [ ] `ruff check src/ tests/ --fix && ruff format src/ tests/` — clean
- [ ] `mypy src/dazzle --ignore-missing-imports --exclude 'eject'` — clean
- [ ] `pytest tests/ -m "not e2e"` — green (unit suite; the new unit tests included)
- [ ] With a reachable `DATABASE_URL`: `pytest tests/integration/test_auth_membership_pg.py -q` — green
- [ ] `/bump patch` + CHANGELOG entry under **Added** (memberships substrate) with an **Agent Guidance** note: "RLS tenant id now sources from `session.active_membership` when present, preferences fallback otherwise; new auth-store table `memberships`; fake auth conns unaffected."

---

## Forward outline (Plans 1b–1d — each its own plan when reached)

- **Plan 1b — two-phase activation + org-context resolution.** Login (`password_login_routes` + the OAuth/magic-link entry points) resolves the identity (Phase 1) then activates a membership (Phase 2): host-pin (reuse `tenant_host` #1289) → that org's membership or 403; else single membership auto-activates, multiple → org-picker surface, zero → "no orgs yet". Sets `active_membership_id` on the created session; org-switch endpoint rotates it. `require_roles`/role checks switch from `auth_context.roles` to `auth_context.effective_roles`.
- **Plan 1c — single-org auto-provision + graceful degradation.** A framework path that, for a single-org app, ensures exactly one Organization (tenant root + `public.tenants` row) exists and every signup creates one membership in it, so Phase 2 is invisible. Trigger + idempotency are open questions (spec §10).
- **Plan 1d — migrate repo apps/fixtures + retire preferences-indirection.** Update `examples/`+`fixtures/` to the membership model; provide the documented single-org migration recipe (+ optional `dazzle auth migrate`); remove the `tenant_id`-via-preferences fallback from `_bind_rls_tenant_id` and the `_load_domain_user_attributes` tenant copy once all callers are migrated.

## Self-review notes

- **Spec coverage (§9 Plan 1):** "Identity/Membership/Session core" → Tasks 1–7; "fence relocation" → Task 8 + Task 9 proof; "roles→membership" → Task 2 (`effective_roles`) + Task 7 (membership-sourced) — full role *switchover* at call sites is 1b. "two-phase auth" + "single-org degradation" are explicitly deferred to 1b/1c (this plan is the substrate they require). Gap is intentional and outlined above.
- **Placeholder scan:** none — every step has concrete code/commands. Two clearly-flagged "verify the exact existing name" notes (`create_user`, `get_user_by_id` signature, `alembic_ini_path`) are real-codebase reconciliations, not placeholders; each says exactly how to confirm and that assertions don't change.
- **Type consistency:** `MembershipRecord` fields (Task 1) are used identically in CRUD (Task 5), `create_session` (Task 6), `validate_session` (Task 7), and the bind (Task 8). `active_membership_id: str | None` is consistent across `SessionRecord` (Task 6), the migration/DDL (Tasks 3–4), and hydration (Task 7). `effective_roles` (Task 2) is the single roles accessor referenced in the 1b outline.
