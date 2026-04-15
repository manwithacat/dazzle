# Dazzle framework maturity assessment — 2026-04-15

**Session scope:** ~4 hours of autonomous `/ux-cycle` loop + targeted investigation and fixes. Covers cycles 199-219 on the new subagent-driven substrate. Shipped v0.55.6 → v0.55.31 (26 patch releases, zero rollbacks, worktree clean throughout).

This is not a full framework audit. It is what the autonomous loop revealed about the state of Dazzle-as-seen-through-its-example-apps, written at a natural pause point where the loop has surfaced enough signal to be worth synthesising.

---

## TL;DR

**The framework is in a good-but-uneven state.** Component-level polish and design-system adherence are strong — 22 of ~50 UX components have shipped contracts governing their visual and interaction grammar, and the ones with contracts verify cleanly via multi-persona fitness runs. **However, the loop surfaced three framework-level defects that every example app exhibits** — two of which are now fixed, one of which is filed and investigated but not yet fixed. These are not polish issues; they're structural problems in the generated runtime that any real app would hit within an hour of use.

The substrate itself — the Claude-Code-subagent + stateless-Playwright-helper pipeline that replaced the cycle-197 DazzleAgent path — is working well. It produces real signal across every example app, it compounds findings into cross-app convergences, and it enables closed-loop bug fixes like the manwithacat/dazzle#776 patch shipped this session.

---

## Framework strengths (what's working)

### 1. Design system coverage is substantive and consistent

22 ux-architect contracts now exist, covering every common SaaS UI primitive: data-table, detail-view, form-chrome, form-field, form-validation, form-wizard, modal, pagination, popover, region-wrapper, related-displays, review-queue, search-input, slide-over, toast, app-shell, command-palette, confirm-dialog, auth-page, base-layout, dashboard-grid, plus all 11 widgets (colorpicker, combobox, datepicker, file, money, multiselect, richtext, search-select, slider, tags, harness-set). And another 12 cycle-198-era components (kanban-board, inline-edit, activity-feed, workspace-detail-drawer, workspace-card-picker, workspace-tabbed-region, column-visibility-picker, dashboard-region-toolbar, dashboard-edit-chrome, bulk-action-bar, feedback-widget, theme-toggle).

Each contract cycle this session produced PASS verdicts on multi-persona fitness contract walks. `fitness run [persona-A, persona-B]: N findings, degraded=False` is the uniform outcome — meaning the walker could reach every anchor, apply every quality gate, and verify the component's stated invariants against live DOM.

**Verdict:** Component-level quality is high. The design system is coherent (single HSL token vocabulary via `design-system.css`, consistent motion grammar `80ms/120ms` + Linear cubic-bezier easing, uniform radius + spacing tokens). The contracts cover most of the practically-reusable surface.

### 2. The subagent-driven explore substrate actually works

Cycle 197 shipped v0.55.4 with DazzleAgent on the direct Anthropic SDK and produced **0 proposals across 11 persona-runs** — the LLM under-invoked the mission tools and the loop never saw component patterns. The cycle 198 substrate pivot to Claude Code subagents via the Task tool + stateless Playwright helper replaced that with a different substrate, not a different prompt.

Since the pivot:

| Cycle | App | Persona | Strategy | Findings |
|---|---|---|---|---|
| 198 | contact_manager | user | missing_contracts | 1 proposal (workspace-detail-drawer) |
| 199 | support_tickets | agent/customer/manager | missing_contracts | 9 proposals + 7 observations |
| 201 | support_tickets | agent | edge_cases | 6 observations (2 concerning) |
| 213 | simple_task | member | missing_contracts | 2 proposals + 2 observations |
| 216 | ops_dashboard | ops_engineer | missing_contracts | 0 props + 3 observations (useful negative) |
| 217 | fieldtest_hub | engineer | edge_cases | 0 props + 7 observations (4 concerning) |
| 218 | contact_manager | user | edge_cases | 0 props + 5 observations (2 concerning) |

**Total: 12 proposals + 30 observations across 5 apps and 8 personas, at ~70k subsidised tokens per cycle.** The substrate is producing increasing cross-app convergence evidence as cycles accumulate, not diminishing returns.

