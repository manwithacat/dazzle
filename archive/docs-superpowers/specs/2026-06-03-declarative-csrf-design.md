# Declarative, Auth-Class-Derived CSRF — Design Spec

**Date:** 2026-06-03
**Status:** Approved design — ready for implementation planning
**Author:** Brainstormed with @manwithacat (James Barlow)
**Related:** #1336, #1337 (the stopgap that prompted this), ADR-0028 (guarded
transactional actions), ADR-0029 (atomic flows), ADR-0032 (lifecycle ↔ atomic
seam). New ADR-0033 to be authored in Phase 4.

---

## 1. Motivation

Two consecutive releases (#1336, #1337) shipped with a broken /app browser
experience that the test suite did not catch:

- **#1336** — vendor widget JS (TomSelect, flatpickr) was never loaded on app
  pages, so FK comboboxes rendered inert and required-FK forms were
  unsubmittable.
- **#1337** — once the combobox mounted, every generated-form write 403'd
  because **no front-end code attached the `X-CSRF-Token` header**. The CSRF
  middleware is enabled for *every* security profile and 403s any state-changing
  request whose header doesn't echo the `dazzle_csrf` cookie, but nothing on the
  page echoed it. This was universal (all profiles, all roles) and stayed
  invisible because every test client (`htmx_client.py`,
  `rbac/verification_harness.py`, `test_runner.py`, `back/tests/test_e2e.py`)
  echoes the cookie *by hand* — the harnesses compensated for a missing
  front-end capability, so the suite was green while the product was broken in
  every real browser.

#1337 was fixed with a transport-level stopgap (`static/js/dz-csrf.js`,
v0.81.14) that wires a global `htmx:configRequest` cookie→header echo. This spec
defines the *target* architecture that makes CSRF a **boring, routine, and
unforgettable** property of a Dazzle app — and generalizes the testing lesson so
this whole family of "required substrate wiring silently absent" bugs cannot
recur.

### Goals

1. CSRF is a property of the **action declaration / authentication class**, not
   of handler code — a handler author (human or LLM) cannot forget it.
2. The token is **session-bound** and rotated only on login / logout / privilege
   change — never per request.
3. **Sec-Fetch-Site + Origin** is the primary admission gate; the session-bound
   token is the fallback leg for browsers without fetch metadata.
4. Exemptions are **derived from auth class**, not a hand-maintained path list,
   and every non-protected disposition is **auditable** from the RBAC/compliance
   report.
5. The testing strategy is generalized so that any always-on substrate
   capability is verified through the *real rendered page*, not a hand-rolled
   client.

### Non-goals

- Changing the JWT/Bearer API authentication model (already CSRF-safe by
  construction).
- Supporting browsers without `Sec-Fetch-Site` as anything more than the
  token-fallback path (Safari < 16.4 and older degrade to token-only, still
  safe, never locked out).
- A general user-facing `csrf: exempt` attribute. The only DSL knob is a loud,
  justification-required escape hatch for the rare session-authed-but-must-be-
  cross-origin case (§5).

---

## 2. Established current state (verified 2026-06-03)

- **Token is already session-*stable*** — `CSRFMiddleware` mints a token only
  when the cookie is absent; it never rotates per request. (We were never
  "cursed" on the per-request-rotation axis.) But the `dazzle_csrf` cookie is a
  **free-floating random value independent of the auth session** — never rotated
  on login, logout, or role change.
- **No origin / fetch-metadata gate.** `csrf.py` is pure double-submit token.
- **Session model:** the browser uses **opaque server-side session ids** —
  `SessionRecord` (`back/runtime/auth/models.py`) carries `id`, `user_id`,
  `expires_at`, and `roles`; the auth cookie holds `session.id`
  (`httponly=True`, `SameSite=Lax`). API clients use a **separate JWT/Bearer
  leg**, already CSRF-exempt in the middleware.
- **Exemptions are hardcoded** `exempt_paths` / `exempt_path_prefixes` /
  `exempt_path_regexes` lists in `csrf.py` (health, docs, `/auth/`,
  `/_dazzle/consent`, `/_dazzle/i18n/`, `/webhooks/`, `/sign/…`,
  `/feedbackreports`, `/qa/`, `/__test__/`, `/dazzle/dev/`).
