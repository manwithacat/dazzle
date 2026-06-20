# Template-Ship-Without-Wiring Gap

!!! info "📜 Historical snapshot — not current docs"
    Captured **2026-04-20** during Dazzle's autonomous-improvement cycles. It records the
    framework as it was then and the gap being worked at the time; **it may not
    describe current behaviour.** Start from the [documentation home](../../index.md),
    or see [Project Evolution](../../architecture/evolution.md) for how these fit together.


**Date:** 2026-04-20 (cycle 305 framework_gap_analysis)
**Class:** Framework structural completeness
**Status:** Open — needs product-direction decision on which of two sub-classes (primitive dormancy vs. page-route gaps) the framework should actively enforce

## Problem statement

The framework ships **UI templates** in `src/dazzle_page/templates/` that have **no production consumer**. Cycle 302's orphan_lint_rule surfaced 7 such templates (after cycle 304's scanner hardening). They fall into **two distinct sub-classes with different severity profiles**:

### Sub-class A: Primitive dormancy (low severity, high ambiguity)

Reusable UI building blocks with `ux-architect` contracts but no downstream adopter:

- `components/alpine/confirm_dialog.html` (UX-014, cycle 175 QA'd)
- `components/alpine/dropdown.html` (cycle 286)
- `components/modal.html` (modal.md contract)
- `components/island.html` (UX-059, DSL-wired via `IslandContext` but no template include)

**Impact:** low. The templates ship but don't execute. Users who would benefit from the primitive are supposed to `{% include %}` it but don't know it exists. Zero user-facing breakage — just wasted investment + potential confusion for AI-assisted adopters who see the contract but can't infer from production examples how to wire it.

### Sub-class B: Page-route gaps (high severity, user-facing breakage)

HTML page templates shipped without the Python glue that serves them:

- `site/auth/2fa_challenge.html` — mid-login challenge (EX-055, filed as [#831](https://github.com/manwithacat/dazzle/issues/831))
- `site/auth/2fa_setup.html` — enrollment
- `site/auth/2fa_settings.html` — management

**Impact: high.** A Dazzle deployment with 2FA configured cannot actually reach the UI to enroll, manage, or complete mid-login challenges. The feature is half-shipped. Unlike Sub-class A, Sub-class B represents genuinely broken user flows.

## Evidence

| Observation | Discovered | Sub-class | Status |
|-------------|------------|-----------|--------|
| PR #600 Alpine primitives (confirm_dialog, dropdown) | cycle 286 + 287 gap doc | A | Awaiting user direction (keep dormant / adopt / delete) |
| `components/modal.html` | cycle 302 orphan scan | A | Dormant; has contract (modal.md) |
| `components/island.html` | cycle 302 orphan scan | A | IslandContext dataclass wired, template never included |
| `site/auth/2fa_challenge.html` | cycle 302 orphan scan | B | Filed: [#831](https://github.com/manwithacat/dazzle/issues/831) |
| `site/auth/2fa_setup.html` | cycle 302 orphan scan | B | Same |
| `site/auth/2fa_settings.html` | cycle 302 orphan scan | B | Same |
| `components/alpine/dropdown.html` (scanner false negative) | cycle 304 | A | Scanner fix + allowlist entry |

**Seven observations — all surfaced by automated lint (cycle 302) + one by a targeted follow-up (cycle 304).** Before cycle 302, the dropdown + confirm_dialog cases were only known because a Heuristic-1-audit in cycles 286-287 discovered them by accident. The scanner converted incidental discovery into systematic discovery — exactly the horizontal-discipline pattern from cycle 284's EX-051 lint.

## Root cause hypothesis

### Root cause for Sub-class A (primitives)

Framework evolution introduces reusable UI primitives (Alpine components, generic HTML components) faster than feature-level adopters pick them up. The `ux-architect` skill documents them in contract form — which reads as "ready for use" — but the `/ux-cycle` workflow that produces contracts is **decoupled from feature development** that would incorporate them. Result: contracts accumulate faster than adoptions.

Why this matters less than Sub-class B:
- No user-facing breakage.
- Contracts serve as documentation even without adoption.
- Selective adoption is legitimate — not every primitive is universally useful.

### Root cause for Sub-class B (pages without routes)

The 2FA case has a specific narrative: cycles 33-41 shipped the UX-036 auth-page macro migration, which included `site/auth/2fa_*.html` templates as part of "all 7 site/auth/ templates under macro governance" (CHANGELOG line 3013). The migration focused on **template styling** but didn't verify that each template had a corresponding **server route**. At migration time `site_routes.py` served `login/signup/forgot_password/reset_password` but not the 2FA pages. The templates were migrated anyway — the CSS + macro work was decoupled from route wiring.

The cycle-298 contract_audit (UX-077) later formalised the 2FA templates without raw-layer-verifying the page routes existed, because cycle 298's tests were **source-level assertions** (read template text + assert structure) rather than end-to-end render tests. The contract passed tests → appeared governed → gave false confidence.

Without the cycle-302 orphan scanner, Sub-class B could have persisted indefinitely: templates present, CSS correct, contract "passing," user flow broken, no automated surface.

## Fix sketch

Two distinct fix tracks, corresponding to the two sub-classes:

### Track A: Primitive-dormancy policy

Make the framework's stance on dormant primitives explicit. Three options:

1. **Accept & document**: each dormant primitive keeps its contract + source, and the `ux-architect` catalog labels it `dormant` or `ready-to-adopt`. The orphan_lint allowlist has reasons. Cost: low. This is the current de-facto state.

2. **Prune**: delete dormant primitives + their contracts. Cost: irreversible. Upside: simpler surface area.

3. **Adopt**: for each dormant primitive, either land a production adopter OR promote to user-facing DSL (so DSL authors can opt in). Cost: ~1-2 cycles per primitive. Upside: shipped code is used code.

Recommendation: **Option 1** for now, flag the catalog, re-evaluate at v1.0. The ux-architect contract is a small investment; shedding it for "dormant" primitives trades off future optionality.

### Track B: Page-route hygiene lint (novel)

Extend the existing orphan_lint_rule or add a parallel test that verifies: **every page template under `site/auth/`, `site/`, and other page-directories has a corresponding route in the site-routes module.** The lint would:

1. List all page-like templates (exclude `includes/`, `sections/` which are loaded dynamically).
2. List all routes that call `render_site_page("<template>")`.
3. Assert page-like templates are served by at least one route OR appear in a new `PAGE_TEMPLATE_ALLOWLIST` with a reason (for genuinely dev-only or testing templates).

Impact: **cycle 302 would have surfaced EX-055 immediately** if this lint existed. It would also catch future regressions where a page template lands without route wiring.

Scope: ~50 LOC in `tests/unit/test_page_route_coverage.py`. Cross-references `site_routes.py` + `routes_2fa.py`'s patterns. A natural extension of cycle 302's orphan_lint infrastructure.

Secondary benefit: the lint's ALLOWLIST becomes a forcing function — if a page template is legitimately dev-only (QA harness pages, etc.), adding it requires a reason that points at the gating flag/env var. Discourages drift.

### Track C: Primitive-adoption-nudge (optional)

For each primitive in Sub-class A that has a `ux-architect` contract but zero adopters, consider whether the contract should include an "adoption signal": a concrete example app that uses it as a demo. This turns "here's a primitive" into "here's a primitive + here's how it looks in production." Lower priority than B.

## Blast radius

- **Sub-class A**: Low. 4 primitives, ~200 LOC of unadopted templates. No user breakage. ~10 KB wasted in shipped wheels.
- **Sub-class B**: **High**. 3 page templates (441 LOC total), covering the entire 2FA UI flow. Dazzle deployments with 2FA enabled have broken setup/management/challenge flows. Any user who runs `dazzle serve` with `twofa_enabled=True` in their DSL hits unreachable pages.

Affected apps: any Dazzle deployment enabling 2FA (unknown downstream count; zero of the 5 example apps enable it).

## Open questions

1. **Should Sub-class A primitives come with example adopters?** The framework ships a `component_showcase` fixture (per CLAUDE.md) — would it be valuable to extend that to demonstrate every ux-architect-contracted primitive, even dormant ones? Might convert dormant primitives into "demonstrated primitives" worth keeping.

2. **What's the right cadence for orphan_lint review?** Currently runs on every test suite run. Should it also run as a cycle 295-style `missing_contracts` counterpart — a periodic scan with human-readable report independent of the binary pass/fail?

3. **Could cycle 298-style source-level assertion failures be pre-emptively caught?** The contract_audit cycle writes tests that check template TEXT, not template USAGE. A meta-lint could verify every contract has at least one end-to-end render test OR a cross-reference to the page route that serves the template. Harder to automate but would catch future Sub-class B cases.

4. **Is Sub-class B possibly a recurring pattern in the site/auth/ family specifically?** EX-055 covers 2FA. What about password-reset-complete, account-deletion-confirmation, account-verification-success? Worth a targeted scan of `site/auth/` to see if other half-shipped flows exist. Currently all 4 non-2FA auth pages (login, signup, forgot_password, reset_password) have routes; but the framework may grow more auth pages in future and the pattern could repeat.

5. **Track B lint implementation detail: how to know which templates are "page-like" vs. "fragment-like"?** The orphan scanner treats everything as a template. Page-route-coverage would need a convention — perhaps a file naming pattern (`*_page.html`?) or a frontmatter comment (`{# ... page: true #}`). Worth discussing before implementing.

6. **Does Sub-class A need a `components/alpine/` family-level contract?** Mirroring how UX-058 site-section-family covers 17 section templates with one doc. Alpine primitives (dropdown, confirm_dialog, slide_over, etc.) share enough structure that a family contract would be cleaner than individual-per-primitive contracts for those that stay dormant.

## Recommendation

**No unilateral action this cycle.** Two tracks warrant separate decisions:

- **Track A (primitives policy)**: Defer to v1.0 review. Current pattern (accept + allowlist) is stable enough.
- **Track B (page-route-coverage lint)**: **File as a focused GitHub issue** if the policy direction is "Sub-class B should never happen again." This would be a direct follow-up to #831 (which is the individual bug) — the lint is the prevention mechanism. Scope: ~50 LOC test addition. Small enough for `/issues` pickup.

Meta-recommendation: cycle 300's external-resource-integrity gap doc + this one + cycle 287's PR #600 dormant primitives gap doc now form a **small library of "framework structural completeness" gap analyses**. A future synthesis cycle could combine them into a single "structural-completeness-health-report" evergreen doc that tracks the state of all identified sub-classes.

## Status tracking

| Sub-class | Track | Status | Issue/Commit |
|-----------|-------|--------|--------------|
| A — primitive dormancy | Policy: accept + allowlist | OPEN (deferred) | Gap doc cycle 287 (PR #600 primitives subset) |
| B — 2FA page route gap | #831 fix | FILED | [#831](https://github.com/manwithacat/dazzle/issues/831) |
| B — page-route-coverage lint | Not filed | OPEN | Candidate for next cycle or `/issues` |

Cross-refs:
- [gap doc 2026-04-20-pr600-dormant-alpine-primitives.md](./2026-04-20-pr600-dormant-alpine-primitives.md) — Sub-class A precursor
- [gap doc 2026-04-20-external-resource-integrity.md](./2026-04-20-external-resource-integrity.md) — parallel structural-completeness theme
- cycle 302 log entry — orphan_lint_rule implementation
- cycle 303 log entry — EX-055 investigation
- `tests/unit/test_template_orphan_scan.py` — the mechanism that surfaces all these
