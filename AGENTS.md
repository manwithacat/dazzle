# AGENTS.md

Canonical repository instructions for ALL coding agents (any harness). Drift-gated by
`tests/unit/test_docs_drift.py`, `tests/unit/test_agent_asset_gates.py` and
`tests/unit/test_documented_commands.py`; the version footer is maintained by the bump workflow. Harness adapters
(`.claude/CLAUDE.md`, `.github/copilot-instructions.md`) stay thin — project facts live
only here. This file is always-on context: it carries judgement, commands and gates.
Reference material lives in `docs/` and is pointed to, not copied.

## Epistemic layout (reconstruct first)

**Stems** are the small conceptual structures that regenerate Dazzle judgement.
Open them before inventing architecture.
Practice note: [`docs/architecture/epistemic-engineering-practice.md`](docs/architecture/epistemic-engineering-practice.md).

| Rank | Location | Role |
|------|----------|------|
| 1 | **[`stems/`](stems/INDEX.md)** | Framework stems (compressed judgement) |
| 2 | **This file** | Always-on didactics + commands |
| 3 | **`docs/adr/`** | Decision history (expressions of stems) |
| 4 | **`docs/decisions/`** | Deferred Decisions — parked plans + force reopen |
| 5 | **`docs/counter-priors/`** | Corpus pathologies (negative space) |
| 6 | **Package stems** | e.g. `packages/hatchi-maxchi/stems/` |
| 7 | **Example / app stems** | `examples/<app>/stems/` — domain judgement |
| 8 | Guides / reference + gates | Mechanics; dual-locks / ship-surface / prove |

**Curriculum:** `stems/INDEX.md` → matching stem → this file's commands → ADR if
constitutional → DD if `future`/parked residual → counter-prior/prove if the design
smells like a known failure → local code. HaTchi-MaXchi: also
`packages/hatchi-maxchi/AGENTS.md`. Do **not** treat every Markdown file as equal weight.

## Project Overview

**DAZZLE** — DSL-first toolkit for building apps from high-level specifications.

```
DSL Files → Parser → IR (AppSpec) → Dazzle Runtime (live app)
                                  → Code Generation (optional)
```

```bash
cd examples/simple_task && dazzle serve
# UI: http://localhost:3000 | API: http://localhost:8000/docs
```

## Architecture

