# Framework Migration Baseline (complete mirror) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to execute this plan task-by-task, with **independent adversarial review on Tasks 1, 2, 4** (schema-sensitive: the orchestrator, the squashed baseline, the parity gate). Steps use checkbox (`- [ ]`) syntax. **This plan is written for a FRESH session** — the design session deferred execution here.

**Goal:** Replace the 19-file partial framework migration chain with one orchestrator (`ensure_framework_schema`) + one complete squashed baseline that provably mirrors it, CI-gated, shipped on a minor (0.84.0).

**Architecture:** A single advisory-locked idempotent `ensure_framework_schema(conn)` becomes the only source of the app-DB framework schema (consolidating ~14 scattered `_init_db`/`ensure_*` entry points). The squashed alembic baseline (stable head id `0019_process_runtime_tables`, `down_revision=None`) mirrors it; a committed readable `SCHEMA_SNAPSHOT` declares it; a real-Postgres CI gate asserts `alembic-head ≡ orchestrator ≡ snapshot` with a readable diff. The ~10 currently-lazy/conditional tables become eagerly created (accepted behavior change). Three concerns stay excluded (ops DB, prefixed event-bus, tenant registry).

**Tech Stack:** Python 3.12+, psycopg3 + SQLAlchemy `inspect`, Alembic, #1431 `dazzle.db.schema_snapshot`/`schema_diff` serializer, pytest (unit + real-PG). Spec: `docs/superpowers/specs/2026-06-22-framework-migration-baseline-design.md`.

## Global Constraints

- **One orchestrator is the source of truth.** `ensure_framework_schema(conn)` creates ALL in-scope app-DB framework tables; the baseline mirrors it; the gate proves equality. No table is created in two divergent places.
- **In-scope tables (enshrine all — usage-audited live, spec §2):** `_dazzle_params`; all auth tables (`users, sessions, memberships, organizations, membership_events, invitations, connections, connection_secret_events, scim_groups, scim_group_members, saml_consumed_assertions, password_reset_tokens, magic_links, email_verification_tokens, user_preferences, join_requests`); `process_runs, process_tasks`; `_dazzle_audit_log, _dazzle_atomic_audit, dazzle_files, refresh_tokens, devices, _grants, _grant_events, _dazzle_otp_codes, _dazzle_recovery_codes, _dazzle_event_inbox, _dazzle_event_outbox`.
- **Excluded (do NOT put in the app-DB baseline):** ops_database tables (separate DB), event-bus `{prefix}events/offsets/dlq` (dynamic prefix), tenant registry `public.tenants` + per-tenant schemas.
- **Stable head id** `0019_process_runtime_tables`, `down_revision=None` — preserves downstream app-migration chains.
- **Idempotent + advisory-locked** DDL (`CREATE TABLE/INDEX IF NOT EXISTS`, `ADD COLUMN IF NOT EXISTS`); existing DBs re-run as a no-op.
- **Behavior change accepted:** in-scope conditional tables created eagerly for every app (document in ADR + CHANGELOG).
- Pre-ship gate = `pytest -m "not e2e"` from repo root + the real-PG suites (`DATABASE_URL`) + drift/ratchet gates; ruff, mypy, lint-imports. Ship discipline: `/bump minor` (0.84.0), ruff-format touched files before commit.

---

### Task 0: Non-idempotent-transform audit (read-only gate before deletion)

**Files:** none (analysis → `dev_docs/` note + ADR input).

- [ ] Read every migration `0002`–`0018` in `src/dazzle/http/alembic/versions/`. For each, classify its ops: pure guarded `CREATE`/`ADD COLUMN IF NOT EXISTS` (safe to fold) vs. a **data migration** (`op.execute` UPDATE/INSERT/bulk_insert) or **destructive/transform** (`op.drop_*`, `op.alter_column` type change, `ALTER … USING`). List any of the latter.
- [ ] For each non-trivial transform, confirm it's already applied on the live deployment (so deleting the historical step only affects a hypothetical mid-chain DB, which the consumer runbook covers). Record the audit table in the ADR (Task 7). **If a transform can't be safely dropped, STOP and escalate** — it may need to remain as a one incremental migration atop the baseline.
- [ ] Commit the audit note: `git commit -m "docs: #framework-baseline non-idempotent-transform audit (0002-0018)"`.

---

### Task 1: `ensure_framework_schema(conn)` orchestrator  *(adversarial review)*

