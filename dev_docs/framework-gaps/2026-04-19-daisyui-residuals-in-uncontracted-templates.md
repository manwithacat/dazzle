# DaisyUI Residuals in Uncontracted Templates

**Date:** 2026-04-19
**Synthesis cycle:** ux-cycle 271
**Theme slug:** `daisyui-residuals-in-uncontracted-templates`

## Problem statement

DaisyUI utility classes (`card`, `menu`, `btn`, `badge`, `alert`, `hero`,
`skeleton`, `link`, etc.) are banned from rendered output under the
design-system token regime established at v0.51. Colours must resolve
through `hsl(var(--token))` HSL-variable lookups; component chrome
must use `.dz-*` canonical class markers. Yet **DaisyUI leaks keep
surfacing in uncontracted or loosely-governed templates** — each
leak discovered only during a `contract_audit` cycle that happens
to touch the template in question. Between cycles 265 and 271, **8
distinct DaisyUI leaks** were found across 6 templates:

- 3 fixed as incidental side-work during promoting a PROP
- 2 fixed as incidental side-work during site-shell + island audits
- 3 still open in templates that haven't been audited

The root issue: **contracting is the only mechanism that systematically
enforces design-token compliance**. A template without a contract
pointer in its header comment — and without a `ux-architect/
components/*.md` file governing its quality gates — silently drifts.
Once drift is present, it survives indefinitely because nothing is
scanning for it except the next audit that touches the file.

## Evidence (8 observations across 6 templates)

Fixed during cycles 265-270:

| Cycle | Template | Leak | Fix |
|-------|----------|------|-----|
| 268 | `workspace/regions/tab_data.html:6` | Duplicate `border border-[hsl(var(--border))]` on `<select>` | Deduplicated |
| 268 | `workspace/regions/tab_data.html:41` | Dangling `hover` utility with no pseudo-class target | → `hover:bg-[hsl(var(--muted)/0.5)]` |
| 268 | `workspace/regions/tab_data.html:61` | `link link-hover link-primary` (DaisyUI) on ref anchors | → `text-[hsl(var(--primary))] hover:underline` |
| 269 | `site/sections/testimonials.html:7` | `class="card bg-[hsl(var(--muted))]"` | → `rounded-[6px] bg-[hsl(var(--muted))]` |
| 270 | `components/island.html:9` | `class="skeleton h-32 w-full"` | → `dz-skeleton h-32 w-full rounded-[4px] bg-[hsl(var(--muted))] animate-pulse` |

Still OPEN as of cycle 271 (identified this cycle via systematic sweep):

| Template | Line | Leak | Context |
|----------|------|------|---------|
| `experience/_content.html` | 138 | `class="card bg-[hsl(var(--muted))] p-8 text-center"` | Non-surface step placeholder (process/integration experiences). Uncontracted. |
| `fragments/detail_fields.html` | 4 | `class="card bg-[hsl(var(--card))] shadow-sm"` | Detail-view fragment used by API read handler for HTMX content negotiation. Governed loosely by `detail-view.md` (UX-012) but the detail fragment's body was never migrated. |
| `components/alpine/dropdown.html` | 13 | `class="... menu p-1 shadow-md bg-[hsl(var(--card))] rounded-lg ..."` | Generic Alpine dropdown component. Uncontracted (no matching `dropdown.md` contract — the `popover.md` contract covers popovers but not `<ul role="menu">` dropdowns). |

The 5 fixed leaks took on average **~1 minute each** to resolve
(each was a one-line edit). The 3 open leaks have the same profile.

## Root cause hypothesis

The **contract-authorship ordering** is the gap:

1. When a template is first written, no contract exists.
2. DSL authoring / template modification may introduce DaisyUI classes
   as the path of least resistance (they're in scope under the
   DaisyUI CDN stylesheet loaded from `site_base.html:18`).
3. A `missing_contracts` scan surfaces the template as a PROP.
4. A `contract_audit` cycle later writes the contract, applies the
   shared quality gates (including "no DaisyUI"), and the drift
   surfaces as a gate failure → fix lands in the same cycle.

For templates that never reach step 3-4 — either because they're off
the scanning radar or because the scan only hits obvious PROP
candidates — the drift persists. **Contracting is reactive, not
proactive.**

