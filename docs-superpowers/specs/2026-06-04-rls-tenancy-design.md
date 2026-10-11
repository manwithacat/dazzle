# RLS-Backed Row Tenancy — Design Spec

**Date:** 2026-06-04
**Status:** Approved design — ready for implementation planning (large; phased)
**Author:** Brainstormed with @manwithacat
**Ratifies as:** ADR-0034 (at implementation capstone, mirroring how ADR-0033 capstoned the declarative-CSRF work)
**Supersedes:** §2 ("Keystone: operate on the existing model — no new isolation mode") of `docs/superpowers/specs/2026-06-04-tenant-lifecycle-design.md`. That spec's Slice 0 (the `is_test` column + reserved `qa-`/`qa_` namespace on `public.tenants`, shipped v0.81.20) is **preserved and becomes foundational** here. Its Slice 1 (FK-closure excision engine) is **replaced** by delete-by-`tenant_id`; its Slice 2 (QA-auth + containment) folds in with a DB-enforced containment invariant.
**Relates:** ADR-0008 (PostgreSQL-only runtime — RLS is always available), ADR-0010 (`scope:`/`permit:` separation), ADR-0017 (all schema changes via Alembic), the scope predicate algebra (`core/ir/predicates.py`, `back/runtime/predicate_compiler.py`), provable RBAC (`src/dazzle/rbac/`), the prior-correction substrate framing.

---

## 0. The load-bearing principle (the ADR's spine)

> **Business logic does not live in the database engine.** The only thing Dazzle generates into PostgreSQL beyond schema is **declarative, generated access-control predicates** (Row-Level Security policies) derived from the scope predicate algebra. No triggers, no stored procedures, no business rules in `CHECK` constraints, no computed "business" columns, no imperative logic of any kind.

RLS policies may grow *more expressive* (the closed predicate grammar can gain forms) but must stay **declarative access control** — "which principal may see/modify which rows" — never computation, state transition, or side effect. The DSL/IR remains the single source of truth; every policy is a *derived projection* of a scope rule an agent can read in the `.dsl`. An agent never has to read raw `CREATE POLICY` to understand authorization, exactly as it never reads generated Alembic SQL to understand the schema.

This principle is what keeps RLS adoption inside Dazzle's core goals — deterministic, statically-analysable, agent-first — instead of devolving into stored-procedure soup.

## 1. Motivation

