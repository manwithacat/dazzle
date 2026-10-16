# Enterprise auth restore — work plan (DD-013, FORCED 2026-10-16)

**Decision record:** `docs/decisions/DD-013-enterprise-sso-scim-connections.md`, *Agreed plan*.
**Source of the retired code:** commit `23cf59372dc91d2636dbde0e6aceb549cd40efd3` (three commits before flense
ship AD `229226a88`; identical to its true parent `ee5a761be` for every enterprise file); `git show 23cf59372:<path>` returns any file, `git show --stat 229226a88`
lists them. **Scope:** OIDC sign-in and SCIM provisioning, per-org connections, verified-domain
routing, `require_sso`. **Not in scope:** SAML in any form (broker route), the capability registry,
the `/auth/connections` pages, `manage_connections`.

## 1. Model placement (AGENTS.md model policy)

| Tier | Work | Why |
|------|------|-----|
| cheapest (Haiku) | EA-0 inventory of the archive: fixed-signature scrape, no judgement | mechanical |
| strong, below session (Opus, worktree) | EA-1 substrate, EA-2 OIDC, EA-3 SCIM | security-bearing restore with design changes (manifest gating, `require_sso`, SAML excision) |
| mid (Sonnet, worktree) | EA-4 CLI + doctor, EA-5 operator guide | prune-and-restore with a clear spec; little new design |
| session (Fable) | harvest, gates, commit, push, EA-6 acceptance pack and the AegisMark hand-off | ship path and final review stay with the session |

Agents in worktrees never commit to `main`, push, bump or tag. They hand back a worktree with
`make ci-fast` green and a report in the house format (what restored, what pruned, what changed from
the archive, evidence, CHANGELOG text under *Unreleased*). The orchestrator cherry-picks, resolves,
records the mass-ratchet exception, runs Tier 0, commits with the agent trailer and pushes under the
push gate (bare, never through `tail`).

## 2. Ships

### EA-0 — Archive inventory (Haiku, read-only, no worktree)
Output `scratchpad/ea0-inventory.md`: every `src/` and `tests/` file ship AD deleted, classified
`oidc | scim | shared-substrate | saml | admin-ui | capability | cli | docs`, with line count, the
public callables each defines, which test file exercises which module, the `store.py` methods by the
same classes, the `subsystems/auth.py` hunk, and every `docs/` and `src/dazzle/mcp/` file at
`23cf59372` that mentions enterprise SSO/SCIM. Feeds the EA-1..EA-5 briefs; the Opus agents may
start before it lands.

### EA-1 — Substrate (Opus, worktree) — **blocks EA-2/3/4**
- `[auth.enterprise]` in `dazzle.toml`: `EnterpriseAuthConfig` on `AuthConfig` in
  `core/manifest.py` with `protocols: list[str] = []` accepting only `oidc` and `scim`; `saml` or an
  unknown name is a manifest validation error naming DD-013. Nothing mounts when the list is empty.
- Restore from `23cf59372`, SAML excised: `auth/connections.py` (`Connection.type` is
  `oidc | scim | domain`; no SP keypair, request-signing, assertion-encryption or IdP-initiated
  fields), `connection_crypto.py`, `domain_verification.py`, `secret_rotation.py`,
  `sso_session.py`, the enterprise half of `auth/store.py` (connection CRUD, verified-domain claim,
  secret rotation and events, `rewrap_all_connection_secrets`, membership `external_id` readers,
  `delete_sessions_for_membership`, SCIM group storage) without `enable/disable_connection_request_signing`,
  `set_connection_idp_initiated`, `record_consumed_assertion`, `_ensure_sp_keypair`,
  `_maybe_remove_sp_keypair`, `enable/disable_connection_assertion_encryption`.
- Boot guard: `capability_guard.py` returns as `auth/enterprise_guard.py` keyed on
  `config.protocols`; a declared protocol whose extra does not import (`authlib` for `oidc`) is a
  boot **error**, and connection rows for an unmounted protocol log at ERROR as before.
- `AuthSubsystem._mount_enterprise(ctx)` reads the config and mounts; EA-2/EA-3 add their routers
  to it. Module-top imports (the deferred-import ratchet).
- Alembic revision `0026_enterprise_auth_oidc_scim` re-creating `connections`,
  `connection_secret_events`, `scim_groups`, `scim_group_members` from the `downgrade` of `0023`
  (not `saml_consumed_assertions`); `dazzle.db.artifact_registry` entries; `FRAMEWORK_SCHEMA_SNAPSHOT`
  regenerated; `docs/reference/db-artifacts.md` regenerated.
- Tests: restore `test_connection_crypto`, `test_domain_verification`, `test_secret_rotation`,
  `test_connections_pg`, `test_domain_connection_verify_pg`, `test_create_domain_connection`,
  `test_domain_connection_routing`, `test_resolve_provider_domain`, `test_connection_provider`
  minus their SAML cases; new tests for the manifest config, the boot error and the guard.
