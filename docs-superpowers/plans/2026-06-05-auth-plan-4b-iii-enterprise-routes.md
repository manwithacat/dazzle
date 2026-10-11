# Auth Plan 4b.iii — Enterprise SSO routes + wiring

> **For agentic workers:** hybrid inline execution + adversarial review (auth route wiring).

**Goal:** Wire the 4a/4b.i/4b.ii pieces into a reachable enterprise-OIDC login flow:
`GET /auth/enterprise/login` (resolve the org's connection → IdP redirect) +
`GET /auth/enterprise/callback` (validate → JIT-join → sign in), register the native
OIDC provider at startup, and ensure `SessionMiddleware` is present.

**Architecture:** The routes mirror the proven `sso_routes.py` (session-fixation regen,
redirect-safety, CSRF-cookie binding) but are simpler — `provision_enterprise_login`
returns the org + membership directly, so there's no org-picker activation. Connection
resolution: `?connection=<id>` · `?email=` (verified-domain routing, anti-hijack) ·
host-pinned tenant. The chosen connection id is stashed in the session so the single
stable callback URL (`/auth/enterprise/callback`) can recover it. Enterprise availability
is gated on the `[sso]` extra (authlib importable) — apps without it are unaffected.

**Tech Stack:** authlib (via the 4b.i provider), the AuthStore session/connection API,
Starlette `SessionMiddleware`, the existing cookie/redirect-safety helpers.

---

## Security properties (must hold — mirror sso_routes)

1. **Session-fixation defence** — regenerate the session id on callback success; delete
   the pre-auth session cookie the client presented.
2. **Redirect safety** — `?next=` runs through `is_safe_redirect_path`; unsafe → `/app`.
3. **No info leak in errors** — `EnterpriseLoginError.reason` → a stable `/login?error=sso_<reason>`
   query code; never the email or secret. Broad exceptions → `sso_failed` (logged, not 500).
4. **Connection must be active OIDC** — a non-active / non-oidc / cross-type connection
   never initiates.
5. **CSRF cookie bound to the new session** — same flags as `sso_routes` (httponly=False so
   htmx can echo it; `cookie_secure` per request).
6. **Anti-hijack inherited** — `?email=` routes via `get_connection_by_verified_domain`
   (verified domains only); the JIT join re-checks the asserted email's domain (4b.ii).

## Task 1: routes module

**Files:** Create `src/dazzle/http/runtime/auth/enterprise_routes.py`,
`tests/integration/test_enterprise_routes.py`.

- `create_enterprise_sso_routes(*, cookie_name="dazzle_session")` → `APIRouter` with
  `enterprise_login` + `enterprise_callback`, plus `_resolve_connection`.
- Tests via `TestClient` + `SessionMiddleware` + a fake auth_store + a registered fake
  provider (mirrors `test_sso_routes`): login redirects to the IdP URL & stashes the
  connection; unknown/inactive connection → `sso_no_connection`; callback success mints a
  session + cookies + regenerates (deletes pre-auth sid); `EnterpriseLoginError` →
  `sso_<reason>`; missing session connection id → `sso_failed`.

## Task 2: subsystem wiring

**Files:** Modify `src/dazzle/http/runtime/subsystems/auth.py`

- Gate enterprise on `find_spec("authlib")`. When global SSO configured OR enterprise
  enabled → add `SessionMiddleware` once (lift it out of the `if configured` block). When
  enterprise enabled → `register_native_oidc()` + mount `create_enterprise_sso_routes()`.

## Task 3: verify + adversarial review + ship

- ruff + mypy + drift gates + mkdocs --strict; **full unit slice** (wiring change → broad slice).
- Adversarial review (silent-failure-hunter) on session-fixation + error-leak + broad-except.
- `/bump patch`, CHANGELOG `### Added` + `### Agent Guidance`, ship.
