# Component Menagerie Roadmap

**Status:** Open (strategic direction doc, not a gap)
**Synthesized:** Cycle 237 (framework_gap_analysis)
**Scope:** Prioritise expansion of Dazzle's canonical HTMX + Alpine component set so DSL authors land on high-quality, consistent affordances without hand-rolling.
**Trigger:** User directive after cycle 236 — *"at a strategic level, we should be aiming to increase the menagerie of available, high-quality components for ux. not necessarily looking for full shadcn/react capabilities, but leveraging htmx and alpine.js to provide canonical solutions to ux requirements"*

---

## Core finding

**The biggest gap is not missing components — it's uncontracted components.** A full inventory pass across `src/dazzle_ui/templates/` reveals ~18 shipped template files that have no matching ux-architect contract in `~/.claude/skills/ux-architect/components/`. The code works; the DSL drives it (in some cases); but without a contract there's no regression gate, no consistent token usage, no discoverability for future DSL authors or for LLM agents trying to propose UX.

Bringing these under governance is higher-leverage than inventing new primitives, because:
- The substrate already exists and works
- A single `missing_contracts` cycle can close 1-3 per pass
- Each new contract immediately gains the fitness-engine walker gate
- Cross-app verification often reveals latent bugs (per cycles 225-229 experience)

Inventing net-new components comes second — but there are a few genuinely missing primitives that warrant it (see §4).

---

## 1. Inventory — what exists today

### 1a. Templated + Contracted + Verified (46 rows)

UX-001..040 in `ux-backlog.md`, mostly PASS. The solid base layer: tables, forms, modals, workspaces, the widget-* family, detail views, navigation chrome. Covered at arc-end cycle 235; no action needed.

### 1b. Contracted but silently unverified (2 rows)

Both surfaced from the contract directory but not yet in the backlog as PASS rows:

| Contract | Template | State | Action |
|---|---|---|---|
| `activity-feed.md` | `workspace/regions/activity_feed.html` + `regions/timeline.html` | Template in use by fieldtest_hub (`display: timeline`) but no PASS row; contract exists | Verification cycle: hit fieldtest_hub timeline region, confirm contract walker passes, add UX-041 row |
| `inline-edit.md` | `fragments/inline_edit.html` | Contract references data-table `inline_editable` columns; no PASS row | Verification cycle + cross-app probe (which apps declare inline_editable columns?) |

### 1c. Templated, uncontracted, governed by DSL (~10 region types)

These are `workspace/regions/*.html` files. The DSL parser accepts them (via `display:` or region block shape), the compiler renders them, but **no ux-architect contract exists**. This is the single richest vein.

| Template | DSL surface | Example app usage | Contract gap |
|---|---|---|---|
| **metrics.html** | `metrics:` block with `source` + `aggregate` | simple_task (2), fieldtest_hub (1), support_tickets (1) | **Highest priority.** Used in every dashboard. Renders KPI tiles + optional drill-down table. Anchor for stat-card semantics. |
| **timeline.html** | `display: timeline` region | fieldtest_hub (1) | Need contract; overlap with `activity-feed.md` (which is regions/activity_feed.html). Likely merge. |
| **kanban.html** | `display: kanban` region | simple_task (1) | Overlaps with `kanban-board.md` UX-040; confirm whether they're the same or distinct. |
| **grid.html** | `display: grid` region | fieldtest_hub (1) | Uncontracted. Used in 1 app. |
| **tree.html** | `display: tree` region | **0 apps** | Speculative; no consumers. Parked until a real app needs it. |
| **bar_chart.html** | (region type) | **0 apps** | Speculative. Parked. |
| **funnel_chart.html** | (region type) | **0 apps** | Speculative. Parked. |
| **heatmap.html** | (region type) | **0 apps** | Speculative. Parked. |
| **progress.html** | (region type) | **0 apps** | Speculative. Parked. |
| **tab_data.html** | (region type) | internal to workspace-tabbed-region | May already be covered by UX-039 workspace-tabbed-region. |

### 1d. Templated, uncontracted, used implicitly everywhere (~8 fragment types)

