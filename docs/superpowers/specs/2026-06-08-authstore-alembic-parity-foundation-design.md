# Auth-store ↔ Alembic parity (SCIM/SAML stepping-stone) — Design

**Context:** Foundation slice for closing the schools SCIM/SAML streamlining gaps
(`dev_docs/2026-06-08-schools-scim-saml-engagement-analysis.md`). Before adding two more
columns to the auth store, make the existing **dual schema mechanism** safe and complete
enough to build on. Chosen path: *stepping-stone now, full consolidation later* (2026-06-08).

## The current reality (evidence)

`AuthStore._init_db()` runs on **every** `AuthStore()` construction (prod, every boot) and is
the **primary creator** of the auth tables via idempotent `CREATE TABLE IF NOT EXISTS` /
`ALTER TABLE … ADD COLUMN IF NOT EXISTS`. Alembic migrations 0005–0012 carry **guarded
*mirrors*** of *some* of those tables (migration 0007's docstring states this is deliberate:
"a guarded safety-net that mirrors what `_init_db` does idempotently"). Two problems:

- **The mirror is incomplete + manual.** `scim_groups` / `scim_group_members` (and
  `users` / `sessions` / `password_reset_tokens` / `user_preferences`) are **`_init_db`-only**
  — in no alembic migration. A DB provisioned purely by `dazzle db upgrade` (no `AuthStore`
  boot) would lack them. Masked today only because `AuthStore` always boots.
- **Nothing enforces parity.** A column added to one mechanism (or with a different type) and
  not the other drifts silently. `scim_groups`-not-in-alembic is a live instance.

This violates ADR-0017 ("all schema via Alembic") in spirit, but full consolidation (retire
`_init_db`'s schema role; move `users`/`sessions` into alembic; reconcile baselines; solve the
test ergonomics of the hundreds of `AuthStore(url); _init_db()` call sites) is a separate,
deliberate piece — explicitly **out of scope here**.

## Goal

1. Complete the alembic mirror for the SCIM tables the gaps touch (`scim_groups`,
   `scim_group_members`).
2. Add the two new `external_id` columns the gaps need, to **both** mechanisms.
3. Add a **drift gate** so the manual mirror can never silently diverge again.

## Components

### 1. Alembic migration `0013_scim_groups_and_external_ids.py`

Guarded (mirrors `_init_db`, like 0007), `down_revision = "0012_connection_grace_secret"`:
- `_has_table`/`_has_column` guards (reuse the 0007 helper shape).
- Guarded-create `scim_groups` and `scim_group_members` with DDL **matching `_init_db`
  exactly** (same columns, types, the `UNIQUE(connection_id, display_name)`; `scim_group_members`
  has **no FK to memberships** — the documented FK-coupling trap).
- Guarded `ADD COLUMN external_id TEXT` to `memberships` and to `scim_groups`.
- `downgrade()` drops the two columns + tables (guarded), mirroring the up.

### 2. `_init_db` — the two new columns

Add (idempotent, alongside the existing `ALTER … ADD COLUMN IF NOT EXISTS` block):
```sql
ALTER TABLE memberships ADD COLUMN IF NOT EXISTS external_id TEXT
ALTER TABLE scim_groups  ADD COLUMN IF NOT EXISTS external_id TEXT
```
(The gap features populate/echo these; this slice only adds the storage.)

### 3. Drift gate — two parts

**Discovery during implementation:** the alembic auth-mirror chain is **not standalone** —
0005/0007 do `ALTER TABLE sessions …` but `sessions` is created only by `_init_db`, so
`alembic upgrade head` on an *empty* DB fails. The real prod order is `_init_db` first (every
AuthStore boot) then alembic as guarded ALTERs. So "build via `_init_db` vs via alembic-head
and diff columns" is not a valid comparison; the gate is instead:

- **Static completeness** (`tests/unit/test_authstore_alembic_mirror_completeness.py`, no DB,
  fast lane): parse `_init_db`'s inline `CREATE TABLE IF NOT EXISTS X` and every alembic
  `op.create_table("X")`; assert `{_init_db tables} − allowlist ⊆ {alembic tables}`. The
  allowlist names the four inline `_init_db`-primary tables alembic doesn't mirror yet
  (`users`, `sessions`, `password_reset_tokens`, `user_preferences`); a NEW un-mirrored table
  fails. A second test keeps the allowlist honest (no stale/mirrored entries).
- **Coexistence** (`tests/integration/test_authstore_alembic_parity_pg.py`, `-m postgres`):
  `_init_db` then `alembic upgrade head` on the **same** scratch DB succeeds (no
  "column already exists" / missing table), reaches head `0013`, and the new
  tables/columns are present — proving the mirror migrations are correctly guarded and
  coexist with `_init_db` (the real prod path). Running upgrade head twice stays clean.

Together: completeness (static teeth) + coexistence (runtime). True column-level parity across
a *standalone* alembic build needs the deferred consolidation (making the chain self-sufficient).

#### (original sketch, superseded by the two-part gate above)
A `-m postgres` test that proves the mirror is faithful:
- Scratch DB **A**: `AuthStore(url_A)` (runs `_init_db`) → introspect every table's columns
  (name + type) via SQLAlchemy `inspect`.
- Scratch DB **B**: `alembic upgrade head` against `url_B` (the prod path; reuse the
  framework alembic config the way `dazzle db upgrade` does) → introspect.
- **Assert:** for every table present in **both** A and B, the column sets (name → type
  family) are identical. This is the enforceable invariant for the *mirrored* tables.
- **Allowlist** the known `_init_db`-primary tables that alembic deliberately does NOT create
  (`users`, `sessions`, `password_reset_tokens`, `user_preferences`) — these are present in A,
  absent in B, and that asymmetry is *expected* until the deferred consolidation. The gate
  asserts the allowlist matches reality (A-only tables ⊆ allowlist), so a NEW `_init_db`-only
  table (a future un-mirrored addition) **fails** the gate — forcing the author to either
  mirror it in alembic or consciously extend the allowlist. That is the anti-drift teeth.

After this slice, `scim_groups`/`scim_group_members` move OUT of the allowlist (now mirrored),
and a column added to one mechanism but not the other fails the gate.

## Out of scope (deferred consolidation — its own spec)

- Moving `users`/`sessions`/`password_reset_tokens`/`user_preferences` into alembic (making
  `dazzle db upgrade` a standalone auth provisioner).
- Retiring `_init_db`'s schema-creation role / the test-ergonomics + baseline reconciliation.
- Any non-additive change (rename/drop/type/constraint) — the dual-write can't express those
  idempotently; the first one forces the consolidation decision.

## Testing

- The drift gate above (the headline).
- `tests/integration/test_connections_pg.py` (or a scim PG test): a fresh `AuthStore` has the
  `external_id` columns on `memberships` + `scim_groups` (storage exists).
- Alembic migration tests if present (`0013` up/down idempotent, guarded) — mirror the
  existing per-migration test pattern if one exists; else the drift gate (which runs alembic
  to head) covers the up path.

## Sequencing after this

Foundation (this) → Gap 3 (SAML overage, no schema) → Gap 2 (group→role by `external_id`) →
Gap 1 (user `externalId` echo + dedup). Gaps 2 & 1 consume the columns added here.
