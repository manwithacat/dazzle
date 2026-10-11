# RLS-Backed Row Tenancy — Phase C (Intra-Tenant Scope → RLS) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Checkbox (`- [ ]`) steps. **Security-critical — final review is adversarial.**

**Goal:** Push the **intra-tenant authorization** (the scope predicate algebra) down into PostgreSQL RLS, so within a tenant the database itself enforces per-persona row visibility — not just the app-layer scope filters. Replaces Phase B's permissive `tenant_baseline` with **per-verb scope policies** generated from `entity.access.scopes`, for entities that declare scope rules. The tenant fence (Phase B) still ANDs over everything.

**Architecture:** (1) A **policy-body mode** for the scope predicate compiler that emits a self-contained SQL string (no bind params) — `current_user.*` → `current_setting('dazzle.user_<attr>', true)::<type>`, literals → safely-inlined SQL literals, with casts derived from the column's IR field type. (2) Per-verb policy generation in `rls_schema.py` (SELECT for read+list union, INSERT/UPDATE/DELETE). (3) Runtime sets the `dazzle.user_<attr>` GUCs per request (extending Phase B's `set_config` wiring) for the app-wide set of referenced attrs. (4) Adversarial real-PG proof. App-layer scope filters stay as defense-in-depth.

**Tech stack:** Python 3.12, psycopg v3, PostgreSQL RLS, pytest.

---

## Context the implementer needs

