# 0003 — Composition is declared (and refusal is too)

**Status:** Accepted
**Date:** 2026-07-11

## Context

Hyperparts do not import each other at runtime. Agents still “compose” by
resemblance (dogfooding combobox into the data table because both select) or
by silent embedding without registry edges. Consumer blast radius then lies.

## Decision

| Edge | Meaning |
|------|---------|
| **`composes`** | Parent embeds child in partial or exchange slot |
| **`composes_with`** | Soft related-parts guidance only |
| **`extensions`** | Optional controller riding host seams |
| **`does_not_compose`** | Parent implements a similar job with a **local primitive**; not the child Hyperpart |

- Resemblance without an edge is **not** composition.
- Refusal is first-class: require/forbid controller locks + optional spike path.
- Parent dual-lock names host seams; child dual-lock is the child’s interface.
- Reverse index: `CONSUMER_MAP.md` (generated, CI drift-gated).

## Consequences

- Agents must open the consumer map before mutating a widely used L1.
- Flipping a refuse edge is a deliberate promotion (spike + dual-lock + tests),
  not a drive-by mount.
- Prose-only “we don’t use X” is insufficient; declare `does_not_compose`.

## See also

- `docs/agent/compose-or-refuse.md`
- `CONSUMER_MAP.md`
- `docs/spikes/combobox-in-grid-cell.md`
