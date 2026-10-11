# Auth-store ↔ Alembic parity (foundation slice) Implementation Plan

> **For agentic workers:** Execute Hybrid (inline). Steps use checkbox (`- [ ]`).

**Goal:** Complete the alembic mirror for `scim_groups`/`scim_group_members`, add `external_id`
to `memberships` + `scim_groups` in BOTH mechanisms, and add a drift gate enforcing parity.

**Spec:** `docs/superpowers/specs/2026-06-08-authstore-alembic-parity-foundation-design.md`

---

## File Structure

- Create `src/dazzle/http/alembic/versions/0013_scim_groups_and_external_ids.py`.
- Modify `src/dazzle/http/runtime/auth/store.py` — `_init_db` adds the two `external_id` columns.
- Create `tests/integration/test_authstore_alembic_parity_pg.py` — the drift gate.
- Modify `tests/integration/test_connections_pg.py` — column-existence check.

---

### Task 1: `_init_db` — the two `external_id` columns

**Files:** Modify `src/dazzle/http/runtime/auth/store.py`

- [ ] **Step 1:** In `_init_db`, alongside the existing `ALTER TABLE … ADD COLUMN IF NOT
EXISTS` block (near the `sessions`/`connections` alters), add:

```python
            cursor.execute("ALTER TABLE memberships ADD COLUMN IF NOT EXISTS external_id TEXT")
            cursor.execute("ALTER TABLE scim_groups ADD COLUMN IF NOT EXISTS external_id TEXT")
```
Place AFTER the `scim_groups` CREATE so the table exists. Comment: "#1342 schools-gap: the
IdP's stable id for the user (membership) / group — see the SCIM/SAML streamlining gaps."

- [ ] **Step 2: Failing test** (append to `tests/integration/test_connections_pg.py`):

```python
def test_external_id_columns_present(store_url: str) -> None:
    import sqlalchemy as sa

    _store(store_url)  # runs _init_db
    eng = sa.create_engine(store_url)
    cols = lambda t: {c["name"] for c in sa.inspect(eng).get_columns(t)}
    assert "external_id" in cols("memberships")
    assert "external_id" in cols("scim_groups")
```

- [ ] **Step 3: Run** `DATABASE_URL=…/dazzle_dev pytest tests/integration/test_connections_pg.py::test_external_id_columns_present -q` → PASS.

---

### Task 2: Alembic `0013` — mirror scim_groups + external_id columns

**Files:** Create `src/dazzle/http/alembic/versions/0013_scim_groups_and_external_ids.py`

- [ ] **Step 1: Write the migration** (guarded, mirrors `_init_db`, DDL matches exactly):

```python
"""Mirror scim_groups + scim_group_members into the alembic chain, and add external_id to
memberships + scim_groups (#1342 schools SCIM/SAML gap foundation).

Guarded safety-net mirroring AuthStore._init_db (the primary creator), same pattern as 0007.
scim_group_members deliberately carries NO FK to memberships (the documented FK-coupling
trap); it DOES keep the FK to scim_groups (matches _init_db)."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect as sa_inspect

revision = "0013_scim_groups_and_external_ids"
down_revision = "0012_connection_grace_secret"
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
    if not _has_table("scim_groups"):
        op.create_table(
            "scim_groups",
            sa.Column("id", sa.Text(), primary_key=True),
            sa.Column("connection_id", sa.Text(), nullable=False),
            sa.Column("display_name", sa.Text(), nullable=False),
            sa.Column("created_at", sa.Text(), nullable=False),
            sa.Column("updated_at", sa.Text(), nullable=False),
            sa.UniqueConstraint("connection_id", "display_name"),
        )
        op.create_index("ix_scim_groups_conn", "scim_groups", ["connection_id"])
    if not _has_table("scim_group_members"):
        op.create_table(
            "scim_group_members",
            sa.Column(
                "group_id",
                sa.Text(),
                sa.ForeignKey("scim_groups.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("membership_id", sa.Text(), nullable=False),
            sa.PrimaryKeyConstraint("group_id", "membership_id"),
        )
        op.create_index(
            "ix_scim_group_members_member", "scim_group_members", ["membership_id"]
        )
    if _has_table("memberships") and not _has_column("memberships", "external_id"):
        op.add_column("memberships", sa.Column("external_id", sa.Text(), nullable=True))
    if _has_table("scim_groups") and not _has_column("scim_groups", "external_id"):
        op.add_column("scim_groups", sa.Column("external_id", sa.Text(), nullable=True))


def downgrade() -> None:
    if _has_column("scim_groups", "external_id"):
        op.drop_column("scim_groups", "external_id")
    if _has_column("memberships", "external_id"):
        op.drop_column("memberships", "external_id")
    if _has_table("scim_group_members"):
        op.drop_table("scim_group_members")
    if _has_table("scim_groups"):
        op.drop_table("scim_groups")
```