- **Builds on Phase B (v0.81.22):** `rls_schema.py` (`build_rls_policy_ddl` emits ENABLE/FORCE + restrictive `tenant_fence` reading the fixed `TENANT_GUC="dazzle.tenant_id"` + permissive `tenant_baseline`); runtime `_set_tenant_context` (parameterised `set_config(...,true)`) in `pg_backend.connection()`, bound per-request in `auth/dependencies.py`; `_apply_rls_policies` post-create_all. Companion `/Volumes/SSD/Dazzle/docs/superpowers/specs/2026-06-04-rls-tenancy-generation-rules.md` §1.4 (per-verb permissive policies; verb coverage; **a fenced table needs ≥1 permissive policy per permitted verb or that verb is denied**), §1.5 (combination), §2.1 (read+list both → SELECT, OR'd; app keeps the read/list split), §6 (GUC context). Companion is authoritative for emitted DDL.
- **Predicate compiler** `/Volumes/SSD/Dazzle/src/dazzle/http/runtime/predicate_compiler.py`: `compile_predicate(predicate, entity_name, fk_graph, *, schema)` → `(sql, params)` with `%s` + markers (`UserAttrRef`/`CurrentUserRef`/`PayloadFieldRef`) + literals. 8 variants: Tautology, Contradiction, ColumnCheck, ColumnRefCheck, UserAttrCheck, PathCheck, ExistsCheck, BoolComposite. `_compile_value_ref` (L117) is the central value emit point; per-variant emit points noted in the compiler.
- **Per-verb scope rules:** `entity.access.scopes: list[ScopeRule]`, each `.operation` (PermissionKind create/read/update/delete/list) + `.predicate` (compiled `ScopePredicate`, set by the linker's `_compile_scope_predicates`). `read` + `list` both map to SQL `SELECT` and must be **OR-unioned** into one `scope_select` policy (companion §2.1).
- **No type info on ValueRef** (`core/ir/predicates.py`): casts must come from the column's `FieldSpec.type`. Reuse/mirror the FieldType→SQL-type mapping in `sa_schema.py` (`_field_type_to_sa`) to produce a pg type name for `current_setting(...)::<type>`. **Casting decision (resolved): cast the GUC to the column's IR type** (correct for equality, IN, and ordering) — not a text-compare (which breaks ordering). When the type can't be resolved, fail policy generation loudly (don't emit a wrong-typed policy).
- **No safe SQL-literal renderer exists** — add one (SQL-standard single-quote escaping for strings; `true/false`; numeric as-is; `NULL`). Scope-rule literals are author/IR-controlled, but render them safely regardless.
- **`current_user` attr set:** add a `collect_user_attr_refs(predicate) -> set[str]` walker (none exists; mirror `scope_create_eval._walk`). The app-wide union of referenced attrs (across all scope rules) is the set of `dazzle.user_<attr>` GUCs the runtime must set per request, resolved via the existing `route_generator._resolve_user_attribute(attr, auth_context)`.
- **Scope of "scoped entity":** an entity with ≥1 `access.scopes` rule. Tenant-flat entities (no scope rules) keep Phase B's `tenant_baseline`. Platform/`domain="platform"` entities remain excluded (Phase A/B). Only `shared_schema` mode.
- **Out of scope (later):** retiring the app-layer scope filters (keep them — defense-in-depth; RLS becomes authoritative in a later cleanup); prod migration emission + `dazzle inspect rls` + drift gate (Phase D); excision/provisioning (Phase E); auth-table fencing (auth-rework). The `permit:`/role gate (visibility/permissions) is NOT moved to RLS here — only `scope:` row-filtering.

## File structure

| File | Responsibility | Change |
|------|----------------|--------|
| `/Volumes/SSD/Dazzle/src/dazzle/http/runtime/predicate_compiler.py` | Predicate → SQL | **Modify** — add a policy-body mode (param-free; GUC + inlined literals + casts) threaded through the emit points; add `collect_user_attr_refs`; add a safe inline-literal renderer |
| `/Volumes/SSD/Dazzle/src/dazzle/http/runtime/rls_schema.py` | Policy DDL | **Modify** — `build_rls_scope_policy_ddl(...)`: per-verb scope policies; baseline dropped for scoped entities, kept for tenant-flat |
| `/Volumes/SSD/Dazzle/src/dazzle/http/runtime/server.py` | Apply hook | **Modify** — `_apply_rls_policies` now also emits scope policies for scoped entities |
| `/Volumes/SSD/Dazzle/src/dazzle/http/runtime/tenant_isolation.py` + `pg_backend.py` + `auth/dependencies.py` | Runtime user-attr GUCs | **Modify** — set `dazzle.user_<attr>` per request for the app-wide attr set |
| `/Volumes/SSD/Dazzle/tests/unit/test_predicate_policy_mode.py` | Policy-body compiler tests | **Create** |
| `/Volumes/SSD/Dazzle/tests/unit/test_rls_scope_policies.py` | Per-verb policy DDL tests | **Create** |
| `/Volumes/SSD/Dazzle/fixtures/tenant_rls/` | Add a scoped entity + scope rules | **Modify** |
| `/Volumes/SSD/Dazzle/tests/integration/test_rls_scope_enforcement_pg.py` | Adversarial intra-tenant proof | **Create** |
| `/Volumes/SSD/Dazzle/CHANGELOG.md` | Release notes | **Modify** |

---

## Task 1: Policy-body mode for the predicate compiler

**Files:** Modify `predicate_compiler.py`; test `tests/unit/test_predicate_policy_mode.py`.

Add a param-free "policy mode" that renders a `ScopePredicate` to a self-contained SQL string for an RLS policy body. Three pieces:

1. **Safe inline-literal renderer** `_inline_sql_literal(value) -> str`: `None`→`NULL`; `bool`→`true`/`false`; `str`→`'…'` with `'`→`''` escaping; `int`/`float`→`str(value)`.
2. **`collect_user_attr_refs(predicate) -> set[str]`**: recursive walk (mirror `scope_create_eval._walk`) collecting every `current_user.<attr>` name across ColumnCheck/UserAttrCheck/PathCheck value refs and ExistsCheck bindings.
3. **Policy-mode rendering**: a `compile_predicate_policy(predicate, entity_name, fk_graph, *, entity_types, schema=None) -> str` that returns a param-free WHERE-fragment. Thread an optional policy context through `compile_predicate`/`_compile_*` (or a sibling code path) so that at each value emit point:
   - `CurrentUserRef` → `current_setting('dazzle.user_id', true)::uuid`
   - `UserAttrRef(a)` → `current_setting('dazzle.user_{a}', true)::{pgtype}` where `{pgtype}` is the **column's** IR type (resolved from `entity_types` — a `{(entity, field): pgtype}` resolver, computed from EntitySpec FieldSpecs via a FieldType→pg-type map mirroring `sa_schema._field_type_to_sa`). For a path terminal, resolve against the terminal entity/field.
   - literal → `_inline_sql_literal(value)`
   - The column side, subquery structure (PathCheck/ExistsCheck `IN (SELECT …)`), and boolean composition are unchanged from the existing compiler — only the value tokens differ (no `%s`, no params).
   - `Tautology` → `"true"`; `Contradiction` → `"false"`.
   - If a needed cast type can't be resolved, raise a clear `ValueError` (don't emit an untyped/wrong policy).

