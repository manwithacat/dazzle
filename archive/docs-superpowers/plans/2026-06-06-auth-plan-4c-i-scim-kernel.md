# Auth Plan 4c.i — SCIM provisioning kernel + bearer auth

> **For agentic workers:** hybrid inline execution + adversarial review (provisioning API).

**Goal:** The security substance of SCIM 2.0 — authenticate an IdP's bearer to its
connection/org, and turn SCIM provisioning intents (create/update, deactivate, deprovision)
into identity + membership state changes, with the **deactivate → suspend + revoke** semantics.
The SCIM REST/JSON-schema endpoints are **4c.ii**.

**Architecture:** `store.get_scim_connection_by_bearer` (constant-time, fail-closed) resolves
the calling IdP to its connection. `scim_provisioning.py` maps intents onto the existing
membership lifecycle (`create_membership`/`suspend_membership`/`reactivate_membership`/
`remove_membership`, all hash-chained) + the new `delete_sessions_for_membership` (multi-org-
correct revocation). The same **anti-hijack** invariant as enterprise OIDC applies: a SCIM
connection may only provision emails within its **verified** domains. Group→role mapping reuses
`enterprise_login.map_groups_to_roles` (default-deny). All ops are scoped to `connection.tenant_id`.

**Tech Stack:** stdlib `hmac` (constant-time bearer compare), the AuthStore membership/session
API, the 4a connection substrate.

---

## Security properties (must hold)

1. **Bearer auth constant-time + fail-closed** — `hmac.compare_digest` against the decrypted
   `secrets['scim_bearer']`; empty token / no stored bearer never matches.
2. **Anti-hijack** — provisioned email's domain ∈ `connection.verified_domains` (a SCIM IdP
   can't provision identities outside the domains it controls). No verified domains → provisions
   nobody.
3. **Deactivate → suspend + revoke** — `active:false` suspends the org membership AND deletes
   its sessions (`delete_sessions_for_membership`), so a deprovisioned user loses access now.
4. **Org-scoped** — every membership lookup/mutation matches `connection.tenant_id`; org A's
   SCIM can't touch org B's memberships. Multi-org sessions for other orgs survive.
5. **Default-deny roles** — unmapped IdP groups grant nothing (reuses `map_groups_to_roles`).

## Task 1: store primitives (done inline)

- `delete_sessions_for_membership(membership_id)` + `get_scim_connection_by_bearer(token)`.

## Task 2: the kernel + tests

**Files:** Create `src/dazzle/http/runtime/auth/scim_provisioning.py`,
`tests/unit/test_scim_provisioning.py`.

- `ScimError(reason, message)`, `ScimResult`, `provision_scim_user`, `set_scim_user_active`,
  `deprovision_scim_user`.
- Tests (fake store): bearer auth match/no-match/empty/constant-time; anti-hijack domain reject;
  create active / create inactive(→suspended); reactivate on active:true; deactivate suspends +
  revokes sessions; role sync; deprovision removes + revokes; org-scoping; idempotency.

## Task 3: PG proof + verify + review + ship

- Real-PG test for `get_scim_connection_by_bearer` + `delete_sessions_for_membership` in
  `tests/integration/test_connections_pg.py`.
- ruff + mypy + drift + mkdocs --strict; full unit slice.
- Adversarial review (silent-failure-hunter) on bearer-auth + anti-hijack + revoke-on-deactivate.
- `/bump patch`, CHANGELOG `### Added` + `### Agent Guidance`, ship.
