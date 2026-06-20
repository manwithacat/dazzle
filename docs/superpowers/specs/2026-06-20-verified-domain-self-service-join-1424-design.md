# Verified-domain self-service join (non-SSO) — design

**Issue:** #1424 Gap 1 (reframed) + Gap 2 (worked example)
**Date:** 2026-06-20
**Status:** Design approved; implementation deferred (large, phased) — issue stays open with this plan linked.
**Predecessors:** #1404 (apex discovery, Phase B/D), #1342 (enterprise auth / connections / DNS-TXT domain verification), #1418/#1393 (host-pin / forbidden-org), admin-capability authz (v0.81.104).

---

## 1. Problem & reframing

#1424 Gap 1 as originally posed: *"should a password login at the apex, given an email
whose domain is verified for exactly one tenant, route to that tenant's host?"*

Tracing the two existing paths showed the literal framing is the wrong question:

- **Password login already routes by *membership*** (`activate_session_for_login` → apex
  discovery, Phase B). For an existing member, membership routing is strictly *more
  precise* than email-domain routing — the domain adds nothing.
- Email-domain routing would therefore only change behaviour in the **zero-membership**
  case. But routing a zero-membership identity *to* a tenant host lands them on the
  `forbidden_org` **403** (#1418/#1393 host-pin) — there is no password-side join
  affordance (JIT is SSO-only today). So "route to the tenant host" as written routes
  people into a 403.

The decision (confirmed with the issue author) is therefore **not** "routing yes/no" but
the feature that makes routing meaningful: a **verified-domain self-service join**. A
tenant proves ownership of a domain (DNS-TXT, the machinery already exists for SSO), and a
non-SSO (password) user with a **verified email** in that domain can join that tenant —
subject to the tenant's join policy. Routing then follows naturally because the user lands
somewhere they actually have access.

This is explicitly *superfluous when SSO is configured* (SSO already does verified-domain
routing + JIT). It is the rational non-SSO equivalent for enterprise apps that don't run an
IdP.

## 2. Decisions (locked during brainstorm)

| Decision | Choice |
|---|---|
| Where verified domains live | **Reuse `connection`** — new `type="domain"` (domain-only connection, no IdP config). Maximal reuse of `verify_domain` / `get_connection_by_verified_domain` / one-owner-per-domain / CLI / admin page. |
| Where join policy lives | **Tenant level** (not per-connection) — admission control spans every membership path and a tenant may own several connections. Effective domain set = union of the tenant's connections' `verified_domains`. |
| Join policy model | Per-tenant `domain_join_policy: off \| auto_join \| admin_approval`. **Default `admin_approval`** (safest enterprise posture). |
| Membership-domain restriction | **In scope, gates ALL membership paths** — invitation accept, self-service join, SSO JIT, admin manual-add. Single `restrict_membership_to_verified_domains` tenant flag. |
| Self-asserted-email defence | **`email_verified == True` required** for any self-service join — converts a self-asserted email into proven mailbox control, matching the SSO anti-hijack strength. |
| Routing | Never a grant. A pre-membership identity is never routed into a tenant host (no 403 bounce); they see "request submitted" / "pending approval". Apex discovery routes only *after* a membership exists. |

## 3. Architecture

```
password login/signup  ──►  email_verified?  ──►  domain ∈ tenant verified set?  ──►  policy
   (apex host)                  │ no                    │ no                            │
                                ▼                       ▼                     off ──────┤──► no-orgs (honest)
                       trigger email-verify      no-orgs (honest)      auto_join ───────┤──► JIT membership ─► apex route to host
                                                                  admin_approval ───────┘──► JoinRequest(pending) ─► "submitted" page
                                                                                                       │
                                                                              admin approves (manage_members) ─► membership ─► next login routes
```

### 3.1 Data model

- **Connection `type="domain"`** — a domain-only connection. Carries `verified_domains`,
  no `provider`/OIDC/SAML config. *All SSO-only code paths must tolerate a connection with
  no provider* (audit `connections.py`, `enterprise_routes.py`, `saml_routes.py`,
  `sso_*`). The one-verified-owner-per-domain invariant (`claim_verified_domain`) already
  prevents a domain being claimed by both a domain-connection and an SSO connection.
- **Tenant settings** (where tenant/org config lives — likely `OrgRecord`/tenant store;
  confirm during impl):
  - `domain_join_policy: str` ∈ {`off`, `auto_join`, `admin_approval`}, default
    `admin_approval`.
  - `restrict_membership_to_verified_domains: bool`, default `False`.
- **`JoinRequest`** record: `id`, `tenant_id`, `identity_id`, `email`, `status` ∈
  {`pending`, `approved`, `denied`}, `created_at`, `decided_at`, `decided_by`. Unique
  `(tenant_id, identity_id)` among non-terminal statuses (no duplicate pending requests).
  All schema via Alembic (ADR-0017); auth tables are dual-written (_init_db + alembic
  mirror) — see the auth-store parity gate.

### 3.2 Core (pure, testable) units

- `email_domain(email) -> str` — already exists in `enterprise_login.py`; lift to a shared
  helper.
- `tenant_verified_domains(store, tenant_id) -> set[str]` — union over the tenant's
  connections.
- `resolve_domain_tenant(store, email) -> tenant_id | None` — reuse
  `get_connection_by_verified_domain` (one-owner ⇒ at most one tenant). Returns the tenant
  owning the email's verified domain, or None.
- `assert_domain_admissible(store, tenant_id, email) -> None | raises` — the single
  admission-control gate. No-op when `restrict_membership_to_verified_domains` is off;
  otherwise requires `email_domain(email) ∈ tenant_verified_domains`. Called by **every**
  membership-creating path.
- `decide_domain_join(policy, *, email_verified, has_membership) -> JoinOutcome` — pure
  decision mapper (`Off` / `AutoJoin` / `NeedsApproval` / `Noop`), mirroring
  `apex_discovery.resolve_apex_redirect`'s pure-mapper style for exhaustive unit testing.

### 3.3 Flow integration

- **Password login/signup** (`password_login_routes.py`): after auth success and *after*
  the existing membership-based `activate_session_for_login`, if that resolved **no**
  membership, evaluate `decide_domain_join`. Gate on `user.email_verified`. `auto_join` →
  JIT membership (reuse the `enterprise_login` step-4 create-membership-with-default-roles
  pattern, default-deny roles) then re-run apex routing; `admin_approval` → create
  `JoinRequest`, redirect to a "request submitted" view.
- **email_verified sequencing**: signup creates the user *before* verification
  (`submit_signup_password`). A self-service join therefore cannot complete at raw signup —
  it requires the email-verification flow first. The join is (re-)evaluated on the
  **email-verification callback** (`email_verification_routes.py`), not at signup. A
  freshly-verifying user whose domain matches a tenant gets the join outcome at that point.
- **Admission control everywhere**: insert `assert_domain_admissible` into
  `invitations.accept_invitation`, `enterprise_login.provision_enterprise_login` (SSO JIT),
  `member_admin` manual-add, and the new self-service join. (SSO JIT already enforces
  verified-domain on the *asserted* email; the new gate additionally enforces the *tenant
  restriction* uniformly.)
- **Routing** (`apex_discovery.py`): unchanged. It already routes by membership; once a
  membership exists the user routes to the host on the next request. No pre-membership
  routing is added — that is the deliberate anti-403 / anti-enumeration choice.

### 3.4 Tenant-admin UX (the flagged concern)

The surface already exists and is capability-gated — we **extend**, not invent:

- `/auth/connections` (gated `manage_connections`, fail-closed `admin_policy`) already
  renders connections + `add-domain` + `verify-domain`. Add:
  - a "Verify a domain for self-service join" affordance → creates a `type="domain"`
    connection, then the existing add-domain/verify-domain actions apply unchanged;
  - a **join-policy selector** (`off`/`auto_join`/`admin_approval`) and the
    **restrict-to-verified-domains** toggle (tenant settings).
- New **join-requests approval queue** under the `member_admin` surface (gated
  `manage_members`): list pending `JoinRequest`s, approve (→ membership) / deny.
- Capabilities: reuse `manage_connections` (domain config) and `manage_members` (approve
  joins). No new capability needed; if a distinct one is wanted later it slots into
  `admin_policy.CAPABILITIES`.
- These are *technical-admin* tasks (not data-admin) — they live on the framework auth
  surfaces, consistent with the existing connection/member admin split.

## 4. Security invariants (must all hold)

1. **Proven mailbox** — no self-service join without `email_verified == True`. Self-asserted
   email never routes or joins.
2. **Verified-domain only** — only DNS-TXT-proven domains (`verified_domains`) participate;
   reuses the SSO anti-hijack. A claimed-but-unverified domain does nothing.
3. **Routing is never a grant** — membership is the grant; routing only follows an existing
   membership.
4. **No enumeration oracle** — the apex/login response must be identical whether or not the
   typed email's domain maps to a tenant (no "this domain belongs to BigCorp" signal to an
   unauthenticated/zero-membership probe). The `admin_approval` "submitted" page must not
   confirm tenant identity beyond what the user already proved by controlling the mailbox.
