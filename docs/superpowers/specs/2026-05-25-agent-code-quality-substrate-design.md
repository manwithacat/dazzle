# Agent Code Quality Enforcement Substrate — Operationalisation Design

**Status:** Draft
**Author:** James Barlow (idea), with Claude (design)
**Date:** 2026-05-25
**Source idea:** `~/Desktop/dazzle-spec-agent-code-quality-substrate.md`
**Related:** `dev_docs/2026-05-25-substrate-audit.md`, `docs/superpowers/specs/2026-03-26-python-audit-agent-design.md`, `docs/superpowers/specs/2026-03-19-anti-pattern-guidance-design.md`

## 1. Why this design exists

The source idea proposes a three-layer substrate (bundled tooling + convention library + custom AST detectors) to systematically catch LLM-prior antipatterns in agent-generated Python before they enter the persistent codebase. The proposal is sound; the only operationalisation question is *fit* — most of the infrastructure it describes is already half-built in Dazzle. This document maps the idea onto what exists, identifies the actual gaps, and scopes a first vertical slice that proves the pipeline end-to-end.

## 2. Reframing — the spec is an extension, not a new substrate

The source idea uses a three-layer model (tooling / convention library / AST detectors). Dazzle already operates a three-layer substrate using different numbering, documented in `dev_docs/2026-05-25-substrate-audit.md` and `project_prior_correction_substrate.md`:

| Existing substrate layer | What it does | Source-idea mapping |
|---|---|---|
| **1. Grammar** | DSL excludes antipatterns by construction (ADR-0024, ADR-0026, ADR-0027, predicate algebra). | Out of scope — the idea is about hand-written Python, not DSL. |
| **2. Inference** | Counter-prior catalogue (`docs/counter-priors/`), agent instructions, `knowledge counter_prior` MCP op, bootstrap briefing. | Source idea's "Layer 2: convention library" extends this — adds `dazzle.result` / `dazzle.types` and `docs/conventions/` referenced from agent instructions. |
| **3. Filter** | Drift gates, conformance, fitness, Sentinel, RBAC matrix, `dazzle validate/lint`. | Source idea's "Layer 1: bundled tooling" and "Layer 3: AST detectors" both live here, applied at the user-app boundary. |

The substrate audit (written earlier the same day) identifies exactly four pathologies still 🟡 partial at the user-app boundary: #5 mutable state, #6 try/catch as control flow, #7 magic strings, #8 N+1 in user code. The source idea targets these directly.

**Decision:** treat this as filling user-app Python gaps inside the existing substrate. No re-layering, no parallel taxonomy.

## 3. What already exists

A blunt audit, because the work is much smaller than the source idea implies:

### Already in place

- **Counter-prior catalogue** at `docs/counter-priors/` with 13 entries, YAML frontmatter, drift test (`tests/unit/test_counter_priors_drift.py`), KG ingestion at seed time, and the `knowledge counter_prior` MCP operation. **This is the "antipattern catalogue" the source idea proposes building.** Several pilot-candidate entries already exist: `exceptions-as-control-flow`, `polymorphic-associations`, `n-plus-one-in-user-code`, `raw-sql-string-building`, `stringly-typed-refs`, `shell-without-strict-mode`.
- **PythonAuditAgent (`PA`)** at `src/dazzle/sentinel/agents/python_audit.py` — a three-layer detection agent (Ruff profile + Semgrep rulesets + `@heuristic` methods) targeting "LLM training-bias patterns in user project code." Currently runs 5 heuristics (PA-LLM-01 through PA-LLM-06, ecosystem hygiene only). The `@heuristic` decorator pattern is the AST-detector contract the source idea calls for.
- **Sentinel finding model** (`src/dazzle/sentinel/models.py`) with `Severity`, `Confidence`, `Evidence`, `Remediation` — already structured for agent consumption.
- **Sentinel CLI/MCP** — `dazzle sentinel scan/suppress` CLI, `sentinel findings/status/history` MCP operations. **The agent feedback loop the source idea describes is already there.**
- **Test pin** `tests/unit/test_no_bare_except_pass.py` already enforces one narrow shape of the exceptions-as-control-flow antipattern at the framework-source level.