Secondary contributor: DaisyUI is NOT removed from the asset stack.
`site_base.html:18` and `base.html` load `daisyui@5/daisyui.css`
unconditionally. DaisyUI classes in HTML ARE processed by the
browser (they just don't match design-system tokens). There's no
build-time lint that fails on DaisyUI class names in Jinja
templates. A proactive lint rule would close this feedback gap.

## Fix sketch

Two complementary mechanisms:

### Mechanism A — Immediate: fix the 3 open leaks in one small cycle.

- `experience/_content.html:138` — replace `card bg-[hsl(var(--muted))]`
  with `rounded-[6px] bg-[hsl(var(--muted))]` (direct analogue of
  testimonials.html cycle 269 fix).
- `fragments/detail_fields.html:4` — replace `card bg-[hsl(var(--card))]
  shadow-sm` with `bg-[hsl(var(--card))] border border-[hsl(var(--
  border))] rounded-[6px] shadow-[0_1px_3px_rgb(0_0_0/0.04)]`
  matching detail-view.md (UX-012) canonical chrome.
- `components/alpine/dropdown.html:13` — replace `menu p-1`
  with `p-1` (the `menu` class provides vertical layout which
  the `<ul>` already has via flex/stack defaults). Verify with a
  raw render that no visual regression occurs.

Cost: <15 minutes total. Verification: re-run the systematic grep;
expect zero real leaks outside `reports/e2e_journey.html` (internal
dev artefact, scope TBD).

### Mechanism B — Durable: add a build-time lint rule.

A Jinja-aware lint that fails CI on any rendered-class-string
containing a known-DaisyUI-only token (card, menu, btn, hero,
skeleton, alert, badge, divider, rounded-box, bg-base-, text-base-
content, link link-, input input-). False positives acceptable —
the fix is either removing the class or renaming it with a `dz-`
prefix.

Lint surface: a pytest test in `tests/unit/` that:
1. Loads every template under `src/dazzle_ui/templates/`.
2. Extracts all static string literals (can't render dynamically
   because context is complex; substring matching on the template
   source is sufficient).
3. Greps each for banned DaisyUI class name patterns inside
   `class="..."` attributes.
4. Exempts `reports/e2e_journey.html` (internal) and anything
   matching `dz-<word>` explicitly.

Cost: ~45 minutes to write, runs in <1s on CI, catches every
future DaisyUI reintroduction at PR time.

## Blast radius

- **Confirmed affected** (open leaks): `experience/_content.html`,
  `fragments/detail_fields.html`, `components/alpine/dropdown.html`.
- **Confirmed clean** (post-cycle-268..270 fixes): `workspace/
  regions/tab_data.html`, `site/sections/testimonials.html`,
  `components/island.html`.
- **Likely clean** (contracted and recently audited):
  `site/sections/*.html` (UX-058 omnibus sweep, cycle 269),
  `site/includes/*.html` (UX-055, UX-056), `site/site_base.html`
  (UX-056), `app_shell.html` + `app/403.html` + `app/404.html`
  (UX-031/050/051), `fragments/parking_lot_primitives*.html`
  (UX-040 + parking-lot-primitives omnibus).
- **Unknown** (not swept): templates outside the sweep this cycle
  ran. The sweep used `grep -rEn` across `src/dazzle_ui/templates/`
  which IS comprehensive. Anything NOT in the "likely clean" list
  and NOT a fresh-look subject should be re-swept.
- **Reports explicitly excluded**: `reports/e2e_journey.html` uses
  DaisyUI classes extensively (`card`, `badge badge-<verdict>`,
  `stat-card`, etc.) but is an internal dev artefact, not user-
  facing. Decision on whether to bring it into the governance
  regime is deferred.

## Open questions

1. **Reports-template policy.** `reports/e2e_journey.html` is the
   only non-user-facing template with extensive DaisyUI class use.
   Decision needed: migrate it (consistent vocabulary across all
   templates) or exempt it (accept that dev-only tooling has its
   own styling conventions). Recommendation: exempt in v1 of the
   lint rule, tackle in a dedicated cycle if it becomes a friction
   point.
2. **`<details>`/`<summary>` DaisyUI `collapse`.** Not observed in
   this sweep, but historically `collapse collapse-arrow` DaisyUI
   classes were used for accordions. Parking-lot-primitives moved
   accordions to native `<details>`/`<summary>` (cycle 247) — worth
   a re-scan to confirm no remnants in template tree.
3. **DaisyUI in CDN.** `site_base.html:18` and `base.html` both
   load `daisyui@5/daisyui.css` as a CDN sheet. Removing DaisyUI
   from the asset stack entirely would make any remaining class
   reference a no-op (breaking visually on purpose). Not
   recommended until the lint rule (Mechanism B) is green — doing
   both in one pass could cause visible regression on any
   unremediated template.
4. **Build-time vs runtime enforcement.** The lint rule in
   Mechanism B is build-time. An alternative is runtime:
   `dz-islands.js`-style JS that walks the DOM after load and
   logs violations to console. Less useful (only catches observed
   pages; slower feedback) but would capture drift in DSL-authored
   island modules that ship their own classes. Worth considering
   but Mechanism B (build-time) is higher-leverage.
5. **DSL-author discipline.** Some DaisyUI leaks originated from
   DSL authors writing class tokens in sitespec YAML. The current
   contract family (site-section-family, site-shell) doesn't gate
   DSL-origin class strings. If Mechanism B's lint only covers
   `src/dazzle_ui/templates/`, DSL-authored class strings via
   `section.background` or similar escape the sweep. Worth
   extending the sweep to rendered output post-compile for these
   cases.

## Next steps

1. **Cycle 272 (next cycle) — tactical cleanup.** Fix the 3 open
   leaks via Mechanism A. Small self-contained work; one commit.
   Adds no new governance but closes visible drift.
2. **Subsequent cycle — durable mechanism.** Write the pytest lint
   rule per Mechanism B. Single-commit feature. Add it to CI. From
   that point forward, DaisyUI drift is caught at PR time.
3. **Reports-template decision.** Log a separate EX row to track
   the open question on `reports/e2e_journey.html`. Defer until
   the lint rule is green.
4. **Re-sweep one cycle after Mechanism B lands.** Confirm zero
   DaisyUI residuals in the `src/dazzle_ui/templates/` tree
   (excluding `reports/*`). If the sweep passes, close this theme
   as resolved.
