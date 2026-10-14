# Flense inventory

> **Generated** by `scripts/flense_inventory.py` from `flense_consumers.toml` and the working tree.
> Do not edit; rerun the script. This table is the only admissible evidence for a keep or a
> removal under [ADR-0057](../adr/0057-consumer-forced-growth-and-mass-ratchet.md).

Snapshot: 2026-10-14. Consumers absent on this machine: none (absent means *unknown*, never *unused*).

**How to read.** DSL declarations are one signal among seven. Consumers also reach the
framework through CLI calls in scripts and docs, Python imports, `dazzle.toml` sections,
framework-read project files (`sitespec.yaml`, `pitchspec.yaml` ...), framework URLs in
app code and assets, and MCP tool use. A removal needs a zero in *every*
signal section below for *every* present consumer; `?` (absent consumer) is unknown,
never zero. The non-DSL scanners are text matches: they over-count rather than miss.

## Totals

| Measure | Value |
|---|---:|
| Framework source lines (`src/dazzle`) | 342,558 |
| Test lines (`tests/`) | 350,262 |
| Documentation lines (`docs/**/*.md`) | 47,259 |
| Top-level DSL constructs | 31 |
| Constructs with zero consumer use | 1 |

## Consumers

| Consumer | Domain | Present |
|---|---|---|
| AegisMark | state education — safeguarding, data protection, high-stakes formative marking | yes |
| cyfuture | accountancy — regulatory filings, KYC/AML, document signing | yes |
| pennydreadful | publishing — IP and authorship verification, royalties, rights auctions | yes |

## Top-level DSL constructs × consumers

Counts are top-level declarations in `.dsl` files.

| Construct | AegisMark | cyfuture | pennydreadful | examples | Disposition hint |
|---|---:|---:|---:|---:|---|
| `analytics` | 1 | 1 | 0 | 0 | consumer-used |
| `app` | 1 | 1 | 1 | 5 | consumer-used |
| `archetype` | 3 | 0 | 0 | 2 | consumer-used |
| `audit` | 0 | 0 | 0 | 2 | examples only |
| `entity` | 68 | 64 | 41 | 28 | consumer-used |
| `experience` | 0 | 2 | 3 | 0 | consumer-used |
| `feedback_widget` | 0 | 1 | 0 | 2 | consumer-used |
| `foreign_model` | 0 | 34 | 0 | 0 | consumer-used |
| `grant_schema` | 2 | 5 | 0 | 0 | consumer-used |
| `guide` | 0 | 2 | 2 | 13 | consumer-used |
| `integration` | 0 | 2 | 0 | 0 | consumer-used |
| `island` | 0 | 2 | 0 | 1 | consumer-used |
| `llm_config` | 1 | 0 | 1 | 2 | consumer-used |
| `llm_intent` | 5 | 0 | 6 | 8 | consumer-used |
| `llm_model` | 2 | 0 | 3 | 4 | consumer-used |
| `nav` | 10 | 6 | 5 | 17 | consumer-used |
| `param` | 5 | 32 | 0 | 0 | consumer-used |
| `persona` | 10 | 6 | 5 | 20 | consumer-used |
| `policies` | 1 | 0 | 0 | 0 | consumer-used |
| `process` | 0 | 1 | 0 | 9 | consumer-used |
| `rhythm` | 3 | 2 | 0 | 1 | consumer-used |
| `scenario` | 26 | 3 | 0 | 9 | consumer-used |
| `schedule` | 0 | 8 | 0 | 4 | consumer-used |
| `search` | 1 | 0 | 0 | 0 | consumer-used |
| `service` | 0 | 11 | 0 | 15 | consumer-used |
| `sla` | 0 | 8 | 0 | 1 | consumer-used |
| `story` | 62 | 214 | 16 | 45 | consumer-used |
| `subprocessor` | 4 | 0 | 0 | 0 | consumer-used |
| `surface` | 234 | 231 | 46 | 98 | consumer-used |
| `tenancy` | 1 | 1 | 0 | 2 | consumer-used |
| `workspace` | 32 | 7 | 4 | 35 | consumer-used |

**Zero consumer use:** `audit`

## Framework subpackages

Test lines are name-matched (`tests/**/test_*<subpackage>*.py`) — a floor, not a census.

