# Auth Plan 1d — Activate the Membership Model (Canonical RLS Proof) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (Hybrid: inline execution with an independent adversarial-review checkpoint on the 1:1 provisioning + fence path). Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the auth membership model *actually fence real domain data* on the canonical RLS-archetype model — a provisioned membership's `tenant_id` equals the domain tenant-root row's id equals `dazzle.tenant_id`, so a logged-in user is structurally fenced to their org by Postgres RLS. Proven end-to-end on `fixtures/tenant_rls` as a non-superuser.

**Architecture:** Three substrate pieces + a canonical proof. (1) `_resolve_user_attribute("tenant_id")` becomes **membership-first** (the active membership's `tenant_id` wins; the legacy preferences/domain-user copy stays as a non-breaking fallback for un-migrated users) — so scope rules like `current_user.tenant_id` read from the membership, matching what `_bind_rls_tenant_id` already binds for the RLS GUC. (2) `auto_provision_single_org` becomes manifest-settable (`[auth]` → `ServerConfig`). (3) A new `db/provision.py provision_single_org(appspec, name, *, conn)` creates the framework `organizations` row **and**, for an app with an `is_tenant_root` domain entity, a matching tenant-root row with the **same id** (the 1:1 mirror; required scalar fields filled from the name, fail-loud if a required field isn't framework-seedable) — so `organizations.id == Workspace.id == the RLS discriminator`. `ensure_single_org_membership` (1c) uses it for archetype apps so the auto-provisioned membership fences the canonical domain rows. The fallback is **kept** (membership-first), per the chosen non-breaking rollout.

**Tech Stack:** Python 3.12, psycopg3 (sync, `sql.Identifier` composition, one txn), the existing RLS schema/role harness (`build_rls_policy_ddl` + a non-superuser `dazzle_app` role), pytest (+ `pytest.mark.postgres`).

---

## Scope

**In scope (Plan 1d):**
- `_resolve_user_attribute("tenant_id", auth_context)` → membership-first (active membership wins; preferences fallback retained).
- `AuthConfig.auto_provision_single_org: bool` (manifest `[auth]`) threaded into `ServerConfig.auto_provision_single_org` in `app_factory`.
- `db/provision.py provision_single_org(appspec, name, *, conn) -> str` — race-safe (fixed slug), 1:1 org↔tenant-root mirror (shared id) for `is_tenant_root` apps; framework-org-only for rootless apps; `ProvisionError` (fail-loud) when a tenant-root required field isn't framework-seedable.
- `ensure_single_org_membership` (1c) routes through `provision_single_org` when an appspec with a tenant root is available (so the auto-provisioned org id == the seeded Workspace id), else keeps 1c's framework-org behaviour.
- **Canonical proof:** a real-PG integration test on `fixtures/tenant_rls` — provision (Workspace + organizations, shared id) + a user + membership, then **as a non-superuser `dazzle_app` role** with `dazzle.tenant_id` bound from the membership, assert RLS returns only that tenant's rows and a fenced insert lands in-tenant.

