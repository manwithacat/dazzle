# Stems — Dazzle framework

**Stems** are the comparatively small conceptual structures from which large
bodies of Dazzle engineering judgement can be reconstructed. They are not
“more documentation.” They are the objects of **epistemic engineering** in
this repository: deliberately maintained, compact representations of
organisational judgement for human and artificial collaborators.

| Term | Role here |
|------|-----------|
| **Stem** | Compressed representation of organisational judgement (this directory) |
| **Expression** | ADR, code path, test, example, dual-lock, or playbook that *points at* a stem |
| **Agent didactics** | How stems and instructions are **sequenced** so a reasoner reconstructs them reliably (`AGENTS.md`, gates) |
| **Counter-prior** | Named corpus pathology + preferred shape (`docs/counter-priors/`) |
| **Deferred Decision (DD)** | Parked *plan* + checkable reopen conditions (`docs/decisions/`) — **not** a stem |
| **Prompt** | Immediate instruction — secondary once stems exist |

Full practice note: [`docs/architecture/epistemic-engineering-practice.md`](../docs/architecture/epistemic-engineering-practice.md).
Published framing: [Epistemic Engineering](https://doi.org/10.5281/zenodo.21415599) (Barlow, 2026).

## Authority

When reconstructing Dazzle judgement:

1. **`stems/`** (this tree) — what must remain true across implementations
2. **`AGENTS.md`** — what to do now (curriculum + commands)
3. **`docs/adr/`** — why a historical decision was taken (expressions of stems)
4. **`docs/decisions/`** — whether residual work is still PARKED or has been FORCED
5. **`docs/counter-priors/`** — negative space the corpus will re-propose
6. **Source + tests + dual-locks + ship-surface** — machine truth / assessment

If an example or package local `stems/` conflicts with **framework** stems on a
framework question, the framework stem wins. App stems own **domain** judgement.

## Layout

```
stems/
  README.md          # this file
  INDEX.md           # catalogue — every stem listed
  <slug>.md          # one stem per file (keep short)
```

Each stem file:

- **Claim** — one paragraph
- **Reconstruct** — what a competent reasoner should conclude
- **Not this** — common mis-reconstructions
- **Expressions** — links to ADRs, DDs, code, tests, examples

## Packages and examples

| Location | Owns |
|----------|------|
| `/stems/` | Framework (this tree) |
| `packages/hatchi-maxchi/stems/` | HaTchi-MaXchi design-system stems |
| `examples/<app>/stems/` | That app’s domain stems + pointer to framework |
| App template blank | Scaffold `stems/` for new projects |
| `stems/app-template/` | Notes for example-app stems layout (not an app) |

## Didactics

**Default agent path:**

1. Open `stems/INDEX.md` → the stem that matches the task
2. `AGENTS.md` for commands and hard rules
3. ADR if constitutional; **DD** if the work is parked residual (`future` / umbrella leftover)
4. Counter-prior / `dazzle prove representation` when the design smells like a known failure
5. Only then local code / examples

Do not treat `docs/` guides as equal weight to `stems/`.
Do not implement a PARKED DD without a named consumer force (see
[`docs/decisions/INDEX.md`](../docs/decisions/INDEX.md)).

Humans: same path when onboarding; ADRs remain decision history; DDs remain
long-horizon parking with force conditions.

## Related

- [epistemic-layout](epistemic-layout.md) stem (hierarchy table)
- [docs/architecture/epistemic-engineering-practice.md](../docs/architecture/epistemic-engineering-practice.md)
- Skill: `.agents/skills/stems/SKILL.md`
