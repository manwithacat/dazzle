# Changelog

All notable changes to DAZZLE will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

## [0.55.31] - 2026-04-15

### Fixed
- **manwithacat/dazzle#776: 404/403 pages under `/app/*` now render inside the
  authenticated app shell.** Previously `site/404.html` and
  `site/403.html` (which extend the marketing site layout) were
  rendered unconditionally for every error, so a logged-in user
  hitting a bad record URL (`/app/contact/bad-id`) or a forbidden
  workspace (`/app/workspaces/forbidden`) was dropped into the public
  marketing chrome with `Sign In` / `Get Started` nav links. Every
  Dazzle example app exhibited this (5-app cross-cycle evidence from
  cycles 201/213/216/217/218 of the /ux-cycle autonomous loop).

  The fix adds two new templates — `templates/app/404.html` and
  `templates/app/403.html` — which extend `layouts/app_shell.html`
  and render the error markup inside the authenticated sidebar +
  navbar chrome. The exception handler in
  `src/dazzle_back/runtime/exception_handlers.py` now inspects
  `request.url.path`: if it starts with `/app/` (or is exactly
  `/app`), the in-app variant is rendered; otherwise the existing
  marketing-site variant is rendered. API requests still return JSON
  regardless of path.

  The in-app error page also includes a **"Back to List" /
  "Back to Dashboard" affordance** computed from the request path.
  `/app/contact/bad-id` → `Back to List` (to `/app/contact`);
  `/app/workspaces/forbidden` → `Back to Dashboard` (to `/app`).
  This was a secondary complaint in the cycle-201 EX-004 and
  cycle-217 EX-014 observations: the only recovery affordance was
  "Go Home" which dropped the user on the public landing page.

### Added
- 14 new unit tests in `tests/unit/test_exception_handlers.py` covering
  `_is_app_path` (5 cases), `_compute_back_affordance` (5 cases), and
  the end-to-end dispatch via the registered handler (4 cases: 404
  in-app, 404 marketing, 403 in-app, API request JSON fallback).

### Agent Guidance
- **Error pages under `/app/*` must render inside the authenticated
  shell.** When adding a new error type or status code that browsers
  might hit inside the app, route through
  `_render_app_shell_error(...)` in `exception_handlers.py` rather
  than calling `render_site_page(...)` directly. The in-app variant
  preserves sidebar, persona badge, and logout context; the marketing
  variant does not.



### Added
- **Cycle 218 — explore: contact_manager / user / edge_cases.** Final
  app to receive an edge_cases run; completes the 5-app coverage matrix
  on the new substrate. 15 helper calls, ~64k subsidised tokens, 238s
  wall-clock. **0 proposals + 5 observations** (2 concerning, 1 notable,
  2 minor) ingested as EX-020..024.
- **5th-app cross-confirmation of the 404/403 marketing-chrome eject.**
  `/app/contact/{nonexistent-id}` drops the authenticated user into the
  public marketing chrome with 'Sign In' nav. Now confirmed in
  support_tickets, simple_task, ops_dashboard, fieldtest_hub, AND
  contact_manager — every example app exhibits the bug.
- **2nd-app confirmation of the data-table formatter bug, worse here.**
  `/app/contact` renders 20 row-action link groups with **zero cell
  content**. Embedded version in `/app/workspaces/contacts` renders
  the same entity correctly. Cycle 217 found "-" / blank cells in
  fieldtest_hub; here the entire row body is blank. Same root cause,
  more severe symptom.
- **Important non-finding: UX-046 bulk-action-bar is NOT regressed.**
  The cycle 217 EX-019 finding was specifically about an unfilled
  count slot in the label, not the visibility binding. The bar IS
  properly CSS-hidden without selection. Cycle 217's contract walker
  PASS stands.

### Filed upstream issues
- **manwithacat/dazzle#776 — framework: 404/403 error pages drop authenticated
  users into public marketing chrome.** Filed with 5-app cross-cycle
  evidence: cycles 201/213/216/217/218. Conclusively a framework-level
  layout dispatch bug. Suggested fix sketch included: dispatch error
  templates by URL prefix (`/app/*` → authenticated shell). Sits
  alongside #774 (silent create-form failure) and #775 (sidebar nav
  shows inaccessible links) as the three confirmed framework-level
  defects this session has surfaced.

### Agent Guidance
- **Cross-cycle convergence at N≥5 is conclusive.** When the same
  defect appears in 5 different apps with 5 different personas across
  5 different cycles, it's not a coincidence. File it. Cycle 218 made
  the 404-eject pattern N=5 and triggered the issue filing.
- **The substrate is in a steady state.** Six cycles of explore
  produce real signal but at decreasing per-cycle marginal yield. The
  high-value action now is converting accumulated cross-app signal
  into upstream issues, not running more explore cycles. The session
  has produced enough evidence to act on.



