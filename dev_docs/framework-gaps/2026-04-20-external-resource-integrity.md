# External Resource Integrity Gap

**Date:** 2026-04-20 (cycle 300 framework_gap_analysis)
**Class:** Framework security / supply-chain
**Status:** Open — needs product-direction decision

## Problem statement

Dazzle's user-facing templates (`base.html`, `site/site_base.html`, `workspace/regions/diagram.html`, `site/auth/2fa_setup.html`) load **executable JavaScript, stylesheets, fonts, and images from public CDNs** without any Subresource Integrity (SRI) protection. The server-side CSP middleware exists and has strict defaults, but **CSP is DISABLED in the default `basic` security profile AND the `standard` profile** — only `strict` turns it on.

This creates a two-layer vulnerability:

1. **SRI absence** — if any of the CDNs (jsdelivr, cdn.tailwindcss.com, fonts.googleapis.com, api.qrserver.com) is compromised, or if DNS/TLS is intercepted between the user and the CDN, attackers can inject arbitrary JavaScript that executes with full-origin privileges on every page that loads the resource. For the highest-risk cases (Tailwind browser JIT, Mermaid, jsdelivr-hosted Dazzle own dist), this is effectively unrestricted XSS.

2. **CSP opt-in burden** — because CSP defaults are OFF in 2 of 3 profiles, the security-conscious defaults coded into `_build_csp_header()` (which would block the external loads above) never actually run. Turning CSP on breaks all the existing pages without coordinated template updates.

Concretely: a Dazzle-back user who sets `security_profile="strict"` today will discover that every rendered page is broken because the default template set violates the built-in CSP. The framework ships with templates and CSP defaults that are **mutually incompatible**.

## Evidence

### External-resource loads in templates (cycle 300 scan)

All found via `grep -rnE "https?://api\.|cdn\.|unpkg\.|googleapis\.|jsdelivr\." src/dazzle_ui/templates/`:

| Template | Line | Resource | Risk | Has SRI? |
|----------|------|----------|------|----------|
| `base.html` | 11 | `fonts.googleapis.com` (preconnect) | Low (Google-operated, stylesheets) | N/A |
| `base.html` | 13 | `fonts.googleapis.com/css2?family=Inter` | Low (stylesheet) | ❌ |
| `base.html` | 24 | `cdn.tailwindcss.com` (Tailwind JIT, JS) | **HIGH** (executable JS) | ❌ |
| `base.html` | 27 | `cdn.jsdelivr.net/gh/manwithacat/dazzle@vX` (own dist) | Medium (vendor-controlled but jsdelivr could mirror a compromised clone) | ❌ |
| `site/site_base.html` | 9 | `fonts.googleapis.com` (preconnect) | Low | N/A |
| `site/site_base.html` | 11 | `fonts.googleapis.com/css2?family=Inter` | Low | ❌ |
| `site/site_base.html` | 18 | `cdn.jsdelivr.net/npm/daisyui@5/daisyui.css` | Low (stylesheet) | ❌ |
| `site/site_base.html` | 19 | `cdn.jsdelivr.net/npm/@tailwindcss/browser@4` (JS) | **HIGH** | ❌ |
| `site/site_base.html` | 21 | `cdn.jsdelivr.net/gh/manwithacat/dazzle@vX` (own dist) | Medium | ❌ |
| `workspace/regions/diagram.html` | 12 | `cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.min.js` | **HIGH** | ❌ |
| `site/auth/2fa_setup.html` | 135 | `api.qrserver.com` (TOTP QR) | **HIGH** (secret exfiltration) | ❌ |

**High-risk loads:** 4 (Tailwind browser JS in both shells, Mermaid, QR service). Of these, the QR service is already filed as issue #829 (cycle 299 EX-054 investigation). The other three are currently undocumented as security concerns.

### CSP configuration gap

`src/dazzle_back/runtime/security_middleware.py`:

```python
# Lines 38, 156-171:
# basic profile:    enable_csp=False
# standard profile: enable_csp=False  # "CSP can break many apps"
# strict profile:   enable_csp=True
```

Default profile (`server.py:107`): `security_profile: str = "basic"`.

Default CSP directives (`security_middleware.py:57-67` when enabled):

