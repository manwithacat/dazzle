# Framework Structural Fitness — Design

**Status:** Approved (2026-06-19). A scoped, Dazzle-native adaptation of the external
`structural-fitness-ci-spec.md` (written without codebase knowledge). Points Dazzle's existing
"encode intent as enforceable constraints + ratchet baselines" instinct at the **framework's own
Python code structure** — the one surface with no fitness coverage today, now decaying under high
(largely agent-driven) change velocity.

## Problem

Dazzle's gates all target the DSL/IR/generated-app surface or user-app pathologies; `src/dazzle/`'s
own internal structure is ungated. Under ~25 releases/session velocity, decay is measurable:
`page_routes.py` 3052 lines, `entity.py` 2981, `server.py` 2354, `app_factory.py` 1350 — and this
session's cross-module friction (`#1392` item 2's `ui`↔`back` wiring; the `#1299` core↔back IR
boundary) is the early signal. Two decay modes are live and ungated: **boundary erosion** and
**size/complexity creep**.

The good news, verified: the layer boundaries are still nearly clean (`core → back` = 1 file,
`core → ui` = 0, `ui → back/auth` = 0, `ui → back` = 1). Locking them is cheap **now**.

## Goal

Diagnose framework structural debt and **gate both decay modes** — reusing Dazzle's drift-baseline
ratchet (`test_*_drift.py` + committed baselines + `--write` regen + CHANGELOG discipline) and the
existing `dazzle fitness` Typer app. No parallel orchestrator.

## Non-goals (deliberately dropped from the external spec)

- The standalone `fitness/` orchestrator + `Finding` schema + SARIF pipeline — Dazzle already has
  drift/conformance/sentinel reporting.
- **Type-annotation coverage** — `mypy src/dazzle` is already a hard gate; the tree is heavily typed.
- `jscpd`/Node duplication; `diff-cover` floor; `wily`/`pydeps` (the trend-depth tier).
- The **core↔back IR-conversion integrity** (#1299 "value dropped at the converter") — a *data-flow*
  concern, NOT expressible as an import contract (back/ legitimately imports core.ir everywhere). A
  future `test_no_*`-style converter-parity gate is the right tool; out of scope here.
- Component **C** (a `framework-structure` /improve lane + a hotspot-sourced counter-prior feeding
  the agent) — its own later initiative; depends on A1's ranking existing first.

## Components

### A1 — hotspot diagnostic (`dazzle fitness code`)

A new subcommand on the existing `dazzle fitness` Typer app. A hand-rolled join (no JVM/`code-maat`):
per-file **change frequency** (`git log --since=<window> --name-only`, counted; window default 180d)
× per-file **complexity** (`radon cc`/`radon mi -j`), ranked by the product. Writes a committed
`dev_docs/framework-hotspots.md` — the ordered structural-debt queue (more actionable than raw size,
since it weights *how often the complex file churns*). **Report-only; never blocks.** Feeds the
later /improve lane (C) and orders manual refactoring (the harness protects gains, it doesn't make
them).

### A2 — complexity ratchet (gates creep)

`dazzle fitness code --write` snapshots **per-file MI rank** + **per-function CC** for every module
under `src/dazzle/` into a committed `tests/unit/fixtures/complexity_baseline.json`.
`tests/unit/test_complexity_ratchet.py` (a drift gate) fails when:
- any file's radon **MI rank drops below** its baseline (e.g. B→C), **or**
- a **new function exceeds** the CC ceiling (Appendix default 15), **or**
- a **new file** lands at C rank.

`--write` re-tightens the baseline on improvement (one-way valve — same as `api-surface`/`ir-types`
drift). Run **whole-tree** (like every other Dazzle drift gate), not diff-scoped: simpler, catches
any worsening regardless of which change introduced it, and fits the pytest-driven CI. Inherits the
existing `--write` + CHANGELOG-on-drift discipline.

### B — import contracts (gates boundary erosion)

Add `import-linter` (new dev dep, uv-pinned) with a `[tool.importlinter]` block in `pyproject.toml`:
- **`core/` independence** — `dazzle.core` must not import `dazzle.http` or `dazzle.page` (the IR/parser
  stays backend-agnostic — the load-bearing boundary).
- **`ui/ ↛ back/`** — the render/UI layer must not reach into the runtime.
- **`back/ ↛ sqlite`** (ADR-0008) — forbid `sqlite3` + `aiosqlite` imports in `dazzle.http`
  (legitimately-SQLite MCP KG + `core/process/version_manager` are *outside* `back/`, so the scope
  is exactly right).

`tests/unit/test_import_contracts.py` runs import-linter (via its API or `lint-imports`) and gates.
**The 2 current violations (`core→back`, `ui→back`) are investigated and FIXED if genuine leaks,
then the contracts gate `absolute`** — locking a clean boundary beats baselining a dirty one. Only
if a violation proves load-bearing does it go on a documented, shrinking allow-list.

## Architecture & boundaries

| Unit | Responsibility | Reuses |
|------|----------------|--------|
| `dazzle fitness code` (cli/fitness.py + a new `dazzle.fitness.code` module) | churn×complexity ranking + `--write` baseline | existing `fitness` Typer app |
| `complexity_baseline.json` + `test_complexity_ratchet.py` | ratchet creep | the `test_*_drift.py` pattern |
| `[tool.importlinter]` + `test_import_contracts.py` | ratchet boundaries | the `test_no_*.py` policy-gate pattern |
| `dev_docs/framework-hotspots.md` | the debt queue (report) | — |

## Dependencies

`radon` and `import-linter` as **dev** dependencies (`pyproject.toml [dev]` + `uv lock`, committed in
the same change per the uv-canonical-toolchain rule). Both are maintained, pure-Python, no JVM/Node.
`git log` is shelled out (already a git repo). No runtime deps added.

## Testing

- **A1:** `dazzle fitness code` on the repo produces a non-empty ranking; the top entries are
  high-churn × high-complexity files (page_routes/server/app_factory/entity expected); `--write`
  regenerates `framework-hotspots.md` deterministically (stable ordering, no timestamps that break
  re-runs — pass the window as an arg, no `Date.now()` in committed output).
- **A2:** the ratchet passes on the committed baseline; a synthetic worsening (a file's MI rank
  dropped, or a new CC-20 function) fails it; `--write` then re-greens it. The baseline is valid JSON
  (the v0.83.16 lesson — never run `ruff format` over it).
- **B:** `test_import_contracts.py` passes with the 2 violations fixed; a synthetic `core/` file
  importing `dazzle.http` fails it.

## Phases (for writing-plans)

- **P1** — deps (`radon`, `import-linter`) + `dazzle fitness code` (A1 ranking + `--write` →
  `dev_docs/framework-hotspots.md`) + a smoke test. Ships the diagnostic.
- **P2** — A2 complexity ratchet: `--write` baseline + `test_complexity_ratchet.py` + CHANGELOG note.
- **P3** — B import contracts: investigate + fix the 2 boundary violations, author the contracts,
  `test_import_contracts.py`, gate `absolute`. CHANGELOG + Agent Guidance ("framework layers are now
  import-gated; `core` ↛ `back`/`ui`, `ui` ↛ `back`, `back` ↛ sqlite").
