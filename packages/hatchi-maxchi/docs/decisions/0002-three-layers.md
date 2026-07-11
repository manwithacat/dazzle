# 0002 — Three layers: recipe, surface, host

**Status:** Accepted
**Date:** 2026-07-11

## Context

Many interactions share a **visual shape** (e.g. “dropdown”) but differ in
**lifetime** and **exchange** (form field vs ephemeral grid cell vs remote FK
typeahead). Agents collapse shape into identity and either merge Hyperparts
incorrectly or invent a fourth picker.

## Decision

Organise judgement in three layers:

| Layer | Question | Unit |
|-------|----------|------|
| **L0 Recipe** | What job is the user doing? | Short pick-matrix (`docs/agent/pick-a-surface.md`) |
| **L1 Surface** | Markup + exchange + lifetime + dual-lock? | One Hyperpart (or declared host-local primitive) |
| **L2 Host** | Who embeds or refuses that surface? | Parent Hyperpart, Blueprint, or extension |

**Same L0 does not imply same L1.**
**L1 identity is lifetime + exchange family**, not appearance.
**L2 hosts do not redefine L0 or fork L1 DOM** “for flexibility.”

Example: L0 single-select → L1 `combobox` (form) *or* grid-edit bare select
(cell); L2 `grid` refuses combobox for in-cell edit today.

## Consequences

- “Should these be the same Hyperpart?” starts with a lifetime/exchange table.
- Mode flags that switch commit path or lifetime on one L1 are a design smell.
- Recipe matrix stays short; it is not a second catalogue of parts.
- Layers are **taxonomy and didactics**, not a runtime import system (no RSC).

## See also

- `docs/agent/pick-a-surface.md`
- `docs/decisions/0003-composition-declared.md`
