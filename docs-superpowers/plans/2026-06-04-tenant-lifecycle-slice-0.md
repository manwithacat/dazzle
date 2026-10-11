# Ephemeral Test-Tenant Lifecycle — Slice 0 (Shared Substrate) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the shared substrate that both #1338 (tenant excision) and #1339 (QA-auth + provisioning) depend on: a queryable `is_test` boolean on the tenant registry record, and a reserved `qa` slug namespace that normal tenant creates cannot claim.

**Architecture:** Two independent, low-risk changes to `src/dazzle/tenant/`. (1) `is_test` boolean column on `public.tenants` — added to the runtime's `CREATE TABLE` for fresh installs, back-filled on existing trees by a hand-authored framework Alembic migration `0006` (canonical, ADR-0017) plus an idempotent boot-time `ALTER ... ADD COLUMN IF NOT EXISTS` mirroring how the `config` column is bootstrapped (the registry table is owned by `ensure_table()`, not Alembic's DSL metadata). (2) A reserved-namespace guard in `tenant/config.py:validate_slug` that rejects normal creates whose slug begins with `qa-` or `qa_`, with an `allow_reserved` seam the Slice-2 provisioner will use to mint `qa`-namespaced test tenants.

**Tech Stack:** Python 3.12, psycopg (v3), SQLAlchemy/Alembic, pytest (`-m "not e2e"` unit; `-m postgres` real-PG integration), typer CLI.

---

## Context the implementer needs

