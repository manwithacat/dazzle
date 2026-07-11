# Playbook: invent safely

**Goal:** Decide whether a new package Hyperpart is allowed; if yes, start correctly.
**Open when:** “We need a new component / picker / widget.”
**Stem:** `docs/decisions/0004-invention-ladder.md`

## Ladder (do not skip)

| Rung | Action | Exit if true |
|------|--------|--------------|
| 1 | `pick-a-surface.md` | Existing L1 fits job + lifetime + exchange |
| 2 | `compose-or-refuse.md` | Host can embed L1 **or** local primitive + refuse is enough |
| 3 | Promote | Spike + dual-lock: compose for real or split a true new L1 |
| 4 | **New Hyperpart** | Only here |

## Before rung 4, answer all

- [ ] Is this a **page motif** of existing parts? → **Blueprint**, not Hyperpart.
- [ ] Does it **replace** a Dazzle-native hole or fill a gap no part covers?
      (Decoration that shadows unconverted CSS is not a part.)
- [ ] Is the **lifetime + exchange** different from every existing L1?
- [ ] Can a **controller-less** partial work? (Controller only if platform lacks primitive.)
- [ ] Will the name import React priors? Prefer Hyperpart vocabulary in docs.

If any checkbox fails, stop inventing a package part.

## If rung 4 proceeds

1. Follow **`contracts/AUTHORING.md`** contract-first (model → DOM_CONTRACT →
   exemplars → render → controller → registry → Dazzle emitter if monorepo).
2. Register exchanges for every request affordance.
3. Guidance: seams + pitfalls (controller-bearing).
4. Behaviour test targeting `hyperparts/<id>.html`.
5. Rebuild site agent pack; regenerate dual-lock coverage.
6. Add consumer-map edges when hosts compose/refuse it.

## Stop conditions

- “Like combobox but for grid” without refuse/promote story → wrong rung.
- New part that is only CSS restyle of an existing partial → not a Hyperpart.
- Pasting `contracts/*.py` dual-lock into app routes as the product API → wrong audience.

## Next

- Authoring path: `contracts/AUTHORING.md`
- Curriculum: `AGENTS.md`
