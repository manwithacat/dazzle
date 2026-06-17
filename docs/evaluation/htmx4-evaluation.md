# htmx 4 upgrade evaluation (independent, from `main`)

Date: 2026-06-17
Worktree: `.claude/worktrees/htmx4-eval`, branch `htmx4-eval` (branched from `origin/main` @ `841ecb9e7`)
Method: fresh static audit of current `main`. No htmx 4 bundle swapped in; no code modified. The
prior worktree (`/Volumes/SSD/Dazzle-htmx4`, branch `codex/htmx-4-eval`, 2026-06-12) was read as
input only and is **not** merged here.

> This is a *feasibility + cost* evaluation, not a migration. Every claim below is anchored to a
> verified `file:line` on `main` so the numbers can be re-checked.

## Verdict

**Feasible, medium-large, single-developer-weeks of effort — but not urgent.** htmx 2.0.9 is healthy
and the auto-update cron deliberately pins `v2.` (`scripts/update_vendors.py:199`). The migration is a
*deliberate, gated* project, not a version bump. The dominant cost is **not** the server (Dazzle's
HX-* contract is already explicit and well-centralised) — it is the **client JS + the idiomorph↔Alpine
coupling**. Recommend: keep htmx 2, land the cheap forward-compatible cleanups now (delete 4 dead
extensions, centralise the event-name strings), and schedule the real migration behind a feature
branch with browser-level coverage as the gate.

## Current state on `main`

| Dimension | Reality |
|---|---|
| htmx version | **2.0.9**, vendored at `src/dazzle/ui/runtime/static/vendor/htmx.min.js` |
| Extensions vendored | 9 + idiomorph, bundled in order via `scripts/build_dist.py` `JS_SOURCES` (77–87) |
| Version pin | `v2.` hard-pin in `scripts/update_vendors.py:199`; v4 explicitly out-of-scope for cron |
| Integrity gates | `vendor_hashes.json` SHA-256 pins every vendor file; 3 drift tests in `tests/unit/test_vendor_hash_drift.py` |
| Server HX-* contract | Centralised in `src/dazzle/ui/runtime/htmx.py` (`HtmxDetails`, response helpers) |
| Rendering | Typed Fragment substrate (ADR-0023, no Jinja2) — htmx attrs emitted from Python, easy to grep/change |
| Architectural anchor | ADR-0011 (SSR + htmx, no SPA). Migration does **not** touch this decision |

## htmx 4 changes that actually hit Dazzle

From the htmx 4 docs (four.htmx.org) cross-checked against our footprint:

1. **fetch() replaces XHR.** `event.detail.xhr` is gone. → 6 sites (see client table).
2. **Events are colon-namespaced.** `htmx:afterSettle` → `htmx:after:settle`, etc. → 30 listener sites.
3. **Errors swap by default.** Only `204`/`304` are no-swap defaults (htmx 2 did not swap 4xx/5xx). →
   *Lower risk than it sounds for us* — see "Server" below.
4. **Attribute inheritance is explicit by default.** Inherited `hx-*` on ancestors no longer cascade
   unless opted in. → needs a markup audit or `htmx.config.implicitInheritance = true` bridge.
5. **Native `innerMorph`/`outerMorph` replace the idiomorph extension.** → 3 emission sites + the
   load-bearing Alpine-preservation patch.
6. **Native `hx-status:*` replaces response-targets**; **`hx-sse:connect`/`hx-preload`** replace those
   extensions; extension registration API changed (`htmx.registerExtension`).

## Migration surface, risk-ranked

### TIER 1 — load-bearing, the real work

**A. Client-side event renames (30 sites, 9 event names).** All in `src/dazzle/ui/runtime/static/js/`.
Mechanical but wide; no central constant today, so it's 30 hand-edits + re-test.

| Event | Sites | Notable consumers |
|---|---|---|
| `htmx:afterSwap` | 5 | a11y aria-busy/focus, analytics page_view, onboarding re-arm |
| `htmx:afterSettle` | 5 | **Alpine.initTree bridge** (`dz-alpine.js:2178`), component-bridge widget mount, islands mount, debug settle stamp |
| `htmx:beforeSwap` | 4 | AbortController wiring, widget/island unmount |
| `htmx:afterRequest` | 3 | haptics, x-optimistic reconcile, analytics — **all read `xhr`** |
| `htmx:beforeRequest` | 3 | aria-busy, optimistic snapshot, table loading flag |
| `htmx:responseError` | 3 | feedback log, table flag clear, preload 401/403 silence |
| `htmx:sendError` | 3 | feedback log, optimistic rollback |
| `htmx:configRequest` | 2 | **CSRF token injection** (`dz-csrf.js:45`), bulk-action ids |
| `htmx:pushedIntoHistory` | 2 | a11y title announce, aria-current |

