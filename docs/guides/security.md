# Security Guide

Dazzle's layered security model, the framework-vs-app responsibility matrix,
threat walkthrough, honest gaps, and the app-developer security checklist.

**Companion reading:**
[RBAC and access control](../reference/access-control.md) covers the three-layer
RBAC system (static matrix + runtime enforcement + audit trail).
[RBAC verification](../reference/rbac-verification.md) covers the dynamic probe
harness.
This guide covers everything else in the security surface — sessions, CSRF,
secrets management, security headers, PII, dependencies, and deployment
hardening — and establishes which protections the framework provides and
which are your responsibility as the application developer.

---

## 1. Overview and Scope

### The anti-Turing attack-surface constraint

Dazzle's DSL is deliberately anti-Turing: no control flow, no function
definitions, no procedural shortcuts. This is not merely an ergonomics
choice — it is a security property. The framework can enumerate every
(entity, operation, persona) triple at parse time. There are no implicit
routes, no dynamic imports, and no surface-extending escape hatches in the
DSL. The attack surface is determined by the specification, not inferred at
runtime.

`dazzle lint --anti-turing --strict` enforces this property mechanically.

### Three-layer RBAC is one layer

The RBAC system is the most thoroughly documented Dazzle security feature:

- **Layer 1 — Static matrix:** `dazzle rbac matrix` generates the complete
  role × entity × operation grid from the DSL, classified as
  `PERMIT`/`PERMIT_SCOPED`/`DENY` etc. Enforced in
  `src/dazzle/rbac/matrix.py`.
- **Layer 2 — Runtime enforcement:** Every generated CRUD route applies
  `permit:` / `scope:` predicates before touching the database. Verified
  by `dazzle rbac verify` (`src/dazzle/rbac/verifier.py`).
- **Layer 3 — Audit trail:** Every access decision for `audit:`-declared
  entities is written to `_dazzle_audit_log` in PostgreSQL
  (`src/dazzle/http/runtime/audit_log.py`).

See [`../reference/access-control.md`](../reference/access-control.md) and
[`../reference/rbac-verification.md`](../reference/rbac-verification.md) for
the full treatment. This guide does not repeat that material.

### The framework-vs-app split

The spine of this guide is the responsibility matrix in section 2. The
framework handles the infrastructure layer. You, as the app developer, own the
configuration layer. Some things fall in a gap — these are documented honestly
in section 4.

---

## 2. The Responsibility Matrix

Each row names a security concern, states what the framework handles (with the
source location), states what is your responsibility, and calls out any honest
gap.

