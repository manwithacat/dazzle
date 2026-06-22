# Framework migration baseline: a CI-managed, squashed shared base

**Status:** Design (brainstormed 2026-06-22), ready for implementation plan.
**Builds on:** the dual-write convention (`_init_db` + guarded alembic mirror), #1431 (DSL-snapshot migration engine + `SCHEMA_SNAPSHOT` serializer), #1390 (autostamp/reconcile), #1309 (baseline reconcile). Ships on a **minor bump (0.84.0)**.
**Disposition:** Medium — collapses the framework migration chain to a single baseline + adds CI gates that keep it faithful. One spec; one implementation plan.

---

## 1. The principle

**New apps built from Dazzle should see a single clean framework migration baseline, not the accreted dev-process churn — and CI, not humans, keeps that baseline provably faithful to what the runtime actually builds.**

Today the framework ships **19 migrations** (`src/dazzle/http/alembic/versions/0001…0019`) — the visible sediment of development. A developer scaffolding an app from Dazzle vX inherits all 19. They are almost all *guarded, idempotent mirrors* of what `_init_db` already creates at boot (the dual-write rule), so the chain carries little independent value yet all the mess.

The goal: **collapse them to one baseline**, and make the shared base a **managed, automated, agent-comprehensible process** rather than a hand-maintained pile.

## 2. Key architectural facts (why this is safe, and where the risk is)

