# Auth Plan 4b.ii — Enterprise JIT identity-join kernel

> **For agentic workers:** hybrid inline execution + adversarial review (account-takeover-risk code).

**Goal:** Turn a `ConnectionProvider` callback's `AssertedIdentity` into a usable
`(global Identity, org Membership)` pair — the security-critical step where an org's
IdP assertion becomes platform access — as a pure, exhaustively-tested function.

**Architecture:** `provision_enterprise_login(store, connection, asserted)` mirrors the
proven `accept_invitation` verified-email→membership path, with an org-level anti-hijack
check (asserted email's domain ∈ `connection.verified_domains`), differential trust on
`AssertedIdentity.claims_source`, identity reuse-or-create, membership reuse-or-JIT-create,
and group→persona mapping (default-deny). **No routes/startup wiring here — that's 4b.iii**
(the kernel is callable + reviewed in isolation first).

**Tech Stack:** the 4a `ConnectionRecord`/`AssertedIdentity`, the AuthStore membership API
(`get_user_by_email`/`create_user`/`get_memberships_for_identity`/`create_membership`).

---

## Security invariants (must hold)

1. **Anti-hijack (load-bearing):** an org's connection may only assert an email within its
   own `verified_domains`. Stops a malicious/compromised org IdP from asserting
   `victim@othercompany.com` and seizing that global identity. Complements the
   discovery-layer verified-domain *routing* with an identity-layer check on the
   *asserted* email. A connection with **no** verified domains can assert **nobody**.
2. **Differential trust:** a non-`id_token` `claims_source` (the unsigned UserInfo-endpoint
   fallback) must carry `email_verified=true`; the provider tolerates a *missing*
   `email_verified` only on the cryptographically-validated id_token path.
3. **Default-deny roles:** unmapped IdP groups contribute no roles. An empty role set means
   the member gets in but `permit:`/`scope:` default-deny their actions.
4. **No duplicate membership:** an existing membership for (identity, org) is reused (any
   status); a concurrent-create unique-violation is caught and re-resolved.
5. **JIT gate:** membership auto-creation is gated by `connection.config["jit_provisioning"]`
   (default True — enterprise SSO's whole point); disabled → `no_membership` (caller decides).

## Task 1: the kernel + tests

**Files:** Create `src/dazzle/http/runtime/auth/enterprise_login.py`,
`tests/unit/test_enterprise_login.py`.

- `EnterpriseLoginError(reason, message)`, `_email_domain`, `map_groups_to_roles`,
  `provision_enterprise_login`.
- Tests (fake store): domain-not-verified refuses; no-verified-domains refuses everyone;
  unsigned-fallback-without-email_verified refuses; id_token path with missing email_verified
  is allowed; identity created when absent / reused when present; membership reused when
  present / JIT-created when absent; jit_provisioning=false refuses; group→role mapping
  (default-deny, dedup); concurrent unique-violation re-resolves.

## Task 2: verify + adversarial review + ship

- ruff + mypy + drift gates + mkdocs --strict; full unit slice.
- Adversarial review (silent-failure-hunter) on the anti-hijack + differential-trust paths.
- `/bump patch`, CHANGELOG `### Added` + `### Agent Guidance`, ship.
