# Thesis: HM as the shadcn of htmx — validated, with two amendments

**Date:** 2026-07-03
**Status:** Analysis for James's decision; Phase 5 (structure conformance)
approved and is the prerequisite machinery.
**Parents:** `2026-07-03-hatchi-maxchi-standalone-design.md`,
`2026-07-03-hm-boundary-and-wcag-gate-design.md`

## The thesis (James)

Standardise "components" — htmx-inscribed HTML partials (markup + classes
+ JS) — the way shadcn/Radix standardises React components, then walk
ui.shadcn.com's catalogue and produce HTMX4 equivalents that server-side
rendering emits. Result: HTMX4 becomes usable by Dazzle the way React is,
but optimised for agent coders.

## Where the analogy is sound

1. **shadcn's innovation is distribution + vocabulary, not React.** Its
   durable ideas: you *own* the code (copy-paste, no dependency); every
   component has a named anatomy (Dialog = Trigger/Content/Header/Title/
   Footer); one theming contract (CSS variables); docs where the demo IS
   the code. None of that is React-specific, and HM already replicates
   each: gallery snippets == demos, OKLCH token contract, MIT copy-paste
   distribution. The thesis is a systematic breadth-and-anatomy pass over
   an architecture we already validated, not a new bet.

2. **Agent optimisation is real — and stronger server-side.** Agents do
   best with deterministic canonical forms, greppable contracts, no
   build step, and locally-verifiable output. An HTML partial with
   semantic classes is more tractable than JSX + hooks + context: there
   is no runtime state graph to simulate. Crucially, an agent's emitted
   HTML can be *linted against a shape spec* cheaply; a React tree
   can't be checked without executing it. The conformance machinery
   (Phase 5) is what turns "agent-friendly" from a vibe into a gate.

3. **The web platform ate much of Radix.** Radix exists largely to
   reimplement primitives browsers lacked in 2020: today `<dialog>`,
   `<details>`, the Popover API, CSS anchor positioning, `:has()`, and
   mature ARIA patterns cover a large share. HM's existing choices
   (menus = details, confirm = dialog, tooltips = CSS) are this exact
   strategy, and the WCAG/behaviour gates prove the primitives hold.

## Where it breaks — and the amendments that fix it

**Amendment 1: components are partial + PROTOCOL pairs, not partials.**
Triage the catalogue by where state lives:

- **Tier A — structure & style** (badge, card, alert, avatar, breadcrumb,
  separator, skeleton, table, accordion, kbd, typography…): pure
  partials; mostly shipped already.
- **Tier B — local UI state, no data** (dialog, popover, dropdown,
  tooltip, switch, toggle-group, collapsible, sheet/drawer, carousel):
  platform primitives + small controllers. Bounded JS; partials suffice.
- **Tier C — data-coupled** (combobox, command, calendar/date-picker,
  data-table sort/filter/page, form validation, toast queue, OTP): the
  hypermedia answer moves state to the server, so the component IS a
  partial **plus an endpoint response contract** (what fragment the
  server returns for which hx- request). The command palette already
  proved the shape (`hx-get` → server-rendered results). This is the
  genuinely novel artifact class — shadcn never had to standardise
  server responses. For Dazzle it's free (Dazzle is the server). For
  external consumers, the registry must document the response contract
  per component or Tier C is vapor. Done well, it's the moat: nobody
  else publishes agent-consumable *hypermedia protocols* per component.

**Amendment 2: triage matrix, not 1:1 transliteration.** Walking the
shadcn list checkbox-style is Model-Driven-Failure bait (the abstraction
stops preserving semantics). Each entry gets an explicit *hypermedia
answer* and some get **rejected with rationale** (recorded like the
hless decision): e.g. `sonner` is a toast implementation detail (HM has
toast semantics); `resizable` panels serve IDE-like client layouts, not
server-owned ops apps; `sidebar` is app-shell (Dazzle's domain, not the
design system's). The KPI is agent-usability per component, not count.

## Honest limits (scope, not blockers)

- **Latency semantics differ.** Tier C round-trips where React resolves
  locally. For HM's target (data-dense, server-owned apps) htmx request
  states + preload cover it; don't claim parity for offline/local-first
  or per-keystroke-latency-critical UX.
- **Composition is convention without a checker.** React enforces
  anatomy via types; HTML enforces nothing — today's badge-slot bug was
  exactly this class. Phase 5's shape specs are the type system.
  It is the prerequisite, not an optional extra.
- **htmx4 is still beta.** The partials lean on stable attributes and
  the gallery carries a mock; protocol churn risk is real but bounded.
- **External adoption is unproven upside.** The thesis pays for itself
  Dazzle-only (stable target for emitters + verifiable agent output);
  outside consumers are the bonus, not the justification.

## Verdict

Proceed. Order: **Phase 5 conformance machinery first** (shape specs
derived from registry canonical markup, load-bearing structure only;
Dazzle emitters gated against them — starting with badge, command,
confirm), then the **catalogue walk in tranches** using a
have / partial / missing / rejected matrix where every Tier C entry
ships with its endpoint response contract documented in the registry.
