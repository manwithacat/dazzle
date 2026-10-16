# DD-013: Enterprise SSO / SCIM connections — parked until a consumer brings a real IdP

```yaml
id: DD-013
status: PARKED
issues: [1342, 1344, 1345]
adrs: [0057, 0044, 0047, 0033, 0003]
decided: 2026-10-15
decided_at_sha: 23cf59372dc91d2636dbde0e6aceb549cd40efd3
parent: flense-programme
```

## One-line intent

Per-org enterprise identity (OIDC and SAML 2.0 sign-in, SCIM 2.0 provisioning,
DNS-verified domains, the connection admin surface and `dazzle auth connection`)
was gated on `[capabilities] enabled = ["auth.enterprise.*"]` in `dazzle.toml`.
No consumer declared the section, and AegisMark's runbook
(`docs/enterprise-auth-enablement.md` in that repo) records the capability as
inert and names go-live as a reviewed architecture change. Flense ship AD
(ADR-0057, operator decision 2026-10-15) removed it: about 7.4k lines of
`src`, 11.6k of tests and the `saml` extra. Social OAuth (`sso_routes`,
`sso_config`, `sso_views`, `social_auth`, Authlib), magic link, member admin,
org activation and the session provider are a different plane and stay.

## Plan (what we already concluded)

Restore from the commit this DD was parked at
(`23cf59372dc91d2636dbde0e6aceb549cd40efd3`, the parent of flense ship AD);
`git show 23cf59372:<path>` returns every file below. The operator guide was
`docs/reference/enterprise-sso.md` at the same commit; its substance is here.

