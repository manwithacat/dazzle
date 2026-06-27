# ADR-0044 — Complete, CI-managed framework migration baseline

**Status:** Accepted
**Builds on:** ADR-0017 (Alembic for all schema changes), ADR-0008 (PostgreSQL-only app runtime), ADR-0005 (no new singletons), ADR-0003 (clean breaks), #1431 (`SCHEMA_SNAPSHOT` serializer + `schema_diff`), #1390 (autostamp), #1309 (baseline reconcile)
**Amended by:** ADR-0047 (2026-06-27) — artifact *membership and per-artifact metadata* (class / owner / RLS posture / boot-DDL gating) is now sourced from the DB-artifact registry (`dazzle.db.artifact_registry`); this ADR's `IN_SCOPE_TABLES` is registry-derived (`in_baseline_tables()`). ADR-0044 remains the record of the baseline *construction + parity* mechanism (the squash, the shared-DDL orchestrator, the three-way real-PG parity gate).

## Decision

The framework ships **one** Alembic migration — a single squashed baseline at the
stable head id `0019_process_runtime_tables` (`down_revision=None`) — and that
baseline is the **complete, provably-faithful mirror** of the framework schema the
runtime builds at boot. A single orchestrator, `ensure_framework_schema(conn)`, is
the **one source of the framework schema**; the baseline mirrors it *by shared
code* (not a copy); a committed readable snapshot declares it; and a real-Postgres
CI gate proves the three agree.

The invariant is structural, enforced on every change in CI:

> **`alembic upgrade head` ≡ `ensure_framework_schema(conn)` ≡ the committed
> `FRAMEWORK_SCHEMA_SNAPSHOT`**, over every in-scope app-DB framework table.

## Context and problem

Two divergences had silently accumulated:

1. **Dev-churn sediment** — the framework shipped 19 development migrations
   (`0001`–`0019`), the visible history of how the schema was built. A new app
   built from Dazzle inherited all of it as its migration baseline.
2. **A partial, arbitrary mirror** — those migrations mirrored only
   `_dazzle_params` + the auth tables + the process-runtime tables. ~10 other
   *live* framework tables (audit, atomic-audit, files, refresh-tokens, devices,
   grants, OTP, recovery-codes, event inbox/outbox) were created by scattered
   lazy/conditional `_init_db`/`ensure_*` calls **with no Alembic representation
   at all**. "The migration chain" and "the framework schema" had drifted apart,
   and nothing detected it.

This is the classic 4GL/MDE failure mode "an abstraction hides a load-bearing
semantic": the baseline looked authoritative but silently diverged from what the
runtime actually builds.

## The model

- **One orchestrator** — `src/dazzle/http/runtime/framework_schema.py`,
  `ensure_framework_schema(conn)`: creates **all in-scope app-DB framework tables
  unconditionally**, under one `pg_advisory_xact_lock`, idempotent
  (`CREATE TABLE/INDEX IF NOT EXISTS`, `ADD COLUMN IF NOT EXISTS`). Its no-commit,
  no-lock core `_ensure_framework_schema_ddl(cur)` is the single DDL body. The ~18
  previously method-based table creators were extracted to shared module-level
  `ensure_*` functions called by **both** their store's `_init_db` **and** the
  orchestrator — no divergent creator.
- **One squashed baseline** — `src/dazzle/http/alembic/versions/0019_process_runtime_tables.py`,
  `down_revision=None`. Its `upgrade()` widens `alembic_version.version_num` to
  `VARCHAR(128)` then calls the orchestrator's **shared core**
  `_ensure_framework_schema_ddl(cur)`. The baseline therefore equals the
  orchestrator *by code*, not by a transcribed copy. `0001`–`0018` are deleted.
- **One readable snapshot** — `FRAMEWORK_SCHEMA_SNAPSHOT` in
  `src/dazzle/http/runtime/framework_schema_snapshot.py`, rendered via #1431's
  `render_snapshot_literal`. It uses a richer index representation
  (`{name: {unique, columns, predicate}}`) than #1431's app-entity snapshot
  format, so dropped duplicate-column indexes and partial-index predicate drift
  are caught.