These are `templates/fragments/*.html` that render on many surfaces but have no contract:

| Template | Where it renders | DSL surface | Contract gap |
|---|---|---|---|
| **status_badge.html** | Every status column in every data table | Auto-derived from enum + state machine fields | **Highest leverage.** Every enum/state field currently has ad-hoc chip rendering. A contract that formalises "one enum = one canonical badge" would unify visual language across all apps. |
| **empty_state.html** | Every empty list/region | DSL `empty:` copy + compiler-derived `create_url` | Already partially documented via EX-046 gap. Contract would formalise the shape AND unblock the per-persona empty-copy extension. |
| **breadcrumbs.html** | Every nested surface | Currently derived from route depth | No contract, no DSL-level control over labels. |
| **tooltip_rich.html** | Ad hoc across several surfaces | No DSL surface — hand-authored in templates | Missing from the contract list entirely. Pair with an ARIA compliance pass. |
| **toggle_group.html** | Filter bars, view switchers (e.g. list/kanban toggle on simple_task) | No DSL surface | This is the **segmented control** primitive. Highly reusable. |
| **accordion.html** | Long-form detail sections, FAQ-like content | No DSL surface | No consumer currently; worth contracting on first real need. |
| **context_menu.html** | Right-click affordances on data-table rows | No DSL surface | Contract would standardise per-row action menus. |
| **skeleton_patterns.html** | In-flight HTMX requests | Implicit via `htmx-indicator` | Worth formalising as the canonical loading-state primitive. |
| **form_stepper.html** | Multi-step forms | Overlaps with form-wizard | Contract to disambiguate: form-wizard = multi-surface flow, form-stepper = single-surface multi-section. |
| **steps_indicator.html** | Same family as form_stepper | Same | Likely collapse into one contract. |
| **alert_banner.html** | Error/warning banners | No DSL surface | Used ad hoc; worth a contract so we can standardise severity → tokens. |
| **date_range_picker.html** | Filter bars with date range columns | `date_range` filter type (I think) | Pair with widget-datepicker.md UX-010. |

### 1e. Contracted but no template (0 rows)

None found. Every contracted component has a shipping template.

### 1f. Absent entirely — genuine menagerie gaps

Components that are neither contracted nor templated. Worth inventing:

| Primitive | Leverage | DSL anchor | Notes |
|---|---|---|---|
| **stat-card** (distinct from metrics region) | Medium | Would need a new DSL construct — e.g. `field metric(...)` on a view | metrics.html covers the "grid of KPIs"; a standalone stat-card for inline use on any surface is still missing |
| **avatar / avatar-group** | High for multi-user apps | Would need EX-045 persona-entity binding first | Parked until the persona→entity question is resolved |
| **badge** (distinct from status_badge) | Medium | Generic counting badge (e.g. "Unread (3)" on nav) | Small addition |
| **chat message list** | Low-urgent, high-future | Would need LLM conversation construct | AI-era primitive, not needed yet |
| **streaming response** | Low-urgent, high-future | LLM response surface | AI-era primitive |
| **progress bar** (inline) | Medium | Already have workspace/regions/progress.html but nothing for inline use | Small addition |
| **segmented control** (distinct from toggle_group) | Low | UI-only convenience | Probably covered by toggle_group contract when written |
| **divider / section header** | Low | Already exists ad hoc in many templates | Housekeeping, not a real gap |
| **markdown preview / diff viewer / code block** | Low | Needed for devtools/admin surfaces | Out of scope for this arc |
| **keyboard shortcut overlay** | Low | Pair with command-palette UX-011 | Nice-to-have |

---

## 2. Prioritisation criteria

Every component proposal is scored on four axes:

1. **Blast radius** — how many example apps and personas would it show up on?
2. **DSL leverage** — does an existing DSL construct want this? (Existing constructs are better anchors than new ones, because the fix is "wire up what's already there" not "evolve the grammar".)
3. **Substrate readiness** — does a working template already exist, or does this require new code?
4. **Governance gap** — would a contract catch drift that's currently un-caught?