- **Mutating-route surface is heterogeneous:** entity CRUD (`POST`/`PUT`/
  `DELETE` auto-generated in `route_generator.py`), atomic flows (ADR-0029),
  lifecycle transitions (ADR-0032), and user-declared webhook/integration
  endpoints (`integrations.py` models `auth_type: api_key | oauth2 | bearer |
  basic`). There is no single "Action" IR node — every entity mutation is
  *auto*-protected, so the opt-out surface is small by construction.

---

## 3. The organizing principle: CSRF is a control on *ambient authority*

CSRF is possible only because the browser attaches the session cookie
**automatically** — a forged cross-site request rides the victim's cookie
without the attacker knowing it (a confused-deputy attack). The corollary is the
spine of this design:

> **CSRF is only relevant to requests authenticated by an ambient credential
> (the session cookie). Any endpoint authenticated by a credential the caller
> must explicitly present — Bearer token, API key header, HMAC webhook
> signature, OAuth `state` nonce — is structurally immune, and CSRF is
> categorically not its control.**

Therefore CSRF admission is **derived from the request's authentication class**,
not declared per path. This dissolves the opt-out-hole risk: there is no
`csrf: exempt` attribute to forget, fat-finger, or sneak past review. An
endpoint is CSRF-protected **iff** it is session-cookie-authenticated.

---

## 4. Architecture

### 4.1 The disposition predicate

A single pure function, evaluated on the unsafe-method path:

```
csrf_disposition(request) -> Disposition
```

| Disposition | When | Action |
|---|---|---|
| `PROTECTED_SESSION` | ambient session cookie authenticates the request | run the admission gate (§4.2) |
| `NA_BEARER` | `Authorization: Bearer …` | admit — caller-presented credential, CSRF N/A |
| `NA_SIGNATURE` | webhook/integration HMAC/signature, or `/sign` HMAC token | admit — message-authenticated, CSRF N/A |
| `NA_PREAUTH` | no session yet (login, OAuth init/callback, consent/i18n cookie-setters) | admit — `SameSite=Lax` + protocol nonce (OAuth `state`) cover these |
| `UNAUTH_MUTATING` | mutating endpoint with **no** auth at all | admit, but **flag for audit** (needs rate-limit/captcha, not CSRF) |
| `ESCAPE_HATCH(reason)` | session-authed endpoint explicitly declared cross-origin-allowed via the §5 knob | admit, **audited** |

**Default-deny invariant:** any request that cannot be positively classified
into one of the `NA_*` / `UNAUTH` / `ESCAPE_HATCH` buckets falls to
`PROTECTED_SESSION`. A new or unclassifiable endpoint is protected until proven
otherwise — absence of a positive non-protected signal never yields "admit".

### 4.2 The admission gate (only for `PROTECTED_SESSION`)

Origin-primary, token-fallback:

1. **`Sec-Fetch-Site` present** → `same-origin` / `none` ⇒ admit;
   `cross-site` / `same-site` ⇒ reject. (`same-site` = a sibling subdomain;
   reject unless an explicitly configured trusted-origin allowlist says
   otherwise.)
2. **else `Origin` present** → equals the app's own origin ⇒ admit; else reject.
3. **else** (no fetch-metadata, no `Origin` — legacy/edge clients) → require the
   session-bound token (§4.3) to match.

This posture is not only modern (OWASP lists fetch-metadata as a robust primary
defense) but **more resilient to the #1337 failure mode**: if a render path ever
omits the token header again, same-origin writes still admit via step 1/2
instead of universally 403'ing. The token is the safety net, not the hot path.

### 4.3 Session-bound token

- Add `csrf_secret: str` to `SessionRecord`, minted at session creation with
  `secrets.token_urlsafe(32)`.
- The presented token **is** the stored secret (double-submit). We deliberately
  prefer the stored secret over a stateless `HMAC(server_key, session.id)`: we
  already persist the session row, so rotation is a single-field update and
  there is no server-key-rotation concern.
- **Rotation = session rotation.** The secret is reissued on login, logout, and
  **privilege change**. `SessionRecord` already carries `roles`, so "roles
  changed ⇒ mint a new secret + reset the cookie" is a localized rule. This is
  *narrower* than today, where the cookie never rotates and outlives login/
  logout.
