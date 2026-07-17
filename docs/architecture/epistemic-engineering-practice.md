# Epistemic engineering in this repository

**Status:** practice note (not an ADR)
**Audience:** humans and agents reconstructing how Dazzle records judgement
**Related:** [`stems/README.md`](https://github.com/manwithacat/dazzle/blob/main/stems/README.md),
[Deferred Decisions](../decisions/INDEX.md),
[README — Epistemic engineering](https://github.com/manwithacat/dazzle/blob/main/README.md#epistemic-engineering-and-stems)

This note is the monorepo’s **internal application** of the discipline of
*epistemic engineering* (Barlow, 2026): the deliberate elicitation, representation,
compression, validation and maintenance of organisational judgement so that
artificial reasoners—and new human collaborators—can reconstruct it without
years of hallway socialisation.

Paper (Zenodo preprint): Barlow, J. M. (2026).
[*Epistemic Engineering: Towards a Discipline of Knowledge Representation for
Artificial Reasoners in Engineering Organisations*](https://zenodo.org/records/21415599)
([DOI 10.5281/zenodo.21415599](https://doi.org/10.5281/zenodo.21415599),
[PDF](https://zenodo.org/records/21415599/files/epistemic-engineering.pdf)).
The paper’s §6 repository exploration describes Dazzle as a field instance of
the same distinctions used below.

## Vocabulary (local)

| Term | In this repo | Not |
|------|----------------|-----|
| **Epistemic engineering** | Choosing *what* judgement is durable, where authority lives, how fidelity is tested | Optimising one prompt |
| **Agent didactics** | Ordering artefacts so reconstruction is reliable (curriculum, gates, sequence) | Dumping every Markdown file into context |
| **Stem** | Compact claim under `stems/` with reconstruct / not-this / expressions | Any long guide |
| **Expression** | ADR, test, dual-lock, example, playbook that *points at* a stem | The stem itself |
| **Counter-prior** | Named corpus pathology + right shape (`docs/counter-priors/`, classify hard-fails) | Vague “don’t do bad code” |
| **Deferred Decision (DD)** | Parked *plan* with checkable consumer-force conditions (`docs/decisions/`) | A stem; an ADR; a soft TODO |

Stems are not a privileged model input type. At inference they become ordinary
context. Their engineering role is **lifecycle**: declared authority, compression,
tests, and maintenance across tasks and models (paper §1, §5).

## Hierarchy of reconstruction (agent didactics)

Do **not** invert this order. Equal-looking files are not equal in authority
(stem: `stems/epistemic-layout.md`).

| Rank | Location | Role |
|------|----------|------|
| 1 | `stems/` | Enduring framework judgement |
| 2 | `AGENTS.md` | Always-on didactics + commands |
| 3 | [`docs/adr/`](../adr/INDEX.md) | Why a constitutional choice was taken |
| 4 | [`docs/decisions/`](../decisions/INDEX.md) | **When** residual work may proceed (PARKED → FORCED → DONE) |
| 5 | [`docs/counter-priors/`](../counter-priors/INDEX.md) | Negative space / corpus pull |
| 6 | Package / example `stems/` | Local domain or design-system judgement |
| 7 | Guides / reference | Mechanics |
| 8 | Dual-locks, drift gates, prove, ship-surface | **Assessment** — executable consequences of the above |

**Curriculum (default agent path):**

1. `stems/INDEX.md` → matching stem
2. `AGENTS.md` for commands and hard rules
3. ADR if the change is constitutional
4. DD if the work is labeled `future` or residual of a closed umbrella
5. Counter-prior / representation prove if the design smells like a known failure
6. Examples and source only after the above

## How ADRs, DDs, and counter-priors compose

Worked example: shared child entity / poly_ref (see [DD-001](../decisions/DD-001-1617-poly-ref-and-sti-eav.md)).

| Layer | Answers |
|-------|---------|
| Stem + hatches ladder | Prefer exclusive FKs / TPT / JSONB first; four-question interrogation |
| ADR-0027 | No untyped polymorphic_ref as product default |
| ADR-0042 | Typed `poly_ref` + scope is the *accepted* escape hatch when interrogation fails |
| Counter-prior / classify | Hand-rolled `*_type`+`*_id` hard-fails |
| **DD-001** | *Product polish* (#1621/#1622) stays **PARKED** until a named consumer forces it |
| Gates | prove/classify enforce priors; deferred-decision gate keeps DD-001 discoverable |

Without the DD layer, agents either re-implement parked polish “because poly is
interesting” or lose the plan when issue comments age out. The DD does **not**
restate the stem; it freezes **timing and force conditions**.

## Agent didactics beyond prose

The paper notes that didactics is not only explanatory text. Dazzle also teaches by:

| Mechanism | Example |
|-----------|---------|
| Sequence | stems → AGENTS → ADR/DD → code |
| Positive example | `examples/simple_task`, journey dogfood |
| Negative example | counter-priors; stem “Not this” |
| Interception | dual-locks; `make ship-surface`; representation classify |
| Freshness | drift gates; cimonitor “promote the check” after badge repair |

A **stale high-authority artefact** is worse than silence: it reconstructs the
wrong organisation (paper §6; ship-surface / SPEC footers / API baselines).

## Maintenance obligations

| Event | Epistemic action |
|-------|------------------|
| Constitutional break | ADR (+ stem update if judgement shifted) |
| Park residual work | **DD required** — not only a `future` label or chat comment |
| Consumer force lands | DD `PARKED` → `FORCED` → implement plan → `DONE` |
| New recurrent CI red class | Promote into `ship_surface` / `preflight_surface` |
| New corpus pathology | Counter-prior entry + gate when possible |

## What we deliberately do not do

- Call every preference a “stem” (term loses discrimination).
- Put DDs under `stems/` (timing ≠ enduring character of the org).
- Treat improve STALE map noise as consumer force.
- Speculative-build PARKED DDs (#1621/#1622 class).

## Pointers

- Practice entry: [README — Epistemic engineering and stems](https://github.com/manwithacat/dazzle/blob/main/README.md#epistemic-engineering-and-stems)
- Stem skill: `.agents/skills/stems/SKILL.md`
- Local CI as epistemic freshness: [local-ci-concordance](../contributing/local-ci-concordance.md)