### Genuinely missing

- **No heuristics yet for the four user-app gaps** (#5-#8). PythonAuditAgent's current heuristics cover ecosystem hygiene, not the behavioural antipatterns the source idea catalogues.
- **No strict Ruff/Pyright defaults shipped to scaffolded projects.** `init_project` in `src/dazzle/core/init_impl.py` doesn't emit a `pyproject.toml` or `pyrightconfig.json` with the source idea's rule set.
- **No `dazzle.result` / `dazzle.types` convention library** exposed at the framework's import surface. Counter-prior entries reference the concept but there's no shipped helper.
- **No structured link between counter-prior catalogue entries and Sentinel heuristic IDs.** A counter-prior entry like `exceptions-as-control-flow.md` does not currently declare which detector (if any) enforces it; conversely, a heuristic's findings do not link back to the catalogue entry. Closing this loop is what makes the agent feedback "structured and actionable" per the source idea's §7.4.

## 4. Scope of this design — vertical slice

A single gap, end-to-end, through every relevant layer. The point is to prove the pipeline and establish the **catalogue-entry ↔ heuristic-ID ↔ scaffolding-rule** wiring once, so subsequent gaps cost only the per-gap detection logic.

**Pilot gap:** `exceptions-as-control-flow`. Chosen because:
- Counter-prior catalogue entry already exists and documents the four canonical wrong shapes.
- Ruff's `TRY`, `BLE`, and `B006` rule families already cover part of it — proves the multi-layer stack pulls weight together.
- Existing `test_no_bare_except_pass.py` proves the policy-gate pattern at framework level — the new work extends that discipline to user `app/` code.
- AST detection is well-defined: catch types in the trivial-precheck set (`KeyError`, `ValueError`, `AttributeError`, `IndexError`) combined with `pass` / `return None` / log-without-raise bodies. Low false-positive risk because re-raising or specific recovery is detectable.

**Out of scope for this slice:**
- Other counter-prior gaps (#5, #7, #8). They use the same wiring once the slice is in place.
- Framework-source enforcement. The existing `test_no_bare_except_pass.py` continues to handle that; user-app enforcement is the new layer.
- JavaScript / TypeScript detectors. The source idea's §10.1 open question; we stabilise Python first.
- Telemetry aggregation across projects (source idea §10.3). Per-project firing counts only.

## 5. Components

### 5.1 Heuristic addition to PythonAuditAgent

New `@heuristic` method `check_exceptions_as_control_flow` in `src/dazzle/sentinel/agents/python_audit.py`. Detects the four canonical wrong shapes from the catalogue entry:

1. **Silent swallow** — `except` (bare or with `Exception`) whose body is `pass`.
2. **Fallback control flow** — `try/except` where the `except` body is `var = <literal>` or `return <literal>`, mirror-shaped against the `try` body's assignment to the same name.
3. **Validation via exception** — `try: int(s); ... except ValueError: ...` and equivalents (`float`, `Decimal`, etc.).
4. **Try-as-conditional** — `try: x = d[k]; except KeyError: ...`, `try: x = obj.attr; except AttributeError: ...`, `try: x = seq[i]; except IndexError: ...` — where a trivial precheck (`d.get(k)`, `getattr(obj, "attr", None)`, length check) exists.

Heuristic ID: `PA-LLM-07`. Severity: `MEDIUM` (CONFIRMED confidence for shapes 1 and 4, LIKELY for shapes 2 and 3).

The heuristic walks AST of every `.py` file under `app/` in the user project. Framework code (`src/dazzle/`, `tests/`) is excluded — that surface remains under the existing `test_no_bare_except_pass.py` discipline.

### 5.2 Catalogue ↔ heuristic wiring

Extend the counter-prior frontmatter schema with a new optional field:

```yaml
detectors:
  - id: PA-LLM-07
    agent: PA
    note: covers shapes 1, 3, 4 fully; shape 2 (fallback control flow) heuristic only.
```

Drift test (`tests/unit/test_counter_priors_drift.py`) extended to assert: every declared `detectors[].id` resolves to a `@heuristic` decorator's `heuristic_id` in the codebase, and vice-versa (every Sentinel heuristic that targets a catalogued pattern declares its catalogue entry). The drift test becomes the contract between the two artefacts.

The `Finding` model gains an optional `catalogue_entry: str | None` field (kebab-case identifier matching `docs/counter-priors/<id>.md`). The `Remediation.references` list is extended on every quality finding to include the canonical catalogue URL.

### 5.3 Project scaffolding

`src/dazzle/core/init_impl.py::init_project` extended to write three new files when scaffolding a project:

- **`pyproject.toml`** — strict Ruff config (`select` list per source idea §5, with rationale comment), `target-version = "py312"`, per-file ignores for `tests/` (`S101`) and `scripts/` (`T201`). If the file already exists, the scaffolder writes only the `[tool.ruff]`, `[tool.ruff.lint]`, and `[tool.ruff.lint.per-file-ignores]` tables, replacing them wholesale; all other tables in the file are left untouched. The Dazzle-managed tables are marked with a header comment `# managed-by: dazzle quality bootstrap` so users can identify what the scaffolder owns.
- **`pyrightconfig.json`** — `typeCheckingMode: strict` with the source-idea's strict-mode overrides.
- **`.pre-commit-config.yaml`** — Ruff hook + ruff-format hook + local hook for `dazzle sentinel scan --agent PA` (so scaffolded projects run quality checks pre-commit).

For existing projects (non-scaffolded), a new command `dazzle quality bootstrap` writes the same three files with the same merge-without-overwrite semantics. **This is distinct from the existing `dazzle quality init`** which scaffolds `.claude/commands/`; the two are complementary and the help text is updated to disambiguate.

### 5.4 Convention library (deferred to round 2)

`dazzle.result` and `dazzle.types` from source idea §6 are **not** part of this slice. Justification: shipping them requires the corresponding detector slice (`optional-instead-of-result`) to pull weight, and bundling that with the pilot doubles the surface area. The exceptions-as-control-flow pilot doesn't need the convention library to land. Round 2 adds both together.

The catalogue entry pattern is the round-2 entry point: when we add the `optional-instead-of-result.md` counter-prior in round 2, we ship `dazzle.result` alongside it.

### 5.5 Agent feedback format

No new format. The existing `sentinel findings` MCP op output is consumed by the agent and already returns structured `Finding` records with `severity`, `evidence`, `remediation`, and `agent_hint`-like prose in `Remediation.guidance`. The only change is that quality findings now carry `catalogue_entry` and reference URL, so the agent can fetch the full antipattern document on demand via the existing knowledge graph (`knowledge counter_prior id=exceptions-as-control-flow`).

## 6. Data flow

```
User-authored Python in app/
            │
            ▼
  dazzle sentinel scan
            │
            ▼
  PythonAuditAgent.run(appspec)
            │
            ├── Layer 1: Ruff profile (TRY, BLE, B006, …)
            ├── Layer 2: Semgrep rulesets
            └── Layer 3: @heuristic methods
                    ├── PA-LLM-01 … PA-LLM-06 (existing)
                    └── PA-LLM-07 exceptions-as-control-flow (new)
                                │
                                ▼
                       Finding(catalogue_entry="exceptions-as-control-flow",
                               remediation=Remediation(references=[<url>], …))
            │
            ▼
  Sentinel store
            │
            ├── CLI: dazzle sentinel scan → text/JSON
            ├── MCP: sentinel findings → agent on next iteration
            └── Pre-commit hook: blocks commit on HIGH/CRITICAL
```

The agent feedback loop is closed by the agent re-reading `sentinel findings` (or having them surfaced by the harness) on its next iteration — same shape as it consumes any other Sentinel finding today.

## 7. Failure semantics and overrides

- **Default severity:** `MEDIUM`. Findings surface as warnings, not commit blockers, in this first slice. Promotion to `HIGH` (commit-blocker) requires a backfill audit demonstrating zero false positives across existing example apps and at least one external Dazzle consumer's codebase.
- **Per-finding suppression** uses the existing `dazzle sentinel suppress <finding-id>` mechanism with mandatory `--reason` justification. No silent ignore.
- **File-level suppression** (e.g. a script that genuinely needs broad-except handling at a boundary) uses Ruff-style `# noqa: PA-LLM-07 — <reason>` comments. The heuristic checks for this comment on the line directly above the `try` statement.
- **No silent rule-weakening at the project level.** If a project wants to disable `PA-LLM-07` entirely it must add the rule ID to a documented `[tool.dazzle.sentinel.suppress]` array in `pyproject.toml`, surfaced in `dazzle sentinel scan --report-suppressions`.

## 8. Testing

Three test surfaces:

1. **Unit tests for the heuristic** — `tests/unit/test_python_audit_exceptions.py`. Positive cases (one per canonical wrong shape, with expected findings). Negative cases (re-raise, specific recovery, type-narrowing-via-except, exception types outside the trivial-precheck list). Boundary cases (nested try, multiple except clauses, try with both `else` and `finally`).
2. **Catalogue-detector drift test** — extend `tests/unit/test_counter_priors_drift.py` to assert the bidirectional contract between catalogue entries and heuristic IDs.
3. **Scaffolding test** — `tests/unit/test_init_project_scaffolding.py` asserts that `init_project` writes the three files with expected content, and that `dazzle quality bootstrap` is a no-op on a project that already has them.

Smoke gate on real example apps: `dazzle sentinel scan --agent PA` runs as part of CI on each example in `examples/`. False positives become a release-blocker until the heuristic is tightened.

## 9. What this slice does not commit us to

- **The full source-idea catalogue.** This slice ships one heuristic and the wiring. Subsequent gaps reuse the wiring at one heuristic-method's worth of cost each.
- **A `dazzle.result` convention library.** Round 2. Documented as a deliberate deferral above.
- **Telemetry across projects.** The source idea's §8 measurement framing depends on cross-project aggregation that we are not building.
- **Hard-blocking agent commits.** First slice ships warnings. Promotion to commit-blocker is a separate decision after backfill.
- **Re-layering of the existing substrate taxonomy.** The Grammar/Inference/Filter framing in the substrate audit stands. The source idea's three-layer numbering is reframed as "extension to existing Layer 2 and Layer 3 at the user-app boundary."

## 10. Implementation order

Five steps, roughly in size order:

1. Add `catalogue_entry: str | None` to `Finding` and propagate through Sentinel store / MCP responses.
2. Extend counter-prior frontmatter schema with optional `detectors:` array; extend drift test for the bidirectional contract.
3. Implement `PA-LLM-07` heuristic with the four wrong-shape detectors + unit tests.
4. Extend `init_project` to ship `pyproject.toml` / `pyrightconfig.json` / `.pre-commit-config.yaml`; add `dazzle quality bootstrap` for existing projects.
5. Wire `PA-LLM-07` into CI for example apps; document the new heuristic in CHANGELOG with an Agent Guidance entry.

Estimated effort: 2-3 days of focused work, one PR per step or one bundled PR depending on review preference.

## 11. Open questions for the user

1. **Bundled vs. split PRs.** Steps 1-5 above can ship as one PR or five. The catalogue-detector wiring (steps 1-2) is the load-bearing part; if it splits cleanly I lean toward two PRs (wiring + first detector + scaffolding). Your call.
2. **Pre-commit hook in scaffolded projects.** Source idea §5.3 ships `.pre-commit-config.yaml`. This adds a dependency surface for downstream Dazzle users. Confirm we want this, or whether scaffolded projects should opt-in via a flag.
3. **Round-2 gap order.** After exceptions-as-control-flow, the natural next gap is either `optional-instead-of-result` (forces the `dazzle.result` convention library — biggest payoff) or `n-plus-one-in-user-code` (already catalogued, no new convention library needed — cheapest follow-on). I lean toward `n-plus-one-in-user-code` next for cheapest delta, then `optional-instead-of-result` with the convention library as round 3. Confirmable in a follow-up.
