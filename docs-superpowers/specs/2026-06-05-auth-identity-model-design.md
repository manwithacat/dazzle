# Aspirational Auth & Identity Model — Design Spec

**Date:** 2026-06-05
**Status:** Approved design; decomposes into sequential implementation plans (see §9)
**Author:** Brainstormed with @manwithacat
**Supersedes:** the RLS-tenancy pivot's locked "users are tenant-scoped, single-tenant-per-user, email unique per-tenant" decision (`2026-06-04-rls-tenancy-design.md` §Locked decisions item 2). That spec + the `project_rls_tenancy` memory must be updated; a new auth-model ADR ratifies this.
**Relates:** RLS tenancy Phases A–D (shipped v0.81.21–24), `is_tenant_root` (`core/ir/domain.py`), the existing `tenancy:` block, provable-RBAC (`src/dazzle/rbac/`), the compliance pipeline (`src/dazzle/compliance/`), `[[auth.oauth_providers]]` (social OIDC, the `sso` extra/authlib), ADR-0003 (clean breaks), ADR-0008 (PostgreSQL-only), ADR-0010 (no field conditions in `permit:`), ADR-0017 (schema changes via Alembic).
**Issues this unblocks:** #1338 (tenant excision) and #1339 (signed/contained QA auth) — both re-home onto Plan 1's membership model as "Phase E" (§9).

---

## 1. Motivation

The work that surfaced this began as "auth-store tenant-scoping," the prerequisite for RLS-tenancy Phase E (provision/excise ephemeral test tenants + a DB-enforced QA containment invariant). Investigating it revealed that the framework auth store (`users`, `sessions`, `password_reset_tokens`, `magic_links`, `user_preferences`) is **global and entirely unscoped** — no `tenant_id` anywhere, email globally unique, login resolves users globally — and that a user's tenant is currently derived **indirectly**, by copying a domain attribute into `auth_context.preferences` (#532) and reading it back via `_resolve_user_attribute("tenant_id")`. That preferences-indirection is brittle and is the cross-tenant hole Phase B flagged.

Rather than bolt a `users.tenant_id` column onto a model that wasn't designed for tenancy, we elevated the question to: **what should the auth model of a modern, aspirational SaaS framework look like — one that natively meets app builders' needs and strengthens the compliance story?**

The modern B2B-auth consensus (WorkOS, Clerk, Auth0 Organizations, Microsoft Entra) is **global user identity + first-class Organization + an Organization-Membership join**, with **two-phase auth** (prove identity, then enter an org context) and per-membership roles. In Auth0's own vocabulary this is the **GitHub/Linear model** (one identity, many org memberships) — as opposed to the **Google model** (one org per account, duplicate accounts per email) that the RLS pivot had locked in for fence-cleanliness.

This design adopts the GitHub/Linear model and shows it is **compatible with the RLS fence**: identity sits *above* tenancy (platform-domain, global), membership *is* the fenced, tenant-scoped object. One person belonging to two orgs is the identity layer the fence hangs from — not business logic crossing the fence, so the pivot's "cross-tenant = events" tenet (about *domain* data) still holds.

## 2. Core data model

Four framework-owned entities (built-in, **not** author-declared — like `AIJob`/`FeedbackReport`), positioned relative to the RLS fence:

### 2.1 `Identity` — the global principal (platform-domain, **outside** the fence)
- `id` (uuid pk), `email` (citext, **globally unique**), `email_verified` (bool)
- credential material: `password_hash` (**nullable** — SSO/passwordless identities have none), `totp_secret`, `totp_enabled`, recovery codes, etc.
- `status` (active/suspended), timestamps
- **A small set of platform roles** (cross-org super-admin / support; see §4) — distinct from org roles.
- This is today's `users` table, recast as global identity and stripped of tenant assumptions. **An Identity with zero memberships is valid** (just-signed-up, awaiting invite).

### 2.2 `Organization` — the tenant (IS the tenant root)
The existing `archetype: tenant` / `is_tenant_root` entity + the `public.tenants` registry (`slug`, `is_test` (Slice 0), `status`, `config`). No new entity — naming the existing one.

