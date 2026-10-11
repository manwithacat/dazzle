# Flense inventory

> **Generated** by `scripts/flense_inventory.py` from `flense_consumers.toml` and the working tree.
> Do not edit; rerun the script. This table is the only admissible evidence for a keep or a
> removal under [ADR-0057](../adr/0057-consumer-forced-growth-and-mass-ratchet.md).

Snapshot: 2026-10-11. Consumers absent on this machine: none (absent means *unknown*, never *unused*).

## Totals

| Measure | Value |
|---|---:|
| Framework source lines (`src/dazzle`) | 476,741 |
| Test lines (`tests/`) | 425,933 |
| Documentation lines (`docs/**/*.md`) | 352,230 |
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
| `http` | 144,229 | 652 |
| `core` | 97,267 | 2,097 |
| `mcp` | 44,145 | 6,382 |
| `cli` | 34,384 | 10,273 |
| `render` | 32,981 | 6,157 |
| `testing` | 27,706 | 68 |
| `page` | 14,233 | 2,599 |
| `agent` | 10,845 | 9,578 |
| `qa` | 7,506 | 3,431 |
| `sentinel` | 7,252 | 563 |
| `fitness` | 5,858 | 1,401 |
| `db` | 4,362 | 3,692 |
| `compliance` | 4,286 | 1,417 |
| `rbac` | 4,243 | 7,853 |
| `pitch` | 4,069 | 1,893 |
| `domain_brief` | 2,634 | 1,017 |
| `demo_data` | 2,159 | 1,129 |
| `signing` | 2,143 | 2,249 |
| `layout` | 1,877 | 2,723 |
| `conformance` | 1,760 | 4,567 |
| `llm` | 1,718 | 3,490 |
| `lsp` | 1,632 | 665 |
| `services` | 1,632 | 274 |
| `agent_loop` | 1,542 | 154 |
| `product_quality` | 1,536 | 293 |
| `examples` | 1,499 | 1,052 |
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
| `tenant` | 537 | 6,998 |
| `stubs` | 517 | 0 |
| `risk` | 344 | 294 |
| `documents` | 212 | 207 |
| `process` | 203 | 5,453 |
| `deploy` | 194 | 671 |
| `seed` | 126 | 1,357 |
| `quality` | 85 | 761 |
| `stdlib` | 56 | 0 |
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

## Documentation by directory

| Directory | Markdown lines |
|---|---:|
| `docs/superpowers/` | 193,364 |
| `docs/api-reference/` | 100,716 |
| `docs/reference/` | 20,911 |
| `docs/adr/` | 5,978 |
| `docs/proposals/` | 4,679 |
| `docs/plans/` | 4,183 |
| `docs/guides/` | 3,671 |
| `docs/history/` | 3,588 |
| `docs/counter-priors/` | 3,112 |
| `docs/architecture/` | 2,696 |
| `docs/harness/` | 1,694 |
| `docs/evaluation/` | 1,662 |
| `docs/contributing/` | 1,415 |
| `docs/examples/` | 819 |
| `docs/research/` | 813 |
| `docs/getting-started/` | 665 |
| `docs/recipes/` | 501 |
| `docs/decisions/` | 239 |
| `docs/agent-loop/` | 25 |
| `docs/api-surface/` | 0 |
| `docs/assets/` | 0 |
| `docs/ux-architect/` | 0 |
