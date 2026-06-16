# ADR-0037 — Declarative Membership Relation

**Status:** Accepted (2026-06-16) — design accepted; **not yet implemented** (tracked by #1393 Phase C). The acceptance decisions on the former open questions are recorded below.
**Issue:** #1393 (multi-tenant login fundamentals) — **Phase C** (declarative user→tenant membership relation). Phase A (`tenant_host:` implies membership-gated login) shipped v0.82.69; branded-403 shipped v0.82.78.
**Depends on:** the auth-identity model (Plan 1a–1d — framework-owned `Identity`/`Organization`/`Membership`/`Session`), the RLS row-tenancy model (`dazzle.tenant_id` fence), #1289 (`tenant_host`), ADR-0036 (tenant hierarchy data model — its sibling).
**Reserved sibling:** ADR-0034 (RLS-tenancy capstone) — distinct; do not conflate.

> **Vocabulary.** An **identity** is a global principal (a framework `users` row). A **tenant root** is the `Organization` whose id is the RLS `dazzle.tenant_id` discriminator. A **membership** is the fenced join `(identity, tenant_root, roles, status)` — a framework `memberships` row. A **tenant kind** and the **hierarchy** (parent/child/ancestor/descendant/root) are as defined in ADR-0036. The running illustration uses a two-level org tree (an *Org* containing *Teams*); ADR text is otherwise domain-neutral.

## Context

The framework already owns membership as a **first-class runtime model** (auth Plan 1a–1d), *not* an inference from scope filters:

- `MembershipRecord(identity_id, tenant_id, roles, status, …)` — the fenced join between a global identity and a tenant root; `tenant_id` is the value the RLS fence reads as `dazzle.tenant_id`, and `roles` are the personas the identity holds *in that tenant* (replacing the global `users.roles`).
- Backed by a `memberships` table + hash-chained `membership_events`, suspend/reactivate, and IDOR-checked `set_session_active_membership`. The tenant root itself is a framework `OrganizationRecord` (auth store, not the IR-entity pipeline).
- Phase A made declaring `tenant_host:` *imply* membership-gated login: a non-member on a host-pinned request gets a branded 403; a genuinely org-less identity routes to `/auth/no-orgs` instead of a silently-empty session.

**The Phase-C gap is narrow but real:** nothing in the DSL *declares* the user→tenant membership relation, so the framework **infers** the binding between the app's domain model and its membership model — specifically, the host-pin login path matches `membership.tenant_id == ResolvedTenant.id` (a "tenant-root-id match"). That inference is silent and unvalidated. When an app's `tenant_host` root kind and its RLS partition root don't line up, the symptom is a passes-auth-but-sees-nothing session — exactly the failure Phase A only partially addressed. There is no link-time check that the membership model is coherent with the declared tenancy.

ADR-0036 (its sibling) decided *what scope a reached host implies* (hierarchy-aware aggregate-vs-single) and left **open** the question of *which hosts a user may reach* — i.e. whether membership at a parent kind grants descendant-host reachability. This ADR answers that.

## Decision

### D1 — Membership binds to the framework model; the DSL declaration is a validated binding, **not** a new table

Phase C does **not** introduce an app-owned membership table. The framework `Identity`/`Organization`/`Membership`/`Session` model (Plan 1a–1d) remains the canonical runtime store — it already carries the RLS discriminator, hash-chained events, IDOR-checked activation, and the per-tenant role source. Phase C adds a **declaration that binds that model to the app's tenant-root kind and makes the previously-inferred tenant-root match explicit and link-validated.**

### D2 — Membership is declared at the **tenant-root kind** only; the root-kind row **is** the tenant root

Membership is declared on the entity that is simultaneously the **RLS partition root and the ADR-0036 hierarchy root**. That root-kind row's id **is** the `dazzle.tenant_id` discriminator (one logical tenant identity — not a framework-`Organization`-plus-app-entity pair). Declaring membership on a non-root kind is a link-time error: membership is a property of the isolation boundary, not of every host kind.

### D3 — Declarative surface: a `membership:` block on the tenant-root kind

```dsl
# Example — a two-level org tree (illustrative; not framework-specific).
entity Org "Org":              # RLS partition root + hierarchy root
  tenant_host:
    domain: app.example
    slug_field: slug
  membership:
    roles: role                # per-tenant role/persona source

entity Team "Team":
  org: ref Org required
  tenant_host:
    domain: app.example
    slug_field: slug
    parent: org                # ADR-0036 hierarchy edge
```

The principal is **always the framework `User`** (the v1 decision below), so the surface carries only `roles:` — the per-tenant role source (defaulting to the membership's `roles`). The block is what makes "this kind is the membership/RLS/hierarchy root, and its members are `User` identities with these roles" a **declared, checked** fact rather than an inferred one.

### D4 — Descendant-host reachability is **derived** from root membership (answers ADR-0036's open question)

A single membership at the tenant root grants reachability of **every descendant-kind host within that root**, via the ADR-0036 `parent:` edges. There are **no per-leaf / per-host membership rows**. Concretely:

- Membership is `(identity, root_tenant_id, roles)` — one row per identity per root.
- A host-pinned request resolves `ResolvedTenant`; reachability holds iff the resolved host's kind is the root **or a descendant of the root the identity is a member of** (the `parent:` chain stays inside the one RLS partition).
- A host outside the member's root → the Phase-A branded 403. No host tenant → deny.

This keeps the RLS root as the **single** membership boundary (no combinatorial membership rows as the tree grows) and composes exactly with ADR-0036's scope selection: ADR-0036 says *what a reached host scopes you to*; this ADR says *which hosts you may reach*.

### D5 — The three roots must align (the validated invariant Phase C exists to provide)

The linker enforces: **membership root == RLS `partition_key` root == ADR-0036 hierarchy root.** An app whose membership tenant root diverges from its RLS partition root (the silent empty-session footgun) is rejected at `dazzle validate`, not discovered at runtime. This is the "declared + validated" the inference lacked.

## Rejected alternatives

- **An app-owned junction entity as the membership relation** (`entity Membership: user: ref User; org: ref Org; …`). Re-implements Plan 1a's table and loses everything attached to it — hash-chained `membership_events`, IDOR-checked activation, the RLS-discriminator integration, suspend/reactivate, SCIM `external_id`. Bind to the framework model (D1), don't fork it. Rejected.
- **Per-descendant-kind (per-host) membership rows.** Membership rows at every host kind in the tree. Combinatorial as the hierarchy grows, and it duplicates what the `parent:` edges already express. Reachability is *derived* (D4). Rejected.
- **Allow the membership root to diverge from the RLS partition root.** This is precisely the inferred status quo and its silent-empty-session failure. The alignment is the invariant Phase C adds (D5). Rejected.
- **Keep inferring the tenant-root match (status quo).** Silent and unvalidated; a coherent membership model can only be asserted, not guessed (mirrors ADR-0036's and ADR-0027's anti-inference posture for security-relevant edges). Rejected.
- **A top-level `tenancy: membership:` block.** Membership is a property of one specific kind (the root); declaring it there, beside `tenant_host:` and the `parent:` edges, keeps the tenancy facts co-located on the entities that carry them. Rejected for locality (minor; revisit if multiple roots ever need it).

## Framing — model-driven failure-modes check (per CLAUDE.md)

1. **Which failure mode does this risk increasing?** *Authority leak / silent under-grant.* A mis-declared membership root could either widen reachability (leak) or collapse it (the empty-session under-grant). Mitigated by D5 (three-root alignment is link-checked) and D4 (reachability never leaves the RLS partition).
2. **Which detector catches it if we're wrong?** The RLS fence is the hard backstop — a derived-reachability bug cannot cross `dazzle.tenant_id` (the descendant chain is inside one partition by D4/ADR-0036-D4). Plus the new link-time alignment check (D5) and the RBAC/compliance surface (membership roles feed the matrix).
3. **Is that detector live in the normal workflow?** Yes — RLS on every request; `dazzle validate` runs the tenancy validator every build. (Same caveat as ADR-0036: the RBAC-verification harness leaves host-tenant cells as truthful WARNINGs pending host-probe simulation.)
4. **Can an engineer trace runtime behaviour to DSL/AppSpec?** Yes — the `membership:` block + `parent:` edges + resolved host `kind` fully determine reachability; it's inspectable in the IR, not inferred in side code (that opacity is the very thing this ADR removes).
5. **Does it preserve Postgres/auth/RLS semantics?** Yes — it binds to the existing framework membership model + RLS discriminator; no new isolation primitive, no new store.

## Consequences

- **New IR:** a `MembershipSpec` (roles source; principal is the framework `User`) on the tenant-root kind; new `core/validation/tenancy.py` rules (membership on exactly the root kind; three-root alignment per D5).
- **Runtime:** the host-pin activation path (`org_activation.resolve_activation`) reads the *declared* binding instead of the inferred tenant-root match; reachability of descendant hosts is computed from root membership + the `parent:` chain. The `memberships` table/store is unchanged.
- **Closes ADR-0036's open question:** membership at the root grants descendant reachability (D4); membership is **not** per-leaf.
- **Greenfield-only**, consistent with the RLS-tenancy posture.

## Out of scope / deferred (the rest of #1393)

- **Phase B — apex tenant discovery** (authed request on the canonical host → resolve memberships → 302 to a host / picker / no-orgs, + a guard so apex never serves scoped surfaces). A routing-flow decision, not a data-model one; its own design.
- **Phase D — email-domain → tenant routing** (the SSO on-ramp via verified domains / `connections`). Builds *on* the declarative membership relation but is a separate construct.
- **Multi-root apps** (an app with several independent tenant trees). The surface assumes one root per app; revisit if a concrete need appears.

## Decisions on the former open questions (resolved at acceptance)

- **Role inheritance across the hierarchy → DECIDED: uniform.** A membership's `roles` apply unchanged at every reachable descendant host within the root. A descendant host does **not** narrow or override the effective roles in v1. This composes with ADR-0036's decision that aggregate (ancestor-kind) host views are read-only across descendants — the role set is the same everywhere; what the host *exposes* narrows by kind, not the roles. Per-descendant role narrowing is a deferred follow-up if a concrete need appears.
- **Identity ≠ framework `User` → DECIDED: the v1 principal is always the framework `User`.** `identity:` is **dropped** from the surface (D3); the `membership:` block carries only `roles:`. A non-`User` identity entity is reserved for a future need (clean-breaks apply), not built now.
- **Invitation/provisioning surface → DECIDED: runtime-only in v1.** Memberships are created by the existing runtime paths (invite flow / `auto_provision_single_org`); the declarative relation does **not** add a declarative invite/provision surface in this ADR. A declarative invite surface is a separate, deferred follow-up.

---
*Accepted 2026-06-16 as the design for #1393 Phase C; sibling ADR-0036 accepted jointly. Not yet implemented — supersedes nothing; implementation tracked by #1393. Clean-breaks (ADR-0003) apply: the acceptance decisions above are revisable pre-v1 should implementation surface a contradiction. Phases B (apex discovery) and D (email-domain routing) remain out of scope.*