- Baselines: `dazzle inspect api ir-types|public-helpers|runtime-urls --write` as needed, each with a
  CHANGELOG line; `db-artifacts` contract test green.

### EA-2 — OIDC sign-in and `require_sso` (Opus, worktree, after EA-1 lands)
- Restore `oidc_provider.py` (`register_native_oidc`), `enterprise_routes.py`
  (`GET /auth/enterprise/login`, `/auth/enterprise/callback`), `enterprise_login.py` (JIT join by
  verified email, membership in the connection's org, default-deny `group_mapping` matched on group
  name or IdP `externalId`, differential trust: id_token trusted, UserInfo fallback needs
  `email_verified=true`), `finish_login_session` as the single session-minting point, the
  `/login?error=sso_*` codes minus the SAML ones.
- **New:** `require_sso` on the connection (`config.require_sso`, default false, org-fenced). When
  an email's domain resolves to a verified connection with it set, `POST /auth/login`,
  `/auth/login/password`, magic-link request and password reset for that address are refused with a
  redirect to `/auth/enterprise/login?email=…` (JSON callers get `{"status": "sso_required"}`); the
  group mapping is then the only source of roles for those users. Superusers are not exempt.
- Tests: `test_oidc_provider`, `test_enterprise_login`, `tests/integration/test_enterprise_routes`,
  `test_group_map_leftover` folded into a parametrised case set; new `require_sso` tests on every
  refused path and on the JSON shape.

### EA-3 — SCIM 2.0 provisioning (Opus, worktree, after EA-1 lands; parallel with EA-2)
- Restore `scim_routes.py`, `scim_provisioning.py`, `scim_discovery.py`: bearer-authenticated
  `/scim/v2/Users` and `/Groups`, RFC 7644 PATCH, `ServiceProviderConfig`/`ResourceTypes`/`Schemas`
  publishing only honoured attributes, `externalId`-first identity, `active:false`/DELETE suspending
  the membership and killing that org's sessions only, group → role recomputed over the union of a
  member's groups, bearer rotation with the SCIM-only grace window audited in
  `connection_secret_events`.
- Tests: `test_scim_provisioning`, `test_scim_discovery`, `tests/integration/test_scim_routes`;
  the ten `test_scim_*_leftover.py` files become **one** `test_scim_leftover_honest.py` with a
  parametrised table (attribute, junk value, expected stay-put status).

### EA-4 — CLI, doctor and probe (Sonnet, worktree, after EA-1 lands; parallel with EA-2/3)
- Restore `cli/auth_connection.py` without `create-saml`, `enable/disable-request-signing`,
  `enable/disable-assertion-encryption`, `enable/disable-idp-initiated`; keep `create`,
  `create-scim`, `list`, `add-domain`, `show-verification`, `verify-domain`, `doctor [--probe]`,
  `rotate-secret [--grace]`, `revoke-previous-secret`, `secret-history`, `scaffold`, `delete`,
  and `dazzle auth rotate-encryption-key`.
- `connection_doctor.py` (readiness checklist, exit 0 iff activation-ready) and
  `connection_probe.py` (OIDC discovery reachability only; SSRF-guarded, informational).
- Tests: `test_auth_connection_cli` minus SAML, `test_connection_doctor`, `test_connection_probe`,
  `test_rotate_encryption_key_cli`; `docs/reference/cli.md` regenerated.

### EA-5 — Operator guide and KB (Sonnet, worktree, after EA-2/3/4 land)
- `docs/reference/enterprise-auth.md` from the archived `enterprise-sso.md` with every SAML
  section removed and the `[auth.enterprise]` gating, `require_sso` and the broker note for
  SAML-only IdPs written in; AGENTS.md *Specialised references* row; the MCP `knowledge`
  `enterprise_sso` pattern at `23cf59372` restored under the new gating text; CHANGELOG
  *Agent Guidance* bullet.

### EA-6 — Acceptance pack and hand-off (session)
- Against AegisMark's `docs/enterprise-auth-enablement.md` minus its SAML lines: a local app with
  `[auth.enterprise] protocols = ["oidc", "scim"]` boots, `dazzle auth connection create` →
  `add-domain` → `verify-domain` → `doctor` exit 0; the OIDC double signs a verified-domain user into
  the right org with group-mapped roles; `require_sso` refuses the password path; SCIM provisions
  and deprovisions a user and a group end to end. Hand-off to `dev_docs/handoff/` in AegisMark.
- Readiness checklist exposure on the org admin page is a follow-up after EA-6, not before.

## 3. Rules every ship obeys

- **Evidence over memory:** restore from `git show 23cf59372:<path>`; do not retype from the DD.
  Diff the restored file against the archive and list every deliberate change in the report.
- **No SAML symbol anywhere:** no `saml`, `onelogin`, `xmlsec`, `InResponseTo`, `sp_entity_id`
  in `src/` or `tests/`; EA-1 adds a one-line gate for it.