Dazzle is already a **row-based** multi-tenant system (`is_tenant_root` + the scope predicate algebra), but isolation is enforced in the **application layer**: scope rules compile to SQL `WHERE` fragments that route handlers inject (`predicate_compiler.py`). That is precisely the historically-dangerous posture — *shared tables, isolation enforced by application code* — that PostgreSQL Row-Level Security (9.5, 2016) was created to fix. It is not hypothetical for Dazzle: the correlated-QA-blind-spot work and the per-route ctx state-bleed bug (#1293/#1294) were both "a filter didn't apply where it should have" failures.

The mature position (a decade past the "schema-per-tenant is the grown-up choice" instinct): **shared-schema + RLS as the canonical tenancy model**, with schema-per-tenant and database-per-tenant demoted to *premium isolation tiers* offered only where a customer's compliance posture demands physical separation. RLS removes the "trust every query" objection that historically justified schemas.

For Dazzle specifically the fit is unusually clean: the scope predicate algebra was *built* to be statically validated against the FK graph and compiled to SQL. **RLS is simply a second compilation target for that same algebra** — emit `CREATE POLICY` instead of (or in addition to) an inline `WHERE`. The investment already made is exactly what makes safe, deterministic RLS generation tractable. And making the database **fail closed** against a forgotten tenant filter is prior-correction enforced in the strongest possible layer: it structurally counters the LLM-authoring failure mode of omitting authz filters.

## 2. Taxonomy & keystone

Three isolation models, not two:

1. **Database-per-tenant** — strongest isolation, highest ops cost, lowest density. *Premium tier.*
2. **Schema-per-tenant** — one DB, one schema per tenant via `search_path`. *Premium/middle tier.* (Dazzle's current `isolation = "schema"` becomes this tier.)
3. **Shared-schema + row-based, RLS-enforced** — one set of tables, a `tenant_id` discriminator, isolation enforced by generated RLS policies. **This is the canonical default.**

**Keystone decision:** the canonical Dazzle tenancy model is **shared-schema, framework-owned uniform `tenant_id` discriminator, isolation enforced by generated RLS policies, intra-tenant authorization still via the FK-path scope algebra layered on top.** Schema-/database-per-tenant remain available as opt-in premium isolation tiers but are no longer the recommended baseline.

## 3. Tenant identity — framework-owned, uniform

The decisive property is that **the tenant discriminator and its isolation predicate are framework-owned and uniform**, not derived per-entity from the domain FK graph. Rationale (scored against agent cognition, determinism, rigorous use of the algebra):

- **One invariant, not N paths.** Every tenant-scoped row carries `tenant_id`; isolation is `tenant_id = current_setting('dazzle.tenant_id')::uuid` — identical on every table. An agent reasons about tenancy as a single rule, never tracing per-entity FK paths.
- **No ambiguity.** Tenant membership is an explicit, non-null column set by the framework on insert — eliminating the nullable-FK / multi-path / cycle / orphan edge cases that derived (FK-path) tenancy forces (the exact cases the superseded FK-closure excision engine had to special-case).
- **Algebra at the right altitude.** Tenant boundary = the algebra's simplest form (column equality to a session setting) applied *universally*; intra-tenant authz = the richer FK-path / EXISTS forms layered on top. Clean separation of the two concerns through one mechanism.
- **Prior-correction.** Tenancy is imposed by the framework, not wired by the (LLM) author across the domain FK graph — the precise place authors slip.
- **Unification.** `public.tenants` becomes the one tenant identity of record; Slice 0's `is_test`/`status`/`config`/reserved-namespace carry forward wholesale; the historical "two-world" gap (registry vs `is_tenant_root` entity) dissolves.

**Domain vocabulary is preserved.** "Framework-owned" means the framework owns the *mechanics* (uniform discriminator, RLS generation, lifecycle, registry) — not that the author loses the ability to name the tenant. The author still declares the tenant concept via the tenant archetype / `is_tenant_root` (`archetype_expander.py` already sets `is_tenant_root=True` for `ArchetypeKind.TENANT`); the framework *binds* that declaration to the canonical identity (`public.tenants`) and injects `tenant_id` everywhere. `is_tenant_root` thus shifts meaning: from a **scope-path anchor** to a **binding to the framework's tenant identity**.

## 3.1 Reconciliation with Dazzle's existing tenancy layer (discovered 2026-06-04)

A code sweep found Dazzle **already has a mature, end-to-end-tested shared-schema row-tenancy layer** — this spec builds on it rather than inventing parallel concepts:

- **`tenancy:` DSL block → `TenancySpec`** (`/Volumes/SSD/Dazzle/src/dazzle/core/ir/governance.py:127-160`): `mode` (`TenancyMode.SHARED_SCHEMA` is exactly our canonical mode), `partition_key` (default `"tenant_id"`), `entities_excluded`, `admin_personas`, `per_tenant_config`, `enforce_in_queries`, `cross_tenant_access`. Parsed by `dsl_parser_impl/governance.py`; used by `examples/invoice_ops` + `examples/support_tickets`; cross-tenant isolation verified in `tests/integration/test_invoice_ops_tenant_isolation.py`.
- **Reuse, don't reinvent:** the canonical switch is `tenancy: mode: shared_schema` (**not** a new `manifest isolation = "row"` string — that legacy `manifest.tenant.isolation` is a separate schema-isolation concern). The "global/shared-entity opt-out" is the **existing `tenancy.entities_excluded`** (and `admin_personas` for bypass) — drop the proposed new `global`/`shared` entity modifier unless ergonomics later justify sugar over `entities_excluded`.
- **The gaps Phase A/B actually close:** today the `partition_key` column is **author-declared** (`tenant_id: ref Tenant required` hand-written on every entity; validator + sentinel MT-01..07 only *check* it exists) and isolation is **app-layer only** (scope `WHERE` clauses). Phase A makes the discriminator **framework-injected and uniform** + adds the construction rules (composite FKs, `UNIQUE(tenant_id, id)`, tenant_id-leading index, tenant-scoped uniqueness). Phase B adds RLS enforcement. The existing `_inject_tenant_fk` (archetype_expander.py:509) is generalized: inject under `SHARED_SCHEMA`, name = `partition_key`, honor `entities_excluded`.

### Resolved: §7 Q2 and Q3
- **Q2 (global/shared surface):** resolved → reuse `tenancy.entities_excluded`.
- **Q3 (tenant identity / FK target):** resolved → **the author's declared tenant entity (`archetype: tenant` → `is_tenant_root`) is the canonical tenant**, a normal domain EntitySpec (clean entity→entity FK layering, matching the existing `ref Tenant` convention). **`public.tenants` is its 1:1 framework registry** (shared `id`), carrying lifecycle/premium-tier metadata (`is_test`/`status`/`config`/`slug` — Slice 0). Provisioning writes the tenant-entity row and its registry row with the **same UUID**, so `tenant_id` (= tenant-entity id = `public.tenants.id`) is one value and `is_test` resolves by `SELECT is_test FROM public.tenants WHERE id = tenant_id`. This honors "framework owns the mechanics, author names the tenant" and reuses the existing layer. (Companion §1.1's `REFERENCES public.tenants(id)` is read as "the canonical tenant identity," realized here as the 1:1 tenant-entity↔registry pair.)

## 4. Architecture

> **Authoritative companion:** `/Volumes/SSD/Dazzle/docs/superpowers/specs/2026-06-04-rls-tenancy-generation-rules.md` pins the exact DDL the generator emits and fixes five correctness defects latent in the templates below. **Where this section and the companion differ on a concrete artefact (policy form, role model, context primitive), the companion is authoritative.** Load-bearing corrections it makes, in brief: (1) **deny-all** — a fenced table needs ≥1 *permissive* policy per permitted verb (a `RESTRICTIVE` fence only subtracts), so tenant-flat entities get a `tenant_baseline USING(true)`; (2) **FK integrity bypasses RLS** → every intra-tenant FK is *composite* `(tenant_id, fk) REFERENCES parent(tenant_id, id)` with `UNIQUE(tenant_id, id)` on the parent; (3) `current_setting('dazzle.tenant_id', true)` (missing-ok arg required for fail-closed); (4) context set via parameterised `set_config(name, value, true)`, **not** `SET LOCAL` (which can't bind params → injection surface); (5) uniqueness is tenant-scoped (`UNIQUE(tenant_id, …)`). Plus a three-role model (`dazzle_owner`/`dazzle_app`/`dazzle_bypass`) and **greenfield-only** scope (no backfill/rebuilds). The subsections below are the design intent; defer to the companion for emitted SQL.

### 4.1 The discriminator
- A `tenant_id UUID NOT NULL` column (FK → `public.tenants.id`) injected by the framework on every **tenant-scoped** entity's table. Indexed, leading (companion §5).
- Set by the framework on insert from the request's tenant context — never author-supplied.
- A first-class **global/shared-entity** concept for *non-tenant reference data only* (lookup/reference tables): no `tenant_id`, no tenant policy, referenced by single-column FKs. Entities are tenant-scoped **by default**; `global`/`shared` is an explicit DSL opt-out (name TBD against the grammar drift test).

**Resolved decision — users are tenant-scoped (single-tenant-per-user), not global** (resolves companion §8). `users` carries `tenant_id` and takes the fence like every other entity; email uniqueness is per-tenant (`UNIQUE(tenant_id, email)` — the same person may be a distinct user in two tenants). **There are no cross-tenant data flows at the DB engine level**; if one tenant must interact with another, that is modelled as **events (HLESS)**, never shared rows or cross-tenant queries. Consequences to carry into the plan: (a) authentication must **resolve the tenant first** (host/subdomain → tenant context, building on `tenant_host` #1289) and then authenticate against that tenant's `users` — a rework of the framework auth store, which today keeps `users`/`sessions` global in `public`; (b) `dazzle_bypass` is needed only for **excision and ops/migrations**, not for any application-level cross-tenant analytics (there is none by design).

### 4.2 RLS generation (the closed grammar)
- Generated into Alembic migrations (ADR-0017): `ALTER TABLE x ENABLE ROW LEVEL SECURITY; ALTER TABLE x FORCE ROW LEVEL SECURITY; CREATE POLICY …`.
- **Tenant-boundary policy** (every tenant-scoped table): a *restrictive* policy `USING (tenant_id = current_setting('dazzle.tenant_id')::uuid) WITH CHECK (same)`. Restrictive = ANDed with everything else, so it can never be widened by another policy.
- **Intra-tenant scope policies**: *permissive* policies generated from the existing scope rules (per-action `read`/`list`/`create`/`update`), compiled by retargeting `predicate_compiler` to emit policy bodies (the same 6-form algebra: column-eq, FK-path subquery, EXISTS-junction, negation, boolean, null).
- **Combination semantics are explicit and deterministic:** one restrictive tenant policy AND the union (OR) of permissive per-action scope policies. No implicit/ambient policy.
- **Closed grammar invariant:** policy bodies may contain *only* what the predicate algebra emits. No arbitrary SQL, no function calls beyond `current_setting`, no volatility. This is the enforcement of §0.

### 4.3 Runtime context contract
*(Authoritative detail in companion §6; summary here.)*
- At transaction start the app issues parameterised `set_config('dazzle.tenant_id', $1, true)` plus one `set_config('dazzle.user_*', …, true)` per `current_user.*` attribute the scope rules reference (the referenced set is statically known from the IR). `set_config(..., true)` is the transaction-scoped, **bind-parameter-able** form — `SET LOCAL` cannot bind params and is an injection surface, so it is not used.
- **Fail closed:** unset context → `current_setting('dazzle.tenant_id', true)` is NULL → fence matches no rows (reads) and `WITH CHECK` rejects writes. **"No tenant" is *unset*, never empty-string** (`''::uuid` raises a hard error). Pinned by test.
- **Transactions mandatory:** `set_config(..., true)` is transaction-scoped, so every tenant-scoped access runs inside an explicit transaction (autocommit loses the context → safe-but-baffling empty result). Correct under PgBouncer transaction pooling; session-scoped `set_config(..., false)` is forbidden (leaks across pooled clients).
- **Role model (three roles):** runtime connects as `dazzle_app` (non-owner, no `BYPASSRLS`); tables use `FORCE ROW LEVEL SECURITY` (subjects the owner to policies too). DDL migrations run as `dazzle_owner`. Excision and cross-tenant analytics run as `dazzle_bypass` (`BYPASSRLS`) — so "I am outside the tenant ring" is never ambient. Provable-RBAC/role-guard asserts `dazzle_app` lacks `rolbypassrls`.
- **Middleware fails loud:** asserts `dazzle.tenant_id` is set before issuing tenant-scoped work (engine fail-closed + middleware fail-loud = defence in depth).

### 4.4 App-layer filters become optional defense-in-depth
Single source of truth = the predicate algebra. RLS is authoritative; the existing inline `WHERE` injection may remain as optional belt-and-suspenders but can be retired. Because both are compiled from the same predicates, they cannot diverge.

### 4.5 Static-analysis surfaces (strengthened)
- `dazzle inspect rls` — generated policies per table (new ext-point alongside the #1120 inspectors).
- An RLS **drift gate** (generated policies vs live `pg_policies`), mirroring the API-surface (#961) and signable-drift (#1340) gates.
- Provable RBAC (`src/dazzle/rbac/`) asserts against **live enforced policy**, not inferred app behavior — strictly stronger evidence for the compliance pipeline.

### 4.6 Lifecycle fold-in (#1338 + #1339)
- **Provisioning** (`provision_test_tenant`): insert a `public.tenants` row (`is_test=true`, reserved `qa-`/`qa_` slug — Slice 0), return its id as the discriminator; seed the first admin.
- **Excision** (#1338): `DELETE FROM <each tenant-scoped table> WHERE tenant_id = X` (uniform; reverse-FK order only to satisfy in-tenant FK constraints, or rely on `ON DELETE CASCADE` from `public.tenants`), then delete the `public.tenants` row. RLS-safe, no FK-closure traversal, no multi-path/nullable/cycle cases. `--dry-run` counts per table; safety guard reads `is_test` directly from the registry row (now resolvable — the unification the interim Slice-1 design deferred).
- **Containment invariant** (#1339, Slice 2): a QA-auth mint sets `dazzle.tenant_id` only to a tenant whose `public.tenants` row is `is_test=true` + reserved-namespaced; RLS then makes cross-tenant access structurally impossible — the invariant becomes **DB-enforced**, not app-checked.

## 5. Decomposition (phases — each its own implementation plan)

Dependency-ordered; each phase ships working, testable software and gets its own plan via writing-plans.

- **Phase A — Tenant identity & discriminator substrate.** Manifest tenancy mode (`isolation = "row"` canonical; `"schema"`/`"database"` premium tiers; `"none"` unchanged). `public.tenants` as canonical identity bound to the declared tenant entity. Inject `tenant_id` on tenant-scoped entities; the global/shared-entity concept + DSL opt-out. Alembic migration adding `tenant_id` + backfill strategy for existing apps. *(Builds directly on shipped Slice 0.)*
- **Phase B — RLS generation: tenant boundary.** Retarget `predicate_compiler` to emit policy bodies; generate the restrictive tenant-boundary policy + `ENABLE/FORCE RLS` into migrations; runtime `SET LOCAL` context + fail-closed; non-owner role + `FORCE RLS`. Adversarial cross-tenant-leak tests against real PG.
- **Phase C — RLS generation: intra-tenant scope.** Generate permissive per-action scope policies from the FK-path/EXISTS forms; define and test combination semantics; make app-layer filters optional.
- **Phase D — Static surfaces.** `dazzle inspect rls` + the RLS drift gate; provable-RBAC asserts against live policies.
- **Phase E — Lifecycle.** Provision (seed `tenant_id`), excise (`DELETE … WHERE tenant_id = X` + registry delete), QA-auth + DB-enforced containment (#1339), closing #1338 and #1339.

Phases A–B are the substrate; C–E build on it. Schema-/database-per-tenant premium tiers are explicitly **out of scope** for the first pass (document as a later concern).

## 6. Testing strategy
- **Adversarial, first-class** (this is a security boundary): an authenticated session for tenant A attempting to read/write tenant B's rows must be **blocked by the database** (RLS), not merely by app code — verified against real PostgreSQL with the app role. Missing/empty `dazzle.tenant_id` context denies all rows (fail-closed). Owner-bypass is gated by `FORCE RLS`. Tampered/forged context cannot widen access.
- **Differential**: for a representative app, the rows returned with RLS authoritative match the rows the legacy app-layer filter returned (no behavior regression) — proving RLS is a faithful retarget of the same algebra.
- **Determinism/drift**: generated policies are byte-stable for a fixed IR; the drift gate catches divergence from live `pg_policies`.
- **Closed-grammar guard**: a test asserts generated policy bodies contain only algebra-emitted constructs (no functions beyond `current_setting`, no subquery shapes outside the 6 forms) — structurally enforcing §0.

## 7. Open questions for the implementation plans
- **Backfill** of `tenant_id` on existing multi-tenant apps: derive from the existing FK path to the tenant root once, then enforce uniform thereafter. Migration shape + idempotence (recall the alembic dual-lineage lessons).
- **Global/shared-entity DSL surface**: keyword/modifier name and default (tenant-scoped by default, explicit `global`/`shared` opt-out) — confirm against the grammar drift test.
- **`is_tenant_root` reinterpretation**: exact binding semantics to `public.tenants`; whether the user's tenant entity *is* `public.tenants` (framework table surfaced as a domain entity) or maps 1:1 to it.
- **Combination semantics** for multiple per-action scope policies on one table (restrictive tenant AND permissive OR of scopes) — pin the precise `CREATE POLICY` set and its `pg_policies` projection.
- **Migration atomicity** of `ENABLE/FORCE RLS` + policy creation across a large existing schema; ordering vs the `tenant_id` backfill.
- **Premium tiers**: whether/when schema- and database-per-tenant are offered, and how the same algebra targets them (`search_path` / separate DB) — stated as a deliberate non-goal for the first pass.

---

## Appendix — what is preserved, replaced, superseded
- **Preserved:** Slice 0 (v0.81.20) — `is_test` + reserved `qa-`/`qa_` namespace on `public.tenants`; it is the foundation of the unified tenant identity here.
- **Replaced:** the original spec's Slice 1 FK-closure reverse-topo excision engine → delete-by-`tenant_id` (Phase E).
- **Superseded:** §2 of `2026-06-04-tenant-lifecycle-design.md` (the "no new isolation mode / row-level-via-scope" keystone) → this spec's framework-owned `tenant_id` + RLS keystone.
- **Folded in:** #1338 (excision) and #1339 (QA-auth + provisioning) deliver in Phase E under the new model.