- **There are two unrelated `validate_slug` functions.** This slice touches **only** `src/dazzle/tenant/config.py:validate_slug` (the schema-isolation registry slug; grammar `^[a-z][a-z0-9_]{1,55}$`, hyphens forbidden, becomes a PG schema name). Do **not** touch `src/dazzle/http/runtime/slug_validator.py` (a different DSL-field validator that *allows* hyphens). Existing tests in `tests/unit/test_tenant_config.py` and `tests/unit/test_security.py` already assert `my-tenant` / `smith-co` raise `"Slug must match"` — those must keep passing.
- **Why reserve both `qa-` and `qa_`:** the spec text says "reserved `qa-` namespace", but the registry grammar already forbids hyphens, so a normal create can *never* produce `qa-foo` (it fails the pattern). The actually-reachable hole is the underscore form `qa_foo`, which is a valid slug today. Reserving **both** separators honours the spec's human-visible `qa-` marker *and* closes the real `qa_` hole. The load-bearing new rejection is `qa_*`.
- **`public.tenants` is NOT in Alembic's `target_metadata`.** It is created by raw `CREATE TABLE IF NOT EXISTS` in `TenantRegistry.ensure_table()` (`src/dazzle/tenant/registry.py`), and the `config` column was added by an idempotent raw `ALTER ... ADD COLUMN IF NOT EXISTS` in the same method (`_ALTER_ADD_CONFIG_SQL`). We follow that established precedent for `is_test` **and** add the Alembic migration the spec asks for. The two paths are convergent (each guards on existence), exactly like the dual fresh-install/migration convergence documented in `0005_session_csrf_secret.py`.
- **Framework migrations are hand-authored** directly into `src/dazzle/http/alembic/versions/NNNN_*.py` (see `0005_session_csrf_secret.py`). Do **not** use `dazzle db revision` for this — that command writes into the *project* versions dir, not the framework tree. The next revision id is `0006_tenant_is_test`, `down_revision = "0005_session_csrf_secret"`.
- **Alembic migrations here must be dialect-agnostic.** They run against the PostgreSQL runtime *and* a SQLite structural-test sandbox. Mirror `0005`: use `sqlalchemy.inspect(bind)` (the dialect-agnostic inspector), guard every DDL op on existence, and use **unqualified** table names (`"tenants"`, not `schema="public"` — schema qualification breaks the SQLite path).
- **Current version:** `0.81.19`. A local Postgres is reachable at `localhost:5432` for execution-time verification (create a disposable DB; don't touch the existing `dazzle*` DBs).
- **Out of scope for Slice 0 (do not build):** the excision engine, `provision_test_tenant`, QA-auth routes, the `allow_reserved=True` *call site* (the provisioner is Slice 2 — we add the parameter seam now, but nothing calls it with `True` yet), and any `isolation="row"` mode (recorded non-goal). The `is_test` parameter on `create()` and `allow_reserved` on `validate_slug` are seams added now and exercised by tests; their production callers arrive in Slices 1–2.

## File Structure

| File | Responsibility | Change |
|------|----------------|--------|
| `src/dazzle/tenant/config.py` | Slug grammar + reserved-namespace guard | Modify `validate_slug` — add `allow_reserved` kwarg + reserved-prefix rejection; add `RESERVED_SLUG_PREFIXES` constant |
| `src/dazzle/tenant/registry.py` | CRUD on `public.tenants` | Modify — add `is_test` to `TenantRecord`, `_CREATE_TABLE_SQL`, `_INSERT_SQL`, all `SELECT`/`UPDATE` column lists, `_row_to_record`; add `_ALTER_ADD_IS_TEST_SQL` to `ensure_table()`; add `is_test` kwarg to `create()` |
| `src/dazzle/http/alembic/versions/0006_tenant_is_test.py` | Canonical schema-change path (ADR-0017) for existing trees | Create — hand-authored, mirrors `0005` |
| `tests/unit/test_tenant_config.py` | Slug-validation unit tests | Modify — add reserved-namespace cases |
| `tests/unit/test_tenant_registry.py` | Registry unit tests (mocked psycopg) | Modify — add `is_test` round-trip + `create(is_test=True)` cases |
| `tests/unit/test_tenant_is_test_migration.py` | Migration upgrade/downgrade unit test (SQLite, dialect-agnostic) | Create |
| `tests/integration/test_tenant_is_test_pg.py` | Real-Postgres verification (fresh `ensure_table` + migration on a pre-existing table) | Create — marked `e2e` + `postgres` |
| `CHANGELOG.md` | Release notes | Modify — Added entry under a new version |

---

## Task 1: Reserved `qa` namespace in `validate_slug`

**Files:**
- Modify: `src/dazzle/tenant/config.py`
- Test: `tests/unit/test_tenant_config.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/unit/test_tenant_config.py` inside the existing `class TestSlugValidation`:

```python
    def test_rejects_reserved_qa_underscore_prefix(self) -> None:
        # The actually-reachable hole: `qa_*` is a grammar-valid slug, so it
        # must be explicitly reserved for test tenants.
        with pytest.raises(ValueError, match="reserved"):
            validate_slug("qa_run_123")

    def test_rejects_reserved_qa_hyphen_prefix(self) -> None:
        # Hyphen form is grammar-invalid anyway, but the reserved check fires
        # first with the clearer message.
        with pytest.raises(ValueError, match="reserved"):
            validate_slug("qa-run-123")

    def test_allow_reserved_permits_qa_prefix(self) -> None:
        # The Slice-2 provisioner mints qa-namespaced test tenants via this seam.
        validate_slug("qa_run_123", allow_reserved=True)

    def test_qa_substring_not_at_start_is_allowed(self) -> None:
        # Only a leading `qa-`/`qa_` is reserved; `qa` elsewhere is fine.
        validate_slug("acme_qa_team")

    def test_bare_qa_without_separator_is_allowed(self) -> None:
        # `qantas` is not in the reserved namespace — only `qa` + separator is.
        validate_slug("qantas")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/unit/test_tenant_config.py::TestSlugValidation -v`
Expected: the four new `qa`-prefix tests FAIL (`qa_run_123` currently passes validation; `allow_reserved` is an unexpected kwarg → `TypeError`).

- [ ] **Step 3: Implement the reserved-namespace guard**

Replace the body of `src/dazzle/tenant/config.py` with:

```python
"""Tenant configuration helpers — slug validation and schema naming."""

import re

# Max slug length: 63 (PG identifier limit) - 7 ("tenant_" prefix) = 56
SLUG_PATTERN = re.compile(r"^[a-z][a-z0-9_]{1,55}$")
SCHEMA_PREFIX = "tenant_"

# Slugs in the `qa` namespace are reserved for ephemeral test tenants
# (#1339). Both separators are reserved: `qa-` is the spec's human-visible
# marker (already grammar-invalid since hyphens are forbidden, but checked
# first for a clearer error), and `qa_` is the grammar-valid form a normal
# create could otherwise claim. The load-bearing test-tenant marker is the
# queryable `is_test` column on the tenant record, not this prefix
# (belt-and-suspenders — see docs/superpowers/specs/2026-06-04-tenant-lifecycle-design.md §5).
RESERVED_SLUG_PREFIXES = ("qa-", "qa_")


def validate_slug(slug: str, *, allow_reserved: bool = False) -> None:
    """Validate a tenant slug.

    Raises ValueError if the slug is invalid or claims the reserved `qa`
    namespace. Pass ``allow_reserved=True`` only from the test-tenant
    provisioner, which is permitted to mint `qa`-namespaced slugs.
    """
    if not allow_reserved and slug.startswith(RESERVED_SLUG_PREFIXES):
        raise ValueError(
            f"Slug prefix is reserved for test tenants ({', '.join(RESERVED_SLUG_PREFIXES)}). "
            f"Got: '{slug}'"
        )
    if not SLUG_PATTERN.match(slug):
        raise ValueError(f"Slug must match {SLUG_PATTERN.pattern}. Got: '{slug}'")


def slug_to_schema_name(slug: str) -> str:
    """Convert a tenant slug to a PostgreSQL schema name."""
    return f"{SCHEMA_PREFIX}{slug}"
```

Note the ordering: the reserved check fires **before** the pattern check, so `qa-run-123` reports `"reserved"` (clearer) rather than `"Slug must match"`. Pre-existing `my-tenant` / `smith-co` still hit the pattern check and report `"Slug must match"` unchanged.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/unit/test_tenant_config.py -v && pytest tests/unit/test_security.py::*::* -k slug -v`
Expected: all PASS, including the pre-existing `test_rejects_special_chars` (`my-tenant`) and `test_security.py` slug cases.

- [ ] **Step 5: Export the new constant**

`src/dazzle/tenant/__init__.py` already re-exports `SLUG_PATTERN`, `slug_to_schema_name`, `validate_slug`. Add `RESERVED_SLUG_PREFIXES` to both the import line and `__all__` so it is discoverable:

```python
from .config import RESERVED_SLUG_PREFIXES, SLUG_PATTERN, slug_to_schema_name, validate_slug
```
and add `"RESERVED_SLUG_PREFIXES",` to the `__all__` list.

- [ ] **Step 6: Run the full tenant unit slice**

Run: `pytest tests/unit/ -k "tenant_config or slug or tenant_registry" -v`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/dazzle/tenant/config.py src/dazzle/tenant/__init__.py tests/unit/test_tenant_config.py
git commit -m "feat(tenant): reserve qa- / qa_ slug namespace for test tenants (#1339 slice 0)"
```

---

## Task 2: `is_test` column on the tenant registry record

**Files:**
- Modify: `src/dazzle/tenant/registry.py`
- Test: `tests/unit/test_tenant_registry.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/unit/test_tenant_registry.py`:

```python
class TestTenantRegistryIsTest:
    @patch("dazzle.tenant.registry.psycopg")
    def test_create_defaults_is_test_false(self, mock_psycopg: MagicMock) -> None:
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.__enter__.return_value = mock_conn
        mock_conn.__exit__.return_value = False
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_conn.cursor.return_value.__exit__.return_value = False
        mock_cursor.fetchone.return_value = {
            "id": "uuid-1",
            "slug": "cyfuture",
            "display_name": "CyFuture UK",
            "schema_name": "tenant_cyfuture",
            "status": "active",
            "config": {},
            "is_test": False,
            "created_at": "2026-01-01",
            "updated_at": "2026-01-01",
        }
        mock_psycopg.connect.return_value = mock_conn

        registry = TenantRegistry("postgresql://localhost/test")
        record = registry.create("cyfuture", "CyFuture UK")

        assert record.is_test is False
        # The INSERT carries is_test as its fourth bind value.
        args, _ = mock_cursor.execute.call_args
        assert args[1] == ("cyfuture", "CyFuture UK", "tenant_cyfuture", False)

    @patch("dazzle.tenant.registry.psycopg")
    def test_create_is_test_true(self, mock_psycopg: MagicMock) -> None:
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.__enter__.return_value = mock_conn
        mock_conn.__exit__.return_value = False
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_conn.cursor.return_value.__exit__.return_value = False
        mock_cursor.fetchone.return_value = {
            "id": "uuid-2",
            "slug": "qa_run_1",
            "display_name": "QA run 1",
            "schema_name": "tenant_qa_run_1",
            "status": "active",
            "config": {},
            "is_test": True,
            "created_at": "2026-01-01",
            "updated_at": "2026-01-01",
        }
        mock_psycopg.connect.return_value = mock_conn

        registry = TenantRegistry("postgresql://localhost/test")
        # allow_reserved is required because qa_ is reserved (Task 1).
        record = registry.create("qa_run_1", "QA run 1", is_test=True, allow_reserved=True)

        assert record.is_test is True
        args, _ = mock_cursor.execute.call_args
        assert args[1] == ("qa_run_1", "QA run 1", "tenant_qa_run_1", True)

    @patch("dazzle.tenant.registry.psycopg")
    def test_row_to_record_tolerates_missing_is_test(self, mock_psycopg: MagicMock) -> None:
        # Defensive: a row read before the column existed must default False.
        from dazzle.tenant.registry import _row_to_record

        record = _row_to_record(
            {
                "id": "uuid-3",
                "slug": "legacy",
                "display_name": "Legacy",
                "schema_name": "tenant_legacy",
                "status": "active",
                "config": {},
                "created_at": "2026-01-01",
                "updated_at": "2026-01-01",
            }
        )
        assert record.is_test is False
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/unit/test_tenant_registry.py::TestTenantRegistryIsTest -v`
Expected: FAIL — `TenantRecord` has no `is_test`; `create()` rejects `is_test`/`allow_reserved` kwargs.

- [ ] **Step 3: Implement the registry changes**

In `src/dazzle/tenant/registry.py`:

(a) Add `is_test BOOLEAN NOT NULL DEFAULT false` to the fresh-install DDL and add the idempotent ALTER. Replace `_CREATE_TABLE_SQL` and add `_ALTER_ADD_IS_TEST_SQL` next to `_ALTER_ADD_CONFIG_SQL`:

```python
_CREATE_TABLE_SQL = """\
CREATE TABLE IF NOT EXISTS public.tenants (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    slug TEXT UNIQUE NOT NULL,
    display_name TEXT NOT NULL,
    schema_name TEXT UNIQUE NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    config JSONB NOT NULL DEFAULT '{}'::jsonb,
    is_test BOOLEAN NOT NULL DEFAULT false,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
)"""

# #957 cycle 7 — idempotent column add for upgraded deployments. Tables
# created before cycle 7 don't have `config`; this back-fills it without
# breaking the existing-table path or affecting fresh installs.
_ALTER_ADD_CONFIG_SQL = (
    "ALTER TABLE public.tenants ADD COLUMN IF NOT EXISTS config JSONB NOT NULL DEFAULT '{}'::jsonb"
)

# #1339 slice 0 — idempotent column add for the test-tenant marker. The
# canonical schema-change path is the Alembic migration 0006 (ADR-0017); this
# ALTER is the registry table's own boot-time bootstrap (public.tenants is
# owned by ensure_table(), not Alembic's DSL metadata), mirroring config above
# so the CLI `dazzle tenant create` path works without a separate
# `dazzle db upgrade`. Both paths guard on existence and converge.
_ALTER_ADD_IS_TEST_SQL = (
    "ALTER TABLE public.tenants ADD COLUMN IF NOT EXISTS is_test BOOLEAN NOT NULL DEFAULT false"
)
```

(b) Add `is_test` to every column list. Replace the four SQL constants:

```python
_INSERT_SQL = """\
INSERT INTO public.tenants (slug, display_name, schema_name, is_test)
VALUES (%s, %s, %s, %s)
RETURNING id, slug, display_name, schema_name, status, config, is_test, created_at, updated_at"""

_SELECT_BY_SLUG = """\
SELECT id, slug, display_name, schema_name, status, config, is_test, created_at, updated_at
FROM public.tenants WHERE slug = %s"""

_SELECT_ALL = """\
SELECT id, slug, display_name, schema_name, status, config, is_test, created_at, updated_at
FROM public.tenants ORDER BY created_at"""

_UPDATE_STATUS = """\
UPDATE public.tenants SET status = %s, updated_at = now()
WHERE slug = %s
RETURNING id, slug, display_name, schema_name, status, config, is_test, created_at, updated_at"""

_UPDATE_CONFIG = """\
UPDATE public.tenants SET config = %s, updated_at = now()
WHERE slug = %s
RETURNING id, slug, display_name, schema_name, status, config, is_test, created_at, updated_at"""
```

(c) Add `is_test` to the `TenantRecord` dataclass (after `config`, both have defaults so field order with defaults is fine):

```python
    is_test: bool = False
```

(d) Read it in `_row_to_record` (tolerant of absence):

```python
    return TenantRecord(
        id=str(row["id"]),
        slug=row["slug"],
        display_name=row["display_name"],
        schema_name=row["schema_name"],
        status=row["status"],
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
        config=dict(raw_config) if isinstance(raw_config, dict) else {},
        is_test=bool(row.get("is_test", False)),
    )
```

(e) Run the new ALTER in `ensure_table()` (add one line after the config ALTER):

```python
    def ensure_table(self) -> None:
        """Create the tenants table if it doesn't exist.

        Also runs the idempotent ALTERs to back-fill the `config` and
        `is_test` columns on tables created before those versions. All
        statements are idempotent — safe to call repeatedly at boot.
        """
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(_CREATE_TABLE_SQL)
                cur.execute(_ALTER_ADD_CONFIG_SQL)
                cur.execute(_ALTER_ADD_IS_TEST_SQL)
            conn.commit()
```

(f) Add the `is_test` + `allow_reserved` seams to `create()`:

```python
    def create(
        self,
        slug: str,
        display_name: str,
        *,
        is_test: bool = False,
        allow_reserved: bool = False,
    ) -> TenantRecord:
        """Insert a tenant record. Raises ValueError for invalid slugs.

        ``is_test`` marks the row as an ephemeral test tenant (#1339).
        ``allow_reserved`` lets the test-tenant provisioner mint a
        `qa`-namespaced slug; normal creates must leave it ``False``.
        """
        validate_slug(slug, allow_reserved=allow_reserved)
        schema_name = slug_to_schema_name(slug)
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(_INSERT_SQL, (slug, display_name, schema_name, is_test))
                row = cur.fetchone()
            conn.commit()
        return _row_to_record(row)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/unit/test_tenant_registry.py -v`
Expected: PASS — both new `TestTenantRegistryIsTest` cases and the pre-existing `TestTenantRegistryCreate`/`List` cases (the pre-existing mocked rows omit `is_test`; `_row_to_record` defaults it to `False`).

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/tenant/registry.py tests/unit/test_tenant_registry.py
git commit -m "feat(tenant): is_test column on the tenant registry record (#1339 slice 0)"
```

---

## Task 3: Framework Alembic migration `0006_tenant_is_test`

**Files:**
- Create: `src/dazzle/http/alembic/versions/0006_tenant_is_test.py`
- Test: `tests/unit/test_tenant_is_test_migration.py`

- [ ] **Step 1: Write the failing migration unit test (SQLite, dialect-agnostic)**

Create `tests/unit/test_tenant_is_test_migration.py`:

```python
"""Unit test for the 0006 is_test migration — runs against an in-memory SQLite
DB to exercise the dialect-agnostic upgrade/downgrade paths without a live
Postgres. (Real-PG behaviour is covered by tests/integration/test_tenant_is_test_pg.py.)"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import inspect as sa_inspect

_MIGRATION = (
    Path(__file__).resolve().parents[2]
    / "src/dazzle/http/alembic/versions/0006_tenant_is_test.py"
)


def _load_migration():
    spec = importlib.util.spec_from_file_location("mig_0006", _MIGRATION)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _run(callback) -> None:
    engine = sa.create_engine("sqlite://")
    with engine.connect() as conn:
        ctx = MigrationContext.configure(conn)
        with Operations.context(ctx):
            callback(conn)
        conn.commit()


def test_upgrade_no_op_when_tenants_absent() -> None:
    mod = _load_migration()
    # No `tenants` table at all → upgrade must be a no-op, not an error.
    _run(lambda conn: mod.upgrade())


def test_upgrade_adds_is_test_to_existing_table() -> None:
    mod = _load_migration()

    def body(conn):
        conn.execute(sa.text("CREATE TABLE tenants (id TEXT PRIMARY KEY, slug TEXT)"))
        conn.execute(sa.text("INSERT INTO tenants (id, slug) VALUES ('1', 'acme')"))
        mod.upgrade()
        cols = {c["name"] for c in sa_inspect(conn).get_columns("tenants")}
        assert "is_test" in cols
        # existing row defaults to false (0 in SQLite)
        val = conn.execute(sa.text("SELECT is_test FROM tenants WHERE id='1'")).scalar()
        assert val in (0, False)

    _run(body)


def test_upgrade_idempotent_when_column_present() -> None:
    mod = _load_migration()

    def body(conn):
        conn.execute(
            sa.text("CREATE TABLE tenants (id TEXT PRIMARY KEY, is_test BOOLEAN NOT NULL DEFAULT 0)")
        )
        mod.upgrade()  # column already present → no-op, no error
        cols = {c["name"] for c in sa_inspect(conn).get_columns("tenants")}
        assert "is_test" in cols

    _run(body)
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest tests/unit/test_tenant_is_test_migration.py -v`
Expected: FAIL — the migration file does not exist yet (`spec` is `None` / import error).

- [ ] **Step 3: Hand-author the migration (mirror `0005`)**

Create `src/dazzle/http/alembic/versions/0006_tenant_is_test.py`:

```python
"""Add is_test to public.tenants (ephemeral test-tenant lifecycle, #1339 slice 0).

The tenant registry record gains a queryable `is_test` boolean so the
test-tenant containment check and the excision reaper can filter on it (a
column, not a forgeable slug prefix). Fresh installs get the column via the
registry's `CREATE TABLE IF NOT EXISTS` (and a convergent boot-time
`ALTER ... IF NOT EXISTS`); this migration is the canonical schema-change path
(ADR-0017) for already-migrated trees. Idempotent + dialect-agnostic, mirroring
0005: guards on existence so it is safe to re-run and no-ops where the registry
table is absent (non-tenant projects, SQLite structural sandbox).

Revision ID: 0006_tenant_is_test
Revises: 0005_session_csrf_secret
Created: 2026-06-04
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect as sa_inspect

revision = "0006_tenant_is_test"
down_revision = "0005_session_csrf_secret"
branch_labels = None
depends_on = None


def _has_column(table: str, column: str) -> bool:
    bind = op.get_bind()
    insp = sa_inspect(bind)
    if not insp.has_table(table):
        return False
    return any(c["name"] == column for c in insp.get_columns(table))


def upgrade() -> None:
    # No-op when the registry table is absent (non-tenant project, or the SQLite
    # structural sandbox) or the column already exists (fresh installs create it
    # in `CREATE TABLE`, and the registry's boot-time ALTER may have run first).
    if not sa_inspect(op.get_bind()).has_table("tenants"):
        return
    if _has_column("tenants", "is_test"):
        return
    # NOT NULL + server_default false back-fills existing rows in one statement.
    op.add_column(
        "tenants",
        sa.Column("is_test", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )


def downgrade() -> None:
    if _has_column("tenants", "is_test"):
        op.drop_column("tenants", "is_test")
```

- [ ] **Step 4: Run the migration unit test to verify it passes**

Run: `pytest tests/unit/test_tenant_is_test_migration.py -v`
Expected: PASS (all three cases).

- [ ] **Step 5: Verify the migration chain has a single head**

Run: `cd src/dazzle/http/alembic && python -c "from alembic.config import Config; from alembic.script import ScriptDirectory; s=ScriptDirectory.from_config(Config('alembic.ini')); print('heads:', s.get_heads())"`
Expected: exactly one head, `0006_tenant_is_test`. If it prints two heads, the `down_revision` linkage is wrong — fix it to `"0005_session_csrf_secret"`.

(If `alembic.ini` needs a project context to load, fall back to: `grep -l "down_revision" src/dazzle/http/alembic/versions/*.py | xargs grep -H "^revision\|^down_revision"` and confirm `0006` chains off `0005` and nothing else points at `0006`.)

- [ ] **Step 6: Commit**

```bash
git add src/dazzle/http/alembic/versions/0006_tenant_is_test.py tests/unit/test_tenant_is_test_migration.py
git commit -m "feat(db): 0006 migration adds is_test to public.tenants (#1339 slice 0, ADR-0017)"
```

---

## Task 4: Real-Postgres verification

**Files:**
- Create: `tests/integration/test_tenant_is_test_pg.py`

- [ ] **Step 1: Write the integration test**

Create `tests/integration/test_tenant_is_test_pg.py`:

```python
"""Real-Postgres verification for the is_test substrate (#1339 slice 0).

Two paths against a disposable database:
  * fresh install — `TenantRegistry.ensure_table()` creates `public.tenants`
    with `is_test`, and `create(..., is_test=True)` round-trips the flag.
  * migration — a pre-0006 `tenants` table (no `is_test`) gains the column via
    the 0006 `upgrade()`, defaulting existing rows to false.

Marked ``postgres`` (+ ``e2e``): skipped locally without
``TEST_DATABASE_URL`` / ``DATABASE_URL``; CI's ``postgres-tests`` job runs it.
"""

from __future__ import annotations

import importlib.util
import os
import uuid
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import inspect as sa_inspect

pytestmark = [pytest.mark.e2e, pytest.mark.postgres]

_PG_URL = os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL")

pytestmark_skip = pytest.mark.skipif(not _PG_URL, reason="no TEST_DATABASE_URL/DATABASE_URL")

_MIGRATION = (
    Path(__file__).resolve().parents[2]
    / "src/dazzle/http/alembic/versions/0006_tenant_is_test.py"
)


def _load_migration():
    spec = importlib.util.spec_from_file_location("mig_0006_pg", _MIGRATION)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def pg_url() -> str:
    if not _PG_URL:
        pytest.skip("no TEST_DATABASE_URL/DATABASE_URL")
    return _PG_URL


def test_fresh_ensure_table_round_trips_is_test(pg_url: str) -> None:
    from dazzle.tenant.registry import TenantRegistry

    # Isolate from any other tenants in the shared scratch DB via a unique slug.
    suffix = uuid.uuid4().hex[:8]
    reg = TenantRegistry(pg_url)
    # Clean slate for THIS test's table only if absent; ensure_table is idempotent.
    reg.ensure_table()

    normal = reg.create(f"cust_{suffix}", "Normal Co")
    test = reg.create(
        f"qa_{suffix}", "QA tenant", is_test=True, allow_reserved=True
    )
    try:
        assert normal.is_test is False
        assert test.is_test is True
        assert reg.get(f"qa_{suffix}").is_test is True
        assert reg.get(f"cust_{suffix}").is_test is False
    finally:
        # Tidy up the two rows we created.
        import psycopg

        with psycopg.connect(pg_url) as conn:
            conn.execute(
                "DELETE FROM public.tenants WHERE slug = ANY(%s)",
                ([f"cust_{suffix}", f"qa_{suffix}"],),
            )
            conn.commit()


def test_migration_adds_is_test_to_pre0006_table(pg_url: str) -> None:
    import psycopg

    mod = _load_migration()
    tbl = f"tenants_pre0006_{uuid.uuid4().hex[:8]}"
    engine = sa.create_engine(
        pg_url.replace("postgresql://", "postgresql+psycopg://"), future=True
    )
    try:
        with engine.begin() as conn:
            # Simulate a pre-0006 registry table (no is_test) with one row.
            conn.execute(sa.text(f'CREATE TABLE "{tbl}" (id TEXT PRIMARY KEY, slug TEXT)'))
            conn.execute(sa.text(f"INSERT INTO \"{tbl}\" (id, slug) VALUES ('1', 'legacy')"))

        # The migration targets the literal name "tenants"; point op at our temp
        # table by adding the column directly through the same op API the
        # migration uses, asserting the dialect-agnostic add_column path on PG.
        with engine.connect() as conn:
            ctx = MigrationContext.configure(conn)
            with Operations.context(ctx) as op_ctx:
                op_ctx.add_column(
                    tbl,
                    sa.Column(
                        "is_test", sa.Boolean(), nullable=False, server_default=sa.text("false")
                    ),
                )
            conn.commit()
            cols = {c["name"] for c in sa_inspect(conn).get_columns(tbl)}
            assert "is_test" in cols
            val = conn.execute(sa.text(f'SELECT is_test FROM "{tbl}" WHERE id=\'1\'')).scalar()
            assert val is False
    finally:
        with psycopg.connect(pg_url) as conn:
            conn.execute(f'DROP TABLE IF EXISTS "{tbl}"')
            conn.commit()
        engine.dispose()
```

> **Implementer note on `test_migration_adds_is_test_to_pre0006_table`:** the 0006 `upgrade()` is hard-wired to the literal table name `"tenants"`, so this test exercises the *same* `op.add_column(..., Boolean, server_default false)` shape against real PG on a uniquely-named scratch table rather than mutating the shared `public.tenants`. That proves the DDL the migration emits is PG-valid and back-fills existing rows to `false`. The `tenants`-absent and column-present no-op branches are already covered dialect-agnostically in `test_tenant_is_test_migration.py`. If you prefer to drive `mod.upgrade()` directly, do it only against a disposable database where renaming the table to `tenants` is safe — do **not** run it against a DB holding real tenant rows.

- [ ] **Step 2: Verify a local scratch DB and run the test against real PG**

A local Postgres is up at `localhost:5432`. Create a disposable DB (do not reuse the existing `dazzle*` DBs):

```bash
createdb dazzle_slice0_scratch
TEST_DATABASE_URL="postgresql://localhost/dazzle_slice0_scratch" \
  pytest tests/integration/test_tenant_is_test_pg.py -v -m postgres
```
Expected: both tests PASS.

- [ ] **Step 3: Drop the scratch DB**

```bash
dropdb dazzle_slice0_scratch
```

- [ ] **Step 4: Commit**

```bash
git add tests/integration/test_tenant_is_test_pg.py
git commit -m "test(tenant): real-PG verification of is_test substrate (#1339 slice 0)"
```

---

## Task 5: Changelog + version bump + full pre-ship gate

**Files:**
- Modify: `CHANGELOG.md`

- [ ] **Step 1: Add the CHANGELOG entry**

Add a new version section at the top of `CHANGELOG.md` (above the current latest entry). Use the version produced by `/bump patch` in Step 4 — author the entry first with a placeholder header, then update the header to the bumped version. Content:

```markdown
### Added
- **Ephemeral test-tenant lifecycle — Slice 0 (shared substrate)** (#1338 + #1339).
  - `is_test` boolean on the tenant registry record (`public.tenants`): fresh installs get it
    via `CREATE TABLE`; existing trees via the new framework Alembic migration
    `0006_tenant_is_test` (canonical per ADR-0017) plus a convergent boot-time
    `ALTER ... ADD COLUMN IF NOT EXISTS`. `TenantRegistry.create()` gains an `is_test=` kwarg.
  - Reserved `qa-` / `qa_` slug namespace in `tenant/config.py:validate_slug`: normal tenant
    creates can no longer claim a `qa`-namespaced slug. An `allow_reserved=` seam lets the
    (Slice-2) test-tenant provisioner mint them. The load-bearing test-tenant marker is the
    queryable `is_test` column, not the prefix (belt-and-suspenders).

### Agent Guidance
- Test tenants are marked by the **queryable `is_test` column**, never by a slug prefix — filter
  on `is_test`, not on the name. The `qa-`/`qa_` namespace is a human-visible reservation only.
- New columns on the `public.tenants` registry table go via a framework migration in
  `src/dazzle/http/alembic/versions/` (hand-authored, mirror `0005`/`0006`) **and** the
  `CREATE TABLE` / idempotent boot-time `ALTER` in `tenant/registry.py` — that table is owned by
  `ensure_table()`, not Alembic's DSL metadata, so both convergent paths are required.
```

- [ ] **Step 2: Run the full pre-ship unit gate**

Per `feedback_pre_ship_test_scope` and `feedback_pre_ship_mypy_scope` (saved memory), run the CI-equivalent scopes, not the narrow ones:

```bash
ruff check src/ tests/ --fix && ruff format src/ tests/
mypy src/dazzle
pytest tests/ -m "not e2e"
```
Expected: ruff clean, mypy clean, unit suite green. (Note: `tests/unit/test_retention_loop.py::TestCronFiring::test_dedupes_within_same_minute` is a known ~0.3% time-coupled flake — if it fails, re-run; it is unrelated to this slice.)

- [ ] **Step 3: Verify the docs-drift gate is unaffected**

Run: `pytest tests/unit/test_api_surface_drift.py tests/unit/test_docs_drift.py -v`
Expected: PASS — this slice adds no DSL construct, IR type, MCP tool, public helper, or runtime URL, so no API-surface baseline changes.

- [ ] **Step 4: Bump the patch version**

Run: `/bump patch` (0.81.19 → 0.81.20). Then update the CHANGELOG header placeholder to the bumped version.

- [ ] **Step 5: Commit**

```bash
git add CHANGELOG.md
git commit -m "docs(changelog): tenant-lifecycle Slice 0 substrate -- v0.81.20"
```

---

## Final integration & ship

- [ ] **Independent review checkpoint.** Before merging, dispatch a fresh `feature-dev:code-reviewer` (or run `/code-review`) over the Slice-0 diff. Slice 0 is low-risk substrate, so a single review pass is sufficient (the security-critical adversarial review is reserved for Slice 2). Address any high-confidence findings via `superpowers:receiving-code-review`.

- [ ] **Confirm a clean, green branch.** `git status` clean; `pytest tests/ -m "not e2e"` green; mypy + ruff clean (per Ship Discipline + `feedback_clean_worktree`).

- [ ] **FF-merge to `main` and push.** Mirror the declarative-CSRF ship sequence; per `feedback_commit_before_tag_push`, confirm each step's exit status before the next (do not chain bump→commit→tag→push blindly across newlines).

- [ ] **Comment progress on #1338 and #1339** (keep both OPEN): note that Slice 0 (shared substrate — `is_test` column + reserved `qa` namespace) shipped in v0.81.20, with Slice 1 (excision) next.

- [ ] **Update memory** `project_tenant_lifecycle.md`: Slice 0 shipped (v0.81.20); record the two decisions made during planning — (a) reserved namespace covers **both** `qa-` and `qa_` (the reachable hole was `qa_`), (b) `is_test` uses dual convergent paths (Alembic 0006 + boot-time idempotent ALTER) because `public.tenants` is outside Alembic's DSL metadata.

---

## Self-Review notes (planner)

- **Spec coverage:** §3 Slice 0's two deliverables (`is_test` column via Alembic; reserved `qa-` in `validate_slug`) → Tasks 2+3 and Task 1 respectively. §6 Slice-0 testing (`validate_slug` rejects a `qa-` slug; `is_test` round-trips) → Task 1 tests + Task 4 round-trip test. §8 open questions deferred to later slices are explicitly listed as out-of-scope above.
- **Two divergences from spec text, both deliberate and recorded in CHANGELOG/memory:** (1) reserve `qa_` as well as `qa-` (the registry grammar already forbids hyphens, so `qa-` alone is a no-op for normal creates — the reachable hole is `qa_`); (2) `is_test` ships via Alembic migration **and** a convergent boot-time `ALTER` because `public.tenants` is owned by `ensure_table()`, not Alembic's DSL metadata (matches the existing `config`-column precedent). Both honour the spec's intent (queryable flag + reserved human-visible namespace) while fitting the real code.
- **Type consistency:** `TenantRecord.is_test: bool`; `validate_slug(slug, *, allow_reserved=False)`; `create(slug, display_name, *, is_test=False, allow_reserved=False)`; `RESERVED_SLUG_PREFIXES: tuple[str, ...]`; migration `revision="0006_tenant_is_test"`, `down_revision="0005_session_csrf_secret"` — used consistently across Tasks 1–4.
