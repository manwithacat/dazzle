# Framework migration baseline: one orchestrator, a complete CI-managed baseline

**Status:** Design (brainstormed 2026-06-22/23). Spec + plan written now; **implementation deferred to a fresh session** (large refactor; maintainer's call).
**Builds on:** dual-write convention (`_init_db` + alembic mirror), #1431 (`SCHEMA_SNAPSHOT` serializer + `schema_diff`/`schema_render`), #1390 (autostamp), #1309 (baseline reconcile), ADR-0017 (Alembic), ADR-0008 (Postgres-only). Ships on a **minor bump (0.84.0)**.
**Disposition:** Large — a single framework-schema orchestrator + a complete squashed baseline + a real three-way parity gate + test surgery. One spec → one plan; execute fresh.

---

## 1. The principle

**New apps built from Dazzle see one clean framework migration baseline, and that baseline is the *complete, provably-faithful* mirror of the framework schema the runtime builds — enforced by CI, comprehensible to an agent.**

Two problems today: (1) the framework ships **19 dev-churn migrations** (the visible sediment of development); (2) those migrations are a **partial, arbitrary subset** — they mirror only `_dazzle_params` + auth + process, while ~10 other live framework tables (audit, atomic_audit, files, refresh_tokens, devices, grants, otp, recovery, inbox, outbox) are created by **scattered lazy/conditional `_init_db`/`ensure_*` calls with no alembic representation at all**. So "the migration chain" and "the framework schema" have silently diverged.

The fix collapses both: **one orchestrator builds the full app-DB framework schema unconditionally; one squashed baseline mirrors it exactly; one CI gate proves `baseline ≡ orchestrator ≡ snapshot`.**

## 2. Usage audit (done 2026-06-23 — nothing is dead)

Every conditional app-DB table has live consumers, so the orchestrator enshrines all of them (none pruned):

| Table | Live consumers (sample) |
|---|---|
| `_dazzle_audit_log` | 4 files (audit wiring) |
| `_dazzle_atomic_audit` | 3 files (atomic flows) |
| `dazzle_files` | file routes |
| `refresh_tokens` | JWT refresh |
| `devices` | 8 files (mobile/device) |
| `_grants`, `_grant_events` | 4 files (grant routes) |
| `_dazzle_otp_codes`, `_dazzle_recovery_codes` | 2FA routes (`routes_2fa`, `two_factor_form_routes`) |
| `_dazzle_event_inbox`, `_dazzle_event_outbox` | event-bus transactional delivery (Inbox: 14 refs) |
| auth tables (15), `_dazzle_params`, `process_runs`/`process_tasks` | always-on |

**Excluded (live, but cannot live in a single unconditional app-DB baseline):** `ops_database` tables (separate DB — `ops_integration` wires a distinct connection; consumed by api_tracker/health/analytics/spec_versioning/deploy_history/email_templates); event-bus `{prefix}events/offsets/dlq` (dynamic per-bus/tenant prefix); tenant registry `public.tenants` + per-tenant schemas (multi-tenant infra). The gate documents these as out-of-scope.

## 3. The model: `ensure_framework_schema(conn)` + complete baseline + parity gate

- **One orchestrator** `ensure_framework_schema(conn)` (new, e.g. `src/dazzle/http/runtime/framework_schema.py`) creates **all in-scope app-DB framework tables unconditionally**, advisory-locked, idempotent (`CREATE TABLE/INDEX IF NOT EXISTS`, `ADD COLUMN IF NOT EXISTS`). It is the **single source of the framework schema**. The ~10 lazy/conditional inits are refactored so their DDL lives in (or is called by) the orchestrator — each store keeps its *runtime* API but no longer owns conditional table creation; tables exist eagerly. (Behavior change, see §4.)
- **One squashed baseline** (`src/dazzle/http/alembic/versions/<head>.py`, `down_revision=None`, stable head id `0019_process_runtime_tables`) whose `upgrade()` produces **exactly** the orchestrator's schema (guarded DDL).
- **One readable snapshot** committed with the baseline (via #1431's `render_snapshot_literal`), the declared schema.
- **CI parity gate** (real Postgres): build a scratch DB three ways and assert structural equality with a **readable diff on mismatch** — (a) `alembic upgrade head`, (b) `ensure_framework_schema`, (c) the committed snapshot. Generalizes `test_authstore_alembic_parity_pg.py` from "head id" to "the whole framework schema agrees three ways."

## 4. Behavior change (accepted)

Conditional/lazy framework tables become **eagerly created for every app** (most are tiny/empty). Justification: they're framework-owned, the cost is negligible, and it's the price of a *complete, provable* baseline + a single comprehensible schema source. Documented in the ADR + CHANGELOG. (Genuinely separate concerns — ops DB, prefixed event-bus, per-tenant — stay conditional and excluded, §2.)

## 5. Squash mechanics + stable head

Collapse 0001–0018 into the head baseline file; the baseline now contains the **full** app-DB framework schema (not just params/auth/process). **Keep the head revision id `0019_process_runtime_tables`** (`down_revision=None`) so downstream app chains referencing the current head don't dangle (§6). The id name is a documented wart (it's the baseline, named for the last pre-squash head, retained for chain stability). **Non-idempotent-transform audit:** before deleting 0002–0018, confirm none carries a data migration / destructive `ALTER ... USING` whose loss matters beyond fresh-install (existing DBs already applied them; fresh installs get the final-state baseline). Record in the ADR.

## 6. Consumer adaptation (shared-base migration)

The framework chain is a shared base (one alembic graph via `version_locations`; downstream app migrations chain off the framework head). By state:
1. **At the head / app-migrations chaining off `0019`:** nothing (`alembic_version` still resolves; baseline is the new root; `upgrade head` no-op). Eager tables arrive via the orchestrator at boot (idempotent).
2. **Lagging on an old framework revision:** one `dazzle db migrate` (autostamp #1390: schema materialized + version stale → stamp; guarded so re-run is a no-op).
3. **App-migration whose `down_revision` = a deleted intermediate id (0002–0018):** the one manual case — re-point that single `down_revision` to `0019`, or stamp. Small engaged consumer set → documented one-time per-app fixup.

## 7. CI-managed shared base (the operating process)

1. **Parity gate** (§3) — the three-way equality with readable diff.
2. **Chain-cleanliness gate** — framework `versions/` is the single baseline at the stable head (no dev-churn re-accumulation between releases without an intentional re-squash).
3. **Regeneration command** (`dazzle db reframework-baseline` or extend an existing `db` subcommand) — regenerates the baseline DDL + snapshot from `ensure_framework_schema` deterministically; the parity gate proves it. Agent workflow: change the orchestrator → regenerate → CI proves equality.
4. **Going-forward dual-write rule** widens: a new framework table goes in the orchestrator (+ the baseline is regenerated), not a fresh per-table migration; the rare destructive change adds one incremental migration, re-folded at release.

## 8. Test surgery (audited; see plan for per-file dispositions)

- **Remove (11)** per-migration isolation/stamp-to-N tests for deleted migrations: `test_subtype_alembic_revision`, `test_alembic_drop_dazzle_migrations`, `test_csrf_session_binding_phase1::TestMigration0005`, `test_cli_db_ops::TestMigration0004…`, `test_tenant_is_test_migration`, and the `_pg` `test_migration_00NN_applies…` in `test_auth_membership_pg`/`test_auth_orgprovision_pg`/`test_membership_events_pg`/`test_org_invitations_pg`/`test_connections_pg` (×2). Their behavior is now covered by the baseline + parity gate (note the coverage shift in the ADR).
- **Update (~4 files)** baseline-id references: `test_alembic_assets_packaging_1308`, `test_runtime_schema_startup::TestFrameworkBaselineMigration`, `test_db_baseline_reconcile_1309` (scaffolded baseline id `0001_framework_baseline` → `0019_process_runtime_tables`), and generalize `test_authstore_alembic_parity_pg` to the three-way parity assertion (§3).
- **Keep** mechanism tests (autostamp #1390, reconcile #1309 generic guards, `test_framework_tables_registry_1357`, `test_schema_snapshot` parametric).

## 9. Deliverables

- `ensure_framework_schema(conn)` orchestrator + refactor of the ~10 lazy/conditional inits to it.
- The complete squashed baseline (full app-DB framework schema, stable head id) + the readable snapshot.
- The three-way **parity gate** + **chain-cleanliness gate** + the **regeneration command**.
- Test surgery (§8) + the non-idempotent-transform audit.
- **ADR** — "Complete CI-managed framework migration baseline" — the orchestrator, the eager-creation behavior change + the 3 exclusions, the shared-base risk + consumer runbook, the widened dual-write rule, the re-squash workflow, the test-coverage shift.
- CHANGELOG `### Changed` (minor 0.84.0) with the consumer runbook + behavior-change note.

## 10. Non-goals

- App-entity (project-local) migrations — the consumer's, handled by #1431.
- Bringing ops-DB / prefixed event-bus / per-tenant tables into the app-DB baseline (the 3 documented exclusions).
- A multi-consumer migration-fleet tool — small engaged consumer set; the runbook suffices.

## 11. Failure-modes rubric sign-off (CLAUDE.md gate)

1. *Failure mode risked:* "abstraction hides a load-bearing semantic" — a baseline that silently diverges from what the runtime builds (the exact divergence we found: 19 partial migrations vs the real framework schema). 2. *Detector:* the §3 three-way parity gate (real PG, readable diff) + chain-cleanliness gate. 3. *Live?* yes — CI on every change. 4. *Trace runtime→DSL?* yes — one orchestrator function = the framework schema; the baseline mirrors it; the snapshot declares it; downstream chains reference one stable head. 5. *Preserve semantics?* yes — parity asserted three ways, downstream-chain stability via the stable head id, the consumer runbook explicit, the 3 exclusions documented. **Agent-comprehensibility (the stated goal):** one orchestrator + one baseline + one rule + a readable-diff gate + a regeneration command — an agent reads the schema in one place, verifies it, extends it without archaeology.