- [ ] **Step 2: Verify the chain head** — run any existing alembic-chain test, or
`DATABASE_URL=…/dazzle_dev python -c "from dazzle.cli.db import _get_alembic_cfg; from alembic import command; command.upgrade(_get_alembic_cfg(), 'head')"` against a scratch DB → no error, head == 0013. (The drift gate in Task 3 also exercises this.)

---

### Task 3: Drift gate (the headline)

**Files:** Create `tests/integration/test_authstore_alembic_parity_pg.py`

- [ ] **Step 1: Write the gate.** Reuse the scratch-DB pattern from `test_connections_pg.py`
(create/drop a uniquely-named DB). Build TWO scratch DBs — one via `_init_db`, one via alembic
`upgrade head` (framework versions only) — and compare:

```python
"""Drift gate (#1342): the alembic mirror of the auth store must stay faithful to
AuthStore._init_db (the primary creator). For every table BOTH produce, the column sets must
match; the known _init_db-primary tables that alembic deliberately doesn't create are
allowlisted, and any NEW un-mirrored table fails the gate (forcing a conscious choice)."""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator

import psycopg
import pytest
import sqlalchemy as sa

pytestmark = [pytest.mark.e2e, pytest.mark.postgres]

_PG_URL = os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL")

# Tables AuthStore._init_db creates that alembic deliberately does NOT (the deferred
# consolidation set — see the foundation spec). A NEW _init_db-only table NOT in this set
# fails the gate.
_INIT_DB_PRIMARY_ONLY = {
    "users",
    "sessions",
    "password_reset_tokens",
    "user_preferences",
    "magic_links",
    "email_verification_tokens",
}


def _scratch(admin: str) -> tuple[str, str]:
    base, _, _ = admin.rpartition("/")
    name = f"dazzle_parity_{uuid.uuid4().hex[:8]}"
    with psycopg.connect(admin, autocommit=True) as a:
        a.execute(f'CREATE DATABASE "{name}"')  # nosemgrep
    return f"{base}/{name}", name


def _drop(admin: str, name: str) -> None:
    with psycopg.connect(admin, autocommit=True) as a:
        a.execute(
            "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
            "WHERE datname=%s AND pid<>pg_backend_pid()",
            (name,),
        )
        a.execute(f'DROP DATABASE IF EXISTS "{name}"')  # nosemgrep


@pytest.fixture
def two_scratch_dbs() -> Iterator[tuple[str, str]]:
    if not _PG_URL:
        pytest.skip("no TEST_DATABASE_URL/DATABASE_URL")
    admin = _PG_URL.replace("postgresql+psycopg://", "postgresql://")
    a_url, a_name = _scratch(admin)
    b_url, b_name = _scratch(admin)
    try:
        yield a_url, b_url
    finally:
        _drop(admin, a_name)
        _drop(admin, b_name)


def _columns_by_table(url: str) -> dict[str, set[str]]:
    eng = sa.create_engine(url)
    insp = sa.inspect(eng)
    out = {t: {c["name"] for c in insp.get_columns(t)} for t in insp.get_table_names()}
    eng.dispose()
    return out


def _alembic_head(url: str) -> None:
    from alembic import command
    from alembic.config import Config

    from dazzle.cli.db import _get_framework_alembic_dir

    fw = _get_framework_alembic_dir()
    cfg = Config(str(fw / "alembic.ini"))
    cfg.set_main_option("script_location", str(fw))
    cfg.set_main_option("path_separator", "os")
    cfg.set_main_option("version_locations", str(fw / "versions"))  # framework only
    cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(cfg, "head")


def test_authstore_alembic_parity(two_scratch_dbs) -> None:
    a_url, b_url = two_scratch_dbs
    from dazzle.http.runtime.auth.store import AuthStore

    AuthStore(database_url=a_url)  # _init_db builds schema A
    _alembic_head(b_url)  # alembic head builds schema B

    a = _columns_by_table(a_url)
    b = _columns_by_table(b_url)
    a_tables, b_tables = set(a), set(b)

    # 1. Every table in BOTH must have identical column sets (the faithful-mirror invariant).
    for t in a_tables & b_tables:
        assert a[t] == b[t], f"column drift on {t!r}: _init_db={a[t]} vs alembic={b[t]}"

    # 2. Any _init_db-only table must be a KNOWN deferred-consolidation table, else the mirror
    #    has a new hole — fail so the author mirrors it (or consciously extends the allowlist).
    init_only = a_tables - b_tables
    # Ignore non-auth framework tables alembic seeds (e.g. _dazzle_params) that _init_db
    # doesn't make — only assert about tables _init_db actually created.
    unexpected = {t for t in init_only if t not in _INIT_DB_PRIMARY_ONLY}
    assert not unexpected, (
        f"these tables are in _init_db but NOT mirrored in alembic: {unexpected}. "
        "Add an alembic migration mirroring them, or add to _INIT_DB_PRIMARY_ONLY with a note."
    )
```