- The `dazzle_csrf` cookie becomes **derived from the session** (set to
  `session.csrf_secret` at login), not an independent random value.
  Anonymous/pre-session requests get **no** CSRF cookie — they are all
  `NA_PREAUTH` by disposition and need none.

### 4.4 Browser transport: `<body hx-headers>`, retire `dz-csrf.js`

Because the token is now known at render time (it is on the session), the shell
renderer injects it declaratively:

```html
<body hx-headers='{"X-CSRF-Token":"<session.csrf_secret>"}'>
```

htmx inherits `hx-headers` from `<body>` on every request, including swapped
fragments (the body element persists across idiomorph morphs). A session-stable
token + body-inheritance is the "boring" combination: it survives swaps,
multi-tab, and the back button with no JS. This **deletes `dz-csrf.js`** (the
v0.81.14 stopgap) — no cookie-read, no `configRequest` hook. Since the token is
now only the fallback leg, the transport being declarative-and-simple is safe.

### 4.5 Middleware ↔ guarded-action seam

Refactor the decision out of the ASGI middleware into two pure functions:

```
csrf_disposition(request) -> Disposition      # classification (§4.1)
csrf_admits(request, disposition) -> bool     # the gate (§4.2)
```

Two call sites, one predicate, no divergence:

- The **ASGI `CSRFMiddleware`** keeps calling it as the outer enforcement
  boundary (defense in depth; uniform across every route).
- The **guarded-transactional-action path (ADR-0028/0029)** also consults it as
  one precondition on the unsafe-method step, alongside the existing
  auth/scope/atomic guards. CSRF admission becomes a *structural property of
  crossing the action boundary* — there is no handler-level code in which to
  forget it. This mirrors how scope rules compile once and are enforced at both
  validate-time and runtime.

---

## 5. The escape hatch (the only DSL knob)

A session-authed endpoint that genuinely must accept cross-origin calls is
almost always a design smell. For the rare legitimate case, the *only* opt-out
is a loud, justification-required attribute, e.g.:

```
csrf: cross_origin_allowed(reason: "embedded partner widget at partner.example")
```

This produces an `ESCAPE_HATCH(reason)` disposition, which is rendered as an
explicit finding in the compliance report (§6). There is no plain
`csrf: exempt`; webhooks/callbacks never need one because they derive `NA_*`.

---

## 6. Audit: fold disposition into the RBAC/compliance report

A static analyzer enumerates every mutating route, runs the same
`csrf_disposition` predicate against its declared auth class, and emits a CSRF
section into `rbac/report.py::generate_report` (alongside the permit/scope
matrix). Of the six dispositions, two get **active findings** in
`dazzle validate` / `lint`; the rest are inventory:

- `UNAUTH_MUTATING` → finding: "unauthenticated mutating endpoint — CSRF is moot
  but it needs rate-limit/captcha." Forces a human/agent decision rather than
  silent blessing.
- `ESCAPE_HATCH(reason)` → finding: every escape-hatch listed with its required
  justification, so an agent auditing the catalogue sees each hole explicitly.

The deterministic majority (`PROTECTED_SESSION`, `NA_BEARER`, `NA_SIGNATURE`,
`NA_PREAUTH`) renders as inventory, not noise.

### 6.1 Exempt-list migration (delete the hardcoded lists)

Each current `csrf.py` entry maps to a derived disposition, and the mapping *is*
the audit record:

| Today (hardcoded) | Derived disposition |
|---|---|
| `/auth/`, `/_dazzle/consent`, `/_dazzle/i18n/` | `NA_PREAUTH` |
| `/webhooks/`, `/api/v1/webhooks/`, `/sign/…`, `/api/sign/…` | `NA_SIGNATURE` |
| Bearer-auth check (already present) | `NA_BEARER` |
| `/feedbackreports`, `/qa/`, `/__test__/`, `/dazzle/dev/` | re-classified explicitly (test/dev → `NA_PREAUTH` / dev-gated; feedback → reviewed, likely `NA_PREAUTH`) |

No path lists survive in `csrf.py` — disposition is computed. Each re-classified
entry is reviewed once during Phase 3 and its justification recorded.