| Subpackage | Source lines | Test lines (name-matched) |
|---|---:|---:|
| `http` | 101,201 | 649 |
| `core` | 74,662 | 2,050 |
| `render` | 29,168 | 5,984 |
| `mcp` | 25,938 | 5,090 |
| `cli` | 25,298 | 8,544 |
| `testing` | 23,388 | 68 |
| `page` | 12,910 | 2,501 |
| `agent` | 7,585 | 7,766 |
| `qa` | 7,368 | 3,129 |
| `sentinel` | 6,154 | 563 |
| `db` | 4,384 | 3,727 |
| `rbac` | 3,826 | 6,860 |
| `compliance` | 3,012 | 1,417 |
| `signing` | 2,143 | 1,969 |
| `demo_data` | 2,127 | 365 |
| `services` | 1,632 | 98 |
| `agent_loop` | 1,533 | 154 |
| `llm` | 1,307 | 2,537 |
| `perf` | 1,197 | 2,203 |
| `i18n` | 1,086 | 851 |
| `e2e` | 1,066 | 1,990 |
| `representation` | 1,023 | 279 |
| `api_surface` | 958 | 148 |
| `api_kb` | 677 | 552 |
| `conformance` | 660 | 3,034 |
| `examples` | 573 | 848 |
| `tenant` | 537 | 6,965 |
| `fitness` | 490 | 186 |
| `deploy` | 181 | 342 |
| `seed` | 126 | 1,357 |
| `docs_update` | 0 | 0 |
| `documents` | 0 | 0 |
| `domain_brief` | 0 | 0 |
| `layout` | 0 | 1,659 |
| `lsp` | 0 | 0 |
| `notifications` | 0 | 0 |
| `pitch` | 0 | 0 |
| `product_quality` | 0 | 0 |
| `quality` | 0 | 80 |
| `risk` | 0 | 171 |
| `spec_narrative` | 0 | 0 |
| `specs` | 0 | 144 |
| `stubs` | 0 | 0 |
| `templates` | 0 | 598 |

## MCP tools

| Tool | Operations |
|---|---:|
| `agent` | 3 |
| `bootstrap` | 0 |
| `compliance` | 5 |
| `conformance` | 4 |
| `db` | 2 |
| `discovery` | 1 |
| `dsl` | 10 |
| `feedback` | 4 |
| `guide` | 4 |
| `knowledge` | 9 |
| `policy` | 6 |
| `rhythm` | 3 |
| `semantics` | 5 |
| `sentinel` | 4 |
| `sitespec` | 14 |
| `spec_analyze` | 6 |
| `status` | 7 |
| `story` | 4 |

## CLI groups

`agent`, `analytics`, `auth`, `capability`, `compliance`, `db`, `demo`, `deploy`, `docs`, `fitness`, `inspect`, `mcp`, `perf`, `pipeline`, `prove`, `qa`, `rbac`, `representation`, `rhythm`, `scaffold`, `sentinel`, `signing`, `spec`, `story`, `tenant`, `test`, `ux`, `vocab`

## CLI groups × consumers

Occurrences of `dazzle <group>` (and bare top-level commands) in `Makefile`, `*.sh`, `*.yml`, `*.yaml`, `*.toml`, `*.md`, `*.py`, excluding `node_modules`, `.venv`, `.git`, `dev_docs/`, `archive/`, `.grok/`, `.dazzle/`, `__pycache__`. "Subcommands seen" is the next word after the group, so prose can add noise.