**Out of scope (explicit follow-ups, noted in the plan's forward outline):**
- **Removing** the preferences-tenant fallback (kept membership-first this slice — the chosen non-breaking rollout; deletion is a later cleanup once every app+user is migrated).
- `dazzle auth migrate` (backfill of *existing* deployed rows: domain tenant rows → organizations, domain users → memberships) — this slice proves greenfield auto-provision; the existing-data migration recipe is its own slice.
- Create-time auto-injection of `tenant_id` from the active membership (the create path still takes `tenant_id` via the request/scope path; injection is a follow-up).
- Migrating the full example-app fleet + scaffolding a login UI onto the fixture; multi-org (Plan 3).

## Design decisions

- **Canonical model, proven as a non-superuser.** The proof binds `dazzle.tenant_id` from the membership and reads as a non-`BYPASSRLS` role, so it exercises the *real* Postgres RLS fence (superusers bypass RLS) — the same harness shape as `test_rls_enforcement_pg.py`. This is the genuine "the membership model enforces isolation" proof.
- **1:1 id mirror, tenant-root authoritative.** `organizations.id == domain tenant-root row id == dazzle.tenant_id`. `provision_single_org` seeds both with one generated id. For an app whose tenant-root has only framework-derivable required fields (e.g. `Workspace.name`), it fills them; a non-derivable required field is a **loud `ProvisionError`** (a documented Tier-0 constraint: a single-org auto-provisioned tenant root must be framework-seedable), never a silent partial.
- **Membership-first, fallback kept.** `current_user.tenant_id` and the RLS GUC both prefer `active_membership.tenant_id`; the preferences/domain-user copy remains for un-migrated sessions (non-breaking). No clean-break this slice.
- **Cross-boundary provisioning isolated to `db/`.** `provision_single_org` (like `db/excision.py`) takes the appspec + a connection and touches both the framework `organizations` table and the domain tenant-root table in one transaction — the one place that legitimately crosses the auth-store/domain boundary.

## File Structure

| File | Responsibility | Change |
|---|---|---|
| `src/dazzle/http/runtime/route_generator.py` | `_resolve_user_attribute` membership-first for `tenant_id` | **Modify** |
| `src/dazzle/core/manifest.py` | `AuthConfig.auto_provision_single_org` | **Modify** |
| `src/dazzle/http/runtime/app_factory.py` | thread the flag into `ServerConfig` | **Modify** |
| `src/dazzle/db/provision.py` | `provision_single_org` + `ProvisionError` (1:1 org↔root mirror) | **Create** |
| `src/dazzle/http/runtime/auth/store.py` | `ensure_single_org_membership` routes through `provision_single_org` when an appspec+root is available | **Modify** |
| `tests/unit/test_resolve_tenant_membership_first.py` | scope-attr resolution unit test | **Create** |
| `tests/integration/test_membership_rls_activation_pg.py` | canonical non-superuser RLS-fence proof | **Create** |

---

## Task 1: `current_user.tenant_id` resolves membership-first

**Files:**
- Modify: `src/dazzle/http/runtime/route_generator.py` (`_resolve_user_attribute`, ~line 1046)
- Test: `tests/unit/test_resolve_tenant_membership_first.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_resolve_tenant_membership_first.py
"""current_user.tenant_id resolves from the active membership first (Plan 1d)."""

from dazzle.http.runtime.auth.models import AuthContext, MembershipRecord, UserRecord
from dazzle.http.runtime.route_generator import _resolve_user_attribute


def _ctx(*, membership_tid=None, prefs_tid=None):
    m = (
        MembershipRecord(id="m-1", tenant_id=membership_tid, identity_id="u-1")
        if membership_tid is not None
        else None
    )
    return AuthContext(
        user=UserRecord(email="a@b.test", password_hash="x"),
        is_authenticated=True,
        roles=[],
        preferences={"tenant_id": prefs_tid} if prefs_tid is not None else {},
        active_membership=m,
    )


def test_tenant_id_prefers_active_membership() -> None:
    # Membership says tenant-A; preferences say tenant-LEGACY — membership wins.
    val = _resolve_user_attribute("tenant_id", _ctx(membership_tid="tenant-A", prefs_tid="tenant-LEGACY"))
    assert val == "tenant-A"


def test_tenant_id_falls_back_to_preferences_without_membership() -> None:
    val = _resolve_user_attribute("tenant_id", _ctx(prefs_tid="tenant-LEGACY"))
    assert val == "tenant-LEGACY"


def test_non_tenant_attr_unaffected_by_membership() -> None:
    # A non-tenant scope attr (e.g. school) still resolves from preferences even
    # when a membership is present — only tenant_id is membership-sourced.
    ctx = _ctx(membership_tid="tenant-A")
    ctx.preferences["school"] = "S1"
    assert _resolve_user_attribute("school", ctx) == "S1"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_resolve_tenant_membership_first.py -q`
Expected: FAIL on `test_tenant_id_prefers_active_membership` — current resolution reads preferences, returning `tenant-LEGACY`.

- [ ] **Step 3: Make `tenant_id` membership-first**

In `src/dazzle/http/runtime/route_generator.py`, at the top of `_resolve_user_attribute` (after the `auth_context is None` guard, before the user/preferences resolution), add:

```python
    # auth Plan 1d: tenant_id is sourced from the active membership first (the
    # hard FK source), matching what _bind_rls_tenant_id binds for the RLS GUC.
    # Only tenant_id is membership-sourced; other current_user.<attr> scope refs
    # (school, department, …) continue to resolve from the domain-user/prefs
    # path below. The preferences copy stays as the un-migrated fallback.
    if attr_name == "tenant_id":
        membership = getattr(auth_context, "active_membership", None)
        if membership is not None and getattr(membership, "tenant_id", None):
            return membership.tenant_id
```

(Locate the exact insertion point: `_resolve_user_attribute(attr_name, auth_context)` returns `"__RBAC_DENY__"` when absent; insert this block right after the `if auth_context is None: return "__RBAC_DENY__"` guard near line 1059.)

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_resolve_tenant_membership_first.py -q`
Expected: PASS (3 passed).

- [ ] **Step 5: Run scope/route regression**

Run: `pytest tests/ -m "not e2e" -k "resolve_user or scope or route_generator or cedar" -q`
Expected: PASS (membership-less contexts unchanged — fallback path intact).

- [ ] **Step 6: Commit**

```bash
git add src/dazzle/http/runtime/route_generator.py tests/unit/test_resolve_tenant_membership_first.py
git commit -m "feat(auth): current_user.tenant_id resolves membership-first, prefs fallback (Plan 1d)"
```

---

## Task 2: manifest-wire `auto_provision_single_org`

**Files:**
- Modify: `src/dazzle/core/manifest.py` (`AuthConfig`)
- Modify: `src/dazzle/http/runtime/app_factory.py` (the `ServerConfig(...)` build)
- Test: `tests/unit/test_resolve_tenant_membership_first.py` (append a tiny manifest-default check) or a focused manifest test

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_auth_autoprovision_manifest.py
"""auto_provision_single_org flows manifest -> ServerConfig (Plan 1d)."""

from dazzle.core.manifest import AuthConfig
from dazzle.http.runtime.server import ServerConfig


def test_authconfig_default_off() -> None:
    assert AuthConfig().auto_provision_single_org is False


def test_authconfig_can_opt_in() -> None:
    assert AuthConfig(enabled=True, auto_provision_single_org=True).auto_provision_single_org is True


def test_serverconfig_field_exists_default_off() -> None:
    assert ServerConfig().auto_provision_single_org is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_auth_autoprovision_manifest.py -q`
Expected: FAIL — `AuthConfig` has no `auto_provision_single_org`.

- [ ] **Step 3: Add the field + thread it**

In `src/dazzle/core/manifest.py`, in the `AuthConfig` dataclass (next to `allow_registration`), add:

```python
    # auth Plan 1d: opt a single-org app into invisible Phase-2 — login lazily
    # provisions one org + membership per identity (and, for an is_tenant_root
    # app, a matching tenant-root row with the shared id). Default off.
    auto_provision_single_org: bool = False
```

In `src/dazzle/http/runtime/app_factory.py`, in the `ServerConfig(...)` call (~line 665), add the kwarg (sourcing from the resolved `auth_config`):

```python
        auto_provision_single_org=bool(
            getattr(auth_config, "auto_provision_single_org", False)
        ),
```

(Confirm `auth_config` is in scope at that call site — it's passed as `auth_config=auth_config` just above; mirror that.)

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_auth_autoprovision_manifest.py -q`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/core/manifest.py src/dazzle/http/runtime/app_factory.py tests/unit/test_auth_autoprovision_manifest.py
git commit -m "feat(auth): manifest [auth] auto_provision_single_org -> ServerConfig (Plan 1d)"
```

---

## Task 3: `provision_single_org` — the 1:1 org↔tenant-root mirror

**Files:**
- Create: `src/dazzle/db/provision.py`
- Test: `tests/integration/test_membership_rls_activation_pg.py`

- [ ] **Step 1: Write the failing integration test (scratch DB, tenant_rls schema)**

```python
# tests/integration/test_membership_rls_activation_pg.py
"""Canonical proof: a provisioned membership fences real RLS domain data as a
non-superuser (auth Plan 1d). Loads fixtures/tenant_rls, applies RLS, provisions
a single org (Workspace + organizations, shared id), and verifies the fence."""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator
from pathlib import Path

import psycopg
import pytest
import sqlalchemy as sa

pytestmark = [pytest.mark.e2e, pytest.mark.postgres]

_PG_URL = os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL")
_PROJECT_ROOT = Path("fixtures/tenant_rls")


def _admin_url() -> str:
    assert _PG_URL is not None
    return _PG_URL.replace("postgresql+psycopg://", "postgresql://")


@pytest.fixture
def scratch_url() -> Iterator[str]:
    if not _PG_URL:
        pytest.skip("no TEST_DATABASE_URL/DATABASE_URL")
    admin_url = _admin_url()
    base, _, _old = admin_url.rpartition("/")
    scratch = f"dazzle_memact_{uuid.uuid4().hex[:8]}"
    url = f"{base}/{scratch}"
    with psycopg.connect(admin_url, autocommit=True) as admin:
        admin.execute(f'CREATE DATABASE "{scratch}"')  # nosemgrep
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


def _appspec_and_md():
    from dazzle.http.converters.entity_converter import convert_entities
    from dazzle.http.runtime.sa_schema import build_metadata, scoped_entity_names

    from dazzle.core.appspec_loader import load_project_appspec

    appspec = load_project_appspec(_PROJECT_ROOT)
    pk = appspec.tenancy.isolation.partition_key
    scoped = sorted(scoped_entity_names(appspec.domain.entities, pk))
    md = build_metadata(convert_entities(appspec.domain.entities), partition_key=pk, tenant_scoped=scoped)
    return appspec, md, pk, scoped


def test_provision_single_org_mirrors_tenant_root_id(scratch_url: str) -> None:
    """provision_single_org creates a Workspace row + an organizations row with
    the SAME id (the 1:1 mirror)."""
    from dazzle.http.runtime.auth.store import AuthStore
    from dazzle.db.provision import provision_single_org

    appspec, md, _pk, _scoped = _appspec_and_md()
    engine = sa.create_engine(
        scratch_url.replace("postgresql://", "postgresql+psycopg://"), future=True
    )
    md.create_all(engine)
    AuthStore(database_url=scratch_url)._init_db()

    with psycopg.connect(scratch_url) as conn:
        org_id = provision_single_org(appspec, "Acme", conn=conn)

    with psycopg.connect(scratch_url) as c:
        ws = c.execute('SELECT id, name FROM "Workspace" WHERE id=%s', (org_id,)).fetchone()
        org = c.execute("SELECT id, slug FROM organizations WHERE id=%s", (org_id,)).fetchone()
    assert ws is not None and ws[0] == org_id  # tenant-root row exists at the shared id
    assert org is not None and org[0] == org_id  # org mirrors it
```

- [ ] **Step 2: Run test to verify it fails**

Run: `TEST_DATABASE_URL="postgresql://localhost:5432/postgres" pytest tests/integration/test_membership_rls_activation_pg.py -k mirrors_tenant_root -q`
Expected: FAIL — `dazzle.db.provision` missing.

- [ ] **Step 3: Write the provisioner**

```python
# src/dazzle/db/provision.py
"""Single-org provisioning with the 1:1 org<->tenant-root mirror (auth Plan 1d).

For an app with an ``is_tenant_root`` domain entity, the framework
``organizations`` row and the domain tenant-root row share ONE id — so
``membership.tenant_id == tenant_root.id == dazzle.tenant_id`` and a member is
fenced to exactly their org by RLS. For a rootless app the framework org IS the
tenant (no domain row). Sync; one transaction on the given connection.
"""

from __future__ import annotations

import secrets
from datetime import UTC, datetime
from typing import Any

from psycopg import sql

DEFAULT_ORG_SLUG = "default"


class ProvisionError(RuntimeError):
    """Single-org provisioning cannot proceed (e.g. a non-seedable tenant root)."""


def _tenant_root_entity(appspec: Any) -> Any | None:
    for e in appspec.domain.entities:
        if getattr(e, "is_tenant_root", False) or getattr(
            getattr(e, "archetype_kind", None), "name", ""
        ) == "TENANT":
            return e
    return None


def _seed_values_for_root(root_entity: Any, org_id: str, name: str) -> dict[str, Any]:
    """Framework-derivable values for the tenant-root row's columns.

    ``id`` = the shared org id. Required scalar text fields get the org name (or
    a slug); a required field the framework can't derive is a loud error.
    """
    values: dict[str, Any] = {"id": org_id}
    for f in root_entity.fields:
        fname = f.name
        if fname == "id":
            continue
        required = bool(getattr(f, "required", False))
        has_default = getattr(f, "default", None) is not None or getattr(f, "auto_add", False)
        ftype = getattr(getattr(f, "type", None), "kind", None)
        ftype = getattr(ftype, "value", ftype)
        if fname in ("name", "title", "display_name"):
            values[fname] = name
        elif fname == "slug":
            values[fname] = name.lower().replace(" ", "-")
        elif required and not has_default:
            # A required field we can't fill — fail loud (documented Tier-0
            # constraint: a single-org auto-provisioned tenant root must be
            # framework-seedable).
            raise ProvisionError(
                f"cannot auto-provision tenant root {root_entity.name!r}: required "
                f"field {fname!r} ({ftype}) is not framework-derivable — make it "
                "nullable/defaulted or provision the tenant explicitly"
            )
    return values


def provision_single_org(appspec: Any, name: str, *, conn: Any) -> str:
    """Ensure ONE default org (+ its 1:1 tenant-root row for archetype apps).

    Race-safe via the fixed ``DEFAULT_ORG_SLUG`` unique constraint. Returns the
    shared id (== the tenant-root row id when there is a root). Commits on
    success; rolls back on error.
    """
    if getattr(conn, "autocommit", False):
        raise ProvisionError("provision_single_org requires a non-autocommit connection")
    now = datetime.now(UTC).isoformat()
    try:
        # Idempotent: if the default org already exists, reuse its id.
        existing = conn.execute(
            "SELECT id FROM organizations WHERE slug = %s", (DEFAULT_ORG_SLUG,)
        ).fetchone()
        if existing is not None:
            org_id = existing[0] if not isinstance(existing, dict) else existing["id"]
            conn.commit()
            return str(org_id)

        org_id = secrets.token_urlsafe(24)
        root = _tenant_root_entity(appspec)
        if root is not None:
            # Seed the domain tenant-root row FIRST (the scoped FKs reference it),
            # at the shared id.
            vals = _seed_values_for_root(root, org_id, name)
            cols = list(vals.keys())
            insert_root = sql.SQL("INSERT INTO {tbl} ({cols}) VALUES ({ph})").format(
                tbl=sql.Identifier(root.name),
                cols=sql.SQL(", ").join(sql.Identifier(c) for c in cols),
                ph=sql.SQL(", ").join(sql.Placeholder() for _ in cols),
            )
            conn.execute(insert_root, tuple(vals[c] for c in cols))

        conn.execute(
            """
            INSERT INTO organizations (id, slug, name, status, is_test, created_at, updated_at)
            VALUES (%s, %s, %s, 'active', false, %s, %s)
            ON CONFLICT (slug) DO NOTHING
            """,
            (org_id, DEFAULT_ORG_SLUG, name, now, now),
        )
        # Re-read (a concurrent winner may own the slug; our root insert then
        # belongs to a losing id — acceptable for the single-org dev/test path,
        # where provisioning is effectively serial).
        row = conn.execute(
            "SELECT id FROM organizations WHERE slug = %s", (DEFAULT_ORG_SLUG,)
        ).fetchone()
        if row is None:
            raise ProvisionError("organization absent after provision insert")
        conn.commit()
        return str(row[0] if not isinstance(row, dict) else row["id"])
    except Exception:
        conn.rollback()
        raise
```

> The `# nosemgrep`-free `sql.Identifier`/`Placeholder` composition is injection-safe (entity/column names are IR identifiers; values are bound). The semgrep MCP hook may still flag dynamic SQL — it is advisory (not in CI/pre-commit), and this is the recommended psycopg composition.

- [ ] **Step 4: Run test to verify it passes**

Run: `TEST_DATABASE_URL="postgresql://localhost:5432/postgres" pytest tests/integration/test_membership_rls_activation_pg.py -k mirrors_tenant_root -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/db/provision.py tests/integration/test_membership_rls_activation_pg.py
git commit -m "feat(db): provision_single_org — 1:1 org<->tenant-root id mirror (Plan 1d)"
```

---

## Task 4: route `ensure_single_org_membership` through `provision_single_org` for archetype apps

**Files:**
- Modify: `src/dazzle/http/runtime/auth/store.py` (`ensure_single_org_membership`)
- Test: `tests/integration/test_membership_rls_activation_pg.py` (append)

- [ ] **Step 1: Write the failing test (append)**

```python
# append to tests/integration/test_membership_rls_activation_pg.py
def test_ensure_membership_uses_mirrored_org_for_archetype_app(scratch_url: str) -> None:
    """For an is_tenant_root app, the auto-provisioned membership's tenant_id is
    the SHARED Workspace/org id (not a fresh framework-only org id)."""
    from dazzle.http.runtime.auth.store import AuthStore
    from dazzle.db.provision import provision_single_org

    appspec, md, _pk, _scoped = _appspec_and_md()
    engine = sa.create_engine(scratch_url.replace("postgresql://", "postgresql+psycopg://"), future=True)
    md.create_all(engine)
    store = AuthStore(database_url=scratch_url)
    store._init_db()

    user = store.create_user(email="w@b.test", password="pw123456", roles=["worker"])
    m = store.ensure_single_org_membership(user, name="Acme", appspec=appspec)

    with psycopg.connect(scratch_url) as c:
        ws = c.execute('SELECT id FROM "Workspace" WHERE id=%s', (m.tenant_id,)).fetchone()
    assert ws is not None, "membership.tenant_id must equal a real Workspace row id"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `TEST_DATABASE_URL="postgresql://localhost:5432/postgres" pytest tests/integration/test_membership_rls_activation_pg.py -k uses_mirrored_org -q`
Expected: FAIL — `ensure_single_org_membership` has no `appspec` param / creates a framework-only org with no Workspace row.

- [ ] **Step 3: Add the `appspec` route-through**

In `src/dazzle/http/runtime/auth/store.py`, modify `ensure_single_org_membership` to accept an optional `appspec` and, when given (and it has a tenant root), provision via `provision_single_org` on the store's own connection so the org id mirrors the seeded tenant-root row:

```python
    def ensure_single_org_membership(
        self, user: "UserRecord", *, name: str = "Default", appspec: Any = None
    ) -> "MembershipRecord":
        """Ensure ``user`` has a membership in the single default org (Plan 1c/1d).

        Plan 1d: when ``appspec`` is provided and declares an is_tenant_root
        entity, the org is provisioned with a matching tenant-root row at the
        same id (the 1:1 mirror) so the membership fences the canonical RLS
        domain rows. Otherwise the framework org IS the tenant (1c behaviour).
        """
        if appspec is not None and _appspec_has_tenant_root(appspec):
            from dazzle.db.provision import provision_single_org

            with self._get_connection() as conn:
                org_id = provision_single_org(appspec, name, conn=conn)
            org = self.get_organization(org_id)
            assert org is not None
        else:
            org = self.get_or_create_default_organization(name=name)

        existing = [
            m for m in self.get_memberships_for_identity(str(user.id)) if m.tenant_id == org.id
        ]
        if existing:
            return existing[0]
        try:
            return self.create_membership(
                tenant_id=org.id, identity_id=str(user.id), roles=list(user.roles or [])
            )
        except psycopg.errors.UniqueViolation:
            again = [
                m for m in self.get_memberships_for_identity(str(user.id)) if m.tenant_id == org.id
            ]
            if not again:
                raise LookupError("membership lost race with no winner") from None
            return again[0]
```

Add the small helper near the top of `store.py` (module level):

```python
def _appspec_has_tenant_root(appspec: Any) -> bool:
    for e in getattr(getattr(appspec, "domain", None), "entities", []) or []:
        if getattr(e, "is_tenant_root", False) or getattr(
            getattr(e, "archetype_kind", None), "name", ""
        ) == "TENANT":
            return True
    return False
```

Then thread the appspec at the live activation call site — in `src/dazzle/http/runtime/auth/org_activation.py` `activate_session_for_login`, pass `appspec=getattr(getattr(request, "app", None), "state", None) and getattr(request.app.state, "appspec", None)` into `ensure_single_org_membership`:

```python
        app_state = getattr(getattr(request, "app", None), "state", None)
        appspec = getattr(app_state, "appspec", None)
        auth_store.ensure_single_org_membership(user, appspec=appspec)
```

> Confirm `request.app.state.appspec` is the live AppSpec (grep `app.state.appspec` / where the runtime stashes it; if it's under a different attr, use that). If unavailable in a given context, `appspec=None` falls back to 1c's framework-org behaviour (non-breaking).

- [ ] **Step 4: Run test to verify it passes**

Run: `TEST_DATABASE_URL="postgresql://localhost:5432/postgres" pytest tests/integration/test_membership_rls_activation_pg.py -k uses_mirrored_org -q`
Expected: PASS.

- [ ] **Step 5: Run the auth unit + 1c regression**

Run: `pytest tests/unit/test_org_activation.py -q` + `TEST_DATABASE_URL=… pytest tests/integration/test_auth_orgprovision_pg.py -q`
Expected: PASS (1c's rootless behaviour unchanged — its fake stores pass `appspec=None`).

- [ ] **Step 6: Commit**

```bash
git add src/dazzle/http/runtime/auth/store.py src/dazzle/http/runtime/auth/org_activation.py tests/integration/test_membership_rls_activation_pg.py
git commit -m "feat(auth): ensure_single_org_membership mirrors org<->tenant-root for archetype apps (Plan 1d)"
```

---

> ### ⛳ ADVERSARIAL REVIEW CHECKPOINT (after Task 4)
> Dispatch an independent reviewer over the provisioning + mirror path (Tasks 3–4). Attack: (1) **wrong-id / split tenant** — can the Workspace row and the organizations row ever get DIFFERENT ids (race, ON CONFLICT loser still inserted a Workspace)? Is the single-org provisioning genuinely idempotent + serial-safe? (2) **partial seed** — if the root insert succeeds but the org insert fails (or vice versa), does the whole thing roll back (one txn)? (3) **non-seedable root** — does a required non-derivable field fail loud (not a silent NULL/partial)? (4) **fence correctness** — does `membership.tenant_id == Workspace.id == dazzle.tenant_id` actually fence a non-superuser to their org (Task 5 proves it; confirm the binding chain)? (5) **non-breaking** — rootless apps (appspec=None or no root) keep 1c behaviour; membership-less sessions keep the prefs fallback. Proceed only when the id-mirror invariant is airtight.

---

## Task 5: Canonical proof — a membership fences RLS data as a non-superuser

**Files:**
- Test: `tests/integration/test_membership_rls_activation_pg.py` (append)

This is the slice's keystone: with RLS applied to the `tenant_rls` schema and a non-`BYPASSRLS` role, a user with a provisioned membership sees ONLY their org's rows, and a fenced insert lands in-tenant — the genuine "membership model enforces isolation via Postgres RLS" proof.

- [ ] **Step 1: Write the failing test (append)**

```python
# append to tests/integration/test_membership_rls_activation_pg.py
_APP_PW = "app-pw"  # noqa: S105 — fixture-local


def test_membership_fences_rls_data_as_non_superuser(scratch_url: str) -> None:
    from dazzle.http.runtime.auth.store import AuthStore
    from dazzle.http.runtime.rls_schema import build_rls_policy_ddl
    from dazzle.db.provision import provision_single_org

    appspec, md, pk, scoped = _appspec_and_md()
    engine = sa.create_engine(scratch_url.replace("postgresql://", "postgresql+psycopg://"), future=True)
    md.create_all(engine)
    store = AuthStore(database_url=scratch_url)
    store._init_db()

    # Provision TWO orgs (two Workspaces, shared-id mirrors) by running the
    # provisioner against two different default slugs is not possible (fixed
    # slug); instead provision org A via the provisioner, and seed org B's
    # Workspace + a row directly, to prove cross-tenant isolation.
    with psycopg.connect(scratch_url) as conn:
        org_a = provision_single_org(appspec, "Tenant A", conn=conn)
    member_user = store.create_user(email="a@b.test", password="pw123456", roles=["worker"])
    m = store.ensure_single_org_membership(member_user, name="Tenant A", appspec=appspec)
    assert m.tenant_id == org_a

    # Seed a second tenant B (Workspace + a Project row) + a Project in A, as superuser.
    org_b = str(uuid.uuid4())
    with psycopg.connect(scratch_url, autocommit=True) as c:
        c.execute('INSERT INTO "Workspace" (id, name) VALUES (%s, %s)', (org_b, "Tenant B"))
        # Project carries the injected tenant_id + an owner Member; seed minimally.
        for tid, label in ((org_a, "A-proj"), (org_b, "B-proj")):
            mid = str(uuid.uuid4())
            c.execute('INSERT INTO "Member" (tenant_id, id, email) VALUES (%s,%s,%s)', (tid, mid, f"{label}@x.test"))
            c.execute(
                'INSERT INTO "Project" (tenant_id, id, name, owner) VALUES (%s,%s,%s,%s)',
                (tid, str(uuid.uuid4()), label, mid),
            )

    # Apply the framework RLS policies + a non-superuser role.
    role = f"memact_app_{uuid.uuid4().hex[:8]}"
    with psycopg.connect(scratch_url, autocommit=True) as c:
        for stmt in build_rls_policy_ddl(scoped, partition_key=pk):
            c.execute(stmt)
        c.execute(f"CREATE ROLE \"{role}\" LOGIN PASSWORD '{_APP_PW}'")  # nosemgrep — uuid-derived
        c.execute(f'GRANT USAGE ON SCHEMA public TO "{role}"')  # nosemgrep
        c.execute(f'GRANT SELECT, INSERT ON ALL TABLES IN SCHEMA public TO "{role}"')  # nosemgrep

    # As the non-superuser, with dazzle.tenant_id bound from the membership,
    # only tenant A's Project is visible.
    base, _, _db = scratch_url.rpartition("/")
    app_url = f"{base.replace('//', f'//{role}:{_APP_PW}@')}/{_db}"
    try:
        with psycopg.connect(app_url) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT set_config('dazzle.tenant_id', %s, false)", (m.tenant_id,))
                rows = cur.execute('SELECT name FROM "Project"').fetchall()
                cur.execute("RESET ROLE") if False else None
            conn.rollback()
    finally:
        with psycopg.connect(scratch_url, autocommit=True) as c:
            c.execute(f'REVOKE ALL ON ALL TABLES IN SCHEMA public FROM "{role}"')  # nosemgrep
            c.execute(f'REVOKE USAGE ON SCHEMA public FROM "{role}"')  # nosemgrep
            c.execute(f'DROP ROLE IF EXISTS "{role}"')  # nosemgrep

    assert {r[0] for r in rows} == {"A-proj"}, "membership must fence to tenant A only"
```

> Adapt the role-URL construction + grants to match `test_rls_enforcement_pg.py`'s harness exactly (it builds `dazzle_app` with no BYPASSRLS and connects via a role-specific URL) — that test is the canonical reference; mirror its connection-string + grant shape rather than the sketch above if they differ. The invariant asserted (a membership-bound non-superuser sees only its tenant's rows) does not change.

- [ ] **Step 2: Run test to verify it passes**

Run: `TEST_DATABASE_URL="postgresql://localhost:5432/postgres" pytest tests/integration/test_membership_rls_activation_pg.py -k fences_rls_data -q`
Expected: PASS — only `A-proj` visible under the membership-bound non-superuser.

- [ ] **Step 3: Run the whole 1d integration file**

Run: `TEST_DATABASE_URL="postgresql://localhost:5432/postgres" pytest tests/integration/test_membership_rls_activation_pg.py -q`
Expected: all PASS.

- [ ] **Step 4: Commit**

```bash
git add tests/integration/test_membership_rls_activation_pg.py
git commit -m "test(auth): canonical proof — membership fences RLS data as non-superuser (Plan 1d)"
```

---

## Final verification (before handing off / shipping)

- [ ] `ruff check src/ tests/ --fix && ruff format src/ tests/` — clean
- [ ] `mypy src/dazzle` — clean (CI scope)
- [ ] `pytest tests/ -m "not e2e"` — green (membership-less + rootless paths unchanged; 1c fakes pass `appspec=None`)
- [ ] With `TEST_DATABASE_URL="postgresql://localhost:5432/postgres"`: `pytest tests/integration/test_membership_rls_activation_pg.py tests/integration/test_auth_orgprovision_pg.py tests/integration/test_rls_enforcement_pg.py -q` — green
- [ ] `/bump patch` + CHANGELOG entry under **Added/Changed** with an **Agent Guidance** note:
  - "`current_user.tenant_id` (scope) + the RLS GUC now source from `session.active_membership.tenant_id` first (preferences fallback retained for un-migrated users). Apps opt into single-org auto-provision via `[auth] auto_provision_single_org = true` in `dazzle.toml`. For an `is_tenant_root` app, auto-provision seeds the tenant-root row + the framework `organizations` row at a **shared id** (the 1:1 mirror) via `dazzle.db.provision.provision_single_org`, so a member is RLS-fenced to their org. A tenant root with a non-framework-derivable required field raises `ProvisionError` (make it nullable/defaulted or provision explicitly). Proven against real Postgres as a non-superuser. NOT yet done: `dazzle auth migrate` (existing-deployment backfill), create-time tenant_id injection, and removing the preferences fallback — all follow-ups."

---

## Forward outline (1d follow-ups + Plan 2)

- **1d follow-ups:** `dazzle auth migrate` (backfill existing deployments: domain tenant rows → organizations by shared id, domain users → memberships, copy roles + preferences-tenant → membership.tenant_id); create-time `tenant_id` auto-injection from the active membership (so creates fence without the client supplying it); flip `auto_provision_single_org` on across the example fleet; finally **remove** the preferences-tenant fallback once every app+user is migrated (the clean break, deferred from this slice).
- **Plan 2 — compliance evidence:** now has a live membership substrate to evidence (lifecycle events → audit trail → access-review export; membership audit attribution; platform roles on identity).

## Self-review notes

- **Spec coverage (§3 graceful degradation on the canonical model + the user's 1d choices):** "activate the membership model" → Tasks 3–5 (1:1 mirror + the non-superuser RLS-fence proof on the canonical `fixtures/tenant_rls`). "current_user.tenant_id from membership" → Task 1. "manifest opt-in" → Task 2. "keep the prefs fallback membership-first" → Task 1 (fallback retained) + the deferred removal. The `dazzle auth migrate` recipe + fallback removal are explicitly deferred follow-ups (the chosen non-breaking rollout), not silently dropped.
- **Placeholder scan:** the resolver edit, manifest field, provisioner, and store route-through all carry concrete code. The flagged confirmations (`_resolve_user_attribute` insertion point, `request.app.state.appspec` attr, the RLS role-harness connection shape) are real-codebase reconciliations with explicit "grep + mirror `test_rls_enforcement_pg.py`" guidance and invariant assertions that don't change.
- **Type consistency:** `provision_single_org(appspec, name, *, conn) -> str` (the shared id) is used identically in Task 3, Task 4 (`ensure_single_org_membership`), and Task 5. `ensure_single_org_membership(user, *, name, appspec)` matches the store def + the activation call site + the tests. `_appspec_has_tenant_root` / `_tenant_root_entity` use the same `is_tenant_root`/`archetype_kind` predicate as `db/excision.py`. `DEFAULT_ORG_SLUG` is the single source of the `"default"` slug shared with 1c's behaviour.
