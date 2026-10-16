# Enterprise SSO & Provisioning (OIDC and SCIM)

Dazzle ships native, per-org enterprise connections so an org's identity provider (Okta,
Microsoft Entra ID, Google, Ping, ...) drives sign-in and user lifecycle. Connections are
**runtime data**, not DSL: created and managed with `dazzle auth connection ...`, fenced to
one org, and gated by **domain verification**.

!!! note "Opt-in: `[auth.enterprise] protocols`"
    Enterprise auth is **off by default**. An app names the protocols it mounts in `dazzle.toml`:

    ```toml
    [auth.enterprise]
    protocols = ["oidc", "scim"]
    ```

    Only `"oidc"` and `"scim"` are accepted; any other name (including `"saml"`) is a manifest
    error that points at DD-013, and an empty list mounts nothing. A declared protocol whose
    extra does not import (`authlib` for OIDC, `cryptography` for both) stops the boot rather
    than skipping the protocol. Install the `sso` extra, which carries `authlib`,
    `cryptography` and `dnspython`. Connection rows of a type the manifest does not declare log at
    ERROR at startup and are not served.

    Decision record: `docs/decisions/DD-013-enterprise-sso-scim-connections.md`.
    Restore plan: `docs/plans/2026-10-16-enterprise-auth-restore.md`.

## The model

A **`Connection`** is a framework-owned, org-fenced record (`type` = `oidc` / `scim`; a `domain`
record carries a verified claim on its own). Secret material (OIDC `client_secret`, SCIM bearer)
is **AES-256-GCM encrypted at rest** under `DAZZLE_CONNECTION_SECRET`.

Two anti-hijack controls gate everything:

- **Verified-domain routing**: `?email=` only routes to a connection whose domain is *verified*.
- **Verified-domain provisioning**: an OIDC login or a SCIM push is accepted only for emails whose
  domain the connection has verified. A connection with no verified domains can assert nobody.

Verify a domain with DNS-TXT: `add-domain` -> publish the printed `dazzle-verify=...` record ->
`verify-domain`. A domain has exactly one verified owner (enforced atomically).

After a login, the asserted identity is joined to a global Identity by **verified email**, and a
**membership** is created or reused in the connection's org; IdP **groups map to roles** via the
connection's `group_mapping` (**default-deny**: an unmapped group grants nothing).

## Setup (per protocol)

| Protocol | Create | IdP configures | Entry point |
|----------|--------|----------------|-------------|
| **OIDC** | `dazzle auth connection create --tenant <org> --issuer ... --client-id ... --client-secret ...` | Redirect URI `<base>/auth/enterprise/callback` | `GET /auth/enterprise/login` |
| **SCIM** | `dazzle auth connection create-scim --tenant <org>` (prints the bearer once) | SCIM base URL `<base>/scim/v2`; header bearer token | `POST /scim/v2/Users` (IdP push) |

`dazzle auth connection scaffold` prints the end-to-end command sequence for a new OIDC
connection. Set `DAZZLE_CONNECTION_SECRET` before creating either type; prefer the
`DAZZLE_OIDC_CLIENT_SECRET` env var over `--client-secret` so the secret stays out of argv.
`--group-map eng=engineer` seeds the group -> role mapping.

`GET /auth/enterprise/login` resolves the connection from `?connection=<id>`, a verified
`?email=` domain, or the host pin of a tenant host, in that order, then redirects to the IdP.

### Readiness: `doctor` and `--probe`

`dazzle auth connection doctor <id> [--json]` reports what a connection still needs to go live
(network-free; exits 0 only when it is activation-ready, so CI and agents can gate on it). For
SCIM it checks that a bearer is present and a domain is verified. Add `--probe` for an opt-in
**live reachability** check of the OIDC discovery document. The probe is SSRF-guarded (https
only, every resolved address globally routable, no userinfo, no redirects) and informational: it
never changes the exit code, which stays bound to config readiness. CLI-only by design, so there
is no request-path SSRF surface.

## `require_sso`: send a domain's users to their IdP

A per-org flag on an OIDC connection. Turn it on or off with:

```bash
dazzle auth connection set-require-sso <connection_id> --on|--off [--tenant <org>]
```

With the flag set, every address on the connection's **verified** domains is refused local
credentials:

- JSON `POST /auth/login`, `POST /auth/forgot-password`, `POST /auth/register` and
  `POST /auth/reset-password` answer **403** with the shape below (403, not the 401 of a bad
  password: the credential is never evaluated).
- The form and link paths (`POST /auth/login/password`, `POST /auth/login/magic-link`,
  `POST /auth/forgot-password/submit`, `POST /auth/signup/password`,
  `POST /auth/signup/magic-link`, `POST /auth/reset-password/submit`, and `GET /auth/magic/{token}`
  for an already-issued token) answer **303** to the same login URL, keeping a safe `next`.
- `POST /auth/change-password` is refused for a signed-in user on such a domain, so a credential
  minted before the flag was set cannot bypass it.

```json
{"status": "sso_required", "login_url": "/auth/enterprise/login?email=..."}
```

Superusers are **not** exempt. **Existing sessions are not revoked**: the flag stops new local
sign-ins, it does not log anyone out. An unverified domain claim, a connection without the flag,
or an app without `oidc` declared behave as before. OIDC connections only.

## Admin capabilities

Connection administration is **CLI-first**: there is no in-app connection page today, and no
`manage_connections` capability. The one org-admin capability is `manage_members` (invite, list,
change-role, remove members). Bind it to your personas in the manifest (default-deny,
fail-closed):

```toml
[auth]
org_admin_roles = ["org_admin"]        # the default for any capability you don't list below

[auth.admin_capabilities]              # optional
manage_members = ["business_admin"]
```