**Gating.** Three capabilities in `dazzle.core.capabilities.registry`:
`auth.enterprise.oidc` (probe `authlib`, extra `sso`), `auth.enterprise.saml`
(probe `onelogin`, extra `saml` = `python3-saml`, needs native `libxmlsec1`),
`auth.enterprise.scim` (no probe, always available once declared). The
registry, `[capabilities]` manifest parsing, `dazzle capability enable|disable`
and the cognition gate (bootstrap / spec-analyze / lint suggest
`dazzle capability enable …` instead of pushing the pattern) were removed in
flense ship AI, since with nothing registered they gated nothing; restore them
from `23cf59372` with the protocol (`core/capabilities/`, `cli/capability.py`,
`CapabilitiesConfig` in `core/manifest.py`). `AuthSubsystem` mounted each route group only
when its capability was active (`_mount_enterprise_capabilities`,
`_mount_enterprise_sso`, `_mount_saml`, `_mount_scim`, `_any_enterprise_active`)
and a boot guard (`auth/capability_guard.py`, #1344) logged loudly when
connection rows existed for a protocol whose capability was off.

**Connection model** (`auth/connections.py`). A `Connection` is framework-owned
runtime data, never DSL: `id, tenant_id, type (oidc | saml | scim | domain),
provider ('native'), domains, verified_domains, config, encrypted_secret,
previous_encrypted_secret, previous_secret_expires_at, group_mapping, status`.
Secrets (OIDC `client_secret`, SCIM bearer, SAML SP private key) were
AES-256-GCM encrypted at rest under `DAZZLE_CONNECTION_SECRET`
(`auth/connection_crypto.py`), with a two-key `…_OLD` window and
`dazzle auth rotate-encryption-key` to rewrap. A provider registry keyed by
`(type, provider)` resolved the native OIDC and SAML providers.

**Domain verification** (`auth/domain_verification.py`). `add-domain` claims a
domain; the admin publishes `dazzle-verify=<HMAC-SHA256(key,
"domain-verify:<conn_id>:<domain>")>` as a TXT record; `verify-domain` checks it
and moves the domain to `verified_domains` under an advisory lock (one verified
owner per domain). Only verified domains route an email to a connection or let
an IdP assert identities: the anti-hijack gate both login and provisioning
depend on. The DNS resolver seam now lives in `tenant/aliases.py` (custom-domain
host aliases use it).

**Login and JIT join** (`enterprise_routes.py`, `enterprise_login.py`,
`sso_session.py`). `GET /auth/enterprise/login` (by `?connection=`, verified
`?email=` domain, or host pin) → IdP → `/auth/enterprise/callback`. The asserted
identity joins a global identity by verified email and gets a membership in the
connection's org; IdP groups map to roles through `group_mapping`, default-deny,
matching a group's name or its IdP `externalId`. Differential trust: id_token
and SAML assertions are trusted as signed; the UserInfo fallback additionally
needs `email_verified=true`. `finish_login_session` was the one place for
session-fixation regeneration and cookie minting. Login errors were
`/login?error=sso_{no_connection,unavailable,domain_not_verified,unverified_fallback,no_membership}`.

**SAML SP** (`saml_provider.py`, `saml_routes.py`, `saml_metadata.py`,
`saml_logout.py`, `saml_sp_keys.py`). All XML parsing and signature checks
delegated to python3-saml in strict mode, never hand-rolled. SP-initiated SSO
with one-time `InResponseTo` binding; opt-in IdP-initiated SSO with a
`saml_consumed_assertions` replay cache; assertion signature, audience and
NotOnOrAfter enforced; NameID or a configured attribute → email; encrypted
assertions and SP-signed AuthnRequests on a per-connection RSA-2048 keypair;
`GET /auth/saml/metadata`; IdP metadata import by URL (SSRF-guarded) or file;
bidirectional SLO (`/auth/saml/sls`, and `/auth/logout` redirecting to the IdP
SLO URL). Entra group-overage claims logged loudly.

**SCIM 2.0** (`scim_routes.py`, `scim_provisioning.py`, `scim_discovery.py`).
Bearer-authenticated `/scim/v2/Users` and `/Groups` with RFC 7644 PATCH, plus
`ServiceProviderConfig`, `ResourceTypes`, `Schemas` publishing only the honoured
attributes. A User is a membership; `active:false` / DELETE suspend or remove it
and kill that org's sessions only. Identity is `externalId`-first
(`memberships.external_id`, unique per tenant) so a re-push under a changed
email updates rather than forks. Groups (`scim_groups`, `scim_group_members`)
own group → role; roles are recomputed over the union of a member's groups,
org-fenced. Bearer rotation with an optional SCIM-only grace window, audited in
`connection_secret_events`.

**Admin surface** (`connection_admin_routes.py`, `connection_admin_views.py`,
`connection_create_form.py`, `connection_doctor.py`, `connection_probe.py`).
`/auth/connections`, gated on the `manage_connections` admin capability
(`auth/admin_policy.py`, removed with it), org-fenced, CSRF-gated: create
OIDC/SCIM/SAML/domain connections, claim and verify domains, readiness
checklist, rotation history; secrets shown once (a minted SCIM bearer) and
never echoed.

**CLI** (`cli/auth_connection.py`): `dazzle auth connection create | create-saml
| create-scim | list | add-domain | show-verification | verify-domain | doctor
[--probe] | rotate-secret [--grace] | revoke-previous-secret | secret-history |
enable/disable-request-signing | enable/disable-assertion-encryption |
enable/disable-idp-initiated | scaffold | delete`, and
`dazzle auth rotate-encryption-key`.

**Schema.** Tables `connections`, `connection_secret_events`, `scim_groups`,
`scim_group_members`, `saml_consumed_assertions`; dropped by Alembic revision
`0023_flense_park_enterprise_auth`, whose `downgrade` holds the exact DDL. Re-add
them with a new revision (ADR-0017), register them in
`dazzle.db.artifact_registry` (ADR-0047) and regenerate
`FRAMEWORK_SCHEMA_SNAPSHOT`. `memberships.external_id` and its unique index
were kept.

**Counter-priors (hold even when forced).**
- Never hand-roll SAML XML or signature validation; python3-saml or an
  equivalent maintained library only.
- Never route or provision on an unverified domain; a connection with no
  verified domains asserts nobody.
- Never let an IdP group grant a role by default; unmapped groups grant nothing.
- Never store or echo a secret in plaintext; never put connections in the DSL.
- Never rewrite a global identity's email from a SCIM push.

## Reopen when (consumer force)

**Operator ruling (James, 2026-10-16):** enterprise auth will be a *core
requirement* of the platform even though no consumer has declared it yet, and
the retired implementation is the starting point for the design discussion, not
a design to restore verbatim. That ruling is a second route to `FORCED`: the
operator may move this DD to `FORCED` with `consumer: platform (core
requirement)` once the **Discussion starter** below is resolved, without the
consumer evidence in items 2 and 3. Until then the status stays `PARKED` and
the `memberships.external_id` drop that plan §10 listed as "open for the
operator" is **off the table** (SCIM identity is `externalId`-first).

1. **Named consumer** — AegisMark (school SSO via Entra ID or Google) is the
   candidate; its runbook `docs/enterprise-auth-enablement.md` already treats
   go-live as a reviewed change. Any consumer qualifies.
2. **Evidence** — the consumer declares `[capabilities] enabled =
   ["auth.enterprise.oidc" | ".saml" | ".scim"]` in `dazzle.toml` **and** has a
   real IdP tenant to test against (not a mock).
3. **Acceptance that unblocks** — in the consumer's CI or staging, a user of a
   verified domain signs in through the real IdP and lands in the right org
   with group-mapped roles; for SCIM, the IdP provisions and deprovisions a user
   and a group end to end.

When a force lands:

1. Set `status: FORCED` and date it.
2. Comment on every linked issue with the consumer + this DD path.
3. Restore the protocol the consumer needs from `23cf59372` (not all three by
   default), with its capability registration, tables (new revision) and
   tests; re-add the `saml` extra only for SAML.
4. When shipped, set `status: DONE` and close issues.

## Discussion starter (2026-10-16)

What flense ship AD removed, as a size: 153 files, 20,757 lines deleted
(about 7.4k `src`, 11.6k `tests`, the 262-line operator guide, the `saml`
extra). `git show 23cf59372:<path>` for any file; `git show --stat 229226a88`
for the list. The largest pieces were `scim_routes.py` (951), `store.py`'s
enterprise mixins (about 1.1k), `cli/auth_connection.py` (841),
`scim_provisioning.py` (617), `saml_provider.py` (492) and the admin surface
(about 1.1k across routes, views, form, doctor, probe).

**Worth keeping as designed** (the parts that encode hard-won judgement):
the `Connection` runtime-data model with org fencing; verified-domain routing
and provisioning as the anti-hijack gate; AES-GCM secrets with the two-key
rotation window; default-deny group → role mapping matched on name or IdP
`externalId`; SAML delegated entirely to python3-saml in strict mode with
one-time `InResponseTo` and the consumed-assertion cache; SCIM identity
`externalId`-first with org-scoped session kill on deprovision;
`finish_login_session` as the single session-minting point. The counter-priors
listed above hold whatever the new shape is.

**Open questions the discussion has to settle before `FORCED`:**

1. *Gating.* The removed code mounted behind `[capabilities] enabled =
   ["auth.enterprise.*"]`, and the capability framework itself went in ship
   AI. If enterprise auth is core, is it gated at all, or does it mount when
   the `[auth.enterprise]` config (or a connection row) exists and the extra
   imports? A core requirement argues for a declared `[auth]` setting a
   consumer writes (DD-014's counter-prior), not a capability registry rebuilt
   for one tenant.
2. *Protocol order.* OIDC first (Entra ID and Google Workspace are both OIDC;
   no native dependency), SCIM second (independent of the sign-in protocol),
   SAML last and only with a customer that cannot do OIDC (python3-saml needs
   `libxmlsec1`, an `Aptfile` on Heroku). Restore one protocol at a time.
3. *Scope boundary with DD-014.* With IdP sign-in, MFA is the IdP's job; local
   two-factor only matters for password accounts. Decide whether "enterprise
   auth" means SSO + SCIM (this DD) or also MFA for non-SSO users (DD-014), and
   whether an org can *require* SSO for its members (the removed code did not).
4. *Admin surface.* `admin_policy.CAPABILITIES` is now `("manage_members",)`;
   `manage_connections` and the `/auth/connections` pages went with ship AD.
   Decide whether connection admin is CLI-only at first (the runbook's
   onboarding is CLI-driven) and the pages come back with the first
   self-service customer.
5. *Tests.* Of the 11.6k test lines, about 3.5k were improve-loop
   `test_scim_*_leftover.py` files (one per SCIM attribute). Restore the
   behaviour tests and the integration doubles (`saml_idp_double.py`); fold the
   leftover files into one parametrised gate (flense ship AX principle: one
   gate per invariant).
6. *Consumer shape.* AegisMark's ADR-0012 (Proposed 2026-06-18) chose the full
   migration onto the framework membership model and its runbook
   (`docs/enterprise-auth-enablement.md`) still describes the two-layer story
   (shared app-level OIDC vs per-org connections) and the Heroku enablement
   steps. It is the design partner for the discussion even without a signed
   customer; cyfuture and pennydreadful have no enterprise identity need.
7. *Schema.* Five tables return by a new Alembic revision from the
   `downgrade` of `0023_flense_park_enterprise_auth`; keep
   `memberships.external_id` and its unique index now (see the ruling above).

## Already shipped (do not re-litigate)

- The code, tests and operator guide at `23cf59372dc91d2636dbde0e6aceb549cd40efd3`
  (the `archive` branch holds retired docs, not this code; use the SHA).
- Kept in the tree: social OAuth via Authlib, magic link, member admin and
  `manage_members`, org activation, global Identity + Organization + fenced
  Membership, `memberships.external_id`, the DNS resolvers (now in
  `tenant/aliases.py`), and the `sso` extra (Authlib + dnspython).

## Explicitly out of scope until force

- WS-Federation, LDAP, Kerberos; SCIM Bulk; just-in-time org creation from an
  IdP; per-connection custom SP entity ids beyond what the restored code had.
- Re-adding a protocol no consumer asked for because the others came back.

## Trail

| Date | Event |
|------|--------|
| 2026-10-15 | Parked (this DD); enterprise auth removed in flense ship AD, tables dropped by `0023_flense_park_enterprise_auth` |
| 2026-10-16 | Operator ruling: enterprise auth is a core requirement without a named consumer; the retired implementation is the discussion starting point; `memberships.external_id` drop withdrawn; **Discussion starter** added |