### Added
- **Cycle 217 — explore: fieldtest_hub / engineer / edge_cases.**
  Highest-yield edge_cases run yet. ~18 helper calls, ~61k subsidised
  tokens, 369s wall-clock. **0 proposals + 7 observations** (4
  concerning, 2 notable, 1 minor) — all ingested as EX-013..019:
  - **Two more cross-app convergences** strengthen existing
    framework-level signals:
    - **404/403 → marketing chrome dropout** now confirmed in **four**
      apps (support_tickets EX-003, simple_task EX-008, ops_dashboard
      adjacent EX-010, fieldtest_hub EX-014). This is conclusively a
      framework-level layout dispatch bug, not a per-app issue.
    - **Silent form submit failure** now confirmed in two apps
      (support_tickets manwithacat/dazzle#774, fieldtest_hub EX-018). Same shape as
      the cycle-201 finding.
  - **Genuinely new framework-level findings**:
    - EX-016: data-table FK lookup + datetime formatter both silently
      failing (rendering "-" and blank). The walker observed
      IssueReport rows where Device should be a ref display name and
      Reported At should be a timestamp — both empty. Two formatters,
      not one.
    - EX-019: bulk-action-bar visible without selection AND showing
      "Delete  items" with missing count. **Possible regression of
      UX-046 quality gate 1** (the visibility binding should be
      `bulkCount > 0`). Worth investigating before the next cycle
      adopts the contract for fieldtest_hub.
    - EX-013: sidebar "Issue Board" link unresolvable; fourth
      independent confirmation of the sidebar-403 / nav-mismatch
      pattern.
    - EX-017: empty-state copy "No issues reported yet - great work!"
      contradicts an adjacent region showing 5 issues. Cross-region
      inconsistency in the same workspace.

### Agent Guidance
- **Edge_cases against rich-content apps is qualitatively different
  from edge_cases against empty apps.** Cycle 217 produced 7 findings
  in fieldtest_hub vs cycle 216's 3 in ops_dashboard. The presence of
  seed data + rich region templates makes the difference. Future
  edge_cases cycles should prefer apps where the persona has reachable
  content.
- **EX-019 may be a UX-046 regression.** The bulk-action-bar contract's
  Quality Gate 1 says "When `bulkCount === 0`, the bar is hidden". The
  fieldtest_hub finding says the bar is visible at zero count. Either
  fieldtest_hub uses a stale fragment, or the contract walker on the
  cycle 212 PASS happened to hit a path where the bar was hidden but
  the gate didn't actually verify the negative. Worth a re-verification
  cycle against fieldtest_hub specifically.



### Added
- **Cycle 216 — explore: ops_dashboard / ops_engineer / missing_contracts.**
  11 helper calls, ~70k subsidised tokens, 264s wall-clock. Useful
  **negative result**: 0 proposals + 3 observations. The substrate is
  operating correctly; ops_dashboard simply doesn't expose new
  uncontracted patterns to this persona because (a) the seed is empty,
  (b) ops_dashboard's DSL only uses `list` mode regions and not the
  richer region templates (heatmap, funnel, timeline, tree, metrics,
  progress, diagram, bar_chart) that `src/dazzle_ui/templates/workspace/regions/`
  ships with.
- **Cross-app convergence #3 on the sidebar-403 pattern.** EX-010 in
  ops_dashboard joins EX-002 (support_tickets) and a similar finding
  in cycle 199's manager run. Same shape: nav links visible, persona
  can't actually access. **Three independent confirmations across
  three distinct example apps now make this a framework-level pattern
  worth filing as an issue separately from the cycle-201 issue #775.**
  Possibly the same root cause manifesting at the framework level
  (sidebar generator doesn't filter by `access:` rules).
- 3 new EX rows (EX-010..012): sidebar-403, ops-engineer empty-state
  CTAs invite admin-gated actions, and a minor "no uncontracted
  components visible on the reachable surface" observation.

### Agent Guidance
- **Empty-state runs have low component yield.** Cycle 216 confirms
  what intuition suggested: subagent explore against an app with no
  seed data reaches very few interactive surfaces. Future explore
  cycles should prefer (a) apps with rich seed data, (b) the
  `component_showcase` fixture which exercises every region template
  type, or (c) personas with admin reach. Picking ops_engineer was
  technically correct (it's the persona that owns the workspace) but
  empirically unproductive.
- **Negative results are first-class findings.** Cycle 216 produced
  zero proposals but a strong cross-app convergence signal on the
  sidebar-403 framework-level pattern. Don't treat 0-proposal cycles
  as wasted — the substrate evidence and the cross-cycle confirmation
  are real value.



### Added
- **Cycle 215 — UX-048 theme-toggle contract drafted + Phase B PASS.**
  Contract documents reality vs the cycle-213 proposal: it's a
  **two-state user-explicit toggle** (light ↔ dark), NOT a tri-state
  switcher as PROP-048 originally claimed. The system preference
  (`prefers-color-scheme`) is consulted only as a default seed when
  localStorage has no stored value. Phase B against simple_task:
  `fitness run [admin:40698edc, member:138ebeb6]: 73 findings (36/37),
  degraded=False`.
- **Headline finding: cross-shell sync is broken.** The marketing shell
  uses `localStorage.dz-theme-variant` (vanilla JS in
  `runtime/static/js/site.js`), the in-app shell uses
  `localStorage.dz-dark-mode` (Alpine `$persist` in `app_shell.html`).
  Both write `<html data-theme>` but neither reads the other's key. A
  user toggles dark on the marketing site, logs in, and the app shell
  silently defaults to light. The cycle-213 proposal claimed "single
  source of truth" — that was aspirational, not reality. v2 must
  consolidate to a single key + controller.
- 5 quality gates (toggle attribute swap, persistence within a shell,
  system seed for marketing only, stored pref overrides system, two
  distinct localStorage keys documented as current-broken-state),
  9 v2 open questions led by the cross-shell sync gap and missing
  `aria-pressed`.

### Agent Guidance
- **Contracts must document reality, not the proposal.** Cycle 213's
  PROP-048 claimed tri-state with a single source of truth. The actual
  code is two-state with two stores. The contract describes what
  exists today and flags the divergence as the v2 priority. Future
  cycles should follow this pattern: read the implementation first,
  write the contract against it, list the gaps in Open Questions.



### Added
- **Cycle 214 — triage + UX-047 feedback-widget contract + Phase B PASS.**
  Combined housekeeping + work cycle. Triaged PROP-047 and PROP-048 (the
  cycle 213 explore findings) into UX-047 and UX-048 PENDING rows, then
  immediately drafted the contract for UX-047 feedback-widget and ran
  Phase B against simple_task. The contract documents the **vanilla-JS
  module** at `runtime/static/js/feedback-widget.js` — no Alpine, no
  HTMX, all DOM construction via `document.createElement` for security,
  dedicated CSS file at `runtime/static/css/feedback-widget.css`.
  Auto-captures page snapshot + nav history + JS errors at submit time.
  Rate-limited 10/hour via localStorage with a 24h retry queue for
  failed submits. Phase B against simple_task:
  `fitness run [admin:6fdba764, member:4f8f6262]: 71 findings (36/35),
  degraded=False`. 5 quality gates, 10 v2 open questions including
  ARIA modal semantics, radiogroup chip ARIA, focus trap, live region
  on toast, toast unification with UX-013, DSL-configurable categories,
  screenshot upload, role-based visibility, page-snapshot privacy
  redaction.
- **First explore→triage→specify→QA chain on the new substrate.**
  Cycle 213 found PROP-047, cycle 214 promoted + drafted + verified it
  in a single iteration. UX-048 theme-toggle is now PENDING for the
  next cycle.

### Agent Guidance
- **The /ux-cycle skill's Step 1 doesn't pick up PROP-NNN rows.** When
  cycle N runs Step 6 EXPLORE and produces PROPs, cycle N+1 needs an
  explicit triage step before Step 1 has anything to work on.
  Otherwise the loop runs Step 6 indefinitely and the backlog
  accumulates untriaged PROPs (the failure mode cycle 200 was created
  to prevent). Until /ux-cycle gains a built-in triage step, the
  pattern is: explore N → manual triage (PROP→UX) → /ux-cycle picks
  the new UX-NNN.



### Added
- **Cycle 213 — first explore cycle past the UX-037..046 milestone.**
  Subagent walked `simple_task` as the `member` persona using the
  `missing_contracts` strategy. 11 helper calls, ~74k subsidised tokens,
  207s wall-clock. Surfaced **2 proposals + 2 observations** ingested
  via `ingest_findings`:
  - `PROP-047 feedback-widget` — `dz-feedback-*` floating FAB + popover
    with chip-group category/severity inputs and submit lifecycle.
    Rendered on every authed layout.
  - `PROP-048 theme-toggle` — `#dz-theme-toggle` tri-state persistent
    theme switcher shared across marketing and authed shells.
  - `EX-008 (notable)` — `/app/task/1` 404 renders the public marketing
    chrome ("Sign In", "Go Home") even when the session is still valid.
    Cross-app convergence with cycle-201 EX-003 (same defect in
    support_tickets) — now confirmed at the **framework level**, not a
    per-app issue.
  - `EX-009 (notable)` — Task create form renders `due_date` and
    `assigned_to` as plain `<input>` elements rather than the
    `widget-datepicker` / `widget-search-select` widgets. DSL author
    expectation vs framework form-generation gap. Same shape as the
    cycle-199 manager observation against support_tickets.

### Agent Guidance
- **Cross-app cross-cycle convergence is the highest-quality signal.**
  Two separate subagents, two different apps, same defect: the 404/403
  marketing-chrome behaviour is now confirmed as a framework-level bug,
  not a support_tickets quirk. Same for the form-widget-selection gap.
  Both are stronger candidates for filing as upstream issues than any
  single-cycle finding.



### Added
- **Cycle 212 — UX-046 bulk-action-bar contract drafted + Phase B PASS.**
  Final cycle-198+ subagent-discovered row to reach DONE. `bulkCount`-driven
  visibility with enter/leave transitions, count-pluralised
  "Delete N item(s)" + "Clear selection" escape, parent-controller-owned
  state, muted destructive treatment (8% bg-tint hover, not filled).
  Phase B against support_tickets:
  `fitness run [admin:424f981a, agent:acb76a1d]: 91 findings (43/48),
  degraded=False`. 5 quality gates, 9 v2 open questions including
  Escape-to-clear, live region, in-flight loading state, built-in
  confirmation, multi-action support, selection persistence across
  pagination, select-all-matching, position variant (inline vs
  fixed-bottom), and undo affordance.

### **MILESTONE — UX-037..046 set complete**

All ten cycle-198+ subagent-discovered UX rows are now `DONE / qa:PASS`.
The full `/ux-cycle` substrate has been proven end-to-end on real
content: explore → ingest → triage → SPECIFY → QA, repeated for ten
distinct components across `support_tickets` and `contact_manager`.

| Row | Component | Cycle DONE | Canonical |
|---|---|---|---|
| UX-037 | workspace-detail-drawer | 205 | contact_manager |
| UX-038 | workspace-card-picker | 206 | support_tickets |
| UX-039 | workspace-tabbed-region | 207 | support_tickets |
| UX-040 | kanban-board | 204 | support_tickets |
| UX-041 | column-visibility-picker | 208 | support_tickets |
| UX-042 | activity-feed | 209 | support_tickets |
| UX-043 | inline-edit | 203 | support_tickets |
| UX-044 | dashboard-region-toolbar | 210 | support_tickets |
| UX-045 | dashboard-edit-chrome | 211 | support_tickets |
| UX-046 | bulk-action-bar | 212 | support_tickets |

The next `/ux-cycle` invocation will fall through Step 1's PENDING
priority and enter Step 6 EXPLORE (or hit the explore budget short-circuit
if the session counter is exhausted).

## [0.55.23] - 2026-04-15

### Added
- **Cycle 211 — UX-045 dashboard-edit-chrome contract drafted + Phase B PASS.**
  Five-state save lifecycle (clean / dirty / saving / saved / error) with
  state-driven `:class` binding on the Save button, Reset button, and
  Add Card affordance opening the UX-038 picker. Treats the top-of-grid
  Reset+Save toolbar and the bottom-of-grid Add Card button as one
  composite component because they share the same `saveState` flag.
  Phase B against support_tickets:
  `fitness run [admin:af51414a, agent:e95819ab]: 88 findings (44/44),
  degraded=False`. 5 quality gates, 9 v2 open questions including the
  cycle-199 cross-persona "Saved" label ambiguity (flagged by both the
  agent and manager personas), missing live region for save-state
  announcements, missing `aria-expanded` on Add Card trigger, Reset
  confirmation dialog, auto-save, save shortcut key, multi-step undo,
  and a confirm-on-leave navigation guard. Ninth cycle-198+
  subagent-discovered row to DONE. **One row remaining (UX-046
  bulk-action-bar).**



### Added
- **Cycle 210 — UX-044 dashboard-region-toolbar contract drafted + Phase B PASS.**
  Per-region toolbar (title + region-actions + CSV export + multi-filter
  `<select>` bar) that recurs above each workspace region body. HTMX
  `hx-include="closest .filter-bar"` ties multi-filter coordination
  together. No Alpine. Phase B against support_tickets:
  `fitness run [admin:42c1d3cf, agent:1c6f1a9d]: 99 findings (50/49),
  degraded=False`. 5 quality gates, 8 v2 open questions. **Notable
  discrepancy with cycle 199 proposal:** the manager-persona observation
  mentioned a collapse/expand eye button but the current code has no
  such affordance — flagged for v2 to decide. Eighth cycle-198+
  subagent-discovered row to DONE.



### Added
- **Cycle 209 — UX-042 activity-feed contract drafted + Phase B PASS.**
  Vertical left-border timeline `<ul>` with primary-coloured bullet
  markers and a relative-time column. Server-rendered, no Alpine,
  optional HTMX click-to-drawer when `action_url` is configured.
  Three-step display-field fallback chain (`description` → `action`
  → `title`). Phase B against support_tickets:
  `fitness run [admin:35d368e4, agent:cdc0c4ae]: 97 findings (48/49),
  degraded=False`. 5 quality gates, 8 v2 open questions including
  severity-tinted bullets, keyboard accessibility (entries are
  `<div>` not `<button>`), drawer auto-open, time-format
  pluggability. Seventh cycle-198+ subagent-discovered row to DONE.



### Added
- **Cycle 208 — UX-041 column-visibility-picker contract drafted + Phase B PASS.**
  ARIA `role="menu"` + `role="menuitemcheckbox"` popover dropdown
  triggered by a "Columns" button in the data-table header. Conditional
  render guarded by `>3 columns`, parent-controller-owned state, no
  server endpoints. Phase B against support_tickets:
  `fitness run [admin:c79c3a35, agent:cea9824b]: 93 findings (45/48),
  degraded=False`. 5 quality gates, 8 v2 open questions including the
  cycle-199-flagged hardcoded threshold (EX-006), missing persistence,
  Escape close, and arrow-key navigation. Sixth cycle-198+
  subagent-discovered row to DONE.



### Added
- **Cycle 207 — UX-039 workspace-tabbed-region contract drafted + Phase B PASS.**
  ARIA `role="tablist"` strip with eager-load on the first tab and
  `intersect once` lazy load on the rest, DOM-classList state (no
  Alpine), inline onclick handler. Phase B against support_tickets:
  `fitness run [admin:2d196ba9, agent:f718e131]: 95 findings (47/48),
  degraded=False`. 5 quality gates, 7 v2 open questions including a
  significant accessibility cluster (anchors not keyboard-focusable,
  missing `aria-selected`, missing `role="tabpanel"`, missing live
  region). Fifth cycle-198+ subagent-discovered row to DONE.



### Added
- **Cycle 206 — UX-038 workspace-card-picker contract drafted + Phase B PASS.**
  Pure-presentation Alpine popover catalog over a server-supplied
  `catalog` array, parent-owned state model (`showPicker`, `catalog`,
  `addCard` on the dashboard editor controller). 5 quality gates,
  7 v2 open questions (ARIA `role="menu"`, focus management, Escape,
  auto-close after add, search filter, keyboard nav, position
  fallback). Phase B against support_tickets:
  `fitness run [admin:569bad2e, agent:e3af653e]: 93 findings (44/49),
  degraded=False`. Fourth cycle-198+ subagent-discovered row to DONE.



### Added
- **Cycle 205 — UX-037 workspace-detail-drawer contract drafted + Phase B PASS.**
  Contract at `~/.claude/skills/ux-architect/components/workspace-detail-drawer.md`:
  permanently-mounted right-anchored drawer with a plain-JS `window.dzDrawer`
  imperative API (no Alpine), three-way interaction model (close /
  expand-to-full / internal-navigate), HTMX content slot at
  `#dz-detail-drawer-content`. 5 quality gates (open via API, Esc close,
  backdrop close, internal-link interception, expand-href update),
  7 v2 open questions including the `href="#"` accessibility gap that
  cycle 198 originally flagged. Phase B against contact_manager:
  `fitness run [admin:562dddac, user:1dc5de59]: 20 findings (10/10),
  degraded=False`. Both personas reached the workspace anchor.



### Added
- **Cycle 204 — UX-040 kanban-board contract drafted + Phase B PASS.**
  Contract at `~/.claude/skills/ux-architect/components/kanban-board.md`:
  read-only horizontally-scrolling column board grouped by enum field,
  HTMX-into-`workspace-detail-drawer` on card click (no drag-and-drop
  in v1), Load-all overflow handling, server-owned state. Inherits
  card chrome from `region-wrapper` (UX-035). 5 quality gates
  (multi-column rendering, card→drawer routing, ref-link
  stopPropagation, Load-all reload, empty-state passthrough), 6 v2
  open questions deferred (card semantics for accessibility,
  horizontal keyboard scroll, drag-and-drop, non-enum grouping, WIP
  limits, scroll-position memory).
- **UX-040 advanced to `DONE / qa:PASS`** via the same Phase B
  fitness contract walk pattern cycle 203 used for UX-043:
  `fitness run [admin:06eae945, agent:ff320c65]: 102 findings total
  (admin=51, agent=51), degraded=False`. Both personas reached
  `/app/workspaces/ticket_queue` and the walker completed cleanly.
  Second cycle-198+ subagent-discovered row to reach DONE.

### Agent Guidance
- **Drafting a contract from existing code is a tight loop.** Cycle
  204 took ~10 minutes wall-clock from "find the template" to "Phase
  B PASS shipped" because the implementation already matched the
  contract semantics — only the documentation was missing. When
  drafting future contracts for cycle 200's promoted rows, look for
  this pattern: read the template, describe what it does, run Phase
  B, ship.

## [0.55.15] - 2026-04-15

### Changed
- **Cycle 203 — UX-043 inline-edit Phase B PASS, advanced to DONE.**
  Multi-persona fitness-engine contract walk against `support_tickets`
  with `personas=["admin", "agent"]`:
  `fitness run [admin:f9c7e3c1, agent:0e8a0f37]: 88 findings total
  (admin=41, agent=47), degraded=False`. PASS under the cycle-156
  `degraded`-based rule — the 88 findings are Pass 2a story_drift /
  spec_stale observations from `support_tickets`'s overall app
  health, orthogonal to the contract walk. The walker (`walk_contract`)
  itself emits zero findings; it only records ledger steps. Both
  personas reached the inline-edit anchor (`/app/ticket`) and the
  walker completed cleanly.
- **First cycle-198+ subagent-discovered UX row to reach `DONE`.**
  Full chain executed in this session: cycle 199 explore (proposal)
  → cycle 200 triage (PROP-043 → UX-043) → cycle 202 contract draft
  → cycle 203 Phase B PASS. The `/ux-cycle` substrate is now end-to-end
  proven for at least one component.

### Agent Guidance
- **Phase B is `degraded`-based, not `findings_count`-based.** The
  cycle 156 fix established this rule; cycle 203 is the first time
  it's been applied to a brand-new contract walked for the first
  time. 88 fitness findings sound alarming but the walker emitting
  zero of them is what matters. Don't fail a row on `findings_count`.

## [0.55.14] - 2026-04-15

### Added
- **Cycle 202 — first contract drafted for a cycle-199/200 promoted row.**
  `UX-043 inline-edit` has a contract at
  `~/.claude/skills/ux-architect/components/inline-edit.md` (in the
  ux-architect skill, not the Dazzle repo). Scope: 4 field types
  (text / bool / badge / date), mutually-exclusive `editing` state on
  the `dzTable` Alpine controller, phase-based lifecycle
  (display → editing → saving → success/error). Includes 5 testable
  quality gates (activation, mutual exclusion, commit round-trip,
  error retry, keyboard-only completion) and a documented server
  contract (`PATCH /api/{entity}/{id}/field/{col}`).
- `UX-043` status in `dev_docs/ux-backlog.md` advanced:
  `PENDING / contract:MISSING / impl:PENDING / qa:PENDING` →
  `READY_FOR_QA / contract:DONE / impl:DONE / qa:PENDING`. `impl:DONE`
  because existing code in `fragments/inline_edit.html`,
  `fragments/table_rows.html`, and `dz-alpine.js` already matches
  the drafted contract — the contract was written to reflect current
  behaviour, not to drive a refactor. First UX-037..046 row to advance
  past PENDING.

### Agent Guidance
- **Draft contracts against the existing implementation when possible.**
  When a component already exists in code (as `inline-edit` did), the
  contract should describe current behaviour rather than propose a
  rewrite — that way `impl:DONE` can be set in the same cycle and the
  row advances straight to READY_FOR_QA. Only mark `impl:PENDING` if
  the current code genuinely needs a refactor to match the contract.
- **Open questions belong in the contract.** Things that are
  deliberately deferred (refocus-after-reload, confirm-mode for
  selects/checkboxes, optimistic updates, bulk-edit, hint tooltips
  for inline-edit) live in the contract's "Open Questions for vNext"
  section. They are not implementation TODOs — they are design
  decisions the v1 contract explicitly declines to make.

## [0.55.13] - 2026-04-15

### Changed
- **Cycle 201 defects filed as GitHub issues.** The two concerning-severity
  observations from cycle 201's edge_cases run against `support_tickets`
  have been filed outside the UX backlog:
  - [#774](https://github.com/manwithacat/dazzle/issues/774) — silent create-form failure on `/app/ticket/create`. Root cause identified: the `ticket_create` surface omits `created_by: ref User required` (from the `Ticket` entity on line 64 of `examples/support_tickets/dsl/app.dsl`), so the backend rejects submissions, and the UI doesn't surface the error. Matches historical cycle 110/126/137 observations about the same underlying bug.
  - [#775](https://github.com/manwithacat/dazzle/issues/775) — sidebar nav shows workspace links that the current persona cannot actually access (403). Cross-persona confirmed: cycle 199 manager run and cycle 201 agent run independently flagged this.
- Updated `EX-002` and `EX-007` rows in `dev_docs/ux-backlog.md` with
  `FILED→#NNN` status and issue cross-links so future diagnosticians can
  trace the backlog row to the upstream issue.

### Agent Guidance
- **Edge-case findings that are real defects belong in GitHub issues,
  not the UX backlog.** The UX backlog is for components to bring under
  ux-architect governance; edge-case findings that turn out to be
  genuine app-level bugs should be promoted to issues with a
  `FILED→#NNN` breadcrumb in the backlog row.

## [0.55.12] - 2026-04-15

### Added
- **`select` action for `playwright_helper`.** The stateless Playwright
  driver used by subagent-driven explore runs can now drive `<select>`
  elements. Signature:
  `python -m dazzle.agent.playwright_helper --state-dir DIR select '<selector>' '<value>'`.
  Attempts to match `value` as an option `value` attribute first; on
  failure, falls back to matching as a visible label. Returns
  `matched_by: "value" | "label"` so callers know how the option was
  resolved.
- Driven by the cycle 201 edge_cases run against `support_tickets` —
  the subagent explicitly flagged that it couldn't drive `<select>`
  elements, which blocked root-causing the silent create-form failure
  (finding EX-007). With this action in place, the next edge_cases
  run can fully exercise forms that use `<select>` for Priority,
  Category, or any DSL enum field.
- 3 new unit tests in `tests/unit/agent/test_playwright_helper.py`
  covering the value-first happy path, the label fallback, and the
  double-failure error shape (17 tests total).

### Agent Guidance
- **Use `select` instead of `click` for `<select>` elements.** Clicking
  a `<select>` opens the native picker but doesn't let the caller
  choose an option. `select '<selector>' '<value>'` resolves the
  option deterministically.

## [0.55.11] - 2026-04-15

### Changed
- **Cycle 201 — first production `edge_cases` explore run.** Ran
  the strategy shipped in v0.55.8 against `support_tickets/agent`
  using the `ingest_findings` writer shipped in v0.55.9. End-to-end
  dogfooding of the full explore-ingest pipeline. The subagent
  surfaced 6 observations (2 concerning, 3 notable, 1 minor) and
  `ingest_findings` wrote them as `EX-002..007` in one call without
  hand-editing.
- The concerning-severity findings include a **suspected silent
  create-form failure** on `/app/ticket/create` (EX-007) — filling
  Title + Description and clicking Create produces no toast, no URL
  change, no state-change signal, and the ticket list still reads
  "No items found" afterwards. Potential data-loss dead-end on the
  support agent's core workflow.
- Three findings cross-confirmed earlier persona-runs (sidebar RBAC
  mismatch, dead `Open full page` affordance, free-text Assigned-To
  field), strengthening the signal on those issues independently of
  any single LLM's interpretation.

### Agent Guidance
- **The `ingest_findings` writer is proven in production.** Future
  `/ux-cycle` Step 6 runs should call it directly instead of
  hand-writing PROP/EX rows. First-try success: schema matched the
  hand-written cycle 199 rows byte-for-byte in the relevant columns.
- **`edge_cases` strategy produces observations, not proposals.**
  Cycle 201 wrote 0 proposals and 6 observations — exactly the shape
  the strategy section promises. Don't run `edge_cases` if you're
  trying to grow the contract backlog; run it if you're trying to
  surface friction on existing surfaces.
- **Follow-up: `playwright_helper` lacks a `select` action.** The
  subagent explicitly called this out as a mission-limiting gap —
  it couldn't drive `<select>` elements, which blocked isolation of
  the EX-007 silent-submit root cause. Worth adding in a later
  cycle.

## [0.55.10] - 2026-04-15

### Changed
- **Cycle 200 triage: 10 PROP rows promoted to UX-037..046.** All ten
  proposals produced by cycles 198+199 (`workspace-detail-drawer`,
  `workspace-card-picker`, `workspace-tabbed-region`, `kanban-board`,
  `column-visibility-picker`, `activity-feed`, `inline-edit`,
  `dashboard-region-toolbar`, `dashboard-edit-chrome`,
  `bulk-action-bar`) passed the three overlap tests — no existing
  contract subsumes them, no two proposals collapse into one, and the
  two that are popover consumers (`column-visibility-picker`,
  `workspace-card-picker`) warrant their own contracts for drift
  prevention. Each `PROP-NNN` row in
  `dev_docs/ux-backlog.md` is now marked `PROMOTED→UX-NNN`, and the
  ten new `PENDING / contract:MISSING` rows sit at the top of the
  `/ux-cycle` Step 1 priority queue for the next cycle.

### Agent Guidance
- **The explore/triage ratio matters.** Cycles 198+199 produced 10
  proposals in 4 persona-runs; cycle 200 triaged them in one pass.
  Don't run another fan-out until the triage queue has been worked
  down at least to first-draft contracts — otherwise the backlog
  just accumulates untriaged noise.

## [0.55.9] - 2026-04-15

### Added
- **`subagent_ingest` helper — automates `/ux-cycle` Step 9 backlog
  writes.** New module
  `src/dazzle/cli/runtime_impl/ux_cycle_impl/subagent_ingest.py`
  exposes `PersonaRun`, `IngestionResult`, and `ingest_findings(...)`.
  Takes a list of per-persona `SubagentExploreFindings`, parses the
  existing `dev_docs/ux-backlog.md` to find the highest existing
  `PROP-NNN` and `EX-NNN` IDs, dedupes proposals by `component_name`
  against the existing table, formats new rows (escaping pipes,
  flattening multi-line descriptions), and appends them after the
  last existing data row in each table. Callers get back an
  `IngestionResult` with added row counts, dedup skips, and
  warnings.
- **13 unit tests** in `tests/unit/test_subagent_ingest.py` covering
  ID allocation, in-call dedup, cross-cycle dedup, row formatting,
  pipe escaping, multi-line flattening, empty-input no-ops,
  single-persona proposals-only runs, and insertion-order
  preservation against unrelated sections.

### Changed
- **`.claude/commands/ux-cycle.md` Step 9 rewritten** to call
  `ingest_findings(...)` from a one-shot `python -c` block instead of
  narrating the manual "find the next ID, write a row, dedup by name"
  dance. The log entry (`ux-log.md`) is still written by hand —
  interpretive prose doesn't benefit from automation.

### Agent Guidance
- **When walking the `/ux-cycle` Step 6 playbook, use
  `ingest_findings` instead of hand-writing backlog rows.** It's
  faster, dedups correctly, and produces consistently-formatted rows
  that the next cycle's ingestion will parse without surprises.

## [0.55.8] - 2026-04-15

### Added
- **`edge_cases` strategy for `build_subagent_prompt`.** Second
  strategy for the cycle-198 subagent-driven explore path. Where
  `missing_contracts` hunts for uncontracted component patterns, the
  `edge_cases` strategy directs the subagent to probe friction and
  defects: empty/error/boundary states, dead-end navigation,
  affordance mismatches (clickable-looking elements that do nothing,
  spinners that never resolve), copy/persona mismatches, and stale
  post-navigation state. Output skews toward observations rather than
  proposals, with explicit severity guidance (concerning / notable /
  minor).
- Strategy dispatch is now validated: unknown strategy literals raise
  `ValueError` with a clear message. Previously the module raised
  `NotImplementedError` unconditionally for anything other than
  `missing_contracts`.
- Test coverage expanded: 6 new tests in
  `tests/unit/agent/test_ux_explore_subagent.py` covering edge-case
  section content, observation-skewing guidance, strategy
  non-bleed-through, and the ValueError path (16 tests total, all
  passing).

### Changed
- `.claude/commands/ux-cycle.md` Strategy Rotation section — removed
  the "not yet implemented, falls back to missing_contracts"
  disclaimer for even-numbered explore cycles. Even cycles now
  actually run the edge_cases strategy.

### Agent Guidance
- **Even-numbered explore cycles now run the `edge_cases` strategy**
  for real. If you're orchestrating `/ux-cycle` from the runbook,
  pass `strategy="edge_cases"` to `build_subagent_prompt` on even
  counts and expect the subagent's findings to be mostly
  observations, not proposals.

## [0.55.7] - 2026-04-15

### Removed
- **Cycle 197 explore path retired.** Deleted ~2100 lines of dead code
  that supported the pre-cycle-198 DazzleAgent-on-SDK explore path.
  Specifically:
  - `src/dazzle/cli/runtime_impl/ux_cycle_impl/explore_strategy.py`
    (480 lines) — the `run_explore_strategy` entry point and the
    `ExploreOutcome` dataclass.
  - `src/dazzle/agent/missions/ux_explore.py` (222 lines) — the
    `build_ux_explore_mission`, `make_propose_component_tool`, and
    `make_record_edge_case_tool` helpers. Not to be confused with
    `ux_explore_subagent.py`, which is the live subagent path added
    in 0.55.5.
  - `src/dazzle/mcp/server/handlers/discovery/explore_spike.py` (192
    lines) — the cycle-198 Path-γ MCP-sampling spike handler. The
    spike proved Claude Code doesn't implement `sampling/createMessage`,
    so the handler is no longer useful.
  - The `discovery.explore` MCP operation, its enum entry, and its
    parameter schema in `tools_consolidated.py` / `handlers_consolidated.py`.
  - Four test files: `tests/unit/test_explore_strategy.py`,
    `tests/unit/test_ux_explore_mission.py`,
    `tests/unit/mcp/test_discovery_explore_spike.py`, and
    `tests/e2e/test_explore_strategy_e2e.py`.
- The live explore path is now the subagent-driven playbook documented
  in `.claude/commands/ux-cycle.md` Step 6, which uses
  `src/dazzle/agent/missions/ux_explore_subagent.py` and
  `src/dazzle/cli/runtime_impl/ux_cycle_impl/subagent_explore.py`.
  The fitness strategy (`fitness_strategy.run_fitness_strategy`) is
  unaffected and still uses `_playwright_helpers.py`.

### Agent Guidance
- **The `discovery` MCP tool now exposes only the `coherence`
  operation.** If you need explore, use the subagent-driven playbook
  via `/ux-cycle` Step 6 — not an MCP operation.

## [0.55.6] - 2026-04-15

### Added
- **Cycle 199 — multi-persona fan-out validated.** Walked the cycle 198
  subagent-driven explore playbook three times against
  `examples/support_tickets`, once per business persona (agent, customer,
  manager). Result: **9 non-overlapping proposal candidates**
  (`PROP-038..046`) plus 7 observations, including two cross-persona
  convergences (workspace save-state label ambiguity; RBAC nav/scope
  inconsistency). Total subsidised cost: ~223k tokens across 40 helper
  calls in 801s wall-clock — roughly 3× a single-persona run with zero
  hidden multipliers. The `existing_components` filter was fed each
  persona the running set of contracts already proposed in the cycle so
  later personas didn't duplicate earlier ones; zero duplicates across
  9 proposals.
- **9 new `PROP-NNN` rows** in `dev_docs/ux-backlog.md`:
  `workspace-card-picker`, `workspace-tabbed-region`, `kanban-board`,
  `column-visibility-picker`, `activity-feed`, `inline-edit`,
  `dashboard-region-toolbar`, `dashboard-edit-chrome`, `bulk-action-bar`.
  Each includes a specific selector hint, the persona that found it,
  and a rationale for why existing contracts don't cover it.

### Agent Guidance
- **Multi-persona fan-out is a playbook concern, not a code concern.**
  `init_explore_run(persona_id=...)` + `playwright_helper login <persona>`
  is the entire per-persona setup. No shared-state races, no state-dir
  clobbering. Each run gets its own `dev_docs/ux_cycle_runs/<example>_<persona>_<run_id>/`.
- **Pass the running set of proposed components into
  `build_subagent_prompt(existing_components=...)`** on each subsequent
  persona-run in a cycle, so later personas don't re-propose what
  earlier personas already found.

## [0.55.5] - 2026-04-15

### Added
- **Cycle 198 — substrate pivot for `/ux-cycle` Step 6 EXPLORE.** Replaces the
  DazzleAgent-on-direct-SDK explore path with a Claude Code Task-tool subagent
  driving a stateless Playwright helper via Bash. Cognitive work runs inside
  the Claude Code host subscription (Max Pro 20) — the metered Anthropic SDK
  is eliminated from the explore path.
- **`src/dazzle/agent/playwright_helper.py`** — stateless one-shot Playwright
  driver. Actions: `login`, `observe`, `navigate`, `click`, `type`, `wait`.
  Each call is a subprocess that loads state (storage_state + base_url +
  last_url) from `--state-dir`, performs one action, and saves state back.
  Session cookies persist across calls. Subagent consumers drive it via Bash.
- **`src/dazzle/agent/missions/ux_explore_subagent.py`** —
  `build_subagent_prompt(...)` parameterised mission template. Cycle 198
  ships `missing_contracts` only; `edge_cases` raises `NotImplementedError`
  pending a later cycle.
- **`src/dazzle/cli/runtime_impl/ux_cycle_impl/subagent_explore.py`** —
  `init_explore_run`, `ExploreRunContext`, `read_findings`,
  `write_runner_script`. Small composable helpers the outer assistant uses
  to stage state, boot ModeRunner, and read findings. No async orchestrator
  function — Claude Code's Task tool is only reachable from the assistant's
  cognitive loop, so the playbook is assistant-driven.
- **First real `PROP-037` backlog row** — `workspace-detail-drawer`, found by
  the production subagent run against `contact_manager` with persona `user`.
  92k subsidised tokens, 18 helper calls, 416s wall-clock.

### Changed
- **`.claude/commands/ux-cycle.md` Step 6 rewritten** as a 10-step
  subagent-driven playbook. Removed all references to `run_explore_strategy`,
  `DazzleAgent`, and `ANTHROPIC_API_KEY` from the explore path. Claude Code
  host is now a hard dependency for Step 6 (not for walk_contract or fitness,
  which still use DazzleAgent).

### Agent Guidance
- **`/ux-cycle` Step 6 EXPLORE requires a Claude Code host session.** The
  substrate pivot replaces DazzleAgent's `observe → decide → execute` loop
  with Claude Code's built-in Task-tool agent framework. Running Step 6 from
  a non-Claude-Code environment (raw pytest, CI runner without an MCP host)
  is not supported in cycle 198 and won't be until a later cycle decides
  whether to generalise.
- **Stateless Playwright helper pattern for browser-driving subagents.** When
  a mission prompt needs a subagent to interact with a running app, reach
  for `python -m dazzle.agent.playwright_helper --state-dir DIR <action>`
  rather than building a new observer/executor stack. The one-shot
  subprocess pattern (storage_state file + last_url file) is the
  load-bearing trick that lets a stateless Bash-driven subagent maintain
  session continuity.
- **`run_explore_strategy` (the cycle 197 DazzleAgent-based explore driver)
  still exists but is deprecated for explore.** It's kept to avoid breaking
  `tests/e2e/test_explore_strategy_e2e.py` during the migration. Cycle 199
  decides whether to delete it entirely.
- **44 new unit tests cover the substrate.** None use Playwright or launch
  real browsers — the walk-the-playbook production test is the acceptance
  check.

## [0.55.4] - 2026-04-15

### Fixed
- **Cycle 197 — Layer 4 (agent click-loop) structurally resolved.** DazzleAgent
  now sees an explicit state-change signal on every action via the new
  `ActionResult.from_url` / `to_url` / `state_changed` fields, plus action-linked
  console errors via `console_errors_during_action`. `_build_messages` renders
  these in the compressed history block so the LLM sees "NO state change (still
  at /app)" instead of the ambiguous "Clicked X" message. A bail-nudge block is
  appended when 3 consecutive no-ops are detected, explicitly telling the LLM to
  try a different action or call `done`. Verified across 5 example apps with 11
  persona-runs: every run stagnates legitimately (no click-loops) with
  `degraded=False`.

### Added
- **`src/dazzle/agent/executor.py`**: `PlaywrightExecutor` captures before/after
  page state (URL + DOM hash) around every action, attaches a `page.on("console")`
  listener that buffers error-level messages, and diff-slices the buffer into
  each `ActionResult.console_errors_during_action` for action→error attribution.
- **`src/dazzle/agent/core.py`**: module-level pure helpers `_format_history_line`
  and `_is_stuck` (with 12 unit tests), wired into `_build_messages` alongside
  the bail-nudge.
- **`src/dazzle/cli/runtime_impl/ux_cycle_impl/explore_strategy.py`**:
  `pick_explore_personas(app_spec, override=None)` auto-picks business personas
  by filtering out those whose `default_workspace` starts with `_` (framework-
  scoped). `pick_start_path` delegates to `compute_persona_default_routes` for
  per-persona start URLs. `_dedup_proposals` merges proposals by
  `(example_app, component_name)` with a `contributing_personas` list.
  `ExploreOutcome` gains `raw_proposals_by_persona: dict[str, int]` for
  pre-dedup stats.
- **`tests/e2e/test_explore_strategy_e2e.py`**: parametrised D2 verification
  sweep across 5 examples, marked `@pytest.mark.e2e` (excluded from default
  pytest, run manually with `pytest -m e2e`). Writes outcome JSON artefacts to
  `dev_docs/cycle_197_verification/` (gitignored).

### Changed
- **`run_explore_strategy` semantics** (breaking): `personas=None` now
  auto-picks business personas from the DSL (was: anonymous). `personas=[]` is
  the new explicit anonymous escape hatch. `personas=["admin"]` is unchanged.
  `start_path` is now `str | None = None` — if None, each persona gets its
  DSL-computed default route; if provided, that value is used for all personas.
  Aggregated proposals are routed through `_dedup_proposals` at the end.

### Agent Guidance
- **Mission tools must not name-collide with builtin page actions.** As of
  v0.55.2 `DazzleAgent` exposes 8 builtin page actions (navigate/click/type/
  select/scroll/wait/assert/done) as native SDK tools. A mission registering
  `click` (or any builtin name) will have its tool silently dropped with a
  warning — pick a domain-specific name like `click_record_row`.
- **Callers who want anonymous explore must explicitly pass `personas=[]`.**
  Passing `personas=None` now auto-picks business personas from the DSL.
  Existing callers that relied on the old `None → anonymous` semantics need
  updating.
- **Layer 5 known gap (cycle 197 verification).** The Layer 4 fix shipped in
  this release resolved the click-loop pathology, but verification exposed a
  deeper blocker: LLM agents under-invoke `propose_component` even when
  infrastructure permits it. 11 persona-runs across 5 examples produced 0
  proposals despite reaching target pages, taking real actions, and receiving
  state-change feedback. Tracked for cycle 198 follow-up — candidate fixes
  include rewriting the bail-nudge to push toward recording (rather than
  exploration), lowering the stagnation threshold, and A/B testing the
  `ux_explore` mission prompt.

## [0.55.3] - 2026-04-14

### Fixed
- **Integration test assertion stale after v0.55.2 builtin-action merge.**
  `tests/integration/test_agent_investigator_tool_use.py::test_nested_changes_array_arrives_intact`
  asserted `len(call_kwargs["tools"]) == 1` against the `_decide_via_anthropic_tools`
  tools list, which v0.55.2 expanded from "1 mission tool" to "8 builtin page
  actions + 1 mission tool". Two unit tests were updated in the same commit,
  but the integration test was missed by the pre-push local verification
  (`-k "agent or tool_use or explore_strategy or fitness_strategy"` was
  scoped to `tests/unit/`). Fixed by looking up the `propose_fix` entry by
  name and asserting `len == 9`. 10784/10784 Python tests pass. No runtime
  behaviour change from v0.55.2 — the shipped agent code was always correct;
  only the test's expectation was stale.

## [0.55.2] - 2026-04-14

### Fixed
- **DazzleAgent `use_tool_calls=True` page actions were text-protocol only.**
  Before this release, `DazzleAgent(use_tool_calls=True)` exposed mission
  tools as native SDK tools but left page actions (navigate/click/type/
  select/scroll/wait/assert/done) as text-protocol JSON instructions in
  `_build_system_prompt`. The LLM obediently emitted a `navigate` action
  as text JSON, `_decide_via_anthropic_tools` found no `tool_use` block,
  returned a DONE sentinel, and the agent loop exited after 1 step with
  0 actions taken. `walk_contract` dodged this because its anchor
  navigation happens outside the agent loop, but in-loop explore missions
  (`ux_explore` MISSING_CONTRACTS / EDGE_CASES) were completely blocked.

  Fixed by declaring page actions as native SDK tools alongside mission
  tools. New module-level `_BUILTIN_ACTION_NAMES` + `_builtin_action_tools()`
  factory; new `_tool_use_to_action` router that maps builtin-named
  `tool_use` blocks to their matching `ActionType` with target/value/
  reasoning extracted from `block.input`, and mission-tool names to
  `ActionType.TOOL` with `json.dumps(input)` as `value` (matching the
  text-protocol shape so `_execute_tool` consumes it unchanged).
  `_decide_via_anthropic_tools` merges builtin+mission tools into the
  SDK `tools=[...]` parameter; mission tools colliding with builtin
  names are dropped with a warning. `_build_system_prompt` branches on
  `self._use_tool_calls` and suppresses the text-protocol "Available
  Page Actions" block under tool-use mode; legacy text-protocol path
  is untouched. Empirically verified against contact_manager:
  pre-fix = 1 step DONE, post-fix = 8 real click actions via native
  tool use + legitimate stagnation.

### Added
- **`src/dazzle/cli/runtime_impl/ux_cycle_impl/explore_strategy.py` —
  production driver for `/ux-cycle` Step 6 EXPLORE.** Before this release,
  `build_ux_explore_mission` existed in `src/dazzle/agent/missions/ux_explore.py`
  but had no production caller — Step 6 was pointing at a function the
  harness could not actually invoke, and cycle 147's "empirical 0 findings"
  data point was produced via a throwaway `/tmp` script. `run_explore_strategy`
  mirrors `run_fitness_strategy`'s structure: caller owns ModeRunner, strategy
  owns Playwright + per-persona login + agent mission + aggregation. Returns
  an `ExploreOutcome` with flat `proposals` / `findings` lists tagged by
  `persona_id`, plus `blocked_personas` for per-persona failures; all-blocked
  raises `RuntimeError`.
- **`src/dazzle/cli/runtime_impl/ux_cycle_impl/_playwright_helpers.py` —
  shared Playwright bundle + persona-login helpers** extracted from
  `fitness_strategy.py` so `explore_strategy` can reuse `PlaywrightBundle`,
  `setup_playwright`, and `login_as_persona` without duplication.
  `fitness_strategy` re-imports them under the old private names
  (`_PlaywrightBundle` etc.) to preserve existing test patch targets — 23/23
  `test_fitness_strategy_integration` tests pass unchanged.

### Changed
- **`.claude/commands/ux-cycle.md` Step 6 is now actionable.** Replaced the
  vague "Dispatch the `build_ux_explore_mission`" prose with a concrete
  runnable code snippet using `run_explore_strategy` + `ModeRunner`.
  Documented the semantic gate on the 5-cycle-0-findings rule (housekeeping
  cycles that never reached Step 6 must not count toward the streak;
  track via `explored_at` in `.dazzle/ux-cycle-state.json`).

### Agent Guidance
- **`DazzleAgent(use_tool_calls=True)` now exposes 8 builtin page actions
  as native SDK tools.** If you write new agent missions and use the tool-use
  path, you no longer need to instruct the LLM to emit navigate/click/type/
  etc. as text JSON — the SDK tools list carries that contract. The system
  prompt under tool-use mode omits the legacy "Available Page Actions" text
  block entirely; the legacy text-protocol path for `use_tool_calls=False`
  is unchanged.
- **Mission tool names must not collide with builtin page action names.**
  A mission that registers a tool named `click`, `navigate`, `type`, `select`,
  `scroll`, `wait`, `assert`, or `done` will have its mission tool silently
  dropped with a warning — the builtin wins. Pick a domain-specific name
  (e.g. `click_record_row` instead of `click`).
- **Prefer `run_explore_strategy` over inline ModeRunner + DazzleAgent glue
  for `/ux-cycle` Step 6.** The driver handles per-persona login, blocked-
  persona absorption, aggregation, and persona-tagged proposals out of the
  box. See `.claude/commands/ux-cycle.md` Step 6 for the invocation shape.

## [0.55.1] - 2026-04-14

### Security
- **Magic link redirect validator hardened (CodeQL `py/url-redirection`).**
  `consume_magic_link`'s `?next=` query parameter validation was
  upgraded from `startswith("/") and not startswith("//")` string-prefix
  checks to a `urllib.parse.urlparse`-based validator that catches
  backslash-bypass attacks (`/\@evil.com` — browsers normalize `\` to
  `/` per the WHATWG URL spec, potentially turning the path into a
  protocol-relative URL pointing at an attacker-controlled host), as
  well as scheme injection (`http://`, `javascript:`, `data:`) and
  authority smuggling. 29 new parametrised tests in
  `tests/unit/test_magic_link_routes.py` cover the accepted paths,
  protocol-relative rejection, scheme rejection, backslash-bypass
  rejection, and non-absolute-path rejection. CodeQL alert #58 resolved.

### Changed
- **CI: bump `actions/github-script` v8 → v9 and
  `softprops/action-gh-release` v2 → v3.** Applies Dependabot PRs #772
  and #773. Both are major-version bumps but neither breaking change
  affects this project — our workflows use the injected `github` and
  `context` parameters of `github-script` (no `require('@actions/github')`
  or `const getOctokit` patterns) and our runners (`ubuntu-latest`,
  `macos-14`) support Node 24 natively.

## [0.55.0] - 2026-04-14

### Fixed
- **DazzleAgent bug 5a (prose-before-JSON parse failure).** Claude 4.6
  frequently emits reasoning prose before JSON action blocks. The strict
  `json.loads` parser returned DONE/failure on any prose prefix, killing
  missions at step 1 (cycle 147's EXPLORE stagnation was caused by this).
  `_parse_action` is refactored as a three-tier fallback: (1) try
  `json.loads` on the whole response, (2) extract the first balanced
  JSON object via a new `_extract_first_json_object` bracket counter
  and preserve the surrounding prose in the action's `reasoning` field,
  (3) return a DONE sentinel with diagnostic if no balanced JSON found.
  Fixes bug 5a on all text-protocol paths (direct SDK and MCP sampling).

### Added
- **DazzleAgent `use_tool_calls` kwarg.** Opt-in flag that routes agent
  decisions through Anthropic's native tool use API when running on the
  direct SDK path. Fixes bug 5b (nested-JSON-in-tool-values encoding)
  for tools with nested input shapes. When combined with an
  `mcp_session`, logs a one-shot warning and falls back to the text
  protocol (MCP sampling is text-only). Currently enabled only for the
  investigator's `propose_fix` terminal action; all other missions
  keep the default `use_tool_calls=False` and use the now-robust text
  parser.
- **Investigator `propose_fix` native tool use.** The investigator
  runner now constructs `DazzleAgent(use_tool_calls=True)`, and the
  `propose_fix` schema is extracted into a module-level
  `PROPOSE_FIX_SCHEMA` constant with full item constraints on the
  `fixes` array (required `file_path`, `diff`, `rationale`,
  `confidence` on each fix). Anthropic's API enforces the shape at the
  tool_use boundary, eliminating the stringified-JSON-in-string
  reliability problem.

### Agent Guidance
- **Authoring new agent tools:** every `AgentTool` already has a
  required `schema` field. For tools used on the text protocol, the
  schema is informational (appears in the system prompt). For tools
  used with `use_tool_calls=True`, the schema becomes Anthropic's
  `input_schema` and is enforced at the API boundary. When a tool has
  a nested input structure (arrays of objects, etc.), tighten the
  schema's item constraints and flip `use_tool_calls=True` on the
  agent — the text protocol's nested-JSON encoding is unreliable
  under Claude 4.6 (bug 5b).
- **Reasoning preservation principle:** the raw LLM output (prose
  preambles, scratch notes, the JSON's `reasoning` field, text blocks
  on the tool-use path) all land in `AgentAction.reasoning` with a
  `[PROSE]` marker where appropriate. Downstream analysis tasks can
  extract human-readable justifications from this corpus later. Do
  not strip prose from the reasoning field — it is signal, not noise.

## [0.54.5] - 2026-04-14

### Added
- **Fitness investigator subsystem** — agent-led investigation of ranked
  fitness clusters. `dazzle fitness investigate` reads a cluster from
  `fitness-queue.md`, gathers context via six read-only tools (file reads,
  DSL queries, spec search, cluster expansion, related-cluster lookup),
  and writes a structured `Proposal` to `.dazzle/fitness-proposals/`.
  Read-only at the codebase level — applying proposals is a separate
  (future) actor subsystem. See `docs/reference/fitness-investigator.md`.

### Agent Guidance
- The investigator is the Option-3 ship on the path to full autonomous
  fix loops. Proposals are accumulated on disk but not applied until the
  actor subsystem lands. Run `dazzle fitness investigate --dry-run` to
  inspect a case file without burning tokens.
- Known v1 limitation: DazzleAgent's text-action protocol can't reliably
  produce the complex JSON payload for `propose_fix`; stagnation is a
  common outcome in real runs. Tracked for v2.

## [0.54.4] - 2026-04-13

## [0.54.3] - 2026-04-13

### Added
- **Fitness v1.0.3 — contract anchor navigation.** New optional `## Anchor` section in ux-architect component contracts is parsed into `ComponentContract.anchor: str | None`. The fitness strategy navigates the Playwright page to `site_url + anchor` (with leading-slash normalization) before the contract walker observes the component, closing the v1.0.2 "walker observes about:blank" gap. Existing contracts without the section continue to parse cleanly with `anchor=None`.
- **Fitness v1.0.3 — multi-persona fan-out.** New optional `personas: list[str] | None = None` kwarg on `run_fitness_strategy`. When set, the strategy runs one fitness cycle per persona inside a single subprocess lifetime: shared Playwright browser, fresh `browser.new_context()` per persona for cookie isolation, `_login_as_persona` via the QA mode magic-link flow (#768), per-persona `FitnessEngine`, per-persona outcome. When `personas=None` (default), runs a single anonymous cycle (v1.0.2 backwards compatibility preserved by construction).
- **`_login_as_persona` helper** at `src/dazzle/cli/runtime_impl/ux_cycle_impl/fitness_strategy.py` — two-step Playwright-driven login reusing the QA mode endpoints from #768. Distinguishes three failure modes with targeted error messages: 404 (QA mode disabled OR persona not provisioned), other non-2xx (generation failed), post-consume URL contains `/login` or `/auth/login` (token rejected).
- **`_aggregate_outcomes` helper** reduces per-persona results into a single `StrategyOutcome`. Single-persona format matches v1.0.2 exactly; multi-persona format uses a bracketed `[admin:r1, editor:r2]` prefix with per-persona finding counts and max-of independence scores. Per-persona failures produce `_BlockedRunResult` outcomes via continue-on-failure semantics — one persona's failure does not abort the loop.

### Changed
- **`_build_engine` refactored** to accept a pre-built Playwright `bundle` parameter instead of creating its own internally. The strategy (`run_fitness_strategy`) now owns bundle lifecycle via outer `try/finally`, allowing the shared browser to be reused across personas. `_EngineProxy.run()` no longer closes the bundle — it simply forwards to `engine.run()`.
- **`/ux-cycle` Phase B runbook** updated to show the `personas=` kwarg with example lists (`["admin", "agent", "customer"]`) and a commented-out anonymous variant. Updated qa field mapping to note that per-persona failures inside a multi-persona run are absorbed into `outcome.degraded=True` rather than raising the whole strategy.

### Agent Guidance
- **Authoring contracts:** new ux-architect component contracts should include a `## Anchor` section with the URL the component lives at (e.g. `/login` for `auth-page`). Contracts without an anchor continue to work — the walker observes whatever page is loaded — but anchor-driven contracts produce more meaningful gate observations. The 35+ existing contracts will be backfilled with anchors as a separate one-shot data migration (not in v1.0.3 source).
- **Multi-persona execution:** when `/ux-cycle` Phase B runs against an in-app component that needs persona-scoped verification, pass `personas=["admin", ...]` matching the example app's DSL persona declarations. For public/anonymous components (auth pages, landing pages), pass `personas=None` (the default) to run a single anonymous cycle. v1.0.4+ may add AppSpec-derived auto-derivation; for v1.0.3, the caller is the source of truth.
- **Per-persona failure semantics:** per-persona failures (login rejected, engine crashed, anchor navigation failed) record `_BlockedRunResult` outcomes that absorb into the aggregated `StrategyOutcome.degraded=True` flag. The strategy only raises when there is nothing useful to return (subprocess failed to start, Playwright bundle couldn't spin up). Phase B `qa` field mapping treats raised strategy errors as `BLOCKED` and per-persona absorbed failures as part of the `FAIL`/`PASS` aggregate.

## [0.54.2] - 2026-04-13

### Added
- **Fitness v1.0.2 — contract-driven Pass 1 walker.** New `walk_contract` mission at `src/dazzle/fitness/missions/contract_walk.py` mirrors the shape of `walker.walk_story` but drives the ledger from a parsed ux-architect `ComponentContract`. Each quality gate becomes one ledger step: expect = gate description, action_desc = `"observe contract gate"`, observed_ui = `await observer.snapshot()`. Deterministic — no LLM calls. Observer is injected via a `Protocol` so unit tests use an in-memory stub and the strategy wraps a Playwright page. Symmetric intent/observation counts per step even on observer errors.
- **`FitnessEngine.contract_paths` + `contract_observer` kwargs.** The engine's Pass 1 loop now iterates contract paths (defaulting to `[]`) after story walks, parsing each via `parse_component_contract` and calling `walk_contract` with the injected observer. Both kwargs default to `None` so existing callers are unaffected. If `contract_paths` is non-empty but `contract_observer` is None, Pass 1 raises `ValueError` loudly rather than silently skipping the walk.
- **Strategy plumbing + `_ContractObserver` adapter.** `run_fitness_strategy` and `_build_engine` gain an optional `component_contract_path: Path | None = None` kwarg. When set, `_build_engine` wraps the Playwright bundle's page in a new `_ContractObserver` adapter whose `snapshot()` delegates to `await page.content()`, then passes both `contract_paths=[path]` and `contract_observer=observer` through to `FitnessEngine`.

### Changed
- **`/ux-cycle` Phase B rewritten to route through `run_fitness_strategy`.** Closes the "irony gap": Phase B previously hand-rolled its own `DazzleAgent` + `PlaywrightObserver` + `PlaywrightExecutor` dispatch, completely bypassing the fitness engine's ledger + Pass 1 machinery. The new three-line snippet calls `run_fitness_strategy(component_contract_path=path)` and the fitness engine owns the contract walk. Findings flow through the normal engine pipeline and land in `dev_docs/fitness-backlog.md`.

### Agent Guidance
- **v1.0.2 does not navigate.** The contract walker observes whatever page is loaded when Pass 1 fires — `about:blank` for fresh Playwright bundles. URL inference from contract anchors is deferred to v1.0.3 along with multi-persona fan-out and the optional `walk_story` → `walk_plan` unification. If you are writing Phase B runbooks that need real component observation, navigate to the right URL before calling `run_fitness_strategy`, or wait for v1.0.3.

## [0.54.1] - 2026-04-13

### Added
- **QA Mode (#768):** `dazzle serve --local` now auto-provisions a dev user for each DSL persona and renders a QA Personas section on the landing page. Testers click "Log in as X" to explore the app as any persona via magic links. Dev-gated generator endpoint `POST /qa/magic-link` is mounted only when `DAZZLE_ENV=development` + `DAZZLE_QA_MODE=1`. A general-purpose `GET /auth/magic/{token}` consumer endpoint is mounted unconditionally for production email-based passwordless login.
- **Magic link consumer endpoint:** `GET /auth/magic/{token}` — production-safe, general-purpose. Validates via existing `validate_magic_link` primitive (one-time use, expiry-gated), creates a session, and redirects to `?next=` (same-origin only) or `/`. Suitable for email-based passwordless login, account recovery, and dev QA mode.
- **`/ux-cycle` slash command:** iterative UX improvement loop that brings Dazzle's UX layer under ux-architect governance one component at a time. OBSERVE → SPECIFY → REFACTOR → QA → REPORT → EXPLORE cycle with persistent backlog (`dev_docs/ux-backlog.md`). Uses the new `ux_quality` DazzleAgent mission to drive Playwright through component contract quality gates as each persona (via QA mode magic link login from #768).
- **`ux_quality` and `ux_explore` agent missions:** two new DazzleAgent missions. `ux_quality` takes a ux-architect component contract and verifies its quality gates. `ux_explore` runs bottom-up gap discovery with two strategies (missing contracts, edge cases).
- **Flat-file signal bus:** `dazzle.cli.runtime_impl.ux_cycle_signals` — cross-loop coordination between `/ux-cycle`, `/improve`, `/ux-converge`. Signals at `.dazzle/signals/*.json` (gitignored).
- **Component contract parser:** `parse_component_contract()` in `dazzle.agent.missions._shared` — extracts quality gates, anatomy, and primitives from ux-architect contract markdown files.
- **DSL:** new `lifecycle:` entity block declaring ordered states and per-transition evidence predicates for the Agent-Led Fitness Methodology's progress evaluator. Orthogonal to the auto-derived `state_machine` (runtime mechanics). See ADR-0020 and `docs/reference/grammar.md`.
- **Agent-Led Fitness Methodology (v1)** — new subsystem at `src/dazzle/fitness/`.
  Continuous V&V loop triangulating `spec.md`, DSL stories, and the running
  app. Ships Pass 1 (story walker), Pass 2a (spec cross-check with structural
  independence), Pass 2b (behavioural proxy with EXPECT/ACTION/OBSERVE hard
  interlock), snapshot-based FitnessLedger, regression comparator, and
  two-gate corrector with alternative-generation disambiguation. See
  `docs/reference/fitness-methodology.md`.
- **DSL:** new `fitness.repr_fields` block on entities — required for entities
  that participate in fitness evaluation. v1 emits a non-fatal lint warning
  when missing; v1.1 will make this fatal.
- **/ux-cycle:** new `Strategy.FITNESS` — rotates alongside MISSING_CONTRACTS
  and EDGE_CASES.
- **Fitness v1.0.1 — real `_build_engine` wiring.** Replaces the
  `NotImplementedError` stub in
  `src/dazzle/cli/runtime_impl/ux_cycle_impl/fitness_strategy.py` with the
  full async composition root: loads `AppSpec` + `FitnessConfig` from the
  example project, constructs `PostgresBackend` from `DATABASE_URL`
  (wrapped in the new `PgSnapshotSource` adapter), instantiates
  `LLMAPIClient`, spins up a headless Chromium `_PlaywrightBundle` via a
  separate `_setup_playwright` helper, builds a `DazzleAgent` with
  `PlaywrightObserver` + `PlaywrightExecutor`, and returns an
  `_EngineProxy` whose `run()` tears down Playwright even if the engine
  raises. Example-app subprocess lifecycle owned by `run_fitness_strategy`
  via `try/finally` delegating to `dazzle.qa.server.connect_app` +
  `wait_for_ready`.
- **`PgSnapshotSource` adapter** at
  `src/dazzle/fitness/pg_snapshot_source.py` — sync `SnapshotSource`
  protocol implementation over `PostgresBackend.connection()` using
  `psycopg.sql.Identifier` for safe SQL composition.
- **Unblocked e2e smoke test:**
  `tests/e2e/fitness/test_support_tickets_fitness.py::test_support_tickets_fitness_cycle_completes`
  now exercises `run_fitness_strategy` end-to-end when `DATABASE_URL` is
  set, asserting `StrategyOutcome` shape and that `fitness-log.md` +
  `fitness-backlog.md` are written.

### Changed
- **`auth_store` on `app.state`:** The auth subsystem now stashes `auth_store` on `app.state.auth_store` during startup. Route handlers can access the auth store without dependency injection gymnastics. Existing routes that receive auth_store via constructor are unchanged.
- **UX-036 auth-page series complete — all 7 `site/auth/` templates under macro governance.** Every template in `src/dazzle_ui/templates/site/auth/` now consumes the `auth_page_card` macro from `macros/auth_page_wrapper.html`. Dropped DaisyUI tokens across the series: `card`/`card-body`/`card-title`, `form-control`/`label-text`/`input-bordered`, `btn-primary`/`btn-outline`/`btn-ghost`/`btn-error`/`btn-sm`, `alert-error`/`alert-success`/`alert-warning`, `bg-base-*`, `divider`, `link-primary`/`link-secondary`, `badge badge-lg badge-outline`. Pure Tailwind replacements use HSL CSS variables from `design-system.css`. Inline JS in `2fa_settings.html` and `2fa_setup.html` extracts button class strings into named constants (`BTN_PRIMARY` / `BTN_DESTRUCTIVE` / `BTN_OUTLINE`, `RECOVERY_CODE_CLASSES`) so future tweaks touch one place. Submission handlers now all use CSRF-header-based JS fetches; `method="POST"` removed from form tags.

### Agent Guidance
- **QA Mode workflow**: When building or modifying example apps for human QA testing, the landing page renders a dev-only Personas panel with "Log in as X" buttons. The flow uses real magic links (no auth backdoor). Persona emails follow `{persona_id}@example.test`. Passwords are not set — magic-link login only. See `docs/superpowers/specs/2026-04-12-qa-mode-design.md` for the full security model.
- **`dazzle serve --local` env flags**: When `--local` is active, the CLI sets `DAZZLE_QA_MODE=1` and `DAZZLE_ENV=development` before uvicorn starts. Dev-only routes should double-check both flags at request time (defense in depth).
- **Lifecycle vs state_machine:** the new `lifecycle:` block is NOT a replacement for the existing auto-derived `state_machine`. Lifecycles encode progress semantics (ordered states, evidence predicates) and are consumed by `src/dazzle/fitness/progress_evaluator.py` once fitness v1 ships. State machines encode runtime mechanics (triggers, guards, effects). Entities may declare both; a validator warning fires if their state lists disagree.
- **Fitness prerequisite:** entities participating in fitness must declare
  both `fitness.repr_fields` (this release) and a `lifecycle:` block
  (ADR-0020). Check the lint output — missing declarations will silently
  skip the entity from fitness evaluation in v1 and error in v1.1.
- **Fitness findings routing:** never auto-correct findings with
  `low_confidence=true`. They go to soft mode (PR queue) regardless of
  maturity level. See `src/dazzle/fitness/corrector.py:route_finding`.

## [0.54.0] - 2026-04-12

### Added
- **ux-architect skill**: New Claude Code skill at `~/.claude/skills/ux-architect/` for constraint-based UI generation. 4-layer model: frozen token sheets, component contracts, interaction primitives, stack adapters. Linear aesthetic, 13 artefact files.
- **Data table inline edit**: `PATCH /api/{entity}/{id}/field/{field_name}` endpoint for single-field updates. Compiler auto-populates `inline_editable` from field types (text, bool, enum, date). Phase-based editing: double-click to enter, Enter/Tab to commit, Esc to cancel, Tab advances to next editable cell.
- **Data table bulk delete**: `POST /api/{entity}/bulk-delete` endpoint with scope-filtered ID list. Delete-only for v1; UI shows confirmation before executing.
- **Data table column resize**: Client-only column width adjustment via pointer events and `<colgroup>`. Snaps to 8px increments, persisted to localStorage per table ID.
- **Quality gate tests**: Playwright integration tests for dashboard (6 tests) and data table (9 tests). Static test harnesses serve mock data without backend. Catches DOM event wiring bugs that unit tests miss.

### Changed
- **Breaking**: Dashboard rewritten — SortableJS replaced with native pointer events + Alpine.js. 5-state save lifecycle (clean/dirty/saving/saved/error), undo stack (Cmd+Z), keyboard move/resize mode. `sortable.min.js` removed from vendor.
- **Breaking**: All table templates rewritten to pure Tailwind — DaisyUI component classes (`btn`, `table`, `badge`, `dropdown`, `checkbox`, `rounded-box`, `bg-base-*`) removed from `filterable_table.html`, `table_rows.html`, `table_pagination.html`, `bulk_actions.html`, `search_input.html`, `filter_bar.html`, `inline_edit.html`. Colours use `design-system.css` HSL variables.
- **Breaking**: `dzTable` Alpine component signature changed from `(tableId, endpoint, sortField, sortDir)` to `(tableId, endpoint, config)` where config is `{sortField, sortDir, inlineEditable, bulkActions, entityName}`.
- `examples/` reorganised: internal tools and test fixtures moved to `fixtures/`. `_archive/` deleted. `examples/` now contains only working Dazzle apps (simple_task, contact_manager, support_tickets, ops_dashboard, fieldtest_hub).

### Fixed
- CI badge (red since 2026-03-30): `test_regions_still_load_without_sse` expected `hx-trigger="load"` but template uses `intersect once`. CI validation loops updated to include `fixtures/*/`.

### Agent Guidance
- **ux-architect skill**: When building or modifying dashboard, data table, or other spec-governed UI, invoke the `ux-architect` skill. Read token sheets and component contracts before writing code. Do not invent values outside the token sheet.
- **DaisyUI phase-out**: New spec-governed components use pure Tailwind utilities. Existing non-governed templates may still use DaisyUI. Migrate incrementally as components get contracts.
- **Inline edit field types**: Compiler determines editability from column type: text, bool, badge (enum), date are editable; pk, ref, computed, sensitive, money are not.
- **examples/ vs fixtures/**: Real example apps in `examples/`, internal tools in `fixtures/`. CI validates both directories.

## [0.53.1] - 2026-03-30

### Fixed
- **SA schema**: `_field_to_column` accessed `field.required` which doesn't exist on IR `FieldSpec` (it has `is_required`). Now uses `getattr` fallback to support both FieldSpec types. Fixes NOT NULL columns for optional fields like `FeedbackReport.reported_by` (#762).
- **QA capture**: `build_capture_plan()` only checked `appspec.archetypes` (always empty for projects using `personas` keyword). Now falls back to `appspec.personas`. Unblocks `dazzle qa visual` and `dazzle qa capture` for all example apps (#763).

## [0.53.0] - 2026-03-30

### Added
- **Dashboard builder**: Replaces the workspace editor with a full card-based dashboard builder. SortableJS drag-to-reorder, snap-grid drag-to-resize (3/4/6/8/12 columns), add/remove cards from DSL-defined catalog, auto-save with 500ms debounce, always-on interactions (no edit mode toggle).
- **Layout schema v2**: Card-instance model where each card is an independent instance referencing a DSL region. Supports duplicate cards of the same type. Automatic v1→v2 migration preserves existing user layouts.
- **Catalog endpoint**: `build_catalog()` returns available widgets per workspace for the "Add Card" picker. Layout JSON data island now includes catalog metadata.
- **Card picker popover**: `_card_picker.html` template lists available regions grouped by display type and entity.

### Changed
- **Breaking**: Alpine Sort plugin removed, replaced by SortableJS (vendored). `workspace-editor.js` replaced by `dashboard-builder.js`.
- **Breaking**: Layout preference format changed from v1 `{order, hidden, widths}` to v2 `{version: 2, cards: [{id, region, col_span, row_order}]}`. Hidden cards are dropped (not flagged) in v2. Auto-migration is seamless.

### Agent Guidance
- AegisMark agents building customizable dashboards should use DSL `workspace` blocks to define the card catalog. End users compose their own layouts via the dashboard builder UI. No code changes needed — the framework handles drag-drop, resize, and persistence automatically.
- Valid `col_span` snap points: 3, 4, 6, 8, 12. The old 6/12-only restriction is gone.

## [0.52.0] - 2026-03-30

### Added
- **QA toolkit**: New `src/dazzle/qa/` package — visual quality evaluation via Claude Vision, Playwright screenshot capture, process lifecycle management, and findings aggregation. Generalized from AegisMark's autonomous quality assessment approach.
- **CLI**: `dazzle qa visual` evaluates running apps against 8 quality categories (text_wrapping, truncation, title_formatting, column_layout, empty_state, alignment, readability, data_quality). Returns structured findings with severity and fix suggestions.
- **CLI**: `dazzle qa capture` captures screenshots per persona per workspace without LLM evaluation — useful for debugging and baselines.
- **Evaluator**: Pluggable `QAEvaluator` protocol with `ClaudeEvaluator` default (via `[llm]` extra). Prompt adapted from AegisMark's battle-tested visual quality assessment.
- **Server lifecycle**: `serve_app()` context manager starts Dazzle apps as subprocesses with health polling. Accepts `--url` for already-running instances.
- **`/improve` integration**: New `visual_quality` gap type with tiered discovery — DSL gaps first (free), visual QA when exhausted (LLM cost). Findings feed into the existing OBSERVE → ENHANCE → VERIFY loop.

### Agent Guidance
- When `/improve` exhausts all DSL-level gaps (lint, validate, conformance, fidelity), it now automatically runs `dazzle qa visual` to discover display bugs (raw UUIDs, broken layouts, missing empty states). Visual findings become backlog items with fix routing by category.
- `dazzle qa visual --app <name>` works against any example app. Use `--url` for deployed instances.

## [0.51.16] - 2026-03-29

### Fixed
- **Display**: FK fields in detail views no longer render as raw Python dicts (#761). `_get_field_spec` now falls back to relation name + `_id` lookup; template else-branch applies `ref_display` filter for mapping values.
- **Display**: Datetime fields (`created_at`, `updated_at`) now format as "27 Mar 2026" instead of raw ISO strings (#760). `_field_type_to_column_type` detects `_at` suffix for framework-injected timestamp columns.
- **Workspace**: Customize button drag-and-drop now gated to edit mode via `x-sort:disabled` (#758). Added visual lift feedback CSS on drag handles.
- **Filter bar**: Ref/FK fields now render as select dropdowns instead of free-text inputs (#759). Alpine.js-driven `<select>` fetches options from the referenced entity's API on page load.

## [0.51.15] - 2026-03-29

### Fixed
- **PyPI**: Fixed `ModuleNotFoundError: No module named 'httpx'` on `dazzle --help` in PyPI installs. The sentinel CLI eagerly imported `dazzle.testing.fuzzer` at module level, which pulled in `httpx` via the e2e_runner import chain. Now lazy-imported inside the `fuzz` command.

## [0.51.14] - 2026-03-29

### Added
- **JS quality checks**: ESLint structural linting for 8 source JS files (no-undef, no-unreachable, no-dupe-keys, valid-typeof). Flat config with browser + framework globals (Alpine, htmx, Quill, etc.).
- **Dist syntax validation**: `node --check` validates composed `dist/*.js` bundles are parseable — catches concatenation errors.
- **Test suite**: `tests/unit/test_js_quality.py` with ESLint + dist syntax checks, skips gracefully if node/npx unavailable.

### Fixed
- **vitest.config.js**: Fixed typo `dazzle_dnr_ui` → `dazzle_ui` in include path.

## [0.51.13] - 2026-03-29

### Added
- **HTML template linting**: Added djLint static analysis for all 102 Jinja2 templates — catches unclosed/mismatched tags deterministically without rendering. Configured in `pyproject.toml` with structural rules only.
- **Rendered HTML validation**: New `HTMLBalanceChecker` validates balanced open/close tags on rendered template output for 18 key templates (fragments, workspace regions, components).
- **Test suite**: `tests/unit/test_template_html.py` with 24 tests covering both static and rendered HTML quality checks.

### Fixed
- **Workspace**: Fixed unclosed `<div>` in list region template causing titles to render inline with content instead of above it (#757).

## [0.51.12] - 2026-03-29

### Fixed
- **Display**: Enum/state fields now show human-readable Title Case instead of raw snake_case values in tables and detail views (#755). Added centralized `humanize` Jinja2 filter.
- **Display**: Grid and list workspace regions no longer show raw UUIDs for ref fields when FK expansion is missing (#756). Unexpanded refs now show "-" instead of the UUID string.

## [0.51.11] - 2026-03-28

### Fixed
- **Parser**: `widget=` can now appear after `visible:` on surface field declarations (#754). Previously, `field x "X" visible: role(admin) widget=picker` failed with "Unexpected 'widget'" — the parser now accepts key=value options, `visible:`, and `when:` in any order.

## [0.51.10] - 2026-03-28

### Added
- **Capability discovery**: New `src/dazzle/core/discovery/` package surfaces relevant Dazzle capabilities (widgets, layouts, components, completeness gaps) to agents at lint time using contextual references to working example apps
- **Widget rules**: Detects text fields without `widget=rich_text`, ref fields without `widget=combobox`, date fields without `widget=picker`, and name-pattern matches for tags, color, slider
- **Layout rules**: Identifies entities with transitions but no kanban workspace, date fields but no timeline, view surfaces with 3+ related entities but no groups, and large single-section forms
- **Component rules**: Suggests `dzCommandPalette` for apps with 5+ surfaces, toggle groups for enum status + grid displays
- **Completeness rules**: Flags entities with permissions but missing CRUD surfaces (edit, list, create) or no surfaces at all
- **Example index**: Scans example apps to build capability key → `ExampleRef` mappings with file paths and line numbers
- **KG seeding**: New `capabilities.toml` with 18 capability concepts seeded into knowledge graph (seed schema v8)
- **Lint integration**: `dazzle lint` and `dsl operation=lint` now include a "Relevant capabilities" section after errors/warnings
- **Bootstrap integration**: Added step 12a in bootstrap agent instructions to review capability relevance after DSL generation
- **Quiet mode**: `suppress_relevance=true` on MCP calls or `suppress=True` in API suppresses relevance output

### Agent Guidance
- After generating DSL, run `dsl operation=lint` and review the "Relevant capabilities" section. Each item references a working example app with file and line number — use these as concrete patterns, not prescriptions.
- Query `knowledge(operation='concept', term='widget_rich_text')` (or any capability key) for deeper exploration of what's available.

## [0.51.9] - 2026-03-28

### Fixed
- **CI green badge**: Resolved all 12 mypy errors across 4 files — triples.py (getattr for object attrs), service.py (mixin method type ignores), ux.py (function annotations + HtmxResponse typing), db.py (union type guard for Alembic revision)

## [0.51.8] - 2026-03-28

### Fixed
- **component_showcase**: `widget=range` on `end_date` (date field) changed to `widget=picker` — range picker returns unparseable string for date columns
- **All examples**: Removed no-op `widget=` annotations from `mode: view` and `mode: list` surfaces — detail_view.html and filterable_table.html do not check `field.widget`
- **project_tracker**: Added missing `project_edit`, `milestone_list`, `milestone_edit` surfaces — previously had broken Edit button (404)
- **design_studio**: Added missing `brand_edit`, `campaign_list`, `campaign_edit` surfaces — previously couldn't update brands or browse campaigns

### Agent Guidance
- `widget=` annotations are only effective on `mode: create` and `mode: edit` surfaces. Do not add them to `mode: view` or `mode: list` surfaces — the templates ignore them.
- `widget=range` (date range picker) should only be used on `str` fields, not `date` fields. A date range returns a compound string ("YYYY-MM-DD to YYYY-MM-DD") that cannot be stored in a scalar date column.

## [0.51.7] - 2026-03-28

### Fixed
- **Duplicated widget map**: `_field_type_to_form_type()` in template_compiler.py now delegates to canonical `resolve_widget()` from triples.py — single source of truth, 9 previously missing field type kinds covered
- **Flattened action provenance**: `VerifiableTriple.actions` now carries `ActionTriple` with `action` + `permission` fields instead of bare strings — reconciler can trace permission grants for ACTION_UNEXPECTED diagnoses
- **TEMPLATE_BUG catch-all**: New `TRIPLE_SUSPECT` diagnosis kind — reconciler cross-checks triple widget against re-derived widget from raw entity field before falling through to TEMPLATE_BUG
- **O(n) triple lookups**: `AppSpec.get_triple()`, `get_triples_for_entity()`, `get_triples_for_persona()` now use `@cached_property` dict indexes for O(1) lookups

### Added
- Scope predicate invariant documented on `derive_triples()` — triples depend only on entities, surfaces, and personas, never FK graph or scope predicates
- 5 synthetic failure tests for reconciler diagnosis paths (ACTION_MISSING, ACTION_UNEXPECTED, FIELD_MISSING, PERMISSION_GAP, TRIPLE_SUSPECT)

### Agent Guidance
- `VerifiableTriple.actions` is now `list[ActionTriple]`, not `list[str]`. Use `triple.action_names` for backward-compatible string list access.
- The template compiler no longer has its own widget map — it imports `resolve_widget()` from `dazzle.core.ir.triples`. When adding new `FieldTypeKind` values, only update `_WIDGET_MAP` in triples.py.

## [0.51.6] - 2026-03-28

### Added
- **`widget=` DSL syntax**: Surface field declarations now support `widget=value` annotations (e.g., `field description "Description" widget=rich_text`). The parser already supported `key=value` options via the `source=` pattern — this commit wires `widget` through the template compiler to `FieldContext.widget`, completing the DSL-to-template pipeline.
- All three Phase 5 example apps updated with `widget=` annotations on appropriate fields

### Agent Guidance
- Use `widget=value` on surface field lines to override the default field rendering. Supported values: `rich_text`, `combobox`, `tags`, `picker`, `range`, `color`, `slider`. The value flows through `SurfaceElement.options["widget"]` → template compiler → `FieldContext.widget` → `form_field.html` macro.
- The `widget=` option is parsed as a generic key-value pair — no parser changes were needed.

## [0.51.5] - 2026-03-28

### Added
- **UX Component Expansion — Phase 5 (Example Apps)**: Three new example apps exercising the expanded component inventory
  - `examples/project_tracker` — Project management app: 6 entities (User, Project, Milestone, Task, Comment, Attachment), kanban board, timeline, status cards, related groups, multi-section forms
  - `examples/design_studio` — Brand/design asset management: 5 entities (User, Brand, Asset, Campaign, Feedback), asset gallery grid, review queue, brand color fields, campaign scheduling
  - `examples/component_showcase` — Kitchen-sink gallery: single "Showcase" entity with every field type, all widget-capable fields exercised from one create/edit form

### Agent Guidance
- The `widget:` syntax is NOT yet implemented in the DSL parser — it exists at the template/rendering layer only. Example apps use standard DSL field types. Widget rendering will be activated when the parser supports `widget=` annotations on surface fields (planned for a future minor version).
- Each example validates cleanly (`dazzle validate`). Framework-generated `FeedbackReport` warnings are expected when `feedback_widget: enabled`.

## [0.51.4] - 2026-03-28

### Added
- **UX Component Expansion — Phase 4 (Vendored Widget Libraries)**: Complex input components via battle-tested JS libraries
  - **Tom Select** (v2.5.2, Apache 2.0): Combobox, multi-select, and tag input — `data-dz-widget="combobox|multiselect|tags"`
  - **Flatpickr** (v4.6.13, MIT): Date picker and date range picker — `data-dz-widget="datepicker|daterange"`
  - **Pickr** (v1.9.1, MIT): Color picker with nano theme — `data-dz-widget="colorpicker"`
  - **Quill** (v2.0.3, BSD-3): Rich text editor with snow theme — `data-dz-widget="richtext"`
  - Range slider with live value tooltip — `data-dz-widget="range-tooltip"`
  - `dz-widget-registry.js`: Bridge handler registrations for all 8 widget types (mount/unmount lifecycle)
  - `dz-widgets.css`: DaisyUI v4 theme overrides for all vendored libraries (oklch color tokens, radius, fonts)
  - `form_field.html` macro: 8 new `widget:` cases — combobox, multi_select, tags, picker, range, color, rich_text, slider
  - Conditional loading via `asset_manifest.py` — vendored JS/CSS only loads on pages that use the widgets

### Agent Guidance
- Set `widget:` on surface fields to use vendored widgets. The `form_field.html` macro checks `field.widget` before `field.type`.
- Widget elements use `data-dz-widget` attributes. The component bridge (`dz-component-bridge.js`) handles HTMX swap lifecycle. `dz-widget-registry.js` registers all mount/unmount handlers.
- Tom Select covers three use cases: `combobox` (single select with search), `multiselect` (multi with remove buttons), `tags` (free-form tag creation).

## [0.51.3] - 2026-03-28

### Added
- **UX Component Expansion — Phase 3 (Alpine Interactive Components)**: 6 new Alpine.js components with Jinja2 fragments
  - `dzPopover` + `popover.html`: Anchored floating content panel with click-outside dismiss
  - `dzTooltip` + `tooltip_rich.html`: Rich HTML tooltip with configurable show/hide delays
  - `dzContextMenu` + `context_menu.html`: Right-click positioned menu with divider support
  - `dzCommandPalette` + `command_palette.html`: Cmd+K spotlight search with fuzzy filter, keyboard navigation, grouped actions
  - `dzSlideOver` + `slide_over.html`: Side sheet overlay with 5 width presets, focus trapping, HTMX content loading
  - `dzToggleGroup` + `toggle_group.html`: Exclusive or multi-select button group with hidden input sync

### Agent Guidance
- All Phase 3 components are registered in `dz-alpine.js` and have matching fragments in `templates/fragments/`.
- `dzCommandPalette` accepts actions as a JSON array via `data-dz-actions` attribute or Jinja2 `actions` variable. Actions have `label`, `url`, optional `group` and `icon`.
- `dzSlideOver` listens for `dz:slideover-open` window event — dispatch from HTMX `hx-on::after-settle`.
- `dzToggleGroup` syncs to a hidden input for form submission. Use `multi=True` for multi-select mode.

## [0.51.2] - 2026-03-28

### Added
- **UX Component Expansion — Phase 2 (Server-Driven Components)**: Template fragments and HTMX patterns
  - `toast.html` fragment: auto-dismissing notifications via `remove-me` extension
  - `alert_banner.html` fragment: full-width dismissible banners with Alpine.js
  - `breadcrumbs.html` fragment + `breadcrumbs.py` module: server-side route-to-breadcrumb derivation with DaisyUI styling and HTMX navigation
  - `steps_indicator.html` fragment: DaisyUI steps component for multi-step wizard flows
  - `accordion.html` fragment: collapsible sections with optional HTMX lazy-load on first open
  - `skeleton_patterns.html` macros: reusable skeleton presets (table rows, cards, detail views)
  - `modal.html` component: general-purpose server-loaded modal using native `<dialog>` element

### Agent Guidance
- Use `build_breadcrumb_trail(path, overrides)` from `dazzle_back.runtime.breadcrumbs` to derive breadcrumb trails. Pass the result as `crumbs` to the breadcrumbs fragment.
- For accordion lazy-loading, set `endpoint` on a section to trigger HTMX fetch on first open; leave it `None` for static content.
- Skeleton macros are importable: `{% from "fragments/skeleton_patterns.html" import skeleton_table_rows, skeleton_card, skeleton_detail %}`.

## [0.51.1] - 2026-03-28

### Added
- **UX Component Expansion — Phase 1 (Foundation)**: Infrastructure for expanding Dazzle's native UX component inventory
  - Vendor HTMX extensions: `remove-me` (auto-dismiss), `class-tools` (timed CSS), `multi-swap` (multi-target), `path-deps` (auto-refresh)
  - Vendor Alpine.js plugins: `@alpinejs/anchor` (Floating UI positioning), `@alpinejs/collapse` (smooth accordion), `@alpinejs/focus` (focus trapping)
  - `dz-component-bridge.js`: Lifecycle bridge for vendored widgets across HTMX DOM swaps — mount/unmount/registerWidget API on `window.dz.bridge`
  - `response_helpers.py`: Server-side `with_toast()` and `with_oob()` helpers for HTMX OOB swaps
  - `asset_manifest.py`: Derives required vendor JS assets from surface field `widget:` hints for conditional loading
  - `base.html`: `#dz-toast-container`, `#dz-modal-slot`, `#dz-dynamic-assets` container elements; conditional vendor asset loading block

### Agent Guidance
- Use `with_toast(response, message, level)` from `dazzle_back.runtime.response_helpers` to append auto-dismissing toast notifications to any HTMX response. Use `with_oob()` for generic OOB swaps.
- Vendor widget libraries register via `window.dz.bridge.registerWidget(type, { mount, unmount })`. The bridge handles HTMX swap lifecycle automatically.
- `collect_required_assets(surface)` from `asset_manifest.py` returns the set of vendor asset keys a page needs. Pass as `required_assets` in template context.

## [0.51.0] - 2026-03-28

### Added
- **Related Display Intent**: `related` DSL block on `mode: view` surfaces for grouped, mode-specific related entity presentation
  - `RelatedDisplayMode` enum: `table`, `status_cards`, `file_list` (closed, extensible per minor version)
  - `RelatedGroup` IR type: name, title, display mode, entity list — validated at link time
  - Parser: `related name "Title": display: mode; show: Entity1, Entity2` syntax
  - Linker validation: entity existence, FK path to parent, no duplicates across groups, view-mode only
  - `RelatedGroupContext` replaces flat `related_tabs` on `DetailContext`
  - Template compiler groups tabs by declared groups; ungrouped entities auto-collect into "Other" with `display: table`
  - Three fragment templates: `related_table_group.html`, `related_status_cards.html`, `related_file_list.html`
  - `VerifiableTriple.related_groups` for contract verification of detail page layout

### Agent Guidance
- Use `related` blocks on `mode: view` surfaces to control how related entities appear on detail pages. Without them, behavior is unchanged (all reverse-FK entities as table tabs). With them, named entities render with declared display modes; unlisted entities auto-group into "Other".

## [0.50.0] - 2026-03-28

### Added
- **IR Triple Enrichment** (Layer A): Cache (Entity, Surface, Persona) triples in AppSpec at link time
  - `WidgetKind` enum: deterministic widget resolution from field types (mirrors template compiler)
  - `SurfaceFieldTriple`: per-field rendering metadata (widget, required, FK status)
  - `SurfaceActionTriple`: per-surface action with permission-based visibility
  - `VerifiableTriple`: atomic unit of verifiable behavior — fields + actions per persona
  - `derive_triples()`: pure function in linker step 10b, no UI imports
  - AppSpec getters: `get_triple()`, `get_triples_for_entity()`, `get_triples_for_persona()`
- **Reconciliation Engine** (Layer C): Back-propagate contract failures to DSL levers
  - `DiagnosisKind`: 7 failure categories (widget_mismatch, action_missing, permission_gap, template_bug, etc.)
  - `DSLLever`: points to specific DSL construct with current/suggested values
  - `Diagnosis`: structured failure report with levers for agent-driven convergence
  - `reconcile()`: deterministic diagnosis from contract + triple + HTML

### Changed
- Contract generation (`contracts.py`) rewritten as thin mapper over `appspec.triples` — ~130 lines of derivation logic removed
- `/ux-converge` command updated to use reconciler for automated failure classification

### Agent Guidance
- **IR Triples**: `appspec.triples` contains pre-computed (Entity, Surface, Persona) triples. Use `appspec.get_triple(entity, surface, persona)` instead of re-deriving from raw IR.
- **Reconciler**: When a contract fails, call `reconcile(contract, triple, html, entities, surfaces)` to get a `Diagnosis` with `levers` pointing to the DSL change that would fix it. No more manual backward reasoning.
- **Convergence loop**: `/ux-converge` now uses the reconciler. Each failure produces a structured diagnosis → apply lever → re-verify → converge.

## [0.49.14] - 2026-03-28

### Added
- **UX Contract Verification** (Layer B): `dazzle ux verify --contracts` — fast, httpx-based DOM assertion system derived from AppSpec
  - Contract generation: mechanically derives ListPage, CreateForm, EditForm, DetailView, Workspace, and RBAC contracts from the DSL
  - Contract checker: parses rendered HTML and asserts DOM structure (hx-* attributes, form fields, action buttons, region presence)
  - HTMX client: simulates browser HTMX requests with correct headers (HX-Request, HX-Target, CSRF)
  - Baseline ratchet: tracks pass/fail per contract across runs, detects regressions and fixes
  - RBAC contracts: verifies UI enforcement of every permit/forbid rule per persona (compliance evidence)
  - Performance: ~25 seconds for full verification vs 5+ minutes for Playwright
- Context selector label: human-readable names from DSL title or PascalCase splitting (#747)
- Feedback widget: validation toast when category not selected (#746)

### Fixed
- Workspace routes registered once instead of N× per workspace (#750)
- Workspace drawer reopens after backdrop close — removed vestigial `history.replaceState` (#748)
- DELETE handler returns 409 on FK constraint instead of 500 (#749)
- `/__test__/reset` clears each entity table in separate connection to avoid FK-aborted transactions (#751)
- `/__test__/seed` rolls back created entities on failure to prevent partial state (#753)
- UX inventory: deduplicated CRUD interactions to one per entity×persona (#752)
- Contract checker: calibrated against real HTML patterns (data-dazzle-table on div, hx-put for edit forms, surface-mode-gated contracts)

### Agent Guidance
- **Contract verification**: Run `dazzle ux verify --contracts` for fast DOM assertion (no browser). Use `--update-baseline` to save results, `--strict` to fail on any violation. 41/48 contracts pass on simple_task; 7 RBAC mismatches are genuine permission model issues.
- **Ratchet model**: Baseline stored in `.dazzle/ux-verify/baseline.json`. Regressions (passed→failed) are flagged prominently. Target: converge to zero failures.

## [0.49.13] - 2026-03-27

### Added
- UX verify CRUD interactions: create_submit, edit_submit, delete_confirm runners with form filling, checkbox handling, unique email generation
- UX verify runtime URL resolution from `.dazzle/runtime.json` — auto-discovers server port
- Per-entity seed batching: fixture seeding continues past individual entity failures

### Fixed
- UX verify workspace URLs: `/app/workspaces/{name}` (was `/workspace/{name}`)
- UX verify fixture generator: correct FK ref detection, skip auto-timestamp fields, exclude framework admin entities
- UX verify detail view: wait for HTMX data load, click table rows (not hidden menu links)
- UX verify drawer: use `dzDrawer` JS API for CSS-transform-based drawers, handle non-drawer regions gracefully
- UX verify auth: send `X-Test-Secret` header, extract cookie domain from URL, handle 403 as skip
- UX verify create forms: target `form[hx-post]`, handle datetime-local/checkbox/radio fields, unique values per interaction

### Agent Guidance
- **UX verify results**: simple_task 97/280 passed (0 failures), contact_manager 45/68 passed (0 failures). Skipped items are state_transition (not yet implemented) and permission/drawer-unsupported regions.
- **Delete CSRF**: `hx-delete` interactions fail with 500 due to missing CSRF token in HTMX DELETE requests — tracked as framework issue.

## [0.49.12] - 2026-03-27

### Added
- UX Verification system (Layer A): `dazzle ux verify` for deterministic interaction testing derived from the DSL
  - Interaction inventory: AppSpec → enumerable list of every testable interaction (280 for simple_task)
  - Structural HTML assertions: fast no-browser checks for back buttons, submit buttons, ARIA, duplicate IDs
  - Playwright runner: real browser interaction verification with per-persona sessions and screenshot capture
  - Postgres test harness: create/drop test database lifecycle management
  - Fixture generator: deterministic seed data from DSL entities
  - Report generator: coverage percentage, markdown/JSON output, failure gallery
- `dazzle db baseline` command for fresh database deployment — generates CREATE TABLE migration from DSL (#742)

### Fixed
- Test routes: replaced `functools.partial` with closures — fixes 422 on `/__test__/seed` and `/__test__/authenticate` (#743)
- Detail page Back button: context-aware — closes drawer when inside one, `history.back()` on full pages (#744, #745)

### Agent Guidance
- **UX verification**: Run `dazzle ux verify --structural` for fast HTML checks, `dazzle ux verify` for full browser verification. Coverage metric = interactions_tested / interactions_enumerated.
- **Fresh DB deployment**: Use `dazzle db baseline --apply` instead of `stamp` + empty revision.

## [0.49.11] - 2026-03-27

### Fixed
- Depth-N FK path scoping: subqueries now `SELECT "id"` instead of FK field values, fixing 0-row results on multi-hop scope rules (#738)
- Kanban regions default to `col_span=12` (full width) regardless of stage defaults (#739)
- Workspace layout: replaced CSS `columns-2` with CSS Grid (`grid-cols-12`) to eliminate heading/content misalignment from multi-column fragmentation (#741)
- Workspace drag-and-drop: added visual feedback — ghost opacity + dashed border, drag elevation + scale, grab cursor, save toast (#740)

## [0.49.10] - 2026-03-27

### Added
- Centralized URL configuration: `[urls]` section in `dazzle.toml` with `site_url` and `api_url` fields (#736)
- `resolve_site_url()` and `resolve_api_url()` helpers with env var → toml → localhost default cascade
- Env vars `DAZZLE_SITE_URL` and `DAZZLE_API_URL` override toml values

### Changed
- ~19 files across runtime, testing, CLI, and MCP handlers now use URL resolvers instead of hardcoded localhost URLs (#736)

### Agent Guidance
- **URL configuration**: Set `DAZZLE_SITE_URL` / `DAZZLE_API_URL` env vars or add `[urls]` to `dazzle.toml` to change default URLs. All tools, magic links, OpenAPI specs, and test infrastructure respect the cascade.

## [0.49.9] - 2026-03-27

### Fixed
- Parser hang in experience block on unexpected tokens — missing `else` branch caused infinite loop when non-`step` token appeared (#733)
- `_grants.principal_id` TEXT→UUID migration for tables created before v0.49.8 + route type coercion to prevent psycopg binary protocol mismatch (#734)
- `AuthService` now delegates `create_session()` and `_execute_modify()` to underlying `AuthStore` — fixes `dazzle auth impersonate` crash (#735)

## [0.49.8] - 2026-03-27

### Added
- DSL parser fuzzer — three-layer hybrid fuzzer (LLM generation, grammar-aware mutation, token-level mutation) with classification oracle detecting hangs, crashes, and poor error messages (#732)
- `dazzle sentinel fuzz` CLI command — run fuzz campaigns against the parser with configurable layers, sample counts, and timeout
- MCP `sentinel` tool: new `fuzz_summary` operation for on-demand parser fuzz reports
- Hypothesis-powered parser fuzz test suite — 7 property-based tests covering arbitrary input, DSL-like text, and 5 mutation strategies

### Fixed
- `parse_duration()` in process parser now raises `ParseError` instead of `ValueError` on invalid duration strings — found by the fuzzer (#732)

### Agent Guidance
- **Parser fuzzing**: Run `dazzle sentinel fuzz --layer mutate --samples 100` to check parser robustness. The fuzzer found a `ValueError` bug and a parser hang (#733) during initial development — use it after parser changes.

## [0.49.7] - 2026-03-27

### Fixed
- DSL parser: infinite loop on unsupported syntax in surface section blocks — now raises a clear `ParseError` (#731)
- DSL parser: bare `owner` in `permit:` now gives actionable guidance pointing to the correct `scope:` block pattern (#729)
- Added `ownership_pattern` concept to semantics KB for MCP knowledge tool discoverability (#729)

### Agent Guidance
- **Ownership pattern**: Row-level ownership uses `scope:` blocks, not `permit:`. Write `scope: read: user_id = current_user for: reader` — there is no standalone `owner` keyword. See KB concept `ownership_pattern`.

## [0.49.6] - 2026-03-27

### Added
- `dazzle db stamp` CLI command — marks a revision as applied without running migrations, wraps `alembic.command.stamp()` (#728)

### Fixed
- `grammar_gen.write_grammar()`, `docs_gen.write_reference_docs()`, and `docs_gen.inject_readme_feature_table()` now write to project directory (CWD) instead of package directory (ADR-0018, #725)
- `tenant/provisioner.py` locates alembic dir via `import dazzle_back` for pip install compatibility (#725)

## [0.49.5] - 2026-03-27

### Fixed
- Alembic `env.py` now normalizes Heroku's `postgres://` scheme to `postgresql://` before adding the psycopg driver — fixes `Can't load plugin: sqlalchemy.dialects:postgres` on Heroku (#727)
- `_get_url()` now prefers `sqlalchemy.url` (already normalized by `db.py`) over raw `DATABASE_URL` env var

## [0.49.4] - 2026-03-27

### Added
- PythonAuditAgent (PA) sentinel agent — detects obsolete Python patterns in user project code (#726)
- Three detection layers: ruff profile (UP/PTH/ASYNC/C4/SIM), semgrep ruleset (8 rules for deprecated stdlib), and 6 `@heuristic` AST-based methods for LLM training-bias patterns
- Semgrep ruleset at `src/dazzle/sentinel/rules/python_audit.yml` covering distutils, pkg_resources, cgi, imp, asyncio.get_event_loop, nose, toml PyPI package, and datetime.timezone.utc
- LLM-bias heuristics: requests-in-async (PA-LLM-01), manual dunders (PA-LLM-03), unittest-in-pytest (PA-LLM-04), setup.py alongside pyproject.toml (PA-LLM-05), pip-when-uv-available (PA-LLM-06)
- Python version filtering — findings with min_version above project target are excluded
- Orchestrator now passes `project_path` through to agents that need it

### Agent Guidance
- **PA agent**: Results appear via existing `sentinel findings`/`status`/`history` MCP tools — no new MCP operations. PA scans user project code (app/, scripts/, root .py files), never framework code.

## [0.49.3] - 2026-03-27

### Fixed
- `dazzle db revision` now writes migration files to project directory (`.dazzle/migrations/versions/`) instead of the framework's package directory (#724)
- Alembic config uses `version_locations` to chain framework + project migrations — upgrade/downgrade discovers both
- Framework alembic directory located via `dazzle_back` package path (works with pip installs, not just editable dev mode)

### Agent Guidance
- **Migration output path**: `dazzle db revision` writes to `.dazzle/migrations/versions/` in the project directory. Framework migrations and project migrations are chained via Alembic's `version_locations`. Never write to the Python package directory.

## [0.49.2] - 2026-03-26

### Added
- Environment profiles: `[environments.<name>]` sections in `dazzle.toml` for per-environment database configuration (#718)
- Global `--env` CLI flag and `DAZZLE_ENV` environment variable to select active profile (#718)
- `EnvironmentProfile` dataclass with `database_url`, `database_url_env`, and `heroku_app` fields (#718)
- `environment_profiles` concept in semantics KB with resolution priority documentation (#718)
- Commented-out `[environments.*]` example in blank project template (#718)

### Changed
- `resolve_database_url()` now accepts `env_name` parameter — inserted at priority #2 between explicit URL and DATABASE_URL env var (#718)
- All database-touching CLI commands (db, dbshell, tenant, serve --local, backup) thread `env_name` through to URL resolution (#718)

### Agent Guidance
- **Environment profiles**: Use `[environments.<name>]` in `dazzle.toml` to declare per-environment database connections. Select via `--env <name>` or `DAZZLE_ENV`. Profile names are freeform (development, staging, production, blue, green, demo, etc.).
- **Resolution priority**: `--database-url` > `--env` profile > `DATABASE_URL` env var > `[database].url` > default. Document this in comments when using profiles.
- **CI/CD**: Set `DAZZLE_ENV=production` in deployment config instead of passing `--env` to every command.

## [0.49.1] - 2026-03-26

### Changed
- All tutorial examples now declare `security_profile: basic` and an `admin` persona — aligns with auth-universal philosophy (#704)
- `llm_ticket_classifier` example: added `[auth]` section to `dazzle.toml` (#704)
- `contact_manager` stories: fixed actor references to match declared persona IDs (#704)

### Agent Guidance
- **Examples are auth-universal**: All tutorial examples now have auth enabled, an `admin` persona, and `security_profile: basic`. When scaffolding new apps from examples, this is the expected baseline.

## [0.49.0] - 2026-03-26

### Added
- MCP `knowledge` tool: `changelog` operation — returns `### Agent Guidance` entries from recent releases, with optional `since` version filter (#716)
- MCP `knowledge` tool: `version_info` block in concept lookup responses — includes `since` version and `changes` history when annotated in TOML (#716)
- Semantics KB: `since_version` and `changed_in` fields on TOML concepts — 5 concepts annotated (feedback_widget, scope, static_assets, predicate_compilation, surface_access) (#716)
- KG seeder: changelog guidance entries stored as `changelog:vX.Y.Z` entities during startup (#716)

### Agent Guidance
- **Version-aware concepts**: Some concept lookups now include a `version_info` block with `since` (introduction version) and `changes` (version history). Use this to understand when features appeared and what changed.
- **Changelog operation**: Use `knowledge(operation='changelog')` to get agent guidance from recent releases. Use `since` parameter to filter (e.g., `knowledge(operation='changelog', since='0.48.0')`). Default: last 5 releases with guidance.

## [0.48.16] - 2026-03-26

### Added
- Admin workspace: `DIAGRAM` display mode — entity relationship diagrams rendered via Mermaid JS (#700)
- Admin workspace: app map region showing entity FK graph in Operations nav group (#700)
- Admin workspace: deploy trigger actions — "Trigger Deploy" header button and per-row "Rollback" on deploys region (#701)
- Admin workspace: `_REGION_ACTIONS` / `_ROW_ACTIONS` action button system for admin regions (#701)
- Admin API: `POST /_admin/api/deploys/trigger` and `POST /_admin/api/deploys/{id}/rollback` endpoints (super_admin only) (#701)

## [0.48.15] - 2026-03-26

### Added
- Admin workspace: `LogEntry` virtual entity and `_admin_logs` region — log viewer backed by `get_recent_logs()` with level filtering (#699)
- Admin workspace: `EventTrace` virtual entity and `_admin_events` region — event explorer backed by event bus replay API (#702)
- Feedback widget: resolved-report notification — toast on page load when reports are resolved, `notification_sent` tracking field (#721)

## [0.48.14] - 2026-03-26

### Removed
- Removed unnecessary `from __future__ import annotations` from 547 files — ban-by-default policy, retained with `# required:` justification in ~145 files with genuine forward references (#717)

### Fixed
- Feedback widget PUT endpoint: added test coverage verifying surface converter generates PUT endpoint and UPDATE service for FeedbackReport (#720)

## [0.48.13] - 2026-03-26

### Fixed
- Feedback widget: all buttons now have `type="button"` — prevents Safari scroll glitch on first click inside `hx-boost` bodies (#722)
- Feedback widget: removed `textarea.focus()` on panel open — eliminates iPad Safari white bar from virtual keyboard reservation (#723)
- Feedback widget: panel height changed from `100vh` to `100dvh` — tracks dynamic viewport excluding virtual keyboard on mobile Safari (#723)

## [0.48.12] - 2026-03-26

### Added
- Universal admin workspace: linker auto-generates `_platform_admin` (and `_tenant_admin` for multi-tenant apps) with profile-gated regions for health, metrics, deploys, processes, sessions, users, and feedback (#686)
- Five synthetic platform entities: `SystemHealth`, `SystemMetric`, `DeployHistory`, `ProcessRun`, `SessionInfo` — backed by existing observability stores (#686)
- `SystemEntityStore` adapter: routes reads for virtual entities to health aggregator, metrics store, and process monitor instead of PostgreSQL (#686)
- Collision detection: `LinkError` raised if user-declared entities/workspaces conflict with synthetic admin names (#686)
- Admin LIST surfaces for all synthetic entities with admin-persona access control (#686)
- Content-hash cache busting: `static_url` Jinja2 filter rewrites asset paths with SHA-256 fingerprints — no build step (#711)
- Project layout convention: recommended `app/` directory structure for custom Python code; `dazzle init --with-app` scaffold (#715)
- Security profile reference: `docs/reference/security-profiles.md` with profile comparison and admin region tables (#705)
- Template override docs: `dz://` prefix, declaration headers, available blocks (#710)

### Fixed
- Feedback widget retry toast no longer shown on page load — silent mode for background retries (#708)
- CSS sidebar hidden on desktop — moved `dz.css` out of `@layer(framework)` so overrides beat DaisyUI (#709)

### Changed
- All schema changes (including framework entities) now go through Alembic — removed raw ALTER TABLE startup path (ADR-0017, #713)
- Virtual entities (SystemHealth, SystemMetric, ProcessRun) excluded from SA metadata — no phantom PostgreSQL tables (#713)

### Deprecated
- Founder console routes (`/_ops/`, `/_console/`) — `X-Dazzle-Deprecated` header added, will be removed in a future release (#686)

### Agent Guidance
- **Admin workspace entities**: The linker now generates synthetic entities with `domain="platform"`. Tests and tools that count entities should filter these out (e.g., `[e for e in entities if e.domain != "platform"]`).
- **Entity naming**: Don't declare entities named `SystemHealth`, `SystemMetric`, `DeployHistory`, `ProcessRun`, or `SessionInfo` — these are reserved by the admin workspace and will cause a `LinkError`.
- **Schema migrations**: Use `dazzle db revision -m "description"` then `dazzle db upgrade` for ALL schema changes, including framework entities. No raw ALTER TABLE (ADR-0017).
- **Static assets in templates**: Use `{{ 'css/file.css' | static_url }}` instead of bare `/static/css/file.css` paths. The filter adds content-hash fingerprints for cache busting.
- **Project layout**: Custom Python code goes in `app/<category>/` (db, sync, render, qa, demo). One-shot scripts go in `scripts/`. Don't create flat `pipeline/` directories.
- **Security profiles**: All three profiles (basic/standard/strict) now include auth and an admin workspace. See `docs/reference/security-profiles.md` for which regions each profile gets.

## [0.48.11] - 2026-03-25

### Fixed
- Feedback widget POST 422: `reported_by` now populated from session email, field made optional (#687)
- Feedback widget CSS: converted `oklch()` to `hsl()` to match design system variable format (#690)
- Missing favicon `<link>` in app `base.html` — 404 console error on all app pages (#691)
- `/__test__/reset` now reads `.dazzle/test_credentials.json` for user creation instead of generic emails (#688)
- Dead-construct lint false positives: surfaces reachable via `nav_group` entity items no longer flagged (#689)

### Agent Guidance
- **FeedbackReport idempotency**: The `idempotency_key` field (str(36), unique) was added to FeedbackReport in #693. Existing deployments need `dazzle db upgrade` to add the column.

## [0.48.10] - 2026-03-25

### Changed
- `process_manager` added to `RuntimeServices`, task route handlers use `Depends(get_services)` (#673)
- Rate-limit globals replaced with `_Limits` dataclass container — eliminates `global` keyword (#673)
- `runtime_tools/state.py` globals (`_appspec_data`, `_ui_spec`) moved to `ServerState` (#673)
- `api_kb/loader.py` cache globals (`_pack_cache`, `_packs_loaded`, `_project_root`) moved to `ServerState` (#673)
- All 17 remaining `global` statements annotated with `# noqa: PLW0603` and mandatory reason (#673)

### Removed
- `src/dazzle/mcp/runtime_tools/state.py` — module deleted, state migrated to `ServerState` (#673)
- `get_process_manager()`, `set_process_manager()` global singleton functions (#673)
- `api_kb.loader.set_project_root()` — cache clearing handled by `ServerState.set_project_root()` (#673)

### Agent Guidance
- **No new singletons** (ADR-0005): Access runtime services via `Depends(get_services)` in route handlers or `request.app.state.services` in middleware. Do not create module-level mutable state.

## [0.48.9] - 2026-03-25

### Changed
- 6 HIGH-risk module-level mutable singletons in `dazzle_back` consolidated into `RuntimeServices` dataclass on `app.state.services` (#673)
- Route handlers access services via `Depends(get_services)`, middleware via `request.app.state.services` (#673)
- Tests use pytest fixtures creating fresh instances instead of global reset functions (#673)

### Removed
- `get_event_bus()`, `set_event_bus()`, `reset_event_bus()` global singleton functions (#673)
- `get_presence_tracker()`, `set_presence_tracker()`, `reset_presence_tracker()` global singleton functions (#673)
- `get_framework()`, `init_framework()`, `shutdown_framework()` global singleton functions (#673)
- `get_collector()`, `reset_collector()`, `get_system_collector()`, `reset_system_collector()` global singleton functions (#673)
- `get_emitter()`, `emit()` global singleton functions (#673)

## [0.48.8] - 2026-03-25

### Changed
- CSS delivery default flipped to local-first (`_use_cdn = False`); CDN opt-in via `[ui] cdn = true` in `dazzle.toml` (#671)
- CSS Cascade Layers (`@layer base, framework, app, overrides`) added to `base.html` and `site_base.html` for explicit cascade ordering (#671)
- New `dazzle-framework.css` entry point replaces standalone `dz.css` loading in local mode (#671)
- `css_loader.py` updated with canonical CSS order, `@layer framework` wrappers, and inline source map (#671)
- `build_dist.py` produces layer-aware `dazzle.min.css` with `@layer framework` wrappers (#671)
- CI publish workflow rebuilds `dist/` at release time for CDN freshness (#671)

### Agent Guidance
- **CSS is local-first**: Static CSS/JS are served from the app, not CDN. The CDN path is opt-in via `[ui] cdn = true` in `dazzle.toml`.
- **Cascade layers**: CSS uses `@layer base, framework, app, overrides`. Framework styles go in `layer(framework)`. Exception: `dz.css` is unlayered so its sidebar overrides beat DaisyUI's unlayered drawer styles.

## [0.48.7] - 2026-03-25

### Fixed
- Workspace regions returning 0 rows: UUID FK attrs from psycopg3 silently dropped in session preferences (#684)
- Feedback widget POST 403 on deployed sites: route now uses direct SQL insert instead of nonexistent repository
- Feedback widget CSS missing from CDN bundle — added to `build_dist.py`

### Added
- Positive auth resolution tests: verify UUID FK attrs resolve through full auth chain, not just deny paths (#684)

### Changed
- PostgreSQL CI job runs only `pytest.mark.postgres` tests (127 tests) instead of full suite (9,143) — ~3 min saved per run

## [0.48.6] - 2026-03-25

### Changed
- `eval_comparison_op` extracted to `dazzle.core.comparison` — eliminates 60-line duplication between `_comparison.py` and `condition_eval.py` (#675)
- `appspec: Any` replaced with `appspec: AppSpec` via `TYPE_CHECKING` across 5 agent mission files (#676)
- `EventFramework.get_bus()` public method replaces all direct `framework._bus` access (#678)
- `AuthStore` public API: `count_users`, `count_active_sessions`, `list_distinct_roles`, `list_sessions`, `store_totp_secret_pending` — eliminates 7 external `_execute` calls (#672)
- `_fastapi_compat.py` TYPE_CHECKING imports — mypy sees real FastAPI types, removes type: ignore cascade (#677)
- `route_generator.py` public handler signatures typed with `BaseService`, `EntityAccessSpec`, `AuditLogger` (#680)

## [0.48.5] - 2026-03-25

### Fixed
- `has_grant()` state machine guard: properly enter `db.connection()` context for GrantStore — was passing context manager generator instead of connection (#669)
- `has_grant()` diagnostic logging: WARNING on missing store/IDs/UUID failures, DEBUG on query results (#669)
- UUID objects passed through without re-casting in `has_grant()` (#669)
- Feedback widget POST route registered at `/feedbackreports` when `feedback_widget.enabled` — was returning 403/404 (#670)

### Changed
- 7 `# type: ignore[no-any-return]` on `json.loads()` replaced with explicit variable annotations (#682)

## [0.48.4] - 2026-03-24

### Added
- SOC 2 Trust Services Criteria taxonomy — 63 controls across 5 categories with DSL evidence mappings (#657)
- Reference documentation for graph features (CTE neighborhood, NetworkX algorithms, domain-scoped graphs) (#656)
- Reference documentation for compliance framework (ISO 27001 + SOC 2 pipeline, CLI, evidence mapping) (#656)
- Grant-based RBAC section in access-control reference (grant_schema, has_grant, four-eyes approval) (#656)
- System endpoints (/health, /_diagnostics) and feedback widget in runtime-capabilities reference (#656)

## [0.48.3] - 2026-03-24

### Fixed
- Connection pool auto-rollback on failed transactions — prevents cascading 500s from poisoned connections (#664)
- `RedisBus.start_consumer_loop()` accepts `poll_interval` kwarg to match base class signature (#662)
- FK fields on detail pages now resolve to `display_field` values instead of showing raw UUIDs (#663)
- ParamRef resolved to its default value before use as field default in `_build_column` (#641)
- GrantStore supports PostgreSQL `%s` placeholders (#640)

### Changed
- Pool `open_pool()` passes a `reset` callback to rollback aborted transactions on connection return
- Detail view template checks `{relation_name}_display` key for ref fields, matching list surface behaviour
- Nav group route dedup prevents entity items appearing in both flat nav and grouped accordion (#661)
- Feedback widget CSS uses oklch fallback values for opaque backgrounds (#660)

## [0.48.2] - 2026-03-24

### Changed
- Event system is now PostgreSQL-only — removed all aiosqlite/SQLite code paths from outbox, inbox, consumer, publisher, and framework (#644)
- `OutboxPublisher`, `IdempotentConsumer`, `idempotent()`: `db_path` parameter removed — use `connect=` instead
- `EventFrameworkConfig`: `db_path` field removed — use `database_url` instead
- `EventOutbox`: `use_postgres` parameter removed — always PostgreSQL
- `EventInbox`: `placeholder`/`backend_type` parameters removed — always PostgreSQL
- Canary dependency probe changed from `aiosqlite` to `psycopg` in `null.py`

### Agent Guidance
- **PostgreSQL only** (ADR-0008): No SQLite code paths remain. All database operations use PostgreSQL via psycopg. Don't propose SQLite as a fallback or dev convenience.

### Fixed
- Feedback widget Jinja global set after `configure_project_templates()` to survive env replacement (#649)
- Workspace grid uses CSS columns for masonry-style card layout — eliminates whitespace gaps (#648)
- `/health` endpoint now reports `version`, `dsl_hash`, and `uptime_seconds` (#651)
- Queue display uses `_display` sibling key for FK ref columns instead of raw dict repr (#654)
- `_eval_func` implements `has_grant()` for state machine transition guards (#653)
- `grant_routes`: `_check_granted_by` reads from `GrantRelationSpec`, not `GrantSchemaSpec` (#650)

### Added
- `/_diagnostics` endpoint (admin-only) returning entity/surface/workspace counts and feature flags (#651)
- Lint warning for FK-target entities missing `display_field` (#652)
- `_extract_roles` helper for compound `ConditionExpr` trees in grant routes (#650)

### Removed
- `aiosqlite` dependency from `events` and `dev` extras in pyproject.toml (#644)
- SQLite DDL constants from outbox.py and inbox.py (#644)
- All `db_path` deprecation shims from event system (#644)

## [0.48.1] - 2026-03-24

### Fixed
- `grant_routes`: `_check_granted_by` now reads `granted_by` and `approval` from `GrantRelationSpec` instead of `GrantSchemaSpec` — fixes 500 error on all grant creation (#650)

### Added
- `_extract_roles` helper to walk `ConditionExpr` trees for compound role expressions (e.g. `role(admin) or role(manager)`)
- `_get_relation_spec` helper for relation-level lookups within grant schemas
- Unit tests for grant routes (`test_grant_routes.py`)

## [0.48.0] - 2026-03-24

### Agent Guidance
- **Grant-based RBAC**: GrantStore is now PostgreSQL-only with atomic state transitions. Use `has_grant()` in state machine guards. See `src/dazzle_back/runtime/grant_routes.py` for the HTTP API.
- **Template overrides**: Use `{% extends "dz://base.html" %}` to extend framework templates from project overrides. Plain `{% extends "base.html" %}` causes infinite recursion.

### Changed
- GrantStore rewritten as PostgreSQL-only — removed all SQLite code paths, `_sql()` helper, and `placeholder` parameter
- Grant tables now use native PostgreSQL types: UUID columns, TIMESTAMPTZ timestamps, JSONB metadata
- State transitions use atomic `UPDATE WHERE status + rowcount` pattern — eliminates TOCTOU race conditions
- `list_grants` uses dynamic WHERE clause construction instead of `IS NULL OR` anti-pattern
- `expire_stale_grants` uses `RETURNING id` for single-pass batch expiry
- `grant_routes.py` docstring and constructor updated for psycopg (was sqlite3)

### Added
- `cancel_grant` transition: `pending_approval → cancelled` (by the granter)
- CHECK constraints on `_grants.status` and `_grant_events.event_type` columns
- Partial index `idx_grants_expiry` for active grants with expiry dates
- FK index `idx_grant_events_grant_id` on grant events table
- Cancel endpoint: `POST /api/grants/{id}/cancel`
- UUID validation at HTTP boundary in grant routes (`_parse_uuid` helper)
- Concurrency tests proving one-winner property for competing state transitions
- PostgreSQL integration tests via `TEST_DATABASE_URL` (skip when not set)

### Removed
- SQLite support in GrantStore — PostgreSQL is the sole supported backend
- `_sql()` placeholder rewriting helper
- `placeholder` parameter on GrantStore constructor

## [0.47.2] - 2026-03-23

### Fixed
- Rebuilt `dist/dazzle.min.js` CDN bundle — stale `dzWorkspaceEditor` signature caused Alpine init failure (#638)
- Context selector `scope_field` now reads domain attributes from `auth_ctx.preferences` instead of `user_obj` (#639)
- Data island `layout_json` uses `| safe` filter to prevent Jinja2 entity-encoding inside `<script>` tags (#635 follow-up)

## [0.47.1] - 2026-03-23

### Fixed
- Workspace layout JSON now embedded as `<script type="application/json">` data island instead of inlined in `x-data` HTML attribute — eliminates JSON/HTML escaping conflict (#632, #635)
- Nav: workspace home link now renders above collapsible nav_groups (#630)
- Heatmap region click-through uses FK target entity ID instead of source item ID (#633)
- Tailwind safelist for `col-span-{4,6,8,12}` at responsive breakpoints — workspace card width customisation now takes effect (#631)
- Context selector: `scope_field` wired into options route + `htmx.ajax()` for unconditional region refresh (#634)
- Event framework startup hang with remote Postgres: added `connect_timeout=10` + lazy pool open + REDIS_URL forwarding (#636)

### Added
- Grant management API: `POST/GET/DELETE /api/grants/*` endpoints wrapping existing `GrantStore` — unblocks `has_grant()` transition guards (#629)
- `dazzle serve --local-assets/--cdn-assets` flag — serve JS/CSS from local installation instead of CDN; defaults local in dev, CDN in production (#637)

## [0.47.0] - 2026-03-23

### Added
- `feedback_widget` DSL keyword with parser mixin, IR model (`FeedbackWidgetSpec`), and auto-entity generation
- Auto-generated `FeedbackReport` entity with lifecycle state machine (new → triaged → in_progress → resolved → verified) when `feedback_widget: enabled` is declared
- Client-side feedback widget (JS/CSS) injected into authenticated pages — safe DOM construction, idempotency keys, rate limiting, offline retry
- Apps can override auto-entity by declaring their own `FeedbackReport` entity

### Changed
- Database migrations now use Alembic instead of hand-rolled `MigrationPlanner`
- `dazzle db migrate` generates and applies migrations in one step
- `dazzle db rollback` reverts migrations with optional revision target
- Type changes detected automatically via `compare_type=True`
- `dazzle serve --production` refuses to start with pending migrations
- Linker `_parse_field_type` now supports `ref <Entity>` and `float` types

### Added
- Compliance documentation compiler: maps DSL metadata to framework controls
- `dazzle compliance compile` / `evidence` / `gaps` CLI commands
- MCP `compliance` tool with 5 operations (compile, evidence, gaps, summary, review)
- ISO 27001:2022 taxonomy (93 controls, 4 themes)
- Pydantic models for Taxonomy, EvidenceMap, AuditSpec IR
- `[compliance]` optional extra in pyproject.toml
- Safe cast registry: text→uuid, text→date, text→timestamptz, text→jsonb applied automatically with USING clauses
- `dazzle db migrate --check` dry-run to preview schema changes
- `dazzle db migrate --tenant <slug>` for per-tenant schema migration

### Removed
- `MigrationPlanner`, `MigrationExecutor`, `MigrationHistory` classes (~400 lines)
- `auto_migrate()` / `plan_migrations()` functions — replaced by Alembic

## [0.46.5] - 2026-03-23

### Fixed
- 77 mypy type errors across `dazzle_back` and `dazzle.core` (Redis async unions, bare `dict` params, missing `column` arg in `make_parse_error`, missing `_build_graph_filter_sql`)
- Gitignore `.claude/projects/` local session data

## [0.46.4] - 2026-03-22

### Fixed
- Suppress misleading "permit without scope" linter warning on framework-generated entities (e.g. AIJob from `llm_intent` blocks)

## [0.46.3] - 2026-03-22

### Added
- `--production` flag on `dazzle serve` — binds 0.0.0.0, reads PORT env var, requires DATABASE_URL, structured JSON logging, disables dev features
- `dazzle deploy dockerfile` — generates production Dockerfile + requirements.txt
- `dazzle deploy heroku` — generates Procfile, runtime.txt, requirements.txt
- `dazzle deploy compose` — generates production docker-compose.yml

### Removed
- Container runtime (`dazzle_ui.runtime.container`) — replaced by `dazzle serve --production`
- `DockerRunner` and Docker template generation — replaced by `dazzle deploy`
- `dazzle rebuild` command — prints migration message directing to `dazzle deploy dockerfile`

### Fixed
- `float` type missing from frontend spec export `FIELD_TYPE_MAP`
- `target:` keyword not recognized in integration transform block parser
- Stale test snapshots for graph semantics and streamspec error types
- Content negotiation test mocks returning truthy MagicMock for `query_params.get()`

## [0.46.2] - 2026-03-22

### Fixed
- Legacy scope condition path (via clauses) now catches exceptions instead of 500 (#617)
- Graph materialization SQL uses `quote_identifier` for defense-in-depth

## [0.46.1] - 2026-03-22

### Added
- `float` field type — IEEE 754 double precision for sensors, weights, and scores (#620)

### Fixed
- Float type included in tagged release (v0.46.0 tag predated the float commit)

## [0.46.0] - 2026-03-22

### Added
- **Graph Semantics** — full directed property multigraph support in the DSL (#619)
  - Phase 1: `graph_edge:` and `graph_node:` blocks on entities with validation and lint hints
  - Phase 2: `?format=cytoscape|d3` on edge entity list endpoints via `GraphSerializer`
  - Phase 3: `GET /{entity}/{id}/graph?depth=N` neighborhood traversal via PostgreSQL recursive CTE
  - Phase 4: Shortest path and connected components via optional NetworkX integration
- Domain-scoped graph algorithms (per-work graph partitioning via filter params)
- `networkx>=3.0` as optional `[graph]` extra

## [0.45.5] - 2026-03-22

### Added
- Graph algorithms: shortest path + connected components endpoints (#619 Phase 4)
- `GraphMaterializer` — on-demand DB → NetworkX graph materialization
- Domain-scoped algorithms via filter params (`?work_id=uuid`) for partitioned graphs
- NetworkX as optional dependency (`pip install dazzle-dsl[graph]`)

## [0.45.4] - 2026-03-22

### Added
- Neighborhood endpoint: `GET /{entity}/{id}/graph?depth=N&format=cytoscape|d3` (#619 Phase 3)
- `NeighborhoodQueryBuilder` — PostgreSQL recursive CTE for graph traversal
- Directed and undirected traversal with automatic cycle prevention via UNION
- Scope predicate injection into CTE WHERE clauses
- Configurable depth bound (1–3 hops)

## [0.45.3] - 2026-03-22

### Added
- Graph serializer: `?format=cytoscape|d3` on edge entity list endpoints (#619 Phase 2)
- `GraphSerializer` class for Cytoscape.js and D3 force-graph JSON output
- Heterogeneous graph support (bipartite graphs with different node entity types)
- Node batch-fetch with scope/permit enforcement

## [0.45.2] - 2026-03-22

### Added
- `graph_edge:` and `graph_node:` blocks on entities — formal graph semantics declarations (#619)
- Graph validation: field references, type checks, cross-entity consistency
- Lint hints: suggest `graph_edge:` for entities with 2+ refs to same entity, suggest `graph_node:` for targeted entities
- Grammar reference updated with graph semantics BNF

## [0.45.1] - 2026-03-22

### Fixed
- CDN bundle at v0.45.0 tag missing Alpine + workspace editor — rebuilt with all components (#615, #618)
- CSRF middleware rewritten as pure ASGI to fix body consumption (#606)
- Scope predicate resolution: most-permissive-wins for dual-role users (#604), pass-through for no-scope entities (#607), Tautology detection (#604)
- Graceful handling of null FK in EXISTS scope bindings (#617)
- MCP db handlers converted to async (#609), topology/triggers import path fixed
- `/create` guard routes registered before `/{id}` routes (#598)
- Circular FK references demoted to warning (#608), decimal parse error improved (#610)
- EntitySpec.relations and FieldSpec.unique API mismatches in migrate (#616)
- Workspace action URL interpolation with cross-entity FK fields (#614)
- Lucide sourcemap 404 in Safari stripped
- Security test updated for CSRF middleware class rename
- `/check` and `/ship` mypy targets aligned with CI (src/dazzle_back/)

### Added
- 15 runtime contract KB entries (display_field, scope, CSRF, request lifecycle, etc.)
- Purpose-annotated `implemented_by` on KB concepts
- `graph topology` operation — derive project structure from DSL
- Knowledge effectiveness metrics in telemetry
- `/improve` autonomous improvement loop (BDD pattern)
- Alpine.js `$persist` plugin for localStorage state
- Example app DSL quality improvements across 6 apps (scope blocks, workspace wiring, ux blocks)

### Changed
- dz.js fully retired — all UI state managed by Alpine.js components in dz-alpine.js

## [0.45.0] - 2026-03-21

### Added
- **Conformance Role 2**: HTTP execution engine — boots FastAPI in-process, seeds fixtures via `/__test__/seed`, runs all derived cases as HTTP assertions (#601)
- **Stage invariant verification**: three-stage verifier for predicate compilation chain (ConditionExpr → ScopePredicate → SQL → resolved params) (#603)
- **Runtime contract monitoring**: `ConformanceMonitor` captures access decisions during scenario execution and compares against expected conformance cases (#602)
- `dazzle conformance execute` CLI command for running HTTP conformance against PostgreSQL
- `monitor_status` MCP operation on conformance tool
- `?q=` alias for `?search=` on all API list endpoints (#596)
- Bare `?field=value` query params accepted when field is in DSL `ux: filter:` list (#596)
- `build_entity_filter_fields()` extracts filter allowlist from surface UX declarations
- Alpine.js `$persist` plugin (835B) for localStorage state management
- `dz-alpine.js` — Alpine.data() components replacing dz.js: dzToast, dzConfirm, dzTable, dzMoney, dzFileUpload, dzWizard (#600)
- `param` DSL construct for runtime-configurable parameters with tenant-scoped cascade (#572)
- `param("key")` reference syntax in workspace region constructs (heatmap thresholds)
- `_dazzle_params` table for storing per-scope parameter overrides
- `param list/get/validate` MCP operations and CLI commands
- Startup validation of stored param overrides against DSL declarations
- `dazzle e2e journey` — persona-driven E2E testing against live deployments (#557)
- Two-phase execution: deterministic workspace exploration + LLM story verification
- Cross-persona pattern analysis with structured HTML reports
- `test_intelligence journey` MCP operation (read-only)
- `.dazzle/test_personas.toml` credential file for journey testing
- `dazzle demo propose` now generates test persona credentials
- `not via` syntax for NOT EXISTS scope rules
- `not (...)` parenthesised negation in scope rules
- depth-N FK path traversal in scope rules (previously depth-1 only)
- Static validation of scope rule FK paths at `dazzle validate` time
- Runtime startup assertion verifies all scope predicates compile

### Changed
- Scope rules compile to formal ScopePredicate algebra with FK graph validation
- OR conditions in scope rules now compile to SQL OR (previously post-fetch filtered)
- Template strings replaced with contextual variables (`app_name`, `entity_name`) across 10 templates (#593)
- Console routes derive `app_name` from AppSpec instead of hardcoding "Dazzle Console"
- All UI state management migrated from dz.js to Alpine.js (#600)

### Removed
- `dz.js` micro-runtime (1102 lines) — replaced by Alpine.js components in `dz-alpine.js`
- Post-fetch OR filtering for scope rules (replaced by SQL OR)

### Fixed
- CSRF middleware now exempts `/__test__/` and `/dazzle/dev/` paths (internal-only endpoints)

## [0.44.0] - 2026-03-19

### Added
- **Schema-per-tenant isolation** — `TenantMiddleware` with subdomain/header/session resolvers, registry cache, `pg_backend` context-var routing, `--tenant` flag on `dazzle db` commands (#531)
- **Domain user attribute resolution** — auth session validation merges DSL User entity fields into `auth_context.preferences` so scope rules like `current_user.school` resolve correctly (#532)
- **Via clause entity ID resolution** — bare `current_user` in via clauses now resolves to DSL User entity PK via `preferences["entity_id"]` (#534)
- **DSL anti-pattern guidance** — 5 modeling anti-patterns (polymorphic keys, god entities, soft-delete booleans, stringly-typed refs, duplicated fields) surfaced via inference KB, lint warnings, and `_guidance` string
- **External action links** — new `OutcomeKind.EXTERNAL` and `external` keyword for URL-based action links on surfaces (#542)
- **Docker dev infrastructure** — `dazzle serve` (Docker mode) now starts Postgres+Redis via Docker Compose while running the app locally (#540, #541)

### Fixed
- Scope rules using `current_user.school` resolve to null — auth users lacked domain attributes (#532)
- Via clause `current_user` resolved to auth user ID instead of DSL entity ID (#534)
- Test generator didn't populate nullable FKs required by 3-way OR invariants (#533)
- 4 pre-existing CI failures (type-check, security tests, PostgreSQL tests, E2E smoke) all resolved
- 6 bare `except Exception: pass` sites given proper logging
- `_pack_cache` thread-safety gap fixed via atomic snapshot replacement
- HTTP retry coverage gap — 4 unretried outbound call sites retrofitted
- Docker container runtime SQLite → PostgreSQL default (#541)

### Changed
- **`server.py` subsystem migration** — reduced from 2,214 to 936 lines; `IntegrationManager` and `WorkspaceRouteBuilder` moved to standalone modules; circular import with `app_factory.py` eliminated (#535)
- **Route factory extraction** — all 13 route factory mega-functions (300-784L each) refactored: handlers extracted to module level with `_XxxDeps` dataclasses, factories shrunk to route registration (#536)
- **Parser nesting depth** — top 4 offenders flattened: `execute_step` (depth 24→dispatch), `_parse_single_step` (22→field parsers), `parse_type_spec` (20→sub-parsers), `handle_runtime_tool` (18→dispatch table) (#537)
- **`dazzle_back` public API** — `__init__.py` exports 11 symbols via lazy loaders; CLI/MCP no longer reach into `dazzle_back.runtime.*` internals (#539)
- Duplicated `error_response`/`unknown_op_response` in `handlers_consolidated.py` removed
- 8 `Any` annotations replaced with concrete `TYPE_CHECKING` types
- `ViaBinding` and `ViaCondition` added to `ir.__init__.__all__`
- Shapes validation DSL fixed: `or` syntax in permit blocks, missing PKs and persona

## [0.43.0] - 2026-03-18

### Added
- **RBAC Verification Framework** — three-layer provable access control: static access matrix (Layer 1), dynamic verification (Layer 2), decision audit trail (Layer 3)
- `dazzle rbac matrix` CLI command — generate (role, entity, operation) → permit/deny matrix from DSL
- `dazzle rbac verify` CLI command (stub) — dynamic verification pipeline
- `dazzle rbac report` CLI command — compliance report from verification results
- `policy access_matrix` and `policy verify_status` MCP operations
- `src/dazzle/rbac/` package: `matrix.py`, `audit.py`, `verifier.py`, `report.py`
- `AccessDecisionRecord` audit trail with pluggable sinks (Null, InMemory, JsonFile)
- `evaluate_permission()` instrumented to emit audit records on every decision
- `examples/shapes_validation/` — abstract RBAC validation domain (7 personas, 4 entities) exercising RBAC0/RBAC2/ABAC/multi-tenancy patterns
- CI security gate: Shapes RBAC matrix validated on every push (fails if any entity is PERMIT_UNPROTECTED)
- Two-tier access control evaluation model documented in `docs/reference/access-control.md`
- RBAC verification deep-dive with academic references in `docs/reference/rbac-verification.md`
- README "Provable RBAC" section

### Fixed
- **Critical: LIST gate silently disabled for all role-based access rules** (#520) — `_is_field_condition()` now correctly classifies role_check conditions as gate-evaluable
- Sidebar navigation not filtered by role — restricted workspaces now hidden from unauthorized users (#521)
- Workspace region filters fall back to unfiltered when result is empty (#522)
- HTMX workspace region loading no longer causes unintended page navigation (#523)
- URL scheme validation in `_sync_fetch` prevents file:// SSRF (#519)
- SQL table name validation in control_plane `_delete_all_rows()` (#519)

### Changed
- 14 code smells fixed from systematic analysis (#504–#518): `_sessions` race condition locked, `__self_service__` monkey-patch removed, comparison logic deduplicated across 3 evaluators, 6 `_generate_field_value` implementations consolidated, FastAPI import guards centralized, HTTP error responses standardized, mutable globals protected with locks, core→backend layer boundary restored, dazzle_ui→dazzle_back dependency made one-directional, subsystem plugin infrastructure created, deep nesting reduced in parser/tokenizer/test runner
- `DazzleBackendApp` partially decomposed into subsystem plugins (9 modules, 6 dead `_init_*` methods removed)

### Removed
- `__self_service__` dynamic attribute pattern in route_generator.py
- 17 duplicate FastAPI import guard blocks (replaced by `_fastapi_compat.py`)
- `hx-push-url="true"` from workspace region templates (redundant with drawer JS)

## [0.42.0] - 2026-03-14

### Added
- **Surface field visibility by role** (`visible:` condition on sections and fields) — role-based RBAC for hiding sensitive fields/sections without duplicating surfaces (#487)
- `visible:` supports `role()`, `has_grant()`, compound `and`/`or` via existing ConditionExpr system
- `visible:` and `when:` can coexist on the same field (role-based vs data-driven visibility)
- **Grant schema infrastructure** — `grant_schema` DSL construct with `relation` sub-blocks, `has_grant()` condition function, `GrantStore` runtime with SQLite-backed CRUD and audit events
- Grant pre-fetching in workspace rendering for synchronous condition evaluation

### Fixed
- Pulse compliance scoring now reads DSL `classify` directives (confidence=1.0) before pattern matching (#488)
- Pulse security scoring counts default-deny as deliberate secure posture instead of penalising it (#488)
- `when_expr` silently dropped in multi-section (wizard) surface forms — now correctly propagated
- Auto-generate READ endpoints for entities with LIST surfaces (#482)
- Resolve `current_user` in workspace filters in test mode (#483)
- Cross-entity navigation resolved by shared workspace nav_groups (#477)
- Infer experience reachability from access spec (#476)

## [0.41.1] - 2026-03-12

### Changed
- `dazzle workshop` rewritten from Rich to Textual TUI with keyboard-driven drill-down
  - DashboardScreen: live active tools + recent completed history
  - SessionScreen: all calls grouped by tool, collapsible groups
  - CallDetailScreen: full progress timeline for a single call
  - Navigation: Enter to drill in, Esc to go back, j/k for movement
- Workshop now requires `textual>=1.0.0` via optional `workshop` extra

### Added
- Handler progress instrumentation: 15 handlers now emit structured progress events
  - pipeline, story.coverage, dsl_test, sentinel, composition, e2e_test,
    dsl.validate, dsl.fidelity, discovery, process.coverage, nightly
- `context_json` on tool completion events for structured summaries in workshop

## [0.41.0] - 2026-03-12

### Added
- **Convergent BDD:** `rule` DSL construct — domain-level business invariants with `kind` (constraint/precondition/authorization/derivation), `origin` (top_down/bottom_up), and `invariant` fields
- **Convergent BDD:** `question` DSL construct — typed specification gaps that block artifacts until resolved, with `blocks`, `raised_by`, and `status` fields
- `exercises:` field on stories — links stories to rules they exercise for convergence tracking
- Rule and question parser mixins (`RuleParserMixin`, `QuestionParserMixin`)
- Rule and question emitters (`emit_rule_dsl`, `emit_question_dsl`, `append_rules_to_dsl`, `append_questions_to_dsl`)
- Linker validation: rule scope, story exercises, question blocks, open-question-blocks-accepted-artifact error
- MCP operations: `rule_propose`, `rule_get`, `rule_coverage`, `question_get`, `question_resolve` (story tool); `converge`, `question_raise` (discovery tool)
- `rule(coverage)` and `rule(converge)` pipeline quality steps
- Convergence handler: structural analysis of rule-story alignment, gap detection, coverage scoring
- Semantics KB: `rule`, `question`, `convergence` concepts with aliases and relations

### Changed
- **Breaking:** Stories now use DSL-only persistence (`dsl/stories.dsl`) — removed JSON persistence layer (`stories.json`, `StoriesContainer`, `_inject_json_stories`)
- **Breaking:** `unless` keyword on stories raises parse error — use `rule` construct with boundary stories instead
- Story IR uses Gherkin fields (`given`, `when`, `then`) — removed legacy fields (`preconditions`, `happy_path_outcome`, `side_effects`, `constraints`, `variants`, `created_at`, `accepted_at`)
- `rbac_validation` example migrated from `unless` to rule + boundary story pattern

### Removed
- `StoryException` class and `unless` field from `StorySpec`
- `unless` handling from fidelity scorer, process proposals, process coverage, serializers
- `unless_block` from grammar
- `src/dazzle/core/stories_persistence.py` — JSON read/write layer
- `StoriesContainer` class and `with_status()` / `effective_given` / `effective_then` helpers
- `_inject_json_stories()` from appspec loader

## [0.40.0] - 2026-03-11

### Added
- Rhythm fidelity metric: `fidelity` operation measures how well surfaces serve scene intent by comparing `expects:` keywords against surface field names (#450)
- Surface reuse detection: `evaluate` handler flags surfaces used in multiple scenes with divergent `expects:` values as specialization signals (#448)
- Standardized action vocabulary: 7 action verbs mapped to 3 archetypes (observe, act, decide) with `classify_action()` API and advisory warnings for non-standard verbs (#449)
- Phase-level `depends_on:` field for declaring phase ordering constraints with circular dependency detection (#451)
- Phase kind `gate` for mandatory completion phases (#451)
- Phase-level `cadence:` field for temporal frequency hints (#447)
- Persona-scoped coverage metric respecting surface ACL `allow_personas`/`deny_personas` (#446)
- Scenes can target workspaces via `on:` field, tracked separately in coverage (#445)

### Fixed
- Rhythm `story:` field now accepts quoted strings for hyphenated IDs like `"ST-020"` (#452)

## [0.39.0] - 2026-03-11

### Added
- Rhythm DSL construct: `rhythm`, `phase`, `scene` keywords for longitudinal persona journey evaluation (#444)
- Rhythm MCP tool with 5 operations: `propose`, `evaluate`, `coverage`, `get`, `list`
- Static rhythm evaluation: surface existence, entity coverage, navigation coherence checks
- Rhythm conceptual guide (`docs/guides/rhythms.md`) and reference page (`docs/reference/rhythms.md`)

## [0.38.1] - 2026-03-10

### Added
- Declarative transition side effects: `on_transition:` blocks fire `create`/`update` actions on entity state changes (#435)
- Configurable per-field max upload size: `file(200MB)` DSL syntax overrides global security profile limit (#436)
- Post-upload event hook: `FILE_UPLOADED` event emitted to event bus after file upload with entity context; `entity.post_upload` hook point for Python hooks (#437)

## [0.38.0] - 2026-03-09

### Fixed
- Nav group `items` key collision with Python `dict.items()` in Jinja2 — renamed to `children` to fix TypeError/500 on workspace pages with nav_groups (#421)

### Added
- Documentation infrastructure: `dazzle docs generate` renders TOML knowledge base into human-readable reference docs; `dazzle docs check` validates coverage
- 17 auto-generated reference doc pages covering all DSL constructs (entities, access control, surfaces, workspaces, LLM, processes, ledgers, governance, etc.)
- 13 new knowledge base concepts for previously undocumented features (nav_group, approval, SLA, webhook, LLM triggers, visibility rules, etc.)
- README.md overhauled — slimmed from 1247 to 509 lines with auto-generated feature table linking to reference docs
- Deterministic demo data loading: `dazzle demo load` loads seed CSV/JSONL files into a running instance via REST API with FK-aware topological ordering (#420)
- `dazzle demo validate` validates seed files against DSL (FK integrity, enum values, field coverage)
- `dazzle demo reset` clears and reloads demo data (deletes in reverse dependency order, then reloads)
- MCP `demo_data` tool: new `load` and `validate_seeds` operations complete the propose → save → generate → load lifecycle
- LLM intent execution: `/_dazzle/llm/execute/{intent_name}` triggers intents at runtime, records AIJob for cost tracking
- MCP `llm` tool: `list_intents`, `list_models`, `inspect_intent`, `get_config` operations
- Collapsible navigation groups with Lucide icon support in workspace DSL (`nav_group` keyword) and app shell sidebar (#418)
- LLM async event queue: background job queue with token-bucket rate limiting and per-model semaphore concurrency (#417)
- LLM entity triggers: `trigger:` clause on `llm_intent` fires intents on entity created/updated/deleted events with input mapping, write-back, and conditional execution
- `llm_config` gains `concurrency:` block for per-model max concurrent request limits
- Process `llm_intent` step kind: processes can now execute LLM intents as steps with `input_map` context resolution
- Linear checkpointed process executor: sequential step execution with checkpoint-based resume on restart
- Async job execution: `POST /_dazzle/llm/execute/{intent_name}?async_mode=true` queues jobs and returns `job_id`; poll with `GET /_dazzle/llm/jobs/{job_id}`
- MCP `graph` tool: new `triggers` operation shows cross-references (what fires when entity X event Y occurs)
- Workspace context selector: multi-scope users get a dropdown to filter all workspace regions by a scope entity (e.g., School) with preference persistence (#425)
- DSL-driven reference data seeding: entities with `seed:` blocks auto-generate rolling-window rows (academic years, fiscal years) at server startup with idempotent upsert (#428)
- FK traversal support in workspace region filter validation (#419)

## [0.37.0] - 2026-03-07

### Added
- AST-level test verifying all server startup paths pass `app_prefix` to `create_page_routes` — prevents #408-style regressions
- AST-level test ensuring auth routes returning `Response` use `include_in_schema=False` — prevents #411-style regressions

### Changed
- Unified server startup paths: `run_unified_server()` and `create_app_factory()` now share `build_server_config()` and `assemble_post_build_routes()`
- `dazzle serve --local` gains experience routes, entity list projections, search fields, auto-includes, schedule sync
- `create_app_factory()` gains route validation
- `run_backend_only()` gains entity projections and search fields

### Fixed
- `dsl-run --cleanup` now cascade-deletes child records before parents, preventing orphaned rows from FK references (#407)
- Sidebar nav links missing `/app` prefix in `dazzle serve` mode — `combined_server.py` now passes `app_prefix="/app"` to `create_page_routes` (#408)
- `ref_display` chain now recognises `forename`/`surname` fields — FK columns for UK naming conventions show names instead of UUIDs (#409)
- `dsl-run --cleanup` no longer queries API for child records — uses topological sort of tracked entities, avoiding RBAC 403 errors (#410)
- `/openapi.json` no longer crashes with `PydanticUserError` — auth and email tracking routes returning `Response` excluded from schema (#411)

## [0.36.0] - 2026-03-07

### Added
- `events` extras group (`pip install dazzle-dsl[events]`) for optional event system dependency (aiosqlite)
- `NullBus` and `NullEventFramework` no-op implementations in `dazzle_back.events.null` — always importable regardless of extras
- `dazzle_back.events.api` public API boundary module for alternative event bus implementations
- Wire `EventEmittingMixin.set_event_framework()` at server startup (fixes dead code bug)
- Event system imports gated behind `EVENTS_AVAILABLE` flag — apps without event extras stay lean

### Fixed
- Workspace redirect missing `/app` prefix — `_workspace_root_route()` now returns `/app/workspaces/{name}` (#406)
- Login form ignoring persona-specific redirect URL — now uses `redirect_url` from server response (#406)
- Role prefix mismatch preventing persona-based routing — `role_` prefix now stripped when matching user roles against persona IDs in auth redirect, RBAC checks, nav filtering, and workspace access (#406)

## [0.35.0] - 2026-03-06

### Added
- **Team section type** (`type: team`) — dedicated cards for team/people pages with circular avatar (image or auto-generated initials), name, role, bio, and social links (linkedin, email, twitter, github) (#394)
- **Section backgrounds** — `background: alt | primary | dark` on any section for visual rhythm; `layout.section_backgrounds: auto-alternate` for automatic alternating backgrounds (#395)
- **Media rendering** in `card_grid` and `features` sections — `section_media()` macro in `_helpers.html` for reusable section-level images (#396)
- **Validation warning** when `media` is set on section types that don't render it (#396)
- **`sitespec advise` MCP operation** — proactive layout suggestions: missing hero sections, background variation, team section recommendations, long markdown splitting (#397)
- **Media.src path validation** — `sitespec validate` warns on non-`/static/` paths and missing files; imagery prompts include `save_to` and `sitespec_src` fields (#391)
- jsDelivr CDN distribution — framework CSS/JS served from `cdn.jsdelivr.net` for faster loading and cache sharing across Dazzle-powered sites
- `dist/dazzle.min.css` (43 KB) — micro-runtime + design system + site sections CSS bundle
- `dist/dazzle.min.js` (131 KB) — HTMX + extensions + micro-runtime JS bundle
- `dist/dazzle-icons.min.js` (350 KB) — Lucide icons bundle (site pages only)
- `scripts/build_dist.py` — concatenates and minifies framework assets into `dist/`
- `scripts/update_vendors.py` — checks/downloads latest vendor JS versions (htmx, idiomorph, lucide)
- `.github/workflows/update-vendors.yml` — weekly automated vendor update PR
- `[ui] cdn = false` in `dazzle.toml` — disables CDN for air-gapped deployments
- `_dazzle_version` and `_use_cdn` Jinja2 globals in template renderer

### Changed
- `base.html` and `site_base.html` now load framework assets from jsDelivr CDN by default, with local vendored fallback when CDN is disabled

### Fixed
- **Legal page CSS** — constrained width (45rem) and left-aligned headings for terms/privacy pages (#393)
- **Markdown `<hr>` styling** — horizontal rules render as subtle centered gradient lines instead of crude browser default (#398)
- **Infrastructure banner** no longer shows stale `.dazzle/data.db` or "Lite (in-process)" when PostgreSQL is configured (#390)
- **Circular FK migration** — `Department ↔ User` foreign keys no longer fail migration (#389)
- **Heroku deployment** — `[serve]` extra installs runtime dependencies (`uvicorn`, `gunicorn`, etc.) (#388)

### Removed
- `LiteProcessAdapter` and `DevBrokerSQLite` — deprecated SQLite-based process/event backends fully removed; PostgreSQL is now required for event bus
- `SQLITE` tier from `EventBusTier` enum

## [0.34.0] - 2026-02-23

### Added
- `ApiResponseCache` — async Redis cache for external API responses with scoped keys, dedup locking, and lazy connection (`dazzle_back.runtime.api_cache`)
- `cache:` keyword in integration mapping blocks — per-mapping TTL (e.g. `cache: "24h"`) parsed via `parse_duration()`
- Fragment route caching — search (5 min TTL) and select (1 hour TTL) endpoints use shared `ApiResponseCache`
- `cache_ttl` values for all API pack foreign models — data-volatility-appropriate defaults across all 10 packs
- `format_duration()` helper — converts seconds to compact duration strings (86400 → "1d", 300 → "5m")
- `ApiPack.generate_integration_template()` — generates DSL integration blocks with `cache:` directives from pack metadata
- `generate_service_dsl` MCP handler now returns `integration_template` field with recommended cache settings
- Pack TTL fallback in `MappingExecutor` — when no `mapping.cache_ttl` is set, looks up the pack's foreign model `cache_ttl` before falling back to the default
- Built-in entity CRUD operations for process service steps — `Entity.create`, `Entity.read`, `Entity.update`, `Entity.delete`, `Entity.transition` now execute directly against PostgreSQL without requiring custom Python service modules (#345)
- Entity metadata (fields, status_field) stored in Redis at startup by `ProcessManager` for Celery worker access
- `query` step kind — queries entities matching Django-style filters (e.g. `{"due_date__lt": "today", "status__not_in": ["completed"]}`) with date literal resolution (#346)
- `foreach` step kind — iterates over query results and executes sub-steps for each item, enabling batch operations like escalation workflows (#346)
- AI cost tracking gateway — `budget_alert_usd`, `default_provider` on `llm_config`; `vision`, `description` on `llm_intent`; auto-generated `AIJob` entity for cost/token audit trail (#376)
- Integration data transformation — `transform:` block on integration mappings with `jmespath`, `template`, and `rename` expressions (#383)
- Workflow Field Specification (WFS) — `wfs_fields:` block on process steps for field-level read/write/required declarations with runtime enforcement (#375)

### Changed
- `MappingExecutor` now accepts `cache: ApiResponseCache | None` instead of auto-creating sync Redis. All cache operations are async
- Cache keys scoped to `api_cache:{scope}:{url_hash}` preventing collisions across integrations
- Cache TTL priority chain: DSL `cache:` directive > pack TOML `cache_ttl` > default 86400
- Replaced `getattr()` string literals with typed attribute access across agent missions, persona journey, workspace/UI files (#367)
- Eliminated `BackendSpec` from main code path — runtime uses `AppSpec` directly (#369)
- Wired `EventBusProcessAdapter` into app startup, simplified Procfile (#368)
- Eliminated Celery dependency for event bus — native async process adapter (#368)
- Fixed silent exception handlers in event delivery path (#365)

### Improved
- Eliminated 8 swallowed exceptions (`except Exception: pass`) — all now log at appropriate levels (debug/info/warning)
- Extracted Cedar/audit helpers in `route_generator.py` — `_build_access_context()`, `_record_to_dict()`, `_log_audit_decision()` replace ~140 lines of duplicated code across 7 handler closures
- Canonicalized AppSpec loading in `tool_handlers.py` — 7 inline manifest→discover→parse→build patterns replaced with single `load_project_appspec()` calls

### Fixed
- `ProcessStateStore` UUID serialization error — `json.dumps()` now uses a custom encoder that handles `uuid.UUID`, `datetime`, `date`, and `Decimal` objects from psycopg v3 / SQLAlchemy (#344)
- `create_app_factory()` now loads persisted processes from `.dazzle/processes/processes.json` — previously only DSL-parsed processes were used, leaving ProcessManager empty when processes were composed via MCP (#343)
- Sync Redis in async context — replaced `import redis` with `redis.asyncio` in cache layer
- `cache=False/None` still created cache — disabled state now respected via `enabled` flag
- Dedup lock never released — `release_lock()` called in `finally` block after HTTP response
- Lock key collisions across integrations — keys now include `{integration}:{mapping}` scope
- `force_refresh=True` blocked by dedup lock — lock check skipped when force-refreshing
- Blocking `redis.ping()` in constructor — connection is now lazy (first `get()`/`put()`)
- Hardcoded `ssl.CERT_NONE` — removed, uses redis-py defaults (validates certs)
- CI test `test_crud_service_with_repository` — fixture missing surface, service name convention mismatch

### Removed
- `IntegrationCache` class from `mapping_executor.py` — replaced by `ApiResponseCache`

## [0.33.0] - 2026-02-19

### Added
- Canonical AppSpec loader (`dazzle.core.appspec_loader`) — single implementation of manifest → discover → parse → build pipeline, replacing 6 duplicate copies (#329)
- `error_response()` and `unknown_op_response()` factory functions in MCP handler common module, replacing ~100 inline `json.dumps({"error": ...})` calls (#329)
- Experience flow entity orchestration — `context:`, `prefill:`, `saves_to:`, `when:` blocks for multi-entity experience steps (#326)
- Process step side-effect actions for cross-entity automation (#323)
- Multi-source workspace regions with tabbed display (#322)
- Guided review surface mode with queue navigation and approve/return actions (#325)
- Experience flow resume with durable file-based progress persistence (#324)
- Polymorphic FK detection for related entity tabs (#321)

### Changed
- HTMX utilities (`HtmxDetails`, `htmx_error_response`) moved from `dazzle_back` to `dazzle_ui.runtime.htmx` — correct layer ownership (#329)
- Backward compatibility policy: clean breaks preferred over shims; breaking changes communicated via CHANGELOG (#329)

### Removed
- Backward-compat shims: `get_project_path()` alias, pipeline/nightly aliases, archetype→stage aliases, `paths.py` re-export module, `handlers/utils.py` re-export module, `site_renderer.py` shim functions, `DNRDevServer`/`DNRDevHandler` aliases, `docker_runner.py` re-export module (#329)
- Deprecated `db_path` parameters from 6 constructor signatures (`TokenStore`, `AuthStore`, `FileMetadataStore`, `OpsDatabase`, `DeviceRegistry`, `create_local_file_service`, `create_s3_file_service`) (#329)
- CLI utils backward-compat aliases (`_print_human_diagnostics`, etc.) (#329)

### Fixed
- Last 2 swallowed exceptions in `workspace_rendering.py` now log at WARNING level (#329)
- Expression evaluator duplication eliminated — shared `dazzle_ui.utils.expression_eval` module (#327)
- Reduced MCP handler inner catches from 71 to 38 (#327)

## [0.32.0] - 2026-02-17

### Added
- Dead construct detection lint pass — warns on unreachable surfaces, entities with no surfaces, orphaned views, and undefined service references (#279)
- Source locations on IR nodes — parser attaches file/line/column to all major constructs for source-mapped diagnostics (#280)
- Query pre-planning at startup — projection pushdown from surface section fields, not just view-backed surfaces (#281)
- Template constant folding — pre-compute workspace column metadata at startup instead of per-request (#282)
- Workspace query batching — concurrent aggregate metric queries via asyncio.gather (#283)
- `dazzle build --target` codegen pipeline — SQL DDL, OpenAPI, and AsyncAPI code generation targets with `--check` validation-only mode (#284)

## [0.31.0] - 2026-02-17

## [0.30.0] - 2026-02-17

### Added
- Typed expression language: tokenizer, recursive descent parser, tree-walking evaluator, and type checker for pure-function expressions over entity fields (`src/dazzle/core/expression_lang/`) ([#275](https://github.com/manwithacat/dazzle/issues/275))
- Expression AST types: `Literal`, `FieldRef`, `DurationLiteral`, `BinaryExpr`, `UnaryExpr`, `FuncCall`, `InExpr`, `IfExpr` with full operator precedence ([#275](https://github.com/manwithacat/dazzle/issues/275))
- Field expression defaults: `total: int = subtotal + tax` — computed default values using typed expressions on entity fields ([#275](https://github.com/manwithacat/dazzle/issues/275))
- Cross-entity predicate guards on state transitions with FK arrow path syntax: `guard: self->signatory->aml_status == "completed"` ([#275](https://github.com/manwithacat/dazzle/issues/275))
- Guard message support: `message: "Signatory must pass AML checks"` sub-clause on transition guards ([#275](https://github.com/manwithacat/dazzle/issues/275))
- Block-mode transition parsing: transitions now support indented sub-blocks alongside existing inline syntax ([#275](https://github.com/manwithacat/dazzle/issues/275))
- Process-aware task inbox with step context enrichment showing position in workflows ([#274](https://github.com/manwithacat/dazzle/issues/274))
- Built-in expression functions: `today()`, `now()`, `days_until()`, `days_since()`, `concat()`, `coalesce()`, `abs()`, `min()`, `max()`, `round()`, `len()` ([#275](https://github.com/manwithacat/dazzle/issues/275))
- Invariant expressions consolidated to unified Expr type with `InvariantSpec.invariant_expr` field ([#275](https://github.com/manwithacat/dazzle/issues/275))
- Computed fields consolidated to unified Expr type with `ComputedFieldSpec.computed_expr` field ([#275](https://github.com/manwithacat/dazzle/issues/275))
- Surface field `when:` clause for conditional visibility: `field notes "Notes" when: status == "pending"` ([#275](https://github.com/manwithacat/dazzle/issues/275))
- Duration word-form mapping in expression parser: `14 days` → `14d`, `2 hours` → `2h` ([#275](https://github.com/manwithacat/dazzle/issues/275))
- Declarative integration mappings: `base_url`, `auth`, `mapping` blocks with HTTP requests, lifecycle triggers, response field mapping, and error strategies ([#275](https://github.com/manwithacat/dazzle/issues/275))

## [0.29.0] - 2026-02-17

### Added
- `sensitive` field modifier for PII masking — auto-masks values in list views, excludes from filters, adds `x-sensitive: true` to OpenAPI schemas ([#263](https://github.com/manwithacat/dazzle/issues/263))
- UI Islands (`island` DSL construct) — self-contained client-side interactive components with typed props, events, entity data binding, and auto-generated API endpoints
- `nightly` MCP tool — parallel quality pipeline with dependency-aware fan-out for faster CI runs
- `sentinel` MCP tool — static failure-mode detection across dependency integrity, accessibility, mapping track, and boundary layer
- `story(scope_fidelity)` operation — verifies implementing processes exercise all entities in story scope, integrated into quality pipeline ([#266](https://github.com/manwithacat/dazzle/issues/266))
- htmx SPA-like UX enhancements: View Transitions API, preload extension, response-targets, loading-states, SSE real-time updates, infinite scroll pagination, optimistic UI feedback, skeleton loading placeholders
- htmx fragment targeting for app navigation — `hx-target="#main-content"` replaces full-body swap for smoother transitions ([#265](https://github.com/manwithacat/dazzle/issues/265))

### Fixed
- Test runner cross-run unique collisions — replaced timestamp-based suffixes with UUID4, regenerate unique fields after design-time overrides ([#262](https://github.com/manwithacat/dazzle/issues/262))
- Persona discovery agent stuck in click loop — extract href from CSS selectors, include element attributes in prompt, start at `/app` not public homepage ([#261](https://github.com/manwithacat/dazzle/issues/261))
- `/_site/nav` authenticated routes returning 404 — fixed double-prefixed page routes and singular slug mismatch ([#260](https://github.com/manwithacat/dazzle/issues/260))
- Entity surface links added to workspace sidebar navigation ([#259](https://github.com/manwithacat/dazzle/issues/259))
- Sitespec review false positives for card_grid, pricing, value_highlight sections ([#258](https://github.com/manwithacat/dazzle/issues/258))
- Visual evaluator false positives from preprocessed images and budget exhaustion ([#257](https://github.com/manwithacat/dazzle/issues/257))
- Sentinel suppress writing invalid status that crashes next scan ([#256](https://github.com/manwithacat/dazzle/issues/256))

## [0.28.2] - 2026-02-16

### Changed
- Split god classes: DazzleBackendApp, KnowledgeGraphHandlers, LiteProcessAdapter into focused sub-classes
- Split large modules: discovery.py and KG handlers.py into packages with focused sub-modules
- Extract BaseEventBus from postgres/redis/sqlite event bus implementations
- Handler factory pattern for consolidated MCP handlers reducing boilerplate
- Centralized path constants in paths.py replacing hardcoded strings
- LSP completion refactored into per-context dispatch for maintainability

### Removed
- Dead tools.py (1623 lines) replaced by tools_consolidated.py

### Fixed
- Error handling in queue/stream adapters for JSON decode and subprocess timeouts
- Type safety: concrete DB return types, TypedDict for structured returns
- ARIA accessibility improvements for generated app interfaces

## [0.28.1] - 2026-02-15

### Fixed
- Composition `analyze` returning false 100/100 when LLM evaluation fails — now returns `visual_score: null` with actual error messages ([#239](https://github.com/manwithacat/dazzle/issues/239))
- Sentinel PR-05 false positives on list surfaces with view-based projections — now counts view fields instead of entity fields ([#238](https://github.com/manwithacat/dazzle/issues/238))
- Sentinel PR-01 false positives for N+1 risk on entities with ref fields — ref fields excluded since runtime auto-eager-loads them ([#238](https://github.com/manwithacat/dazzle/issues/238))

## [0.28.0] - 2026-02-15

### Added
- Agent swarm infrastructure with parallel execution and background tasks ([#224](https://github.com/manwithacat/dazzle/issues/224))
- `--base-url` flag for `dsl-run` to test against remote servers ([#226](https://github.com/manwithacat/dazzle/issues/226))
- File-based MCP activity log for Claude Code progress visibility ([#206](https://github.com/manwithacat/dazzle/issues/206))
- Infrastructure manifest for auto-provisioning services from DSL declarations ([#200](https://github.com/manwithacat/dazzle/issues/200))
- Authenticated UX coherence check for post-login experience validation ([#197](https://github.com/manwithacat/dazzle/issues/197))
- Business priority and revenue-criticality signals on DSL constructs ([#196](https://github.com/manwithacat/dazzle/issues/196))
- Persona-scoped navigation audit to detect admin content shown to all users ([#195](https://github.com/manwithacat/dazzle/issues/195))
- Project-level custom CSS override via `static/css/custom.css` ([#187](https://github.com/manwithacat/dazzle/issues/187))
- CSS computed style inspection for agent-driven layout diagnosis ([#186](https://github.com/manwithacat/dazzle/issues/186))
- Layout geometry extraction via Playwright bounding boxes in composition ([#183](https://github.com/manwithacat/dazzle/issues/183))
- Composition analysis MCP tool with dual-layer DOM audit and visual evaluation ([#180](https://github.com/manwithacat/dazzle/issues/180))
- Pulse tool with story wall, readiness radar, and decision queue for founders ([#178](https://github.com/manwithacat/dazzle/issues/178))
- Summary mode for pipeline and fidelity output for LLM-friendly compact results ([#173](https://github.com/manwithacat/dazzle/issues/173))
- Declarative `themespec.yaml` for deterministic design generation ([#167](https://github.com/manwithacat/dazzle/issues/167))
- Batch MCP operations to reduce round-trips for agent loops ([#165](https://github.com/manwithacat/dazzle/issues/165))
- Responsive testing strategy with structural, viewport, and visual tiers ([#153](https://github.com/manwithacat/dazzle/issues/153))
- MCP entrypoint for agent-driven smoke test authoring and execution ([#148](https://github.com/manwithacat/dazzle/issues/148))
- HX-Trigger response headers for server→client event coordination ([#142](https://github.com/manwithacat/dazzle/issues/142))
- Auto-generated curl smoke test suite from DSL specification ([#138](https://github.com/manwithacat/dazzle/issues/138))
- Per-persona authenticated sessions for testing and ACL verification ([#137](https://github.com/manwithacat/dazzle/issues/137))

### Changed
- Expanded LSP hover and go-to-definition to all DSL construct types ([#235](https://github.com/manwithacat/dazzle/issues/235))
- Context-aware completion suggestions in LSP ([#234](https://github.com/manwithacat/dazzle/issues/234))
- Missing construct keywords added to TextMate grammar for syntax highlighting ([#236](https://github.com/manwithacat/dazzle/issues/236))
- Parser diagnostics published to editor for real-time error feedback ([#232](https://github.com/manwithacat/dazzle/issues/232))
- Auto-eager-load ref fields on list surfaces to prevent N+1 queries ([#231](https://github.com/manwithacat/dazzle/issues/231))
- View projections on list surfaces to reduce column fetch ([#230](https://github.com/manwithacat/dazzle/issues/230))
- Per-test progress and result annotations in Workshop for `dsl_test.run_all` ([#227](https://github.com/manwithacat/dazzle/issues/227))
- CLI command activity written to shared store for Workshop visibility ([#225](https://github.com/manwithacat/dazzle/issues/225))
- UK government identifier detection (NINO, UTR) added to compliance scanner ([#221](https://github.com/manwithacat/dazzle/issues/221))
- Discovery agent now uses MCP sampling instead of direct Anthropic API calls ([#220](https://github.com/manwithacat/dazzle/issues/220))
- Progress feedback, token visibility, and streaming added to MCP tools ([#201](https://github.com/manwithacat/dazzle/issues/201))
- Explicit password option in `create-user` and `reset-password` CLI commands ([#199](https://github.com/manwithacat/dazzle/issues/199))
- Production-grade Docker setup with Postgres, Redis, and Celery ([#198](https://github.com/manwithacat/dazzle/issues/198))
- Orphan experience detection for experiences with no workspace entry point ([#194](https://github.com/manwithacat/dazzle/issues/194))
- Composition audit step added to pipeline for visual hierarchy validation ([#192](https://github.com/manwithacat/dazzle/issues/192))
- Pipeline semantics step returns counts and summaries instead of full schemas ([#190](https://github.com/manwithacat/dazzle/issues/190))
- Perfect-score surfaces omitted from fidelity output to reduce pipeline size ([#189](https://github.com/manwithacat/dazzle/issues/189))
- Hero-balance severity escalated when media is declared but not side-by-side ([#188](https://github.com/manwithacat/dazzle/issues/188))
- Sitespec media declarations cross-checked against rendered layout in audit ([#185](https://github.com/manwithacat/dazzle/issues/185))
- Money field widget with major/minor unit conversion in forms ([#172](https://github.com/manwithacat/dazzle/issues/172))
- Runtime standardised on PostgreSQL-only backend; SQLite removed ([#158](https://github.com/manwithacat/dazzle/issues/158))
- Migrated from psycopg2 + asyncpg to unified psycopg v3 driver ([#155](https://github.com/manwithacat/dazzle/issues/155))
- PostgreSQL-first runtime with SQLite-isms eliminated ([#154](https://github.com/manwithacat/dazzle/issues/154))
- Postgres constraint violations return 422 with helpful messages ([#146](https://github.com/manwithacat/dazzle/issues/146))
- htmx upgraded from 2.0.3 to 2.0.8 ([#144](https://github.com/manwithacat/dazzle/issues/144))
- Idiomorph swap for table performance to preserve DOM state ([#143](https://github.com/manwithacat/dazzle/issues/143))
- Alpine.js replaced with lightweight `dz.js` micro-runtime (~3 KB) ([#141](https://github.com/manwithacat/dazzle/issues/141))

### Deprecated
- Dazzle Bar dev toolbar feature removed ([#164](https://github.com/manwithacat/dazzle/issues/164))

### Fixed
- Recursive FK dependency chains in DSL test generator ([#237](https://github.com/manwithacat/dazzle/issues/237))
- Document symbol positions so outline navigation works correctly ([#233](https://github.com/manwithacat/dazzle/issues/233))
- Auth propagation to TestRunner and test generator quality issues ([#229](https://github.com/manwithacat/dazzle/issues/229))
- Authentication before CRUD tests when using `--base-url` ([#228](https://github.com/manwithacat/dazzle/issues/228))
- JSONL file writer connected to SQLite activity store for Workshop visibility ([#223](https://github.com/manwithacat/dazzle/issues/223))
- v0.25.0 constructs silently dropped by pre-v0.25.0 dispatchers ([#222](https://github.com/manwithacat/dazzle/issues/222))
- DSL with reserved keyword conflicts now rejected during MCP validation ([#219](https://github.com/manwithacat/dazzle/issues/219))
- Remaining ForwardRef modules causing `/openapi.json` 500 ([#218](https://github.com/manwithacat/dazzle/issues/218))
- Pydantic ForwardRef errors causing `/openapi.json` 500 ([#217](https://github.com/manwithacat/dazzle/issues/217))
- `asyncio.run()` conflict in `create_sessions` under MCP event loop ([#216](https://github.com/manwithacat/dazzle/issues/216))
- `InFailedSqlTransaction` recovery in publisher loop instead of cascading ([#215](https://github.com/manwithacat/dazzle/issues/215))
- Pluralization in surface converter to match test infrastructure ([#214](https://github.com/manwithacat/dazzle/issues/214))
- `from __future__ import annotations` removed from remaining route modules ([#213](https://github.com/manwithacat/dazzle/issues/213))
- `/openapi.json` returning 500 Internal Server Error ([#211](https://github.com/manwithacat/dazzle/issues/211))
- `asyncio.run()` conflict in `dsl_test` `create_sessions` ([#210](https://github.com/manwithacat/dazzle/issues/210))
- Workspace routes returning 404 despite nav links pointing to them ([#209](https://github.com/manwithacat/dazzle/issues/209))
- Entity route names using proper English pluralization ([#208](https://github.com/manwithacat/dazzle/issues/208))
- `dsl_test` route pattern matching actual runtime API routes ([#207](https://github.com/manwithacat/dazzle/issues/207))
- Partial stories always appear in pipeline coverage regardless of pagination ([#193](https://github.com/manwithacat/dazzle/issues/193))
- False positives in compliance signal detection for non-PII fields ([#191](https://github.com/manwithacat/dazzle/issues/191))
- LLM vision path not executing in `composition(analyze)` ([#184](https://github.com/manwithacat/dazzle/issues/184))
- Sitespec rendering for `split_content` source.path and pricing layout ([#182](https://github.com/manwithacat/dazzle/issues/182))
- Playwright async API in composition capture to fix asyncio conflict ([#181](https://github.com/manwithacat/dazzle/issues/181))
- Hero section media image not rendering despite correct sitespec ([#179](https://github.com/manwithacat/dazzle/issues/179))
- Sitespec rendering for `card_grid`, `split_content`, `trust_bar`, and more ([#177](https://github.com/manwithacat/dazzle/issues/177))
- `role()` conditions evaluated in policy simulate instead of always allowing ([#176](https://github.com/manwithacat/dazzle/issues/176))
- False HIGH severity gaps suppressed for system entities lacking create/edit ([#175](https://github.com/manwithacat/dazzle/issues/175))
- Standalone entity routes recognised in sitespec validator ([#174](https://github.com/manwithacat/dazzle/issues/174))
- Money field expansion accounted for in fidelity checker to prevent false positives ([#171](https://github.com/manwithacat/dazzle/issues/171))
- CSS/HTML class name mismatches breaking site styling ([#166](https://github.com/manwithacat/dazzle/issues/166))
- SQLAlchemy included as base dependency to prevent fresh deploy crashes ([#163](https://github.com/manwithacat/dazzle/issues/163))
- Tables topologically sorted by FK dependencies during PostgreSQL migration ([#162](https://github.com/manwithacat/dazzle/issues/162))
- `DATABASE_URL` honoured in `dazzle migrate` CLI command ([#161](https://github.com/manwithacat/dazzle/issues/161))
- Extra `dazzle` argument removed from subprocess command in `dazzle check` ([#160](https://github.com/manwithacat/dazzle/issues/160))
- Entity list routes 500 from psycopg v3 `dict_row` incompatibility ([#157](https://github.com/manwithacat/dazzle/issues/157))
- PostgresBus table creation crash from `.format()` vs JSONB DEFAULT conflict ([#156](https://github.com/manwithacat/dazzle/issues/156))
- SQL placeholder for FK pre-validation on PostgreSQL ([#152](https://github.com/manwithacat/dazzle/issues/152))
- psycopg2 `IntegrityError` subclasses handled in repository exception check ([#151](https://github.com/manwithacat/dazzle/issues/151))
- DaisyUI drawer hamburger toggle not appearing on tablet viewports ([#150](https://github.com/manwithacat/dazzle/issues/150))
- Project-level static images served after unified server change ([#149](https://github.com/manwithacat/dazzle/issues/149))
- `dz.js` and `dz.css` returning 404 after Alpine.js migration ([#147](https://github.com/manwithacat/dazzle/issues/147))
- Authentication enforced on workspace dashboard routes ([#145](https://github.com/manwithacat/dazzle/issues/145))
- Enum validation error handler crash from non-serializable `ValueError` ([#140](https://github.com/manwithacat/dazzle/issues/140))
- Orphaned column removed after money field expansion to fix NOT NULL violation ([#139](https://github.com/manwithacat/dazzle/issues/139))
- Entity route names using proper English pluralization ([#136](https://github.com/manwithacat/dazzle/issues/136))
- HTML sanitized in string/text fields to prevent stored XSS ([#135](https://github.com/manwithacat/dazzle/issues/135))
- Unique constraint violations return 422 instead of 500 ([#134](https://github.com/manwithacat/dazzle/issues/134))
- Foreign key constraint violations return 422 instead of 500 ([#133](https://github.com/manwithacat/dazzle/issues/133))
- `auto_add` and `auto_update` timestamp fields populated on insert and update ([#132](https://github.com/manwithacat/dazzle/issues/132))
- `money(GBP)` type expanded to `_minor`/`_currency` column pair instead of string ([#131](https://github.com/manwithacat/dazzle/issues/131))
- Enum field values validated against DSL-defined options on CRUD endpoints ([#130](https://github.com/manwithacat/dazzle/issues/130))

## [0.16.0] - 2025-12-16

### Added
- **MkDocs Material Documentation Site** ([manwithacat.github.io/dazzle](https://manwithacat.github.io/dazzle))
  - Complete DSL reference with 10 sections (modules, entities, surfaces, workspaces, services, integrations, messaging, ux, scenarios, experiences)
  - Architecture guides (overview, event semantics, DSL to AppSpec, MCP server)
  - 5 example walkthroughs (simple_task, contact_manager, support_tickets, ops_dashboard, fieldtest_hub)
  - Getting started guides (installation, quickstart, first app)
  - Contributing guides (dev setup, testing, adding features)
  - Auto-generated API reference from source code analysis (315 files)
  - GitHub Pages deployment via GitHub Actions

- **Event-First Architecture** (Issue #25) - Events as invisible substrate
  - EventBus interface (Kafka-shaped) with DevBrokerSQLite (zero-Docker development)
  - Transactional outbox for at-least-once delivery (no dual writes)
  - Idempotent inbox for consumer deduplication
  - DSL extensions: `event_model`, `topic`, `event`, `publish when`, `subscribe`, `project`
  - Replay capability for projection rebuild
  - Developer Observability Pack:
    - CLI commands: `dazzle events status|tail|replay`, `dazzle dlq list|replay|clear`, `dazzle outbox status|drain`
    - Event Explorer API at `/_dnr/events/`
    - AsyncAPI 3.0 generation from AppSpec
  - Email as events: raw stream, normalized stream, outbound events
  - Data products module: field classification, curated topics, policy transforms
  - 12 Stability Rules (Constitution) for event-first systems
  - KafkaBus adapter for production
  - Multi-tenancy strategies and topology drift detection

- **SiteSpec: Public Site Shell** (Issue #24)
  - YAML-based `sitespec.yaml` for public pages (home, about, pricing, terms, privacy)
  - 10 section types: hero, features, feature_grid, cta, faq, testimonials, stats, steps, logo_cloud, pricing
  - Template variable substitution (`{{product_name}}`, `{{year}}`, etc.)
  - Legal page templates (terms.md, privacy.md with full boilerplate)
  - Generated auth pages (login, signup) with working forms
  - Theme presets (`saas-default`, `minimal`)
  - MCP tools: `get_sitespec`, `validate_sitespec`, `scaffold_site`

- **Performance & Reliability Analysis (PRA)**
  - Load generator with configurable event profiles
  - Throughput and latency metrics collection
  - CI integration with stress test scenarios
  - Pre-commit hook for PRA unit tests

- **HLESS (High-Level Event Semantics Specification)**
  - RecordKind enum: INTENT, FACT, OBSERVATION, DERIVATION
  - StreamSpec model with IDL fields
  - HLESSValidator enforcing semantic rules
  - Cross-stream reference validation

- **Playwright E2E Tests**
  - Smoke tests for P0 examples (simple_task, contact_manager)
  - Screenshot tests for fieldtest_hub (16 screenshots)
  - Semantic DOM contract validation

- **Messaging Channels** (Issue #20) - Complete email workflow
  - DSL parser for `message`, `channel`, `asset`, `document`, `template`
  - IR types: MessageSpec, ChannelSpec, SendOperationSpec, ThrottleSpec
  - Outbox pattern: transactional persistence, status tracking, retry logic, dead letter handling
  - Background dispatcher: `ChannelManager.start_processor()` processes outbox every 5s
  - Email adapters: MailpitAdapter (SMTP), FileEmailAdapter (disk fallback)
  - Provider detection framework for email, queue, stream providers
  - Template engine with variable substitution and conditionals
  - Server integration: API routes at `/_dnr/channels/*`
  - MCP tools: `list_channels`, `get_channel_status`, `list_messages`, `get_outbox_status`
  - 95 unit tests

### Changed
- Examples reorganized: removed obsolete examples, added support_tickets and fieldtest_hub
- Consolidated `tools/` into `scripts/` directory
- API reference generator now excludes `__init__.py` files and detects events/invariants

---

## [0.15.0] - 2025-12-15

### Added
- **Interactive CLI Commands**: New user-friendly interactive modes
  - `dazzle init`: Interactive project wizard with guided setup
  - `dazzle doctor`: Environment diagnostics with automatic fixes
  - `dazzle explore`: Interactive DSL explorer with syntax examples
  - `dazzle kb`: Knowledgebase browser for DSL concepts and patterns

### Changed
- CLI version bumped to 0.15.0

---

## [0.14.0] - 2025-12-14

### Added
- **MCP Commands Restored**: Full MCP server functionality in Bun CLI
  - `dazzle mcp`: Run MCP server for Claude Code integration
  - `dazzle mcp-setup`: Register MCP server with Claude Code
  - `dazzle mcp-check`: Check MCP server status
- **Deterministic Port Allocation**: DNR serve now uses deterministic ports based on project path
- **Semantic E2E Attributes**: Added `data-dazzle-*` attributes for E2E testability

---

## [0.9.3] - 2025-12-11

### Added
- **Documentation Overhaul**
  - Complete DSL reference guide in `docs/reference/` (11 files)
  - Comprehensive README with DSL constructs overview
  - Renamed docs/v0.7 to docs/v0.9

---

## [0.8.0] - 2025-12-09

### Added
- **Bun CLI Framework**: Complete CLI rewrite for 50x faster startup
  - Bun-compiled binary (57MB, single file)
  - 20ms startup vs 1000ms+ Python CLI
  - JSON-first output for LLM integration
  - `__agent_hint` fields in errors for AI remediation

### Changed
- **Command Mappings**:
  | Old Command | New Command |
  |-------------|-------------|
  | `dazzle init` | `dazzle new` |
  | `dazzle dnr serve` | `dazzle dev` |
  | `dazzle validate` | `dazzle check` |
  | `dazzle inspect` | `dazzle show` |
  | `dazzle dnr test` | `dazzle test` |
  | `dazzle eject run` | `dazzle eject` |
  | `dazzle dnr migrate` | `dazzle db` |

### Distribution
- GitHub Releases with 4 platform binaries (darwin-arm64, darwin-x64, linux-arm64, linux-x64)
- Homebrew tap updated (`brew install manwithacat/tap/dazzle`)
- VS Code extension v0.8.0 with new command mappings

---

## [0.7.2] - 2025-12-10

### Added
- **Ejection Toolchain**: Generate standalone code from DNR applications
  - Ejection config parser for `dazzle.toml` `[ejection]` section
  - Adapter registry with pluggable generators
  - FastAPI backend adapter (models, schemas, routes, guards, validators, access)
  - React frontend adapter (TypeScript types, Zod schemas, TanStack Query hooks)
  - Testing adapters (Schemathesis contract tests, Pytest unit tests)
  - CI adapters (GitHub Actions, GitLab CI)
  - OpenAPI 3.1 generation from AppSpec
  - Post-ejection verification (no Dazzle imports, no template markers)
  - `.ejection.json` metadata file for audit trail
  - CLI: `eject run`, `eject status`, `eject adapters`, `eject openapi`, `eject verify`
  - 35 unit tests

---

## [0.7.1] - 2025-12-10

### Added
- **LLM Cognition & DSL Generation Enhancement**
  - Intent declarations on entities (`intent: "..."`)
  - Domain and patterns semantic tags (`domain: billing`, `patterns: lifecycle, audit`)
  - Archetypes with extends inheritance (`archetype Timestamped`, `extends: Timestamped`)
  - Example data blocks (`examples: [{...}]`)
  - Invariant messages and codes (`message: "...", code: ERROR_CODE`)
  - Relationship semantics (`has_many`, `has_one`, `embeds`, `belongs_to`)
  - Delete behaviors (`cascade`, `restrict`, `nullify`, `readonly`)
  - Updated MCP semantic index with all v0.7.1 concepts
  - 5 example projects updated

---

## [0.7.0] - 2025-12-10

### Added
- **Business Logic Extraction**: DSL as compression boundary for semantic reasoning
  - State machines for entity lifecycle (`transitions:` block)
  - Computed fields for derived values (`computed` keyword)
  - Invariants for data integrity (`invariant:` rules)
  - Access rules for visibility/permissions
  - All 5 example projects upgraded with v0.7 features
  - 756 tests passing

---

## [0.6.0] - 2025-12-09

### Added
- **GraphQL BFF Layer**: API aggregation and external service facade
  - GraphQLContext: Multi-tenant context with role-based access control
  - SchemaGenerator: Generate Strawberry types from BackendSpec
  - ResolverGenerator: Generate CRUD resolvers with tenant isolation
  - FastAPI Integration: `mount_graphql()`, `create_graphql_app()`
  - CLI: `--graphql` flag for `dazzle dnr serve`
  - `dazzle dnr inspect --schema` command
  - External API Adapters with retry logic and rate limiting
  - Error normalization with unified error model
  - 53 unit tests for adapter interface
  - 7 GraphQL integration tests

---

## [0.5.0] - 2025-12-02

### Added
- **Anti-Turing Extensibility Model**
  - Domain Service DSL: `service` with `kind`, `input`, `output`, `guarantees`, `stub`
  - Service Kinds: domain_logic, validation, integration, workflow
  - ServiceLoader: Runtime discovery of Python stubs
  - Stub Generation: `dazzle stubs generate` command
  - EBNF Grammar: Restricted to aggregate functions only
  - Documentation: `docs/EXTENSIBILITY.md`
  - 31 new tests (14 domain service + 17 service loader)

- **Inline Access Rules**
  - New `access:` block syntax in entity definitions
  - `read:` rule for visibility/view access control
  - `write:` rule for create/update/delete permissions
  - 8 unit tests

- **Component Roles** (UISpec)
  - `ComponentRole` enum: PRESENTATIONAL, CONTAINER
  - Auto-inference based on state and actions
  - 13 unit tests

- **Action Purity** (UISpec)
  - `ActionPurity` enum: PURE, IMPURE
  - Auto-inference based on effects
  - 14 unit tests

### Status
- 601 tests passing

---

## [0.4.0] - 2025-12-02

### Added
- **DNR Production Ready**
  - `dazzle dnr test` command for API contract testing
  - `--benchmark` option for performance testing
  - `--a11y` option for WCAG accessibility testing
  - `dazzle dnr build` for production bundles
  - Multi-stage Dockerfile generation
  - docker-compose.yml for local deployment
  - `dazzle dnr migrate` for database migrations
  - Kubernetes health probes (`/_dnr/live`, `/_dnr/ready`)

---

## [0.3.3] - 2025-12

### Added
- **DNR Developer Experience**
  - DSL file watching with instant reload (`dazzle dnr serve --watch`)
  - Browser dev tools panel with state/action inspection
  - State inspector with real-time updates
  - Action log with state diff visualization
  - `dazzle dnr inspect` command for spec inspection
  - `dazzle dnr inspect --live` for running server inspection
  - `/_dnr/*` debug endpoints (health, stats, entity details)

---

## [0.3.2] - 2025-12

### Added
- **Semantic E2E Testing Framework** (8 phases complete)
  - DOM Contract: `data-dazzle-*` attributes for semantic locators
  - TestSpec IR: FlowSpec, FlowStep, FlowAssertion, FixtureSpec, E2ETestSpec
  - Auto-Generate E2ETestSpec from AppSpec (CRUD, validation, navigation flows)
  - Playwright Harness: semantic locators, flow execution, domain assertions
  - Test Endpoints: `/__test__/seed`, `/__test__/reset`, `/__test__/snapshot`
  - DSL Extensions: `flow` block syntax with parser support
  - CLI: `dazzle test generate`, `dazzle test run`, `dazzle test list`
  - Usability & Accessibility: axe-core integration, WCAG mapping
  - 61 new tests

---

## [0.3.1] - 2025-12

### Fixed
- **Critical Bug Fixes**
  - ES module export block conversion failure in `js_loader.py`
  - HTML script tag malformation in `js_generator.py`

### Added
- **E2E Testing**
  - E2E tests for DNR serve in `tests/e2e/test_dnr_serve.py`
  - Matrix-based E2E testing for example projects in CI
  - P0 examples (simple_task, contact_manager) block PRs on failure

- **MCP Server Improvements**
  - Getting-started workflow guidance
  - Common DSL patterns documentation
  - Semantic index v0.5.0 with extensibility concepts

---

## [0.3.0] - 2025-11

### Added
- **Dazzle Native Runtime (DNR)**: Major pivot to runtime-first approach

  **DNR Backend**:
  - SQLite persistence with auto-migration
  - FastAPI server with auto-generated CRUD endpoints
  - Session-based auth, PBKDF2 password hashing
  - Row-level security, owner/tenant-based access control
  - File uploads: Local and S3 storage, image processing, thumbnails
  - Rich text: Markdown rendering, HTML sanitization
  - Relationships: Foreign keys, nested data fetching
  - Full-text search: SQLite FTS5 integration
  - Real-time: WebSocket support, presence indicators, optimistic updates

  **DNR Frontend**:
  - Signals-based UI: Reactive JavaScript without virtual DOM
  - Combined server: Backend + Frontend with API proxy
  - Hot reload: SSE-based live updates
  - Vite integration: Production builds

  **UI Semantic Layout Engine**:
  - 5 Archetypes: FOCUS_METRIC, SCANNER_TABLE, DUAL_PANE_FLOW, MONITOR_WALL, COMMAND_CENTER
  - Attention signals with priority weights
  - Engine variants: Classic, Dense, Comfortable
  - `dazzle layout-plan` command
  - Persona-aware layout adjustments

### Changed
- Legacy code generation stacks deprecated in favor of DNR

---

## [0.2.0] - 2025-11

### Added
- **UX Semantic Layer**: Fundamental DSL language enhancement
  - Personas: Role-based surface/workspace variants with scope filtering
  - Workspaces: Composed dashboards with multiple data regions
  - Attention Signals: Data-driven alerts (critical, warning, notice, info)
  - Information Needs: `show`, `sort`, `filter`, `search`, `empty` directives
  - Purpose Statements: Semantic intent documentation
  - MCP Enhancements: Semantic concept lookup, example search

---

## [0.1.1] - 2025-11-23

### Fixed
- **express_micro stack**:
  - Graceful fallback for AdminJS on incompatible Node.js versions (v25+)
  - Node.js version constraints to package.json (`>=18.0.0 <25.0.0`)
  - Missing `title` variable in route handlers
  - Admin interface mounting in server.js
  - Error handling with contextual logging

### Added
- Environment variable support with dotenv
- Generated `.env.example` file

---

## [0.1.0] - 2025-11-22

### Added
- **Initial Release**
  - Complete DSL parser (800+ lines)
  - Full Internal Representation (900+ lines, Pydantic models)
  - Module system with dependency resolution
  - 6 code generation stacks (Django, Express, OpenAPI, Docker, Terraform)
  - LLM integration (spec analysis, DSL generation)
  - LSP server with VS Code extension
  - Homebrew distribution
  - MCP server integration

---

## Deprecated Features

The following are deprecated as of v0.3.0 in favor of DNR:

| Stack | Status | Recommendation |
|-------|--------|----------------|
| `django_micro` | Deprecated | Use DNR |
| `django_micro_modular` | Deprecated | Use DNR |
| `django_api` | Deprecated | Use DNR |
| `express_micro` | Deprecated | Use DNR |
| `nextjs_onebox` | Deprecated | Use DNR |
| `nextjs_semantic` | Deprecated | Use DNR |
| `openapi` | Available | For API spec export only |
| `terraform` | Available | For infrastructure |
| `docker` | Available | For DNR deployment |