**Files:**
- Create: `src/dazzle/http/runtime/framework_schema.py`
- Modify: the ~14 entry points (delegate to / be subsumed by the orchestrator) — `auth/store.py` (`_init_db`), `migrations.py` (`ensure_dazzle_params_table`), `process_schema.py` (`ensure_process_tables`), `audit_log.py`, `atomic_flow_executor.py`, `file_storage.py`, `token_store.py`, `device_registry.py`, `grant_store.py`, `otp_store.py`, `recovery_codes.py`, `inbox.py`, `outbox.py` (+ their DDL-constant modules).
- Test: `tests/unit/test_framework_schema.py` (real-PG)

**Interfaces:**
- Produces: `ensure_framework_schema(conn: Any) -> None` — advisory-locked, idempotent; on return, ALL in-scope tables (global-constraints list) exist. Plus boot wiring so it runs once at startup (replacing the scattered per-subsystem creates).

**Approach:** consolidate each in-scope store's existing DDL (already idempotent + mostly already in DDL-constant modules — reuse them) into one orchestrator under a single advisory lock. Keep each store's *runtime* API; remove its conditional table-creation (or make it call the orchestrator's per-group helper). The orchestrator is the union; eager creation is the behavior change.

- [ ] Step 1: failing real-PG test — call `ensure_framework_schema(conn)` on a scratch DB; assert every in-scope table exists (`information_schema`); call twice (idempotent, no error). RED.
- [ ] Step 2: implement the orchestrator (compose the existing DDL constants/`_init_db` bodies; one `pg_advisory_xact_lock`; reuse `claim`/auth/process DDL). GREEN.
- [ ] Step 3: refactor the entry points to delegate (no divergent second creator). Run `pytest -m "not e2e" -k "auth or audit or file or token or device or grant or otp or recovery or inbox or outbox or process or params"` (both env modes) — fix fallout from eager creation.
- [ ] Step 4: wire `ensure_framework_schema` into boot (replace the scattered creates at the call sites the audit found). Commit.

> Adversarial review focus: completeness (every in-scope table; nothing excluded leaked in; no in-scope table left to a divergent creator), idempotency + advisory-lock correctness, eager-creation fallout, that excluded tables (ops/prefixed-bus/tenant) are untouched.

---

### Task 2: The complete squashed baseline  *(adversarial review)*

**Files:**
- Modify: `src/dazzle/http/alembic/versions/0019_process_runtime_tables.py` → becomes the full baseline (`down_revision=None`, all in-scope tables, guarded).
- Delete: `0002_…`–`0018_…` (and `0001_framework_baseline.py` folded in).
- Test: `tests/unit/test_runtime_schema_startup.py` (update baseline assertions).

- [ ] Step 1: write the baseline `upgrade()` to create exactly the orchestrator's schema (guarded DDL; `down_revision=None`; keep `revision="0019_process_runtime_tables"`). Mirror the orchestrator table-for-table.
- [ ] Step 2: delete 0001–0018. Run `alembic upgrade head` on a scratch DB → succeeds, single head.
- [ ] Step 3: update `test_runtime_schema_startup` baseline-id/coverage assertions. GREEN. Commit.

> Adversarial review focus: baseline ≡ orchestrator (table/column/index parity — Task 4's gate is the real proof, but eyeball here); `down_revision=None`; head id unchanged; deleted migrations carry no un-folded transform (Task 0).

---

### Task 3: Committed readable `SCHEMA_SNAPSHOT`

**Files:** the baseline file (embed `SCHEMA_SNAPSHOT = …`) or a sibling committed snapshot; reuse `dazzle.db.schema_snapshot.render_snapshot_literal`.

- [ ] Generate the snapshot from the orchestrator's resulting schema (introspect a scratch DB built by `ensure_framework_schema`, or from metadata) via `render_snapshot_literal`; commit it with the baseline. Test: the snapshot parses and equals the introspected schema.

---

### Task 4: Three-way parity gate (real PG)  *(adversarial review)*

**Files:** Test: `tests/integration/test_framework_baseline_parity_pg.py`; generalize `tests/integration/test_authstore_alembic_parity_pg.py`.

**Interfaces:** Consumes a live-DB schema-introspection helper (build one — `sa.inspect(conn)` → the `schema_snapshot` ColSnap/TableSnap shape — there is no existing full-introspection fn; add `introspect_schema(conn) -> Snapshot` next to `schema_snapshot.py`).

- [ ] Step 1: failing test — on three scratch DBs/states: (a) `alembic upgrade head`, (b) `ensure_framework_schema`, (c) the committed snapshot; introspect (a)+(b), assert `(a) == (b) == (c)` over the in-scope tables; on mismatch emit a **readable diff** (reuse `schema_diff.diff` to render the delta). RED.
- [ ] Step 2: implement `introspect_schema` + the gate; make all three agree (fixing any baseline/orchestrator drift Task 1/2 left). GREEN. Commit.

> Adversarial review focus: the gate genuinely compares all in-scope tables (not a subset); the readable-diff path works; excluded tables aren't falsely flagged; runs in CI's PostgreSQL job.

---

### Task 5: Chain-cleanliness gate + regeneration command

**Files:** Test: `tests/unit/test_framework_chain_clean.py`; Modify: `src/dazzle/cli/db.py` (add `reframework-baseline` or extend `snapshot-baseline`).

- [ ] Chain-cleanliness test: assert `src/dazzle/http/alembic/versions/` is the single baseline at the stable head (plus at most documented incremental migrations).
- [ ] Regeneration command: regenerates the baseline DDL + snapshot from `ensure_framework_schema` deterministically (introspect a scratch DB built by the orchestrator → emit baseline + `render_snapshot_literal`). Test it round-trips (regenerate → parity gate still green). Commit.

---

### Task 6: Test surgery

**Files:** per the spec §8 audit.

- [ ] **Remove** the 11 per-migration tests: `test_subtype_alembic_revision.py`, `test_alembic_drop_dazzle_migrations.py`, `test_csrf_session_binding_phase1.py::TestMigration0005`, `test_cli_db_ops.py::TestMigration0004WidensVersionNum1282`, `test_tenant_is_test_migration.py`, and the `test_migration_00NN_*` functions in `test_auth_membership_pg.py`/`test_auth_orgprovision_pg.py`/`test_membership_events_pg.py`/`test_org_invitations_pg.py`/`test_connections_pg.py` (×2). Note the coverage shift in the ADR.
- [ ] **Update** baseline-id references: `test_alembic_assets_packaging_1308.py` (file name → `0019_process_runtime_tables.py`), `test_runtime_schema_startup.py::TestFrameworkBaselineMigration` (import + `revision` assertion; keep `down_revision is None`), `test_db_baseline_reconcile_1309.py` (scaffolded `0001_framework_baseline` → `0019_process_runtime_tables`; drop the intermediate-migration scaffolding in `test_guard_traces_framework_root_…`).
- [ ] Run `pytest -m "not e2e" -k "alembic or migration or baseline or schema_startup or reconcile"` (both env modes) → green. Commit.

---

### Task 7: ADR + CHANGELOG + ship (0.84.0)

**Files:** Create `docs/adr/0044-framework-migration-baseline.md` (+ INDEX); Modify `CHANGELOG.md`.

- [ ] ADR: the orchestrator-as-source-of-truth, the eager-creation behavior change + the 3 exclusions, the shared-base risk + the consumer-adaptation runbook (spec §6), the widened dual-write rule, the re-squash workflow, the test-coverage shift, the Task-0 transform audit.
- [ ] CHANGELOG `### Changed` (0.84.0): the squash + behavior change + consumer runbook.
- [ ] **Full gate** — `pytest -m "not e2e"` repo root + real-PG suites + drift/ratchet (golden_master, parser_corpus, api_surface_drift, docs_drift, complexity_ratchet, deferred_imports_ratchet) + mypy + lint-imports. Regenerate baselines that legitimately shift.
- [ ] `/bump minor` (0.84.0), commit, tag, push, watch CI green, then write the ADR/CHANGELOG note. (No GitHub issue tied; this is the Celery/PG-coordination arc's capstone.)

---

## Self-Review

**Spec coverage:** §1 principle → Tasks 1+2+4. §2 audit/in-scope/excluded → global constraints + Task 1. §3 orchestrator+baseline+snapshot+gate → Tasks 1/2/3/4. §4 behavior change → Task 1 + ADR. §5 squash+stable-head+transform-audit → Tasks 0/2. §6 consumer adaptation → ADR (Task 7). §7 CI-managed process → Tasks 4/5 + the widened rule. §8 test surgery → Task 6. §9 deliverables → all tasks. §11 rubric → Task 4 gate is the live detector.

**Placeholder scan:** the orchestrator/baseline DDL is "consolidate the existing idempotent DDL constants/`_init_db` bodies" (named entry points in global constraints) rather than transcribing ~30 tables' DDL verbatim — appropriate for a *fresh-session subagent-driven* execution where each task fleshes its DDL from the cited existing source; the novel logic (the `introspect_schema` helper, the three-way gate, the regeneration command, the test dispositions) is specified concretely.

**Type consistency:** `ensure_framework_schema(conn)` (Task 1) consumed by Tasks 2/4/5. `introspect_schema(conn) -> Snapshot` (Task 4) reuses `schema_snapshot`'s ColSnap/TableSnap shape, fed to `schema_diff.diff` for the readable diff. Stable head id `0019_process_runtime_tables` consistent across Tasks 2/5/6.

**Scope:** large but one coherent arc (one orchestrator + one baseline + the gate + test surgery); execute fresh, subagent-driven, adversarial on 1/2/4.