The ideal target scores high on all four: already shipped but ungoverned, DSL-addressable, on every app.

---

## 3. Top 5 for the next mini-arc (cycles 238-242)

Ranked by combined score. Each cycle is one contract + cross-app verify + fitness gate.

### 3.1 — `status-badge` (cycle 238 target)

- **Blast radius:** 5/5 apps. Every enum field, every state machine field, every status column on every table.
- **DSL leverage:** Very high. Auto-derivable from `enum[a,b,c]` and state machine fields without any new DSL.
- **Substrate:** `fragments/status_badge.html` exists. Needs audit for consistent colour-token-to-state mapping.
- **Governance gap:** Huge. Currently each app's status rendering drifts (colours, shapes, sizes). A contract formalises the "enum → badge" pipeline and the token palette.
- **Scope:** Contract + template audit + add `widget: badge` option for enum fields + cross-app probe of every status column. Expected 1 cycle.

### 3.2 — `metrics` region / stat-card (cycle 239 target)

- **Blast radius:** 3/5 apps currently; will be 5/5 once other dashboards adopt `metrics:` blocks.
- **DSL leverage:** Very high. `workspace → metrics:` block already in the DSL grammar with `source` + `aggregate` semantics. Compiler already populates the template.
- **Substrate:** `workspace/regions/metrics.html` is a UX-035 region-wrapper adopter with tiles + drill-down table. Works.
- **Governance gap:** Large. No contract; tile sizing, attention-level colour mapping, and drill-down interaction are ungoverned. First contract pass will likely surface small improvements.
- **Scope:** Contract + verify each of the 4 existing metrics blocks in example apps renders cleanly per-persona + confirm `_attention` colour semantics match the design tokens. Expected 1 cycle.

### 3.3 — `empty-state` (cycle 240 target)

- **Blast radius:** 5/5 apps. Every list surface, every region, every drawer.
- **DSL leverage:** Medium-high. `empty:` copy already DSL-declared. Overlaps with EX-046 (per-persona empty copy gap).
- **Substrate:** `fragments/empty_state.html` exists. Cycle 234 verified the framework withholds the Create-first CTA correctly via `create_url` gate.
- **Governance gap:** Medium. Contracting it would formalise the CTA gating, icon/copy contract, and unblock the EX-046 per-persona override cleanly — "add `empty:` to `for <persona>:` blocks" becomes a grammar extension on a governed component rather than an ungoverned hack.
- **Scope:** Contract + EX-046 DSL grammar extension + cross-app verify. **Bundles a framework fix and a contract in one cycle.** Expected 1.5 cycles.

### 3.4 — `tooltip` (cycle 241 target)

- **Blast radius:** 5/5 apps will want this. Currently missing from the menagerie entirely at the contract level.
- **DSL leverage:** Low (UI-only, no DSL construct). But: ARIA compliance + keyboard accessibility is load-bearing for any professional admin UX.
- **Substrate:** `fragments/tooltip_rich.html` exists but is under-adopted. Needs audit for modern ARIA (`aria-describedby`, `role="tooltip"`, hover + focus triggers).
- **Governance gap:** Large. Nothing currently guarantees tooltip consistency.
- **Scope:** Contract + template refresh + seed adoption on a few common surfaces (icon buttons, truncated cell values, form hints). Expected 1 cycle.

### 3.5 — `toggle-group` / segmented control (cycle 242 target)

- **Blast radius:** 2/5 apps currently; more when DSL adds a standardised "view switcher" pattern.
- **DSL leverage:** Medium. simple_task already has a hidden "list/kanban toggle" on its task surface. A DSL anchor like `display: [list, kanban]` would turn that into a declarative view switcher.
- **Substrate:** `fragments/toggle_group.html` exists.
- **Governance gap:** Medium. Used ad hoc; contracting it formalises the list/grid/kanban switching pattern across all surfaces.
- **Scope:** Contract + optional DSL `display: [...]` grammar extension + simple_task adoption. Expected 1 cycle.

