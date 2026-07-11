# Stems — Dazzle framework

**Stems** are the comparatively small conceptual structures from which large
bodies of Dazzle engineering judgement can be reconstructed. They are not
“more documentation.” They are the objects of **epistemic engineering** in
this repository.

| Term | Role here |
|------|-----------|
| **Stem** | Compressed representation of organisational judgement (this directory) |
| **Expression** | ADR, code path, test, example, or playbook that *points at* a stem |
| **Agent didactics** | How stems are sequenced so a reasoner reconstructs them reliably (`AGENTS.md`) |
| **Prompt** | Immediate instruction — secondary once stems exist |

## Authority

When reconstructing Dazzle judgement:

1. **`stems/`** (this tree) — what must remain true across implementations
2. **`AGENTS.md`** — what to do now (curriculum + commands)
3. **`docs/adr/`** — why a historical decision was taken (expressions of stems)
4. **`docs/`** reference / guides — mechanics and tutorials
5. **Source + tests** — machine truth for behaviour

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
- **Expressions** — links to ADRs, code, tests, examples

## Packages and examples

| Location | Owns |
|----------|------|
| `/stems/` | Framework (this tree) |
| `packages/hatchi-maxchi/stems/` | HaTchi-MaXchi design-system stems |
| `examples/<app>/stems/` | That app’s domain stems + pointer to framework |
| App template blank | Scaffold `stems/` for new projects |
| `stems/app-template/` | Notes for example-app stems layout (not an app) |

## Didactics

Agents: open `AGENTS.md` → `stems/INDEX.md` → the stem that matches the task →
only then local code. Do not treat `docs/` as equal weight to `stems/`.

Humans: same path when onboarding; ADRs remain the place for decision history.