**B. XHR → fetch Response (6 sites).** `dz-alpine.js` (94, 636, 2294-95), `dz-analytics.js`
(154, 191-93 — reads `xhr.getResponseHeader`), `feedback-widget.js:68`. These need real rewrites
(status/header access differs under fetch), not just renames. Highest-attention: the **x-optimistic**
directive (`dz-alpine.js`) and analytics header reads.

**C. idiomorph → native morph + the Alpine coupling (the single biggest risk).**
- Emission: `table_renderer.py:426`, `back/runtime/htmx_render.py:89`, `_render_interactive.py:209`
  (`hx-swap="morph:innerHTML"`).
- The coupling: `dz-alpine.js:2158-2224` re-runs `Alpine.initTree`/`destroyTree` on `htmx:afterSettle`
  after a morph, **and** `dz-alpine.js:2226-2270` (#964) patches
  `Idiomorph.defaults.callbacks.beforeAttributeUpdated` to skip `@`-prefixed Alpine directives
  (Chromium `InvalidCharacterError`). htmx 4's native morph is a *different implementation* — this
  patch and the settle-bridge must be re-derived against htmx 4's morph callbacks/events, and the
  Chromium `@`-attribute behaviour re-verified. **This is where a "looks done" migration silently
  breaks workspace re-hydration.** Needs browser-level proof, not unit tests.

**D. json-enc (5 emission sites + server body parser).** `experience_renderer.py:134`,
`detail_renderer.py:495`, `template_renderer.py:66`, `_render_forms.py:79`, `_render_tables.py:462`;
server side `back/runtime/handlers/write_handlers.py:42-60` sniffs the json-enc body. htmx 4 removes
the json-enc *extension*; the prior worktree's approach (emit `data-dz-encoding="json"` + a small
Dazzle bridge, keep the server parser tolerant) is sound and worth reusing. Touches both ends of the
write contract, so it needs paired client+server change in one commit (ADR-0003).

### TIER 2 — bounded, mostly markup

- **response-targets → `hx-status:*`** — 1 site, `experience_renderer.py:131-132`
  (`hx-target-422` / `hx-target-5*` → `hx-status:422="target:#form-errors"` etc.).
- **loading-states** — 1 site, `experience_renderer.py:140` (`data-loading-*`). Replace with a tiny
  bridge or `hx-disabled-elt` + Alpine.
- **remove-me** — 1 site, `back/runtime/response_helpers.py:39` (toast auto-dismiss). Needs a small
  timer behaviour (the prior worktree emitted `data-dz-remove-after`).
- **SSE** — 1 *conditional* site, `_render_dashboard.py:63` (only when `DashboardGrid.sse_url` set).
  Move to `hx-sse:connect`. No live example app exercises it, so verify carefully or defer.
- **Attribute inheritance audit** — find inherited `hx-*` on ancestor elements. Cheapest first
  landing is `htmx.config.implicitInheritance = true`; converting markup is a follow-up.

### TIER 3 — free wins, do regardless of timing

**4 extensions have ZERO emission sites** — they are bundled dead weight today:
`preload`, `class-tools`, `multi-swap`, `path-deps` (only referenced from
`static/test-workspace-perf.html` as library loads). Removing them from `JS_SOURCES` +
`vendor_hashes.json` shrinks the bundle and the migration surface **now**, independent of htmx 4.

> Note: this refines the prior worktree's inventory, which listed `preload` as removed-but-replaced.
> On `main` it is simply unused.

### Server side — lower risk than the change-count implies

Dazzle's HX-* contract is centralised (`ui/runtime/htmx.py`, re-exported via
`back/runtime/htmx_response.py`) and already **explicit**:
- Mutations set `HX-Trigger` (+ optional `HX-Redirect`) via `_with_htmx_triggers`
  (`htmx_render.py:599-602`).
- Form errors return **422 with explicit `HX-Retarget #form-errors` + `HX-Reswap`**
  (`htmx.py:104-108, 183-189`) → htmx 4's default-swap-errors does not regress these; the target is
  pinned.
