# Auth Plan 4b.i — NativeOIDCProvider Implementation Plan

> **For agentic workers:** hybrid inline execution + adversarial review (security-sensitive).

**Goal:** Fill the empty 4a `ConnectionProvider` registry with a native enterprise-OIDC
implementation built on authlib, so per-org enterprise OIDC connections can `initiate`
the IdP login and `callback`-validate the response into an `AssertedIdentity`.

**Architecture:** `NativeOIDCProvider` wraps a per-connection authlib `StarletteOAuth2App`
(built lazily from the connection's `config` issuer/discovery + decrypted `client_secret`).
id_token signature/iss/aud/exp/nonce validation is delegated to authlib's
`authorize_access_token` (discovery `jwks_uri`) — **no hand-rolled token crypto**. The seam
methods become `async` (authlib is async); 4a's registry was empty so this is a clean break.

**Tech Stack:** authlib (`[sso]` extra, lazy import), the 4a `ConnectionRecord`/`AssertedIdentity`/
`ConnectionProvider` seam.

**Scope split:** This slice ships the *provider* + registration + unit tests. The enterprise
routes + org-resolution + JIT membership + group→persona mapping + session activation are
**4b.ii** (the account-takeover-risk identity-join lands there with its own review).

---

## Security properties (must hold)

1. **id_token validation delegated to authlib** — discovery doc `jwks_uri` → authlib verifies
   signature/iss/aud/exp/nonce inside `authorize_access_token`. We never parse the JWT ourselves.
2. **email required + normalized** — empty email → `ConnectionError` (refuse, never assert an
   empty identity). Lowercased + stripped (join key for 4b.ii).
3. **explicit `email_verified: false` → refuse** — parity with global SSO (a missing claim is
   tolerated; an explicit false is not).
4. **client_secret from decrypted `secrets`, never logged** — `ConnectionRecord.__repr__`
   already masks it; the provider never logs the secret or the token.
5. **per-connection client isolation** — memoized by `connection.id`; org A's client never
   carries org B's credentials.
6. **stable single redirect URI** — `{base_url}/auth/enterprise/callback` (one URI the admin
   registers with their IdP); the connection is carried in OAuth `state` (4b.ii wires that).

---

## Task 1: Refine the seam to async

**Files:** Modify `src/dazzle/http/runtime/auth/connections.py`

- Change `ConnectionProvider.initiate`/`callback` to `async def` (registry is empty in 4a —
  no callers break). Update the docstring.

## Task 2: NativeOIDCProvider

**Files:** Create `src/dazzle/http/runtime/auth/oidc_provider.py`

- `NativeOIDCProvider` with `CALLBACK_PATH = "/auth/enterprise/callback"`, lazy per-connection
  authlib client (`_client`), `async initiate` (→ authorize redirect URL str), `async callback`
  (→ `AssertedIdentity`). `_extract_groups` reads `config["groups_claim"]` (default `"groups"`).
- `register_native_oidc()` helper → `register_provider("oidc", "native", NativeOIDCProvider())`.
- Missing `client_id`/discovery → `ConnectionError` (fail-loud config gap — the agent-driven
  doctor in a later slice surfaces this as an actionable runbook).

## Task 3: Unit tests (mock authlib client)

**Files:** Create `tests/unit/test_oidc_provider.py`

- initiate returns the IdP authorize URL; callback maps userinfo→AssertedIdentity (email
  lowercased, groups extracted); empty email raises; `email_verified: false` raises; missing
  config raises; register_native_oidc → resolve_provider returns it.

## Task 4: Verify + adversarial review + ship

- ruff + mypy + drift gates + mkdocs --strict; full unit slice + e2e auth regression.
- Adversarial review (silent-failure-hunter) on the callback path (the validation seam).
- `/bump patch`, CHANGELOG `### Added` + `### Agent Guidance`, ship.