- **Dual-write:** `_init_db` (every boot, guarded `CREATE TABLE / ADD COLUMN IF NOT EXISTS`, advisory-locked) is the *real* framework-schema mechanism. The alembic chain is a **stampable baseline + parity record**, not the evolution engine. (Auth-store parity precedent.)
- **The framework chain is a *shared base*.** A user app's `dazzle db revision` writes to project-local `.dazzle/migrations/versions/`, and `_get_alembic_cfg` chains both via `version_locations` into **one** alembic graph / one `alembic_version` table. So a deployed app's first app-entity migration has `down_revision` pointing at the framework head it was created against. **Deleting framework revision ids orphans downstream chains** — the central risk.
- **`SCHEMA_SNAPSHOT` (#1431):** the migration engine embeds a serialized schema snapshot in a migration and diffs *intent-vs-snapshot* (DSL-vs-DSL), hermetic and DB-independent. We reuse the serializer to make the framework baseline self-describing and the CI parity check produce a **readable diff** on failure (agent-comprehensible).

## 3. The model: one fixed-head baseline, mirror of `_init_db`, CI-verified

- The framework `versions/` dir holds **one** baseline file: the full current framework schema as **guarded** DDL (`CREATE TABLE / INDEX IF NOT EXISTS`), `down_revision = None`.
- Its **revision id is held stable** across this squash so downstream chains that reference the current head don't dangle (see §5 for the id choice + consumer adaptation).
- A **readable framework schema snapshot** (via #1431's serializer) is attached to / committed alongside the baseline — the declared "this is the schema this baseline produces."
- **`_init_db` remains the evolution mechanism** for additive framework changes (new table/column → guarded `_init_db` DDL applies at boot on existing DBs; the baseline is regenerated to match for fresh installs). The **rare destructive** framework change (drop/retype) adds **one** incremental migration on top of the baseline, re-folded at the next release squash.
- **Re-squash is a repeatable release-boundary operation**, not a one-off (§6).

This is the robust shape: **one file, one rule (baseline ≡ `_init_db`), CI-enforced.**

## 4. CI-managed shared base (the heart of the request)

A new CI gate + a `dazzle db` subcommand operate the base so humans don't hand-maintain it:

1. **Parity gate (`baseline ≡ _init_db ≡ snapshot`).** In CI (real Postgres): build a scratch DB two ways — (a) `alembic upgrade head` (the baseline), (b) `_init_db`. Introspect both; assert structural equivalence (tables, columns, types, indexes, constraints). Also assert the committed **snapshot** equals the introspected schema. On mismatch, emit a **readable diff** (what the baseline has vs what `_init_db` produces vs the snapshot) — so an agent sees exactly which table/column drifted. This generalizes the existing `test_authstore_alembic_parity_pg.py` from "head id is N" to "the whole framework schema agrees three ways."
2. **Chain-cleanliness gate.** Assert the framework `versions/` dir is the single baseline (plus at most the documented in-flight destructive migrations), at the stable head id — so dev-churn files don't silently re-accumulate between releases without an intentional re-squash.
3. **Regeneration command** (`dazzle db reframework-baseline` or similar): regenerates the baseline DDL + snapshot from `_init_db`'s current schema, deterministically. The gate (1) is what proves the regenerated baseline is correct. Agent workflow: change `_init_db` → run the command → CI parity gate confirms.

## 5. Consumer adaptation (the shared-base migration)

The squash collapses 0001–0018 into the head baseline. Adaptation by consumer DB state:

1. **At the current head, or app-migrations chaining off it:** **nothing.** `alembic_version` still resolves; the baseline is the new graph root; `upgrade head` is a no-op; next `dazzle db revision` still chains off the head.
2. **Lagging on an old framework revision (schema materialized by `_init_db`, `alembic_version` stale):** one command — `dazzle db migrate` (autostamp, #1390: "schema materialized, version stale → stamp to head"; baseline is guarded so re-run is a no-op). `dazzle db reconcile-baseline` (#1309) covers the merge variant.
3. **App-migration whose `down_revision` = a deleted intermediate id (0001–0018):** the one manual case — re-point that single `down_revision` to the head baseline id, or stamp. For the small, engaged consumer set, a documented one-time per-app fixup.

**Id choice (implementation detail, recommendation):** keep the **current head revision id** as the baseline id (minimizes case-1 → "nothing" for everyone on a recent Dazzle); accept that case-3 (old-head chainers) re-point. Documented in the ADR runbook. (Alternative — a fixed semantic id like `0001_framework_baseline` — maximizes long-term clarity but forces more re-pointing now; rejected for higher immediate disruption.)

## 6. The repeatable re-squash workflow (release boundary)

1. During dev, framework schema changes ride `_init_db` (additive) or a one-off incremental migration (destructive).
2. At a release boundary: run the regeneration command → baseline DDL + snapshot refreshed from `_init_db`.
3. CI parity gate (§4.1) proves `baseline ≡ _init_db ≡ snapshot`; chain-cleanliness gate (§4.2) proves it's a single file at the stable head.
4. Minor bump; CHANGELOG `### Changed` notes the baseline refresh + the consumer runbook.

## 7. Blast radius / tests to update

~10 tests pin specific framework revision ids or per-migration behavior. Each is updated or replaced:
- `test_authstore_alembic_parity_pg.py` — generalize from "head == 0019" to the three-way parity assertion (§4.1).
- `test_alembic_drop_dazzle_migrations.py`, `test_subtype_alembic_revision.py`, `test_db_migrate_autostamp_1390.py`, `test_db_baseline_reconcile_1309.py`, `test_framework_tables_registry_1357.py`, `test_alembic_assets_packaging_1308.py`, `test_csrf_session_binding_phase1.py`, `test_runtime_schema_startup.py`, `test_cli_db_ops.py`, `test_schema_snapshot.py` — audit each: tests of a *deleted* migration's behavior are removed if that behavior is now covered by the baseline + parity gate; tests of *mechanism* (autostamp/reconcile) are repointed to the new head id. The implementation plan enumerates the disposition of each.
- **Non-idempotent-transform audit:** before deleting 0001–0018, confirm none carries a data migration or destructive `ALTER ... USING` whose loss matters for any path other than fresh-install (it doesn't — existing DBs already applied them; fresh installs get the final-state baseline). Record the audit in the ADR.

## 8. Deliverables

- The squashed single framework baseline (guarded full schema, `down_revision=None`, stable head id) + the readable schema snapshot.
- `dazzle db` regeneration command + the two CI gates (parity, chain-cleanliness).
- Updated/removed revision-pinning tests (§7) + the non-idempotent-transform audit.
- **ADR** — "CI-managed framework migration baseline" — the model, the shared-base risk, the consumer-adaptation runbook, the re-squash workflow.
- CHANGELOG `### Changed` (minor 0.84.0) with the consumer runbook.

## 9. Non-goals

- Squashing *app-entity* (project-local) migrations — those are the consumer's, handled by #1431; out of scope.
- Changing `_init_db` as the framework evolution mechanism (it stays; the baseline mirrors it).
- A general multi-consumer migration-fleet tool — the consumer set is small and engaged; the runbook suffices.

## 10. Failure-modes rubric sign-off (CLAUDE.md gate)

1. *Failure mode risked:* "abstraction hides a load-bearing semantic" — a baseline that silently diverges from what the runtime builds. 2. *Detector:* the §4.1 three-way parity gate (baseline ≡ `_init_db` ≡ snapshot) on real Postgres + the chain-cleanliness gate. 3. *Live?* yes — CI on every change; readable diff on failure. 4. *Trace runtime→DSL?* yes — the baseline is guarded DDL a developer can read; the snapshot is the declared schema; downstream chains reference one stable head. 5. *Preserve semantics?* yes — `_init_db` parity is asserted, downstream-chain stability is preserved by the stable head id, the consumer runbook is explicit. **Agent-comprehensibility (the stated goal):** one baseline file + one rule + a readable-diff gate + a regeneration command — an agent can read the base, verify it, and extend it without archaeology.
