# Flense inventory

> **Generated** by `scripts/flense_inventory.py` from `flense_consumers.toml` and the working tree.
> Do not edit; rerun the script. This table is the only admissible evidence for a keep or a
> removal under [ADR-0057](../adr/0057-consumer-forced-growth-and-mass-ratchet.md).

Snapshot: 2026-10-11. Consumers absent on this machine: none (absent means *unknown*, never *unused*).

**How to read.** DSL declarations are one signal among seven. Consumers also reach the
framework through CLI calls in scripts and docs, Python imports, `dazzle.toml` sections,
framework-read project files (`sitespec.yaml`, `pitchspec.yaml` ...), framework URLs in
app code and assets, and MCP tool use. A removal needs a zero in *every*
signal section below for *every* present consumer; `?` (absent consumer) is unknown,
never zero. The non-DSL scanners are text matches: they over-count rather than miss.

## Totals

| Measure | Value |
|---|---:|
| Framework source lines (`src/dazzle`) | 465,791 |
| Test lines (`tests/`) | 420,335 |
| Documentation lines (`docs/**/*.md`) | 249,410 |
| Top-level DSL constructs | 57 |
| Constructs with zero consumer use | 27 |

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
| `app` | 1 | 1 | 1 | 13 | consumer-used |
| `approval` | 0 | 0 | 0 | 3 | examples only |
| `archetype` | 3 | 0 | 0 | 2 | consumer-used |
| `asset` | 0 | 0 | 0 | 0 | unused |
| `atomic` | 0 | 0 | 0 | 0 | unused |
| `audit` | 0 | 0 | 0 | 2 | examples only |
| `channel` | 0 | 0 | 0 | 6 | examples only |
| `data_products` | 0 | 0 | 0 | 0 | unused |
| `demo` | 0 | 0 | 0 | 0 | unused |
| `document` | 0 | 0 | 0 | 0 | unused |
| `entity` | 68 | 60 | 41 | 74 | consumer-used |
| `enum` | 0 | 0 | 0 | 1 | examples only |
| `event_model` | 0 | 0 | 0 | 3 | examples only |
| `experience` | 0 | 2 | 3 | 1 | consumer-used |
| `feedback_widget` | 0 | 1 | 0 | 4 | consumer-used |
| `flow` | 0 | 0 | 0 | 0 | unused |
| `foreign_model` | 0 | 34 | 0 | 1 | consumer-used |
| `grant_schema` | 2 | 5 | 0 | 0 | consumer-used |
| `guide` | 0 | 2 | 2 | 30 | consumer-used |
| `hless` | 0 | 0 | 0 | 0 | unused |
| `ingest` | 0 | 0 | 0 | 0 | unused |
| `integration` | 0 | 2 | 0 | 1 | consumer-used |
| `interfaces` | 0 | 0 | 0 | 0 | unused |
| `island` | 0 | 2 | 0 | 1 | consumer-used |
| `job` | 0 | 0 | 0 | 4 | examples only |
| `ledger` | 0 | 0 | 0 | 2 | examples only |
| `llm_config` | 1 | 0 | 1 | 3 | consumer-used |
| `llm_intent` | 5 | 0 | 6 | 12 | consumer-used |
| `llm_model` | 2 | 0 | 3 | 7 | consumer-used |
| `message` | 0 | 0 | 0 | 10 | examples only |
| `nav` | 10 | 6 | 5 | 35 | consumer-used |
| `notification` | 0 | 0 | 0 | 0 | unused |
| `param` | 5 | 32 | 0 | 0 | consumer-used |
| `persona` | 10 | 6 | 5 | 44 | consumer-used |
| `policies` | 1 | 0 | 0 | 0 | consumer-used |
| `process` | 0 | 1 | 0 | 14 | consumer-used |
| `projection` | 0 | 0 | 0 | 1 | examples only |
| `question` | 0 | 0 | 0 | 0 | unused |
| `rhythm` | 3 | 2 | 0 | 4 | consumer-used |
| `rule` | 0 | 0 | 0 | 0 | unused |
| `scenario` | 26 | 3 | 0 | 11 | consumer-used |
| `schedule` | 0 | 8 | 0 | 4 | consumer-used |
| `search` | 1 | 0 | 0 | 1 | consumer-used |
| `service` | 0 | 11 | 0 | 16 | consumer-used |
| `sla` | 0 | 8 | 0 | 1 | consumer-used |
| `story` | 62 | 214 | 16 | 128 | consumer-used |
| `stream` | 0 | 0 | 0 | 0 | unused |
| `subprocessor` | 4 | 0 | 0 | 0 | consumer-used |
| `subscribe` | 0 | 0 | 0 | 4 | examples only |
| `surface` | 234 | 219 | 46 | 258 | consumer-used |
| `template` | 0 | 0 | 0 | 0 | unused |
| `tenancy` | 1 | 1 | 0 | 3 | consumer-used |
| `test` | 0 | 0 | 0 | 0 | unused |
| `transaction` | 0 | 0 | 0 | 1 | examples only |
| `webhook` | 0 | 0 | 0 | 1 | examples only |
| `workspace` | 32 | 7 | 4 | 91 | consumer-used |