**Implementation note:** prefer threading a `policy: bool` + a `types` resolver through the existing `_compile_*` functions over duplicating them (DRY — one algebra, two render targets), but keep the param-mode path byte-for-byte unchanged (Phase B + the route layer depend on it). A focused refactor of `_compile_value_ref` to accept an optional "render mode + expected pg-type" and return either `("%s",[marker])` or `(inlined_token, [])` is the cleanest seam.

- [ ] **Step 1: Write failing tests** (`tests/unit/test_predicate_policy_mode.py`) covering, with a small synthetic FKGraph + entity-type map: ColumnCheck vs literal → `"status" = 'archived'`; UserAttrCheck → `"school_id" = current_setting('dazzle.user_school_id', true)::uuid`; CurrentUserRef → `current_setting('dazzle.user_id', true)::uuid`; a depth-2 PathCheck → nested `IN (SELECT … WHERE … = current_setting(...)::uuid)`; BoolComposite AND/OR/NOT; null check → `IS NULL`; literal injection safety (`status = "a'b"` → `'a''b'`); `collect_user_attr_refs` returns the right set; an unresolvable-type cast raises ValueError. Assert the output contains **no `%s`** and policy compilation returns **no params**.
- [ ] **Step 2: Run → fail.**
- [ ] **Step 3: Implement** the renderer + collector + policy-mode threading.
- [ ] **Step 4: Run → pass.** Also run `pytest tests/unit/ -k "predicate_compiler or scope or predicate_policy" -q` to confirm the **param-mode path is unchanged** (Phase B + route tests still green).
- [ ] **Step 5:** ruff + `mypy src/dazzle/http/runtime/predicate_compiler.py` clean. Commit `feat(rls): policy-body mode for the scope predicate compiler (GUC + inlined literals + casts) (Phase C)`.

---

## Task 2: Per-verb scope policy DDL

**Files:** Modify `rls_schema.py`; test `tests/unit/test_rls_scope_policies.py`.

Add `build_rls_scope_policy_ddl(entity, fk_graph, entity_types, *, partition_key) -> list[str]` (or extend `build_rls_policy_ddl` to take the appspec/fk_graph). For an entity with `access.scopes`:
- Keep `ENABLE`/`FORCE` + the restrictive `tenant_fence` (Phase B).
- **Drop the permissive `tenant_baseline`** (`DROP POLICY IF EXISTS tenant_baseline`) — scoped entities are governed by per-verb policies instead.
- Emit, idempotently (DROP-then-CREATE), one permissive policy per **permitted verb**, body = `compile_predicate_policy(rule.predicate, …)`:
  - `scope_select` `FOR SELECT USING (<OR of read + list predicates>)` (companion §2.1 union).
  - `scope_insert` `FOR INSERT WITH CHECK (<create predicate>)`.
  - `scope_update` `FOR UPDATE USING (<update predicate>) WITH CHECK (<update predicate>)`.
  - `scope_delete` `FOR DELETE USING (<delete predicate>)`.
  - A verb with no scope rule for the entity → **emit no policy for that verb → that verb is denied** (companion §1.4). This is intentional; do not silently fall back to permissive.