| CLI group / command | AegisMark | cyfuture | pennydreadful | examples | Subcommands seen |
|---|---:|---:|---:|---:|---|
| `agent` | 28 | 35 | 1 | 2 | `playbook`, `prove`, `seed`, `signals`, `sync`, `wall` |
| `analytics` | 0 | 0 | 0 | 0 |  |
| `auth` | 26 | 1 | 1 | 2 | `connection`, `create-user`, `impersonate`, `migrate` |
| `build` | 0 | 0 | 0 | 2 |  |
| `build-api` | 0 | 4 | 0 | 0 |  |
| `build-ui` | 0 | 0 | 0 | 1 |  |
| `capability` | 0 | 0 | 0 | 0 |  |
| `compliance` | 3 | 2 | 0 | 6 | `compile`, `privacy` |
| `coverage` | 1 | 0 | 0 | 0 |  |
| `db` | 136 | 27 | 83 | 8 | `apply-rls`, `baseline`, `current`, `downgrade`, `history`, `migrate`, `no`, `reconcile-baseline`, `revision`, `snapshot`, `snapshot-baseline`, `stamp`, `status`, `upgrade`, `verify` |
| `demo` | 3 | 0 | 2 | 0 | `ingest`, `load`, `validate` |
| `deploy` | 1 | 0 | 0 | 0 | `plan` |
| `docs` | 3 | 12 | 0 | 0 | `claims`, `guides`, `site` |
| `doctor` | 0 | 0 | 0 | 0 |  |
| `fitness` | 2 | 0 | 3 | 0 | `queue`, `triage`, `vitality` |
| `fragment-audit` | 0 | 0 | 0 | 0 |  |
| `grammar` | 0 | 0 | 0 | 0 |  |
| `init` | 0 | 0 | 0 | 1 |  |
| `inspect` | 1 | 0 | 3 | 0 | `renderers`, `rls` |
| `lint` | 29 | 14 | 29 | 0 |  |
| `mcp` | 0 | 0 | 0 | 0 |  |
| `migrate` | 2 | 3 | 0 | 0 |  |
| `perf` | 1 | 0 | 0 | 0 | `sweep` |
| `pipeline` | 83 | 41 | 0 | 0 | `run` |
| `prove` | 0 | 0 | 0 | 3 | `representation`, `story` |
| `qa` | 2 | 10 | 0 | 3 | `login`, `taste-panel`, `trial`, `trial-hypotheses` |
| `rbac` | 12 | 5 | 0 | 0 | `matrix`, `prove`, `routes` |
| `representation` | 0 | 0 | 0 | 0 |  |
| `rhythm` | 0 | 0 | 0 | 0 |  |
| `scaffold` | 1 | 1 | 0 | 1 |  |
| `search` | 0 | 0 | 0 | 0 |  |
| `sentinel` | 2 | 3 | 0 | 0 | `scan` |
| `serve` | 100 | 11 | 44 | 20 |  |
| `signing` | 1 | 0 | 0 | 0 | `init` |
| `spec` | 0 | 0 | 0 | 0 |  |
| `story` | 0 | 2 | 0 | 0 | `list` |
| `tenant` | 0 | 5 | 0 | 0 | `create` |
| `test` | 9 | 62 | 0 | 5 | `agent`, `coverage`, `create-sessions`, `diff-personas`, `dsl-run`, `generate`, `pack`, `populate`, `run`, `tier2-generate`, `verify-story`, `walk` |
| `ux` | 63 | 12 | 5 | 0 | `explore`, `maturity`, `verify` |
| `validate` | 46 | 129 | 89 | 12 |  |
| `version` | 0 | 0 | 0 | 0 |  |
| `vocab` | 0 | 0 | 0 | 16 | `expand`, `list`, `show` |

## Framework modules imported × consumers

`from dazzle.<a>[.<b>] import` / `import dazzle.<a>[.<b>]` in `*.py`, keyed by the first two levels. A module not listed is imported by nobody.