**Zero consumer use:** `approval`, `asset`, `atomic`, `audit`, `channel`, `data_products`, `demo`, `document`, `enum`, `event_model`, `flow`, `hless`, `ingest`, `interfaces`, `job`, `ledger`, `message`, `notification`, `projection`, `question`, `rule`, `stream`, `subscribe`, `template`, `test`, `transaction`, `webhook`

## Framework subpackages

Test lines are name-matched (`tests/**/test_*<subpackage>*.py`) — a floor, not a census.

| Subpackage | Source lines | Test lines (name-matched) |
|---|---:|---:|
| `http` | 135,321 | 652 |
| `core` | 96,887 | 2,097 |
| `mcp` | 44,145 | 6,382 |
| `cli` | 34,425 | 9,971 |
| `render` | 32,981 | 6,157 |
| `testing` | 27,704 | 68 |
| `page` | 14,233 | 2,599 |
| `agent` | 10,845 | 9,573 |
| `qa` | 7,506 | 3,431 |
| `sentinel` | 7,252 | 563 |
| `fitness` | 5,858 | 1,401 |
| `db` | 4,404 | 3,779 |
| `compliance` | 4,286 | 1,417 |
| `rbac` | 4,243 | 7,853 |
| `pitch` | 4,069 | 1,893 |
| `domain_brief` | 2,634 | 1,017 |
| `demo_data` | 2,159 | 814 |
| `signing` | 2,143 | 2,249 |
| `layout` | 1,877 | 2,723 |
| `conformance` | 1,760 | 4,567 |
| `llm` | 1,718 | 3,490 |
| `lsp` | 1,632 | 665 |
| `services` | 1,632 | 274 |
| `agent_loop` | 1,542 | 154 |
| `product_quality` | 1,536 | 293 |
| `perf` | 1,217 | 2,357 |
| `specs` | 1,149 | 466 |
| `e2e` | 1,095 | 2,440 |
| `i18n` | 1,086 | 851 |
| `api_kb` | 1,065 | 552 |
| `representation` | 1,024 | 279 |
| `api_surface` | 989 | 160 |
| `notifications` | 900 | 0 |
| `docs_update` | 886 | 599 |
| `spec_narrative` | 881 | 523 |
| `examples` | 571 | 1,052 |
| `tenant` | 537 | 6,998 |
| `stubs` | 517 | 0 |
| `deploy` | 194 | 671 |
| `seed` | 126 | 1,357 |
| `quality` | 85 | 761 |
| `documents` | 0 | 0 |
| `risk` | 0 | 196 |
| `templates` | 0 | 912 |

## MCP tools