- Combination: per verb `(OR of permissive scope policies) AND (restrictive tenant_fence)` — exactly the companion §1.5 semantics. (Multiple personas/rules for one verb OR together; if the algebra already merges them into one predicate per (verb), one policy suffices — check how `_compile_scope_predicates` stores multiple rules per verb and OR them if there are several.)
- Tenant-flat entities (no `access.scopes`) keep Phase B's `tenant_baseline` unchanged.

- [ ] **Step 1: Write failing tests** — for a scoped entity with read/list/create/update/delete scope rules: assert `tenant_baseline` is dropped, `scope_select/insert/update/delete` emitted with the right `FOR`/`USING`/`WITH CHECK` and GUC bodies; a verb missing a rule → no policy (denied); a tenant-flat entity keeps `tenant_baseline`; the fence is still present.
- [ ] **Step 2: Run → fail. Step 3: Implement. Step 4: Run → pass** + `pytest tests/unit/ -k "rls_schema or rls_scope" -q`.
- [ ] **Step 5:** ruff + mypy clean. Commit `feat(rls): per-verb intra-tenant scope policies; drop baseline for scoped entities (Phase C)`.

---

## Task 3: Runtime — set `dazzle.user_<attr>` GUCs per request

**Files:** Modify `tenant_isolation.py`, `pg_backend.py`, `auth/dependencies.py`, `server.py`; test `tests/unit/test_rls_user_gucs.py`.

The scope policies read `current_setting('dazzle.user_<attr>', true)`. The runtime must set those GUCs per transaction, for the **app-wide set of referenced attrs** (union of `collect_user_attr_refs` across all entities' scope rules — computed once from the appspec at startup, stored on the backend/server), resolved per request via `_resolve_user_attribute(attr, auth_context)`.

- Extend the per-request bind (Phase B set only `dazzle.tenant_id`) to also carry a `{f"user_{attr}": value}` map. `_resolve_user_attribute` returns string values (or `__RBAC_DENY__` → leave that GUC unset → fail-closed for predicates needing it).
- `_set_tenant_context` (or a sibling `_set_rls_context`) sets each GUC via parameterised `set_config('dazzle.user_<attr>', %s, true)` on the leased connection (same transaction). Keep `dazzle.tenant_id` behavior.
- Store the app-wide attr set on `ServerState`/the backend at link/startup (so the connection layer knows which GUCs to set without re-walking predicates per request); thread the resolved values via the contextvar (extend `_current_tenant_id` to a small context object `{tenant_id, user_attrs}` or add a parallel `_current_user_attrs` contextvar).
- Fail-closed: an attr that resolves to `__RBAC_DENY__`/None → GUC unset → its predicate denies.

- [ ] **Step 1: Write failing tests** — contextvar carries the user-attr map; `_set_rls_context` emits parameterised `set_config` for each attr (values as bind params, never interpolated); unset attr → no set_config for it; non-shared_schema → no-op.
- [ ] **Step 2-4: TDD;** run `pytest tests/unit/ -k "rls or pg_backend or tenant_isolation or auth_dep" -q`.
- [ ] **Step 5:** ruff + mypy clean. Commit `feat(rls): per-request dazzle.user_* GUCs for scope policies (Phase C)`.

---

## Task 4: Adversarial real-PostgreSQL intra-tenant proof

**Files:** extend `fixtures/tenant_rls`; create `tests/integration/test_rls_scope_enforcement_pg.py`.

Add to `fixtures/tenant_rls` a **scoped** entity within a tenant — e.g. give `Project` a department/owner field and a scope rule (`read/list: owner = current_user` or `department = current_user.department`), so there's intra-tenant row filtering to enforce. Then prove, as non-superuser `dazzle_app` (mirror `test_rls_enforcement_pg.py`'s role + scratch-DB harness):

