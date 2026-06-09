# Enterprise SSO & Provisioning (OIDC · SAML · SCIM)

Dazzle ships native, per-org enterprise connections so an org's identity provider (Okta,
Microsoft Entra ID, Google, Ping, …) drives sign-in and user lifecycle. Connections are
**runtime data**, not DSL — created and managed with `dazzle auth connection …`, fenced to
one org, and gated by **domain verification**.

!!! note "Opt-in capability (#1342)"
    Enterprise SSO/SCIM is **off by default**. An app must declare it in `dazzle.toml`
    (`[capabilities] enabled = ["auth.enterprise.oidc", …]`) — or run
    `dazzle capability enable auth.enterprise.oidc` — before any enterprise route or the
    `/auth/connections` admin surface mounts. A greenfield app sees none of this, even if
    the `[sso]`/`[saml]` extras happen to be installed. Capability ids:
    `auth.enterprise.oidc`, `auth.enterprise.saml`, `auth.enterprise.scim`. See the
    capability model in `docs/superpowers/specs/2026-06-06-capability-opt-in-model-design.md`.

    **Cognition (Phase 2):** the agent won't *proactively* suggest enterprise SSO
    while building a simple app. If your spec states the need ("staff sign in via
    Okta"), `bootstrap` surfaces a one-line `dazzle capability enable …` suggestion
    instead of full guidance; once declared, the full `enterprise_sso` pattern is
    pushed. Direct `knowledge` queries always return this content regardless.

## The model

A **`Connection`** is a framework-owned, org-fenced record (`type` = `oidc` / `saml` / `scim`).
Secret material (OIDC `client_secret`, SCIM bearer) is **AES-256-GCM encrypted at rest** under
`DAZZLE_CONNECTION_SECRET`; a SAML IdP signing cert is *public* and lives in plaintext config.

Two anti-hijack controls gate everything:

- **Verified-domain routing** — `?email=` only routes to a connection whose domain is *verified*.
- **Verified-domain provisioning** — an assertion/SCIM push is accepted only for emails whose
  domain the connection has verified. A connection with no verified domains can assert nobody.

Verify a domain with DNS-TXT: `add-domain` → publish the printed `dazzle-verify=…` record →
`verify-domain`. A domain has exactly one verified owner (enforced atomically).

## Setup (per protocol)

| Protocol | Create | IdP configures | Entry point |
|----------|--------|----------------|-------------|
| **OIDC** | `dazzle auth connection create --tenant <org> --issuer … --client-id … --client-secret …` | Redirect URI `<base>/auth/enterprise/callback` | `GET /auth/enterprise/login` |
| **SAML** | `dazzle auth connection create-saml --tenant <org>` + either `--idp-metadata-url <https>` / `--idp-metadata-file <path>` (auto-fills entity id / SSO URL / cert) **or** the explicit `--idp-entity-id … --idp-sso-url … --idp-cert-file …` | ACS URL `<base>/auth/saml/acs`; SP entity id `<base>/auth/saml/acs`; NameID `emailAddress` | `GET /auth/saml/login` |
| **SCIM** | `dazzle auth connection create-scim --tenant <org>` (prints the bearer once) | SCIM base URL `<base>/scim/v2`; header bearer token | `POST /scim/v2/Users` (IdP push) |

Check readiness with `dazzle auth connection doctor <id> [--json]` (exits 0 iff activation-ready).
Add `--probe` for an opt-in **live reachability** check of the IdP endpoints (OIDC discovery doc;
SAML `idp_sso_url`/`idp_slo_url`) on top of the network-free config audit — SSRF-guarded
(https-only, public-IP-only, no redirects), and informational only (it never changes the exit
code, which stays bound to config-readiness). The `[sso]` extra (authlib + dnspython) covers
OIDC/SCIM; **SAML needs the separate `[saml]` extra** (python3-saml + native `libxmlsec1`).

## Admin capabilities (who manages what)

The framework's org-admin surfaces are gated by named **admin capabilities**, so a multi-tenant app
can distinguish a business administrator from an IT/technical admin:

- `manage_members` — invite / list / change-role / remove members (the business administrator).
- `manage_connections` — enterprise-connection CRUD, domain claim/verify, secret rotation, and
  connection security (the IT/technical admin). The `/auth/connections` surface gates on this.

Bind each capability to your DSL personas in the manifest (default-deny, fail-closed):

```toml
[auth]
org_admin_roles = ["org_admin"]        # the default for any capability you don't list below

[auth.admin_capabilities]              # optional
manage_members     = ["business_admin"]
manage_connections = ["it_admin"]
```

If `[auth.admin_capabilities]` is omitted, **every** capability falls back to `org_admin_roles` — so
existing apps are unchanged. A capability you don't list also falls back to `org_admin_roles` (it is
never silently locked out). A persona referenced here that isn't a declared persona logs a boot
warning (it would grant nobody).