| Tool | Operations |
|---|---:|
| `agent` | 3 |
| `agent_commands` | 3 |
| `api_pack` | 3 |
| `bootstrap` | 0 |
| `compliance` | 5 |
| `composition` | 6 |
| `conformance` | 4 |
| `db` | 2 |
| `demo_data` | 1 |
| `discovery` | 1 |
| `domain` | 5 |
| `dsl` | 11 |
| `e2e` | 4 |
| `feedback` | 4 |
| `fitness` | 1 |
| `graph` | 14 |
| `guide` | 4 |
| `knowledge` | 9 |
| `llm` | 4 |
| `mock` | 2 |
| `param` | 2 |
| `perf` | 3 |
| `pitch` | 1 |
| `policy` | 6 |
| `presentation` | 4 |
| `process` | 5 |
| `product_quality` | 1 |
| `representation` | 4 |
| `rhythm` | 3 |
| `semantics` | 6 |
| `sentinel` | 4 |
| `sitespec` | 14 |
| `spec_analyze` | 6 |
| `status` | 7 |
| `story` | 4 |
| `test_design` | 2 |
| `test_intelligence` | 6 |
| `user_management` | 9 |
| `user_profile` | 4 |

## CLI groups

`agent`, `analytics`, `api-pack`, `auth`, `backup`, `capability`, `clean`, `compliance`, `composition`, `conformance`, `contribution`, `db`, `demo`, `deploy`, `discovery`, `dlq`, `docs`, `domain`, `events`, `feedback`, `fitness`, `guide`, `inspect`, `kg`, `lsp`, `mcp`, `mock`, `nightly`, `outbox`, `param`, `perf`, `pipeline`, `pitch`, `process`, `process-migrate`, `prove`, `pulse`, `qa`, `quality`, `rbac`, `representation`, `rhythm`, `scaffold`, `sentinel`, `signing`, `spec`, `specs`, `story`, `stubs`, `sweep`, `tenant`, `test`, `test-design`, `theme`, `ux`, `vocab`, `worker`

## CLI groups × consumers

Occurrences of `dazzle <group>` (and bare top-level commands) in `Makefile`, `*.sh`, `*.yml`, `*.yaml`, `*.toml`, `*.md`, `*.py`, excluding `node_modules`, `.venv`, `.git`, `dev_docs/`, `archive/`, `.grok/`, `.dazzle/`, `__pycache__`. "Subcommands seen" is the next word after the group, so prose can add noise.