### 2.3 `Membership` — the join, and **the RLS-fenced object** (tenant-scoped)
- `id` (uuid pk), `tenant_id` → Organization (the partition key, **fenced**)
- `identity_id` → Identity (FK points *out* of the fence to the global principal — allowed; "which person this membership is for")
- `roles` — the personas-as-roles for this person *in this org* (per-membership, replaces global roles)
- `status` (active / invited / suspended) — carries the invitation flow
- `invited_by`, `joined_at`, timestamps
- **unique (tenant_id, identity_id)** — one membership per person per org

### 2.4 `Session` — scoped to `(identity, active_org)`
- `id`, `identity_id`, `active_membership_id` → Membership (pins active org **and** roles), `expires_at`, `csrf_secret`, ip/ua
- Org-switch = swap `active_membership_id` → re-binds the fence (§3).

### 2.5 What the shape buys
- *"Email unique per-tenant"* is **subsumed** by something stronger: email is globally unique on `Identity`; `Membership` is unique per `(org, identity)`. Same person → many orgs; never double-membered in one.
- **Fence relocation is explicit:** `Identity`/`Session` are platform-domain (outside, like `AIJob`); `Membership` is fenced. A request's tenant context now comes from `session → active_membership → tenant_id` — a **hard FK**, replacing the preferences-copy.
- **Phase E falls out for free:** excision = delete the org's memberships + cascade, then reap now-orphaned identities; #1339 containment = `session → membership → org`, check `is_test`.

## 3. Two-phase auth, org-context resolution & graceful degradation

**Phase 1 — prove identity.** Password / OIDC / SAML / magic-link → resolves an `Identity`. No tenant context yet.

**Phase 2 — activate an org context.** Pick one of the identity's memberships → scope the session to `(identity, active_membership)` → bind `dazzle.tenant_id` + role/attr GUCs from that membership.

This **replaces the preferences-indirection**: the per-request auth dependency stops reading `_resolve_user_attribute("tenant_id")` from copied preferences and reads `session → active_membership → tenant_id` (hard FK) for the fence, and `active_membership.roles` for the scope-policy GUCs.