## Trust model (why each source is trusted)

The JIT identity-join applies **differential trust** by claims source: an OIDC **id_token** is
cryptographically validated by authlib, so it is trusted as signed; the OIDC **UserInfo-endpoint
fallback** is unsigned and additionally requires `email_verified=true`. The verified-domain
anti-hijack applies to *all* sources.

## SCIM lifecycle

A SCIM `User` resource is a **membership**. `active:false` suspends and `DELETE` removes the
org membership **and revokes that org's sessions immediately** (other orgs' sessions survive).
Provisioning only lands on the connection's verified domains. Junk attribute values
(`active: "zzz"`, `members: "ghost"`, ...) answer a SCIM 400 and write nothing.

### SCIM Groups

`/scim/v2/Groups` is the authoritative path for **group -> role** assignment. Groups are
persisted, org-scoped resources with full CRUD and RFC 7644 member PATCH. A member references a
SCIM `User` (a membership) by id and must belong to the connection's org.

A membership's roles are recomputed over the union of **all** its groups (default-deny), so
removing a user from one group keeps a role still granted by another. The recompute is
**org-fenced**: a SCIM bearer cannot perturb another org's members.

`group_mapping` entries match a group by **either its display name or its IdP `externalId`**
(the stable group GUID, e.g. an Entra group objectId), so a GUID-keyed mapping survives a rename
and a name-keyed mapping still works. Renaming a group re-derives roles; if neither the new name
nor the GUID is in `group_mapping`, the mapped role is dropped (correct, since the mapping is now
stale).

**SCIM `User` identity is externalId-first.** Provisioning persists the IdP's stable user id
(`externalId`) on the membership (`memberships.external_id`, unique per org). A re-push under a
*changed email* updates the existing membership instead of forking a duplicate. The global
identity's email is **never** rewritten from a SCIM push, since it may be shared across orgs.

Per RFC 7643, `User.groups` is server-managed and read-only: the `groups` attribute on a `User`
POST/PUT is informational. Drive roles through `/scim/v2/Groups`.

### SCIM discovery

An IdP can self-configure from three bearer-authenticated discovery endpoints:

| Endpoint | Returns |
|----------|---------|
| `GET /scim/v2/ServiceProviderConfig` | supported features |
| `GET /scim/v2/ResourceTypes[/{id}]` | the `User` and `Group` resource types |
| `GET /scim/v2/Schemas[/{id}]` | the `User` and `Group` schema definitions |

The published schemas are a faithful subset: they advertise only the attributes Dazzle honours,
so discovery never promises an attribute the runtime ignores.

## Secret and key rotation

Both layers are CLI/devops-only.

| Command | Rotates |
|---------|---------|
| `dazzle auth connection rotate-secret <id>` | one connection's credential: the OIDC `client_secret` (`--client-secret`, never echoed) or a freshly minted SCIM bearer (printed once). |
| `dazzle auth connection rotate-secret <id> --grace 24h` | **SCIM only**: mints the new bearer but keeps the OLD one valid for the window, so the IdP migrates without a provisioning outage. |
| `dazzle auth connection revoke-previous-secret <id>` | ends a grace window early; the old bearer stops working immediately. |
| `dazzle auth connection secret-history <id>` | the append-only rotation audit trail. |
| `dazzle auth rotate-encryption-key` | the AES master key (`DAZZLE_CONNECTION_SECRET`): re-wraps every stored secret onto the new key with a two-key (`..._OLD`) window. |

Without `--grace`, rotation is a **hard swap** (right for a leak). `--grace <m|h|d|w>` is
SCIM-bearer-only: an OIDC `client_secret` is arbitrated by the IdP, so holding two does not help.
Expiry of the previous bearer is enforced at verification time. `rotate-secret`,
`revoke-previous-secret` and the key rewrap each append a `connection_secret_events` row with
non-secret detail; a secret value is never stored.

## Login error codes

A failed enterprise login never yields a session. It redirects to `/login?error=<code>`:

| Code | Meaning |
|------|---------|
| `sso_no_connection` | no active OIDC connection resolved for the connection id, email domain or host |
| `sso_unavailable` | the connection's provider could not be built or reached |
| `sso_domain_not_verified` | the email's domain is not verified for the connection |
| `sso_unverified_fallback` | the UserInfo fallback did not assert `email_verified=true` |
| `sso_no_membership` | no membership in the connection's org could be created or reused |
| `sso_no_email` | the IdP asserted no email |
| `sso_failed` | any other failure completing the sign-in |

## Troubleshooting

- **Boot stops naming `authlib` or `cryptography`**: install the `sso` extra; a declared
  protocol never silently skips.
- **Manifest error naming DD-013**: `protocols` holds a name other than `oidc` / `scim`.
- **Login goes to `sso_no_connection`**: check `dazzle auth connection list --tenant <org>`;
  an unverified domain does not route, so run `verify-domain`.
- **`doctor` exits non-zero**: read its checklist; it lists exactly what is missing.
- **SCIM 401 after a rotation**: the IdP still holds the old bearer; use `--grace` next time, or
  paste the new bearer into the IdP.
- **SCIM push for an address is refused**: its domain is not verified for that connection.
- **A user still reaches a password form after `--on`**: confirm the domain is *verified* (an
  unverified claim does not trigger `require_sso`) and that `oidc` is declared.

## SAML-only identity providers

SAML is **out of scope** (DD-013). An IdP that offers only SAML is bridged with a broker that
terminates SAML and presents OIDC to Dazzle: Keycloak, Auth0 or Entra External ID. The known
cases are RM Unify and UK federation Shibboleth. Create a normal OIDC connection against the
broker's issuer.