| CLI group / command | AegisMark | cyfuture | pennydreadful | examples | Subcommands seen |
|---|---:|---:|---:|---:|---|
| `agent` | 28 | 35 | 1 | 2 | `playbook`, `prove`, `seed`, `signals`, `sync`, `wall` |
| `analytics` | 0 | 0 | 0 | 0 |  |
| `analyze-spec` | 0 | 0 | 0 | 0 |  |
| `api-pack` | 0 | 0 | 0 | 0 |  |
| `auth` | 26 | 1 | 1 | 4 | `connection`, `create-user`, `impersonate`, `migrate` |
| `backup` | 0 | 0 | 0 | 0 |  |
| `build` | 0 | 0 | 0 | 3 |  |
| `build-api` | 0 | 4 | 0 | 0 |  |
| `build-css` | 0 | 0 | 0 | 0 |  |
| `build-ui` | 0 | 0 | 0 | 1 |  |
| `capability` | 0 | 0 | 0 | 0 |  |
| `check` | 0 | 0 | 0 | 0 |  |
| `clean` | 0 | 0 | 0 | 0 |  |
| `commands` | 0 | 0 | 0 | 2 |  |
| `compliance` | 3 | 2 | 0 | 17 | `compile`, `evidence`, `gaps`, `privacy` |
| `composition` | 0 | 0 | 0 | 0 |  |
| `conformance` | 0 | 0 | 0 | 0 |  |
| `contribution` | 0 | 0 | 0 | 0 |  |
| `coverage` | 1 | 0 | 0 | 0 |  |
| `db` | 136 | 25 | 83 | 36 | `apply-rls`, `at`, `baseline`, `current`, `downgrade`, `history`, `migrate`, `reconcile-baseline`, `revision`, `snapshot`, `snapshot-baseline`, `stamp`, `status`, `upgrade`, `verify` |
| `dbshell` | 0 | 0 | 0 | 0 |  |
| `demo` | 3 | 0 | 2 | 0 | `ingest`, `load`, `validate` |
| `deploy` | 1 | 0 | 0 | 0 | `plan` |
| `discovery` | 0 | 0 | 0 | 0 |  |
| `dlq` | 0 | 0 | 0 | 0 |  |
| `docs` | 3 | 12 | 0 | 0 | `claims`, `guides`, `site` |
| `doctor` | 0 | 0 | 0 | 0 |  |
| `domain` | 0 | 0 | 0 | 12 | `promote` |
| `events` | 0 | 0 | 0 | 0 |  |
| `example` | 0 | 0 | 0 | 0 |  |
| `feedback` | 0 | 0 | 0 | 0 |  |
| `fitness` | 2 | 0 | 3 | 0 | `queue`, `triage`, `vitality` |
| `fragment-audit` | 0 | 0 | 0 | 0 |  |
| `grammar` | 0 | 0 | 0 | 0 |  |
| `guide` | 0 | 0 | 0 | 0 |  |
| `info` | 0 | 0 | 0 | 0 |  |
| `init` | 0 | 0 | 0 | 1 |  |
| `inspect` | 1 | 0 | 3 | 0 | `renderers`, `rls` |
| `kg` | 0 | 0 | 0 | 0 |  |
| `layout-plan` | 0 | 0 | 0 | 0 |  |
| `lint` | 29 | 14 | 29 | 0 |  |
| `lsp` | 0 | 0 | 0 | 0 |  |
| `mcp` | 0 | 0 | 0 | 0 |  |
| `migrate` | 2 | 3 | 0 | 0 |  |
| `mock` | 0 | 0 | 0 | 0 |  |
| `nightly` | 0 | 0 | 0 | 0 |  |
| `outbox` | 0 | 0 | 0 | 0 |  |
| `param` | 0 | 0 | 0 | 0 |  |
| `perf` | 1 | 0 | 0 | 0 | `sweep` |
| `pipeline` | 83 | 41 | 0 | 0 | `run` |
| `pitch` | 0 | 0 | 0 | 0 |  |
| `process` | 0 | 0 | 0 | 9 | `list` |
| `process-migrate` | 0 | 0 | 0 | 0 |  |
| `prove` | 0 | 0 | 0 | 3 | `representation`, `story` |
| `pulse` | 0 | 0 | 0 | 0 |  |
| `qa` | 2 | 10 | 0 | 6 | `login`, `taste-panel`, `trial`, `trial-hypotheses` |
| `quality` | 0 | 0 | 0 | 0 |  |
| `rbac` | 12 | 5 | 0 | 36 | `byte-routes`, `matrix`, `prove`, `report`, `routes` |
| `representation` | 0 | 0 | 0 | 0 |  |
| `rhythm` | 0 | 0 | 0 | 0 |  |
| `scaffold` | 1 | 1 | 0 | 1 |  |
| `schema` | 0 | 0 | 0 | 0 |  |
| `search` | 0 | 0 | 0 | 0 |  |
| `sentinel` | 2 | 3 | 0 | 0 | `scan` |
| `serve` | 103 | 11 | 44 | 33 |  |
| `signing` | 1 | 0 | 0 | 0 | `init` |
| `spec` | 0 | 0 | 0 | 0 |  |
| `specs` | 0 | 0 | 0 | 2 | `asyncapi` |
| `story` | 0 | 2 | 0 | 0 | `list` |
| `stubs` | 0 | 0 | 0 | 0 |  |
| `sweep` | 0 | 0 | 0 | 0 |  |
| `tenant` | 0 | 5 | 0 | 3 | `create`, `list` |
| `test` | 9 | 62 | 0 | 8 | `agent`, `coverage`, `create-sessions`, `diff-personas`, `dsl-run`, `generate`, `pack`, `populate`, `run`, `tier2-generate`, `verify-story`, `walk` |
| `test-design` | 0 | 0 | 0 | 0 |  |
| `theme` | 0 | 0 | 0 | 0 |  |
| `ux` | 63 | 12 | 5 | 1 | `explore`, `maturity`, `verify` |
| `validate` | 46 | 129 | 89 | 40 |  |
| `version` | 0 | 0 | 0 | 0 |  |
| `vocab` | 0 | 0 | 0 | 25 | `expand`, `list`, `show` |
| `worker` | 1 | 0 | 0 | 0 |  |

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
| `dazzle.core.demo_blueprint_persistence` | 0 | 0 | 0 | 1 |
| `dazzle.core.environment` | 2 | 0 | 0 | 0 |
| `dazzle.core.ir` | 9 | 5 | 0 | 0 |
| `dazzle.core.validator` | 1 | 0 | 0 | 0 |
| `dazzle.demo_data.blueprint_generator` | 0 | 0 | 0 | 1 |
| `dazzle.http` | 2 | 0 | 0 | 0 |
| `dazzle.http.runtime` | 78 | 159 | 9 | 0 |
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
| `dazzle.signing` | 0 | 0 | 0 | 2 |
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
| `auth` | 1 | 1 | 0 | 12 |
| `database` | 0 | 0 | 1 | 0 |
| `dsl` | 0 | 0 | 0 | 1 |
| `environments` | 1 | 1 | 1 | 0 |
| `extensions` | 0 | 0 | 1 | 0 |
| `fileset` | 1 | 0 | 0 | 1 |
| `llm` | 0 | 0 | 0 | 12 |
| `modules` | 0 | 1 | 1 | 10 |
| `project` | 1 | 1 | 1 | 12 |
| `renderers` | 1 | 0 | 1 | 0 |
| `serve` | 0 | 0 | 1 | 0 |
| `signing` | 1 | 0 | 0 | 0 |
| `stack` | 1 | 1 | 0 | 12 |
| `storage` | 1 | 0 | 0 | 0 |
| `tenant` | 0 | 1 | 0 | 0 |
| `theme` | 0 | 0 | 0 | 1 |
| `ui` | 1 | 1 | 0 | 6 |

