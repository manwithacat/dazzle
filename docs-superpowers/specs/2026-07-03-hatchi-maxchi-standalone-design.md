# HaTchi-MaXchi Standalone Design System — Design

**Date:** 2026-07-03
**Status:** Approved direction (James, 2026-07-03); supersedes the "Phase 4
convergence then done" endgame of the taste spec — the oracle and margins
carry over as the permanent quality gate.
**Parent spec:** `docs/superpowers/specs/2026-07-02-taste-house-aesthetic-design.md`
**Evidence at approval:** `dev_docs/taste/review-2026-07-03.md` — fleet
passes 5/6 locked margins one day after an all-FAIL baseline;
`perceived_craft` (gap 0.98 vs margin 0.50) is the binding dimension and
its residue is component breadth + detail, i.e. exactly this scope.

## The idea

HaTchi-MaXchi graduates from "Dazzle's house aesthetic" to a **standalone
design system for htmx4-oriented apps**, published as its own repo.
Dazzle becomes its first consumer.

**Success criteria (James's words): agent-first structures and modern
world-class aesthetics.** Concretely:

1. **Coverage parity with shadcn/ui** (https://ui.shadcn.com) — the same
   breadth of components and features, NOT the same code, mechanism, or
   markup. Where shadcn's answer is client state, HaTchi-MaXchi's answer
   is hypermedia: server-rendered markup + htmx4 wiring + CSS + minimal
   vanilla-JS behavior controllers.
2. **Optimised for htmx4 and the Dazzle htmx4 vernacular** — the request/
   swap lifecycle is a design material (taste principle 9): hx-indicator
   drives loading states, swaps drive transitions, `hx-confirm`-class
   interactions get designed surfaces, boosted navigation feels native.
3. **Agent-first structures**: one semantic root class per component +
   `data-dz-*` modifiers (never utility soup), a documented copy-paste
   markup contract per component, tokens for all variation. The published
   docs ARE the agent's component reference — an agent building any htmx4
   app (Dazzle or not) learns one stable vocabulary.

## Decisions locked (2026-07-03)

| Decision | Choice |
|---|---|
| Prefix | **Keep `dz-*` / `data-dz-*`** — it becomes the brand's published API; zero churn in Dazzle, extraction is a move not a rename |
| Migration | **Develop in-tree, extract when stable** — build the full breadth inside Dazzle (where the oracle, walks, and gates live) in an extraction-ready tree; cut the repo when the contract stops churning |
| Distribution | **CSS bundle + JS controllers** (npm/CDN, themable via tokens) **and copy-paste HTML registry** (per-component documented snippets with htmx4 wiring — the hypermedia analogue of shadcn's registry, doubling as the agent-facing reference). Server-side emitter kits are out of scope; Dazzle's Fragment substrate is the first emitter and stays in Dazzle |

## Familiar, not identical (the counter-pull)

Two objectives pull against each other and BOTH are requirements
(James, 2026-07-03): the maturity and community-understood aesthetic of
shadcn, and a distinct identity — never a clone chasing pixel-identity.
The resolution: **match the quality signals, own the identity signals.**

**Quality signals we match** (these read as "mature" to the community and
are not anyone's property): complete interactive states, spacing on a
strict scale, focus-ring discipline, restrained neutral structure, subtle
layered elevation, dark mode as a designed material, typographic role
clarity.

**Identity signals we own** (deliberate divergence — a screen should be
recognisably HaTchi-MaXchi at a glance):
1. **Chromatic accent.** shadcn's default voice is monochrome zinc with
   black CTAs; ours is a chromatic brand accent (single hue token,
   themable per app). CTAs carry colour.
2. **Colour+icon+text semantics.** Badges/alerts always pair tone with a
   registry glyph and text (WCAG 1.4.1 as an aesthetic, not a retrofit).
3. **Tone washes.** Semantic soft-wash surfaces (the `--colour-*-soft`
   family) as a first-class layer — shadcn has no equivalent vocabulary.
4. **Lifecycle motion.** Loading/settle/swap choreography derives from
   the htmx request lifecycle (skeleton→settle, row swap slides) — a
   signature no client-state system reproduces honestly.
5. **Data density.** Ops-app-first defaults: denser tables, tabular
   numerals everywhere, drill affordances on rows.

**Review test for every component:** (a) would a shadcn-fluent developer
find it immediately credible? (b) would they mistake it for shadcn in a
side-by-side? The target is yes/no. The blind panel enforces (a); (b) is
a checklist item in each component's contract review.

## Separation of concerns

**In HaTchi-MaXchi (the repo, eventually):**
- Design tokens (OKLCH ramps, type scale, spacing/radii/shadows/motion,
  focus ring) + cascade-layer architecture
- Component CSS (the current 17 families, restructured per-component)
- The markup contract: per-component canonical HTML (classes +
  `data-dz-*` attributes + ARIA), with htmx4 wiring examples
- Behavior controllers: small vanilla-JS for the purely-client bits
  (dropdown/popover positioning, dialog focus trap, toast queue, command
  palette keys) — no framework, htmx4-aware where relevant
- Vendored Geist/Geist Mono + the Lucide icon registry + its generator
- The foundations specimen page (productised from `/tmp/gen_specimen.py`)
  and the docs site (component gallery = the registry)
- The taste oracle: rubric + blind-panel harness + reference capture — the
  design system carries its own quality gate

**Stays in Dazzle:**
- The Fragment substrate and all Python emitters (they EMIT the contract)
- DSL→component mapping, RBAC/scope/HTMX runtime, walks and app-level
  gates
- `dazzle qa taste-panel` remains, pointed at the vendored system

**Boundary invariant:** Dazzle's render layer may only produce markup
that validates against the published contract. The existing
`test_fragment_primitive_css` gate ("every emitted class has a rule")
generalises into the cross-repo contract test once extracted.

## Coverage target — the shadcn breadth matrix

Working set (~50 components). Initial classification (Task 1 of the plan
audits this precisely against the catalogue):

- **Have (solid):** button, badge, card, data-table (rich: sort/filter/
  bulk/inline/peek), table, tabs, dialog/modal, drawer/sheet, skeleton,
  toast, sidebar, form + input/textarea/label/select, combobox,
  date-picker, slider, charts (bar/line/pie/area/stacked), empty state,
  kanban, breadcrumb-ish nav, pagination (audit), color picker, rich
  text, tags input, OTP-adjacent (audit)
- **Partial (generalise/systematise):** accordion/collapsible (nav-group
  `<details>` pattern → generic), dropdown-menu (column menu → generic),
  tooltip (range tooltip → generic), progress (audit), avatar (initials
  exist? audit), alert (tone washes exist; component missing), switch/
  checkbox/radio (native-styled; need designed variants), separator,
  typography/prose styles
- **Missing (htmx4-native designs needed):** alert-dialog (designed
  `hx-confirm` replacement — high leverage, every delete uses it),
  command palette (hx-get search — flagship htmx4 showcase), calendar
  (month view), context-menu, hover-card, menubar, navigation-menu
  (marketing), popover (generic), carousel, resizable, scroll-area,
  toggle/toggle-group, input-otp (if absent), sonner-grade toast
  stacking, aspect-ratio (trivial)

Each component ships as: contract doc (canonical HTML + attributes +
states + htmx4 wiring) + CSS + controller (if needed) + catalogue entry +
Dazzle emitter (where the DSL reaches it) + gate coverage.

## Quality gates (all carried forward)

- Blind taste panel with locked margins — `perceived_craft` must clear
  0.50 with the full breadth landed; references list refreshed
  (shadcn_cards target rotted — replace).
- WCAG token-contrast gate; card-safety invariants; icon-registry drift
  gate; UX catalogue currency; walks.
- New: per-component contract examples must render through the real
  pipeline (catalogue generation is the harness).

## Risks

- **Scope**: ~25 net-new/generalised components. Mitigation: tranches
  ordered by fleet leverage (alert-dialog, dropdown-menu, tooltip,
  popover, alert, switch/checkbox/radio first — they appear on every
  screen), each tranche re-judged.
- **Two-repo drift (later)**: extraction only after contract stability;
  vendoring via the existing update-vendors.yml pattern; cross-repo
  contract test at the boundary.
- **Vercel/React idiom leakage** (James's stated anti-pattern): the
  contract review checklist includes "is this the hypermedia answer or a
  transliterated React answer?" — e.g. command palette is an hx-get
  endpoint + designed results list, not a client fuzzy-finder.
- **MDF check**: no new DSL constructs; detectors (panel, catalogue,
  contract gates) are live in the loop, not documented-only.

## Non-goals

- Duplicating shadcn's code, class names, or Radix behavior semantics.
- React/JSX bindings, client-state stores, utility-class layers.
- Renaming `dz-*`.
