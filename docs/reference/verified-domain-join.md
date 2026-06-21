# Verified-Domain Self-Service Join

The verified-domain join (#1424) lets a **non-SSO** user with a *verified* work
email self-join the org that owns their email domain — no per-user invitation.
A tenant proves it owns a domain (the same DNS-TXT mechanism enterprise SSO
uses), sets a per-tenant join policy, and verified-email users in that domain
join (or request to join) under it.

It is the password-side complement to invitations and SSO JIT provisioning, and
is superfluous once SSO is configured. The worked example is
[`examples/domain_join_co`](https://github.com/manwithacat/dazzle/tree/main/examples/domain_join_co).

> **Why this exists.** Password login already routes by *membership*, so a member
> reaches their org fine. The gap was a verified-email user with *no* membership
> who lands on a tenant host → `forbidden_org` 403, with no password-side way to
> join. This flow fills exactly that gap. Routing is never itself a grant: a
> not-yet-member is never silently admitted by visiting a tenant host.

## Where each step lives (CLI vs admin console)

| Step | Surface |
|---|---|
| Create the provider-less `type="domain"` connection | **Admin console** — `/auth/connections` (needs `manage_connections`) |
| Claim a domain + show / verify its DNS-TXT record | **CLI** — `dazzle auth connection {add-domain,show-verification,verify-domain}` (or the same `/auth/connections` page) |
| Set the join policy (`off` / `auto_join` / `admin_approval`) | **Admin console** — `/auth/connections` policy controls |
| Set `restrict_membership_to_verified_domains` | **Admin console** — `/auth/connections` policy controls |
| Approve / deny a pending join | **Admin console** — `/auth/join-requests` (needs `manage_members`) |
| The join itself | **Runtime** — evaluated at password login + email-verify, fail-closed on `email_verified` |

There is intentionally **no CLI to create the connection, set the policy, or
approve a join** — those are capability-gated admin actions and live in the
console. The CLI owns only the domain-ownership proof.

## The loop

### 1. Create a domain connection (admin console)

As an admin with `manage_connections`, open **`/auth/connections`**, choose
**"Add connection → Domain"**, and create a provider-less connection for the org.
A `type="domain"` connection carries no IdP secrets — it exists purely to hold
verified domains and reuse the DNS-TXT machinery. Note its connection id.

### 2. Claim and verify the domain (CLI)

```bash
# Claim the domain — prints the DNS TXT record to publish.
dazzle auth connection add-domain <connection-id> acme.test

# (Re-print the expected record at any time; no DNS lookup.)
dazzle auth connection show-verification <connection-id> acme.test

# Publish the printed TXT record at the domain, then verify ownership.
dazzle auth connection verify-domain <connection-id> acme.test
```

On success the domain is added to the connection's `verified_domains` and starts
routing. Verification is required before any join can reference the domain — an
**unverified** domain never admits anyone (fail-closed).

### 3. Set the join policy (admin console)

Back on **`/auth/connections`**, set the org's `domain_join_policy`:

| Policy | Effect for a verified-email user in the domain |
|---|---|
| `off` | No self-service join. Invitation / SSO only. |
| `auto_join` | Joined immediately on (verified) login / email-verify. |
| `admin_approval` *(default)* | A join **request** is queued; the user lands on a generic "request submitted" page. |

Optionally enable **`restrict_membership_to_verified_domains`** to fence *every*
membership path (invitation, SSO-JIT, SCIM, self-service) to the org's verified
domains — a uniform admission gate, not just a self-service toggle.

### 4. The user joins

A user signs up / logs in with a work email and **verifies it**. At login and at
the email-verify callback the runtime checks: is this email's domain a verified
domain of some org, and what is that org's policy?

- `auto_join` → membership is created and the user is routed to the org's host.
- `admin_approval` → a join request is queued; the user sees a generic
  "request submitted" page (**no tenant disclosure / no enumeration oracle**).

A **self-asserted** (unverified) email never grants membership — the gate is
fail-closed on `email_verified`.

### 5. Approve the join (admin console)

For `admin_approval`, an admin with `manage_members` opens
**`/auth/join-requests`**, reviews the queue, and approves or denies each pending
request. Approval creates the membership (default-deny roles) and marks the
request approved; the decision is lock-serialized so concurrent approvers can
never double-create a membership (#1430). The user can then reach the org on its
tenant host.

## Security invariants

These hold across all paths (proven against real Postgres in
`tests/integration/test_domain_join_routing_pg.py`):

- **A self-asserted email never grants.** The gate requires `email_verified`.
- **Routing is never a grant.** Visiting a tenant host does not create
  membership for a non-member; there is no pre-membership host routing.
- **No enumeration oracle.** The "request submitted" page is identical
  regardless of which (or whether any) tenant owns the domain.
- **Admin actions are CSRF + capability gated.** Connection ops require
  `manage_connections`; join approval requires `manage_members`.
- **Uniform admission.** With `restrict_membership_to_verified_domains`, the same
  `assert_domain_admissible` gate fences invitation / SSO-JIT / SCIM / self-service.

## See also

- [Enterprise SSO & Provisioning](enterprise-sso.md) — OIDC / SAML / SCIM, the
  connection + DNS-TXT machinery this flow reuses.
- [Multi-Tenant Hosts](tenant-hosts.md) — the `tenant_host:` routing a join lands into.
- [`examples/domain_join_co`](https://github.com/manwithacat/dazzle/tree/main/examples/domain_join_co) — the worked example app + per-persona guides.
