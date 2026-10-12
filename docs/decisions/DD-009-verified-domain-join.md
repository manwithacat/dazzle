# DD-009: Verified-domain self-service join — parked until a consumer admits members by email domain

```yaml
id: DD-009
status: PARKED
issues: [1424]
adrs: [0057, 0003, 0036, 0037]
decided: 2026-10-12
decided_at_sha: 2de583aa741ecc4dfad1f369f6c773fa12f99966
parent: flense-programme
```

## One-line intent

No consumer turns on verified-domain join; its example (`domain_join_co`) was
retired in flense ship E. Flense ship F (ADR-0057) removes the join policy,
the join-request queue and the membership admission gate. Enterprise SSO's
DNS-TXT domain verification (`auth/domain_verification.py`,
`verified_domains` on connections, home-realm routing) stays.

## Plan (what we already concluded)

Restore from the commit this DD was parked at
(`2de583aa741ecc4dfad1f369f6c773fa12f99966`):

- `auth/domain_join.py` — pure decision logic: `assert_domain_admissible`
  (uniform fail-closed gate on every membership-creating path: invitation
  accept, SSO JIT, SCIM) and `decide_domain_join(policy, email_verified,
  has_membership)` → Off / AutoJoin / NeedsApproval / Noop.
- `auth/org_settings.py` — typed view of `organizations.settings`:
  `domain_join_policy` (`off` | `auto_join` | `admin_approval`) and
  `restrict_membership_to_verified_domains`; leftover form tokens never
  invent a policy.
- `auth/join_requests.py` + `join_request_routes.py`, the `join_requests`
  table (re-add with a new Alembic revision; revision 0022 leaves the table in place pending operator sign-off), the
  `/auth/join-requests` admin queue (approve / deny, `FOR UPDATE`
  serialisation, CSRF-gated) and the `/auth/join-requested` page.
- Hooks: password login and email verification call `apply_domain_join`
  for a verified email with no membership; a join hiccup never breaks auth.
- Counter-priors: never admit on an unverified email or an unverified
  domain; never let the domain match override an explicit invitation.

## Reopen when (consumer force)

1. **Named consumer** — AegisMark wants staff with a school's email domain
   to join that school's tenant without an invitation.
2. **Evidence of host workaround** — bulk invitation scripts per school, or
   an `app/` route that creates memberships from email domains.
3. **Acceptance that unblocks** — in AegisMark's CI a verified
   `@school.example` user lands in the school tenant (auto-join) or in the
   admin queue (approval), and an off-domain user is refused when the
   tenant restricts membership.

When a force lands:

1. Set `status: FORCED` and date it.
2. Comment on every linked issue with the consumer + this DD path.
3. Implement against the plan above; open child issues if the plan splits.
4. When shipped, set `status: DONE` and close issues.

## Already shipped (do not re-litigate)

- Enterprise SSO connections, DNS-TXT domain verification and
  verified-domain home-realm discovery for OIDC/SAML.
- The `organizations.settings` JSON column (still present, now unread).

## Explicitly out of scope until force

- Multi-domain policies per tenant, domain allow/deny lists beyond the
  verified set, cross-tenant join suggestions.

## Trail

| Date | Event |
|------|--------|
| 2026-10-12 | Parked (this DD); verified-domain join removed in flense ship F |