| Concern | Framework-handled | App-responsibility | Gap / note |
|---|---|---|---|
| **Authentication & sessions** | Session cookie `dazzle_session`: `HttpOnly=true`, `Secure=true` when HTTPS, `SameSite=Lax`. 7-day TTL. PBKDF2-SHA256 password hashing (100 000 iterations, `auth/crypto.py`). JWT minimum secret length enforced (32 bytes, `jwt_auth.py`). | Rotate `DAZZLE_SECRET_KEY` on compromise. Set `AUTH_DATABASE_URL` separate from app DB if required. Choose `session_expires_days` appropriate to your risk profile. | No session fixation defence: login creates a new session but does not invalidate any pre-existing session for the same user. No automatic session rotation on privilege change. |
| **CSRF** | Double-submit cookie pattern: `dazzle_csrf` cookie (HttpOnly=false so JS can read it), `X-CSRF-Token` header required on POST/PUT/DELETE/PATCH. Bearer-authenticated requests are exempt. Enabled on all security profiles. Default exempt list is enumerated in section 3 T3 below — health/docs endpoints, the auth router, webhooks, the `__test__` and `dev` mounts, the QA magic-link route, and idempotent consent/i18n cookie-setters. Source: `src/dazzle/http/runtime/csrf.py`. | App-level state-changing endpoints (e.g. a mounted `POST /graphql`) **must** echo the `dazzle_csrf` cookie back as `X-CSRF-Token` — they are not exempt by default. Use the `csrfFetch` client snippet in section 3 T3. Extend the exempt list via `ServerConfig.csrf_exempt_paths` (#1212) when an endpoint is intentionally Bearer-only or genuinely public. | None — but the default behaviour was previously undocumented; this surfaced as `403 {"detail":"CSRF token missing or invalid"}` on every `POST /graphql` from JS clients that copied the standard GraphQL fetch snippet. |
| **Secrets management** | `env:VAR` indirection in `dazzle.toml` (`src/dazzle/core/manifest.py`) — database URL and OAuth credentials are never committed. DB URL masked in `/_dazzle/db-info` response (`subsystems/system_routes.py`). JWT secret auto-generated if not provided; minimum length 32 bytes enforced at startup. | Provide `DAZZLE_SECRET_KEY` as a strong random string (≥ 32 bytes) in production. Keep all secrets in your deployment platform's secret store, not in committed config files. | No framework-level secret redaction in log lines or error responses beyond the DB URL mask. A secret that appears in structured logging (e.g. via a misconfigured integration) will not be scrubbed. |
| **Audit trail** | `AuditLogger` (`src/dazzle/http/runtime/audit_log.py`) writes every access-control decision (allow and deny, with policy match, user, IP, path, latency) to `_dazzle_audit_log` in PostgreSQL. Bounded async queue (default max 10 000 entries). Fail-closed on startup: server refuses to boot with audited entities and no `DATABASE_URL`. Queryable via `/_dazzle/audit/logs` (admin auth required). | Declare `audit:` on every entity that requires a durable access trail. Set a retention policy and archive/purge on a schedule appropriate to your compliance requirements. | `_dazzle_audit_log` is a regular PostgreSQL table — no append-only constraint, no signing. Opt-in tamper-evident hash chain available via `audit_integrity = "hash_chain"` in `ServerConfig` (#1197): each row's `row_hash = sha256(prev_hash || canonical_payload)` so a tampered row breaks the chain at that entry, and `AuditLogger.verify_chain()` reports the first mismatch. Default (`"none"`) leaves schema and write path byte-identical to pre-#1197 behaviour. The chain provides tamper evidence, not prevention. |
| **API auth & rate limiting** | Rate-limit config per security profile (`src/dazzle/http/runtime/rate_limit.py`): `standard` — auth 10/min, API **300/min**; `strict` — auth 5/min, API 30/min; `basic` — none. Generated **entity API routes** are auto-wrapped at the profile's `api_limit` (since #1196), as are the auth routes (login, register, forgot/reset password, 2FA verify) and file upload endpoints. Per-user keyed (XFF-aware behind trusted proxies, #1296). Uses slowapi; falls back to no-op if not installed. | Install `slowapi` in production (`pip install slowapi`). Tune any single limit per-deploy without changing the profile via `DAZZLE_RATE_LIMIT_API` / `_AUTH` / `_UPLOAD` / `_2FA` (e.g. `DAZZLE_RATE_LIMIT_API=600/minute`) — keeps CSP/HSTS/auth intact (#1298). Behind a proxy set `DAZZLE_RATE_LIMIT_TRUSTED_PROXIES` (#1296). | The uniform profile `api_limit` is applied to every generated entity route — the per-entity `rate_limit:` DSL field is still **not** consumed (no per-entity tuning via DSL). Workspace SSR **page** routes and custom `service:` routes are not auto-wrapped; protect those at the load balancer / API gateway. |
| **Security headers & transport** | `src/dazzle/http/runtime/security_middleware.py` — `X-Frame-Options: DENY` (standard/strict), `X-Content-Type-Options: nosniff` (standard/strict), `Referrer-Policy: strict-origin-when-cross-origin` (standard/strict), `HSTS` (standard/strict), CSP in report-only mode on `standard`, CSP enforced on `strict`. CORS: wildcard on `basic`, same-origin on `standard`/`strict`. | Set `security_profile: standard` (at minimum) or `strict` in every production `app` block. Configure explicit CORS `allowed_origins` for `standard`/`strict` profiles — the framework leaves this `None` (same-origin only) by default when no origins are specified; if your app serves a separate SPA front-end, this must be set explicitly. Terminate TLS at the load balancer or use a reverse proxy. | CSP in `standard` profile is report-only (`Content-Security-Policy-Report-Only`), not enforced. The template set ships `'unsafe-inline'` on `script-src` and `style-src` because inline `<script>` and `<style>` blocks are still used in base shells; a nonce-based CSP is a follow-up. |
| **PII & data export** | `pii()` field modifier and `classify` construct annotate fields by category (contact, identity, location, financial, health, etc.) and sensitivity. PII-annotated values are stripped from analytics events at runtime (`pii-privacy.md`). Bulk CSV export via `workspace_csv.py` runs through the same `resolve_request_user_context` auth gate as all other workspace routes — `permit:` / `scope:` are checked before any row is fetched. | Annotate PII fields with `pii()`. Gate bulk-export surfaces with `permit:` / `scope:` rules. No export-specific audit trail exists — if you need "who downloaded this export and when", add an `audit:` declaration on the entity, or log the export event in a custom service block. | No export-specific audit event is generated. The audit trail records entity-level read decisions, not "user downloaded CSV". |
| **Input validation & XSS** | Pydantic validates every API request body against generated schemas. The typed Fragment substrate escapes all primitive text content by default at the HTML emission boundary via `dazzle.render.html.esc` (ADR-0023 Pattern A); only explicit `Raw(...)` primitives skip escaping. Query parameters used in HTML attributes are also escaped via `html.escape` in the route generator. | Do not pass user-controlled data into `Raw(...)` primitives, framework-internal `string.Template` Pattern B templates, or custom rendering without sanitisation. Validate business constraints beyond type-checking (e.g. enum ranges, numeric bounds) in service blocks. | No server-side input schema validation beyond what Pydantic derives from the DSL IR types. Custom service blocks that accept free-form input must validate it themselves. |
| **Dependencies & supply chain** | `pip-audit` runs in CI (`ci.yml` step "Run pip-audit (informational)"). `pyproject.toml` pins dependency ranges. | Pin exact versions in production deployments. Review `pip-audit` output on every merge. | `pip-audit` runs with `continue-on-error: true` and `|| true` — a vulnerable dependency does **not** fail the build. No hard fail on critical/high severity. |
| **Deployment hardening** | The framework exposes no privileged management surface beyond `/_dazzle/audit/*` (admin-auth required) and `/_diagnostics` (admin role required). The `/_dazzle/entity/*` and `/_dazzle/tables` debug endpoints are unconditionally registered — they are not removed in production. | Block `/_dazzle/entity/*`, `/_dazzle/tables`, `/_dazzle/spec`, and `/spec` at your load balancer or ingress in production (keep `/health`, `/_dazzle/health`, `/_dazzle/live`, `/_dazzle/ready` accessible). See [Observability guide](observability.md) section 1 for the full endpoint inventory. Provide `DATABASE_URL` and `AUTH_DATABASE_URL` over TLS. Use a PostgreSQL user with least privilege. | No framework-managed network policy or secret rotation. |

---

## 3. Threat Walkthrough

### T1: Session hijacking

**Scenario:** An attacker intercepts a session cookie (via network sniff or
cross-site script) and replays it to the API.

**Dazzle's mitigation:** The `dazzle_session` cookie is `HttpOnly=true`
(inaccessible to JavaScript on the page) and `Secure=true` when the request
arrives over HTTPS (determined per-request in `auth/crypto.py:cookie_secure`).
`SameSite=Lax` prevents the cookie from being sent with cross-site navigations
that carry side effects.

**Residual risk:** If TLS is not terminated before Dazzle receives the request,
the cookie is transmitted in plaintext. If the app is served over HTTP in
production (`DAZZLE_ENV != https`, no `X-Forwarded-Proto: https` header set by
a proxy), the `Secure` flag is omitted. Ensure TLS termination is in place
before a Dazzle app serves production traffic.

### T2: Session fixation

**Scenario:** An attacker sets a known session token on the victim's browser
(e.g. by injecting a cookie via a subdomain), then waits for the victim to log
in. After login, the attacker uses the known token.

**Dazzle's mitigation:** Partial. Login creates a fresh session record with a
`secrets.token_urlsafe(32)` ID. However, the login handler does **not**
invalidate any existing session for the same user before creating the new one.
A pre-seeded session ID from before login is not retired on authentication.

**Residual risk:** This is the session-fixation gap noted in section 4. To
mitigate in the interim, call `auth_store.delete_user_sessions(user.id)` in a
custom post-login hook if your threat model requires it.

### T3: CSRF

**Scenario:** An attacker lures a logged-in user to a malicious page that
submits a cross-site form POST to a Dazzle API endpoint.

**Dazzle's mitigation:** `CSRFMiddleware` in `src/dazzle/http/runtime/csrf.py`
requires a matching `X-CSRF-Token` header on all POST/PUT/DELETE/PATCH requests.
The token is set as a non-HttpOnly cookie (`dazzle_csrf`) on the first request;
the browser JS reads it and adds it as a header. A cross-site request cannot
read the cookie from a different origin, so the attacker cannot supply the
matching header. Bearer-authenticated requests are exempt (the Bearer token is
the non-forgeable credential).

**Residual risk:** The CSRF cookie is `SameSite=Lax`, not `Strict`. `Lax` sends
the cookie on top-level navigations (e.g., link clicks that trigger a GET
followed by a redirect to a POST). If your app uses POST-redirect patterns
triggered by external navigations, consider whether `SameSite=Strict` is
appropriate.

**Default exempt list.** The middleware skips its check on a small set of
paths that either (a) cannot carry an authority-escalating side effect, or
(b) are authenticated by a different non-forgeable credential. The current
defaults (read directly from `src/dazzle/http/runtime/csrf.py`):

*Exact paths (`exempt_paths`):*

- `/health` — liveness probe.
- `/docs`, `/openapi.json`, `/redoc` — OpenAPI / Swagger UI.
- `/feedbackreports` — framework feedback ingest.
- `/_dazzle/consent`, `/_dazzle/consent/banner`, `/_dazzle/consent/state` —
  idempotent cookie-setters reachable from anonymous marketing pages that
  do not carry a CSRF token (#868).

*Prefix paths (`exempt_path_prefixes`):*

- `/webhooks/`, `/api/v1/webhooks/` — webhook receivers, authenticated by
  per-provider signature verification.
- `/__test__/` — pytest harness routes (only mounted when test mode is on).
- `/dazzle/dev/` — dev control plane (gated by `enable_dev_mode`).
- `/auth/` — login/logout/register; CSRF is not the right primitive here
  (sessions don't exist yet at login time).
- `/feedbackreports/`.
- `/qa/` — QA magic-link generator (#768), triple-gated by env flags +
  mount-time + request-time checks.
- `/_dazzle/i18n/` — locale-switcher cookie endpoint (#955); writes the
  `dz_locale` cookie after validating against the project's
  `supported_locales` allow-list.

Bearer-authenticated requests (`Authorization: Bearer …`) are exempt
regardless of path — the Bearer token is itself non-forgeable.

**GraphQL endpoints are NOT exempt.** If your app mounts `POST /graphql`,
`POST /graphql/v1`, or any equivalent (Strawberry, Ariadne, Graphene, etc.),
the request must carry `X-CSRF-Token`. GraphQL POSTs include mutations and
are state-changing by design; exempting them would defeat the protection on
every framework using GraphQL as its primary write API. The symptom of
missing the token is `403 {"detail":"CSRF token missing or invalid"}` on
every mutation — which is exactly the failure mode that motivated this
documentation (#1212).

**Client pattern.** Your front-end must echo the `dazzle_csrf` cookie back
as the `X-CSRF-Token` header on every state-changing request. The minimal
wrapper:

```js
// csrf-fetch.js
function getCsrfToken() {
  const m = document.cookie.match(/(?:^|; )dazzle_csrf=([^;]+)/);
  return m ? decodeURIComponent(m[1]) : '';
}
async function csrfFetch(url, init = {}) {
  const headers = new Headers(init.headers || {});
  const token = getCsrfToken();
  if (token) headers.set('X-CSRF-Token', token);
  return fetch(url, { ...init, headers, credentials: init.credentials || 'same-origin' });
}
```

Replace every state-changing `fetch(...)` call in your app with
`csrfFetch(...)`. The cookie is set on the first `GET` response, so the
first `csrfFetch` from a fresh page load will already find it.

**Extending the exempt list.** If you mount an internal POST endpoint that
is genuinely public-read or authenticated by Bearer only, declare it via
`ServerConfig.csrf_exempt_paths` (#1212):

```python
from dazzle.http.runtime.server import ServerConfig

config = ServerConfig(
    security_profile="standard",
    csrf_exempt_paths=["/integrations/stripe-webhook-v2"],
)
```

Entries are merged with the framework defaults (duplicates de-duped) before
the `CSRFConfig` is built. This replaces the previous workaround of mutating
`app.state.csrf_config.exempt_paths` after framework boot, which relied on
the middleware closing over the same list — an implementation detail. There
is no env-var path for this knob; downstream apps set it at the
`create_app_factory()` call site.

### T4: Cross-tenant data access

**Scenario:** A user in Tenant A crafts a request that retrieves or modifies
records belonging to Tenant B.

**Dazzle's mitigation:** On `security_profile: strict` with `multi_tenant: true`,
the scope predicate algebra compiles tenant-isolation filters into every
generated query. The FK graph is validated at `dazzle validate` time — a scope
predicate that does not correctly chain to the tenant FK fails validation before
the app boots. The `dazzle rbac verify` harness can probe cross-tenant isolation
empirically.

**Residual risk:** Tenant isolation is enforced by `scope:` predicates you
declare. An entity with no `scope:` rule resolves to `PERMIT_UNPROTECTED` —
globally accessible. The RBAC matrix reports this as a warning; it is not a
hard error. Review the matrix output after every DSL change.

### T5: Audit-log tampering

**Scenario:** An attacker (or an insider with database access) deletes or alters
rows in `_dazzle_audit_log` to cover their tracks.

**Dazzle's mitigation:** The audit log exists and is queryable via
`/_dazzle/audit/logs` (admin auth required). Every access-control decision for
`audit:`-declared entities is written asynchronously. The server refuses to boot
with audited entities when `DATABASE_URL` is absent (fail-closed).

**Residual risk:** `_dazzle_audit_log` is a plain PostgreSQL table. There is no
`SECURITY BARRIER` view, no append-only trigger, and no external log sink. An
attacker with `DELETE` privilege on the table can erase records.

**Opt-in hash chain (#1197):** Set `audit_integrity = "hash_chain"` in
`ServerConfig` to enable a per-row sha256 chain (`row_hash` column). Downstream
apps booting via `create_app_factory()` enable it either via `dazzle.toml`:

```toml
[audit]
integrity = "hash_chain"
```

…or by setting `DAZZLE_AUDIT_INTEGRITY=hash_chain` in the environment (env var
wins over the manifest). The value is validated at config-build time — an
unknown mode (e.g. `"hash-chain"` with a hyphen typo) raises `ValueError`
during boot rather than silently coercing to `"none"` (#1206). Each row's
hash is `sha256(prev_row_hash || canonical_payload).hexdigest()`, so a tampered
row breaks the chain at the modified entry. `AuditLogger.verify_chain()` walks
the table and reports the first mismatch. The default (`"none"`) leaves the
schema and write path byte-identical to pre-#1197 behaviour. The hash chain
provides tamper *evidence*, not tamper *prevention* — an attacker with full DB
write access can still delete the entire table. For tamper-resistant evidence
suitable for SOC 2 / ISO 27001 A.8.15, combine the hash chain with streaming
to an immutable external sink (e.g. CloudWatch Logs, Splunk, BigQuery
append-only table).

### T6: Secret leakage via logs or error messages

**Scenario:** A misconfigured integration credential (API key, webhook secret)
appears in a stack trace or structured log line, and is ingested by a logging
aggregator.

**Dazzle's mitigation:** The database URL is masked in the `/_dazzle/db-info`
response (`_mask_database_url` in `subsystems/system_routes.py`). The
`env:VAR` indirection keeps secrets out of committed config files.

**Residual risk:** There is no framework-level log-redaction filter. If an
integration value read from an environment variable is logged (e.g. in an
exception traceback), it will appear in plaintext. This is the log-redaction
gap in section 4. Use a structured-logging library with a scrubbing filter for
known secret-shaped values, or configure your log aggregator to mask patterns
matching API key formats.

### T7: Vulnerable dependency

**Scenario:** A transitive dependency ships a known CVE (e.g., a remote code
execution vulnerability in a cryptography library or a prototype pollution in a
JS package).

**Dazzle's mitigation:** `pip-audit` runs on every CI push. `pyproject.toml`
uses range pins.

**Residual risk:** `pip-audit` runs with `continue-on-error: true` and
`|| true` — a known vulnerability does not fail the build. The CI step is
informational only. You must review the `pip-audit` output from CI and act on
high/critical findings manually. See section 4 for the tracking issue.

### T8: Bulk-export exfiltration

**Scenario:** An attacker with a low-privilege role triggers a CSV export of
a sensitive workspace region, downloading thousands of records in a single
request.

**Dazzle's mitigation:** The CSV export handler in
`src/dazzle/http/runtime/workspace_region_handler.py` calls
`resolve_request_user_context` before fetching any data — the same `permit:`
and `scope:` auth gate that governs all workspace routes. A role without `read`
permission on the entity cannot reach the CSV path; a scoped role receives only
the rows their scope permits.

**Residual risk:** There is no export-specific rate limit or per-session export
cap. A user with legitimate read access can export all accessible rows as CSV on
every request. There is no audit event specifically recording "user exported CSV
of entity X" — the regular per-row read decisions are recorded if `audit:` is
declared, but there is no aggregate "export" event. Gate bulk-export surfaces
with the narrowest `permit:`/`scope:` rule appropriate to your risk model.

---

## 4. Honest Gaps

These are real limitations. They are not presented as features.

### Gap 1: Rate limiting is partial — uniform profile limit, no per-entity DSL tuning

**Resolved (#1196):** Generated **entity API routes** ARE now auto-wrapped at
the active profile's `api_limit` (`route_generator.py` `_add_route` →
`limits.limiter.limit(limits.api_limit)`). They are per-user keyed and
XFF-aware behind trusted proxies (#1296). The earlier "zero calls to the
rate-limit decorator" statement is obsolete.

**What is wired:** Generated entity CRUD/API routes, auth endpoints (login,
register, forgot/reset password, 2FA verify), and file upload endpoints —
rate-limited at the profile limits when `slowapi` is installed. The `standard`
default is **300/min** (#1298, raised from 60/min which self-429'd SSR pages
that fan out multiple client XHRs). Tune any single limit per-deploy with
`DAZZLE_RATE_LIMIT_{API,AUTH,UPLOAD,2FA}` without changing the profile.

**What is still not:** (a) the per-entity `rate_limit:` DSL field in
`src/dazzle/core/ir/governance.py` is parsed into the IR but **not consumed** —
all entity routes share the one profile `api_limit`, you can't set a stricter
limit on a single hot entity via DSL; (b) workspace SSR **page** routes and
custom `service:` routes you register are not auto-wrapped.

**Mitigation:** For per-entity limits and for page/service routes, apply rate
limits at your load balancer / API gateway. Ensure `slowapi` is installed.

### Gap 2: Audit log has no tamper-resistance affordance

**Source verification:** `_dazzle_audit_log` DDL in `audit_log.py:_init_db`
is a plain `CREATE TABLE IF NOT EXISTS` with no `SECURITY BARRIER`, trigger,
or other integrity mechanism.

**Mitigation while gap is open:** Stream audit log rows to an immutable external
sink as soon as they are written. PostgreSQL's logical replication or a
background `pg_notify` listener are practical integration points.

*(Tracked: #1197)*

### Gap 3: No session fixation defence on login

**Source verification:** `auth/routes.py:_login` calls
`auth_store.create_session()` but does not call `delete_user_sessions()` or
`delete_session()` for any pre-existing session before creating the new one.

**Mitigation while gap is open:** Implement a post-login hook in a custom service
block that calls `auth_store.delete_user_sessions(user.id)` before the new
session is issued. Alternatively, avoid long-lived pre-auth sessions.

*(Tracked: #1198)*

### Gap 4: No framework-level log redaction

**Source verification:** Only the database URL is masked (in
`subsystems/system_routes.py:_mask_database_url`). No general scrubbing filter
exists in the logging pipeline.

**Mitigation while gap is open:** Configure your logging framework to scrub
known secret patterns. For Python's `logging`, a `logging.Filter` that replaces
known-secret-shaped values (API keys, bearer tokens) before records are emitted
is the standard approach.

*(Tracked: #1199)*

### Gap 5: `pip-audit` is CI-informational-only

**Source verification:** `.github/workflows/ci.yml` line 135:
`pip-audit --strict --desc 2>&1 || true` with `continue-on-error: true`.
A known vulnerable dependency does not fail the build.

**Mitigation while gap is open:** Review the `pip-audit` section of your CI
output on every merge. Act on critical/high findings before merging to
production.

*(Tracked: #1200)*

### Gap 6: Field-level security is deliberately absent

Dazzle does not offer per-field access control — this is a design decision, not
a gap in the usual sense. The authorisation surface is the set of
(entity, operation, persona) triples. A field that requires different access
from its sibling fields has a different security lifecycle and belongs in its
own entity with its own `permit:` / `scope:` rules.

**Rationale:** Documented in [ADR-0025](../adr/0025-authorization-is-entity-level.md).
The 2-D role × entity × operation matrix is fully enumerable; field-level
authorisation would expand it to a 3-D tensor, breaking the static-analysis
surface that `dazzle rbac matrix`, `dazzle rbac verify`, and the compliance
evidence mapper all depend on.

---

## 5. App-Developer Security Checklist

Work through this list before deploying to production.

**Security profile**
- [ ] Set `security_profile: standard` or `security_profile: strict` in the
      `app` block. Do not ship `basic` to production — it opens CORS to all
      origins and disables HSTS.
- [ ] If your app serves a separate SPA or API clients from a different origin,
      set `cors_origins` explicitly. The `standard`/`strict` profiles default
      to same-origin only when no origins are configured.

**Secrets**
- [ ] Generate a strong `DAZZLE_SECRET_KEY`:
      `python -c "import secrets; print(secrets.token_urlsafe(48))"` — at
      least 32 bytes; 48 gives ample margin.
- [ ] Store `DAZZLE_SECRET_KEY`, `DATABASE_URL`, `AUTH_DATABASE_URL`, and all
      OAuth / integration credentials in your platform's secret store
      (Heroku Config Vars, AWS Secrets Manager, etc.). Never commit them.
- [ ] Use `env:VAR` indirection in `dazzle.toml` — commit the pointer, not
      the value.

**Authentication**
- [ ] If you enable JWT auth (`jwt_auth`), set `JWT_SECRET` to at least 32
      bytes. The framework enforces this at startup (`MIN_HMAC_SECRET_LENGTH`
      in `jwt_auth.py`), but the enforcement only fires when the secret is
      configured — an absent `JWT_SECRET` may auto-generate an ephemeral one
      that does not survive restart.
- [ ] Consider setting `session_expires_days` to the shortest interval
      acceptable for your use case (default: 7 days).

**Access control**
- [ ] After every DSL change, run `dazzle rbac matrix` and review the diff.
      Any new `ALLOW` on a sensitive entity requires sign-off.
- [ ] Run `dazzle rbac verify` in CI against a staging database to catch
      runtime divergence from the static matrix.
- [ ] Annotate every entity that handles sensitive data with `audit:` so
      access decisions are logged. Set a retention schedule and archive on
      a defined cadence.
- [ ] Verify that bulk-export surfaces carry the narrowest `permit:`/`scope:`
      rule consistent with your use case.
- [ ] Ensure custom POST endpoints carry the CSRF token (or are explicitly
      added to `ServerConfig.csrf_exempt_paths` if intentionally
      Bearer-authenticated or genuinely public). The default exempt list
      does **not** include `/graphql` — wire `csrfFetch` (section 3 T3) into
      every GraphQL client.

**PII**
- [ ] Annotate personal data fields with `pii(category=..., sensitivity=...)`.
      This drives the GDPR ROPA, the privacy page, and analytics PII stripping.
- [ ] Declare `subprocessor` blocks for every third-party that handles
      personal data on your behalf.
- [ ] Review `dazzle compliance compile --framework iso27001` and
      `--framework soc2` output for uncovered controls.

**Dependencies**
- [ ] Pin exact versions in your production `requirements.txt` or
      `pyproject.toml` `[tool.uv.constraints]`.
- [ ] Review `pip-audit` CI output on every merge; act on critical/high
      findings before deploying.

**Deployment**
- [ ] Block `/_dazzle/entity/*`, `/_dazzle/tables`, `/_dazzle/spec`, and
      `/spec` at your load balancer in production.
- [ ] Keep `/_dazzle/health`, `/_dazzle/live`, `/_dazzle/ready`, and `/health`
      accessible (needed for probes and monitoring).
- [ ] Use a PostgreSQL role with `SELECT, INSERT, UPDATE, DELETE` on
      application tables only — no `DROP`, no `TRUNCATE`, no DDL in
      production.
- [ ] Terminate TLS before traffic reaches the Dazzle process so the session
      cookie `Secure` flag is set correctly.

---

## 6. What the Framework Verifies vs. What You Must

### The ASVS test suite

Dazzle ships an OWASP ASVS test suite under `tests/security/`:

| File | ASVS chapter | What it covers |
|---|---|---|
| `test_asvs_v2_authentication.py` | V2 | Password hashing, login error handling, credential management |
| `test_asvs_v3_session.py` | V3 | Session cookie flags, TTL, logout |
| `test_asvs_v4_access_control.py` | V4 | RBAC enforcement, default-deny, scope isolation |
| `test_asvs_v5_validation.py` | V5 | Input validation, Pydantic schema enforcement |
| `test_asvs_v6_cryptography.py` | V6 | PBKDF2 iteration count, JWT secret length |
| `test_asvs_v7_error_handling.py` | V7 | Error response format, stack trace suppression |
| `test_asvs_v8_data_protection.py` | V8 | Audit trail, session data handling |
| `test_asvs_v9_communication.py` | V9 | TLS headers (HSTS), cookie transport |
| `test_asvs_v12_files.py` | V12 | File upload controls, storage isolation |
| `test_asvs_v13_api.py` | V13 | API authentication, content type enforcement |

Run them with `pytest tests/security/ -m "not e2e"`.

### What the ASVS suite and SECURITY_CLAIMS.md cover

The ASVS tests are unit and integration probes against the framework's
infrastructure layer. They verify that:

- The session cookie ships the correct flags.
- The rate-limiter fires on auth endpoints.
- Pydantic rejects malformed request bodies.
- PBKDF2 uses at least 100 000 iterations.
- The RBAC enforcement path correctly returns 403 to an unpermitted role.

The [SECURITY_CLAIMS.md](https://github.com/manwithacat/dazzle/blob/main/SECURITY_CLAIMS.md)
file inventories every security-relevant claim with its maturity rating,
implementation source, and test coverage. It is the reference for a skeptical
evaluator. The [EVALUATION.md](https://github.com/manwithacat/dazzle/blob/main/EVALUATION.md)
guide provides a ~30-minute hands-on walkthrough for verifying the claims.

### What you must verify yourself

The ASVS suite and `SECURITY_CLAIMS.md` do not cover:

- **Business-logic abuse.** Whether a legitimate user can exploit your specific
  workflow to create fraudulent records, approve their own transactions, or
  escalate within your domain's state machines is a function of your DSL design,
  not the framework's infrastructure. Adversarial test coverage for business
  logic must be hand-authored.
- **Architecture-level threats.** Cross-tenant isolation depends on the
  `scope:` predicates you declare. The ASVS tests do not exercise your app's
  specific tenant boundary — `dazzle rbac verify` does, but only against the
  matrix you provide.
- **Deployment posture.** Whether TLS is correctly configured, whether
  `/_dazzle/entity/*` is blocked at your ingress, whether your PostgreSQL
  role has least privilege — these are infrastructure concerns the framework
  cannot verify.
- **Third-party integrations.** `service:` blocks declare contracts with
  external systems. The framework validates the DSL side; it cannot verify the
  external endpoint's security posture.

**The framework reduces the infrastructure attack surface. It does not remove
the need for security review of your application's design.**

---

*Related:
[Access control reference](../reference/access-control.md) ·
[RBAC verification](../reference/rbac-verification.md) ·
[Security profiles](../reference/security-profiles.md) ·
[PII & privacy](../reference/pii-privacy.md) ·
[ADR-0025: Authorization is entity-level](../adr/0025-authorization-is-entity-level.md) ·
[SECURITY_CLAIMS.md](https://github.com/manwithacat/dazzle/blob/main/SECURITY_CLAIMS.md) ·
[EVALUATION.md](https://github.com/manwithacat/dazzle/blob/main/EVALUATION.md) ·
[Agent workflow guide](agent-workflow.md) ·
[Observability guide](observability.md)*