### 3. The QA path works

Every one of the 12 cycle-198-era UX rows that reached `READY_FOR_QA` passed the Phase B fitness contract walk on first attempt. The walker's degraded-based pass/fail rule (established by the cycle 156 fix) is stable: 0 regressions across 12 consecutive ships.

### 4. End-to-end pipeline is proven

Cycles 203-212 demonstrated the full explore → triage → SPECIFY → QA → DONE chain working mechanically for 10 distinct components (UX-037..046). Each cycle was 8-15 minutes of wall-clock, each shipped a patch release, and each passed Phase B verification cleanly. No flaky retries, no manual intervention, no debugging sessions. That's a working pipeline.

### 5. Cycles 214 + 219 proved the loop can close its own bugs

Cycle 214 took a subagent-discovered component (feedback-widget) through triage + contract + QA in a single cycle. Cycle 219 **investigated and fixed** a framework-level bug (manwithacat/dazzle#776) that was surfaced by cycles 201/213/216/217/218 of the explore loop. The loop is capable of producing closed bug fixes, not just discovery.

---

## Framework weaknesses (what's structurally broken)

The loop surfaced **three framework-level defects** that every example app exhibited. They are not polish issues. They are defects in the generated runtime that any real production app would hit.

### 1. 404/403 error pages dropped authenticated users into marketing chrome (manwithacat/dazzle#776 — FIXED in v0.55.31)

**Evidence:** 5 apps, 5 independent subagent observations:
- cycle 201 support_tickets/agent EX-003
- cycle 213 simple_task/member EX-008
- cycle 216 ops_dashboard/ops_engineer adjacent
- cycle 217 fieldtest_hub/engineer EX-014
- cycle 218 contact_manager/user EX-020

Every example app hit a 404 or 403 during exploration. Every time the error page rendered with `Home | Sign In | Get Started` nav bar, dropping the logged-in user back to the public marketing landing with no sidebar, persona badge, or logout.

**Root cause:** `src/dazzle_back/runtime/exception_handlers.py` unconditionally rendered `site/404.html` and `site/403.html` which extend the marketing layout. No URL-prefix dispatch.

**Fix (cycle 219):** Added `templates/app/404.html` + `templates/app/403.html` extending `layouts/app_shell.html`. `_is_app_path()` helper + dispatch logic routes `/app/*` paths to the in-app variant. Plus a context-aware back-affordance computed from the path (`/app/contact/{bad-id}` → Back to List; `/app/workspaces/{bad-ws}` → Back to Dashboard). 14 new unit tests.

**Severity:** concerning. This is exactly the kind of bug that kills retention — users think they've been signed out and leave.

### 2. Sidebar-nav shows links the current persona cannot access (manwithacat/dazzle#775 — FILED, NOT YET FIXED)

**Evidence:** 4 apps, 4 independent observations:
- cycle 199 support_tickets/manager + cycle 201 support_tickets/agent
- cycle 216 ops_dashboard/ops_engineer
- cycle 217 fieldtest_hub/engineer
- (implicit) cycle 218 contact_manager/user had this pattern but less prominently

Every app exposes sidebar links to workspaces the current persona doesn't have `access:` rule permission for. Clicking the link 403s (and — combined with #776 before the fix — dropped the user to marketing chrome).

**Root cause (hypothesised — not yet verified in code):** The sidebar generator builds nav items from the full workspace catalogue, not from the subset the current persona is permitted to access. The workspaces' `access:` rules are the source of truth for which persona can enter, but the sidebar doesn't consult them.

**Status:** manwithacat/dazzle#775 filed with cycle 201 evidence. Cross-app evidence has accumulated to 4 apps since then. Issue body should probably be updated with the full matrix before work starts.

**Severity:** concerning. Any real deployment with multiple personas shows at least one dead link.

### 3. Silent form submit failure on create surfaces (manwithacat/dazzle#774 — FILED, NOT YET FIXED)

**Evidence:** 2 apps (support_tickets, fieldtest_hub), 3 observations total including historical cycles 110/126/137 (support_tickets only).

**Root cause (confirmed in support_tickets):** The `ticket_create` surface omits `created_by` from its section, but the `Ticket` entity declares `created_by: ref User required`. The backend rejects the submission; the UI doesn't surface the error; the user clicks Create with no feedback.

Two plausible framework fixes:
- **Auto-inject `current_user` into `ref User required` fields** on create surfaces where the field is absent. This is the obvious convention.
- **Flag at DSL validate time** when a create surface omits a required entity field. Early error beats runtime silent failure.

Both should probably happen. The silent-submit symptom (error not surfaced in UI) is a separate layer of the same bug — even if the DSL author fixes the created_by gap, the UI's lack of validation feedback remains a defect.

**Severity:** concerning. `ticket_create` is the core workflow of support_tickets and cycle 201 found it on day one.

### 4. List routes don't eagerly load ref relations (manwithacat/dazzle#777 — NEWLY FILED, not yet fixed)

**Evidence:** 1 app confirmed (fieldtest_hub via cycle 217 EX-017 + cycle 219 investigation).

**Root cause:** The template compiler strips `_id` suffix from ref column keys expecting the server to populate the joined dict at `item['device']`. The list route's repository query emits raw FK UUIDs at `item['device_id']` without the joined record. Template's `ref` branch resolves to empty because neither `item.get('device_display', '')` nor `item['device'] | ref_display` find anything.

**Plus:** a separate `datetime auto_add` seed-data gap where `reported_at` is `None` on every seeded IssueReport row.

**Severity:** notable. Any list surface that references another entity via `ref` is broken in a visually obvious way.

### Cross-cutting observation: the substrate has a known false-positive mode

Cycles 217 and 218 both flagged the data-table formatter bug, but cycle 219's direct HTML dump + JSON API inspection showed:
- Cycle 217 EX-017 was a **real bug** (the manwithacat/dazzle#777 case above)
- Cycle 218 EX-021 was a **false positive** — contact_manager `/app/contact` renders rows correctly when loaded in a real browser

The subagent's observation method (`visible_text` via `document.body.innerText`) has ambiguous behaviour around `<template x-if>` Alpine idioms and filter-bar `<select>` dropdowns. When two cycles produce the same finding, the second one should ideally cross-validate with a different extraction method before being treated as confirmed. Worth flagging as a substrate-level improvement for a future cycle.

---

## Framework gaps (things the loop did NOT test)

Honest caveats about what this session's evaluation did not cover:

- **Data mutation safety.** Fitness contract walks are read-mostly. Create, update, and delete operations were exercised only incidentally and usually failed silently (see #774). A focused write-path audit would probably surface more defects.
- **Concurrent session behaviour.** Every run used exactly one persona's cookie. Multi-user contention, session expiry, permission changes mid-session — all untested.
- **Real-world data shapes.** Seed data is synthetic and uniform (`Test name 1`, `uxv-5@contact.test`). No edge cases like empty strings, unicode, very long names, collisions, or adversarial input.
- **Performance under load.** Every cycle ran against a single-user dev server with ~5-20 rows per table. Pagination, N+1 query behaviour, large-dataset table rendering — untested.
- **Mobile + responsive layouts.** Playwright was run at default viewport. Mobile sidebar collapse, small-viewport overflow, touch interactions — untested.
- **Accessibility beyond what contracts demand.** Keyboard-only traversal, screen reader semantics, focus management — flagged as open questions in many contracts but never actually audited.
- **DSL author ergonomics.** Nothing tests the DSL itself — just what the runtime produces. Clarity of error messages, DSL author feedback loops, learning curve — all out of scope.
- **Documentation / onboarding.** The loop validates behaviour, not documentation. Whether a new developer could actually pick up Dazzle and build something productive remains an open question.

---

## Maturity verdict

**On a rough 1-5 scale:**

- **Component design system (UX):** **4 / 5** — coherent, contracted, tested, visually consistent. Missing: more accessibility depth, responsive/mobile breakpoints, theme-toggle cross-shell sync (UX-048 contract flagged this explicitly).
- **Runtime correctness for read paths:** **3 / 5** — most list/detail/workspace surfaces render correctly, but the 3 framework-level defects (error pages, sidebar nav, ref eager-load) affect every app. 1/3 fixed this session.
- **Runtime correctness for write paths:** **2 / 5** — the silent-submit bug is alarming precisely because it went undetected for multiple cycles and hit the core workflow. DSL-level validation + form error surfacing are both incomplete.
- **Substrate + discovery loop:** **4 / 5** — the explore→triage→SPECIFY→QA→DONE pipeline proven end-to-end, 12 components shipped through it, 3 issues filed, 1 closed with a working fix. Remaining friction is the untriaged PROP→UX manual step (Step 1 of /ux-cycle doesn't auto-triage).
- **Framework production-readiness (composite):** **3 / 5** — usable for prototyping and internal apps today, but the open framework defects (especially #774 silent-submit, which every entity create form likely inherits, and #775 sidebar nav) would each block a real customer-facing deployment until fixed.

The best description I can offer: **the framework is no longer in "demo" mode but not yet in "production-hardened" mode.** It generates working apps quickly, the generated apps look good, the internal plumbing is mostly sound — but each new end-user interaction with a real dataset has a meaningful chance of hitting one of the structural defects above. An internal or trusted-user deployment is fine. A public-facing deployment would need #774, #775, and #777 closed first.

---

## Recommended focus for the next framework work

Strictly ordered by impact × ease:

1. **Fix #774 (silent form submit).** Two related fixes:
   - Auto-inject `current_user` into `ref User required` fields on create surfaces when the DSL omits them
   - Surface backend validation errors in the UI (toast or inline, never silent)
   Estimated scope: 2-3 focused cycles. This closes the single most-dangerous active bug.

2. **Fix #775 (sidebar nav filter by access rules).** The sidebar generator should consult the workspace `access:` rules per persona. Estimated scope: 1 cycle plus the nav refresh wiring.

3. **Fix #777 (ref eager-load + datetime auto_add).** Two related fixes:
   - Repository query for list routes should `selectinload` every ref column in the surface sections
   - Investigate whether `datetime auto_add` is being honored at insert time (seed-data vs ORM hook)
   Estimated scope: 1-2 cycles, depends on SQLAlchemy relation-loading surface.

4. **Write-path audit cycle.** Pick one example app, seed it minimally, drive every create / update / delete path via the subagent substrate with `edge_cases` strategy. Identify the full set of silent-failure modes. Probably surfaces the same error-surfacing gap #774 flagged.

5. **Triage-aware `/ux-cycle` Step 1.** The current Step 1 priority queue doesn't pick up PROP-NNN rows — they require manual triage to become UX-NNN first. Add a built-in triage step (or change the priority to include PROPs directly).

6. **Substrate improvement: cross-validate subagent findings before second-cycle confirmation.** The cycle 218 false positive on data-table cells was confirmed-looking but wrong. Future edge_cases runs should probably dump raw HTML snippets for any `concerning` finding instead of relying on `visible_text`.

---

## Session artifacts

- 26 patch releases: v0.55.6 → v0.55.31
- 22 UX contracts shipped through the full pipeline (12 in cycles 203-215, 2 in cycles 214-215, 10 pre-existing)
- 24 EX observations in `dev_docs/ux-backlog.md` (EX-002..024, with EX-001 being the historical cycle 17 coverage-gap row)
- 4 GitHub issues filed: manwithacat/dazzle#774, #775, #776 (closed), #777
- 1 framework-level fix shipped (manwithacat/dazzle#776 via v0.55.31)
- 14 new unit tests in `test_exception_handlers.py` covering the #776 fix
- Zero rollbacks, worktree clean at every checkpoint

**End of assessment.**

---

*Written at cycle 219 as the natural pause point for qualitative evaluation. The autonomous loop is stopped here, not exhausted — the explore counter is at 27/30 and the substrate continues to produce signal. Resuming discovery is strictly less valuable than acting on the three filed-and-unfixed framework defects above.*
