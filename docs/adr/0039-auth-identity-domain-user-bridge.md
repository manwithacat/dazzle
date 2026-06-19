# ADR-0039 — Auth-identity ↔ domain-`User` bridge via a declared binding

**Status:** Accepted (2026-06-19) — **fully implemented** (#778/#1398), shipped v0.83.15–v0.83.18
across four slices: D2 IR+parser (`auth_identity:` block, v0.83.15) · D6/A1 validate-completeness
(v0.83.16) · D3a/D4 shared provisioning mirror + production `AuthStore.create_user` hook (v0.83.17) ·
D3b `ref User` link-resolution + `examples/simple_task` dogfood (v0.83.18). The two former open
questions were ratified on 2026-06-19:
**A1 = a1** (validate-time resolution of every required column; never a swallowed runtime failure)
and **A2 = opt-in** (declared `auth_identity:` enables the bridge). Both are folded into the
decisions below.

## Context

An authenticated principal lives in **two places** that the framework keeps only loosely coupled:

1. The **auth store** `users` table — the identity that owns sessions, memberships, the RLS
   fence, and audit. `session.user_id == auth user.id`, and that id is consumed *everywhere* as
   the auth id (`get_user_by_id`, `delete_user_sessions`, `set_session_active_membership AND
   user_id = %s`, membership resolution, RLS tenant binding, audit user-id).
2. The DSL-defined **`User` domain entity** — what app FKs point at (`created_by: ref User`,
   `tipper: ref User`).

Today these are bridged by two implicit conventions:

- **`ref User` FK auto-injection (#774)** injects `current_user` — i.e. `session.user_id`, the
  **auth id** — directly into the FK. This *silently assumes* `domain User.id == auth user.id`
  **and** that the domain row exists. When it doesn't (a user created via the real
  `/auth/register` flow is never mirrored into the `User` entity), every `ref User` create
  fails with a FK violation. This is #778.
- The auth store separately reads domain `User` **attributes** by **email**
  (`_load_domain_user_attributes`) — read-only, no id assumption — so scope rules like
  `current_user.school` resolve.

A partial fix exists for the **test path only**: `_mirror_auth_user_to_domain`
(`test_routes.py`, schema-derived since #1398) upserts a domain `User` row at the auth id on
`/__test__/authenticate`. It is *not* invoked by the production auth flow, so the real-flow gap
(#778) remains. Downstream consumers (e.g. the "pennydreadful" lens) paper over it with a manual
`_seed_domain_user(...)` upsert commented *"works around the broken Dazzle #778 mirror."*

The framework **already has** the general, auth-safe bridge mechanism for *other* persona-backed
entities: **`backed_by` + `link_via`** (cycle 249, EX-049). A `persona tester: backed_by: Tester`
binding makes the create handler resolve the backing row by `link_via` at request time and inject
the **domain row's** id — no id-equality assumption, no session change. `User` is explicitly
special-cased *out* of this path (`target != "User"`); it falls back to the auth-id injection that
assumes id-equality. **This ADR brings `User` into the same declared-binding model.**

## Decision

### D1 — Never repoint `session.user_id`. Bridge at the injection/provisioning layers, not the session layer.

`session.user_id` is the auth-store identity and is load-bearing for sessions, membership, the RLS
fence, and audit. Conflating it with the domain `User` id (so a `ref User` FK resolves) would
break every auth-store lookup keyed on it. **The auth↔domain bridge is established by (a) which id
lands in a `ref User` FK, and (b) ensuring the domain row exists — never by changing what the
session stores.** This is the invariant the whole ADR protects.

### D2 — The bridge is a **declared, validated binding** on the `User` entity, not a silent default.

The `User` entity declares that it is the domain projection of the auth principal, with the link
field (provisional surface; exact keyword finalised at implementation):

```dsl
entity User "User":
  id: uuid pk
  email: str required
  username: str(40) required
  display_name: str(80) required
  # Declares: this entity IS the authenticated principal's domain row,
  # joined to the auth identity by `email`. Field maps/defaults let the
  # registration mirror satisfy NOT-NULL columns the auth flow can't supply.
  auth_identity:
    link_via: email
    map: { username: email_localpart, display_name: email_localpart }
```

The declaration is the contract. It is FK-graph/link validated at `dazzle validate` time
(`link_via` must be a column; mapped/defaulted columns must exist), the same posture ADR-0036/0037
take for security-relevant edges: **assert the bridge, don't infer it.**

### D3 — When declared, the framework does two things, both auth-safe:

- **(a) Provision (mirror) on real registration.** On `/auth/register` (and any production
  auth-user creation), upsert a domain `User` row using the declared `link_via` + `map`/defaults —
  the same schema-derived logic as the #1398 test-route mirror, promoted out of `test_routes.py`
  into a shared helper both paths call. Idempotent (`ON CONFLICT … DO UPDATE`).
- **(b) Inject the domain id, resolved by `link_via`.** Stop special-casing `User` in the create
  handler; resolve the domain `User` row by the link (email) at request time and inject **its** id
  into `ref User` FKs — exactly the cycle-249 path used for `Tester`/`Agent`. Removes the
  `domain User.id == auth id` assumption entirely.

With (a) keeping the row present and (b) removing the id-equality assumption, `ref User` creates
resolve for any principal, through any auth path, with zero changes to session/membership/RLS/audit.

### D4 — Mirror at the **shared helper**, called from both auth paths (no duplication).

`_mirror_auth_user_to_domain` is generalised into a path-neutral
`mirror_auth_user_to_domain(deps, identity, binding)` and called from **both** `/__test__/authenticate`
(unchanged behaviour) and the production registration path. The test-route mirror stops being a
divergent copy of the production rule (which is how #1398 and #778 drifted apart).

### D5 — Undeclared `User` behaves exactly as today (backward compatible).

No `auth_identity:` declaration ⇒ no mirror, and `ref User` injection keeps using `current_user`
(the auth id) as it does now. Apps that own their `User` table / signup flow, or that don't define a
`User` entity, are untouched. This answers "apps that don't want auto-mirrored domain rows": opt
in by declaring; opt out by omitting.

### D6 — (A1, ratified) Hard-schema & tenancy: fail at **validate**, never swallow at runtime.

When the registration mirror can't safely complete a required column — an `enum`/`ref`/`uuid` or any
required-no-default scalar with no `map`/default, **or** a `tenant_id` on an RLS-fenced `User` (the
principal registers *before* having an org/membership) — the framework does **not** best-effort and
swallow (the #1398/#778 failure mode). Instead:

- The `auth_identity:` declaration MUST resolve **every** required-no-default column on `User` (via
  `map` or `default`), checked at **`dazzle validate`** against the entity schema. An unresolvable
  required column is a **validate-time error**, not a runtime exception. (This converts the silent
  runtime FK/insert failure into a static, traceable error — satisfies the model-driven
  failure-mode posture in the Framing section.)
- For an **RLS-tenanted `User`**, the declaration MUST state tenant placement — i.e. `User` is a
  global/unfenced principal table (the common case: the principal exists above any one tenant), or
  the binding is rejected at validate with a clear message directing the author to make `User`
  unfenced or own provisioning themselves. v1 does **not** create a fenced `User` row at
  registration-before-membership (no tenant to place it in); that path is a validate error, not a
  silent half-write. *(Deferred alternative — provision at first org-membership — recorded in Out
  of scope; not v1.)*

### D7 — (A2, ratified) The bridge is **opt-in** (declared), never always-on.

Only an `auth_identity:` declaration enables provisioning + link_via injection (D2/D3). A `User`
entity with no declaration behaves exactly as today (D5). No always-on "mirror whenever a `User`
entity exists" — declared contracts over inferred behaviour, per ADR-0027/0036/0037, and the
declaration is also where D6's required-column maps live.

## Rejected alternatives

- **Repoint `session.user_id` to the domain `User` id (session-time resolution).** The auth-model
  breaker: `session.user_id` is consumed as the auth id across sessions/membership/RLS/audit;
  repointing it makes those lookups miss (the domain id isn't in `users`) and would need a second
  id field plus an audit of every consumer. Violates D1. **Rejected.**
- **Always inject the auth id and require id-equality (status quo + a global registration mirror,
  no declaration).** Keeps the brittle `domain User.id == auth id` assumption and the
  swallow-on-failure mirror; surprises apps that own `User`. Inferred, not asserted. **Rejected**
  in favour of the declared binding (D2) + link_via injection (D3b).
- **A new bespoke `principal:`/`identity_user:` construct unrelated to `backed_by`.** Duplicates the
  cycle-249 `backed_by`/`link_via` machinery that already does exactly this for other entities.
  Reuse the proven path; don't fork it. **Rejected.**
- **Leave it test-only + document the contract as "app owns the upsert."** This is the current
  downstream workaround (`_seed_domain_user`). Pushes a framework-shaped concern (the principal's
  domain projection) into every consumer's side code — the failure mode this ADR exists to remove.
  **Rejected** as the *only* answer; the declared bridge subsumes it.

## Framing — model-driven failure-modes check (per CLAUDE.md)

1. **Which failure mode does this risk increasing?** *Hidden side-channel semantics* — an auth↔domain
   coupling that lives in runtime code rather than the AppSpec. We *reduce* it: the coupling becomes a
   declared, validated binding instead of two implicit conventions (id-equality + email-attr-merge).
2. **Which detector catches it if we're wrong?** `dazzle validate` (link/required-column validation
   of the binding) + the FK graph; at runtime, the existing FK constraint still fails closed.
3. **Live or merely documented?** Live — validation runs every `validate`/CI; the A1 disposition
   makes the previously-*swallowed* runtime failure a *static* error.
4. **Can an engineer trace runtime behaviour back to the AppSpec?** Yes — the `auth_identity:` block
   is the single declared source of "this entity is the principal; mirror + inject via email."
5. **Does it preserve auth/Postgres semantics, or push them into side code?** Preserves: D1 keeps the
   auth-store identity untouched; the bridge is a declared projection. It *removes* side code (the
   downstream `_seed_domain_user` workaround).

## Consequences

- **New IR:** an `AuthIdentitySpec` (link_via + field map/defaults) on `EntitySpec`; a
  `core/validation/` rule (binding on at most one entity; `link_via` is a column; every
  required-no-default column is resolved per A1).
- **Runtime:** `_mirror_auth_user_to_domain` generalised to a shared helper (D4) invoked from the
  production registration path *and* the test route; the create handler's `ref User` special-case
  (route_generator.py ~L566) replaced by the `link_via` resolution already used for backed entities
  (D3b). **No change** to `SessionRecord`, `create_session`, membership, RLS, or audit (D1).
- **Closes the #1398/#1413/#778 cluster's parent:** the real-auth-flow mirror gap is resolved by a
  declared binding, and downstream `_seed_domain_user` workarounds are deletable.
- **Greenfield-friendly**, consistent with the RLS-tenancy / membership posture (ADR-0036/0037).

## Out of scope / deferred

- **Multi-`User`-shaped principals** (more than one domain entity backing one auth identity). v1
  binds exactly one entity (the `User`), mirroring ADR-0037's "principal is always the framework
  `User` in v1".
- **Email change / re-link.** `link_via: email` assumes a stable link; an email change updating both
  stores is a follow-up (the idempotent upsert handles re-provision, not key migration).
- **Non-email link fields** beyond the v1 `email` join — allowed by `link_via` but only `email` is
  validated/tested in v1.
- **Provision a fenced `User` at first org-membership** (the A1/a2 alternative). v1 rejects a
  fenced-`User` binding at validate (D6) rather than create a tenant-fenced principal row at
  registration-before-membership. Deferring the mirror to membership-activation is a coherent future
  extension if a tenanted principal table is ever required; out of scope for v1.