```python
{
    "default-src": "'self'",
    "script-src": "'self' 'unsafe-inline'",
    "style-src": "'self' 'unsafe-inline'",
    "img-src": "'self' data: blob:",
    "font-src": "'self'",           # Blocks Google Fonts
    "connect-src": "'self'",
    # ... no external CDN whitelist
}
```

Every template external load violates these defaults. If `strict` profile is enabled (to get CSP), every page breaks.

### SRI absence

`grep -rnE "integrity=" src/dazzle_ui/templates/` → **zero hits.** No template includes SRI hashes. All external loads are trusted blindly.

### Cross-cycle reinforcement

- **EX-054** (cycle 298/299, FILED→#829): api.qrserver.com exfiltration. Individual fix = server-side QR render. Class = external-resource without SRI or CSP pinning.
- **base.html Tailwind JIT** (newly surfaced, cycle 300): Executable JS loaded from `cdn.tailwindcss.com` without SRI. Higher blast radius than EX-054 because it runs on every authenticated page.
- **Mermaid CDN** (newly surfaced, cycle 300): Only loaded when a workspace has a diagram region. Lower blast radius but same class.
- **DaisyUI CSS** (newly surfaced, cycle 300): Lower-risk stylesheet. Cycle 239+ has been migrating Dazzle's own design system away from DaisyUI — the fact that it's still loaded as a CDN dep in `site_base.html` may be legacy.

## Root cause hypothesis

Three overlapping root causes:

1. **No template build pipeline SRI enforcement.** CDN URLs are hand-written in templates. No tooling generates `integrity=` attributes or fails the build when they're missing.

2. **CSP middleware designed for back-end routes, not frontend template asset loading.** The `_build_csp_header()` defaults correctly lock down `font-src`, `script-src`, etc. to `'self'` but the template layer was developed independently and the two pieces never got coordinated integration testing.

3. **"Don't break apps" default priority.** The commit that introduced CSP explicitly marked `enable_csp=False` for `standard` with comment `# CSP can break many apps`. This was a pragmatic choice at the time but the "break" is exactly the signal a user needs that their asset loads aren't SRI-protected. Disabling the feature to avoid the signal hides the gap.

## Fix sketch

Progressive hardening, in order of leverage:

### Phase 1 — add SRI to fixed-version CDN loads (LOW effort, HIGH value)

`jsdelivr` supports `?integrity` helpers that return the current hash. For each fixed-version CDN URL, compute the SHA-384 hash and add `integrity="sha384-<hash>" crossorigin="anonymous"`:

- `base.html:24` — Tailwind CDN
- `base.html:27` + `site_base.html:21` — Dazzle own dist at vX (version-pinned, ideal for SRI)
- `site_base.html:18` — DaisyUI v5
- `site_base.html:19` — @tailwindcss/browser@4
- `diagram.html:12` — Mermaid v11

Scope: ~10 lines of HTML. Doesn't require CSP changes. Immediate defense against CDN compromise.

### Phase 2 — vendor the highest-risk assets

- **Tailwind CDN**: Dazzle already has a CSS build pipeline (`build_css.py`). The CDN is likely a prototype/dev affordance. Switching to the locally-built `dazzle-bundle.css` removes the external load entirely.
- **Dazzle own dist from jsdelivr/gh**: This is strange — Dazzle ships as a Python package; its UI assets should ship via the same package, not via a jsdelivr-of-GitHub URL. PyPI distribution already includes `src/dazzle_ui/runtime/static/`. Migrating to `/static/` self-hosted loads removes the CDN dep entirely.
- **Mermaid**: Harder to vendor (~1MB library). SRI (Phase 1) is the pragmatic fix here.

### Phase 3 — fix the CSP defaults + make strict actually work

- In `_build_csp_header()`, change defaults to whitelist the specific CDN origins needed by the bundled templates (after Phase 2, this list should be near-empty — just whatever still loads externally).
- Enable CSP in the `standard` profile (not just `strict`) once the default template set is CSP-clean.
- Consider `Content-Security-Policy-Report-Only` in `basic` to surface violations without breaking, as an adoption stepping stone.

### Phase 4 — lint rule

Add a template-scan unit test analogous to cycle 284's EX-051 None-vs-default lint: parse every template, extract every `<script src=` and `<link href=` with absolute URLs, and assert each has an `integrity=` attribute. Prevent future regressions.

## Blast radius

**Current state:**
- Every authenticated page load triggers 3+ high-risk CDN JS loads (Tailwind + Dazzle own dist, possibly Mermaid on workspace surfaces with diagrams).
- Every marketing-site page load triggers 2 high-risk CDN JS loads (Tailwind browser + Dazzle own dist) plus 2 medium-risk stylesheets (DaisyUI + Google Fonts).
- Every 2FA enrollment transmits the TOTP secret to api.qrserver.com (the EX-054 class).

Phase 1 alone closes the SRI gap without breaking anything. Phase 2 reduces the external-load surface by ~60% (Tailwind CDN and Dazzle-own-dist both become self-hosted). Phase 3 brings CSP into alignment with the intent. Phase 4 prevents regression.

**Affected:** all 5 example apps + any downstream Dazzle deployment.

## Open questions

1. **Is cdn.tailwindcss.com the Tailwind JIT a dev affordance or intentional?** If the CSS-build pipeline produces equivalent output, the CDN is unnecessary. Worth checking if the CDN gives something build-time-compile can't (dynamic class generation from JS-added markup at runtime?).

2. **Why does Dazzle load its own dist from jsdelivr/gh instead of the installed package's /static?** The pattern `cdn.jsdelivr.net/gh/manwithacat/dazzle@v0.58.1/dist/...` is weird for a Python-package-installed framework. Likely a legacy pattern from an era before pip-installed Dazzle had its own static asset serving. Modern Dazzle-back already serves `/static/` — why isn't the template pointing there?

3. **Mermaid's vendoring cost.** Mermaid minified is ~1MB. Self-hosting means shipping that in every Dazzle deployment whether or not a workspace uses diagrams. Lazy-load via `<script src="/static/mermaid.min.js">` with SRI is the middle ground, but someone has to own the version bumps.

4. **Google Fonts — vendor or pin?** Self-hosted Inter is well-supported. But a `woff2` font file per weight per script is bulky. Worth measuring Inter-self-hosted-bundle size vs. the current Google CDN dep.

5. **CSP-report-only mode.** Would users accept temporary Report-Only mode as a stepping stone to full CSP? Or just go straight to block when ready?

6. **Backwards compatibility.** Changing CDN→local asset serving is a potential breaking change for anyone who has custom infra in front of Dazzle. Worth a deprecation flag + clear migration note.

## Recommendation

**No unilateral action this cycle.** The phases above span days of work and require coordinated template + middleware + CSS-build changes. Flagging for product direction:

- **Minimum action**: Phase 1 alone (SRI for all fixed-version CDN loads). Small scope, high value, low risk. A `/issues` candidate — file it as a focused PR.
- **Medium action**: Phase 1 + Phase 2 (vendor Tailwind + Dazzle-own-dist). Removes most of the external surface. 1-2 dev-days of careful work.
- **Full hardening**: Phase 1+2+3+4. Turns CSP into a real defense-in-depth layer with regression prevention. Probably a 1-week dedicated security sprint.

Cycle 299's EX-054 filing (#829) already covers the QR-service piece in isolation. This gap doc captures the class and the CSP-middleware integration that `#829` alone doesn't touch.

**Separately recommend filing a GitHub issue summarising Phase 1 as a focused SRI hardening PR**. Pure HTML change across 4 template files; no behavioural change; immediate CDN-compromise defense.

## Status tracking

| Phase | Status | Issue/Commit |
|-------|--------|--------------|
| 1 — SRI attributes on fixed-version CDN loads | FILED | [#830](https://github.com/manwithacat/dazzle/issues/830) (cycle 301) |
| 2 — Vendor Tailwind + Dazzle own dist | FILED | [#832](https://github.com/manwithacat/dazzle/issues/832) (cycle 323) |
| 3 — CSP default alignment | OPEN | Not filed yet |
| 4 — Template lint rule | **SHIPPED** | cycle 324 commit `a699e11c` — `tests/unit/test_external_resource_lint.py` |

Sub-case: QR service exfiltration — [#829](https://github.com/manwithacat/dazzle/issues/829) (cycle 299, EX-054).