5. **Uniform admission control** — when restriction is on, *every* membership path enforces
   it; no back door (invitation, manual-add, JIT).
6. **One-owner-per-domain** — preserved by the existing `claim_verified_domain` advisory
   lock; a domain cannot route to two tenants.

## 5. Worked example (Gap 2)

A kayfabe **`examples/`** app (it needs per-persona guides + serves as the canonical
on-ramp reference, so an example — not a `fixtures/` probe — is the right home; this incurs
the guide-bar + drift-list + compliance-regen burden, which is acceptable and is the point
of Gap 2):

- DSL with `tenant_host:` + `membership:`, a `type="domain"` connection, and
  `restrict_membership_to_verified_domains` on.
- CLI runbook doc (`docs/reference/`): create-connection → `add-domain` → DNS-TXT
  `verify-domain` → self-service join → admin approval → tenant-host routing.
- Per-persona guides: a **tenant technical admin** (configures domains/policy, approves
  joins) and a **joining employee** (verifies email, requests/auto-joins).
- Gives the loop runtime/e2e coverage (`dazzle ux verify --guides`) beyond the existing
  unit/integration tests (`test_domain_verification.py`, `test_connection_admin_routes.py`,
  `test_connections_pg.py`).
- Drift-gated lists to update: `.claude/CLAUDE.md` examples line + `tests/unit/test_docs_drift.py`.