## Framework project files × consumers

Files the framework reads from a project (`*spec.yaml` literals in `src/dazzle`, `*.toml` literals in `src/dazzle/cli`), counted by name. This is how `pitch`, `sitespec` and `theme` are consumed without any CLI call.

| File | AegisMark | cyfuture | pennydreadful | examples |
|---|---:|---:|---:|---:|
| `brandspec.yaml` | 1 | 0 | 0 | 0 |
| `dazzle.toml` | 1 | 1 | 1 | 12 |
| `pitchspec.yaml` | 1 | 0 | 0 | 0 |
| `sitespec.yaml` | 1 | 1 | 0 | 12 |
| `test_personas.toml` | 0 | 0 | 0 | 0 |
| `themespec.yaml` | 1 | 1 | 0 | 1 |
| `trial.toml` | 1 | 1 | 0 | 11 |

## Framework endpoints referenced × consumers

Literal `/<segment>` references in `*.py`, `*.js`, `*.html`, `*.md`. Segments: the first segment of every route in `docs/api-surface/runtime-urls.txt` plus the router mount prefixes in `src/dazzle/http`. Baseline routes are router-relative, so generic segments (`/app`, `/api`, `/select`) also match app-owned URLs: a non-zero is *possible* use, a zero is strong evidence of none.

| Path prefix | AegisMark | cyfuture | pennydreadful | examples |
|---|---:|---:|---:|---:|
| `2fa` | 0 | 0 | 0 | 0 |
| `__test__` | 12 | 9 | 51 | 0 |
| `_dazzle` | 45 | 8 | 2 | 10 |
| `_dz` | 0 | 0 | 0 | 0 |
| `_ops` | 0 | 0 | 0 | 0 |
| `_site` | 0 | 0 | 0 | 0 |
| `api` | 201 | 94 | 1240 | 27 |
| `app` | 2216 | 5967 | 74 | 41 |
| `auth` | 129 | 135 | 71 | 1 |
| `banner` | 0 | 0 | 0 | 0 |
| `data` | 1 | 1 | 0 | 6 |
| `dazzle` | 0 | 0 | 3 | 6 |
| `devices` | 0 | 0 | 0 | 1 |
| `field` | 0 | 0 | 0 | 0 |
| `files` | 7 | 21 | 0 | 0 |
| `forgot-password` | 0 | 1 | 0 | 0 |
| `graphql` | 0 | 0 | 47 | 0 |
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
| `select` | 141 | 8 | 11 | 21 |
| `sign` | 28 | 12 | 1 | 0 |
| `signup` | 236 | 101 | 0 | 2 |
| `site.js` | 0 | 0 | 0 | 0 |
| `state` | 0 | 0 | 0 | 0 |
| `stats` | 0 | 0 | 0 | 0 |
| `styles` | 3 | 0 | 0 | 0 |
| `ws` | 0 | 0 | 0 | 0 |