- **The three-way parity gate** — `tests/integration/test_framework_baseline_parity_pg.py`
  (real Postgres): builds a scratch DB three ways and asserts structural equality
  with a readable diff on mismatch, plus a *no-unlisted-table* guard
  (`introspect_schema(orchestrator, only=None) - {alembic_version} == IN_SCOPE_TABLES`)
  so a future framework table that isn't listed breaks the gate instead of going
  unguarded.
- **The chain-cleanliness gate** — `tests/unit/test_framework_chain_clean.py`:
  `versions/` is exactly the single baseline at the stable head (no dev-churn
  re-accumulation between releases without an intentional re-squash).
- **The regeneration command** — `dazzle db reframework-baseline`: builds a scratch
  DB via the orchestrator, introspects the in-scope tables, and rewrites the
  committed snapshot deterministically (ruff-formats its output, so it is
  byte-idempotent against the committed file). Agent workflow: change the
  orchestrator → `dazzle db reframework-baseline` → the parity gate proves equality.

## Behavior change (accepted)

The ~10 previously lazy/conditional framework tables are now **eagerly created for
every app at boot**. Most are tiny or empty; they are framework-owned; the cost is
negligible. This is the price of a complete, provable baseline and a single
comprehensible schema source. A usage audit (2026-06-23) confirmed **every**
in-scope table has live consumers — none is dead, none was pruned.

### In-scope (the orchestrator + baseline own these)

`_dazzle_params`; auth (`users`, `sessions`, `memberships`, `organizations`,
`membership_events`, `invitations`, `connections`, `connection_secret_events`,
`scim_groups`, `scim_group_members`, `saml_consumed_assertions`,
`password_reset_tokens`, `magic_links`, `email_verification_tokens`,
`user_preferences`, `join_requests`); `process_runs`, `process_tasks`;
`_dazzle_audit_log`, `_dazzle_atomic_audit`, `dazzle_files`, `refresh_tokens`,
`devices`, `_grants`, `_grant_events`, `_dazzle_otp_codes`,
`_dazzle_recovery_codes`, `_dazzle_event_inbox`, `_dazzle_event_outbox` (30 tables).

### Excluded (live, but cannot live in one unconditional app-DB baseline)

- **ops_database tables** — a *separate* database (`ops_integration` wires a
  distinct connection); consumed by api-tracker/health/analytics/spec-versioning/
  deploy-history/email-templates.
- **Event-bus `{prefix}events/offsets/dlq`** — dynamic per-bus/tenant prefix,
  created by `PostgresBus`.
- **Tenant registry `public.tenants`** + per-tenant schemas — multi-tenant infra.

## Squash mechanics + stable head

`0001`–`0018` are collapsed into `0019`. The head revision id
`0019_process_runtime_tables` is **kept** (`down_revision=None`) so downstream app
chains that reference the current framework head don't dangle. The id name is a
documented wart — it is the baseline, named for the last pre-squash head, retained
for chain stability.

**Non-idempotent-transform audit (Task 0):** before deleting `0002`–`0018`, each
was checked for a data migration or destructive `ALTER ... USING` whose loss would
matter beyond fresh-install. **None carries one** — existing DBs already applied
them; fresh installs get the final-state baseline. (Recorded in
`dev_docs/2026-06-23-framework-baseline-transform-audit.md`.) The two load-bearing
non-table transforms were folded into `0019`: the `alembic_version` VARCHAR(128)
widening (was `0004`) and the `assert_subtype_kind()` plpgsql function (was `0003`).

## Consumer adaptation (shared-base migration)

The framework chain is a shared base (one Alembic graph via `version_locations`;
downstream app migrations chain off the framework head). By consumer state:

1. **At the head / app-migrations chaining off `0019`:** nothing.
   `alembic_version` still resolves; the baseline is the new root; `upgrade head`
   is a no-op. Eager tables arrive via the orchestrator at boot (idempotent).
