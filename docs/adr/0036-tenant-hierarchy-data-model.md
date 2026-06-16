# ADR-0036 — Tenant Hierarchy Data Model

**Status:** Proposed
**Issue:** #1394 (`current_tenant` Layer 2 — hierarchy-aware aggregate-vs-single); sibling #1393 (multi-tenant login fundamentals, Phase C — declarative membership relation)
**Depends on:** ADR-0009 (predicate algebra), ADR-0008 (PostgreSQL-only), the RLS row-tenancy model (`project_rls_tenancy`, `dazzle.tenant_id` fence), #1289 (`tenant_host`), #1394 Layer 1 (`current_tenant` bound to the host `ResolvedTenant`, `dazzle.host_tenant_id` GUC, shipped v0.82.67)
**Reserved sibling:** ADR-0034 (RLS-tenancy capstone) — distinct decision; do not conflate.

## Context

Dazzle carries **three** distinct tenant notions that this ADR must keep straight:

1. **The schema registry** — `public.tenants` (`TenantRecord`: `slug`, `schema_name`, `is_test`, `status`). The schema-per-tenant *lifecycle* registry behind `dazzle tenant create`, QA-auth containment (ADR-0035), and RLS Phase E excision. **Operational/lifecycle**, not request-time row scoping.
2. **RLS row-tenancy** — a framework-owned `tenant_id` column + generated Postgres RLS, fenced per leased connection via the `dazzle.tenant_id` GUC. The **hard isolation boundary**: one tenant per transaction, fail-closed.
3. **The host tenant** — `tenant_host:` (#1289) resolves a host header to a *domain-entity row*, producing `ResolvedTenant(kind, id, slug, name)` where `kind` is the resolving **entity name** (e.g. `School`). #1394 Layer 1 bound the `current_tenant` scope/display variable to **this** model (the `dazzle.host_tenant_id` GUC), deliberately *not* the RLS `tenant_id` — the two can diverge and reusing one for the other binds the wrong tenant.

Layer 1 shipped id-equality (`field = current_tenant`) + kind-based display gating. The **open** headline feature (Layer 2) is *hierarchy-aware aggregate-vs-single*: in a parent/child tenant app (a Trust contains Schools), the **same** workspace should render an **aggregate** view at the parent host (`trust.aegismark.ai` → all member schools) and a **single** view at a child host (`school.aegismark.ai` → one school), selected by one variable rather than per-workspace conditionals:

- `school.trust = current_tenant` at the trust host (aggregate over the trust's schools)
- `school = current_tenant` at the school host (one school)

The FK-path predicate form already compiles (depth-N, ADR-0009), so authors can write the aggregate **manually** today. What's missing is the **declared hierarchy** that lets the framework *auto-select* aggregate-vs-single by the resolved host `kind`. `TenantRecord` has no parent/kind edge and `ResolvedTenant.kind` is just the resolving entity name with no parent relationship.

## Decision

### D1 — The hierarchy lives on the **domain entities**, not on `public.tenants`

Tenant *kinds* are already domain entities that declare `tenant_host:` (`entity School: tenant_host: …`, `entity Trust: tenant_host: …`), and `ResolvedTenant.kind` is already the entity name. The hierarchy is therefore a **declared parent edge between `tenant_host` entities, validated against the existing FK graph** — *not* a new parent column on the `public.tenants` registry. Reusing `public.tenants` would re-introduce exactly the crossroads Layer 1 resolved away from (host tenant vs schema/RLS tenant) and would duplicate, in a parallel framework table, a parent relationship the domain model already expresses as an FK (`School.trust → Trust`).

### D2 — Declarative surface (proposed): `parent:` on the child's `tenant_host:` block

```dsl
entity Trust "Trust":
  tenant_host:
    domain: aegismark.ai
    slug_field: slug

entity School "School":
  trust: ref Trust required
  tenant_host:
    domain: aegismark.ai
    slug_field: slug
    parent: trust            # parent kind = Trust, via the school.trust FK
```

`parent:` names a **required `ref` field on the same entity** whose target is another `tenant_host` entity. The framework derives the kind partial-order from these edges. Depth-N is allowed (Trust ▸ Region ▸ School) because the FK-path predicate already compiles depth-N; the chain is validated at link time (`TenantHostSpec.parent` → IR; new `tenancy` validator rules). A cycle, a non-`ref` `parent`, or a parent target that lacks `tenant_host:` is a link-time error.

### D3 — Aggregate-vs-single is compiled from the host `kind` vs the source entity's kind

`field = current_tenant` on a region/scope whose source entity is `S` compiles, at request time, against the resolved host `ResolvedTenant.kind = H`:

- **H == S** → direct equality `S = current_tenant` (single view — the child host).
- **H is a proper ancestor of S** in the declared hierarchy → the FK-path predicate `S.<declared-path-to-H> = current_tenant` (aggregate view — the parent host). The path is the chain of `parent:` FK edges from S up to H.
- **H is a descendant of S, or unrelated** → **deny** (fail-closed). A school host must never widen to trust-level data.
- **No host tenant** (apex / non-tenant / pooled empty-string GUC) → deny, exactly as Layer 1 (`NULLIF(current_setting('dazzle.host_tenant_id', true), '')`).

This is a *compile-time selection of an already-audited ADR-0009 predicate* keyed on the request's host kind — **no new predicate node, no new runtime authority path**. Display gating (`visible_when: current_tenant.kind == trust`) is unchanged from Layer 1 and stays bound to the same host-tenant source, so display hides exactly when scope denies.

### D4 — The hierarchy lives strictly **within one RLS isolation boundary** (the load-bearing reconciliation)

This is the crux and the reason the feature is ADR-material. RLS row-tenancy fences a leased connection to **one** `dazzle.tenant_id`. A parent-host *aggregate* spans many child rows. These compose **only** if the aggregate stays inside a single RLS partition. Therefore:

> **The RLS `tenant_id` partition boundary must sit at or above the root of the declared `current_tenant` hierarchy.** `current_tenant` host-kind scoping selects a *sub-tree view within* the RLS fence; it must never aggregate **across** RLS tenants.

Concretely, for the Trust/School example, the app has two valid shapes:

- **Trust is the RLS tenant** (isolation root). Schools are intra-trust rows (scoped by `school_id`/the `school.trust` FK). The trust host aggregates across its schools; a school host narrows to one school — **all within the trust's single RLS partition**. ✅ Layer 2 applies.
- **Each School is its own RLS tenant** (per-school isolation). Schools are mutually isolated **by design**, so cross-school aggregation is definitionally impossible — Layer 2 hierarchy aggregation **does not apply** (and a `parent:`-declared aggregate that would cross the per-school RLS boundary is a **link-time error**).

The linker validates this: the RLS `partition_key` entity must be the hierarchy root or an ancestor of it. An app that declares a `current_tenant` hierarchy whose aggregation would cross its own RLS `tenant_id` fence is rejected at `dazzle validate`, not discovered as an empty/500 result at runtime. The schema registry (`public.tenants`) is untouched and orthogonal throughout.

### D5 — Scope on tenant *attributes* (`x = current_tenant.slug`) stays deferred

Layer 1 deferred per-attribute GUCs; this ADR does not add them. `current_tenant` in scope predicates remains **id-equality** (plus the FK-path form D3). `.kind/.slug/.name` remain display-only. Adding attribute-equality is a separate, smaller follow-up.

## Rejected alternatives

- **Parent + kind columns on `public.tenants` (`TenantRecord`).** Binds the hierarchy to the schema/lifecycle registry, which Layer 1 deliberately decoupled from the host `ResolvedTenant`. Forces every host-hierarchy app onto schema-per-tenant, duplicates a relationship the domain FK already models, and resurrects the host-vs-RLS crossroads. Rejected.
- **Pure inference from the FK graph (no declaration).** "Both are `tenant_host` entities and there's an FK between them, so it's the hierarchy." Ambiguous when an entity has multiple FKs to tenant-host entities; silent and unauditable; a wrong inference is a cross-tenant data-exposure footgun. The hierarchy must be **declared and FK-validated**, not guessed. Rejected (consistent with ADR-0027's anti-inference posture for security-relevant edges).
- **Aggregate-at-parent bypasses RLS.** Letting a trust-host request read across school RLS partitions by lifting the fence. A cross-tenant read path that exists at all is the failure mode RLS exists to prevent. Rejected outright; D4 keeps aggregation inside one fence instead.
- **A bespoke `hierarchy:`/`tenancy: tree:` top-level block.** A second place to declare what `tenant_host:` + a domain FK already carry. Rejected for surface minimalism (the `parent:` field reuses both).
- **Multi-level rejected in v1.** Considered (mirror ADR-0026's flat-only posture) but rejected *against* — the FK-path predicate already compiles depth-N, so depth-N costs nothing extra and Trust ▸ Region ▸ School is a real shape. The IR still records single `parent:` edges, so a future revisit (DAG / multiple parents) stays open.

## Framing — model-driven failure-modes check (per CLAUDE.md)

1. **Which failure mode does this risk increasing?** *Semantic drift / authority leak* — a hierarchy mis-declaration could widen a child host to parent data. Mitigated by D3 fail-closed (descendant/unrelated → deny) and D4 (aggregation can't cross the RLS fence).
2. **Which detector catches it if we're wrong?** The RLS fence (Phase B, real-PG tested) is the backstop — even a mis-compiled aggregate cannot cross `dazzle.tenant_id`. Plus link-time validation (D2/D4) and the RBAC matrix/conformance surface.
3. **Is that detector live in the normal workflow?** Yes — RLS runs on every request against `dazzle_app`; `dazzle validate` runs the tenancy validator on every build. (Caveat: the RBAC-verification harness leaves `current_tenant` cells as truthful WARNINGs — full cell verification needs host-tenant probe simulation, a known #1394 follow-up.)
4. **Can an engineer trace runtime behaviour to DSL/AppSpec?** Yes — `parent:` edges + the resolved host `kind` fully determine which ADR-0009 predicate compiles; it is inspectable in the IR, not hidden in side code.
5. **Does it preserve Postgres/auth/RLS semantics?** Yes — it *composes within* RLS (D4) rather than around it, and reuses the existing FK-path predicate + the `dazzle.host_tenant_id` GUC; no new isolation primitive.

## Consequences

- **New IR:** `TenantHostSpec.parent: str | None` (the FK field name) + a linker-derived kind partial-order; new `core/validation/tenancy.py` rules (parent is a `ref` to a `tenant_host` entity; no cycles; RLS-root-dominance per D4).
- **Compiler:** `predicate_compiler` selects direct-vs-FK-path for `current_tenant` by comparing the request host `kind` to the source entity's kind via the declared hierarchy; deny when not an ancestor.
- **Sibling coupling (#1393 Phase C):** the declarative **membership** relation ("which hosts a user may enter") and this hierarchy ("what scope the entered host implies") are complementary; Phase C should be designed jointly so membership at a parent kind implies reachability of its descendants per the same edges. This ADR does **not** decide the membership-relation surface — that is #1393's ADR.
- **Greenfield-only**, consistent with the RLS-tenancy posture: no migration path for re-parenting an existing tenant tree in v1.

## Open questions (resolve before Accepted)

- **Membership × hierarchy:** does an active membership at a parent kind auto-grant child-host reachability, or must membership be per-leaf? (Couple with #1393 Phase C.)
- **Cross-kind row actions at an aggregate host:** at the trust host the user sees many schools' rows — are write actions allowed there, and under which row's scope? (Likely: aggregate views are read-mostly; writes require descending to the single host. Needs a decision.)
- **`order:` interaction:** `tenant_host` already has an `order:` for multi-entity resolution; confirm the hierarchy chain and resolution order can't disagree.

---
*Draft raised from the #1394/#1393 escalation. Not yet implemented; supersedes nothing. Promote to Accepted after the membership-relation (#1393 Phase C) brainstorm resolves the open questions.*