| Directory | Purpose |
|-----------|---------|
| **`stems/`** | **Framework epistemic stems** — reconstruct judgement here first |
| `src/dazzle/core/` | Parser, IR, linker, validation |
| `src/dazzle/agent/` | Generic mission-driven agent framework |
| `src/dazzle/mcp/` | MCP server, knowledge graph, semantics KB |
| `src/dazzle/cli/` | CLI commands (`dazzle serve`, `dazzle mcp`, etc.) |
| `src/dazzle/lsp/` | LSP server (diagnostics, hover, completion) |
| `src/dazzle/specs/` | OpenAPI and AsyncAPI specification generators |
| `src/dazzle/compliance/` | Compliance pipeline — ISO 27001 + SOC 2 evidence extraction, taxonomy, compiler |
| `src/dazzle/rbac/` | Provable RBAC — static matrix, dynamic verification, audit trail, compliance report |
| `src/dazzle/testing/` | Test infrastructure (agent E2E wrapper, browser gate) |
| `src/dazzle/http/` | **HTTP runtime** (FastAPI: API, auth, channels, events, grants). Renamed from `back/` in ADR-0041 |
| `src/dazzle/page/` | **Page-orchestration layer** — page/route renderers (`*_renderer.py`), converters, static JS/CSS, residual product glue (CSRF, toast host, analytics, capability islands). Calls *down* into `render/`. **Not** a second component library — user-visible chrome stranded here is **promoted** to Hyperparts. No Jinja2 since #1042 (ADR-0023). Was `ui/` / `dazzle_ui` pre-ADR-0041; those paths are dead |
| `src/dazzle/render/` | Pure rendering: AppSpec → Fragment → HTML, no I/O. The four-layer stack is `http → page → render → core` (ADR-0038/0041) |
| `packages/hatchi-maxchi/` | **Frontend design system** (Hyperparts, dual-locks, component CSS/controllers, gallery). Own `stems/` + `AGENTS.md`. Pages compose Hyperparts from the gallery; novel UX is invented *inside* HM shapes (ADR-0053 / #1585). Standalone CI must stay green — the Dazzle job **HaTchi-MaXchi standalone CI (mirror)** (`scripts/hm_standalone_ci_status.py`) fails Dazzle transitively on a red HM main |
| `examples/*/` | Apps; each carries `stems/` for domain judgement |

**Project layout for user apps** (not the framework): production code in `app/<category>/`
(`app/sync/`, `app/render/`, `app/db/`), one-shot scripts in `scripts/`, no flat dumping
grounds — `docs/reference/project-layout.md`.

## Style Guide

- **Type hints required** on all public functions (enforced by mypy)
- **Pydantic models** for data crossing module boundaries
- **Explicit dependencies** — no hidden globals or singletons (ADR-0005)
- **No backward compat shims** — clean breaks, update all callers in same commit (ADR-0003)
- Prefer explicit over magic; keep functions small and single-purpose
- Data shapes in dedicated files (`models.py`)
- Never edit auto-generated files (marked with `# AUTO-GENERATED`)

## Authoring vs API Boundary (#1222)

**Dazzle structural authoring stays in the agent session.** The MCP, KG, parser, IR types
and examples assume an in-session agent does DSL synthesis with full Dazzle context.

- ✅ Delegate to an API: domain-neutral structural extraction (SPEC.md → entities/personas/
  rules), language tasks (summarise, translate, classify) — anything whose output is *data*.
- ❌ Never delegate: authoring or modifying `.dsl` files, IR types, parser dispatchers,
  schema migrations, examples, fixtures. Warning sign: an LLM call that *writes* DSL.

## Counter-Prior Catalogue

Before emitting non-trivial user-app code (Python in `app/`, raw SQL, shell), call
`knowledge counter_prior code_shape="<one-sentence description>"` to check
`docs/counter-priors/` for matching pathologies (exceptions-as-control-flow, n+1, raw-sql,
shell-strict, polymorphic-associations, …); `query="<excerpt>"` for spec-driven structural
choices. Full list: `docs/counter-priors/INDEX.md`.

## Model-Driven Failure Modes (review rule)

`docs/architecture/model-driven-failure-modes.md` catalogues the 14 historical 4GL/MDE/CASE
failure modes Dazzle is exposed to. Before selling a new DSL construct, runtime subsystem,
escape hatch or QA harness as a safe pattern, answer: (1) which failure mode does this risk
increasing? (2) which detector dimension catches it? (3) is that detector *live* in the
normal workflow? (4) can an engineer trace runtime behaviour back to DSL/AppSpec? (5) does
the abstraction preserve Postgres/auth/workflow/UI semantics, or push them into side code?
Unanswered → the change carries an explicit risk note and is not marketed as a pattern.

## Commands

### Dev Setup
```bash
# uv is the only supported local toolchain (same as Heroku's uv buildpack).
# .python-version pins primary Python 3.14; [tool.uv] python-preference = only-managed.
make dev-install              # uv python install + uv sync (full local extras) + pre-commit
# or: uv sync --extra dev --extra llm --extra mcp …
```
**Do not use pyenv or `pip install -e` for this repo.** After changing deps in
`pyproject.toml`, run `uv lock` and commit the updated `uv.lock` in the same change —
CI syncs with `--frozen` and fails on lock drift. A uv `.venv` has no `pip`; use
`uv pip install <tool>` for one-off tooling. pre-commit runs via `uvx pre-commit`.
Details: `docs/contributing/dev-setup.md`. Binary floor + remedies:
`docs/harness/tool-floor.md`; probe: `uv run python scripts/improve_toolchain.py --status`.

```bash
# Run app (against your own Postgres + Redis via DATABASE_URL / REDIS_URL)
uv run dazzle serve

# Validate / lint DSL. The framework repo root is NOT a Dazzle project — pass -p.
uv run dazzle validate -p examples/simple_task   # Parse and validate DSL
uv run dazzle lint -p examples/simple_task       # Extended checks

# Test
make test-fast                # pytest tests/ -x -q --ignore=tests/integration/ -m "not slow"
uv run pytest -n auto --dist loadgroup -m "not e2e"   # full suite (~2 min; per-worker Postgres DBs when TEST_DATABASE_URL is set)
uv run pytest tests/ -m e2e

# Lint / types
make lint format              # or: uv run ruff … / uv run mypy src/dazzle

# Find a command
uv run dazzle search <keyword>
```

Full CLI reference: `docs/reference/cli.md`. API specs: `dazzle specs openapi|asyncapi`.
Inspect extension points and public surface: `dazzle inspect <renderers|primitives|routes|page <URL>|oauth-providers|db-artifacts|api <baseline>>`
(manifest-only by default, `--runtime` boots the app; `docs/reference/page-inspection.md`).
LSP: `dazzle lsp run|check|grammar-path`. Ratchet baselines: `dazzle fitness code|clones --write-baseline`.

## DSL Quick Reference

```dsl
module my_app
app todo "Todo App"

entity Task "Task":
  id: uuid pk
  title: str(200) required
  completed: bool=false

surface task_list "Tasks":
  uses entity Task
  mode: list
  section main:
    field title "Title"
    field completed "Done"
```

**Constructs**: `entity`, `surface`, `workspace`, `experience`, `island`, `service`, `foreign_model`, `integration`, `ledger`, `transaction`, `process`, `schedule`, `story`, `archetype`, `persona`, `scenario`, `enum`, `webhook`, `ingest`, `approval`, `sla`, `rhythm`, `feedback_widget`, `subprocessor`, `analytics`, `guide`, `atomic`

*(User-facing subset. The parser also dispatches on `app`, `test`, `flow`, `rule`, `message`, `channel`, `asset`, `document`, `template`, `demo`, `event_model`, `subscribe`, `projection`, `stream`, `hless`, `policies`, `tenancy`, `interfaces`, `data_products`, `llm_model`, `llm_config`, `llm_intent`, `notification`, `job`, `audit`, `search`, `grant_schema`, `param`, `question`. Drift-gated: every name listed must exist in the parser.)*

**On `hless`** (High-Level Event Semantics Specification): a deliberate break from
Kafka vocabulary; **don't propose renaming it** (rejected, #1069 API-003) —
`docs/architecture/hless-deep-dive.md`.

**Scope rules** compile to a predicate algebra statically validated against the FK graph
at `dazzle validate` time. Each `scope:` rule needs a matching `permit:` rule and an `as:`
clause naming the personas (`as:` replaced `for:` in #998). The supported forms (direct,
FK path, EXISTS / NOT EXISTS, negation, boolean, polymorphic `subject[Type]` selectors) and
their pitfalls live in the **dsl-authoring** skill; verify any scope with
`dazzle db explain-scope <Entity> <verb>`.

## Extending

### Adding DSL Constructs
1. Update grammar in `docs/reference/grammar.md`
2. Add IR types in `src/dazzle/core/ir/`
3. Implement parser mixin in `src/dazzle/core/dsl_parser_impl/`
4. Add tests in `tests/unit/test_parser.py`

### Public API surface (#961)
Five committed baselines under `docs/api-surface/` (`dsl-constructs`, `ir-types`,
`mcp-tools`, `public-helpers`, `runtime-urls`) pin the framework's public API; drift gate
`tests/unit/test_api_surface_drift.py`. `dazzle inspect api <name> --diff` shows the
diff, `--write` regenerates. Any drift requires a CHANGELOG entry.

## Examples

Working Dazzle apps in `examples/`: `simple_task`, `contact_manager`, `support_tickets`, `ops_dashboard`, `fieldtest_hub`, `project_tracker`, `design_studio`, `llm_ticket_classifier`, `acme_billing`, `hr_records`, `invoice_ops`, `domain_join_co`

Framework-validation fixtures in `fixtures/` (not user-facing apps — abstract probes used only by `tests/`): `shapes_validation`, `rbac_validation`, `investigator_smoke`, `asset_registry`, `shared_parent_aggregate`, `signing_validation`, `tenant_rls`, `transition_atomic`, `scope_runtime`, `pra`, `custom_renderer`, `component_showcase`, `tenant_hierarchy` (FK-path/EXISTS create-scope #1311 + update-destination #1312 verified against real Postgres via `tests/integration/test_scope_runtime_pg.py`; `pra` = parser-conformance corpus, `custom_renderer` = renderer-extension demo, `component_showcase` = component gallery — reclassified from examples/ 2026-06-13; `tenant_hierarchy` = ADR-0036/0037 hierarchy + membership worked example)

Both lists are drift-gated against the directory trees — adding or removing an
example/fixture requires updating the matching line here.

**Examples are framework probes, not list-first CRUD.** Read
`stems/example-apps-as-probes.md` before changing an example's job screen; map persona
jobs → workspace Hyperparts via `docs/guides/story-to-composition.md` (prefer
`display: queue` / `metrics` / `status_list` for open work).

## MCP / CLI Boundary

MCP = fast knowledge/query (prefer no side effects); CLI = process, writes, long work
(ADR-0002). Protocol is **stateless** (SDK v2 / 2026-07-28); app state is explicit handles
(project root), not transport sessions.

- **MCP tools**: the client loads the live tool schemas; the generated inventory with every
  operation and parameter is `docs/reference/mcp-tools.md` (`dazzle docs generate`), and
  the surface is drift-gated by the `mcp-tools` API baseline. `bootstrap` is the entry
  point for "build me an app"; `knowledge` (concept, examples, cli_help, workflow,
  counter_prior, search_commands) is the fastest orientation call.
- **CLI process groups**: `discovery`, `e2e`, `story`, `rhythm`, `process`, `test-design`,
  `test`, `pulse`, `sentinel`, `db`, `tenant`, `demo`, `api-pack`, `mock`,
  `test`, `pitch`, `sentinel`, `db`, `tenant`, `demo`, `api-pack`, `mock` —
  `dazzle <group> --help` or `dazzle search <keyword>`.

## Autonomous Loops (awareness)

- The **issues loop** (`.agents/skills/issues/SKILL.md`) runs on consumer force only.
- The cross-app **fuzz sweep** (`.agents/skills/fuzz/SKILL.md`) stays.
- ANY agent that pushes to `main` honours `.dazzle/improve.lock` (15-min TTL) and Ship Discipline below.

## Deferred decisions (long-horizon plans)

When you park work as "not yet / consumer-forced / future", write or update a
**Deferred Decision** under `docs/decisions/` (template `TEMPLATE.md`, row in `INDEX.md`,
`status: PARKED`, **Plan** / **Reopen when** / **Already shipped** / **Out of scope**),
pin the DD path in the issue body, and link it from any related stem **Expressions**.
The issues loop must **not** implement `PARKED` DDs or `future`-labeled issues until
`status: FORCED` with a named consumer. When the consumer appears: `FORCED` → implement
*that* plan → `DONE`. Grep: `rg -n '^status: PARKED' docs/decisions/`.
Example: [DD-001](docs/decisions/DD-001-1617-poly-ref-and-sti-eav.md) for #1621/#1622.

## Specialised references (read before touching the area)

| Area | Read first | Gate |
|------|-----------|------|
| Chart / report regions (`bar_chart`, `pivot_table`, `heatmap`, `funnel_chart`, `metrics`) | `docs/reference/reports.md` — display-mode per cardinality, fast vs slow path, scope-safety, `dazzle db explain-aggregate` | one scope-aware `GROUP BY` per region, never N+1 |
| Per-persona onboarding `guide` overlays | `docs/reference/guides.md` | `tests/unit/test_example_guide_bar.py`; `dazzle ux verify --guides`; declaring guides adds `OnboardingState` to RBAC + compliance evidence — regenerate `expected/` |
| Writing / editing `.dsl` | **dsl-authoring** skill; `docs/reference/grammar.md` | `dazzle validate` / `dazzle lint` |
| PyPI | package `dazzle-dsl`, import name `dazzle`, console command `dazzle` | — |

## Architectural Decisions

See `docs/adr/INDEX.md` for the full index. Key constraints:
- **No new singletons** — use `RuntimeServices` or `ServerState` (ADR-0005)
- **No SQLite in the app runtime** — `src/dazzle/http/` is PostgreSQL-only (ADR-0008). The MCP server's knowledge-graph DB and `core/process/version_manager.py` are outside that scope and may use SQLite.
- **No SPA frameworks** — server-side rendering + HTMX (ADR-0011); rendering is the typed Fragment substrate since #1042 (ADR-0023), not Jinja2
- **No field conditions in `permit:`** — use `scope:` with `as:` (ADR-0010)
- **No `from __future__ import annotations`** in FastAPI route files (ADR-0014)
- **All schema changes via Alembic** — including framework entities. No raw ALTER TABLE. `dazzle db revision -m "description"` then `dazzle db upgrade` (ADR-0017)
- **DB artifacts have one registry** — before adding a framework table, boot-DDL, or RLS, read `docs/reference/db-artifacts.md` or run `dazzle inspect db-artifacts`. `dazzle.db.artifact_registry` is the source of truth; `tests/unit/test_db_artifact_contract.py` enforces boot-entry gating (the #1495 class) and `IN_SCOPE_TABLES` is registry-derived (ADR-0047)

## Ship Discipline

- **Clean worktree**: Every push must leave `git status` clean. After shipping, check for untracked or modified files (especially `dist/`) and commit them before moving on.
- **Bump on human-initiated ships, not on autonomous loop cycles**: `/bump` + `/ship` tag a defined change a person asked for. An autonomous loop commits on `main` **without** bump or tag.
- **Local CI tiers (concordance)** — laptop green ≠ GitHub badge. Canonical doc:
  `docs/contributing/local-ci-concordance.md`. Shared runner: `scripts/ci_local.sh`.
  | Habit | Command | When |
  |-------|---------|------|
  | Structural debt | `make preflight-surface` | Always before ship (also first step of ci-fast/ci-core) |
  | Recurrent badge-red pack | `make ship-surface` | Always in Tier 0 — bandit + SPEC/IR/viewport pack |
  | Path-aware mid-edit | `make ci-changed` | After touching examples DSL, shell/viewport, KB, or `src/` — not a ship substitute |
  | Default ship gate | `make ci-fast` | Every `/ship` (preflight + ship-surface + ruff + mypy + gate + docs); writes push stamp |
  | Push allow/deny | `make push-gate` | **Before every `git push`** — stamp match + ≤4 commits/h + CI not in_progress + HM plane |
  | Release / version bump | `make ci-core` | Before tags / when operator wants GitHub-core concordance |
  | HM visual ship / tag | `push_gate check --require-hm-green` | Sibling hatchi-maxchi CI must be green for gallery CSS/JS baselines |
  | Badge red | `/cimonitor` | Fix **and** promote the failure class into ship-surface/preflight |
  Do **not** ship on ad-hoc pytest alone. **Do not** `git push` while main CI is still
  `in_progress` (cancel storm) — wait, or `push_gate check --repair` only for cimonitor.
- **Agent Guidance in CHANGELOG**: When a release introduces new patterns, conventions, ADRs, or breaking changes that affect how agents work, add a `### Agent Guidance` section to that version's entry — one bullet per topic, the rule and where to look.
- **Commit attribution (read before `git commit`)**:
  - **Author / Committer** must be the human account owner (`James Barlow` /
    `332269+manwithacat@users.noreply.github.com` via **global** git config). Do **not**
    set **local** `user.name` / `user.email` on this repo. Verify with
    `git var GIT_AUTHOR_IDENT` before the first ship in a session.
  - **Agent recognition** is the trailer only (`Co-Authored-By: …`) for the **acting**
    harness — concrete strings in **Capability Mapping** below. Do **not** rewrite
    published history to fix past mis-attributed commits unless the operator asks.

## Workflows

Reusable workflows live in `.agents/skills/<name>/SKILL.md` (open-standard format, any harness):

- **ship** — Commit, verify, tag, and push via Tier 0 (`make ci-fast`) or Tier 1 (`make ci-core` for version bumps); never ad-hoc pytest-only
- **check** — On-demand quality gate on modified files; prefers `make ci-changed` path packs + full unit when Python changed
- **bump** — Bump the semantic version across all six canonical locations and update CHANGELOG
- **cimonitor** — Snapshot/repair the main CI badge; after repair, promote new failure classes into `ship-surface` / `preflight-surface`
- **semgrep** — Diff-scoped Semgrep (python/owasp/audit) + optional Sentinel modernisation; CLI SSOT via `scripts/semgrep_diff.py`
- **dsl-authoring** — Syntax rules, common mistakes and scope-rule forms for writing/editing Dazzle `.dsl` files
- **qa-trial** — Author `trial.toml` scenarios that evaluate a Dazzle app as a real business user
- **stems** — Reconstruct framework/package/app judgement from `stems/` before inventing structure
- **issues** — Consumer-forced issue triage and resolution loop
- **fuzz** — Cross-app boot and integration fuzz sweep

## Capability Mapping

Playbooks and skills in this repo are written in capability language. This table — the
only place in this file where vendor names may appear — maps each capability to concrete
harness features. *degrade* = follow the playbook sequentially and note the degradation.

| Capability | Generic instruction | Claude Code | Codex CLI | Grok Build |
|---|---|---|---|---|
| ask-user-choice | present 2–4 mutually-exclusive options and wait | AskUserQuestion tool | inline prompt | inline prompt |
| task-list | maintain a visible task list for multi-step work | TaskCreate/TaskUpdate | plan mode | plan mode |
| subagent-dispatch | delegate a scoped task to a fresh agent | Agent tool | subtask/spawn if available, else *degrade* | subAgents config |
| parallel-investigation | run independent investigations concurrently | background Agent tool | *degrade* (sequential) | subagents |
| scheduled-loop | re-run a playbook on a cadence | /loop + session cron | external scheduler (CI cron) | headless CI mode |
| web-search | consult current docs when knowledge may be stale | WebSearch tool | built-in browse | built-in search |
| model-tiering | mechanical work → cheapest tier; ship-level judgement → strong tier; review + ship path → session tier | host model selection | single model — n/a | per-subagent model field |
| commit-trailer | `Co-Authored-By` for the acting harness only; human stays Author | `Co-Authored-By: Claude <noreply@anthropic.com>` (a model-versioned form such as `Claude Fable 5.1` is acceptable) | (none standard) | `Co-Authored-By: Grok Build <grok@x.ai>` |

Model policy: mechanical work (lint, fixed-signature scrapes, format churn, reference
sweeps) runs on the cheapest tier; ship-level judgement (a flense ship, a bug fix prepared
in a worktree) runs on a strong tier below the session; final review and the ship path
(gates, commit, push) stay with the session tier. Portable playbooks never require a named
model. Harness-specific runtime notes (PATH, hooks, local services) live in the harness
adapter, not here.

## UI Invariants

- **Alpine.js is deprecated for new code** (ratified 2026-07-06). Client behaviour follows the HM Hyperpart idiom: delegated document-level vanilla controllers, state in the DOM, server-owned rendering. Never author `x-*` attributes — the vendored Alpine runtime was removed; client behaviour is HM delegated controllers + `dz-utils.js`.
- **Taste (HaTchi-MaXchi)**: the house aesthetic is `docs/reference/taste.md` (9 principles → TASTE-n rules → judged rubric). Read it before styling work in framework CSS. Blind parity gate `dazzle qa taste-panel`; rubric source `src/dazzle/core/taste_rubric.py` (drift-gated by `tests/unit/test_taste_doc_drift.py`).
- **Card safety**: any new region template, dashboard layout change, or fragment primitive must satisfy the 8 invariants in `docs/reference/card-safety-invariants.md`. Scanners in `src/dazzle/testing/ux/contract_checker.py`; composite gate `tests/unit/test_htmx_workspace_composite.py` runs on the stitched post-HTMX DOM. Regions emit zero chrome + zero title; the dashboard slot owns both.

## Test Authoring — Distillation Feedback Loop

Before adding non-trivial tests, consult `tests/audit/` (strategy:
`docs/proposals/Suite Distillation Strategy.md`; regeneration commands in
`docs/contributing/testing.md`):

- **`redundancy_report.md`** — if the file you're extending already carries a cluster matching your new test's assertion shape, extend the existing `@pytest.mark.parametrize` set instead of adding a standalone test. Cross-file: `cross_file_report.md`.
- **`taxonomy_report.md`** — don't add the flagged archetypes: implementation mirrors (importing private `_`-callables + heavy mocking) or tautologies. One behaviour = one test; count is cheap, attention-per-failure is not.

Tests that boot an app subprocess against a repo directory (not `tmp_path`) must carry
an `xdist_group` pin naming that directory's cohort.

## Gotchas

- **MCP test isolation**: Tests that mock `mcp.*` modules pollute `sys.modules`. The `tests/unit/conftest.py` 3-phase fixture handles this — don't bypass it.
- **PersonaSpec identity**: `.id`, not `.name` — call `spec_display_id(spec)` (`dazzle.core.ir.identity`), don't re-inline `getattr(p, "name", None) or getattr(p, "id", …)` (gated by `tests/unit/test_dedup_footgun_gates.py`).
- **State machine states**: Plain strings, not objects — call `StateMachineSpec.state_names()` or `state_name(s)` (`dazzle.core.ir.state_machine`), don't re-inline `s if isinstance(s, str) else s.name` (gated).
- **KG re-seeding**: `ensure_seeded()` checks a version key; bump it in `seed.py` when TOML data changes.

---
**Version**: 0.115.0 | **Python**: 3.12+ | **Status**: Production Ready