- Toast-only read-context errors return **200 with empty body + `HX-Trigger showToast`**
  (`htmx.py:262-282`) → 200 is swapped in both htmx 2 and 4; empty body = no visible swap. Fine.
- Onboarding `complete`/`dismiss` return **200 empty body intentionally to swap-away the popover**
  (`onboarding/routes.py:53,68`) → this is a deliberate outerHTML swap, **not** an error-swap
  regression. Re-verify the popover still clears, but it is low risk.
- Auth/admin/locale redirects already use **204 + `HX-Redirect`/`HX-Refresh`** — htmx 4 safe.

Net: the server needs a *review pass and a couple of confirmations*, not a rewrite. The
default-swap-errors change — usually the scary headline — is largely absorbed because Dazzle never
relied on implicit error non-swap; it always set explicit retarget/reswap.

## Verification & gates that will fire

Swapping the bundle trips, in order:
1. `tests/unit/test_vendor_hash_drift.py` (3 tests) — regenerate via `scripts/update_vendor_hashes.py`.
2. `tests/unit/test_htmx_extensions_v2_clean.py` — asserts v2 extension provenance; will need rework
   for v4's separate extension model.
3. `tests/unit/test_asset_bundle.py` — `base.html` ↔ `JS_SOURCES` parity.
4. Header/behaviour suites: `test_htmx_details.py`, `test_ux_htmx_client.py`,
   `test_htmx_mutation_response.py`, `test_json_or_htmx_error_get_toast.py`, `test_region_adapter.py`,
   `test_optimistic_directive*.py`, `test_htmx_workspace_composite.py`, `test_view_transition_swap.py`,
   `render/fragment/test_htmx_types.py`.

**Critical gap:** none of these are browser-level. The Tier-1 risks (morph↔Alpine re-hydration,
fetch event renames, x-optimistic) can pass every unit test and still break in the browser. The
migration's real gate must be `dazzle ux verify` / e2e browser coverage on the workspace-heavy apps
(`ops_dashboard`, `design_studio`, `support_tickets`) — exactly the three the prior worktree
smoke-tested. **Add that coverage *before* migrating**, so it's a regression oracle, not an
afterthought.

## Effort estimate (single developer)

| Phase | Scope | Est. |
|---|---|---|
| 0 | Tier-3 dead-extension removal (safe now) | 0.5 day |
| 1 | Browser-level regression coverage for the 3 workspace apps (the gate) | 2–3 days |
| 2 | Client event renames + fetch/xhr rewrites (Tier 1A/B), CSRF + analytics + optimistic | 3–4 days |
| 3 | Morph + Alpine coupling re-derivation against htmx 4 native morph (Tier 1C) | 3–5 days |
| 4 | json-enc bridge, both ends (Tier 1D) | 1–2 days |
| 5 | Tier-2 markup (status targets, loading, remove-me, sse, inheritance) | 2–3 days |
| 6 | Vendor/hash/bundle/test-suite reconciliation + docs/ADR-0011 note | 1–2 days |
| | **Total** | **~13–20 working days** |

## Recommendation

1. **Now, on `main` (no htmx 4 needed):** remove the 4 dead extensions (Tier 3); introduce a single
   source of truth for htmx event-name strings in the JS layer so Phase 2 is a one-file diff, not 30.
   These are pure forward-compat cleanups.
2. **Schedule the migration as a gated feature branch**, Phase 1 (browser coverage) first. Do not
   start Phase 2+ until the three workspace apps have a browser regression oracle.
3. **Keep htmx 2.0.9 in the meantime.** It is maintained and the cron keeps it patched. There is no
   functional or security forcing-function to move today; htmx 4 is still beta (`4.0.0-beta*`) — that
   alone is a reason to wait for GA before committing the framework's default.
4. **Reuse the prior worktree's proven fixes** as implementation input (json-enc `data-dz-encoding`
   bridge, `HX-Reswap: none` for toast-only, ops-dashboard filter `hx-trigger` gating), but
   re-validate each against current `main`, which has moved since 2026-06-12.

## Open questions for a go decision

- Wait for htmx 4 GA, or migrate on beta to de-risk early? (Recommend: wait for GA; prep now.)
- Accept `implicitInheritance = true` for first landing, or convert inherited markup up front?
- Is the conditional SSE path (`DashboardGrid.sse_url`) actually used by any consumer, or can it be
  deferred/dropped from the v4 surface?
- Native morph behaviour parity with idiomorph's Alpine `@`-attribute skip — confirmed by browser test
  before committing? (This is the make-or-break item.)
