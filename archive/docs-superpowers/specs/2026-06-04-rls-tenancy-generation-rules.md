# RLS Tenancy — Generation Rules & Correctness Invariants (Greenfield)

**Date:** 2026-06-04
**Status:** Companion to `2026-06-04-rls-tenancy-design.md` — defines the precise artefacts the generator emits
**Author:** Brainstormed with @manwithacat; correctness pass applied
**Scope:** **Greenfield only.** No backfill, no constraint rebuilds, no FK-path disambiguation, no breaking-change migration of existing schemas. Every rule below is a *forward construction rule* the discriminator injector and RLS generator obey when emitting a new schema.
**Relates:** ADR-0008 (PostgreSQL-only runtime — RLS always available), ADR-0017 (schema changes via Alembic), the scope predicate algebra (`core/ir/predicates.py`, `back/runtime/predicate_compiler.py`), provable RBAC (`src/dazzle/rbac/`).

-----

## 0. Relationship to the design spec

The parent spec establishes the keystone (shared-schema, framework-owned uniform `tenant_id`, RLS-enforced, intra-tenant scope layered on top) and §0’s load-bearing principle (no business logic in the engine; policies are *derived projections* of the scope algebra). None of that changes.

This document fixes five correctness defects latent in the parent spec’s templates, records two semantic limits of RLS that the generator must respect, and pins the exact DDL the generator emits. Where the parent and this document differ on a concrete artefact (policy form, role model, context-setting primitive), **this document is authoritative.**

Because the target is greenfield, the correctness items below are not migration hazards — they are properties the *generated* schema must have from the first migration.

-----

## 1. The canonical per-table emission

For every **tenant-scoped** entity, the generator emits the following, in this order, into the Alembic migration.

### 1.1 Table shape

```sql
CREATE TABLE app.<entity> (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id   uuid NOT NULL REFERENCES public.tenants(id),
    -- ... domain columns ...

    -- Required so children can reference this row *within its tenant*
    -- (see §4 — composite FK target). id is already unique; this names
    -- the (tenant_id, id) pair as a referenceable key.
    UNIQUE (tenant_id, id)
);

-- Primary access-path index leads with tenant_id (§5).
CREATE INDEX <entity>_tenant_idx ON app.<entity> (tenant_id);
```

`tenant_id` is `NOT NULL`, set by the framework on insert from the request context, never author-supplied. The FK to `public.tenants` deliberately omits `ON DELETE CASCADE`: excision is explicit (§6 of the parent spec), so children are deleted in reverse-FK order before the `public.tenants` row. (Cascade remains available as an opt-in convenience for small tenants; it is not the default because it removes batching and `--dry-run` counts.)

### 1.2 Enable and force RLS

```sql
ALTER TABLE app.<entity> ENABLE ROW LEVEL SECURITY;
ALTER TABLE app.<entity> FORCE  ROW LEVEL SECURITY;
```

`FORCE` is mandatory: it subjects the table **owner** to the policies, closing the owner-bypass hole. The only roles that bypass are superusers and `BYPASSRLS` roles (§3).

### 1.3 The restrictive tenant fence (always emitted)

```sql
CREATE POLICY tenant_fence ON app.<entity>
    AS RESTRICTIVE
    FOR ALL
    USING      (tenant_id = NULLIF(current_setting('dazzle.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('dazzle.tenant_id', true), '')::uuid);
```

Notes that are load-bearing, not stylistic:

- **`AS RESTRICTIVE`** — restrictive policies are ANDed with everything else and can never be widened by a permissive policy. This is the tenant ring.
- **`current_setting('dazzle.tenant_id', true)`** — the `true` (missing-ok) argument is **required**. Without it, an *undefined* GUC raises `ERROR: unrecognized configuration parameter` (a hard transaction abort) rather than the “matches no rows” deny you want. With it: unset → text `NULL` → `NULL::uuid` → `NULL`, and `tenant_id = NULL` is `NULL` (not true), so the row is excluded. This is fail-closed for **reads and writes alike** (the `WITH CHECK` rejects inserts/updates when context is unset).
- **`NULLIF(.., '')`** — (#1400) the empty-string GUC state (a pooled connection whose placeholder reverted to `''`) would make a bare `''::uuid` **raise** `invalid input syntax for type uuid: ""` during policy evaluation — a 500, not a clean deny, and a potential per-tenant DoS if the GUC can be steered to `''`. Wrapping the read in `NULLIF(.., '')` collapses `''` to `NULL`, so that state denies identically to the unset state. Mirrors the host-GUC hardening for `dazzle.host_tenant_id` (#1394).
- **`WITH CHECK` on the fence** enforces that the framework-injected `tenant_id` equals the session’s tenant on every insert/update — a write cannot smuggle in another tenant’s id.

### 1.4 Permissive policies (at least one, always)

**Invariant: a table with RLS enabled must carry ≥1 permissive policy *per command verb it permits*.** This is the single most important correction. In Postgres the visible/operable row set is:

```
(OR of all permissive policies for the verb) AND (AND of all restrictive policies for the verb)
```

A restrictive policy **only subtracts**; it never grants. A table with the `tenant_fence` and **no permissive policy is deny-all** — invisible even to a correctly-scoped session. A verb (SELECT/INSERT/UPDATE/DELETE) with no permissive policy is denied for that verb specifically.

Two cases:

**(a) Tenant-flat entity** (no intra-tenant scoping). Emit a permissive baseline covering all verbs:

```sql
CREATE POLICY tenant_baseline ON app.<entity>
    AS PERMISSIVE
    FOR ALL
    USING (true)
    WITH CHECK (true);
```

Effective set = `(true) AND (tenant_id = ctx)` = exactly the tenant’s rows, for every verb.

**(b) Intra-tenant scoped entity.** Emit one permissive policy **per permitted verb**, compiled from the scope algebra. The baseline is **dropped only when every permitted verb is covered**; any verb left uncovered becomes denied — which must be a deliberate decision, not an accident of generation.

```sql
-- SELECT — covers both `read` and `list` (see §2.1); body is the
-- union of their predicates.
CREATE POLICY scope_select ON app.<entity>
    AS PERMISSIVE FOR SELECT
    USING (<algebra: select-scope predicate>);

-- INSERT — WITH CHECK only (USING is not consulted for INSERT).
CREATE POLICY scope_insert ON app.<entity>
    AS PERMISSIVE FOR INSERT
    WITH CHECK (<algebra: create-scope predicate>);

-- UPDATE — USING gates which rows may be targeted;
--          WITH CHECK gates the post-image.
CREATE POLICY scope_update ON app.<entity>
    AS PERMISSIVE FOR UPDATE
    USING      (<algebra: update-scope predicate>)
    WITH CHECK (<algebra: update-scope predicate>);

-- DELETE — USING only.
CREATE POLICY scope_delete ON app.<entity>
    AS PERMISSIVE FOR DELETE
    USING (<algebra: delete-scope predicate>);
```

**Generator rule:** for each verb the entity permits, emit ≥1 permissive policy; for each verb it forbids, emit nothing (denied) **and record the denial in the IR** so the closed-grammar guard can assert the omission was intentional rather than a generation gap.

### 1.5 Combination semantics (deterministic, by construction)

Per verb: `(OR of permissive scope policies) AND (RESTRICTIVE tenant_fence)`. No ambient or implicit policy is ever emitted. The closed-grammar guard (§7) asserts that every enabled table has exactly one `tenant_fence` and the verb-coverage invariant holds.

-----

## 2. Semantic limits of RLS the generator must respect

These are not bugs to fix; they are properties of the engine that bound what RLS can enforce. Write them down so they are not rediscovered through a leak or a spurious test failure.

### 2.1 `read` and `list` both compile to `SELECT`

Postgres policy commands are `SELECT / INSERT / UPDATE / DELETE / ALL`. There is no row-cardinality distinction, so Dazzle’s `read` (single-row) and `list` (collection) actions both map to `SELECT` and **OR together** — the more permissive of the two governs both.

Consequences:

1. If the algebra emits *different* predicates for `read` vs `list`, RLS enforces their **union**. The read/list distinction, where it exists, must remain in the **application layer**; RLS is authoritative for the tenant fence and for the SELECT union, not for the read/list split.
1. The “app-layer filter may be retired” claim (parent §4.4) holds for the tenant fence and for entities where read = list. For entities where read ≠ list, the app filter is retained for that distinction — defence in depth becomes load-bearing there.
1. The differential test (parent §6) will **correctly** show divergence on such entities. Pre-register those divergences as expected; do not treat them as regressions.

### 2.2 Foreign-key integrity bypasses RLS

Referential-integrity checks run as a system-internal operation that is **not** subject to RLS. A session scoped to tenant A can therefore insert a child whose `parent_id` points at a parent owned by tenant B: the FK check sees the parent (it bypasses the fence) and validates, producing a cross-tenant reference neither tenant can read.

**Mitigation (mandatory for intra-tenant FKs): composite foreign keys.** See §4. The uniform `tenant_id` makes this clean. Without it, “structurally impossible cross-tenant access” is true for reads but **false for referential links**.

-----

## 3. Role model

Three roles, clean by construction (no legacy to reconcile):

```sql
-- Owns schema + tables; runs DDL migrations. Subject to RLS for DML
-- under FORCE, but DDL is unaffected, so pure-DDL migrations are fine.
CREATE ROLE dazzle_owner NOLOGIN;

-- Runtime role. NOT owner; no BYPASSRLS. Subject to every policy.
-- Connects per request and runs all tenant-scoped DML.
CREATE ROLE dazzle_app LOGIN PASSWORD :'app_pw';

-- Explicitly outside the fence: excision, cross-tenant analytics, ops.
-- Named so that "I am outside the tenant ring" is never ambient.
CREATE ROLE dazzle_bypass LOGIN PASSWORD :'bypass_pw' BYPASSRLS;

GRANT USAGE ON SCHEMA app TO dazzle_app, dazzle_bypass;
GRANT SELECT, INSERT, UPDATE, DELETE
    ON ALL TABLES IN SCHEMA app TO dazzle_app, dazzle_bypass;
ALTER DEFAULT PRIVILEGES IN SCHEMA app
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO dazzle_app, dazzle_bypass;
```

Rules:

- **Runtime** uses `dazzle_app`, always with tenant context set (§4). It can never bypass the fence; a missing context denies.
- **DDL migrations** run as `dazzle_owner`. RLS does not govern DDL, so this is unaffected by `FORCE`.
- **Tenant-scoped seeds** (e.g. seeding a tenant’s first admin) are **DML** and therefore *are* governed by `FORCE` RLS. They must either set context first (`set_config` then insert as `dazzle_app`) or run as `dazzle_bypass`. A tenant-scoped insert run as `dazzle_owner` with no context will be rejected by the fence’s `WITH CHECK` — fail-closed, as intended.
- **Excision and cross-tenant analytics** use `dazzle_bypass`. Provable-RBAC and the drift gate assert `dazzle_app` does **not** hold `rolbypassrls`.

-----

## 4. Foreign keys and uniqueness (construction rules)

### 4.1 Composite FKs for all intra-tenant references

Every FK from one tenant-scoped entity to another is composite, carrying `tenant_id`:

```sql
CREATE TABLE app.line_item (
    id        uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id uuid NOT NULL REFERENCES public.tenants(id),
    order_id  uuid NOT NULL,
    -- ...
    UNIQUE (tenant_id, id),
    FOREIGN KEY (tenant_id, order_id)
        REFERENCES app.order (tenant_id, id)
);
```

Because `app.order` is keyed unique on `(tenant_id, id)` and `id` alone is its PK, the matching parent for a given `order_id` is unique, and its `tenant_id` must equal the child’s. This **forces child and parent into the same tenant** at the engine level, closing §2.2. The generator emits the composite FK automatically for any reference between two tenant-scoped entities; references to **global** entities (§4.3) stay single-column.

### 4.2 Uniqueness is tenant-scoped

Every uniqueness constraint on a tenant-scoped entity leads with `tenant_id`:

```sql
-- A natural key unique *within* a tenant:
UNIQUE (tenant_id, email)
```

A bare `UNIQUE (email)` would enforce **global** uniqueness — two tenants could not both have `alice@example.com`. Uniqueness is enforced by the index, not the policy, so RLS does not save you here. The generator must prepend `tenant_id` to every author-declared unique key on a tenant-scoped entity.

### 4.3 Global / shared entities

Reference and lookup tables, and the framework-global `users` table (see §8), carry **no** `tenant_id`, get **no** RLS, and are referenced by single-column FKs. Entities are tenant-scoped **by default**; `global` / `shared` is an explicit DSL opt-out (open question in parent §7 — name to confirm against the grammar drift test).

-----

## 5. Indexing

- The primary access-path index of every tenant-scoped table **leads with `tenant_id`**: `(tenant_id, <selective column>)`. A standalone index on `tenant_id` alone is low-selectivity and rarely the plan the optimiser wants.
- `current_setting` is `STABLE`, so the planner evaluates the tenant predicate once per execution and can drive an index scan from it. A composite index leading with `tenant_id` therefore makes the fence essentially free.
- Greenfield removes the rebuild cost: these indexes are correct from the first migration. The only standing obligation is that the injector keeps `tenant_id` leading.

-----

## 6. Runtime context contract

### 6.1 Set context with `set_config`, parameterised

```sql
-- $1 = tenant uuid as text; is_local = true → transaction-scoped.
SELECT set_config('dazzle.tenant_id', $1, true);
SELECT set_config('dazzle.user_id',   $2, true);
-- ... one per current_user attribute the scope rules reference
--     (the referenced set is statically known from the IR).
```

`SET LOCAL` **cannot take a bind parameter**, which forces string interpolation of the value into SQL text — an injection surface and an easy agent footgun. `set_config(name, value, true)` is the function form: it accepts bind parameters and has `SET LOCAL` (transaction-scoped) semantics via `is_local = true`. All Dazzle GUCs are text; cast in the policy body per attribute.

### 6.2 Transaction-scoped, therefore transactions are mandatory

`is_local = true` is transaction-scoped — correct under PgBouncer transaction pooling (a session-level `set_config(..., false)` would leak across pooled clients and must never be used). The hard consequence: **every tenant-scoped DB access must run inside an explicit transaction.** An autocommit single-statement path loses the context (its implicit one-statement transaction does not carry the prior `set_config`), and fail-closed then returns nothing — safe, but a baffling empty result. The session/middleware contract asserts a transaction is open before issuing tenant-scoped work.

### 6.3 Fail-closed engine, fail-loud middleware

- **Engine:** fail-closed. Unset context → `tenant_id = NULL` → no rows (reads) and rejected writes (the fence’s `WITH CHECK`). Defence in depth.
- **Middleware:** fail-loud. Assert `dazzle.tenant_id` is set before issuing tenant-scoped work; raise an explicit error at the app boundary rather than letting the query silently return nothing.
- **“No tenant” is always *unset*, never empty-string.** The middleware never sets an empty value; the absence of a tenant is the absence of the GUC. Since #1400 the fence reads `NULLIF(current_setting(..), '')::uuid`, so even if a pooled connection’s placeholder reverts to `''`, that state collapses to `NULL` and denies identically to the unset state — fail-closed, never a raising `''::uuid` (a 500 + per-tenant DoS vector). The middleware contract (never emit `''`) still holds as defence-in-depth; the engine no longer *relies* on it to avoid a hard error.

-----

## 7. Static surfaces & guards (parent §4.5, strengthened)

- **`dazzle inspect rls`** — the generated policy set per table.
- **RLS drift gate** — generated policies vs live `pg_policies`. Proves the policy *text* is present; it does **not** prove enforcement. The adversarial tests (§9) prove enforcement. Keep both; do not let the drift gate masquerade as the proof.
- **Closed-grammar guard** — asserts policy bodies contain only algebra-emitted constructs (no functions beyond `current_setting` / `set_config`, no subquery shapes outside the six algebra forms, no volatility). This is the enforcement of parent §0.
- **Structural invariants guard** — for every RLS-enabled table: exactly one `RESTRICTIVE tenant_fence`; ≥1 permissive policy per permitted verb; every permitted verb covered or its denial recorded in the IR.
- **Role guard** — `dazzle_app` does not hold `rolbypassrls`; `dazzle_bypass` does.

-----

## 8. Resolved decision: the `users` table

The parent spec makes `users` framework-global with no `tenant_id`. That commits the product to **users as cross-tenant identities**, with tenant membership carried on a separate **tenant-scoped, fenced** membership/junction table. This is the correct model **iff** a user may belong to more than one tenant (or exist before joining one).

**Decision to confirm before Phase A:** if the product model is “every user belongs to exactly one tenant,” `users` should instead be tenant-scoped (carry `tenant_id`, take the fence) like every other entity, and the global table is wrong. The consequence of leaving it global under a single-tenant-per-user model is that “which users are mine” is enforced on the membership table, not on `users` — and any code path querying `users` directly sits outside the fence.

State the chosen model explicitly in the IR; it is not a detail that can stay implicit.

-----

## 9. Test assertions (one per invariant)

Each invariant above is pinned by a test against **real PostgreSQL**, with `dazzle_app` as the connecting role.

1. **Cross-tenant read blocked by the engine.** Session scoped to tenant A reading tenant B’s rows returns nothing — verified with the app role, not app code.
1. **Cross-tenant write blocked.** Insert/update carrying tenant B’s `tenant_id` under tenant A’s context is rejected by the fence’s `WITH CHECK`.
1. **Fail-closed on missing context.** No `dazzle.tenant_id` set → reads return zero rows; writes rejected.
1. **Empty context denies, never errors (#1400).** `set_config('dazzle.tenant_id','',true)` then a read returns zero rows and a write is RLS-rejected — the `NULLIF(.., '')` wrapper collapses `''` to `NULL` so the empty-string state fails closed identically to the unset state, rather than raising `invalid input syntax for type uuid` (a 500 + per-tenant DoS vector). The middleware still must not produce `''`; the engine just no longer turns it into a hard error.
1. **Restrictive-only is deny-all.** A table with the fence and no permissive policy returns nothing for a correctly-scoped session — guards against accidentally shipping a fenced-but-ungranted table.
1. **Verb coverage.** For a scoped entity, each permitted verb has ≥1 permissive policy; a forbidden verb is denied and its denial is recorded in the IR.
1. **Owner does not bypass under FORCE.** `dazzle_owner` running tenant-scoped DML with no context is filtered/rejected.
1. **`dazzle_bypass` bypasses; `dazzle_app` does not.** Role-attribute assertions.
1. **Composite FK forbids cross-tenant reference.** Inserting a child in tenant A referencing a parent in tenant B is rejected by the composite FK.
1. **Tenant-scoped uniqueness.** Two tenants may hold the same natural key; one tenant may not duplicate it.
1. **Transaction requirement.** A tenant-scoped statement outside a transaction (autocommit) loses context and returns nothing — proving the transaction precondition.
1. **Differential.** Rows returned with RLS authoritative match the legacy app-layer filter, with read/list divergences (§2.1) pre-registered as expected.
1. **Determinism.** Generated policies are byte-stable for a fixed IR; the drift gate catches divergence from live `pg_policies`.
1. **Closed grammar.** Generated policy bodies contain only algebra-emitted constructs.

-----

## 10. What greenfield removes from the parent spec

- **Phase-A backfill** of `tenant_id` from existing FK paths — gone. Rows carry `tenant_id` from insert.
- **Constraint and index rebuilds** — gone. Unique keys are tenant-scoped and indexes lead with `tenant_id` from the first migration.
- **FK-path disambiguation** at migration time — gone. Tenancy is the uniform discriminator, never derived.
- **Phase B/C deny-all window** — neutralised by §1.4: the permissive baseline ships *with* the fence, so a fenced table is never transiently invisible.

The correctness items in §1–§6 are **not** migration concerns and remain in force: they govern the artefacts the generator emits, greenfield or not.