| Module | AegisMark | cyfuture | pennydreadful | examples |
|---|---:|---:|---:|---:|
| `dazzle` | 0 | 0 | 1 | 0 |
| `dazzle.api_kb.loader` | 0 | 2 | 0 | 0 |
| `dazzle.cli.db` | 1 | 0 | 0 | 0 |
| `dazzle.cli.services` | 10 | 0 | 0 | 0 |
| `dazzle.core` | 0 | 0 | 3 | 0 |
| `dazzle.core.access` | 1 | 0 | 0 | 0 |
| `dazzle.core.appspec_loader` | 4 | 3 | 2 | 0 |
| `dazzle.core.environment` | 2 | 0 | 0 | 0 |
| `dazzle.core.ir` | 9 | 5 | 0 | 0 |
| `dazzle.core.validator` | 1 | 0 | 0 | 0 |
| `dazzle.http` | 2 | 0 | 0 | 0 |
| `dazzle.http.runtime` | 78 | 160 | 9 | 0 |
| `dazzle.i18n.display_locale` | 0 | 2 | 0 | 0 |
| `dazzle.page.runtime` | 2 | 0 | 0 | 0 |
| `dazzle.page.themes` | 1 | 0 | 0 | 0 |
| `dazzle.rbac.matrix` | 1 | 0 | 0 | 0 |
| `dazzle.render` | 0 | 1 | 0 | 0 |
| `dazzle.render.context` | 0 | 1 | 4 | 0 |
| `dazzle.render.dispatch` | 0 | 0 | 1 | 0 |
| `dazzle.render.fragment` | 13 | 9 | 7 | 0 |
| `dazzle.render.onboarding` | 0 | 0 | 1 | 0 |
| `dazzle.seed.generator` | 0 | 1 | 0 | 0 |
| `dazzle.signing` | 0 | 0 | 0 | 1 |
| `dazzle.signing.tokens` | 1 | 1 | 0 | 0 |
| `dazzle.tenant` | 1 | 0 | 0 | 0 |
| `dazzle.tenant.cache_registry` | 1 | 0 | 0 | 0 |
| `dazzle.testing.entity_client` | 0 | 2 | 0 | 0 |
| `dazzle.testing.session_manager` | 0 | 1 | 0 | 0 |
| `dazzle.testing.step_executor` | 0 | 1 | 0 | 0 |
| `dazzle.testing.test_design_persistence` | 1 | 0 | 0 | 0 |
| `dazzle.testing.test_runner` | 0 | 1 | 0 | 0 |
| `dazzle.testing.testspec_generator` | 1 | 0 | 0 | 0 |
| `dazzle.testing.unified_runner` | 0 | 1 | 0 | 0 |
| `dazzle.testing.walk` | 0 | 11 | 0 | 0 |
| `dazzle.ui.runtime` | 0 | 1 | 0 | 0 |

## dazzle.toml sections × consumers

Number of `dazzle.toml` files declaring each top-level table (`[[auth.oauth_providers]]` counts as `auth`). A section not listed is declared by nobody.

| Section | AegisMark | cyfuture | pennydreadful | examples |
|---|---:|---:|---:|---:|
| `audit` | 1 | 0 | 0 | 0 |
| `auth` | 1 | 1 | 0 | 4 |
| `database` | 0 | 0 | 1 | 0 |
| `environments` | 1 | 1 | 1 | 0 |
| `extensions` | 0 | 0 | 1 | 0 |
| `fileset` | 1 | 0 | 0 | 0 |
| `llm` | 0 | 0 | 0 | 4 |
| `modules` | 0 | 1 | 1 | 4 |
| `project` | 1 | 1 | 1 | 4 |
| `renderers` | 1 | 0 | 1 | 0 |
| `serve` | 0 | 0 | 1 | 0 |
| `signing` | 1 | 0 | 0 | 0 |
| `stack` | 1 | 1 | 0 | 4 |
| `storage` | 1 | 0 | 0 | 0 |
| `tenant` | 0 | 1 | 0 | 0 |
| `ui` | 1 | 1 | 0 | 3 |

## Framework project files × consumers

Files the framework reads from a project (`*spec.yaml` literals in `src/dazzle`, `*.toml` literals in `src/dazzle/cli`), counted by name. This is how `pitch`, `sitespec` and `theme` are consumed without any CLI call.

| File | AegisMark | cyfuture | pennydreadful | examples |
|---|---:|---:|---:|---:|
| `brandspec.yaml` | 1 | 0 | 0 | 0 |
| `dazzle.toml` | 1 | 1 | 1 | 4 |
| `flense_consumers.toml` | 0 | 0 | 0 | 0 |
| `sitespec.yaml` | 1 | 1 | 0 | 4 |
| `test_personas.toml` | 0 | 0 | 0 | 0 |
| `themespec.yaml` | 1 | 1 | 0 | 1 |
| `trial.toml` | 1 | 1 | 0 | 4 |

## Framework endpoints referenced × consumers

Literal `/<segment>` references in `*.py`, `*.js`, `*.html`, `*.md`. Segments: the first segment of every route in `docs/api-surface/runtime-urls.txt` plus the router mount prefixes in `src/dazzle/http`. Baseline routes are router-relative, so generic segments (`/app`, `/api`, `/select`) also match app-owned URLs: a non-zero is *possible* use, a zero is strong evidence of none.

