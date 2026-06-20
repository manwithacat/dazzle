# RLS-Backed Row Tenancy — Phase B (Tenant Fence) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`) syntax. **This is the security-critical phase — the final review is adversarial.**

**Goal:** Make the tenant boundary **DB-enforced** for `tenancy: mode: shared_schema` apps: generate + apply PostgreSQL RLS so a connection scoped to tenant A physically cannot read or write tenant B's rows, fail-closed when context is unset. Phase B delivers the **tenant fence + permissive baseline + FORCE RLS + runtime context + role model + adversarial proof**. (Intra-tenant per-verb scope policies are Phase C; this phase keeps app-layer scope filters as defense-in-depth.)

**Architecture:** (1) A DDL generator (`rls_schema.py`) emits, per tenant-scoped entity, `ENABLE/FORCE ROW LEVEL SECURITY` + a **restrictive `tenant_fence`** (`tenant_id = current_setting('dazzle.tenant_id', true)::uuid`) + a **permissive `tenant_baseline`** (`USING(true)`). (2) Runtime sets the GUC per transaction via `set_config(...,true)` from the authenticated user's tenant, applied on each leased connection (mirrors `_set_search_path`); policies applied post-`create_all` (mirrors `_apply_search_indexes`). (3) A three-role model (`dazzle_owner`/`dazzle_app`/`dazzle_bypass`); the app connects as `dazzle_app` in prod for enforcement. (4) Adversarial real-PG tests connecting as `dazzle_app`.

**Tech stack:** Python 3.12, psycopg v3 + psycopg_pool, PostgreSQL RLS, pytest (`-m "not e2e"` unit, `-m postgres` real-PG).

---

## Context the implementer needs

