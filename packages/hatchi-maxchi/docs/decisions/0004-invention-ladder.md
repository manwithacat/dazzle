# 0004 — Invention ladder

**Status:** Accepted
**Date:** 2026-07-11

## Context

Agents need freedom to invent, and packages need reliable primitives. Unbounded
invention produces near-duplicate Hyperparts and almost-DOM forks. Zero freedom
forces wrong L1s into hosts (combobox-in-cell by force).

## Decision

Invention follows a **ladder** (always try lower rungs first):

1. **Reuse** — L1 matching job + lifetime + exchange (`pick-a-surface.md`).
2. **Refuse** — host cannot mount that L1 → local primitive + `does_not_compose`
   + optional spike.
3. **Promote** — repeated need → real composition or a proper new L1 with
   dual-lock and tests.
4. **New Hyperpart** — only after the above; contract-first
   (`contracts/AUTHORING.md`); prefer **Blueprint** for page motifs; **build-to-replace**
   a Dazzle hole or fill a gap no part covers; controller only if platform lacks
   a primitive.

App-local partials need not enter the package catalogue.

## Consequences

- “Like X but…” without a refuse edge or distinct exchange fails review.
- AUTHORING §0 is the ladder, not optional colour.
- Spikes document promotion criteria; refuse edges should not rot without a path.

## See also

- `docs/agent/invent-safely.md`
- `contracts/AUTHORING.md`
