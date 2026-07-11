# 0007 — No Alpine.js in HM core

**Status:** Accepted
**Date:** 2026-07-11
**Stem:** `stems/morph-safe-hypermedia.md`

## Context

Alpine’s primitive is **local reactive component state** (`x-data` scopes,
client-applied classes, expression bindings). HM’s primitive is
**server-rendered DOM with explicit affordances** and morph-friendly updates.
Mixing them produces recurring failure classes, not one-off bugs:

- morph strips or reverts Alpine-applied classes;
- `x-data` scope boundaries silently kill menus and delegated handlers;
- interpolated ids inside Alpine expressions create quoting hazards;
- JSON / `x-data` state duplicates what the DOM already carries;
- client state competes with server-rendered state after swaps.

HM is **not** “htmx plus Alpine.”

## Decision

**Alpine.js must not be used inside HM core** (Hyperparts, controllers, dual-lock
templates, gallery product contracts, framework shells that morph).

**Preferred behaviour model:** small named vanilla modules that:

- attach listeners at stable roots or `document` (delegation);
- discover behaviour via `data-hm-*` / dual-lock `data-dz-*` attributes;
- read state from the DOM and write only narrowly scoped DOM state when needed;
- avoid parallel application models, hydration, and per-instance lifecycle graphs.

**Userland exception:** Alpine may appear in isolated app/marketing islands
explicitly outside HM core morphing and state model (decorative disclosure,
client-only demos, non-persistent previews). Those islands must be marked as
boundaries (decision 0006) and must not be presented as HM Hyperpart contracts.

### Forbidden in core (non-exhaustive)

`x-data`, `x-show`, `x-bind`, `:class`, `@click` / `x-on`, `x-model`, `x-effect`,
`x-ref`, `x-for`, `x-if`, and Alpine plugin attributes on HM-owned surfaces.

### Especially do not use Alpine for

Data tables, column menus, filters, sort, pagination, selection, row actions,
server-rendered menu state, or anything inside frequently morphed regions.

## Consequences

- Controllers under `controllers/` stay vanilla and document-delegated.
- Template lint (decision 0008) fails on Alpine attributes in core fixtures.
- Migrating legacy Alpine stragglers is a correctness fix, not style churn.
- Dazzle app islands that use Alpine remain possible **outside** HM core
  contracts; they do not redefine Hyperpart doctrine.

## See also

- `stems/morph-safe-hypermedia.md`
- `docs/decisions/0001-hyperpart-not-component.md`
- `docs/decisions/0006-dom-identity-and-state.md`
