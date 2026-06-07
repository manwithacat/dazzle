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
| **SAML** | `dazzle auth connection create-saml --tenant <org> --idp-entity-id … --idp-sso-url … --idp-cert-file …` | ACS URL `<base>/auth/saml/acs`; SP entity id `<base>/auth/saml/acs`; NameID `emailAddress` | `GET /auth/saml/login` |
| **SCIM** | `dazzle auth connection create-scim --tenant <org>` (prints the bearer once) | SCIM base URL `<base>/scim/v2`; header bearer token | `POST /scim/v2/Users` (IdP push) |

Check readiness with `dazzle auth connection doctor <id> [--json]` (exits 0 iff activation-ready).
The `[sso]` extra (authlib + dnspython) covers OIDC/SCIM; **SAML needs the separate `[saml]`
extra** (python3-saml + native `libxmlsec1`).

After any login, the asserted identity is joined to a global Identity by **verified email**, and
a **membership** is created/reused in the connection's org; IdP **groups map to roles** via the
connection's `group_mapping` (**default-deny** — an unmapped group grants nothing).

## SAML conformance matrix

Dazzle is a SAML 2.0 **Service Provider**. All XML parsing + signature validation is delegated
to **python3-saml** (`strict=True`); Dazzle never hand-rolls XML.

| Capability | Support | Notes |
|------------|---------|-------|
| SP-initiated SSO (Redirect → POST) | ✅ | The only supported flow |
| **IdP-initiated / unsolicited SSO** | ❌ **by design** | An ACS POST with no session-stashed AuthnRequest id is **refused**; `rejectUnsolicitedResponsesWithInResponseTo` is on |
| Assertion signature required | ✅ | `wantAssertionsSigned=True`; verified against the connection's IdP cert |
| InResponseTo (replay/injection) | ✅ | The AuthnRequest id is stashed at `initiate` and enforced at the ACS |
| Audience / Conditions / NotOnOrAfter | ✅ | Enforced by python3-saml in strict mode |
| NameID → email | ✅ | `emailAddress` format; or a configured `email_attribute` |
| Group attribute → roles | ✅ | `groups_attribute` (default `groups`) → `group_mapping`, default-deny |
| Encrypted assertions | ❌ | Deferred — assertions must be signed, not encrypted |
| SP metadata endpoint | ✅ | `GET /auth/saml/metadata` serves the SP metadata XML so an IdP can import the ACS URL / entityId / NameID instead of hand-config (#1342) |
| Single Logout (SLO) | ❌ | Deferred |
| SP-signed AuthnRequests | ❌ | Deferred (the Response signature is the trust anchor) |
| IdP metadata auto-import | ❌ | Provide entity id / SSO URL / cert explicitly (`create-saml`) |

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

Because `group_mapping` is keyed by **display name**, renaming a group re-derives its members'
roles from the *new* name. If the new name isn't in `group_mapping`, the mapped role is dropped
for every member (correct — the mapping is now stale — and logged at WARNING). Pair an
IdP-driven group rename with a `group_mapping` update to retain the role.

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

An org admin (a role in `org_admin_roles`) gets an in-app page at `GET /auth/connections`
— mounted only when an enterprise capability is active, fenced to their own org, CSRF-protected.
It is **read + domains only, and deliberately secret-free**: creating connections, rotating
secrets, and revoking a grace window stay in the operator CLI (they involve secret I/O). Per
connection the page shows:

- **Domain lifecycle** — claim a domain, see its DNS-TXT record, and Verify it (the in-app
  counterpart to `add-domain` / `verify-domain`).
- **Activation readiness** — the same diagnosis `dazzle auth connection doctor` reports (shared
  `diagnose_connection`), as ✓/✗ required checks plus a "what's left" list. Presence and
  remedies only — never a secret value.
- **Secret-rotation history** — a read-only view of the `connection_secret_events` audit trail
  (event names + timestamps + a grace-until note), and a "Grace window active until …" badge
  when a SCIM bearer overlap is open. No secret value is rendered.

## Deferred

SAML SLO, encrypted assertions, SP-signed AuthnRequests, IdP-initiated opt-in, IdP-metadata
auto-import.
