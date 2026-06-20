# RLS-Backed Row Tenancy — Phase D (Production Apply + Static Surfaces) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Checkbox (`- [ ]`) steps.

**Goal:** Make the RLS tenant fence + scope policies (Phases B/C) **actually enforced in production**, and give operators tooling to see + verify them. Phase D delivers: (1) one shared RLS-DDL builder; (2) production apply (`dazzle db apply-rls` + a hook in `dazzle db upgrade`, run as the owner role); (3) `dazzle inspect rls`; (4) an RLS drift gate in `dazzle db verify`.

**Architecture:** Extract the dev-only `server._apply_rls_policies` partitioning into a reusable `build_all_rls_ddl(appspec, entities) -> list[str]`. Wire it into: the existing dev `create_all` apply (refactor to reuse), a new `dazzle db apply-rls` command, the `dazzle db upgrade` flow (apply after migrations — same owner role that runs DDL), `dazzle inspect rls` (show generated vs live), and `dazzle db verify` (drift = generated-policy-set vs live `pg_policies`).

**Tech stack:** Python 3.12, psycopg v3, PostgreSQL `pg_policies`/`pg_class`, typer CLI, pytest.

---

## Context the implementer needs

- **Why prod doesn't enforce today:** RLS policies are runtime-applied only on the dev `create_all` path (`/Volumes/SSD/Dazzle/src/dazzle/http/runtime/server.py:766` `_apply_rls_policies`, gated on `may_create_schema` = non-prod). In prod (Alembic owns the schema) they're never applied → the fence/scope DDL exists but isn't active; app-layer filters are the only enforcement. Phase D fixes this.
- **CRITICAL — apply runs as the OWNER role, not `dazzle_app`.** `ENABLE/FORCE ROW LEVEL SECURITY` + `CREATE POLICY` require table ownership. The runtime connects as the non-owner `dazzle_app` (Phase B), which **cannot** run this DDL. So prod apply must happen in the **deploy/migrate step** (which connects as the owner, like `dazzle db upgrade`/migrations), NOT at `dazzle serve` startup. The dev `create_all` path already runs as the dev superuser/owner, so it's fine there. Do **not** call the apply from serve-boot in prod.
- **Source generators (Phases B/C):** `/Volumes/SSD/Dazzle/src/dazzle/http/runtime/rls_schema.py` — `build_rls_policy_ddl(names, *, partition_key)` (fence+baseline for tenant-flat), `build_rls_scope_policy_ddl(entity, fk_graph, entity_types, *, partition_key)` (per-verb for scoped), `TENANT_GUC`, `USER_GUC_PREFIX`. `predicate_compiler.build_entity_type_resolver(entities)`. `sa_schema.scoped_entity_names(entities, partition_key)`. All DDL is idempotent (DROP-then-CREATE; ENABLE/FORCE re-run-safe).
- **Precedents:** `dazzle db verify` + `detect_signable_drift` (`/Volumes/SSD/Dazzle/src/dazzle/db/signable_drift.py`, #1340) — the drift-gate shape (load appspec, connect, compare expected-vs-live, report, exit non-zero). `dazzle inspect <ext-point>` (`/Volumes/SSD/Dazzle/src/dazzle/cli/inspect.py`) — the `InspectResult`/`InspectEntry`/`_emit` pattern + `@inspect_app.command(...)` registration + manifest-vs-`--runtime`. `dazzle db` command registration + `_resolve_url`/`_run_with_connection` (`/Volumes/SSD/Dazzle/src/dazzle/cli/db.py`).
- **Reading live policies:** `SELECT policyname, cmd, permissive, qual, with_check FROM pg_policies WHERE schemaname='public' AND tablename=%s`; `SELECT relrowsecurity, relforcerowsecurity FROM pg_class WHERE relname=%s AND relnamespace='public'::regnamespace`. The Phase B/C integration tests query `pg_policies` — mirror them.
- **Drift comparison must be shape-based, not text-based.** Comparing the live `qual`/`with_check` TEXT to the generated body is fragile (PG normalizes/reparenthesizes). Compare the **policy SET**: per tenant-scoped table, the expected policy NAMES (`tenant_fence`, `tenant_baseline` or `scope_select`/`scope_insert`/`scope_update`/`scope_delete`) + each one's `cmd` + permissive/restrictive + that RLS is ENABLED and FORCED. Drift = a tenant-scoped table with RLS disabled, a missing expected policy, or an unexpected/extra policy. (Exact-body equivalence is out of scope — that's a deeper, separate check.)
- **API surface:** `dazzle inspect rls` + `dazzle db apply-rls` are CLI tooling, NOT public exports → no `docs/api-surface/` baseline change. Keep `build_all_rls_ddl` internal to `back.runtime` (don't export from `dazzle.__init__`) so `public-helpers` is unaffected. A CHANGELOG entry IS required. Run the full gate to catch any CLI-enumeration/help-snapshot test (e.g. `test_cli_sweep`, `test_docs_drift`) and update deliberately if a new command must be registered there.
- **Out of scope (note as non-goals):** provable-RBAC asserting vs live `pg_policies` (a `dazzle rbac verify --rls` extension — defer); persona-gated DB policies (#604, the OR-vs-first-match nuance from Phase C — defer); exact policy-body equivalence drift. Phase E (excision/provisioning) is separate.

## File structure

| File | Responsibility | Change |
|------|----------------|--------|
| `/Volumes/SSD/Dazzle/src/dazzle/http/runtime/rls_schema.py` | RLS DDL | **Modify** — add `build_all_rls_ddl(appspec, entities) -> list[str]` (extract partitioning) |
| `/Volumes/SSD/Dazzle/src/dazzle/http/runtime/server.py` | Dev apply | **Modify** — `_apply_rls_policies` calls the extracted builder |
| `/Volumes/SSD/Dazzle/src/dazzle/db/rls_apply.py` | Apply RLS DDL to a connection (shared by command + upgrade) | **Create** |
| `/Volumes/SSD/Dazzle/src/dazzle/db/rls_drift.py` | `detect_rls_drift(conn, appspec, entities)` | **Create** |
| `/Volumes/SSD/Dazzle/src/dazzle/cli/db.py` | `dazzle db apply-rls`; hook into `upgrade`; drift in `verify` | **Modify** |
| `/Volumes/SSD/Dazzle/src/dazzle/cli/inspect.py` | `dazzle inspect rls` | **Modify** |
| `/Volumes/SSD/Dazzle/tests/unit/test_rls_build_all.py` | builder unit tests | **Create** |
| `/Volumes/SSD/Dazzle/tests/unit/test_inspect_rls.py` | inspect unit tests | **Create** |
| `/Volumes/SSD/Dazzle/tests/integration/test_rls_apply_and_drift_pg.py` | apply + drift real-PG | **Create** |
| `/Volumes/SSD/Dazzle/docs/reference/deployment.md` + `CHANGELOG.md` | docs | **Modify** |

---

## Task 1: Extract `build_all_rls_ddl`

**Files:** Modify `rls_schema.py`, `server.py`; test `tests/unit/test_rls_build_all.py`.

- [ ] **Step 1: Failing tests** — `build_all_rls_ddl(appspec, entities)` returns: `[]` when `tenancy` is None / not SHARED_SCHEMA / no scoped entities; for a SHARED_SCHEMA appspec with a scoped entity (has `access.scopes`) → includes its `scope_*` policies + drops `tenant_baseline`; for a tenant-flat scoped entity → fence + baseline; raises `ValueError` when a scoped-with-rules entity has no `fk_graph`. (Construct a synthetic appspec + back-spec entities mirroring `test_rls_scope_policies.py`.)
- [ ] **Step 2: Run → fail.**
- [ ] **Step 3: Implement** `build_all_rls_ddl(appspec, entities) -> list[str]` in rls_schema.py — lift the partitioning logic verbatim from `server._apply_rls_policies:766-859` (scoped_entity_names + build_entity_type_resolver + the scoped-vs-flat loop + fail-loud-on-missing-fk_graph). It computes everything from `appspec` (`tenancy`, `domain.entities`, `fk_graph`) + the passed back-spec `entities`. Returns the flat DDL list (no DB).
- [ ] **Step 4: Refactor `server._apply_rls_policies`** to `statements = build_all_rls_ddl(self._appspec, self._entities)` then `if statements: with engine.begin() as conn: ...`. Behavior must be identical (the existing server RLS unit tests + the dev-boot smoke stay green). Keep the loud-halt + logging.
- [ ] **Step 5: Run** `pytest tests/unit/ -k "rls_build_all or rls_schema or rls_scope or server" -q`; ruff + mypy clean. Commit `refactor(rls): extract build_all_rls_ddl shared by dev-apply/prod-apply/inspect/drift (Phase D)`.

---

## Task 2: Production apply — `dazzle db apply-rls` + `dazzle db upgrade` hook

**Files:** Create `src/dazzle/db/rls_apply.py`; modify `src/dazzle/cli/db.py`; test in Task 4's integration file (apply path) + a unit test for the command wiring.

- [ ] **Step 1:** Create `src/dazzle/db/rls_apply.py` with `apply_rls_policies(conn, appspec, entities) -> int` — runs `build_all_rls_ddl(...)` statements on `conn` (sync or async to match `_run_with_connection`'s contract — check db.py), returns the statement count; no-op (returns 0) when the DDL list is empty. Idempotent (the DDL is DROP-then-CREATE).
- [ ] **Step 2: `dazzle db apply-rls` command** in db.py (mirror `verify_command`): resolve URL (`_resolve_url`), load appspec + convert entities, `_run_with_connection(... apply_rls_policies ...)`, print the count + a note that this must run as a role that owns the tables (the deploy/owner role). `--database-url`/`--tenant`/`--json` options like verify. Gated: if `tenancy` not SHARED_SCHEMA, print "no row-level tenancy; nothing to apply" and exit 0.
- [ ] **Step 3: Hook `dazzle db upgrade`** — after the alembic upgrade succeeds, in SHARED_SCHEMA mode, call `apply_rls_policies` (same connection/role that just ran migrations = owner = correct privilege). Make it best-effort-loud: log applied count; if it raises, surface clearly (the upgrade already changed schema, so don't silently swallow — but don't leave the migration half-done; log ERROR + re-raise). Add a `--no-rls` escape to skip (for operators applying RLS separately). Confirm `dazzle db upgrade` connects as an owner-capable role (it runs DDL migrations, so yes).
- [ ] **Step 4:** Unit test the command wiring (typer runner + a stub appspec/conn): `apply-rls` on a non-tenant app → exit 0 "nothing to apply"; on a shared_schema app → calls apply_rls_policies. (Real-PG apply is Task 4.)
- [ ] **Step 5:** Run the db-cli unit slice + full `dazzle --help`/CLI-sweep test if one exists; ruff + mypy clean. Commit `feat(rls): dazzle db apply-rls + apply RLS on db upgrade (production enforcement, owner role) (Phase D)`.

---

## Task 3: `dazzle inspect rls`

**Files:** Modify `src/dazzle/cli/inspect.py`; test `tests/unit/test_inspect_rls.py`.

- [ ] **Step 1: Failing tests** — `dazzle inspect rls` (manifest mode) on a shared_schema fixture lists the expected policies per tenant-scoped entity (entry per `tenant_fence`/`tenant_baseline`/`scope_*`, with the table + cmd + permissive/restrictive + source framework-vs-scope-rule); on a non-tenant app → empty/notes "no row-level tenancy". Use the typer runner + `fixtures/tenant_rls`.
- [ ] **Step 2: Run → fail.**
- [ ] **Step 3: Implement `@inspect_app.command("rls")`** (mirror an existing inspector): load appspec; derive entries by parsing the `build_all_rls_ddl` output OR (cleaner) by introspecting the same per-entity structure the builder uses — list each policy name + table + verb/cmd + permissive/restrictive + whether it comes from the framework fence/baseline or a DSL `scope:` rule. `--runtime` flag: connect to the DB and cross-reference against live `pg_policies` (report missing/extra as `mismatches`), reusing `detect_rls_drift` (Task 4) for the live comparison. Manifest-only by default (no DB). `_emit(result, output_json)`.
- [ ] **Step 4: Run** `pytest tests/unit/test_inspect_rls.py -v` + the inspect slice; ruff + mypy clean. Commit `feat(rls): dazzle inspect rls — generated (and --runtime live) policy view (Phase D)`.

---

## Task 4: RLS drift gate + real-PG apply/drift proof

**Files:** Create `src/dazzle/db/rls_drift.py`; modify `dazzle db verify` (db.py); create `tests/integration/test_rls_apply_and_drift_pg.py`.

- [ ] **Step 1:** Create `detect_rls_drift(conn, appspec, entities) -> list[dict]` (mirror `detect_signable_drift`). For each tenant-scoped entity: query `pg_class` (relrowsecurity/relforcerowsecurity) + `pg_policies` (policyname, cmd, permissive); compute the EXPECTED policy set from the builder's per-entity structure (names + cmd + permissive/restrictive + RLS enabled+forced). Drift entry per table: `{entity, issues:[...]}` for — RLS not enabled/forced, missing expected policy, unexpected extra policy. **Shape-based, not qual-text** (see Context). Empty list = no drift.
- [ ] **Step 2: Wire into `dazzle db verify`** — add `detect_rls_drift` alongside the FK + signable checks in the `_run` aggregate; include in the human + JSON output; exit non-zero if RLS drift found (mirror the existing exit logic).
- [ ] **Step 3: Real-PG integration test** `tests/integration/test_rls_apply_and_drift_pg.py` (e2e+postgres, scratch DB, mirror the Phase B/C harness): (a) **apply** — load `fixtures/tenant_rls`, create_all (as owner), run `apply_rls_policies(conn, appspec, entities)`, assert `pg_policies`/`pg_class` show the fence+scope policies + RLS enabled+forced; assert idempotent (re-apply → no error, same policy set). (b) **drift detected** — after apply, `detect_rls_drift` → empty; then `DROP POLICY tenant_fence ON "Project"` (or disable RLS on one table) → `detect_rls_drift` reports exactly that table's missing fence; (c) **no drift on a clean apply**. Drop scratch DB in finally.
- [ ] **Step 4: Run** the integration test against a scratch DB (must pass, not skip); the db-verify unit slice; ruff + mypy. Commit `feat(rls): RLS drift gate in dazzle db verify + real-PG apply/drift proof (Phase D)`.

---

## Task 5: Docs, changelog, ship

- [ ] **Step 1: Update `docs/reference/deployment.md`** — replace the Phase-B/C "run the policy DDL manually" note with the real story: in production, `dazzle db upgrade` now applies RLS after migrations (as the owner role), or run `dazzle db apply-rls` explicitly; `dazzle db verify` gates RLS drift in CI; `dazzle inspect rls` shows the generated/live policy set. RLS DDL must run as the table owner (`dazzle_owner`), not the runtime `dazzle_app`.
- [ ] **Step 2: CHANGELOG + Agent Guidance** — Phase D: production RLS enforcement (apply on `db upgrade` + `db apply-rls`, owner-role), `dazzle inspect rls`, RLS drift in `dazzle db verify`. Note non-goals (provable-RBAC-vs-pg_policies, persona-gating #604, exact-body drift). Update the Phase B/C "prod doesn't auto-apply" guidance to "now applied via db upgrade / db apply-rls".
- [ ] **Step 3: Full gate** — `ruff check src/ tests/ --fix && ruff format src/ tests/`; `mypy src/dazzle`; `pytest tests/ -m "not e2e"`. Watch CLI-enumeration/help/docs-drift tests (new `dazzle db apply-rls` + `dazzle inspect rls` commands) — update any command snapshot deliberately. Green.
- [ ] **Step 4:** `/bump patch` (0.81.23 → 0.81.24); update CHANGELOG header; commit.

## Final integration & ship
- [ ] **Independent review** over the whole Phase D diff — focus: (a) the **owner-vs-app-role** correctness (apply runs where it has ownership; never from serve-boot/dazzle_app); (b) `build_all_rls_ddl` extraction is behavior-identical to the old `_apply_rls_policies`; (c) drift detection is shape-based + correct (no false drift on a clean apply; catches a dropped policy / disabled RLS); (d) `db upgrade` hook doesn't leave a half-applied state silently; (e) idempotent re-apply. (Standard review depth — the enforcement itself shipped in B/C; this is apply-mechanism + tooling.)
- [ ] Confirm green + clean; FF-merge to main + push; watch CI green.
- [ ] Update memory `project_rls_tenancy.md`: Phase D shipped (prod apply via db upgrade/apply-rls as owner; inspect rls; drift gate); only Phase E (lifecycle, #1338/#1339) remains.

---

## Self-Review notes (planner)
- **Spec coverage:** the design's Phase D = static surfaces (`inspect rls` + drift gate + provable-RBAC) + prod apply. Covered: builder extraction (T1), prod apply as owner (T2), inspect (T3), drift gate (T4). Provable-RBAC-vs-pg_policies + persona-gating explicitly deferred (noted).
- **Key correctness constraint:** apply runs as the OWNER role (deploy/migrate step), never the runtime `dazzle_app` — baked into T2 (db upgrade hook + apply-rls command, not serve-boot).
- **Drift is shape-based** (policy presence/cmd/permissive + RLS enabled/forced), not fragile qual-text — stated in Context + T4.
- **Type consistency:** `build_all_rls_ddl(appspec, entities) -> list[str]`; `apply_rls_policies(conn, appspec, entities) -> int`; `detect_rls_drift(conn, appspec, entities) -> list[dict]`.
- **Risk:** the `db upgrade` hook must run as an owner-capable role and not swallow a half-applied state — flagged for the review.
```
