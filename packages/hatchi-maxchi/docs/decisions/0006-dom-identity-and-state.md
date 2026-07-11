# 0006 — DOM identity and DOM-carried state

**Status:** Accepted
**Date:** 2026-07-11
**Stem:** `stems/morph-safe-hypermedia.md`

## Context

Morphing and agent inspectability both reward **stable identity** and **state
visible in markup**. Patterns that work for one-shot `innerHTML` replacement —
random ids, index-based keys, wrapper churn, JSON config mirroring the table —
break morph keys, ARIA links, and agent reconstruction.

## Decision

### Identity

Elements that participate in morphing (or act as persistent targets) **must**
have stable, deterministic identity:

- Prefer domain keys: `id="invoice-row-{{ invoice.id }}"`, `data-row-id`,
  `data-column-id`, stable menu/panel roots.
- Prefer framework markers (`data-hm-*` / dual-lock `data-dz-*`) that declare
  role without encoding unstable indexes.
- **Avoid:** duplicate ids; ids from loop indexes, timestamps, or random tokens;
  conditional wrappers that appear/disappear around the same logical content;
  sibling reorders without stable keys; client classes that fight server classes.

### State surface

UI state that affects server-rendered HM surfaces is carried in the DOM (and
server), not a parallel client model:

- URL / query parameters;
- form inputs and hidden fields;
- `data-*` attributes;
- ARIA attributes (`aria-expanded`, `aria-pressed`, `aria-selected`, …);
- server-rendered classes that are part of the contract.

### Configuration

**The DOM is the default configuration surface.** Do not add JSON config blobs
that re-list information already present in markup (e.g. columns in `<th
data-column-id>` *and* a parallel column array). JSON is allowed only when the
data cannot naturally live in markup, has a clear owner/lifecycle, is
validated, and does not become a second source of truth.

### Islands

Third-party or preserve-across-morph widgets declare an **explicit boundary**
(e.g. island / morph-skip attributes — exact names may evolve). Islands are
named exceptions, not silent exceptions.

## Consequences

- Controllers discover behaviour from attributes and read state from the DOM
  (decision 0007).
- Dual-lock and contract tests pin identity and state attributes, not only
  class names.
- Template lint posture (decision 0008) prioritises duplicate/unstable ids,
  ARIA consistency, and config duplication.
- Agent review checklist: second source of truth? stable ids? legible from HTML?

## See also

- `stems/morph-safe-hypermedia.md`
- `docs/decisions/0005-morphing-policy.md`
- `docs/decisions/0007-no-alpine-in-core.md`