## 6. Phasing (suggested)

1. **Data model + admission gate** — `type="domain"` connection, tenant settings,
   `JoinRequest`, `assert_domain_admissible` wired into all membership paths (restriction
   enforceable even before self-service join exists). Alembic + parity mirror.
2. **Verification reuse** — confirm `verify_domain` / CLI / one-owner work for a
   domain-only connection; audit SSO-only paths for provider-None safety.
3. **Self-service join flow** — `decide_domain_join` pure mapper, login/signup +
   email-verification-callback integration, JoinRequest creation, "submitted" view.
4. **Tenant-admin UX** — extend `/auth/connections` (policy selector + restrict toggle +
   domain-connection affordance) and the `member_admin` join-requests queue.
5. **Routing confirmation** — verify apex discovery routes post-join; assert no
   pre-membership routing / no enumeration oracle (negative tests).
6. **Worked example + guides** (Gap 2) — example app, CLI runbook, guides, e2e.

Each phase ships independently (staged IR/runtime pattern where applicable) with its own
tests. Default-off settings (`domain_join_policy=admin_approval` only *acts* once a domain
is verified; `restrict=False`) mean phases 1–2 are inert until a tenant opts in — safe to
land early.

## 7. Model-driven failure-mode note (CLAUDE.md review rule)

- **Failure mode risked:** hidden-side-effect auth behaviour (a login doing more than
  authenticating). Mitigated by routing-never-a-grant (invariant 3) and the pure
  `decide_domain_join` mapper that makes the behaviour traceable from inputs.
- **Detector:** negative tests for the enumeration oracle (invariant 4) and the uniform
  admission gate (invariant 5); these must be *live* tests, not just documented.
- **Traceability:** a competent engineer can trace "user X got a membership" to either an
  approved JoinRequest row or an auto_join with the connection/domain that matched — both
  auditable.
- **Semantics preserved:** membership/authz remain the grant; this adds an on-ramp, not a
  new authz path.

## 8. Out of scope / follow-ons

- Distinct admin capability for domain-join config (reuse `manage_connections` for now).
- Bulk domain import, wildcard/subdomain matching (exact-domain only, as today).
- Cross-tenant domain sharing (one-owner-per-domain stands).
