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
membership **and revoke that org's sessions immediately** (other orgs' sessions survive). Roles
are fully re-synced on every push, including down to zero when a user leaves all mapped groups.

## Deferred

SAML SLO, encrypted assertions, SP-signed AuthnRequests, IdP-initiated opt-in, IdP-metadata
auto-import; the SCIM Groups endpoint + Schemas discovery; connection secret rotation; an in-app
org-admin connection surface.
