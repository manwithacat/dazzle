# ADR-0033 — CSRF as an Auth-Class-Derived Disposition

**Status:** Accepted 2026-06-03 — **implemented (Phases 1–3)** (#1337). Phase 1 (session-bound token, v0.81.15), Phase 2 (origin-primary admission gate, v0.81.16), Phase 3 (disposition predicate + auditable policy, v0.81.17). Phase 4 governance items deliberately scoped down — see *Deferred*.
**Issue:** #1337 (the 403-on-every-write bug that prompted the rework), follow-on to #1336. Design + 4-phase plan brainstormed with the maintainer: `docs/superpowers/specs/2026-06-03-declarative-csrf-design.md`.
**Relates:** ADR-0028 (guarded transactional actions — the precondition substrate a future CSRF seam could join), ADR-0029 (atomic flows), ADR-0008 (PostgreSQL-only runtime — the server-side session store this binds to). Supersedes the ad-hoc hardcoded-exempt-path-list model that preceded it.

## Context

The pre-rework CSRF middleware was a pure double-submit token check with a hardcoded list of exempt paths/prefixes/regexes. Two consecutive releases shipped a browser-broken /app experience the test suite did not catch (#1336: vendor widget JS never loaded; #1337: **no front-end code attached the `X-CSRF-Token` header**, so every generated-form write 403'd in a real browser — universal, all profiles, masked in CI only because the test clients echo the cookie by hand). The token was also free-floating: a random cookie independent of the auth session, never rotated.

The deeper problem the rework addresses: **CSRF protection was modeled as a token dance bolted onto every request, with exemptions as an inferred-from-absence path list** — opaque, easy to get wrong, and impossible to audit ("what is exempt and why?").

## Decision

**CSRF is a control on *ambient authority*** — the credential the browser attaches automatically (the session cookie). A forged cross-site request "works" only because it rides the victim's cookie. The corollary is the spine of this architecture:

> CSRF is relevant **only** to requests authenticated by an ambient credential. A request authenticated by a credential the caller must *explicitly present* — a Bearer token, an HMAC webhook signature, an OAuth `state` nonce — is structurally immune, and CSRF is categorically **not** its control.

Therefore **CSRF admission is derived from the request's authentication class, not declared per path.** Every state-changing request classifies into a `Disposition`; the disposition decides admission. This dissolves the opt-out-hole risk (there is no `csrf: exempt` attribute to forget or sneak past review) and makes the policy *auditable* — an endpoint is CSRF-protected **iff** it is session-cookie-authenticated.

### The disposition model (Phase 3, `back/runtime/csrf.py`)

Two pure functions, evaluated on the unsafe-method path:

- `csrf_disposition(method, path, headers, config) -> Disposition` — classify. **Default-deny:** anything not positively classified `NA_*` is `PROTECTED_SESSION`.
- `csrf_admits(disposition, headers, host, csrf_cookie, config) -> bool` — admit.

| Disposition | When | Admission |
|---|---|---|
| `PROTECTED_SESSION` | ambient session cookie (the default) | origin-primary gate + session-bound token fallback |
| `NA_BEARER` | `Authorization: Bearer …` | admit — caller-presented credential |
| `NA_SIGNATURE` | HMAC/signature endpoints (webhooks, doc signing) | admit — message-authenticated |
| `NA_PREAUTH` | pre-session / idempotent cookie-setter / infra | admit — `SameSite=Lax` + protocol nonce cover these |
| `UNAUTH_MUTATING` | mutating, no auth at all | *defined, not yet produced at runtime — see Deferred* |
| `ESCAPE_HATCH` | session-authed, explicitly cross-origin-allowed | *defined, not yet produced — see Deferred* |

### The admission gate for `PROTECTED_SESSION` (Phase 2, origin-primary)

1. `Sec-Fetch-Site` present → `same-origin`/`none` admit; `cross-site`/`same-site` reject (unless the `Origin` is in `trusted_origins`).
2. else `Origin` present → admit iff its host authority equals the request `Host` (per-request comparison, so `tenant_host` multi-tenancy works with zero config), or it is trusted.
3. else (no fetch metadata) → fall back to the double-submit token.

A same-origin request admits **without** a token; a provably cross-site/same-site one is rejected **even with** one. Both signals are browser-set and unforgeable cross-site, so this is strictly stronger than token-only — and resilient to the #1337 failure mode (if a render path ever drops the token header again, same-origin writes still admit via the origin signal instead of universally 403'ing).

### The session-bound token (Phase 1)

The token IS the server-side session's own `csrf_secret` (a `sessions.csrf_secret` column, minted with the session), set as the `dazzle_csrf` cookie at every browser-login site and cleared at logout. It rotates on session lifecycle (login/logout) — never per request, so it survives htmx swaps, multi-tab, and the back button. The CSRF middleware defers to a route-set cookie rather than clobbering it with a freshly-minted one (the C1 fix — caught only by composing middleware + route, not by router-only unit tests).

### Auditability (Phase 3, §6)

`render_csrf_policy(config)` enumerates every disposition rule with its rationale into the RBAC compliance report — so an agent or auditor reads *what* is exempt from CSRF and *why*, rather than inferring protection from absence.

## Why this shape (agent-first)

A handler author — human or LLM — **cannot forget CSRF**, because admission is a structural property of crossing the request boundary (the always-on middleware), not handler code. And an agent auditing the catalogue sees every non-protected disposition explicitly, with its auth-class justification, rather than having to prove a negative. This collapses CSRF from "remember the token dance per form" to "the layer derives admission from the request's auth class" — the boring, routine, auditable outcome the rework set out to deliver.

## Deferred (deliberately not built, with rationale)

These were in the original 4-phase plan; investigation during Phase 3–4 found them low-value, redundant, or speculative. Recorded here so the absence is a decision, not an oversight:

- **`<body hx-headers>` transport switch (retire `dz-csrf.js`).** Dropped. `dz-csrf.js` is one central bundled script that echoes the cookie on every htmx request; the swap would have scattered the per-request token across 6+ `Page`-construction sites for marginal benefit, and post-Phase-2 the token is only a fallback leg.
- **Guarded-action seam (wire `csrf_admits` into the ADR-0028/0029 precondition path).** Dropped as redundant — the CSRF middleware already runs on every request including atomic-flow routes, so the "handler can't forget CSRF" goal is already met. `csrf_admits` is nonetheless shaped as a reusable precondition should a non-HTTP invocation path ever need it.
- **Test-harness refactor (stop clients hand-rolling the token).** Dropped — the original motivation was that harnesses masked a *missing* front-end capability; Phases 1 + dz-csrf.js made that capability exist, so the harnesses no longer mask anything.
- **`ESCAPE_HATCH` DSL knob (`csrf: cross_origin_allowed(reason:)`).** Deferred — real grammar/IR/parser work for a genuinely rare case (a session-authed endpoint that must accept cross-origin). The enum value exists; the classifier doesn't produce it. Revisit when a concrete need arises.
- **`UNAUTH_MUTATING` runtime classification.** Deferred — it is a security-sensitive *behavior change* (it would admit unauthenticated mutating POSTs that today hit the gate) plus a design fork (reliable no-session detection in the raw ASGI middleware). The `method` parameter on `csrf_disposition` is already plumbed (currently unread) as the signal it will need.

## Consequences

- The CSRF enforcement boundary is one predicate with one outer call site (the middleware), behavior-equivalent to the prior model (verified by a 585-case differential during the Phase-3 refactor).
- Exemptions are disposition-labeled config (`na_signature_*` for signature endpoints; `exempt_paths`/`exempt_path_prefixes` for pre-auth/idempotent) — typed, not a flat untyped list — and surfaced in the compliance report.
- `regenerate_session_csrf` rotates a session's secret in place (the privilege-change-rotation primitive); it guards the no-match case loudly rather than returning an un-persisted secret.
