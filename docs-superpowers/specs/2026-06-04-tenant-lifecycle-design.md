# Ephemeral Test-Tenant Lifecycle — Design Spec

> **⚠️ Partially superseded (2026-06-04).** §2's keystone (operate on the existing row-level model via `is_tenant_root` scope paths; no new isolation mode) is superseded by [`2026-06-04-rls-tenancy-design.md`](2026-06-04-rls-tenancy-design.md), which adopts a framework-owned uniform `tenant_id` discriminator enforced by generated RLS. **Slice 0 (shipped v0.81.20) is preserved and foundational.** Slice 1's FK-closure excision engine is replaced by delete-by-`tenant_id`; Slices 1–2 (#1338/#1339) now deliver in that spec's Phase E. This document remains the record of the lifecycle requirements and the Slice-0 work.

**Date:** 2026-06-04
**Status:** §2 superseded by the RLS-tenancy spec; Slice 0 shipped; Slices 1–2 re-homed to RLS-tenancy Phase E
**Author:** Brainstormed with @manwithacat
**Issues:** #1338 (first-class tenant excision), #1339 (signed/contained QA auth + ephemeral test-tenant provisioning). Both originate from AegisMark's QA harness (the one that surfaced framework bugs #1336/#1337).
**Relates:** ADR-0008 (PostgreSQL-only runtime), `is_tenant_root` (v0.10.3, `core/ir/domain.py:396`), `FKGraph.creation_order` (#1315, `core/ir/fk_graph.py:182`), existing tenant isolation (#957, #1209, #1289 `tenant_host`), ADR-0017 (all schema changes via Alembic).

---

## 1. Motivation

AegisMark drives a real prod/staging-safe QA harness against the framework (it found #1336/#1337). Two of its homegrown patterns deserve to graduate into the framework:

1. **Tenant excision** — delete a tenant and all its rows. AegisMark's `reap_tenant` heuristically walks `information_schema` with a retry loop to dodge FK-ordering errors. The framework already knows the exact deletion order (the IR's FK graph), so it can do this authoritatively.
2. **Signed, contained QA auth + ephemeral test-tenant provisioning** — a way to authenticate as a test persona and spin up a throwaway tenant on a prod-like deployment, with a hard guarantee the QA credential can never touch a real tenant.

Together they form a lifecycle: **provision → drive → excise**. They share a small substrate and can ship in either order (excision is independently useful for GDPR/offboarding; provisioning is usable with manual teardown).

## 2. Keystone decision: operate on the existing model (no new isolation mode)

Both RFCs assume **row-level / shared-schema** tenancy (many tenants' rows in one table, partitioned by a tenant FK). Dazzle has no such *declared* mode today — `manifest.TenantConfig.isolation` is only `"none"` | `"schema"` (`core/manifest.py:343`), and row-level multi-tenancy is a user-space scope-rule pattern keyed off `is_tenant_root`.

**Resolution (worked through the mechanics):** a tenant's row-set is exactly the **FK-reachable closure of the tenant-root row**, which the IR already *fully determines* (the FK graph + `is_tenant_root`). Reachability is **computed, not declared** — so neither a `tenant_scoped` entity flag nor a first-class `isolation="row"` mode is required to deliver either RFC.

- A tenant = an instance of the `is_tenant_root` entity (id `X`).
- For each entity, "rows belonging to tenant `X`" = rows whose FK path leads back to `X` (direct: `school_id = X`; transitive: `E → AssessmentEvent → School`, filtered by a subquery chain).
- Excision walks that closure in **reverse FK-topological order** (children before parents), deleting each entity's rows filtered to `X`.

**Non-goal (recorded deliberately):** a first-class `isolation = "row"` TenantConfig mode. It would be the cleanest long-term tenancy model, but it is a large tenancy-model feature in its own right (manifest + IR + scope + migrations + runtime) and is **not needed** to deliver excision or provisioning — both are operations over the FK-reachable closure of a tenant-root row, which the IR already determines. Revisit only if row-level tenancy needs to become a *declared, analyzable* property for reasons beyond these two features.

## 3. Architecture — three slices in dependency order

### Slice 0 — Shared substrate (small)

- **`is_test` boolean column on the tenant record** (`tenant/registry.py:TenantRecord` + its table), added via Alembic (ADR-0017). A *queryable* flag — not a `qa-` string-prefix heuristic — because both the containment check (§5) and any future reaper need to filter on it, and a prefix is forgeable/ambiguous. Default `false`.
- **Reserved `qa-` slug namespace** enforced in `tenant/config.py:validate_slug` — a real signup/tenant-create cannot claim a `qa-`-prefixed slug. The reserved prefix is the *human-visible* marker; `is_test` is the *load-bearing* one. (Belt-and-suspenders: reserved prefix AND `is_test` flag.)

This slice is a prerequisite for both #1338's safety guard and #1339's containment invariant.

### Slice 1 — #1338 Tenant excision (medium; independently useful)

**Engine** — `src/dazzle/tenant/excision.py`:

```
excise_tenant(root_entity, root_id, *, conn, dry_run=False) -> ExcisionResult
```

1. **Resolve the closure:** from the FK graph, compute the set of entities transitively FK-reachable to the `is_tenant_root` entity, and for each the FK path back to the root. A `FKGraph` helper produces the **reverse-topological deletion order** over that entity set (a thin wrapper / reverse of `creation_order`, which today is shaped for flow-step subsets and returns `None` on a cycle).
2. **Delete child-first:** for each entity in deletion order, `DELETE` the rows reaching `root_id` (direct child: `WHERE <tenant_fk> = root_id`; deeper: a subquery chain along the FK path). Because we go child-first, parents are safe to delete once their children are gone.
3. **Cascade framework auth artifacts** belonging to the tenant's users: `sessions`, `password_reset_tokens`, `user_preferences` (and the users themselves if user→tenant is modeled).
4. **One transaction**, rolled back entirely on any error.

**Loud-failure cases the FK graph surfaces** (vs AegisMark's silent retry) — each is an *error to report*, not retry:
- **Cycle** → no topo order → refuse with the cycle named.
- **Nullable tenant-FK** → rows belonging to no tenant; left untouched, **reported** in the result (not silently deleted).
- **Multiple / polymorphic paths** to the root → union the filters, **flag** the ambiguity in the result for review.
- **No FK path** (a global entity) → not tenant-scoped; correctly excluded.

**CLI** — `dazzle tenant excise <root_id>` (`cli/tenant.py`):
- `--dry-run` prints the per-entity row counts that *would* delete, in order, and exits.
- A `--confirm <slug>` guard requires the operator to retype the tenant slug.
- A **safety check**: refuse (or require an explicit `--force`) when the target is **not** `is_test` — production-tenant excision is possible (GDPR/offboarding) but must be deliberate.

**Testing:** one real-Postgres integration test (`tests/integration/test_tenant_excision_pg.py`, mirroring `test_scope_runtime_pg.py`) seeding two tenants with multi-level FK descendants, exciseing one, asserting (a) all of tenant A's rows gone across every level, (b) tenant B's rows **untouched** (the critical isolation assertion), (c) dry-run deletes nothing. Unit tests for the reverse-order helper + the cycle/nullable/multi-path reporting.

### Slice 2 — #1339 QA auth + ephemeral provisioning (large; security-critical)

**Route module** — a **new** `src/dazzle/http/runtime/qa_secure_routes.py`, physically separate from the dev-only `qa_routes.py` (keeps the "dev route untouched" promise visibly true and gives the secret-gated tier its own auditable boundary). **Self-disabling:** the router is **not mounted** when `QA_AUTH_SECRET` is unset → prod-off-by-default with no runtime branch to misconfigure. The `/qa/` prefix is already CSRF-exempt.

**Signer** — stdlib `hmac` (already imported in `auth/crypto.py`; no new dependency): sign/verify `persona:timestamp`, reject outside a ~60s replay window. (`itsdangerous` was considered and rejected for dependency hygiene.)

**Provisioning** — `provision_test_tenant(run_id) -> TenantRecord`:
- Emits a tenant whose slug is `qa-<run_id>` (reserved namespace) with `is_test=true`.
- Seeds the tenant's first admin user.
- Row-level (shared-schema) mode first — the case AegisMark actually exercises and the one excision (Slice 1) targets. Schema-isolation parity is an explicit later concern, not part of this slice.

**The load-bearing containment invariant** (§5).

**Testing:** adversarial security tests are first-class (§6).

This slice warrants its **own ADR** (the containment invariant is a security guarantee worth recording).

## 4. The lifecycle

```
provision_test_tenant(run_id)         # Slice 2 — qa-<run_id>, is_test=true, first admin seeded
   → QA-auth mint (signed, contained)  # Slice 2 — session into the test tenant only
   → drive the app (the QA harness)
   → excise_tenant(root, id)           # Slice 1 — reverse-topo delete, tenant B untouched
```

Excision is usable standalone (offboarding); provisioning is usable with manual/SQL teardown until excision lands.

## 5. The containment invariant (security crux of Slice 2)

> A QA-auth mint resolves the target user's tenant **from the database** and **refuses (403)** unless that tenant is `is_test=true` **and** in the reserved `qa-` namespace **and** matches the run's provisioned tenant.

Properties:
- The QA secret can **never** mint a session into a real tenant — even if an attacker knows a real user's email/persona, the DB lookup of that user's tenant fails the `is_test` check.
- Resolution is from the **DB record**, not from a request-supplied tenant id (no confused-deputy).
- `is_test` is a column, not a slug heuristic — unforgeable from the request.
- Defense in depth: reserved-namespace check **and** `is_test` flag **and** run-match — any one failing refuses.

## 6. Testing strategy

- **Slice 1:** real-PG integration (two-tenant isolation: A gone, B untouched, dry-run no-op) + unit tests for reverse-order/cycle/nullable/multi-path.
- **Slice 2 (adversarial, first-class):** mint refused for a real (non-`is_test`) tenant → 403; mint refused outside the replay window → 403; mint refused with a tampered signature → 403; router **absent** (404) when `QA_AUTH_SECRET` unset; provisioned tenant is `is_test=true` + `qa-`-namespaced; a QA session cannot read/write another tenant's rows (scope-enforced).
- **Slice 0:** `validate_slug` rejects a `qa-` slug from a normal create; the `is_test` column round-trips on the tenant record.

## 7. Slicing & sequencing for the implementation plan

1. **Slice 0 — substrate** (Alembic `is_test` column + reserved-`qa-` `validate_slug` guard + tests). Smallest; unblocks both.
2. **Slice 1 — excision** (engine + FK reverse-closure helper + CLI + PG integration test). Independently shippable; delivers #1338.
3. **Slice 2 — QA auth + provisioning** (qa_secure_routes + hmac signer + provision_test_tenant + containment invariant + adversarial tests + ADR). Delivers #1339; the largest, security-critical slice.

Each slice is its own plan → subagent-driven execution with a final holistic (adversarial, for the security slices) review, mirroring the declarative-CSRF rework.

## 8. Open questions for the implementation plan

- **Tenant-FK resolution per entity:** the FK path back to the root may be ambiguous (multiple paths) or absent; the engine derives it from `FKGraph`, but the planner must decide the exact per-entity tenant-FK-column resolution (first-hop vs full-path subquery) and how to represent a multi-path union.
- **User → tenant modeling:** how a `UserRecord` links to its tenant (direct column vs membership table) determines the auth-artifact cascade in Slice 1 and the DB tenant-lookup in Slice 2's containment check. Confirm against the current auth/tenant schema before Slice 1.
- **`creation_order` reuse vs new traversal:** `FKGraph.creation_order` returns `None` on cycle and is shaped for flow-step subsets; decide whether to generalize it or add a dedicated full-entity-set reverse-topo method.
- **Schema-isolation parity:** Slice 2 does row-level first; whether/when schema-isolation test-tenants are supported is deferred and should be stated as a non-goal in that slice's plan.