| Path prefix | AegisMark | cyfuture | pennydreadful | examples |
|---|---:|---:|---:|---:|
| `2fa` | 0 | 0 | 0 | 0 |
| `__test__` | 12 | 9 | 51 | 0 |
| `_dazzle` | 45 | 8 | 2 | 3 |
| `_dz` | 0 | 0 | 0 | 0 |
| `_ops` | 0 | 0 | 0 | 0 |
| `_site` | 0 | 0 | 0 | 0 |
| `api` | 201 | 94 | 1240 | 21 |
| `app` | 2216 | 5967 | 74 | 1 |
| `auth` | 129 | 135 | 71 | 0 |
| `banner` | 0 | 0 | 0 | 0 |
| `data` | 1 | 1 | 0 | 6 |
| `dazzle` | 0 | 0 | 3 | 0 |
| `field` | 0 | 0 | 0 | 0 |
| `files` | 7 | 21 | 0 | 0 |
| `forgot-password` | 0 | 1 | 0 | 0 |
| `intents` | 0 | 0 | 0 | 0 |
| `jobs` | 0 | 0 | 0 | 0 |
| `locale` | 0 | 0 | 0 | 0 |
| `login` | 84 | 145 | 6 | 29 |
| `logs` | 0 | 4 | 0 | 0 |
| `models` | 0 | 0 | 0 | 0 |
| `pending` | 0 | 0 | 0 | 0 |
| `qa` | 113 | 14 | 0 | 0 |
| `reset-password` | 0 | 0 | 0 | 0 |
| `search` | 1 | 2 | 0 | 0 |
| `select` | 141 | 8 | 11 | 4 |
| `sign` | 28 | 12 | 1 | 0 |
| `signup` | 236 | 101 | 0 | 2 |
| `site.js` | 0 | 0 | 0 | 0 |
| `state` | 0 | 0 | 0 | 0 |
| `stats` | 0 | 0 | 0 | 0 |
| `styles` | 3 | 0 | 0 | 0 |

## MCP tools named × consumers (approximate)

`mcp__dazzle__<tool>`, a backticked tool name followed by one of its operations, or `<tool>(operation=...)` in `*.md`, `*.toml`, `*.py`. Approximate: bare prose mentions are missed and agent transcripts are not scanned.

| Tool | AegisMark | cyfuture | pennydreadful | examples |
|---|---:|---:|---:|---:|
| `agent` | 0 | 1 | 0 | 0 |
| `bootstrap` | 0 | 0 | 0 | 0 |
| `compliance` | 1 | 0 | 0 | 0 |
| `conformance` | 0 | 1 | 0 | 0 |
| `db` | 5 | 0 | 2 | 0 |
| `discovery` | 0 | 4 | 0 | 0 |
| `dsl` | 82 | 8 | 0 | 0 |
| `feedback` | 5 | 0 | 0 | 0 |
| `guide` | 1 | 0 | 0 | 0 |
| `knowledge` | 3 | 0 | 0 | 0 |
| `policy` | 5 | 0 | 0 | 0 |
| `rhythm` | 3 | 0 | 0 | 0 |
| `semantics` | 1 | 4 | 0 | 0 |
| `sentinel` | 4 | 6 | 0 | 0 |
| `sitespec` | 16 | 0 | 0 | 0 |
| `spec_analyze` | 0 | 0 | 0 | 0 |
| `status` | 3 | 1 | 0 | 0 |
| `story` | 5 | 13 | 0 | 0 |

## Documentation by directory

| Directory | Markdown lines |
|---|---:|
| `docs/reference/` | 17,290 |
| `docs/adr/` | 5,978 |
| `docs/proposals/` | 4,679 |
| `docs/plans/` | 4,047 |
| `docs/guides/` | 3,458 |
| `docs/counter-priors/` | 3,095 |
| `docs/architecture/` | 1,955 |
| `docs/evaluation/` | 1,660 |
| `docs/contributing/` | 1,358 |
| `docs/decisions/` | 1,148 |
| `docs/getting-started/` | 663 |
| `docs/recipes/` | 457 |
| `docs/examples/` | 343 |
| `docs/harness/` | 47 |
| `docs/agent-loop/` | 25 |
| `docs/api-reference/` | 0 |
| `docs/api-surface/` | 0 |
| `docs/assets/` | 0 |
| `docs/superpowers/` | 0 |
| `docs/ux-architect/` | 0 |
