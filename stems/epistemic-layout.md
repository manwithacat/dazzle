# Stem: Epistemic layout

## Claim

The repository is a **representational system**. Different artefact classes have
different authority. Agents reconstruct judgement from that hierarchy; they do
not treat every Markdown file as equal.

## Reconstruct

| Rank | Location | Role |
|------|----------|------|
| 1 | `stems/` | Framework stems (this tree) |
| 2 | `AGENTS.md` | Always-on didactics + commands |
| 3 | `docs/adr/` | Decision history (expressions) |
| 4 | Package/example `stems/` | Local stems (domain or HM) |
| 5 | Guides / reference | Mechanics |
| 6 | Gallery mocks / demos | Not product API |

Package maps (e.g. HM `CONSUMER_MAP.md`, `CONTRACT_SURFACE.md`) are **machine
truth** for that package’s graph and dual-locks—consult when mutating those
surfaces.

## Not this

- Prompt libraries as the main engineering artefact.
- “More docs” without organising stems.
- Example demos overriding framework stems on framework questions.

## Expressions

- This directory; `packages/hatchi-maxchi/stems/`; `examples/*/stems/`
- `AGENTS.md` curriculum
- HaTchi-MaXchi agent playbooks under `packages/hatchi-maxchi/docs/agent/`
