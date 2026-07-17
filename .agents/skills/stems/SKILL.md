---
name: stems
description: Reconstruct Dazzle/HM judgement from stems before inventing structure
---

# Skill: stems (epistemic entry)

Use when starting non-trivial work on the monorepo, HaTchi-MaXchi, or an example
app — architecture, new Hyperparts, DSL domain expansion, RBAC, or “should we
build X like Y?”

Practice note: `docs/architecture/epistemic-engineering-practice.md`
Paper: [Epistemic Engineering](https://doi.org/10.5281/zenodo.21415599) (Barlow, 2026)

## Do this first (agent didactics)

1. **Framework:** open `stems/INDEX.md`, then the stem that matches the task.
2. **This package (HM):** `packages/hatchi-maxchi/stems/INDEX.md` if UI/Hyperparts.
3. **This app:** `examples/<app>/stems/INDEX.md` or project `stems/INDEX.md`.
4. **Then** `AGENTS.md` (repo or package) for commands and playbooks.
5. **Constitutional?** → `docs/adr/`.
6. **Parked residual / `future` issue?** → `docs/decisions/` (`rg '^status: PARKED'`).
   Do **not** implement a PARKED DD without moving it to `FORCED` with a named consumer.
7. **Design smells like a corpus pathology?** → `docs/counter-priors/` or
   `dazzle prove representation` / MCP knowledge counter_prior.
8. **Then** code / DSL / unit packs / examples.

## Authority (do not invert)

```text
stems → AGENTS → ADRs → DDs → counter-priors → package/app stems
  → maps/tests/dual-locks/ship-surface → guides → gallery mocks
```

| Class | Is a stem? | Role |
|-------|------------|------|
| `stems/*.md` | yes | Enduring judgement |
| ADR | no (expression) | Why we chose |
| DD | **no** | When residual work may proceed |
| Counter-prior | no | Negative space |
| Dual-lock / gate | no | Assessment |

## Stop if

- You are about to invent a parallel domain model, SPA, or fourth picker without
  a matching stem (or an explicit new stem + INDEX entry).
- Example work overrides a framework stem on a framework question.
- You are about to implement a `future` issue that links a PARKED DD “to make progress.”
- You are about to treat every Markdown file as equal weight in context.

## Related

- Stem: `stems/epistemic-layout.md`
- Deferred Decisions: `docs/decisions/INDEX.md`
- Counter-priors: `docs/counter-priors/INDEX.md`
- HM playbooks: `packages/hatchi-maxchi/docs/agent/`