- [ ] Within ONE tenant (tenant_id GUC fixed), set `dazzle.user_<attr>` for user X → user X sees only their in-scope rows; another user Y's rows in the **same tenant** are invisible (intra-tenant RLS enforced by the engine).
- [ ] Verb coverage: an entity/verb with no scope rule is denied; a permitted verb works for in-scope rows.
- [ ] read/list union: the SELECT policy reflects the OR of read+list predicates.
- [ ] Cross-tenant still blocked (tenant_fence ANDs over the scope policy — a scope-permitted row in another tenant is still invisible).
- [ ] Fail-closed: unset `dazzle.user_<attr>` → scope predicate denies.
- [ ] **Run against a scratch DB** (must pass, not skip); drop DB + roles in `finally`. If any assertion fails, STOP and report — do not weaken.
- [ ] Commit `test(rls): adversarial real-PG intra-tenant scope enforcement (Phase C)`.

---

## Task 5: Docs, changelog, ship

- [ ] CHANGELOG + Agent Guidance: intra-tenant scope is now DB-enforced via per-verb RLS policies generated from `scope:` rules; `current_user.*` → `dazzle.user_<attr>` GUCs set per request; read+list union; a verb without a scope rule is denied at the DB; app-layer scope filters retained as defense-in-depth; casting is to the column's IR type. Note still-open: prod apply + drift gate (Phase D), excision (Phase E).
- [ ] Full gate: `ruff check src/ tests/ --fix && ruff format src/ tests/`; `mypy src/dazzle`; `pytest tests/ -m "not e2e"`. Green.
- [ ] `/bump patch` (0.81.22 → 0.81.23); update CHANGELOG header; commit.

## Final integration & ship
- [ ] **Adversarial final review** over the whole Phase C diff — focus: (a) **literal-inlining injection safety** (every inlined literal goes through `_inline_sql_literal`; no raw value reaches the policy string); (b) **cast correctness** (GUC cast to the right column type; ordering predicates correct); (c) the param-mode compiler path is byte-unchanged (Phase B + routes unaffected); (d) **verb-coverage / no accidental permissive gap** (a scoped entity can't end up with a verb both un-denied and un-fenced); (e) the user-attr GUCs are bind-param set, fail-closed; (f) read/list union correct. Address via `superpowers:receiving-code-review`.
- [ ] Confirm green + clean; FF-merge to main + push (confirm exit statuses); watch CI green (PostgreSQL Tests runs the new scope-enforcement proof).
- [ ] Update memory `project_rls_tenancy.md`: Phase C shipped; intra-tenant scope DB-enforced; Phase D (static surfaces + prod apply + drift) next.

---

## Self-Review notes (planner)
- **Companion coverage:** §1.4 per-verb permissive + verb-coverage → Task 2; §2.1 read/list union + app keeps the split → Task 2 + retained app filters; §6 GUC context → Task 3; the closed grammar (only algebra constructs in policies) → Task 1 (policy mode emits only algebra forms + current_setting + inlined literals).
- **Resolved decision:** cast GUC to the column's IR type (not text-compare) — correct for ordering; fail loud if type unresolved.
- **Top risks for the adversarial review:** literal-inlining injection (mitigated by `_inline_sql_literal`); not regressing the param-mode path (Phase B fence + all route scope filters depend on it — keep it byte-identical); a verb accidentally left permissive-uncovered (deny is correct, silent-permissive is a leak).
- **Deliberate deferrals:** app-filter retirement, prod migration/drift (Phase D), excision (Phase E), auth-table fencing, `permit:` role gate (stays app-layer).
- **Type consistency:** `compile_predicate_policy(predicate, entity_name, fk_graph, *, entity_types, schema=None) -> str`; `collect_user_attr_refs(predicate) -> set[str]`; `_inline_sql_literal(value) -> str`; `build_rls_scope_policy_ddl(...) -> list[str]`.
```