- [ ] **Step 2: Run** `DATABASE_URL=…/dazzle_dev pytest tests/integration/test_authstore_alembic_parity_pg.py -q`. Expect PASS — `scim_groups`/`scim_group_members` now mirrored (not in the allowlist), `external_id` present in both, and the four+ `_init_db`-primary tables allowlisted. If it fails listing an unexpected table, that's a real pre-existing hole — mirror it in 0013 or add it to `_INIT_DB_PRIMARY_ONLY` with a comment (decide per table; prefer mirroring the small SCIM-adjacent ones).

- [ ] **Step 3:** If `_dazzle_params` (alembic-only, from 0001) shows up in `b_tables - a_tables`, that's expected (the gate only asserts about `init_only` and shared tables) — no action.

---

### Task 4: Ship

- [ ] **Step 1: CHANGELOG** `### Added`: "Auth-store ↔ Alembic parity (SCIM/SAML gap
foundation): `scim_groups`/`scim_group_members` mirrored into the alembic chain (0013),
`external_id` added to `memberships` + `scim_groups`, and a drift gate
(`test_authstore_alembic_parity_pg`) that fails if `_init_db` and alembic-head diverge on any
shared table or a new un-mirrored auth table appears." Add an `### Agent Guidance` line: "auth
schema changes go in BOTH `_init_db` and an alembic migration; the parity gate enforces it."
- [ ] **Step 2:** `/bump patch`; gates (`ruff`, `mypy src/dazzle`, drift/policy,
`pytest -m "not e2e"`, and the postgres slice incl. the new parity gate); commit (verify
`COMMIT_EXIT=0`), tag, push, watch CI (incl. `PostgreSQL Tests`) + release.
- [ ] **Step 3:** update memory — foundation shipped; gaps 3→2→1 next; note the parity gate +
the deferred full consolidation.

## Self-review

- **Spec coverage:** mirror scim tables (T2), external_id in both (T1+T2), drift gate with
  allowlist teeth (T3). ✓
- **DDL match:** 0013's scim_groups/members columns + UNIQUE + FK-to-scim_groups (no FK to
  memberships) + indexes mirror `_init_db` exactly (verified against store.py:2360). ✓
- **Risk:** additive-only; guarded migration is a no-op where `_init_db` already created the
  tables; the gate is the safety net. No production data migration.
