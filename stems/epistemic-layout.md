# Stem: Epistemic layout

## Claim

The repository is a **representational system**. Different artefact classes have
different authority. Agents reconstruct judgement from that hierarchy; they do
not treat every Markdown file as equal. **Epistemic engineering** decides what
judgement is durable; **agent didactics** is the ordered path that makes that
judgement reconstructable during work (Barlow, 2026 — see practice note).

## Reconstruct

| Rank | Location | Role |
|------|----------|------|
| 1 | `stems/` | Framework stems (this tree) — enduring judgement |
| 2 | `AGENTS.md` | Always-on didactics + commands |
| 3 | `docs/adr/` | Decision history (expressions of stems) |
| 4 | `docs/decisions/` | **Deferred Decisions** — parked plans + consumer-force reopen |
| 5 | `docs/counter-priors/` | Negative space / corpus pull (expressions of “not this”) |
| 6 | Package/example `stems/` | Local stems (domain or HM) |
| 7 | Guides / reference | Mechanics |
| 8 | Dual-locks, drift gates, prove, `make ship-surface` | Executable assessment |

**Curriculum (do not invert):**

1. `stems/INDEX.md` → matching stem
2. `AGENTS.md` for commands and hard rules
3. ADR if the change is constitutional
4. DD if work is `future` / residual of a closed umbrella (`rg '^status: PARKED' docs/decisions/`)
5. Counter-prior / representation classify if the design smells like a known failure
6. Examples and source

Package maps (e.g. HM `CONSUMER_MAP.md`, `CONTRACT_SURFACE.md`) are **machine
truth** for that package’s graph and dual-locks—consult when mutating those
surfaces.

### How artefact classes compose (not interchangeable)

| Class | Answers | Example |
|-------|---------|---------|
| **Stem** | What must stay true across implementations | dsl-first, clean-breaks |
| **ADR** | Why we chose a constitutional option | ADR-0042 poly_ref |
| **DD** | *When* residual work may proceed; full plan if forced | [DD-001](../docs/decisions/DD-001-1617-poly-ref-and-sti-eav.md) |
| **Counter-prior** | Plausible wrong shape the corpus will re-suggest | polymorphic associations |
| **Gate / dual-lock** | Machine intercept when reconstruction fails | classify hand_rolled_poly |

A DD is **not** a stem. Timing and consumer-force are not the same as enduring
character of the organisation.

## Not this

- Prompt libraries as the main engineering artefact.
- “More docs” without organising stems.
- Example demos overriding framework stems on framework questions.
- Treating every Markdown file as equal weight in context.
- Implementing `future` / PARKED DD work without a named consumer force.
- Inventing a parallel hierarchy in chat that contradicts this table.

## Expressions

- This directory; `packages/hatchi-maxchi/stems/`; `examples/*/stems/`
- `AGENTS.md` curriculum + Deferred decisions section
- `docs/decisions/INDEX.md`, `docs/counter-priors/INDEX.md`
- `docs/architecture/epistemic-engineering-practice.md`
- README › Epistemic engineering and stems
- Dual-locks, `make ship-surface`, representation prove/classify
