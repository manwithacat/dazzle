# ADR-0021: Marketing Pages via Sitespec, Not Route Overrides

**Status:** Accepted
**Date:** 2026-04-30
**Supersedes:** none
**Related:** ADR-0011 (SSR + HTMX), ADR-0018 (project-local file writes), [#969](https://github.com/manwithacat/dazzle/issues/969)

## Context

A Dazzle project's public-facing surface (marketing site, legal pages, blog) lives on the same domain as the authenticated app — same hostname, same cookie scope. The framework provides a declarative path for these pages: `sitespec.yaml` declares pages with framework page types (`landing`, `markdown`, `legal`), and `src/dazzle_back/runtime/site_routes.py` registers route handlers that:

- Render the page via `render_site_page("site/page.html", ctx)`
- Resolve auth state via `_resolve_auth(request)` (read-only, never writes cookies)
- Resolve consent state via `_resolve_consent(request)` (read-only)
- Honour CSRF middleware (GETs are exempt; cookie is read-only on safe methods)
- Surface auth-aware nav (logged-in users see "App" link; logged-out see "Sign In")

The framework's site router **never writes to `dazzle_session` cookies** on marketing GETs. This is a load-bearing invariant: a logged-in user can navigate freely between `/about`, `/pricing`, and `/app/dashboard` without the marketing visit affecting their app session.

#969 surfaced a regression class where a downstream project's marketing visits were correlated with subsequent `/app/*` requests returning 403 — symptom of the session being silently invalidated by the marketing pageview. Investigation found the framework code does not produce this behaviour. The cause was a project-side route override that bypassed the framework's site router and introduced custom rendering / cookie / auth logic on marketing paths.

The temptation to use `# dazzle:route-override GET /about` for a marketing page is real:

- Project owns the rendering; sitespec feels constraining
- Project can wire in custom analytics, A/B tests, gated content
- "It's just HTML, why not write it directly?"

But the failure mode is severe: every cookie / header / middleware interaction the framework's site_routes carefully gets right must be re-implemented correctly per route. The class of bugs is not detectable by unit tests on the framework — they only appear in the project's runtime, often under load, often months after deployment.

## Decision

**Marketing pages, legal pages, and any page rendered on the same hostname as the authenticated app must be declared in `sitespec.yaml` using a framework page type.** Custom rendering of a route on the public surface is forbidden unless the route is structurally outside the framework's domain (e.g. a dynamic image generator, a JSON feed endpoint, a redirect target).

Specifically:

| Pattern | Status | Rationale |
|---------|--------|-----------|
| `sitespec.yaml` page with `type: landing` | ✅ Required | Framework owns auth-aware rendering |
| `sitespec.yaml` page with `type: markdown` | ✅ Required | Framework owns markdown processing + section composition |
| `sitespec.yaml` page with `type: legal` (terms, privacy) | ✅ Required | Same as markdown plus legal-specific scaffolding |
| `# dazzle:route-override GET /<marketing-path>` | ❌ Forbidden | Bypasses framework's auth/cookie/CSRF/consent stack |
| `# dazzle:route-override` for app routes (e.g. `/app/<entity>/...`, custom flows) | ✅ Allowed | App routes are project-scoped; route-override is the documented extension point |
| Custom middleware that touches `dazzle_session` | ❌ Forbidden | Only `auth/routes.py` may write the session cookie |
| Custom middleware that touches `dazzle_csrf` | ❌ Forbidden | Only `csrf.py` may write the CSRF cookie |

If the framework's page-type vocabulary is insufficient for a given marketing need (e.g. a dynamic blog index that pulls from external CMS), the right path is to:

1. **File a framework issue** proposing the new page type
2. **Implement it as a framework page type**, not as a project-side override
3. **Add it to `sitespec.yaml`'s schema** so other projects benefit

Project-specific extensions to a framework page type (custom CSS, custom analytics tags, A/B test variants) are wired through:

- `[ui] custom_css = true` for project-specific CSS injected into all pages
- `[analytics]` block in `dazzle.toml` for analytics provider configuration
- Sitespec's `sections` array with `type: markdown` body for custom prose

If neither suffices for a specific page, that's a signal to file a framework issue, not to bypass the site router.

### Why so strict

Three properties of the framework's site router are easy to break in custom rendering:

1. **Cookie discipline.** Framework site_routes never call `set_cookie` / `delete_cookie` on a marketing GET. Custom handlers that do — even unintentionally, e.g. via a third-party FastAPI dependency that emits Set-Cookie in its response — break the invariant.
2. **CSRF middleware compatibility.** The framework's `CSRFMiddleware` reads `dazzle_csrf` and emits a fresh token only when absent. Custom handlers that wrap responses in a `Response()` constructor without preserving inbound headers can drop the framework's Set-Cookie injection.
3. **Auth-aware nav rendering.** Framework site_routes call `_resolve_auth` and pass `is_authenticated` + `dashboard_url` into the page context. Custom handlers that don't replicate this render an inconsistent nav (logged-in user sees "Sign In" button, etc.).

Allowing custom marketing handlers means each project re-litigates these three properties on every page. The framework's site router has been hardened against the failure modes — duplicating that hardening per-project is unsustainable.

## Consequences

### Positive

- One auth-cookie-clearing failure mode (#969-class) eliminated by construction
- Auth-aware nav is consistent across all marketing pages by default
- Consent banner, analytics consent, and CSRF tokens applied uniformly
- Project-side code is smaller — no per-marketing-page handler boilerplate
- Framework can add cross-cutting marketing features (e.g. preview-mode, A/B testing, schema.org JSON-LD) once and have them apply everywhere

### Negative

- Projects with idiosyncratic marketing needs must invest in a framework PR rather than a one-off override
- The `sitespec.yaml` schema must grow over time to cover legitimate page types (current vocab: `landing`, `markdown`, `legal` — likely to add `blog_index`, `feature_compare`, etc.)
- Some early-stage projects may push back on the constraint when their marketing is not yet stable

### Neutral

- App routes (`/app/*`, project-specific flows) remain freely overridable via `# dazzle:route-override` — the constraint targets marketing surfaces only
- Existing project-side route overrides for marketing must be migrated to sitespec entries before 1.0 (cf. project conformance checklist in `docs/guides/marketing-conformance.md`)

## Implementation

The framework's site_routes layer is the source of truth. Drift gates:

- **Conformance checklist** — `docs/guides/marketing-conformance.md` (project-facing)
- **Project layout audit** — projects that use Dazzle should run a pre-1.0 audit of their `routes/` directory and flag any `# dazzle:route-override` on a public path
- **CHANGELOG entry** under "Agent Guidance" when this ADR is added so agents writing project code reference the right pattern

A future framework lint check could scan project `routes/*.py` files for `# dazzle:route-override` directives on paths that overlap the project's `sitespec.yaml` page list — this would mechanically enforce the policy. Filed as a follow-up.

## Alternatives Considered

### 1. Allow custom marketing handlers, document the cookie discipline

**Rejected.** Documentation is read once, missed often. The #969-class failure mode is too severe (silent auth invalidation under load) to leave to project discipline. Mechanical enforcement via "use sitespec or file a framework issue" is the only durable answer.

### 2. Mark custom marketing handlers as "advanced" but allowed

**Rejected.** Same as 1, with extra steps. Anything labelled "advanced" gets used by every project that thinks they're advanced, which is most of them.

### 3. Provide a framework hook (e.g. `register_marketing_renderer`) that lets projects customise without overriding

**Rejected for now.** Adds API surface without proven need. If the sitespec vocabulary turns out to be too narrow for real projects, this is the natural escape hatch — but it should be designed against concrete pain, not in advance. Filed as a future possibility.

## See also

- `docs/guides/marketing-conformance.md` — the project-facing conformance checklist
- `src/dazzle_back/runtime/site_routes.py` — framework site router (source of truth for cookie / auth / consent discipline)
- ADR-0011 — SSR + HTMX (the broader architecture this fits into)
- [#969](https://github.com/manwithacat/dazzle/issues/969) — the regression that surfaced the policy
