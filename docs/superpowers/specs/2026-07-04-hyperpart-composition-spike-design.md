# Hyperpart composition spike — design

**Date:** 2026-07-04
**Status:** design approved (conversation) — spike
**Scope:** `packages/hatchi-maxchi/` (registry, gallery build, controllers, CSS, tests).

## Why

Before expanding the primitive library, prove the Hyperpart model can **compose**
and establish the template every future composite follows. The insight: hypermedia
composition is **by-exchange, not by-tree** (shadcn composes via a React tree; HM
composes by nesting markup OR by a slot that `hx-get`s a child fragment). The
`Exchange` contract already models the dynamic seam — the command palette is
already an exchange-composite. This spike makes composition *first-class*:
visible, checkable, and demonstrated.

## Decision: `composes` is declarative, not a runtime engine

A composite's partial still contains the real markup (nested children, or a slot
with `hx-get`). `composes: tuple[str, ...]` only **declares** which child
Hyperparts it embeds — it never *executes* an include/template. This is the
discipline that keeps HM out of the 4GL "everything is a magic container" failure
mode and out of React-tree complexity: composition stays "it's just HTML (nested
or hx-loaded)"; `composes` describes it for docs + drift + dependency aggregation.

(The rejected alternative — a server-side slot mechanism that *references* a
child's partial to remove copy-drift — edges toward a template engine; defer until
copy-drift is a demonstrated problem.)

## Infrastructure

1. **`Hyperpart.composes: tuple[str, ...] = ()`** — child Hyperpart ids it embeds.
2. **Dependency-class aggregation** — a composite's chips = `["Composite"]` +
   union of its own classes (Sprite/Controller/Endpoint) and each child's own
   classes (one level; children are primitives). Dedup, order-preserving.
3. **"Composed of" note** — the gallery renders `Composed of: <links to children>`
   in a composite's section.
4. **Drift gate** — every id in `composes` must be a real Hyperpart (test_contract).
5. **New `Composites` group** in `GROUPS` surfaces them as a category.

## Controller instance-isolation (the real technical blocker)

Today `dz-command.js` does `document.querySelector("dialog.dz-command")` — a single
global instance. Composable interactive components must be **instance-isolated**:
event-delegated from `document`, scoping every DOM query to `evt.target.closest(root)`
so N instances on one page each manage their own state (the way `<details>` menus
already compose cleanly). The spike's new controller is written this way from the
start and is the reference pattern. (`dz-command`'s page-level `⌘K` singleton is
left as-is — a page has one palette; not every controller needs multi-instance,
but *composable* ones do.)

## The two flagship composites

### 1. Toolbar — inline composition
- `composes = ("button", "toggle-group", "menu")`. A `role="toolbar"` flex bar
  nesting real primitive markup. No controller, no exchange.
- Demonstrates: static nesting + dependency aggregation (Composite + Sprite,
  since the menu carries icons).

### 2. Master–detail — exchange composition (the canonical htmx composite)
- `composes = ("card",)`. A list pane + a detail pane; clicking a list item
  `hx-get`s its detail **card** fragment into the detail slot.
- `Exchange`: `GET /app/master-detail/{id}` → a card fragment → `#…__detail`,
  states `loading/populated/error`.
- Controller `dz-master-detail.js` — **instance-isolated**: delegated click sets
  `aria-current` on the chosen item and clears siblings *within the same
  `.dz-master-detail` root*, so two master-details coexist.
- Mock `/mock/master-detail/*` returns a card fragment for the static gallery.
- Demonstrates: exchange-composition, composing an existing primitive (card) via
  `hx-get`, and instance-isolation on a live example.

## Acceptance

- Both composites render live + as snippets; chips show `Composite` + aggregated
  classes; "Composed of" links resolve.
- `composes` drift gate + naming-grammar gate + WCAG + Nu/W3C validity + visual
  all green (monorepo + standalone after sync).
- Master-detail keyboard/selection works with two instances on the page (isolation).

## Non-goals

- No runtime slot/include engine (`composes` stays declarative).
- Not expanding the primitive library (that's the next line of work; this spike
  de-risks the composition seam first).
- No deep (composite-of-composite) recursion in aggregation yet — one level.
