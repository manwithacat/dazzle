# SAML SP-initiated Single Logout — Design

**Issue:** #1342 (enterprise auth). The deferred follow-on to feature A (IdP-initiated SLO,
v0.81.95). With this, the SAML cluster's SLO is bidirectional.

## Goal

When a user logs out of a SAML-authenticated Dazzle session, also end their **IdP** session:
the SP sends a signed `LogoutRequest` to the IdP's SLO URL; the IdP logs them out and redirects
the browser back to the SP's `/auth/saml/sls` with a `LogoutResponse`. The local session is always
cleared first (security), so a failed IdP round-trip can never leave a live local session.

## Decisions (from brainstorm, 2026-06-08)

- **Integrate into the generic logout** (one logout button). `/logout` clears the local session +
  cookies as today, then — if the session was SAML-backed with an `idp_slo_url` — redirects the
  browser to the IdP SLO instead of `/`. The SAML resolution lives in a SAML-module helper so
  `routes.py` stays domain-neutral.
- **NameID-only** (org-scoped, no stored SessionIndex) — consistent with feature A; no schema change.
- **Testing: a real-crypto in-process IdP double** (no real IdP infra) is the centerpiece — see below.

## Flow

```
1. user → POST /logout
2. _logout: resolve SAML SLO redirect (helper, BEFORE deleting the session) → url | None
3. _logout: delete local session + clear cookies (always — security)
4. if url:  302 → url   (IdP SLO, carrying the signed SP LogoutRequest)
   else:    existing local-logout redirect ("/" etc.)
5. IdP logs out, 302 → /auth/saml/sls?SAMLResponse=<signed LogoutResponse>
6. SLS: process_logout validates the LogoutResponse signature → land on a logged-out page
```

The local session is gone by step 4, so step 6 is **post-logout cosmetic** — it confirms the IdP
completed and shows a logged-out page. It performs **no session kill** (that's the IdP-initiated
path). Replay/forgery of a `LogoutResponse` is therefore harmless (the user is already logged out).
The response is still signature-validated for hygiene; on validation failure we still land the user
logged-out (never error-out). **InResponseTo replay-pinning on the response is deferred** — the
signature is the trust anchor and the response path is cosmetic; pinning would require carrying the
LogoutRequest id across the local-session clear (a follow-up if ever needed).

## Components

### 1. Provider — `initiate_logout` (`saml_provider.py`)

```python
def initiate_logout(self, connection, request, *, name_id) -> str:
    """Build the SP-initiated LogoutRequest and return the redirect URL to the IdP SLO.
    Requires idp_slo_url (else ConnectionError — caller falls back to local logout). Signs the
    LogoutRequest when request-signing is on (reuses _slo_settings / C's keypair)."""
    settings = self._slo_settings(connection, request)
    auth = self._build_auth(self._request_data(request), settings)
    return auth.logout(name_id=name_id, return_to=self._post_logout_url(request))
```
`auth.logout(...)` returns the IdP SLO URL with a deflated+(optionally signed) `SAMLRequest`.
`_slo_settings` already provides `idp.singleLogoutService` (from `idp_slo_url`) + `wantMessagesSigned`
+ logoutRequestSigned/keypair. Guard: if no `idp_slo_url`, raise so the caller stays local-only.

### 2. SAML-module helper — `saml_slo_redirect_url` (`saml_routes.py` or a small `saml_logout.py`)

```python
def saml_slo_redirect_url(store, request, *, session_id) -> str | None:
    """If session_id belongs to a SAML SSO session whose connection has SLO configured, return
    the IdP SLO redirect (signed LogoutRequest); else None. Called by the generic logout BEFORE
    it deletes the session. Never raises — any failure → None (fall back to local logout)."""
    # session → active_membership → tenant_id → active SAML connection w/ idp_slo_url
    # name_id = the membership identity's email
    # return NativeSAMLProvider().initiate_logout(conn, request, name_id=email)  (try/except → None)
```
Resolution mirrors feature A's kill chain in reverse: `get_session` → `get_membership(active_membership_id)`
→ `get_connections_for_tenant(tenant_id)` pick the active SAML conn with `idp_slo_url` → email via the
identity. Defensive: any missing link / error → `None`.

### 3. Generic logout integration (`routes.py:_logout`)

