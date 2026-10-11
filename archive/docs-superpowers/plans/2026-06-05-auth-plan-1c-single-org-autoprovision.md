# Auth Plan 1c — Single-Org Auto-Provision + Invisible Degradation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (Hybrid: inline execution with an independent adversarial-review checkpoint on the provisioning path before the config wiring). Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Phase-2 org activation *invisible* for single-org apps — a framework-owned `organizations` registry plus lazy, race-safe first-signup provisioning so every identity ends up with exactly one membership (and the RLS fence binds to that org) without any picker, switcher, or "no orgs yet" dead-end.

**Architecture:** A framework `organizations` table joins `memberships`/`sessions`/`users` in the **auth-store raw-SQL world** (the 1a architectural call — framework owns Identity/Org/Membership/Session). Provisioning is **lazy at the activation step** (1b's `activate_session_for_login`), not at the four scattered signup sites: when an app opts into single-org mode (`app.state.single_org_auto_provision`) and the proven identity has zero memberships, the framework ensures one default `organizations` row exists (race-safe via a fixed-slug `UNIQUE` + `INSERT … ON CONFLICT DO NOTHING`) and creates this identity's membership in it, then resolution proceeds → exactly one membership → auto-activates. This doubles as **lazy backfill** for pre-1c users. `membership.tenant_id = organizations.id = dazzle.tenant_id` (the user's decision: framework Organization registry as the discriminator source).

**Tech Stack:** Python 3.12, Pydantic v2 (frozen models), psycopg3 (raw SQL, `%s` params, `INSERT … ON CONFLICT`), Alembic (ADR-0017), pytest (+ `pytest.mark.postgres` integration tests against `TEST_DATABASE_URL`).

---

## Scope

**In scope (Plan 1c):**
- `OrganizationRecord` model + `organizations` table (auth-store raw-SQL) + Alembic `0008` + `_init_db` parity.
- `AuthStore` org CRUD: `create_organization`, `get_organization_by_slug`, `get_or_create_default_organization` (race-safe), and `ensure_single_org_membership(user, roles)`.
- Lazy provisioning in the activation path (`activate_session_for_login`) gated by `single_org_auto_provision(request)`, with `membership.tenant_id = organizations.id`.
- Config wiring: `ServerConfig.auto_provision_single_org` (default `False`) → `app.state.single_org_auto_provision` + `app.state.memberships_required`, set in `subsystems/auth.py`.
- Real-PG proof: first signup provisions org + owner-ish membership; second identity joins the *same* org; concurrent first-signups don't create two orgs; flag-off / multi-org does NOT auto-provision; the bound fence shows only that org's rows.

**Out of scope (later slices / explicitly deferred):**
- **1:1 seeding of a domain `archetype: tenant` entity row** with the org's shared id (for apps that declare a tenant-root entity) — needs app-specific required-field knowledge; **Plan 1d** (app migration) handles it. 1c targets the framework-org-as-tenant case (the org id is the discriminator; domain rows fenced by it).
- **Owner-vs-member role elevation** for the org creator (needs the app's admin-persona vocabulary). 1c gives every auto-membership the identity's signup roles (`user.roles`); first-user-owner elevation is a documented follow-up.
- Migrating `examples/`+`fixtures/` and flipping their flag on, and retiring the preferences-tenant fallback — **Plan 1d**.
- Multi-org invitations / member-admin / `tenancy: multi_org:` DSL — **Plan 3**; enterprise `Connection`s — **Plans 4–5**.
- Reconciling the schema-isolation `public.tenants` registry with this `organizations` table — they coexist (`public.tenants` is the premium schema-per-tenant registry behind `dazzle tenant create`; `organizations` is the shared-schema framework Organization). A future unification is noted, not built.

## Design decisions (carrying the user's Plan 1c answers + resolving spec §10)

- **Org source = framework Organization registry.** `organizations` is a framework-owned auth-store table; `membership.tenant_id = organizations.id` is the `dazzle.tenant_id` discriminator. Chosen over tying to the app's `archetype: tenant` entity so it works uniformly whether or not the app declares a tenant root (e.g. `support_tickets` has none).
- **Trigger = first-signup, lazy, at activation.** The first identity to reach activation with zero memberships *and* single-org mode creates the default org (race-safe) and an owner-roles membership; subsequent identities join it. Implemented at `activate_session_for_login` (one site) rather than the 4 signup routes — DRY, and it also lazily backfills pre-1c users on their next login.
- **Race safety / idempotency.** The default org has a fixed slug (`"default"`) with a `UNIQUE` constraint; `get_or_create_default_organization` does `INSERT … ON CONFLICT (slug) DO NOTHING` then `SELECT`, so concurrent first-signups converge on one row. The membership's `(tenant_id, identity_id)` unique (from 1a) makes the per-user membership idempotent.
- **Non-breaking.** `auto_provision_single_org` defaults `False`, so existing un-migrated apps keep 1b's legacy-proceed behavior (zero membership → proceed, legacy fence). Plan 1d turns it on per migrated app; the new-app scaffolder can default it on.

## File Structure

| File | Responsibility | Change |
|---|---|---|
| `src/dazzle/http/runtime/auth/models.py` | `OrganizationRecord` Pydantic model | **Modify** |
| `src/dazzle/http/alembic/versions/0008_organizations.py` | `organizations` schema migration | **Create** |
| `src/dazzle/http/runtime/auth/store.py` | `organizations` DDL in `_init_db`; org CRUD; `ensure_single_org_membership` | **Modify** |
| `src/dazzle/http/runtime/auth/org_activation.py` | `single_org_auto_provision(request)` + lazy provision in `activate_session_for_login` | **Modify** |
| `src/dazzle/http/runtime/server.py` | `ServerConfig.auto_provision_single_org` field | **Modify** |
| `src/dazzle/http/runtime/subsystems/auth.py` | set `app.state.single_org_auto_provision` + `memberships_required` | **Modify** |
| `tests/unit/test_org_activation.py` | provisioning glue unit tests (append) | **Modify** |
| `tests/integration/test_auth_orgprovision_pg.py` | real-PG provisioning proof | **Create** |

---

## Task 1: `OrganizationRecord` model

**Files:**
- Modify: `src/dazzle/http/runtime/auth/models.py`
- Test: `tests/unit/test_auth_membership_model.py` (append — the existing auth-model unit file from 1a)

- [ ] **Step 1: Write the failing test (append)**

```python
# append to tests/unit/test_auth_membership_model.py
from dazzle.http.runtime.auth.models import OrganizationRecord


class TestOrganizationRecord:
    def test_minimal_construction_defaults(self) -> None:
        o = OrganizationRecord(id="o-1", slug="default", name="Default")
        assert o.id == "o-1"
        assert o.slug == "default"
        assert o.name == "Default"
        assert o.status == "active"
        assert o.is_test is False

    def test_is_frozen(self) -> None:
        import pytest
        from pydantic import ValidationError

        o = OrganizationRecord(id="o-2", slug="acme", name="Acme")
        with pytest.raises(ValidationError):
            o.status = "suspended"  # type: ignore[misc]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_auth_membership_model.py -k Organization -q`
Expected: FAIL — `ImportError: cannot import name 'OrganizationRecord'`.

- [ ] **Step 3: Add the model**

In `src/dazzle/http/runtime/auth/models.py`, after the `MembershipRecord` class, add:

```python
class OrganizationRecord(BaseModel):
    """A framework-owned Organization — the tenant root in the shared-schema
    model (auth Plan 1c).

    ``id`` is the value the RLS fence reads as ``dazzle.tenant_id`` (and the
    ``tenant_id`` a ``MembershipRecord`` carries). Lives in the auth store
    alongside ``users``/``sessions``/``memberships`` (framework owns
    Identity/Org/Membership/Session), not the IR-entity pipeline. ``slug`` is
    unique; single-org apps use the fixed slug ``"default"`` so lazy
    provisioning is race-safe.
    """

    model_config = ConfigDict(frozen=True)

    id: str
    slug: str
    name: str
    status: str = "active"
    is_test: bool = False
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
```

(`BaseModel`, `ConfigDict`, `Field`, `datetime`, `UTC` are already imported at the top of `models.py` — used by `MembershipRecord`/`SessionRecord`.)

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_auth_membership_model.py -k Organization -q`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/http/runtime/auth/models.py tests/unit/test_auth_membership_model.py
git commit -m "feat(auth): OrganizationRecord model (Plan 1c)"
```

---

## Task 2: Alembic `0008_organizations` + `_init_db` DDL parity

**Files:**
- Create: `src/dazzle/http/alembic/versions/0008_organizations.py`
- Modify: `src/dazzle/http/runtime/auth/store.py` (`_init_db`)
- Test: `tests/integration/test_auth_orgprovision_pg.py`

- [ ] **Step 1: Write the failing integration test (with the scratch-DB harness)**

```python
# tests/integration/test_auth_orgprovision_pg.py
"""Real-PostgreSQL proof of single-org auto-provision (auth Plan 1c).

Marked e2e + postgres: skipped without TEST_DATABASE_URL/DATABASE_URL.
Mirrors tests/integration/test_auth_activation_pg.py's scratch-DB harness.
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
    scratch = f"dazzle_auth_1c_{uuid.uuid4().hex[:8]}"
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


def test_init_db_creates_organizations(scratch_url: str) -> None:
    from dazzle.http.runtime.auth.store import AuthStore

    store = AuthStore(database_url=scratch_url)
    store._init_db()
    cols = _columns(scratch_url, "organizations")
    assert {"id", "slug", "name", "status", "is_test"} <= cols


def test_migration_0008_creates_organizations(scratch_url: str) -> None:
    from alembic import command
    from alembic.config import Config

    from dazzle.http.runtime.auth.store import AuthStore

    store = AuthStore(database_url=scratch_url)
    store._init_db()  # baseline users/sessions/memberships

    # Locate alembic.ini the same way tests/integration/test_auth_membership_pg.py does.
    from dazzle.http.alembic import alembic_ini_path  # if absent, mirror cli/db.py's Config()

    cfg = Config(str(alembic_ini_path()))
    cfg.set_main_option(
        "sqlalchemy.url", scratch_url.replace("postgresql://", "postgresql+psycopg://")
    )
    command.upgrade(cfg, "head")
    assert {"id", "slug", "name", "status", "is_test"} <= _columns(scratch_url, "organizations")
```

> If `dazzle.http.alembic.alembic_ini_path` doesn't exist, copy the exact `Config(...)` construction used in `tests/integration/test_auth_membership_pg.py` (1a's migration test) — assertions unchanged.

- [ ] **Step 2: Run test to verify it fails**

Run: `TEST_DATABASE_URL="postgresql://localhost:5432/postgres" pytest tests/integration/test_auth_orgprovision_pg.py -k "init_db_creates_organizations or migration_0008" -q`
Expected: FAIL — no `organizations` table.

- [ ] **Step 3a: Write the migration**

```python
# src/dazzle/http/alembic/versions/0008_organizations.py
"""Add organizations table (auth Plan 1c — framework Organization registry).

The framework gains an `organizations` join (the tenant root in shared-schema):
`organizations.id` is the `dazzle.tenant_id` discriminator a membership carries.
Idempotent: guards on table presence so the dev `_init_db` create path and this
migration are interchangeable. No DB FK from `memberships.tenant_id` (the auth
tables aren't in the Alembic-managed DSL metadata; the join is enforced in the
store, mirroring 0007's identity_id treatment).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect as sa_inspect

revision = "0008_organizations"
down_revision = "0007_memberships"
branch_labels = None
depends_on = None


def _has_table(table: str) -> bool:
    return sa_inspect(op.get_bind()).has_table(table)


def upgrade() -> None:
    if not _has_table("organizations"):
        op.create_table(
            "organizations",
            sa.Column("id", sa.Text(), primary_key=True),
            sa.Column("slug", sa.Text(), nullable=False),
            sa.Column("name", sa.Text(), nullable=False),
            sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'active'")),
            sa.Column("is_test", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("created_at", sa.Text(), nullable=False),
            sa.Column("updated_at", sa.Text(), nullable=False),
            sa.UniqueConstraint("slug", name="uq_organizations_slug"),
        )


def downgrade() -> None:
    if _has_table("organizations"):
        op.drop_table("organizations")
```

- [ ] **Step 3b: Add the DDL to `_init_db`**

In `src/dazzle/http/runtime/auth/store.py`, inside `_init_db`, after the `memberships` table block (added in 1a), add:

```python
        # auth Plan 1c: organizations (framework tenant root). Mirrors alembic
        # 0008_organizations. organizations.id is the dazzle.tenant_id a
        # membership carries; single-org apps use the fixed slug "default".
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS organizations (
                id TEXT PRIMARY KEY,
                slug TEXT NOT NULL,
                name TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'active',
                is_test BOOLEAN NOT NULL DEFAULT false,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                CONSTRAINT uq_organizations_slug UNIQUE (slug)
            )
        """)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `TEST_DATABASE_URL="postgresql://localhost:5432/postgres" pytest tests/integration/test_auth_orgprovision_pg.py -k "init_db_creates_organizations or migration_0008" -q`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/http/alembic/versions/0008_organizations.py src/dazzle/http/runtime/auth/store.py tests/integration/test_auth_orgprovision_pg.py
git commit -m "feat(auth): organizations table — alembic 0008 + _init_db (Plan 1c)"
```

---

## Task 3: `AuthStore` organization CRUD (race-safe get-or-create)

**Files:**
- Modify: `src/dazzle/http/runtime/auth/store.py`
- Test: `tests/integration/test_auth_orgprovision_pg.py` (append)

- [ ] **Step 1: Write the failing test (append)**

```python
# append to tests/integration/test_auth_orgprovision_pg.py
def test_get_or_create_default_organization_is_idempotent(scratch_url: str) -> None:
    from dazzle.http.runtime.auth.store import AuthStore

    store = AuthStore(database_url=scratch_url)
    store._init_db()

    o1 = store.get_or_create_default_organization(name="Acme")
    o2 = store.get_or_create_default_organization(name="Acme")
    assert o1.id == o2.id  # same row — not a second org
    assert o1.slug == "default"
    assert store.get_organization_by_slug("default").id == o1.id


def test_create_organization_slug_unique(scratch_url: str) -> None:
    import pytest

    from dazzle.http.runtime.auth.store import AuthStore

    store = AuthStore(database_url=scratch_url)
    store._init_db()
    store.create_organization(slug="acme", name="Acme")
    with pytest.raises(Exception):  # noqa: B017 — unique violation
        store.create_organization(slug="acme", name="Acme 2")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `TEST_DATABASE_URL="postgresql://localhost:5432/postgres" pytest tests/integration/test_auth_orgprovision_pg.py -k "default_organization or slug_unique" -q`
Expected: FAIL — no `get_or_create_default_organization` / `create_organization`.

- [ ] **Step 3: Add CRUD + row mapper**

In `src/dazzle/http/runtime/auth/store.py`, import `OrganizationRecord` from `.models` alongside the other model imports, and add near the membership methods:

```python
    DEFAULT_ORG_SLUG = "default"

    def _row_to_organization(self, row: dict[str, Any]) -> "OrganizationRecord":
        return OrganizationRecord(
            id=row["id"],
            slug=row["slug"],
            name=row["name"],
            status=row["status"],
            is_test=bool(row["is_test"]),
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )

    def create_organization(
        self, *, slug: str, name: str, is_test: bool = False
    ) -> "OrganizationRecord":
        """Create an organization (raises on duplicate slug)."""
        org = OrganizationRecord(
            id=secrets.token_urlsafe(24), slug=slug, name=name, is_test=is_test
        )
        self._execute(
            """
            INSERT INTO organizations
                (id, slug, name, status, is_test, created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (
                org.id,
                org.slug,
                org.name,
                org.status,
                org.is_test,
                org.created_at.isoformat(),
                org.updated_at.isoformat(),
            ),
        )
        return org

    def get_organization_by_slug(self, slug: str) -> "OrganizationRecord | None":
        row = self._execute_one("SELECT * FROM organizations WHERE slug = %s", (slug,))
        return self._row_to_organization(row) if row else None

    def get_or_create_default_organization(self, *, name: str = "Default") -> "OrganizationRecord":
        """Return the single default org, creating it race-safely if absent.

        Concurrent first-signups converge on one row: the INSERT is a no-op on
        slug conflict, then we SELECT the winner. The fixed ``DEFAULT_ORG_SLUG``
        + its UNIQUE constraint is the idempotency key.
        """
        org_id = secrets.token_urlsafe(24)
        now = datetime.now(UTC).isoformat()
        # ON CONFLICT DO NOTHING: if another request already inserted "default",
        # this writes nothing; the subsequent SELECT returns the existing row.
        self._execute(
            """
            INSERT INTO organizations
                (id, slug, name, status, is_test, created_at, updated_at)
            VALUES (%s, %s, %s, 'active', false, %s, %s)
            ON CONFLICT (slug) DO NOTHING
            """,
            (org_id, self.DEFAULT_ORG_SLUG, name, now, now),
        )
        existing = self.get_organization_by_slug(self.DEFAULT_ORG_SLUG)
        assert existing is not None  # we just ensured it exists
        return existing
```

> Confirm `_execute` issues each call on its own committed connection (1a's membership CRUD relies on the same). The `ON CONFLICT (slug)` targets the `uq_organizations_slug` unique constraint from Task 2.

- [ ] **Step 4: Run test to verify it passes**

Run: `TEST_DATABASE_URL="postgresql://localhost:5432/postgres" pytest tests/integration/test_auth_orgprovision_pg.py -k "default_organization or slug_unique" -q`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/http/runtime/auth/store.py tests/integration/test_auth_orgprovision_pg.py
git commit -m "feat(auth): organization CRUD + race-safe get_or_create_default (Plan 1c)"
```

---

## Task 4: `AuthStore.ensure_single_org_membership`

**Files:**
- Modify: `src/dazzle/http/runtime/auth/store.py`
- Test: `tests/integration/test_auth_orgprovision_pg.py` (append)

- [ ] **Step 1: Write the failing test (append)**

```python
# append to tests/integration/test_auth_orgprovision_pg.py
def test_ensure_single_org_membership_first_and_second_user(scratch_url: str) -> None:
    from dazzle.http.runtime.auth.store import AuthStore

    store = AuthStore(database_url=scratch_url)
    store._init_db()
    u1 = store.create_user(email="a@b.test", password="pw123456", roles=["member"])
    u2 = store.create_user(email="b@b.test", password="pw123456", roles=["member"])

    m1 = store.ensure_single_org_membership(u1, name="Acme")
    m2 = store.ensure_single_org_membership(u2, name="Acme")
    # Both joined the SAME org.
    assert m1.tenant_id == m2.tenant_id
    # The membership carries the user's signup roles.
    assert m1.roles == ["member"]
    # Idempotent: calling again for u1 returns the existing membership, no dup.
    m1_again = store.ensure_single_org_membership(u1, name="Acme")
    assert m1_again.id == m1.id
    assert len(store.get_memberships_for_identity(str(u1.id))) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `TEST_DATABASE_URL="postgresql://localhost:5432/postgres" pytest tests/integration/test_auth_orgprovision_pg.py -k ensure_single_org -q`
Expected: FAIL — no `ensure_single_org_membership`.

- [ ] **Step 3: Add the method**

In `src/dazzle/http/runtime/auth/store.py`, add near `create_membership`:

```python
    def ensure_single_org_membership(
        self, user: "UserRecord", *, name: str = "Default"
    ) -> "MembershipRecord":
        """Ensure ``user`` has a membership in the single default org (Plan 1c).

        Race-safe: get-or-create the default org, then return the user's existing
        membership in it (the 1a ``(tenant_id, identity_id)`` unique makes the
        create idempotent — on a lost race we re-read). The membership's roles
        mirror the user's signup roles (``user.roles``) so ``effective_roles``
        equals what the user had before the membership model.
        """
        org = self.get_or_create_default_organization(name=name)
        existing = [
            m for m in self.get_memberships_for_identity(str(user.id))
            if m.tenant_id == org.id
        ]
        if existing:
            return existing[0]
        try:
            return self.create_membership(
                tenant_id=org.id,
                identity_id=str(user.id),
                roles=list(user.roles or []),
            )
        except Exception:
            # Lost a concurrent create for the same (tenant_id, identity_id) —
            # re-read the winner rather than failing the login (anti-silent:
            # we only swallow the unique-violation, then assert the row exists).
            again = [
                m for m in self.get_memberships_for_identity(str(user.id))
                if m.tenant_id == org.id
            ]
            assert again, "membership create failed and no existing row found"
            return again[0]
```

> `UserRecord.roles` is the global roles list set at signup from `default_signup_roles`. `create_membership` is 1a's keyword-only CRUD.

- [ ] **Step 4: Run test to verify it passes**

Run: `TEST_DATABASE_URL="postgresql://localhost:5432/postgres" pytest tests/integration/test_auth_orgprovision_pg.py -k ensure_single_org -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/http/runtime/auth/store.py tests/integration/test_auth_orgprovision_pg.py
git commit -m "feat(auth): ensure_single_org_membership — idempotent per-user join (Plan 1c)"
```

---

## Task 5: Lazy provisioning at activation

**Files:**
- Modify: `src/dazzle/http/runtime/auth/org_activation.py`
- Test: `tests/unit/test_org_activation.py` (append) + `tests/integration/test_auth_orgprovision_pg.py` (append)

- [ ] **Step 1: Write the failing unit test (append)**

```python
# append to tests/unit/test_org_activation.py
class _ProvisioningStore:
    """Fake store that records ensure_single_org_membership calls."""

    def __init__(self) -> None:
        self.provisioned: list[str] = []
        self._memberships: dict[str, list[MembershipRecord]] = {}

    def get_memberships_for_identity(self, identity_id: str) -> list[MembershipRecord]:
        return list(self._memberships.get(identity_id, []))

    def ensure_single_org_membership(self, user, *, name="Default"):  # noqa: ANN001
        self.provisioned.append(str(user.id))
        m = MembershipRecord(id="m-prov", tenant_id="t-default", identity_id=str(user.id))
        self._memberships[str(user.id)] = [m]
        return m


def _req_with_flag(*, provision: bool, tenant=None) -> SimpleNamespace:
    app = SimpleNamespace(state=SimpleNamespace(single_org_auto_provision=provision))
    return SimpleNamespace(app=app, state=SimpleNamespace(tenant=tenant))


class TestLazyProvisioning:
    def test_provisions_when_flag_on_and_zero_memberships(self) -> None:
        store = _ProvisioningStore()
        user = SimpleNamespace(id="u-1")
        out = activate_session_for_login(store, user, _req_with_flag(provision=True))
        assert store.provisioned == ["u-1"]  # provisioned once
        assert isinstance(out, Activated)
        assert out.membership_id == "m-prov"

    def test_does_not_provision_when_flag_off(self) -> None:
        store = _ProvisioningStore()
        user = SimpleNamespace(id="u-1")
        out = activate_session_for_login(store, user, _req_with_flag(provision=False))
        assert store.provisioned == []
        assert isinstance(out, NoOrgs)

    def test_does_not_provision_when_membership_already_exists(self) -> None:
        store = _ProvisioningStore()
        store._memberships["u-1"] = [
            MembershipRecord(id="m-x", tenant_id="t-1", identity_id="u-1")
        ]
        user = SimpleNamespace(id="u-1")
        out = activate_session_for_login(store, user, _req_with_flag(provision=True))
        assert store.provisioned == []  # already had one — no provision
        assert isinstance(out, Activated)
        assert out.membership_id == "m-x"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_org_activation.py -k Provision -q`
Expected: FAIL — `activate_session_for_login` doesn't provision (no `single_org_auto_provision` handling).

- [ ] **Step 3: Add `single_org_auto_provision` + provisioning step**

In `src/dazzle/http/runtime/auth/org_activation.py`, add the flag helper next to `memberships_required`:

```python
def single_org_auto_provision(request: Any) -> bool:
    """Whether this app lazily provisions a single default org at activation
    (Plan 1c). Default False — pre-1c / multi-org apps don't auto-provision."""
    state = getattr(getattr(request, "app", None), "state", None)
    return bool(getattr(state, "single_org_auto_provision", False))
```

Then modify `activate_session_for_login` to provision before resolving:

```python
def activate_session_for_login(auth_store: Any, user: Any, request: Any) -> ActivationOutcome:
    """Resolve Phase 2 for a just-proven ``user`` on this ``request``.

    Plan 1c: when the app opts into single-org auto-provision and the identity
    has no membership *and* the request is not host-pinned (a host pin names a
    specific org — provisioning a different default would be wrong), lazily
    ensure a default-org membership first. This makes single-org Phase 2
    invisible and backfills pre-1c users on next login.
    """
    host_tenant_id = host_tenant_id_from_request(request)
    memberships = auth_store.get_memberships_for_identity(str(user.id))
    if (
        not memberships
        and host_tenant_id is None
        and single_org_auto_provision(request)
    ):
        auth_store.ensure_single_org_membership(user)
        memberships = auth_store.get_memberships_for_identity(str(user.id))
    return resolve_activation(memberships=memberships, host_tenant_id=host_tenant_id)
```

> Note the **host-pin guard**: auto-provision only runs when there's no host pin. A host-pinned request names a specific org; if the identity has no membership there, the correct answer is `HostForbidden` (403) — *not* silently provisioning a default org and letting them in. This keeps the 1b host-pin security property intact.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_org_activation.py -k Provision -q`
Expected: PASS (3 passed). Also run the full file to confirm no regression: `pytest tests/unit/test_org_activation.py -q` (the 1b tests build requests without `app.state.single_org_auto_provision`; `single_org_auto_provision` returns False for them via getattr-default).

- [ ] **Step 5: Real-PG end-to-end (append integration test)**

```python
# append to tests/integration/test_auth_orgprovision_pg.py
def test_activation_provisions_and_auto_activates(scratch_url: str) -> None:
    from types import SimpleNamespace

    from dazzle.http.runtime.auth.org_activation import (
        Activated,
        activate_session_for_login,
    )
    from dazzle.http.runtime.auth.store import AuthStore

    store = AuthStore(database_url=scratch_url)
    store._init_db()
    user = store.create_user(email="solo@b.test", password="pw123456", roles=["member"])

    app = SimpleNamespace(state=SimpleNamespace(single_org_auto_provision=True))
    request = SimpleNamespace(app=app, state=SimpleNamespace(tenant=None))

    out = activate_session_for_login(store, user, request)
    assert isinstance(out, Activated)
    m = store.get_membership(out.membership_id)
    assert m.roles == ["member"]
    # The org now exists with the default slug.
    assert store.get_organization_by_slug("default").id == m.tenant_id


def test_host_pin_does_not_auto_provision(scratch_url: str) -> None:
    """A host-pinned request to an org the user isn't in stays 403 — provisioning
    must not paper over it."""
    from types import SimpleNamespace

    from dazzle.http.runtime.auth.org_activation import (
        HostForbidden,
        activate_session_for_login,
    )
    from dazzle.http.runtime.auth.store import AuthStore

    store = AuthStore(database_url=scratch_url)
    store._init_db()
    user = store.create_user(email="solo@b.test", password="pw123456", roles=["member"])

    app = SimpleNamespace(state=SimpleNamespace(single_org_auto_provision=True))
    request = SimpleNamespace(
        app=app, state=SimpleNamespace(tenant=SimpleNamespace(id="t-pinned", slug="acme"))
    )
    out = activate_session_for_login(store, user, request)
    assert isinstance(out, HostForbidden)
    # No org was provisioned.
    assert store.get_organization_by_slug("default") is None
```

Run: `TEST_DATABASE_URL="postgresql://localhost:5432/postgres" pytest tests/integration/test_auth_orgprovision_pg.py -k "provisions_and_auto_activate or host_pin_does_not" -q`
Expected: PASS (2 passed).

- [ ] **Step 6: Commit**

```bash
git add src/dazzle/http/runtime/auth/org_activation.py tests/unit/test_org_activation.py tests/integration/test_auth_orgprovision_pg.py
git commit -m "feat(auth): lazy single-org provisioning at activation, host-pin-guarded (Plan 1c)"
```

---

> ### ⛳ ADVERSARIAL REVIEW CHECKPOINT (after Task 5)
> Before wiring the config flag, dispatch an **independent reviewer subagent** (or run `/code-review`) over the provisioning path (Tasks 3–5). Brief it to attack: (1) **cross-tenant leak** — can provisioning ever attach a user to the wrong org, or create a second default org that splits the tenant (race)? Verify `ON CONFLICT (slug)` + the `(tenant_id, identity_id)` unique genuinely converge. (2) **host-pin bypass** — confirm auto-provision is skipped when host-pinned so `HostForbidden` still fires (no "provision a default and let them in"). (3) **silent failure** — the `except Exception` in `ensure_single_org_membership` swallows then re-reads; confirm it can't mask a real failure (asserts the row exists) and only the unique-violation path is intended. (4) **backfill correctness** — an existing pre-1c user logging in gets exactly one membership with their existing roles, not a role downgrade/escalation. (5) **multi-org safety** — confirm a multi-org app (flag off) never auto-provisions. Apply receiving-code-review rigor. Proceed only when clean.

---

## Task 6: Config wiring — `ServerConfig.auto_provision_single_org` → app.state

**Files:**
- Modify: `src/dazzle/http/runtime/server.py` (`ServerConfig`)
- Modify: `src/dazzle/http/runtime/subsystems/auth.py`
- Test: `tests/integration/test_auth_orgprovision_pg.py` (append — flag-default assertion)

- [ ] **Step 1: Write the failing test (append)**

```python
# append to tests/integration/test_auth_orgprovision_pg.py
def test_server_config_defaults_auto_provision_off() -> None:
    """Non-breaking default: existing apps don't auto-provision (no DB needed)."""
    from dazzle.http.runtime.server import ServerConfig

    assert ServerConfig().auto_provision_single_org is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/integration/test_auth_orgprovision_pg.py::test_server_config_defaults_auto_provision_off -q`
Expected: FAIL — `ServerConfig` has no `auto_provision_single_org`.

- [ ] **Step 3a: Add the `ServerConfig` field**

In `src/dazzle/http/runtime/server.py`, in the `ServerConfig` dataclass (around line 81), add a field with the others:

```python
    # auth Plan 1c: lazily provision a single default Organization + one
    # membership per identity at activation (invisible single-org degradation).
    # Default False — non-breaking; Plan 1d turns it on for migrated apps and
    # the new-app scaffolder defaults it on.
    auto_provision_single_org: bool = False
```

(Match the existing field style — if `ServerConfig` is a `@dataclass`, add it as a plain annotated field with a default; if Pydantic, use the same field idiom the neighbours use.)

- [ ] **Step 3b: Surface it on `app.state` in the auth subsystem**

In `src/dazzle/http/runtime/subsystems/auth.py`, near where `ctx.app.state.auth_store` is set (~line 58), add:

```python
        # auth Plan 1c — single-org auto-provision + the 1b memberships gate.
        # When on, activation lazily provisions one default org + membership
        # (invisible single-org), and a genuinely org-less identity routes to
        # /auth/no-orgs rather than the legacy proceed.
        _auto_provision = bool(getattr(ctx.config, "auto_provision_single_org", False))
        ctx.app.state.single_org_auto_provision = _auto_provision
        ctx.app.state.memberships_required = _auto_provision
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/integration/test_auth_orgprovision_pg.py::test_server_config_defaults_auto_provision_off -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/http/runtime/server.py src/dazzle/http/runtime/subsystems/auth.py tests/integration/test_auth_orgprovision_pg.py
git commit -m "feat(auth): ServerConfig.auto_provision_single_org → app.state flags (Plan 1c)"
```

---

## Task 7: Keystone — provisioned membership fences a domain query

**Files:**
- Test: `tests/integration/test_auth_orgprovision_pg.py` (append)

End-to-end proof: after lazy provisioning, the bound fence (from the provisioned membership's `tenant_id`) shows only that org's rows.

- [ ] **Step 1: Write the failing test (append)**

```python
# append to tests/integration/test_auth_orgprovision_pg.py
def test_provisioned_membership_binds_fence(scratch_url: str) -> None:
    """A provisioned membership's tenant_id binds dazzle.tenant_id; a restrictive
    fence returns only that org's rows (mirrors the 1a keystone)."""
    from types import SimpleNamespace

    from dazzle.http.runtime.auth.org_activation import activate_session_for_login
    from dazzle.http.runtime.auth.store import AuthStore

    ddl = [
        'CREATE TABLE "Note" (tenant_id TEXT NOT NULL, id TEXT PRIMARY KEY, body TEXT)',
        'ALTER TABLE "Note" ENABLE ROW LEVEL SECURITY',
        'ALTER TABLE "Note" FORCE ROW LEVEL SECURITY',
        "CREATE POLICY tenant_fence ON \"Note\" AS RESTRICTIVE FOR ALL "
        "USING (tenant_id = current_setting('dazzle.tenant_id', true)) "
        "WITH CHECK (tenant_id = current_setting('dazzle.tenant_id', true))",
    ]
    with psycopg.connect(scratch_url, autocommit=True) as conn:
        for stmt in ddl:
            conn.execute(stmt)  # nosemgrep — static test DDL

    store = AuthStore(database_url=scratch_url)
    store._init_db()
    user = store.create_user(email="solo@b.test", password="pw123456", roles=["member"])
    app = SimpleNamespace(state=SimpleNamespace(single_org_auto_provision=True))
    request = SimpleNamespace(app=app, state=SimpleNamespace(tenant=None))
    out = activate_session_for_login(store, user, request)
    org_id = store.get_membership(out.membership_id).tenant_id

    # Seed one row in the provisioned org and one in another tenant.
    with psycopg.connect(scratch_url, autocommit=True) as conn:
        conn.execute('INSERT INTO "Note" VALUES (%s, %s, %s)', (org_id, "n1", "mine"))
        conn.execute('INSERT INTO "Note" VALUES (%s, %s, %s)', ("t-other", "n2", "theirs"))

    with psycopg.connect(scratch_url) as conn:
        conn.execute("SELECT set_config('dazzle.tenant_id', %s, true)", (org_id,))
        rows = conn.execute('SELECT id FROM "Note"').fetchall()
        conn.rollback()
    assert {r[0] for r in rows} == {"n1"}, "fence must return only the provisioned org's row"
```

- [ ] **Step 2: Run test to verify it passes**

Run: `TEST_DATABASE_URL="postgresql://localhost:5432/postgres" pytest tests/integration/test_auth_orgprovision_pg.py::test_provisioned_membership_binds_fence -q`
Expected: PASS — composes Tasks 3–5; fix upstream if it fails.

- [ ] **Step 3: Run the whole Plan-1c suite**

Run: `pytest tests/unit/test_org_activation.py tests/unit/test_auth_membership_model.py -q && TEST_DATABASE_URL="postgresql://localhost:5432/postgres" pytest tests/integration/test_auth_orgprovision_pg.py -q`
Expected: all PASS.

- [ ] **Step 4: Commit**

```bash
git add tests/integration/test_auth_orgprovision_pg.py
git commit -m "test(auth): keystone — provisioned membership binds the fence (Plan 1c)"
```

---

## Final verification (run before handing off / shipping)

- [ ] `ruff check src/ tests/ --fix && ruff format src/ tests/` — clean
- [ ] `mypy src/dazzle` — clean (CI scope)
- [ ] `pytest tests/ -m "not e2e"` — green (the unit suite; new unit tests included; confirm no auth-route regression — existing apps default `auto_provision_single_org=False` so behave exactly as 1b)
- [ ] With `TEST_DATABASE_URL="postgresql://localhost:5432/postgres"`: `pytest tests/integration/test_auth_orgprovision_pg.py tests/integration/test_auth_activation_pg.py tests/integration/test_auth_membership_pg.py -q` — green
- [ ] `/bump patch` + CHANGELOG entry under **Added** (single-org auto-provision) with an **Agent Guidance** note:
  - "Single-org apps can opt into invisible Phase-2 via `ServerConfig.auto_provision_single_org` (default off → unchanged 1b behavior). When on, login lazily provisions one framework `organizations` row (slug `default`) + one membership per identity (roles = the user's signup roles), so Phase 2 auto-activates and `/auth/no-orgs` only shows for genuinely org-less identities. Auto-provision is skipped under a host pin (a host-pin mismatch still 403s). New auth-store table `organizations` (alembic 0008). Domain `archetype: tenant` row 1:1-seeding and example-app migration are Plan 1d."

---

## Forward outline (Plan 1d + 2 — each its own plan)

- **Plan 1d — migrate repo apps/fixtures + retire preferences-indirection + domain tenant-root 1:1 seed.** Turn `auto_provision_single_org` on for `examples/`+`fixtures/`; for apps declaring an `archetype: tenant` entity, seed that entity's row with the org's shared id (or wire onboarding to create it); provide the documented single-org migration recipe (+ optional `dazzle auth migrate`); remove the `_bind_rls_tenant_id` preferences fallback + the `_load_domain_user_attributes` tenant copy once all callers are on memberships.
- **Plan 2 — RBAC re-sourcing + compliance evidence.** Membership audit attribution; platform roles on identity; lifecycle events (Provision/Authenticate/Authorize/Role-change/Deprovision) → audit trail → access-review export; first-user-owner role elevation lands here (needs the persona/admin vocabulary).

## Self-review notes

- **Spec coverage (§3 graceful degradation + §10 open questions):** "single-org app auto-provisions one Organization; every signup → one membership; Phase 2 invisible" → Tasks 1–6 (framework org + lazy per-identity membership + auto-activate). §10 "auto-provisioning trigger" → resolved to first-signup-lazy-at-activation (Task 5). §10 "how it stays invisible" → single membership ⇒ `Activated` (1b), no picker/no-orgs. The "Organization IS the tenant root" 1:1 with a *domain* `archetype: tenant` row is explicitly deferred to 1d (needs app field knowledge); 1c uses the framework org as the discriminator, which the user selected.
- **Placeholder scan:** every step carries concrete code/SQL. The two flagged reconciliations (`alembic_ini_path` location, `ServerConfig` dataclass-vs-pydantic field idiom) have an explicit "mirror the existing pattern" instruction with an unchanged assertion — real-codebase confirmations, not deferred work.
- **Type consistency:** `OrganizationRecord` fields (Task 1) are used identically in CRUD (Task 3) and `ensure_single_org_membership` (Task 4). `get_or_create_default_organization(*, name)` / `ensure_single_org_membership(user, *, name)` / `single_org_auto_provision(request)` signatures match across the store, the activation glue (Task 5), and the tests. `membership.tenant_id == organizations.id` is the single discriminator identity threaded through Tasks 3–5 and the keystone (Task 7). `auto_provision_single_org` (ServerConfig) → `single_org_auto_provision`/`memberships_required` (app.state) is consistent across Task 6 and the activation reads.