---

## 7. Testing strategy (the durable generalization)

This answers the question that prompted the whole exercise: how to instrument
any vendor/framework JS correctly into the HTMX + SSR substrate **and test that
it works**. #1336 and #1337 both shipped green because the test clients
hand-rolled the missing capability. Three rules apply to *any* always-on
substrate capability (CSRF, a vendor widget runtime, an event-bus shim):

1. **Bundled-capability assertion.** The capability must be present in the
   *shipped artifact* (the dist bundle or `app_chrome.js_scripts`), asserted
   against the built bytes — not a manifest list. A list-level "is it
   referenced" check passes vacuously when the capability is simply absent. Cf.
   `tests/unit/test_csrf_wiring_1337.py`.
2. **Functional-through-the-real-page test.** A browser/E2E test loads a *real
   generated page* and exercises the capability the way a user does — submits a
   form via the actual rendered `hx-headers` + cookie and asserts 200 /
   row-created — with **no hand-rolled wiring**.
3. **Test clients must consume the real transport.** `htmx_client.py`,
   `rbac/verification_harness.py`, `test_runner.py`, and `back/tests/test_e2e.py`
   are refactored to *read the rendered `hx-headers` / cookie from the page*
   rather than manually echoing the token, so they can never again mask an
   absent capability. A harness that compensates for a missing front-end feature
   is a bug in the harness.

Per-disposition middleware contract tests (echo → 200; missing/mismatch → 403;
each `NA_*` admits; `UNAUTH_MUTATING` admits + flags) round out the coverage.

---

## 8. Phasing

Each phase leaves the system shippable and greener than before; the `dz-csrf.js`
stopgap covers the gap until Phase 3 removes it. Phases follow Dazzle's
staged-ship culture (independently landable slices).

- **Phase 1 — Session-bound token.** Add `csrf_secret` to `SessionRecord`; mint
  at session creation; rotate on login / logout / privilege change; derive the
  `dazzle_csrf` cookie from the session. Keep current double-submit semantics.
  Low risk, ships alone. Replaces the free-floating cookie.
- **Phase 2 — Origin-primary gate.** Add the `Sec-Fetch-Site` + `Origin`
  admission gate (§4.2) with the session-bound token as fallback. Configurable
  trusted-origin allowlist for the same-site subdomain case.
- **Phase 3 — Derivation + transport.** Implement `csrf_disposition` (§4.1),
  replace the hardcoded exempt lists with derivation (§6.1), switch the browser
  to `<body hx-headers>` injection, and **retire `dz-csrf.js`**. Refactor the
  middleware to the shared predicate (§4.5).
- **Phase 4 — Audit + guarded-action seam + governance.** Compliance-report CSRF
  section + `validate`/`lint` findings (§6); the `ESCAPE_HATCH` DSL knob (§5);
  consult the predicate from the guarded-transactional-action path (§4.5);
  refactor the test harnesses (§7.3); author **ADR-0033**
  (CSRF-as-derived-from-auth-class).

---

## 9. Risks & open questions for the implementation plan

- **Privilege-change detection point.** Where exactly roles can change
  mid-session (admin role grant, 2FA elevation, impersonation) must be
  enumerated so rotation fires at each. `routes_2fa.py` and any role-grant path
  are candidates.
- **Same-site subdomain policy.** Multi-tenant `tenant_host` deployments (#1289)
  may legitimately span subdomains; the trusted-origin allowlist must integrate
  with the tenant-host resolution rather than hardcoding `same-site = reject`.
- **`NA_SIGNATURE` derivation for user webhooks.** The analyzer must read the
  webhook/integration construct's declared auth to classify it; webhooks with
  *no* declared signature verification should surface as `UNAUTH_MUTATING`, not
  silently `NA`.
- **Pre-auth POST inventory.** Confirm the full set of legitimate pre-session
  POSTs (login, password reset, magic-link, consent, i18n, 2FA challenge) so
  none falls through to `PROTECTED_SESSION` and 403s a logged-out user.
- **GZip/middleware ordering.** The refactored middleware must retain its
  current position relative to `GZipMiddleware` and the auth middleware so the
  session is resolvable when the disposition is computed.