After any login, the asserted identity is joined to a global Identity by **verified email**, and
a **membership** is created/reused in the connection's org; IdP **groups map to roles** via the
connection's `group_mapping` (**default-deny** — an unmapped group grants nothing).

## SAML conformance matrix

Dazzle is a SAML 2.0 **Service Provider**. All XML parsing + signature validation is delegated
to **python3-saml** (`strict=True`); Dazzle never hand-rolls XML.

| Capability | Support | Notes |
|------------|---------|-------|
| SP-initiated SSO (Redirect → POST) | ✅ | The default flow |
| **IdP-initiated / unsolicited SSO** | ⚙️ **opt-in** | Off by default. `dazzle auth connection enable-idp-initiated <id>` accepts unsolicited Responses; since there is no session AuthnRequest-id binding, replay is closed by **one-time assertion consumption** (the `saml_consumed_assertions` cache). See *IdP-initiated SSO* below |
| Assertion signature required | ✅ | `wantAssertionsSigned=True`; verified against the connection's IdP cert |
| InResponseTo (replay/injection) | ✅ | SP-initiated: the AuthnRequest id is stashed at `initiate` and enforced (one-time) at the ACS. There is no python3-saml "reject unsolicited" *setting* — replay protection is SP-side (request-id binding for SP-initiated; the assertion cache for IdP-initiated) |
| Audience / Conditions / NotOnOrAfter | ✅ | Enforced by python3-saml in strict mode |
| NameID → email | ✅ | `emailAddress` format; or a configured `email_attribute` |
| Group attribute → roles | ✅ | `groups_attribute` (default `groups`) → `group_mapping`, default-deny. Matches on the group's **name or its IdP `externalId` (GUID)**, so a GUID-keyed mapping works for both the SAML groups claim and SCIM |
| Encrypted assertions | ✅ | `dazzle auth connection enable-assertion-encryption <id>` — accepts `EncryptedAssertion` (per-connection SP keypair, shared with request signing). Once on, a plaintext assertion is rejected |
| SP metadata endpoint | ✅ | `GET /auth/saml/metadata` serves the SP metadata XML so an IdP can import the ACS URL / entityId / NameID instead of hand-config (#1342). `?connection=<id>` includes the connection's SP signing cert when request signing is on |
| Single Logout (SLO) | ✅ | **Bidirectional.** IdP-initiated (`GET /auth/saml/sls`, signature-verified) + SP-initiated (`/logout` redirects to the IdP SLO when an `idp_slo_url` is configured). Sessions are killed org-scoped |
| SP-signed AuthnRequests | ✅ | Per-connection SP keypair via `dazzle auth connection enable-request-signing <id>` (RSA-2048, self-signed; private key encrypted at rest). Re-import `?connection=<id>` metadata at the IdP. The Response signature remains the trust anchor — this is additive |
| IdP metadata auto-import | ✅ | `create-saml --idp-metadata-url <https>` (SSRF-guarded fetch) or `--idp-metadata-file <path>` parses the IdP's metadata into entity id / SSO URL / cert (+ SLO URL); explicit `--idp-*` flags override |

**SP metadata** (`GET /auth/saml/metadata`, public, unauthenticated — IdPs fetch it
anonymously): serves the **default app-level** SP identity (entityId = ACS URL, NameID
`emailAddress`). It contains nothing secret. Two notes: a connection that pins a custom
`sp_entity_id` is not reflected (configure that value IdP-side directly); and the
entityId/ACS URL derive from the request's base URL (Host header) — front SAML
deployments with a trusted-host / canonical base URL so the advertised ACS can't be
Host-spoofed (this applies to the live login/ACS path too, not just metadata).

A malformed or invalid Response never yields a session — it is logged and redirected to
`/login?error=sso_failed`. Error reasons surface as `/login?error=sso_<reason>`
(`no_connection` / `unavailable` / `failed` / `domain_not_verified` / `unverified_fallback` /
`no_membership`).

### IdP-initiated SSO (opt-in)

SAML is SP-initiated only by default — which is itself a replay defense: the ACS enforces that
the Response's `InResponseTo` matches a **one-time** AuthnRequest id stashed in the session at
`initiate`, so a captured Response can't be replayed (the id is consumed on first use).

A connection can opt into accepting **IdP-initiated** (unsolicited) Responses:

```bash
dazzle auth connection enable-idp-initiated <connection-id>     # SAML-only, default-off
dazzle auth connection disable-idp-initiated <connection-id>    # revert
```

Unsolicited Responses have no AuthnRequest, hence no `InResponseTo` binding. So the opt-in path
enforces a different replay defense — **one-time assertion consumption**: each accepted assertion's
id is recorded in `saml_consumed_assertions` (expiring at its `NotOnOrAfter`) with an atomic
insert-or-conflict; a second sighting of the same assertion is refused as a replay. python3-saml
still validates the signature, audience, recipient, and conditions on this path. Only enable this
if your IdP/portal requires IdP-initiated SSO. (Who may flip it maps to the `manage_connections`
[admin capability](#admin-capabilities-who-manages-what); the toggle is CLI-only today.)

## Trust model (why each source is trusted)

The JIT identity-join applies **differential trust** by claims source: an OIDC **id_token** and a
**SAML assertion** are cryptographically validated by their library, so they are trusted directly;
the OIDC **UserInfo-endpoint fallback** is unsigned and additionally requires `email_verified=true`.
The verified-domain anti-hijack applies to *all* sources.

## SCIM lifecycle

A SCIM `User` resource is a **membership**. `active:false` / `DELETE` suspend/remove the
membership **and revoke that org's sessions immediately** (other orgs' sessions survive).

## SCIM Groups (#1342)

`/scim/v2/Groups` is the authoritative path for **group → role** assignment. Groups are
persisted, org-scoped resources with full CRUD + RFC-7644 member PATCH (`add` / `remove`
`members[value eq "id"]` / `replace` / `displayName` rename). A member references a SCIM
`User` (= a membership) by id, and must belong to the connection's org.

A membership's roles are recomputed as `map_groups_to_roles` over the union of **all** its
groups' display names (**default-deny**), so multi-group de-escalation is exact — removing a
user from one group keeps a role still granted by another. The recompute is **org-fenced**: it
only ever touches a membership in the connection's own org, so a SCIM bearer can't perturb
another org's members (member ids are caller-supplied in PATCH `remove`). `GET /Users/{id}`
echoes the membership's group memberships as a read-only `groups` array.

`group_mapping` entries match a group by **either its display name or its IdP `externalId`** (the
stable group GUID, e.g. an Entra group objectId). So a GUID-keyed mapping survives a display-name
rename *and* works for both the SAML groups claim (which carries GUIDs) and SCIM. A name-keyed
mapping still works (Google sends names). Renaming a group re-derives roles; if neither the new name
nor the group's GUID is in `group_mapping`, the mapped role is dropped for every member (correct —
the mapping is now stale — and logged at WARNING).

**SCIM `User` identity is externalId-first.** Provisioning persists the IdP's stable user id
(`externalId`, e.g. an Entra user objectId GUID) on the membership and echoes it back in the User
resource. A re-push under a *changed email* (common in schools) updates the existing membership
instead of forking a duplicate; a `(tenant, externalId)` unique index makes the dedup race-safe. On
an externalId match with a different email the membership is kept and the conflict is logged — the
global identity email is **never** rewritten from a SCIM push (it may be shared across orgs).

**SAML group overage.** When an IdP truncates the groups claim (Entra caps it at 150 groups, emitting
a `…groups.link` overage indicator instead), the provider logs a loud WARNING rather than silently
leaving a member with no group-derived roles.

!!! warning "Clean-break: `User.groups` no longer assigns roles"
    Per RFC 7643, `User.groups` is server-managed/read-only. The `groups` attribute on a
    `User` POST/PUT is now **informational** — it does not add or remove roles. Drive roles
    through `/scim/v2/Groups`. A connection that previously relied on the `User.groups`
    write-path must configure group push to the Groups endpoint.

## SCIM discovery (#1342)

An IdP can self-configure from three bearer-authenticated discovery endpoints (RFC 7643/7644):

| Endpoint | Returns |
|----------|---------|
| `GET /scim/v2/ServiceProviderConfig` | supported features (patch ✅, filter ✅, bulk ❌, …) |
| `GET /scim/v2/ResourceTypes[/{id}]` | the `User` + `Group` resource types (endpoint + schema URN) |
| `GET /scim/v2/Schemas[/{id}]` | the `User` + `Group` schema definitions |

The published schemas are a **faithful subset** — they advertise only the attributes Dazzle
actually honors (`User`: `userName`, `active`, `emails` (readOnly), `groups` (readOnly);
`Group`: `displayName`, `members`), so discovery never promises an attribute the runtime
ignores. A single-fetch `/{id}` for an unknown id returns a SCIM 404.

## Secret rotation (#1342)

Two layers of rotation, both CLI/devops-only (the org-admin UI is deliberately secret-free):

| Command | Rotates |
|---------|---------|
| `dazzle auth connection rotate-secret <id>` | one connection's credential — OIDC `client_secret` (`--client-secret`, never echoed) or a freshly-minted SCIM bearer (printed once). SAML refused. |
| `dazzle auth connection rotate-secret <id> --grace 24h` | **SCIM only** — mints the new bearer but keeps the OLD one valid for the window, so the IdP migrates without a provisioning outage. |
| `dazzle auth connection revoke-previous-secret <id>` | ends a grace window early — the old bearer stops working immediately. |
| `dazzle auth connection secret-history <id>` | the append-only rotation audit trail. |
| `dazzle auth rotate-encryption-key` | the AES master key (`DAZZLE_CONNECTION_SECRET`) — re-wraps every stored secret (and any grace blob) onto the new key with a two-key (`…_OLD`) window. |

**Grace semantics.** Without `--grace`, rotation is a **hard swap** (the old secret dies
immediately — right for a leak). `--grace <m|h|d|w>` is **SCIM-bearer-only**: an OIDC
`client_secret` is arbitrated by the IdP, so Dazzle holding two can't help. The old bearer is
honored only while its window is open — **expiry is enforced at verification time** (an expired
previous bearer is rejected; there's no background reaper). A subsequent hard-swap rotation, or
`revoke-previous-secret`, clears the grace bearer at once.

**Audit.** `rotate-secret`, `revoke-previous-secret`, and the encryption-key rewrap each append
a `connection_secret_events` row (`rotated` / `revoked_previous` / `encryption_key_rewrapped`)
with non-secret detail (connection type, grace flag + expiry) — a secret value is never stored.

## Org-admin surface (`/auth/connections`)

An org admin gets an in-app page at `GET /auth/connections` — mounted only when an enterprise
capability is active, **gated on the `manage_connections` [admin capability](#admin-capabilities-who-manages-what)**,
fenced to their own org, and CSRF-protected. Per connection the page shows:

- **Create a connection** — `?new=oidc|scim|saml` renders a type-specific form; `POST /auth/connections/create`
  creates it. OIDC takes a `client_secret` (encrypted at rest, never echoed); SCIM mints a bearer
  shown **exactly once**; SAML takes the explicit entity-id/SSO-URL/cert or an `idp_metadata_url`
  (SSRF-guarded fetch). OIDC/SCIM creation needs `DAZZLE_CONNECTION_SECRET` set. The org is always
  the caller's active org, never request input.
- **Domain lifecycle** — claim a domain, see its DNS-TXT record, and Verify it (the in-app
  counterpart to `add-domain` / `verify-domain`).
- **Activation readiness** — the same diagnosis `dazzle auth connection doctor` reports (shared
  `diagnose_connection`), as ✓/✗ required checks plus a "what's left" list. Presence and
  remedies only — never a stored secret value.
- **Secret-rotation history** — a read-only view of the `connection_secret_events` audit trail
  (event names + timestamps + a grace-until note), and a "Grace window active until …" badge
  when a SCIM bearer overlap is open. No secret value is rendered.

The read surface stays secret-free: the only secret ever shown is a freshly-minted SCIM bearer, once,
at creation. Secret **rotation** and grace-window revocation remain CLI-only (see *Secret rotation*).

## Live reachability check (`doctor --probe`)

`dazzle auth connection doctor <id>` reports config-readiness (network-free, exit 0 iff ready). Add
`--probe` for an **opt-in** live check of the IdP endpoints — OIDC fetches + validates the discovery
doc; SAML checks `idp_sso_url`/`idp_slo_url` reachability; SCIM is informational (inbound). The fetch
is SSRF-guarded (https-only, public-IP-only, no redirects, size-capped) and informational only — it
never changes the exit code. CLI-only by design (no request-path SSRF surface).

## Status

The #1342 enterprise-auth backlog is **complete**: OIDC + SAML + SCIM connections; SAML SLO
(bidirectional), encrypted assertions, SP-signed AuthnRequests, IdP-metadata import, SP-metadata
endpoint, and IdP-initiated opt-in; SCIM Users + Groups + discovery, externalId dedup, and group→role
by stable id; per-connection secret rotation + encryption-key rotation; case-insensitive identity
email; the in-app org-admin surface; `doctor --probe`; and the admin-capability model. No SSO/SCIM
features remain deferred.