**Total mini-arc estimate:** 5 cycles (238-242), closing roughly 5 contract gaps, 1 DSL grammar extension (EX-046), 1 optional DSL grammar extension (multi-display), and 1 unblock (EX-046 persona-empty-copy). After this mini-arc the menagerie's "base layer" should be meaningfully more complete.

---

## 4. Parking lot (lower priority, but tracked)

These are real gaps but don't belong in the first mini-arc. Listed in rough priority order so a future cycle can pull from the top:

1. **`breadcrumbs`** — contract + DSL anchor for per-surface crumb labels. Bundle with navigation-chrome audit.
2. **`activity-feed` / timeline contract verification** — contract exists, template exists, fieldtest_hub uses it; needs a formal PASS row.
3. **`inline-edit` contract verification** — same situation as activity-feed.
4. **`form-stepper` / `steps-indicator` merged contract** — disambiguate from form-wizard.
5. **`alert-banner`** — small, worth doing.
6. **`accordion`** — contract on first real consumer (no example app currently needs it).
7. **`context-menu`** — contract when the first data-table wants row-level action menus beyond bulk-action-bar.
8. **`skeleton-patterns`** — canonical loading-state primitive.
9. **`date-range-picker`** — pair with widget-datepicker extension.
10. **`avatar` + `avatar-group`** — blocked on EX-045 persona-entity binding.
11. **`progress-bar` (inline)** — small addition once any app needs it.
12. **`stat-card` (inline, not in a metrics region)** — wait for a real consumer.
13. **Speculative region types** (bar_chart, funnel_chart, heatmap, tree, progress region) — audit-and-park; contract only when a real app consumes them.
14. **AI-era primitives** (chat bubble, streaming response, tool call accordion) — forward-looking, not needed for current apps.

---

## 5. Meta-observations

### 5.1 — "Contract audit" is a distinct cycle shape

Cycles 225-229 established `finding_investigation` and `framework_gap_analysis` as named strategies. The pattern emerging from this roadmap — "pick an ungoverned template, write a contract for it, cross-verify, add the PASS row" — is sufficiently common that it deserves a name. Proposal: **`contract_audit`** as a fourth strategy alongside `missing_contracts` / `edge_cases` / `framework_gap_analysis` / `finding_investigation`. The existing `missing_contracts` strategy is close but slightly different — it looks for recurring patterns that *should* have a contract, whereas `contract_audit` picks a specific *known-templated-but-ungoverned* component and formalises it. I'll promote this to a skill update after cycle 238 (or whenever the first of the mini-arc lands) has demonstrated the shape.

### 5.2 — DSL anchors are the multiplier

The three highest-scoring components in §3 (status-badge, metrics, empty-state) all share one property: **they already have a DSL anchor.** Enum/state-machine fields, `metrics:` blocks, `empty:` copy. Contracting these gives every DSL author in every future app the component for free.

The low-scoring ones (tooltip, accordion, breadcrumbs, skeleton) are UI primitives without DSL anchors. They're still worth doing, but the ROI per cycle is lower — we're adding paint, not unlocking new declarative surface.

### 5.3 — Avoid inventing while audit is incomplete

The natural instinct after cycle 236 is to start inventing avatars and chat bubbles. That's a trap: we'd be building ungoverned new components while our existing shipped templates still lack governance. **Finish the audit first**, then invent. The §3 mini-arc is a disciplined closure pass; §4 is the parking lot; §1f (true gaps) comes last.

### 5.4 — The cycle 236 ref-entity select is the template

Cycle 236's ref-select fix is the exact shape a component expansion cycle should take: (1) raw-layer reproduction confirms the defect; (2) existing machinery (resolve_widget, the widget map) already wants this; (3) small compiler + template change unlocks cross-app consistency; (4) the DSL author writes nothing and gets the new behaviour for free. Every cycle in the §3 mini-arc should aim for this shape.

---

## 6. Recommended next step

Proceed with **cycle 238 — `contract_audit` on status-badge**. Highest blast radius, clearest DSL anchor, substrate already shipped. First fast win of the new arc.

If the user signals a different priority, swap it in. The roadmap is durable — it persists across cycles and will be refreshed every 5-10 cycles via `framework_gap_analysis`.