Before `delete_session`, call the helper; after deleting + clearing cookies, if it returned a URL,
return `RedirectResponse(url, 303)` instead of the local redirect. HTMX/JSON callers: for HTMX use
`HX-Redirect: <url>`; JSON callers get the url in the body (they don't follow redirects, but SP-SLO is
a browser flow — JSON logout stays local). Import the helper lazily from the SAML module so `routes.py`
keeps no SAML dependency at module load.

### 4. SLS handles the returning `LogoutResponse` (`saml_routes.py`)

Mostly already works: `process_logout` calls `process_slo`, which validates a `SAMLResponse` too;
`_logout_request_nameid("")` → None → no kill; redirect/200. Two adjustments:
- Extend the zip-bomb length guard to **`SAMLResponse`** as well as `SAMLRequest`.
- On a `LogoutResponse` (no `name_id`), land on a logged-out page; on a provider error for a
  *response*, still land logged-out (don't 400 a returning user who's already locally logged out) —
  log and redirect. (A 400 stays correct for a malformed/forged inbound `LogoutRequest`, the
  IdP-initiated path.) Distinguish by which param is present (`SAMLRequest` vs `SAMLResponse`).

## Testing — the in-process real-crypto IdP double (centerpiece, no IdP infra)

A reusable test helper `tests/.../saml_idp_double.py`:

```python
class SamlIdpDouble:
    """Acts as the IdP, in-process, with a throwaway RSA keypair — so the SP's REAL process_slo /
    signature validation runs against genuinely-signed messages. No network, no real IdP."""
    def __init__(self, *, entity_id, slo_url): ...        # generates RSA-2048 key + self-signed cert
    @property
    def idp_cert(self) -> str: ...                        # PEM to put in the SP connection's idp_x509_cert
    def signed_logout_request(self, *, name_id, sp_sls_url) -> dict:
        """Redirect-binding query params (SAMLRequest, SigAlg, Signature) for an IdP-initiated
        LogoutRequest, signed via OneLogin_Saml2_Utils.sign_binary(key)."""
    def signed_logout_response(self, *, in_response_to, sp_sls_url) -> dict:
        """Same, for the LogoutResponse (SP-initiated completion)."""
```
Built from python3-saml primitives: `OneLogin_Saml2_Logout_Response.build(...)` /
`OneLogin_Saml2_Logout_Request` XML, `deflate_and_base64_encode`, and **`OneLogin_Saml2_Utils.sign_binary`**
for the Redirect-binding query signature that the SP's `validate_binary_sign` checks. The SP connection
in the test sets `idp_x509_cert = double.idp_cert`, so `process_slo` validates for real.

Two test tiers:
- **Tier 1 — seam fakes (fast):** `initiate_logout` returns a URL (fake `_build_auth`); the generic
  logout redirects to it; the SLS completes on a faked `process_slo`. Covers the wiring/branching.
- **Tier 2 — real crypto (the value):** the IdP double mints a **genuinely-signed** LogoutResponse →
  fed to the SLS → SP's real `process_slo` validates → logged-out page. **A tampered/wrong-cert
  signature → rejected.** And (retro-hardening feature A) a genuinely-signed **LogoutRequest** → SLS
  → real validation → org-scoped kill; an **unsigned/forged** one → rejected, nothing killed. This is
  the first test that exercises the actual SAML signature path end-to-end with zero infra.

`pytest.importorskip("onelogin")` gates Tier 2 (runs in the CI `integration` job where `[saml]` is
installed). Tier 1 runs everywhere.

## Security review lens

- Local logout is **unconditional and first** — SP-SLO never gates it; a broken IdP can't keep a
  session alive.
- The IdP SLO redirect URL is built by python3-saml from operator-configured `idp_slo_url` (not
  attacker input) — no open redirect.
- `name_id` is the session user's own email — the SP can only ask the IdP to log out *this* user.
- The returning `LogoutResponse` performs no privileged action (no kill) → replay-harmless; still
  signature-checked for hygiene.
- The zip-bomb guard now covers `SAMLResponse` too.

## Out of scope

- InResponseTo replay-pinning on the LogoutResponse (deferred — see Flow).
- Back-channel (SOAP) SLO; non-browser/JSON SP-initiated logout (stays local).
- The schools SCIM/SAML streamlining gaps (`dev_docs/2026-06-08-schools-scim-saml-engagement-analysis.md`)
  — separate work, deliberately not bundled here.