**Org-context resolution — host-pinned, else switcher:**
- **Host-pinned** (`acme.app.com` → org `acme`, reusing `tenant_host` #1289): the session must activate that org's membership; if the proven identity has no membership there → **403** (you exist, but not here).
- **Switcher** (shared domain, no host pin): one membership → auto-activate (invisible); multiple → org picker; zero → "no orgs yet" (awaiting invite / create-org).

**Graceful degradation — "simple stays simple":** a single-org app auto-provisions (or declares) one Organization; every signup → one membership; Phase 2 is invisible. No subdomain, no switcher, no org UI. Complexity surfaces only with multiple orgs.

**SSO/SCIM mapping onto the phases:**
- **Enterprise SSO is org-pinned-first.** The IdP is configured per-org, so the org is resolved (host or verified email-domain→org) *before* Phase 1 runs through that org's IdP; JIT-provision a membership if the connection permits.
- **SCIM is out-of-band** (no interactive login): the IdP pushes create/update/deactivate to the org's SCIM endpoint → directly manages `Membership`/`Identity`.

**Org-switch ≠ re-auth:** switching re-scopes (new `active_membership_id`, re-bind GUCs, CSRF/session rotation); it never re-proves identity.

## 4. RBAC: personas-as-roles, composed onto `permit:` / `scope:` / `grant_schema`

Roles relocate from global (on the user) to **per-membership**; the provable-RBAC structure is otherwise intact — only the *source* of the role set changes.

- **Personas → membership roles.** A `persona admin` stays an app-global role *definition*; an Identity *holds* it *in org Y* via `Membership.roles`. "Is this user an admin?" = "does the session's active membership include `admin`?"
- **`permit:` — DSL unchanged, re-sourced.** `permit: as admin` evaluation reads the persona set from `session.active_membership.roles` instead of global `user.roles`. The provable-RBAC matrix stays static and analyzable (persona × action). ADR-0010 preserved.
- **`scope:` — composes with the fence.** The fence (`dazzle.tenant_id`) is already bound from `active_membership.tenant_id`, so scope rules operate within the already-fenced tenant (exactly Phase C, membership-sourced). `current_user.<attr>` resolves **membership-first, then identity**; Phase C's `dazzle.user_<attr>` GUCs populate from the membership. Keep the `current_user.<attr>` spelling (no grammar churn); reserve an explicit `current_membership.` accessor as a *possible later* affordance.
- **`grant_schema` — membership-scoped.** Grant tuples become `(grantor_membership, grantee_membership, permission, resource)`; the decision log gains org attribution.
- **Platform roles (escalation subtlety).** Cross-org super-admin / support can't be membership-scoped → a **small, separate set of platform roles on the `Identity`**; platform-admin acting inside an org runs through an elevated, heavily-audited `dazzle_bypass`-style context. Org roles on membership; platform roles on identity; never conflated.

**Net for the author:** the `permit:`/`scope:`/`as:`/`grant_schema` surface is unchanged; only the runtime *source* of identity + roles moves from "global user" to "session's active membership." Provability + static matrix survive; the audit trail gets richer.

## 5. The per-org enterprise-connection model

**A new framework-owned, *fenced* entity: `Connection`** — an enterprise auth connection belonging to an org.
- `id`, `tenant_id` → Organization (**fenced**), `type` (`oidc | saml | scim`), `provider` (`native` default | `<vendor>` — the seam)
- `domains[]` (verified email domains routing to this org/connection), type-specific config (OIDC issuer/client; SAML IdP metadata/entityID/cert/ACS; SCIM bearer/endpoint), `group_mapping` (IdP group/attribute → persona, default-deny if unmapped), `status`
- **all secret material encrypted at rest, never in artifacts**

**The seam — a `ConnectionProvider` protocol** (call sites never know who implements):
- `NativeOIDCProvider` (authlib) · `NativeSAMLProvider` (pysaml2) · `NativeSCIMProvider` (SCIM 2.0 endpoints) — the default.
- `DelegatedProvider(provider="workos"|…)` — same protocol, calls a vendor; future-addable without touching call sites. **Native vs delegated is config, per connection.**
- Interface: SSO → `initiate(org, req) → redirect`, `callback(org, req) → AssertedIdentity(email, attrs, groups)`; SCIM → per-org REST handlers.

**Build-vs-integrate decision: native via mature libraries, seam preserved.** authlib (OIDC; already a dep) + pysaml2 (SAML; mature, actively maintained, ~195k weekly downloads, the de-facto Python SAML library) + a native SCIM 2.0 server. The seam means a deployment that doesn't want to run `libxmlsec1`/own the IdP-compat treadmill can delegate that one connection to a provider. python3-saml (OneLogin) was rejected — stalled (no release in 12 months).

**JIT provisioning (interactive SSO):** org resolved (host or verified email-domain→org) → connection `initiate` → IdP → `callback` validates → resolve/create global `Identity` by verified email → ensure `Membership` in the org (JIT if allowed), mapping IdP groups → personas → session scoped to (identity, that membership).

**SCIM provisioning (out-of-band):** IdP pushes to `/scim/v2/...` with the org's bearer token → org resolved from token → create/update/**deactivate** `Membership` (+ `Identity` by email). Deactivate ⇒ suspend membership + revoke sessions — the **timely-deprovisioning** control.

**Distinct from existing social login:** `[[auth.oauth_providers]]` (social Google/MS via authlib) is a global, non-org-pinned Phase-1 method — separate from enterprise per-org OIDC. Both stay.

**Security-critical (feeds the SAML ADR + conformance matrix):**
- SAML assertion validation: signature *scope*, audience restriction, `NotBefore`/`NotOnOrAfter`, `InResponseTo`/replay, single-use, **`defusedxml`** against XXE — proven by a conformance matrix (Okta / Azure AD / Google).
- Secrets encrypted at rest; SCIM bearer tokens constant-time-compared + rotatable.
- **Email-domain→org claims require verified domain ownership** (else org A hijacks org B's SSO).

## 6. Compliance evidence (self-evidencing access control)

Making identity/membership/roles **structural** turns access-control evidence into a **byproduct of the architecture, complete by construction**. Each model boundary emits a typed lifecycle event that the existing `compliance/` pipeline maps to a control:

| Event | Source | Maps to |
|---|---|---|
| **Provision** — membership created (invite / JIT / SCIM; org; roles; connection) | Membership create | SOC 2 **CC6.2**, ISO **A.5.16/A.5.18** |
| **Authenticate** — login (identity, method, MFA), org-activation, failures/lockouts | Session / Phase 1–2 | **CC6.1**, **A.5.17** |
| **Authorize** — permit/scope/grant decisions, attributed to identity × membership × org × role × time | provable-RBAC decision log | **CC6.1/CC6.3**, **A.5.15** |
| **Role change** — `Membership.roles` grant/revoke; grant tuples issued/revoked (+ grantor) | Membership / grant_schema | **CC6.3**, **A.5.18** |
| **Deprovision** — membership suspend/remove (SCIM deactivate, manual, excision) + session revocation | Membership / Session | **CC6.2/CC6.3**, **A.5.18** |
| **Privileged use** — platform-role / `dazzle_bypass` elevation (who/when/why/what) | platform-role path | ISO **A.8.2** |
| **Connection lifecycle** — enterprise connection create/modify/disable, domain verification | Connection | config-mgmt evidence |

**Why materially stronger than today:**
- The **membership table *is* the per-org access matrix.** "Everyone with access to org X and their roles as of date D" is a query; "every access change in period P" is the event stream — exactly an auditor's user-access-listing + access-review requests, answered completely (not sampled).
- **Access reviews (CC6.3)** become a generated, owner-attestable export.
- **Joiners/Movers/Leavers** = the provision/role-change/deprovision streams; SCIM gives automated leaver evidence.
- Clean **identity-vs-authorization separation** is itself what least-privilege / segregation-of-duties controls want to see.

**Requirements:** emission is a **framework concern at the model boundary** (incomplete if author-wired), stored in the existing **append-only/tamper-evident audit trail** (`audit`/`ledger`). Deliverable: an **access-evidence / access-review export** extending the current `rbac` compliance report with per-org membership snapshots + JML streams mapped to controls.

## 7. DSL surface & author experience

Principle: **invisible by default, opt-in complexity, enterprise config never in the DSL.** Identity/Membership/Session/Connection are framework built-ins — no new grammar.

**Tier 0 — single-org (default, invisible):** today's DSL — `persona`s + `permit:`/`scope:`. Framework provides login, one auto-org, one membership per signup. Author never sees `Membership`.

**Tier 1 — multi-org / B2B (opt-in via the existing `tenancy:` block):**
```dsl
tenancy:
  isolation: shared_schema
  multi_org: true          # opt into user-managed memberships: invitations + org switcher
archetype: tenant
  entity Workspace "Workspace": ...
persona owner "Owner"
persona member "Member"
archetype: profile          # optional per-member app data, framework-linked to membership
  entity Member "Member":
    display_name: str(120)
    avatar: file
```
→ Framework generates invitation flow, org switcher, member-admin surface, parameterized by personas.

**Tier 2 — enterprise (opt-in, runtime per-org, NOT DSL):** `Connection`s are per-customer-org *data*, configured by an org admin (admin surface / `dazzle.toml` / env) — never authored in `.dsl`. Grammar grows **zero** SSO keywords.

**New author surface is tiny:** `persona` (the single role vocabulary), `archetype: tenant` (exists), `archetype: profile` (new convention via the existing archetype mechanism), `current_user.<attr>` (unchanged spelling), and one new field — `multi_org:` in the `tenancy:` block.

**Existing apps' `entity User`:** auth-bearing fields migrate up to `Identity`; app-specific per-user fields migrate to the `profile` archetype (§8).

## 8. Migration / greenfield break

Bigger break than the RLS pivot (`users` → `Identity` + `Membership`). Per Dazzle's stage (pre-1.0, ADR-0003 clean-breaks):
- **Greenfield-native** for new apps.
- **Repo's own apps/fixtures** updated in the same breaking change (ADR-0003: all callers in one commit).
- **Downstream deployed apps:** a documented **single-org migration recipe** (Alembic data migration — create one default org, one membership per existing user, copy `users.roles`→`membership.roles`, preferences-tenant→`membership.tenant_id`), optionally a `dazzle auth migrate` helper for that mechanical case. **Multi-org migration is bespoke** (app judgment) — documented, not automated. No general migration engine (YAGNI).

**Identity-join rule (model invariant):** the same **verified** email arriving via multiple methods resolves to **one `Identity`** (verified email is the global join key). SSO/SCIM link to the existing identity by verified email and add a membership. Unverified-email collisions require verification before any merge (no confused-deputy). This makes JIT provisioning safe.

## 9. Non-goals & slicing

**Non-goals (designed-for, not built):** passwordless / passkeys / WebAuthn (future phase-1 method); migration auto-tooling beyond the single-org recipe; org hierarchies (flat orgs only); schema-isolation/db-per-tenant parity for the new model (shared_schema + RLS first); cross-org identity federation beyond verified-email matching.

**Slicing — sequential plans (each its own spec→plan→build→adversarial-review, mirroring CSRF/RLS phasing):**
1. **Identity/Membership/Session core** + two-phase auth + fence relocation + roles→membership + single-org degradation. *The keystone — closes the original "auth-store tenant-scoping" prerequisite, unblocking Phase E.*
2. **RBAC re-sourcing + compliance evidence** — permit/scope/grant from membership; platform roles on identity; lifecycle events → audit trail → compliance pipeline + access-review export.
3. **Multi-org UX** — invitations, org switcher, member-admin surfaces, `tenancy: multi_org:`, `archetype: profile`.
4. **Enterprise connections** — `Connection` + `ConnectionProvider` seam, native OIDC (authlib) + SCIM, org-admin config.
5. **SAML** — `NativeSAMLProvider` (pysaml2) + `defusedxml` + IdP conformance matrix + the SSO-validation ADR. (Isolated — highest-care security slice.)
6. **Phase E** (tenant excision #1338 + signed/contained QA provisioning #1339) — lands on Plan 1's membership model. Excise = delete the org's memberships + cascade orphaned identities (`DELETE … WHERE tenant_id = X` per scoped table in reverse `creation_order`, as `dazzle_bypass`); QA containment = `session → membership → org`, refuse unless `is_test`.

**ADRs:** one for this auth model (supersedes the RLS pivot's single-tenant-per-user decision; update `2026-06-04-rls-tenancy-design.md` + the `project_rls_tenancy` memory), and one for SAML/SSO validation guarantees (Plan 5).

## 10. Open questions for the implementation plans

- **Profile ↔ Membership linkage:** does `archetype: profile` carry its own row FK'd to `Membership`, or are profile fields columns on `Membership`? (1:1 either way; the converter must wire it.)
- **Session storage of `active_membership_id`** vs deriving it each request from a host-pin — and how org-switch rotates the session/CSRF.
- **`creation_order` reuse for excision** (Phase E): generalize `FKGraph.creation_order` (returns `None` on cycle, shaped for flow subsets) or add a dedicated full-entity-set reverse-topo method — and how orphaned-identity reaping composes with the per-tenant delete.
- **Where platform roles live exactly** (a column on `Identity` vs a separate `platform_grants` table) and how the elevated `dazzle_bypass` path is audited.
- **Single-org auto-provisioning trigger** (first boot vs first signup vs explicit `archetype: tenant`) and how it stays invisible.
- **Domain-ownership verification mechanism** for email-domain→org SSO routing (DNS TXT vs emailed token).
