# SAML Single Logout (feature A) — Design

**Issue:** #1342 (enterprise auth capability). SAML cluster, feature **A** — the last of
D→C→B→A. **Scope: IdP-initiated SLO only** (chosen 2026-06-08); SP-initiated is a deferred
follow-on.

## Goal

When an org's IdP logs a user out — or deprovisions them and broadcasts a logout — the SP
receives a signed SAML `LogoutRequest` at a new `/auth/saml/sls` endpoint, verifies it, and
**kills that user's app sessions in that org**. This is the enterprise/compliance-critical
half of Single Logout: an IdP-side logout must not leave live app sessions behind.

## Mechanism

SAML SLO front-channel, HTTP-Redirect binding: the IdP redirects the user's browser to the
SP's SingleLogoutService (SLS) URL with a `SAMLRequest` (the `LogoutRequest`) and a
`Signature`. The flow:

1. **Resolve the connection.** Reuse the existing `_resolve_saml_connection(store, request,
   connection_id, domain, host_tid)` — a `?connection=<id>` query param (advertised in the
   SP metadata SLS Location) or the host-pinned tenant's SAML connection. We need the
   connection to get `idp_x509_cert` (to verify) and `tenant_id` (the org to scope the
   kill).
2. **Verify (fail-closed).** `provider.process_logout(connection, request)` wraps
   python3-saml `auth.process_slo(...)`. The SP settings set `security.wantMessagesSigned =
   True`, so an **unsigned or wrong-signature** `LogoutRequest` is rejected — without this,
   anyone could force-logout a user by POSTing their email. python3-saml validates the
   signature against `idp_x509_cert`. On any validation error → 400, no session touched.
3. **Org-scoped session kill.** Extract the NameID (email-format, the enforced default).
   Map it with existing primitives — no schema change:
   `get_user_by_email(nameid)` → `get_memberships_for_identity(user.identity_id)` →
   keep the membership whose `tenant_id == connection.tenant_id` →
   `delete_sessions_for_membership(membership_id)`. This invalidates **all** the user's
   server-side sessions in that org (every browser), not just the current one — the
   server-side `sessions` row is the source of truth, so other browsers' cookies become
   invalid on their next request. (If the user has no membership in that org, or no
   sessions, the kill is a no-op — still respond 200/redirect.)
4. **Respond.** `process_slo` returns the LogoutResponse redirect URL back to the IdP
   (signed with C's SP keypair when request-signing is enabled — additive, reuses the
   existing `sp_cert`/`sp_private_key`). Also clear the current browser's auth + CSRF
   cookies on the redirect response (best-effort for the browser that carried the request).

## Connection resolution & metadata

- The SP must advertise its SLS endpoint so the IdP knows where to send `LogoutRequest`s.
  `_sp_only_settings` / `sp_metadata` gain `sp.singleLogoutService = {url: <SLS>, binding:
  HTTP-Redirect}` so `get_sp_metadata()` emits the `<SingleLogoutService>` element. The SLS
  URL is the app-level `/auth/saml/sls` (host-pinned) — same single-stable-URL pattern as
  the ACS. When a connection is given, the metadata may carry `?connection=<id>` for
  deterministic resolution on multi-connection hosts.
- The IdP's SLO URL (`idp_slo_url`, already captured by feature D's metadata import) is put
  into `idp.singleLogoutService` in the settings so `process_slo` can build the
  LogoutResponse redirect.

## Provider changes (`saml_provider.py`)

- `_slo_settings(connection, request)` — settings for SLO: the existing SP/IdP blocks plus
  `sp.singleLogoutService` (the SLS URL), `idp.singleLogoutService` (`idp_slo_url`),
  `security.wantMessagesSigned = True` (require signed LogoutRequests), and the SP keypair +
  `logoutRequestSigned`/`logoutResponseSigned` when request-signing is on.
- `process_logout(connection, request) -> SamlLogout` — builds the auth object with
  `_slo_settings`, calls `auth.process_slo(keep_local_session=True)` (we do the kill
  ourselves via the membership primitive, not onelogin's per-session callback), checks
  `auth.get_errors()` (raise `ConnectionError` on any), and returns a small result:
  `(name_id: str | None, redirect_url: str | None)`. `keep_local_session=True` because the
  app's session is server-side keyed by membership, not by onelogin's session notion.
- `_sp_only_settings` gains the `sp.singleLogoutService` block (so metadata advertises it).

## Route (`saml_routes.py`)

`GET /auth/saml/sls` (HTTP-Redirect binding; also accept `POST` for IdP POST-binding SLO):

```
1. resolve connection via _resolve_saml_connection (else 400 — no enumeration detail)
2. result = provider.process_logout(connection, request)   # verifies signature; raises on bad
3. if result.name_id:
       user = store.get_user_by_email(result.name_id)
       if user: for m in store.get_memberships_for_identity(user.identity_id):
                    if m.tenant_id == connection.tenant_id:
                        store.delete_sessions_for_membership(m.id)
4. response = RedirectResponse(result.redirect_url) if result.redirect_url else 200
5. clear auth + dazzle_csrf cookies on response (current browser)
```

Capability-gated under `auth.enterprise.saml` (the router only mounts when active — existing
gating, no change). Errors (bad signature, unresolvable connection) → 400 with a generic
message; never reveal whether an email/connection exists.

## Security review lens (model-driven-failure-modes)

- **Forgery / unauthorized logout (the main risk):** `wantMessagesSigned = True` + signature
  verification against the connection's `idp_x509_cert` means only the real org IdP can
  trigger a kill. An unsigned/forged LogoutRequest is rejected before any session is
  touched. This is the load-bearing control — tested explicitly.
- **Cross-org isolation:** the kill is scoped to `connection.tenant_id` — a LogoutRequest on
  org A's connection can only kill org A memberships, even if the NameID's user also belongs
  to org B (`get_memberships_for_identity` is filtered by the connection's tenant). Tested.
- **No new secret / no schema change / no DB-side logic;** behaviour traces from the signed
  request + connection config to the existing session-kill primitive — auditable.
- **DoS / abuse:** a valid signed LogoutRequest only logs out the named user in that org —
  no amplification. Connection resolution failure is a flat 400.

## Testing

- `tests/unit/test_saml_provider.py`: `_slo_settings` sets `wantMessagesSigned`, the
  SLS/IdP-SLO URLs, and the keypair+`logoutResponseSigned` only when signing on;
  `process_logout` raises `ConnectionError` on `get_errors()`; returns `(name_id,
  redirect_url)` on success (onelogin `process_slo` faked via the `_build_auth` seam, as the
  callback tests already do).
- `tests/integration/test_saml_routes.py`: the SLS route end-to-end with a faked provider —
  a valid LogoutRequest kills the user's sessions in the connection's org and NOT another
  org's; a provider error → 400 and **no** session deleted (the fail-closed proof); cookies
  cleared on the response; unresolvable connection → 400.
- `tests/unit/test_saml_metadata.py` (or provider): SP metadata advertises a
  `<SingleLogoutService>` element with the SLS URL.

## Out of scope

- **SP-initiated SLO** (app logout → IdP SLO round-trip) — deferred follow-on; the existing
  local logout is unchanged.
- **SessionIndex-precise logout** — we kill org-scoped (all the user's sessions in the org),
  which is stricter and needs no per-session SessionIndex storage.
- **Back-channel (SOAP) SLO** — front-channel HTTP-Redirect/POST only.
- #1344 boot guard — separate.