- **Counter-priors in DD-013 hold:** never route or provision on an unverified domain; unmapped
  groups grant nothing; secrets encrypted at rest and shown once; never rewrite a global identity's
  email from a SCIM push; connections are runtime data, never DSL.
- **Ratchets:** the mass ratchet will rise; the orchestrator records each harvest with
  `scripts/mass_ratchet.py --write-baseline --force --reason "DD-013 FORCED (operator 2026-10-16): EA-n"`.
  Deferred-import, dead-definition, complexity and clone ratchets must pass without exceptions.
  API-surface baselines regenerate with `dazzle inspect api <name> --write` plus a CHANGELOG line.
- **Tests:** one behaviour per test; extend a parametrised set before adding a file; integration
  tests that need Postgres read `TEST_DATABASE_URL`.
- **Introspection posture:** any new route that exposes connection state takes the app's auth
  posture (admin dependency), as the `/_dazzle/*` routes do since v0.119.0.

## 4. EA-6 acceptance record (2026-10-16, session)

Scratch copy of `examples/simple_task` with `[auth.enterprise] protocols = ["oidc", "scim"]`,
fresh Postgres database, `dazzle db upgrade head` (0001 → 0026, the four tables present,
no `saml_consumed_assertions`), `sso` extra installed (`authlib`, `cryptography`, `dnspython`).

| Step | Result |
|------|--------|
| `dazzle auth connection create` (Entra issuer, two `--group-map`), `add-domain acme.test` | TXT record printed; domain claimed |
| `doctor --json` before verification / without `authlib` | exit 1, `verified_domain` and `sso_extra` fail (JSON was unparseable and the remedy lost `[sso]` → fixed, `db40394b0`) |
| domain verified (`claim_verified_domain` stands in for DNS; the DNS path is covered by the Postgres tests with a fake resolver), `doctor --json` | exit 0, `ready: true`, 8 checks ok |
| `create-scim`, then share `acme.test` with the SCIM connection | refused by the archive's one-connection-per-domain rule → owner is now the org (`db40394b0`); SCIM `doctor` exit 0 |
| `set-require-sso --on` | flag set; existing verified-domain sessions revoked (`c6838ef49`) |
| app boots with both protocols declared | no boot errors; SCIM and enterprise routes mounted |
| `GET /scim/v2/ServiceProviderConfig` no bearer / bad bearer / good bearer | 401 / 401 / 200 |
| `GET /auth/enterprise/login?email=jane@acme.test` | 303 to the Entra `authorize` endpoint (discovery fetched live, state + nonce set) |
| same for an unverified domain | 303 `/login?error=sso_no_connection` |
| `require_sso`: JSON login, JSON register | 403 `{"status":"sso_required","login_url":…}` |
| `require_sso`: form password login | 303 `/auth/enterprise/login?email=…` |
| another domain's JSON login | 401 (unaffected) |
| SCIM `POST /Users` in the verified domain / outside it | 201 / 400 |
| SCIM group → roles: `externalId`-keyed group POST, name-keyed group PATCH add / remove | roles `["senior_leader"]` → `["senior_leader","teacher"]` → `["senior_leader"]` |
| SCIM `PUT` re-push of the same `externalId` under a changed email | 200, one membership, global email **not** rewritten |
| SCIM `PATCH active:false`, junk `active`, `DELETE` | 200 → `suspended`; 400 stay-put; 204 → row gone |

Not exercised live: the OIDC callback (no IdP double over HTTP; covered by
`tests/integration/test_enterprise_routes.py`), DNS TXT verification (Postgres tests
with a fake resolver), `doctor --probe` against a real issuer.

**Follow-ups recorded, not done:** (1) the IdP group → role map is per connection, so an
org configures it on both its OIDC and its SCIM connection; a shared org-level map would
remove that double entry. (2) SCIM `filter` supports `userName eq` (what Entra and Okta
send) but not `externalId eq`. (3) The readiness checklist on the org admin page
(plan §2 EA-6 note) remains a follow-up. (4) An OIDC login reuses an existing membership
without recomputing roles; SCIM owns recompute. Revisit if a consumer runs OIDC without
SCIM and expects IdP groups to drive roles on every sign-in.

## 5. Log

| Date | Event |
|------|-------|
| 2026-10-16 | Plan written; DD-013 moved to FORCED (`consumer: platform (core requirement)`); EA-0 (Haiku) and EA-1 (Opus) dispatched |
| 2026-10-16 | EA-0 inventory landed; EA-1 harvested `a736301fd`; EA-4 `c1fb6e0a5`; EA-2 `98b144181`; EA-3 `05075459a`; EA-2b (`require_sso` gaps + CLI) `6cc8c1f56`; EA-6 session hardening `c6838ef49`, `87460d497` (runtime-urls lens), `db40394b0` (domain ownership per org, doctor JSON); EA-5 `b864abdb6`. Acceptance record §4. All ships on the tiers §1 planned |