- **Authoritative DDL:** `/Volumes/SSD/Dazzle/docs/superpowers/specs/2026-06-04-rls-tenancy-generation-rules.md` — §1.2 (ENABLE/FORCE), §1.3 (the restrictive fence — note `current_setting('dazzle.tenant_id', true)` with the **missing-ok `true` arg**, required for fail-closed), §1.4 (the **permissive baseline** — a fenced table with no permissive policy is **deny-all**), §1.5 (combination), §3 (role model), §6 (runtime context: `set_config(...,true)`, fail-closed, transactions mandatory, empty-string is a hard error), §9 (the test list). Where this plan and the companion differ on emitted SQL, **the companion wins**.
- **Decisions (locked with @manwithacat):**
  - **Emission = runtime-apply** (a `_apply_rls_policies(engine)` post-`create_all`, mirroring `_apply_search_indexes` at `/Volumes/SSD/Dazzle/src/dazzle/http/runtime/server.py:684`). Idempotent DDL. NOT an Alembic migration (versioning/verification comes from Phase D's drift gate). App-layer scope filters remain in Phase B, so a skipped apply cannot leak.
  - **Role model = generate roles + docs; tests connect as `dazzle_app`; dev runs unenforced.** Superusers bypass RLS even under FORCE, so RLS only enforces when the app connects as a non-superuser non-owner (`dazzle_app`). In local dev (superuser DATABASE_URL) RLS is bypassed and app-layer filters enforce — acceptable; prod connects as `dazzle_app`. Role-creation DDL is for the **test fixture + deploy docs**, NOT the per-boot apply (roles are cluster-level).
- **Scope — fence tenant-scoped DOMAIN entities only.** Use `scoped_entity_names(appspec.domain.entities, partition_key)` (Phase A, `/Volumes/SSD/Dazzle/src/dazzle/http/runtime/sa_schema.py:333`) + `appspec.tenancy.isolation.mode == TenancyMode.SHARED_SCHEMA` + `.partition_key`. The framework `users`/`sessions`/auth tables are raw-SQL in `public` (not EntitySpecs) and are **NOT fenced** here — login keeps working; user-table fencing + "auth resolves tenant first" is the separate auth-store-rework phase.
- **Greenfield only.** No migration of existing deployed schemas.
- **Out of scope (later phases):** intra-tenant per-verb scope policies + the `predicate_compiler` GUC retarget (Phase C); `dazzle inspect rls` + drift gate + provable-RBAC-vs-pg_policies (Phase D); excision/provisioning/containment (Phase E); auth-store tenant-scoping (its own phase). Do NOT build these.
- **No existing RLS** anywhere in the tree (greenfield — verified).

## File structure

| File | Responsibility | Change |
|------|----------------|--------|
| `/Volumes/SSD/Dazzle/src/dazzle/http/runtime/rls_schema.py` | Generate RLS policy + role DDL from the IR | **Create** — `build_rls_policy_ddl(...)`, `build_rls_role_ddl(...)` |
| `/Volumes/SSD/Dazzle/src/dazzle/http/runtime/tenant_isolation.py` | Tenant context vars | **Modify** — add `_current_tenant_id` contextvar (get/set/reset) |
| `/Volumes/SSD/Dazzle/src/dazzle/http/runtime/pg_backend.py` | Connection lifecycle | **Modify** — `_set_tenant_context(conn, tenant_id)` + call it in `connection()` after `_set_search_path` |
| `/Volumes/SSD/Dazzle/src/dazzle/http/runtime/tenant_middleware.py` | Per-request tenant context | **Modify** — set `_current_tenant_id` from the authenticated user's tenant (see Task 2 integration note) |
| `/Volumes/SSD/Dazzle/src/dazzle/http/runtime/server.py` | Startup schema/DDL | **Modify** — `_apply_rls_policies(engine)` after `_apply_search_indexes`, gated on `shared_schema` |
| `/Volumes/SSD/Dazzle/tests/unit/test_rls_schema.py` | DDL generator unit tests | **Create** |
| `/Volumes/SSD/Dazzle/tests/unit/test_rls_runtime_context.py` | Context/apply unit tests | **Create** |
| `/Volumes/SSD/Dazzle/tests/integration/test_rls_enforcement_pg.py` | Adversarial real-PG tests (as `dazzle_app`) | **Create** |
| `/Volumes/SSD/Dazzle/docs/reference/` (tenancy/deploy doc) | Operator docs | **Modify/Create** — connect as `dazzle_app` for enforcement |
| `/Volumes/SSD/Dazzle/CHANGELOG.md` | Release notes | **Modify** |

---

## Task 1: RLS DDL generator (`rls_schema.py`)

**Files:** Create `/Volumes/SSD/Dazzle/src/dazzle/http/runtime/rls_schema.py`; test `/Volumes/SSD/Dazzle/tests/unit/test_rls_schema.py`.

- [ ] **Step 1: Write the failing tests**

```python
"""Unit tests for RLS policy + role DDL generation (RLS tenancy Phase B)."""
from __future__ import annotations

from dazzle.http.runtime.rls_schema import build_rls_policy_ddl, build_rls_role_ddl


def test_fence_is_restrictive_with_missing_ok_current_setting() -> None:
    ddl = "\n".join(build_rls_policy_ddl(["Project"], partition_key="tenant_id"))
    assert "ALTER TABLE \"Project\" ENABLE ROW LEVEL SECURITY" in ddl
    assert "ALTER TABLE \"Project\" FORCE ROW LEVEL SECURITY" in ddl
    # restrictive fence, USING + WITH CHECK, missing-ok current_setting, ::uuid
    assert "AS RESTRICTIVE" in ddl
    assert "current_setting('dazzle.tenant_id', true)::uuid" in ddl
    assert ddl.count("current_setting('dazzle.tenant_id', true)::uuid") >= 2  # USING + WITH CHECK


def test_permissive_baseline_present() -> None:
    ddl = "\n".join(build_rls_policy_ddl(["Project"], partition_key="tenant_id"))
    assert "AS PERMISSIVE" in ddl
    assert "USING (true)" in ddl  # baseline so a fenced table is not deny-all (companion §1.4)


def test_idempotent_drop_before_create() -> None:
    # CREATE POLICY has no IF NOT EXISTS; generator drops first so re-apply is safe.
    ddl = "\n".join(build_rls_policy_ddl(["Project"], partition_key="tenant_id"))
    assert 'DROP POLICY IF EXISTS tenant_fence ON "Project"' in ddl
    assert 'DROP POLICY IF EXISTS tenant_baseline ON "Project"' in ddl
    fence_drop = ddl.index('DROP POLICY IF EXISTS tenant_fence')
    fence_create = ddl.index("CREATE POLICY tenant_fence")
    assert fence_drop < fence_create


def test_custom_partition_key() -> None:
    ddl = "\n".join(build_rls_policy_ddl(["Project"], partition_key="org_id"))
    assert "org_id = current_setting('dazzle.org_id', true)::uuid" in ddl or \
           "\"org_id\" = current_setting('dazzle.org_id', true)::uuid" in ddl


def test_empty_when_no_entities() -> None:
    assert build_rls_policy_ddl([], partition_key="tenant_id") == []


def test_role_ddl_three_roles_idempotent_no_bypass_on_app() -> None:
    ddl = "\n".join(build_rls_role_ddl())
    assert "dazzle_owner" in ddl and "dazzle_app" in ddl and "dazzle_bypass" in ddl
    assert "BYPASSRLS" in ddl  # on dazzle_bypass
    # dazzle_app must NOT be granted BYPASSRLS
    app_line = next(l for l in ddl.splitlines() if "dazzle_app" in l and ("ROLE" in l or "LOGIN" in l))
    assert "BYPASSRLS" not in app_line
    # idempotent (guarded create — DO block / IF NOT EXISTS pattern)
    assert "pg_roles" in ddl or "IF NOT EXISTS" in ddl
```

- [ ] **Step 2: Run → fail** (`pytest tests/unit/test_rls_schema.py -v`) — module missing.

- [ ] **Step 3: Implement `rls_schema.py`**

Follow the companion §1.2-1.4 + §3 exactly. `build_rls_policy_ddl(tenant_scoped_names, *, partition_key)` returns a list of idempotent SQL strings; for each entity emit (in order): `ENABLE`, `FORCE`, `DROP POLICY IF EXISTS tenant_fence` + `CREATE POLICY tenant_fence ... AS RESTRICTIVE FOR ALL USING (...) WITH CHECK (...)`, `DROP POLICY IF EXISTS tenant_baseline` + `CREATE POLICY tenant_baseline ... AS PERMISSIVE FOR ALL USING (true) WITH CHECK (true)`. Quote identifiers with the existing `quote_identifier` (from `dazzle.http.runtime.query_builder`). The fence body is `{quote(partition_key)} = current_setting('dazzle.{partition_key}', true)::uuid` for both USING and WITH CHECK. `build_rls_role_ddl()` returns the §3 role DDL (dazzle_owner NOLOGIN; dazzle_app LOGIN, no BYPASSRLS; dazzle_bypass LOGIN BYPASSRLS; grants), each guarded idempotently (a `DO $$ ... IF NOT EXISTS (SELECT FROM pg_roles ...) $$` block — passwords are NOT embedded; use `CREATE ROLE ... LOGIN` and let deploy set passwords, or accept a password param for the test fixture). Note: role DDL is for tests + deploy docs, **not** auto-run on boot.

Pure string generation — no DB. No business logic, only the closed templated DDL (ADR tenet).

- [ ] **Step 4: Run → pass.** ruff + `mypy src/dazzle/http/runtime/rls_schema.py` clean.

- [ ] **Step 5: Commit** — `feat(rls): RLS policy + role DDL generator — tenant fence + baseline + FORCE (Phase B)`

---

## Task 2: Runtime tenant context + policy apply

**Files:** Modify `tenant_isolation.py`, `pg_backend.py`, `tenant_middleware.py`, `server.py`; test `/Volumes/SSD/Dazzle/tests/unit/test_rls_runtime_context.py`.

> **Integration note (load-bearing — read before coding).** The fence reads `current_setting('dazzle.tenant_id')`, which must be set per transaction to the **authenticated user's tenant id**. In `shared_schema` row mode the request's tenant = `current_user.tenant_id` (users are single-tenant). The value is resolvable via the existing `_resolve_user_attribute("tenant_id", auth_context)` (`/Volumes/SSD/Dazzle/src/dazzle/http/runtime/route_generator.py:1046`). The hook must set a `_current_tenant_id` contextvar **after auth resolves current_user and before DB queries run**, and `pg_backend.connection()` reads it (mirroring `_set_search_path` reading `_current_tenant_schema`). **Trace the auth→request→DB ordering first:** confirm where `auth_context`/current_user becomes available (a middleware vs a per-route dependency) and set the contextvar there. If auth is a per-route dependency (resolved after `TenantMiddleware`), set the contextvar in that dependency (or a thin wrapper), NOT in `TenantMiddleware` alone. **Fallback if ordering is awkward:** set it lazily — have `connection()` read the current `auth_context` contextvar (if one exists) and resolve `tenant_id` at lease time. Pick whichever cleanly guarantees the GUC is set within the same transaction as the query. Report which you used. Fail-closed: if no tenant id is resolvable, leave the GUC unset (the fence then denies — correct for unauthenticated/no-tenant requests against fenced tables).

- [ ] **Step 1: Write the failing tests** (`/Volumes/SSD/Dazzle/tests/unit/test_rls_runtime_context.py`)

```python
"""Unit tests for RLS runtime context + apply gating (Phase B)."""
from __future__ import annotations

from unittest.mock import MagicMock

from dazzle.http.runtime.tenant_isolation import (
    get_current_tenant_id, set_current_tenant_id, _current_tenant_id,
)


def test_tenant_id_contextvar_roundtrip() -> None:
    assert get_current_tenant_id() is None
    tok = set_current_tenant_id("11111111-1111-1111-1111-111111111111")
    try:
        assert get_current_tenant_id() == "11111111-1111-1111-1111-111111111111"
    finally:
        _current_tenant_id.reset(tok)
    assert get_current_tenant_id() is None


def test_set_tenant_context_emits_set_config_when_id_present() -> None:
    from dazzle.http.runtime.pg_backend import _set_tenant_context
    conn = MagicMock()
    _set_tenant_context(conn, "abc")
    # parameterised set_config(..., true); never SET LOCAL string-interpolation
    assert conn.execute.called
    args = conn.execute.call_args
    sql = str(args[0][0])
    assert "set_config" in sql and "dazzle.tenant_id" in sql
    # value passed as a bind parameter, not interpolated
    assert "abc" not in sql


def test_set_tenant_context_noop_when_id_none() -> None:
    from dazzle.http.runtime.pg_backend import _set_tenant_context
    conn = MagicMock()
    _set_tenant_context(conn, None)
    assert not conn.execute.called  # unset → fail-closed (fence denies), nothing set
```

(Plus a test that `server._apply_rls_policies` is a no-op when `tenancy` is None / not `shared_schema` — use a `MagicMock` engine + a stub appspec; assert `engine.begin` not entered when not shared_schema.)

- [ ] **Step 2: Run → fail.**

- [ ] **Step 3: Implement.**
  - `tenant_isolation.py`: add `_current_tenant_id: ContextVar[str | None]` + `get_current_tenant_id()` / `set_current_tenant_id()` (mirror the existing `_current_tenant_schema` trio).
  - `pg_backend.py`: add `_set_tenant_context(conn, tenant_id: str | None)` — when `tenant_id` is not None, `conn.execute(pgsql.SQL("SELECT set_config('dazzle.tenant_id', %s, true)"), [tenant_id])` (parameterised — NEVER `SET LOCAL`). In `connection()`, after `_set_search_path(...)` in BOTH the pooled and direct paths, call `_set_tenant_context(conn, get_current_tenant_id())`. (Same transaction as the subsequent query because the GUC is set on the leased connection before yield and the query runs before the block commits.)
  - Wire the contextvar set per the integration note (after auth resolves the tenant; report the hook chosen).
  - `server.py`: add `_apply_rls_policies(self, engine)` mirroring `_apply_search_indexes` — gated on `self._appspec.tenancy and tenancy.isolation.mode == SHARED_SCHEMA`; compute `scoped = scoped_entity_names(self._appspec.domain.entities, pk)`; run `build_rls_policy_ddl(sorted(scoped), partition_key=pk)` via `with engine.begin() as conn: conn.execute(text(stmt))`. Call it right after `self._apply_search_indexes(engine)` (both `_setup_database` and, if applicable, leave `_migrate_tenant_schemas` alone — shared_schema uses the public path). Do **not** auto-run `build_rls_role_ddl` (roles are cluster/deploy-level).

- [ ] **Step 4: Run → pass;** ruff + mypy clean on the four files.

- [ ] **Step 5: Boot smoke-check** — run an example with `shared_schema` (e.g. a copy of `fixtures/tenant_rls`) via `dazzle serve --local` against the local DB (superuser → RLS present but bypassed); confirm it boots, `_apply_rls_policies` runs (log line), and normal CRUD still works (dev superuser bypasses the fence; app-layer filters enforce). Report the boot log line. If boot breaks, STOP and report.

- [ ] **Step 6: Commit** — `feat(rls): per-transaction tenant context (set_config) + post-create_all policy apply (Phase B)`

---

## Task 3: Adversarial real-PostgreSQL enforcement tests

**Files:** Create `/Volumes/SSD/Dazzle/tests/integration/test_rls_enforcement_pg.py`. Reuse `fixtures/tenant_rls`.

This is the security proof. Marked `e2e`+`postgres`, skip-gated on `TEST_DATABASE_URL`/`DATABASE_URL`. Disposable scratch DB (mirror `/Volumes/SSD/Dazzle/tests/integration/test_tenant_rls_constraints_pg.py`). Setup per test/module: create scratch DB; create roles via `build_rls_role_ddl()` (with test passwords); `metadata.create_all` (as owner/superuser); apply `build_rls_policy_ddl(...)`; grant table privileges to `dazzle_app`/`dazzle_bypass`; **connect as `dazzle_app`** for the assertions; set context via `SELECT set_config('dazzle.tenant_id', <id>, false)` per test connection (session-scoped is fine in a dedicated test connection) or within an explicit transaction. Always drop the scratch DB + roles in `finally`.

- [ ] **Step 1: Write the tests** — one per companion §9 invariant relevant to Phase B (the fence; scope-policy ones are Phase C):
  1. **Cross-tenant read blocked.** As `dazzle_app`, context = tenant A; a row inserted under tenant B is invisible. (Positive control: tenant A's own row is visible.)
  2. **Cross-tenant write blocked.** Insert/update carrying tenant B's `tenant_id` under tenant A's context → rejected by the fence `WITH CHECK`.
  3. **Fail-closed on missing context.** No `dazzle.tenant_id` set → reads return zero rows; writes rejected.
  4. **Empty context is a hard error.** `set_config('dazzle.tenant_id','',true)` then a query → `invalid input syntax for type uuid` (proves middleware must never set empty).
  5. **Restrictive-only is deny-all.** Drop the `tenant_baseline` → a correctly-scoped `dazzle_app` session sees nothing (proves the baseline is load-bearing, companion §1.4).
  6. **Owner does not bypass under FORCE.** Connect as the table owner (non-superuser `dazzle_owner`), no context → filtered/denied. (Skip cleanly if the test DB owner is a superuser and a non-superuser owner can't be arranged; assert the FORCE attribute via `pg_tables.rowsecurity`/`relforcerowsecurity` as a fallback.)
  7. **Role attributes.** `dazzle_bypass` has `rolbypassrls=true`; `dazzle_app` has `rolbypassrls=false` (and as `dazzle_bypass`, tenant B's rows ARE visible — bypass works).

- [ ] **Step 2: Run against a scratch DB** (must PASS, not skip):
```bash
createdb dazzle_rls_enf && TEST_DATABASE_URL="postgresql://localhost/dazzle_rls_enf" python -m pytest tests/integration/test_rls_enforcement_pg.py -v -m postgres ; dropdb dazzle_rls_enf
```
If any assertion fails, the fence is wrong — STOP and report precisely; do NOT weaken. This run is the proof the security boundary holds.

- [ ] **Step 3: Commit** — `test(rls): adversarial real-PG enforcement of the tenant fence as dazzle_app (Phase B)`

---

## Task 4: Docs, changelog, ship

- [ ] **Step 1: Operator/deploy docs.** Add (to a tenancy/deploy reference doc under `/Volumes/SSD/Dazzle/docs/reference/`): RLS enforcement requires the app to connect as a **non-superuser, non-owner role (`dazzle_app`)** — superusers/owners bypass RLS (owners only when not under FORCE; FORCE closes the owner hole, but superusers always bypass). In local dev with a superuser `DATABASE_URL`, RLS is present but bypassed and app-layer scope filters enforce. Document `build_rls_role_ddl()` as the role-provisioning DDL for deploys. State that the GUC `dazzle.tenant_id` is set per transaction from the authenticated user's tenant; tenant-scoped DB access must be inside a transaction.
- [ ] **Step 2: CHANGELOG** (+ Agent Guidance): RLS tenant fence shipped (runtime-applied, restrictive fence + permissive baseline + FORCE); per-transaction `set_config` context, fail-closed; three-role model; **enforcement requires connecting as `dazzle_app`** (dev superuser = unenforced + app-layer filters); intra-tenant scope→RLS is Phase C; auth-table fencing + "auth resolves tenant first" is the auth-rework phase; the USER_MEMBERSHIP composite-FK gap (Phase A note) still stands.
- [ ] **Step 3: Full gate** — `ruff check src/ tests/ --fix && ruff format src/ tests/`; `mypy src/dazzle`; `pytest tests/ -m "not e2e"`. All green (watch example apps with `shared_schema` — they now get `_apply_rls_policies` at boot in tests that boot them; in unit tests no real DB so apply is gated/mocked).
- [ ] **Step 4: `/bump patch`**; update CHANGELOG header; commit `docs(changelog): RLS tenancy Phase B -- vX.Y.Z`.

---

## Final integration & ship

- [ ] **Adversarial final review** — dispatch a fresh `feature-dev:code-reviewer` over the whole Phase-B diff, **adversarial on the security boundary**: can any path reach a fenced table with the GUC unset-but-treated-as-permissive? Is `current_setting` always the **missing-ok** form (no hard-abort)? Is the value ALWAYS a bind param (never interpolated → no injection)? Could the permissive baseline be accidentally omitted (deny-all) or be too wide? Does the apply step ever run as a path that silently no-ops in prod? Is `set_config(...,true)` always in the same transaction as the query (the autocommit/transaction trap, companion §6.2)? Address high-confidence findings via `superpowers:receiving-code-review` (verify before implementing).
- [ ] **Confirm green + clean**; **FF-merge to main + push** (confirm each step's exit status, `feedback_commit_before_tag_push`); watch CI to green (the PostgreSQL Tests job runs the adversarial enforcement test).
- [ ] **Update memory** `project_rls_tenancy.md`: Phase B shipped; fence enforced (runtime-apply, dazzle_app role, fail-closed); Phase C (intra-tenant scope→RLS + predicate_compiler GUC retarget) next.

---

## Self-Review notes (planner)

- **Spec/companion coverage:** companion §1.2 (ENABLE/FORCE) §1.3 (restrictive fence, missing-ok) §1.4 (permissive baseline) → Task 1; §6 (set_config, fail-closed, empty-string hard error, transactions) → Task 2 + tests; §3 (roles) → Task 1 role DDL + Task 3 fixture; §9 fence-relevant assertions → Task 3.
- **Decisions honored:** runtime-apply (not migration); roles generated + docs + tests-as-`dazzle_app` + dev-unenforced.
- **Deliberate deferrals:** per-verb scope policies + predicate_compiler GUC retarget (Phase C); inspect/drift/RBAC-vs-pg_policies (Phase D); auth-table fencing + tenant-first login (auth-rework phase); excision/provisioning (Phase E).
- **Top risk:** the auth→`dazzle.tenant_id` wiring (Task 2 integration note) — depends on where current_user becomes available; the implementer traces it and reports the hook, with a lazy-at-lease-time fallback. The adversarial real-PG test (Task 3) is the backstop that proves the fence regardless of the app wiring.
- **Type consistency:** `build_rls_policy_ddl(names, *, partition_key) -> list[str]`; `build_rls_role_ddl() -> list[str]`; `get/set_current_tenant_id`; `_set_tenant_context(conn, tenant_id: str | None)`; `_apply_rls_policies(self, engine)`.
```
