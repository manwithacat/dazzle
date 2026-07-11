---
name: stems
description: Reconstruct Dazzle/HM judgement from stems before inventing structure
---

# Skill: stems (epistemic entry)

Use when starting non-trivial work on the monorepo, HaTchi-MaXchi, or an example
app — architecture, new Hyperparts, DSL domain expansion, RBAC, or “should we
build X like Y?”

## Do this first

1. **Framework:** open `stems/INDEX.md`, then the stem that matches the task.
2. **This package (HM):** `packages/hatchi-maxchi/stems/INDEX.md` if UI/Hyperparts.
3. **This app:** `examples/<app>/stems/INDEX.md` or project `stems/INDEX.md`.
4. **Then** `AGENTS.md` (repo or package) for commands and playbooks.
5. **Then** code / DSL / unit packs.

## Authority (do not invert)

stems → AGENTS → ADRs/decisions → maps/tests → guides → gallery mocks

## Stop if

- You are about to invent a parallel domain model, SPA, or fourth picker without
  a matching stem (or an explicit new stem + INDEX entry).
- Example work overrides a framework stem on a framework question.

## Related

- Paper concepts: epistemic engineering (representations) + agent didactics (sequence)
- HM playbooks: `packages/hatchi-maxchi/docs/agent/`