## MCP tools named × consumers (approximate)

`mcp__dazzle__<tool>`, a backticked tool name followed by one of its operations, or `<tool>(operation=...)` in `*.md`, `*.toml`, `*.py`. Approximate: bare prose mentions are missed and agent transcripts are not scanned.

| Tool | AegisMark | cyfuture | pennydreadful | examples |
|---|---:|---:|---:|---:|
| `agent` | 0 | 1 | 0 | 0 |
| `agent_commands` | 0 | 0 | 0 | 0 |
| `api_pack` | 0 | 0 | 0 | 0 |
| `bootstrap` | 0 | 0 | 0 | 0 |
| `compliance` | 1 | 0 | 0 | 0 |
| `composition` | 0 | 0 | 0 | 0 |
| `conformance` | 0 | 1 | 0 | 0 |
| `db` | 5 | 0 | 2 | 0 |
| `demo_data` | 0 | 0 | 0 | 0 |
| `discovery` | 0 | 4 | 0 | 0 |
| `domain` | 0 | 0 | 0 | 0 |
| `dsl` | 82 | 8 | 0 | 0 |
| `e2e` | 0 | 0 | 0 | 0 |
| `feedback` | 5 | 0 | 0 | 0 |
| `fitness` | 0 | 0 | 0 | 0 |
| `graph` | 0 | 0 | 0 | 0 |
| `guide` | 1 | 0 | 0 | 0 |
| `knowledge` | 3 | 0 | 0 | 0 |
| `llm` | 0 | 0 | 0 | 0 |
| `mock` | 0 | 0 | 0 | 0 |
| `param` | 0 | 0 | 0 | 0 |
| `perf` | 0 | 0 | 0 | 0 |
| `pitch` | 0 | 0 | 0 | 0 |
| `policy` | 5 | 0 | 0 | 0 |
| `presentation` | 0 | 0 | 0 | 0 |
| `process` | 0 | 0 | 0 | 0 |
| `product_quality` | 0 | 0 | 0 | 0 |
| `representation` | 0 | 0 | 0 | 0 |
| `rhythm` | 3 | 0 | 0 | 0 |
| `semantics` | 1 | 4 | 0 | 0 |
| `sentinel` | 2 | 6 | 0 | 0 |
| `sitespec` | 16 | 0 | 0 | 0 |
| `spec_analyze` | 0 | 0 | 0 | 0 |
| `status` | 3 | 1 | 0 | 0 |
| `story` | 5 | 13 | 0 | 0 |
| `test_design` | 0 | 0 | 0 | 0 |
| `test_intelligence` | 0 | 0 | 0 | 0 |
| `user_management` | 0 | 0 | 0 | 0 |
| `user_profile` | 0 | 0 | 0 | 0 |

## Documentation by directory

| Directory | Markdown lines |
|---|---:|
| `docs/superpowers/` | 193,364 |
| `docs/reference/` | 20,894 |
| `docs/adr/` | 5,978 |
| `docs/proposals/` | 4,679 |
| `docs/plans/` | 4,183 |
| `docs/guides/` | 3,671 |
| `docs/history/` | 3,588 |
| `docs/counter-priors/` | 3,112 |
| `docs/architecture/` | 2,696 |
| `docs/evaluation/` | 1,662 |
| `docs/contributing/` | 1,414 |
| `docs/examples/` | 819 |
| `docs/research/` | 811 |
| `docs/getting-started/` | 665 |
| `docs/recipes/` | 501 |
| `docs/decisions/` | 239 |
| `docs/harness/` | 47 |
| `docs/agent-loop/` | 25 |
| `docs/api-reference/` | 0 |
| `docs/api-surface/` | 0 |
| `docs/assets/` | 0 |
| `docs/ux-architect/` | 0 |