2. **Lagging on an old framework revision:** one `dazzle db migrate` (autostamp
   #1390: schema materialized + version stale → stamp; guarded, re-run is a no-op).
3. **App migration whose `down_revision` is a deleted intermediate id
   (`0002`–`0018`):** the one manual case — re-point that single `down_revision`
   to `0019_process_runtime_tables`, or stamp. Small engaged consumer set → a
   documented one-time per-app fixup.

## The widened dual-write rule

A new framework table goes in the **orchestrator** (preferably as a shared
`ensure_*` function called by both the store and the orchestrator), and the
baseline is **regenerated** (`dazzle db reframework-baseline`) — *not* added as a
fresh per-table migration. The rare destructive change adds one incremental
migration, re-folded into the baseline at the next release. The chain-cleanliness
gate enforces that `versions/` doesn't silently re-accumulate churn.

## Test-coverage shift

The 11 per-migration isolation/stamp-to-N tests for deleted migrations were
removed (`test_subtype_alembic_revision`, `test_alembic_drop_dazzle_migrations`,
`TestMigration0005`, `TestMigration0004WidensVersionNum1282`,
`test_tenant_is_test_migration`, and the `test_migration_00NN_*` `_pg` functions in
`test_auth_membership_pg`/`test_auth_orgprovision_pg`/`test_membership_events_pg`/
`test_org_invitations_pg`/`test_connections_pg`). Their behavior is now covered by
the **baseline + the three-way parity gate**, which proves the *whole* framework
schema agrees three ways — a stronger guarantee than per-migration application
checks. Baseline-id references were updated to `0019_process_runtime_tables`
throughout, and `test_authstore_alembic_parity_pg` was generalized from a head-id
assertion to the three-way parity assertion.

## Failure-modes rubric sign-off (CLAUDE.md gate)

1. *Failure mode risked:* "an abstraction hides a load-bearing semantic" — a
   baseline that silently diverges from what the runtime builds (the exact
   divergence found: 19 partial migrations vs the real framework schema).
2. *Detector:* the three-way parity gate (real PG, readable diff, no-unlisted-table
   guard) + the chain-cleanliness gate.
3. *Live?* Yes — CI on every change.
4. *Trace runtime → DSL?* Yes — one orchestrator function *is* the framework
   schema; the baseline mirrors it; the snapshot declares it; downstream chains
   reference one stable head.
5. *Preserve semantics?* Yes — parity asserted three ways, downstream-chain
   stability via the stable head id, the consumer runbook explicit, the three
   exclusions documented.

**Agent-comprehensibility (the stated goal):** one orchestrator + one baseline +
one rule + a readable-diff gate + a regeneration command. An agent reads the
framework schema in one place, verifies it, and extends it without archaeology.

## Known follow-ons (non-blocking; parity-gate-covered)

The parity gate proves the orchestrator, baseline, and snapshot are non-divergent
*today*; these are future-divergence hazards worth tidying, not live bugs:

- **Four in-scope tables are still *inlined* in the orchestrator** rather than
  delegated to a shared `ensure_*` function (`process_runs`/`process_tasks`,
  `_dazzle_params`, `_dazzle_atomic_audit`). The 18 method-based tables were
  extracted; these four keep an inlined copy. `process_runs`/`process_tasks` also
  have an *unavoidable* core-layer copy in `core/process/pg_state.py` (core ↛ http
  by import-linter, so it cannot import the http-layer DDL). Confirmed
  byte-equivalent at review time. Cleaner finish: refactor
  `process_schema.ensure_process_tables(conn)` into a cursor-based shared core the
  orchestrator delegates to.
- **`ensure_process_tables` (`process_schema.py`) has no live production caller**
  now that the orchestrator inlines its DDL (only the unit test exercises it).
  Either delete it or make the orchestrator delegate to it (preferred — resolves
  the previous point too).
- **A redundant idempotent `ensure_atomic_audit_table(conn)` call remains** at
  `server.py:1949` after the orchestrator already creates `_dazzle_atomic_audit`
  earlier in the same boot path. Harmless (idempotent) but removable.
- **`version_manager.py`'s Postgres branch creates a structurally stale
  `process_runs`** (no queue columns). Not a live app-DB creator — `VersionManager`
  is only ever constructed SQLite-backed in-tree — so the gate's blind spot isn't
  exercised. Pre-existing; worth a comment.
