# Flense programme — a smaller framework with a provable moat

**Date:** 2026-10-11 · **Status:** Accepted by the operator 2026-10-11; in execution · **Owner:** primary agent, steered by the operator
**Constitution:** [ADR-0057](../adr/0057-consumer-forced-growth-and-mass-ratchet.md) (proposed alongside this plan)

## 1. Why

Frontier agents write SaaS from a spec without help, so Dazzle's original
"agents need a small surface" argument is spent. What survives is the
**verifiable** part: an anti-Turing DSL from which RBAC, scope, tenancy,
audit, signing and compliance evidence are *derived*, not asserted. The
target market makes that the whole product:

| Consumer | Domain | Obligations the app must demonstrate |
|---|---|---|
| AegisMark | state education, formative marking | safeguarding of children, data protection, high-stakes integrity of marks |
| cyfuture | accountancy | regulatory filings, KYC/AML, document signing, client-money discipline |
| pennydreadful | publishing | IP and authorship verification, royalty calculation, rights auctions |

The moat is: *a customer of a Dazzle app can be shown that their data is secure,
safe, auditable and ISM-disciplined, from the model.* Everything that does not
feed that demonstration is mass, and mass is now the main cost of the thesis.

## 2. The evidence (2026-10-11)

| Measure | Value | Reading |
|---|---|---|
| Framework Python | 477k lines (`http` 144k, `core` 97k, `mcp` 44k, `cli` 34k, `render` 33k, `testing` 28k) | ~30× the DSL it serves |
| Tests | 426k lines, 25.6k tests; ≥10k lines gate the harness, not the product | attention per failure is the scarce resource |
| Docs | 352k Markdown lines; `docs/superpowers/` alone is 193k (181 plans + 145 specs, excluded from the site) | the harness writing about itself |
| Consumer DSL | 33k lines in three live apps | the only usage signal that counts |
| Top-level DSL constructs | 57 dispatched; **27 have zero consumer use** (`ledger`, `transaction`, `enum`, `webhook`, `ingest`, `approval`, `atomic`, `test`, `flow`, `rule`, `message`, `channel`, `asset`, `document`, `template`, `demo`, `event_model`, `subscribe`, `projection`, `stream`, `hless`, `interfaces`, `data_products`, `notification`, `job`, `audit`, `question`) | half the vocabulary is unproven |
| Proof commands consumers actually run | `rbac matrix`, `sentinel scan`, `ux verify`, `qa trial`, `tenant create` | **nobody runs `dazzle compliance`, `policy`, or `audit`** |
| Commits, last 90 days | 1,961; 1,254 from the improve loop; its last cycles report "zero belief revisions" | the loop optimises what it can see: itself |
| Open issues | #1773, #1774, #1775 are real consumer bugs at `needs-triage` | consumer force was waiting while the loop measured clean apps |

Two conclusions follow. The moat is **claimed but not exercised** by its own
consumers, and the framework's growth has been driven by exploration, not force.

## 3. Principles (the ADR, in one paragraph)

1. **Consumer-forced growth only.** A construct, subsystem, MCP tool, CLI group or
   document stays if a named consumer app uses it or a Deferred Decision names
   the consumer that will. "Might be useful for a regulated domain" is not force.
2. **Mass ratchet.** Framework source, test and documentation mass may only go
   down until the targets in §7 are met; a feature that adds mass must retire at
   least as much. Mechanically enforced like the complexity ratchet.
3. **The proof surface is sacred and must be exercised.** RBAC matrix, scope
   algebra, tenancy/RLS, audit trail, signing, PII handling, compliance evidence:
   keep, harden, and make each consumer app *produce* them in CI.
4. **The anti-Turing constraint is non-negotiable.** No construct may make the DSL
   unverifiable; this is what competitors cannot copy by prompting harder.
5. **Delete, don't deprecate** (ADR-0003). Removed things leave a one-line
   CHANGELOG epitaph and, if a consumer may later force them back, a parked DD.

## 4. Phases

### Phase 0 — Baseline and governance (week 1)

- Accept ADR-0057. Add `scripts/flense_inventory.py` that emits one committed
  table, `docs/reference/flense-inventory.md`: per subpackage / construct / MCP
  tool / CLI group → lines, test lines, and **consumer users** (AegisMark,
  cyfuture, pennydreadful, examples). Consumer paths come from a small
  `flense_consumers.toml` the operator maintains. The inventory is the only
  admissible evidence for a removal or a keep.
- Add the **mass ratchet** gate: `tests/unit/test_mass_ratchet.py` with a
  baseline `{src_lines, test_lines, docs_lines, construct_count}`; any increase
  fails `make ci-fast`; `--write-baseline` only lowers it.
- Triage #1773, #1774, #1775 and fix them first. Consumer bugs outrank everything
  in this plan; they are also the proof that consumer force now drives the queue.

### Phase 1 — Stop the bleeding: the improve loop (week 1)

- The improve driver loses its explore budget and its measurement lanes. What
  remains is an **issues-first loop**: consumer issues, consumer-app CI
  failures, and proof-surface regressions. `trials`, `framework-ux` fitness
  walks, `example-apps` smoke-digs, `hm-convergence` and `test-suite` lanes are
  retired; their playbooks are deleted, not archived.
- The capability map, orientation benchmark, principle-gate registry,
  leftover-token contract, and improve-commit contract are harness
  instruments for a loop that no longer runs that way. Delete them with their
  gates (≈10k test lines, ≈30 `tests/unit` modules). Keep: `preflight-surface`,
  `ship-surface`, `push-gate`, the API-surface baselines, docs-drift, and the
  agent-asset gate (they protect the product and the ship path).
- `dev_docs/improve-*` stop being written. `fuzz-nightly` stays (it finds boot
  regressions in consumers' shapes); `mutation-nightly` is reviewed in Phase 3.

### Phase 2 — Harness and docs diet (weeks 1–2)

- `docs/superpowers/` (193k lines) and `docs/history/` move to a separate
  archive repository or an orphan `archive` branch; the working tree keeps
  `stems/`, `docs/adr/`, `docs/decisions/`, `docs/counter-priors/`,
  `docs/reference/`, `docs/guides/`, `docs/contributing/`, `docs/getting-started/`
  and the two moat documents (`SECURITY_CLAIMS.md`, `EVALUATION.md`).
- `docs/harness/` shrinks to `tool-floor.md` and `operator-field-guide.md`.
- `docs/api-reference/` (100k generated lines) is built, not committed.
- `.agents/skills/` keeps `ship`, `bump`, `check`, `cimonitor`, `dsl-authoring`,
  `qa-trial`, `stems`, `semgrep`, `issues` (rewritten as the loop), `fuzz`.
  `blue-sky`, `xproject`, `smells`, `docs-update`, `spec-narrate`,
  `phase-contract` and `improve` go, with their shims and `.claude/workflows/`.
- AGENTS.md drops the Autonomous Loops section to three lines and loses the
  Capability Mapping table once only one harness family is in use; the vendor
  gate is relaxed to "no vendor names in `.agents/skills/`".

### Phase 3 — Framework flense (weeks 2–6), one subsystem per ship

Dispositions, from the inventory. **Delete** = no consumer, no DD. **Park** = no
consumer today, a named future consumer, DD written, code removed. **Prove** =
on the moat, unused today, a consumer adopts it or it is parked.

| Candidate | Lines (src / tests) | Disposition | Reason |
|---|---|---|---|
| GraphQL BFF (`http/graphql`, #1757) | 11k / 0.4k | Delete | wired but unproven; no consumer |
| `pitch/` + `sitespec` + marketing conformance | 4k + ? / 3.5k | Delete | not a regulated-SaaS concern |
| `composition` (screenshot + LLM visual eval) | ? / 4.3k | Delete | harness instrument |
| `fitness/`, `product_quality/`, `domain_brief/`, `spec_narrative/`, `docs_update/`, `agent_loop/`, `agent/` (10.8k) | ~22k / ~3k | Delete (keep complexity/clone/dead-definition ratchets as plain tests) | loop instruments |
| `i18n`, `saml`, `mobile` extras | ~2k / ~2k | Park (DD: cyfuture SSO is OAuth today; SAML returns on a named tenant) | no consumer |
| `perf/` envelope | 1.2k / 1.8k | Delete; keep `dazzle perf report` only if cyfuture adopts it | — |
| `api_kb/` packs (Stripe, Companies House remain) | 1k | Keep only packs a consumer declares | already in progress (#1768, #1771) |
| `hless`, `stream`, `event_model`, `subscribe`, `projection`, `channel`, `message`, `notification`, `job` | parser + `http/events` 8k + `channels` 4.8k / ~9k | Park (DD: pennydreadful rights auctions may force events; a notification construct may be forced by AegisMark safeguarding alerts) | zero consumer use |
| `ledger`, `transaction`, `atomic` | ? / 2.7k | Park (DD: pennydreadful royalties, cyfuture client money) | zero use today; likely forced within months — keep the IR design in the DD |
| `approval`, `sla`, `rhythm`, `flow`, `rule`, `test`, `question` | ? / ~4k | `sla`/`rhythm`: keep (cyfuture uses). Others: delete | — |
| `document`, `template`, `asset`, `demo`, `interfaces`, `data_products`, `ingest`, `webhook` | `http/data_products` 1.5k … / ~6k | `webhook`/`ingest`: Prove — cyfuture KYC and signing callbacks should be webhooks, not app code. Rest: delete | — |
| `audit` construct | ? / 9.3k | **Prove** — AegisMark declares `[audit]` in config; the moat needs the DSL-level construct exercised by both regulated consumers, or the config path is the construct | the biggest test mass in the unused set |
| `compliance/`, `policy`, `rbac/`, `signing/`, `tenant/`, `risk/`, `pii` | 4.3k + 4.2k + 2.1k + … | **Prove** — see Phase 4 | the moat, unexercised |
| `http/pra` (parser-conformance runtime) | 6k | Keep as a fixture-only test asset | — |
| `http/tests` routes, `test_routes.py` (1k) | 10k | Fold into `testing/`; delete what `ux verify` does not use | — |
| Examples | 13 apps, 22.6k DSL | Keep `simple_task`, `support_tickets`, `invoice_ops`, `hr_records`; retire the rest once their probes are covered by consumer apps | examples are probes; consumers are better probes |

Each removal is one ship: inventory row → delete → gates → CHANGELOG epitaph →
DD if parked. The ratchet baseline is lowered with each ship so the mass cannot
return.

### Phase 4 — Prove the moat on the consumers (weeks 3–8)

The deliverable is an **assurance pack** per app, produced by one command
(`dazzle assure`, or the existing commands composed in each app's CI):

- RBAC matrix + scope proofs (`rbac matrix`, `db explain-scope`, the dynamic verifier)
- Tenancy / RLS proof for cyfuture; safeguarding data-boundary proof for AegisMark
- Audit-trail coverage: every state transition and every PII read/write is evidenced
- Signing chain (`signing_validation` shape) for cyfuture filings and AegisMark marks
- PII inventory and retention from the model
- Compliance evidence (`compliance compile|gaps`) mapped to ISO 27001 / SOC 2 /
  the UK education and AML control sets the two consumers face
- A rendered, customer-facing summary that a non-technical buyer can read

Acceptance: both regulated consumers run the pack in CI and commit the output;
a `gaps` count that rises fails their build. Framework work in this phase is
whatever the pack reveals (today: nobody runs `compliance`, so expect gaps).

### Phase 5 — Measure (from week 4, continuous)

| Metric | Source | Direction |
|---|---|---|
| Framework src / test / docs lines; src lines per used construct | mass ratchet baseline | down |
| Consumer bugs open > 7 days; median time from report to fix | tracker | down |
| Assurance-pack gaps per consumer | Phase 4 output | down to zero, then held |
| Cost of a representative change (new entity + scope + screen) on a consumer | timed agent run, recorded per release | down |
| The thesis test: same spec built on Dazzle vs plain stack, scored on RBAC correctness, evidence produced, and cost of a later change | one benchmark per quarter | Dazzle must win on evidence; if it does not, revisit the thesis |

## 5. Sequencing and effort

| Week | Work |
|---|---|
| 1 | ADR-0057, inventory script + table, mass ratchet gate, consumer bugs fixed, improve loop retired |
| 1–2 | docs archive, harness gates pruned, skills pruned |
| 2–6 | one flense ship per working day; ~25 ships |
| 3–8 | assurance pack on AegisMark and cyfuture; framework fixes it forces |
| 8 | first thesis benchmark; review targets |

## 6. Risks

- **Over-flensing a future consumer need.** Mitigation: parked DDs carry the IR
  design; pennydreadful (events, ledgers) is the likely re-forcing consumer.
- **Breaking consumers mid-flense.** Mitigation: a consumer-CI job in this repo
  that validates the three apps' DSL against the working tree before every ship.
- **The archive hides judgement.** Mitigation: stems and ADRs stay; the archive
  holds plans and reports, which are expressions, not stems.
- **Loop retirement loses nightly hygiene.** Mitigation: fuzz-nightly and the
  ship gates remain; the issues loop runs on consumer force only.

## 7. Targets (end of Phase 3; src/tests end state revised 2026-10-16, see §10.4)

| Measure | Now | Target |
|---|---|---|
| Framework src lines | 477k | ≤ 300k (was ≤ 250k; revised 2026-10-16 — the remaining mass is consumer-used feature mass ADR-0057 keeps) |
| Test lines | 426k | ≤ 250k, zero harness-only gates (was ≤ 200k; revised 2026-10-16) |
| Docs lines in tree | 352k | ≤ 60k |
| Top-level constructs | 57 | ≤ 30, all consumer-used or parked |
| Consumers producing an assurance pack in CI | 0 | 2 |

## 8. Status (2026-10-13, after the first autonomous run and the operator's decisions)

Phases 0–3 are landed on `main` (sixteen ships between 518c02a6e and the closing ship), run as a
self-paced loop with Opus worktree agents preparing each ship and this session reviewing,
merging, gating and pushing.

| Measure | Start | Now | Target (§7) |
|---|---:|---:|---:|
| Framework src lines | 476,741 | 394,479 | ≤ 250,000 |
| Test lines | 425,933 | 363,392 | ≤ 200,000 |
| Docs lines in tree | 352,230 | 48,439 | ≤ 60,000 |
| Top-level constructs | 57 | 31 | ≤ 30 |
| Consumers producing an assurance pack | 0 | 0 | 2 |

Landed: Phase 0 (inventory + mass ratchet); Phase 1 (improve-loop instruments); Phase 2
(docs archive → `archive` branch); ships A, B1, B2, C, D, E, F, G; consumer bugs #1773,
#1774, #1775; the consumer-aware artefact coverage gate (now enforcing in
`make preflight-surface`). Deferred Decisions written: DD-002 pitch, DD-003 domain brief,
DD-004 ledger/transaction, DD-005 inbound webhooks, DD-006 events DSL, DD-007 messaging
DSL, DD-008 background jobs, DD-009 verified domain join.

Decisions taken on 2026-10-13: (1) the drop of `_dazzle_atomic_audit`,
`_dazzle_ingest_fingerprint` and `join_requests` is approved — revision
`0022_flense_park_tables` now performs it (it had shipped as a no-op on `main`, before any
release carried it); (2) Phase 4 runs inside the consumer repos through hand-off files
`FLENSE_AEGISMARK.md`, `FLENSE_CYFUTURE.md` and `FLENSE_PENNYDREADFUL.md`, each given to an
agent working in that checkout; (3) Phases 0–3 are released as v0.116.0 (minor; Breaking
entries in the CHANGELOG); (4) the strategy for the remaining src and test mass is agreed:
surgical cuts inside the kept subsystems from the inventory's per-subpackage table
(`http/runtime` 103k, `core/dsl_parser_impl` 30k, `mcp` 44k), not whole-subsystem removals.

Phase 4 starting point, measured on 2026-10-13 with the v0.116.0 tree against each checkout
(`rbac prove`, `compliance gaps -f iso27001`, `analytics audit`, `rbac routes`):

| Consumer | `rbac prove` | ISO 27001 gaps | PII hints / subprocessors | Routes outside the matrix | DSL evidence |
|---|---|---:|---:|---:|---|
| AegisMark | 2 proved, 1 informational, 2 vacuous, 12 residual notes | 10 (all tier 3) | 31 / 12 | 0 (route scan cannot import `pipeline`) | 111 classify, 354 permit, 612 scope, 10 persona |
| cyfuture | 2 proved, 1 informational, 2 vacuous, 4 residual notes | 16 (incl. A.5.12/13 classification, A.5.34 PII, A.8.11 masking) | 32 / 8 | 1 (`POST /companycontacts`); 4 `admin` delete permits with no scope rule | 0 classify, 296 permit, 881 scope, 8 sla |
| pennydreadful | 2 proved, 1 informational, 2 vacuous, 16 residual notes | 10 (all tier 3) | 3 / 8 | 0 | 0 classify, 144 permit, 271 scope; persona `agent` unreferenced |

### 8.1 The surgical loop (2026-10-13/14, after v0.116.0)

Twenty commits on `main` after the release, ships H–AC, run the same way (Opus worktree
agents, the session harvesting by cherry-pick, every ship gated with `make ci-fast` and
pushed under the push gate; CI green on every push). Removals were evidenced by
zero-importer and reachability walks from the console entry point, the MCP dispatch table,
the HTTP server, Alembic and every consumer, script, hook and skill import, then a word
search across the framework and the three checkouts; anything with a reader stayed and is
listed in the CHANGELOG.

| Measure | v0.116.0 | After ship AC | Target (§7) |
|---|---:|---:|---:|
| Framework src lines | 394,547 | 339,095 | ≤ 250,000 |
| Test lines | 363,407 | 350,984 | ≤ 200,000 |
| Docs lines in tree | 48,483 | 47,806 | ≤ 60,000 |
| Top-level constructs | 31 | 31 | ≤ 30 |

What the loop found that mattered more than the lines: the search routes applied no scope
(ship P), the rich-text sanitiser was never called and the plain-text denylist was
bypassable and mangled ordinary text (T, W), the list endpoint showed anonymous callers
every row in test mode (AA), `GET /_dazzle/grants` listed every grant to any user (AC),
the grant clauses both regulated consumers declare were parsed and never enforced (Q),
`tenancy: mode:` was never applied (R), no CRUD service ever inherited the event mixin
DD-006 described (O), islands were never rendered (DD-011), the locale middleware was never
mounted and the feedback widget never served (AB), and a long tail of DSL clauses
consumers write that nothing reads — now `dazzle validate` warnings (U, X, Z, AC).

The src and test targets are not met. The remaining mass is live: `http/runtime` ≈ 85k,
`core` ≈ 70k, `render` 29k, `mcp` ≈ 30k, `cli` ≈ 25k, with the reachability walks now
finding no unreached module in those packages. Further reduction means retiring features
consumers use or re-architecting kept ones, which is a product decision, not a flense.

Open for the operator: drop revisions for the `devices` table (ship O) need sign-off;
`/_dazzle/metrics` serves a constant document (drop the URL or wire a collector); the
`SortHeader` dual lock retires HM-first; `mobile_full` has no consumer; pennydreadful serves
`/app` page lists unscoped to anonymous callers (AA finding, consumer decision); cyfuture's
`/actions` command calls the now-empty `extract_guards`. Each consumer's actions are in its
`FLENSE_*.md` §8.

Known nuisances: the HaTchi-MaXchi prose-drift tests fail when run from the framework root
(pre-existing; they pass in the package's own gate), and `test_api_surface_drift[ir_types]`
is order-dependent after the presentation MCP tests in one process.

## 9. Phase 6 — the second flense (planned 2026-10-15, after v0.117.0)

Phases 0–3 and the surgical loop removed ~800k lines across src, tests, docs and the
archive branch without changing the consumer-facing feature set. §8.1 concluded that the
reachability walks find no unreached *module*; this phase works one level down and on the
test suite, which is now larger than the framework it tests (351k test lines for 339k src).

### 9.1 Principles carried forward, one added

- Everything in §3 and ADR-0057 still applies: a thing stays only with a named consumer, a
  named future consumer gets a Deferred Decision and the code goes, evidence is `rg` across
  the framework, the three checkouts, scripts, hooks, skills, Makefile and CI, never a guess.
- **HaTchi-MaXchi is exempt.** `packages/hatchi-maxchi/` is a design system pursuing parity
  with shadcn-class component libraries; a Hyperpart without a consumer is a deliberate,
  speculative asset, not flense mass (operator ruling 2026-10-15). No Phase 6 ship touches
  HM components, controllers, CSS, gallery or baselines; the HM standalone CI stays the gate.
- A test is kept for the behaviour it pins, not for its name or count. The distillation
  reports under `tests/audit/` are the evidence; one behaviour = one test; a cluster that
  asserts one shape over N inputs becomes one parametrised test.

### 9.2 Evidence (measured 2026-10-15 against v0.117.0 and the three checkouts)

| Finding | Size (src / tests) | Evidence |
|---|---:|---|
| Enterprise auth (SAML, SCIM, enterprise OIDC, connections, domain verification, `dazzle auth connection`) | ≈ 5,500 / ≈ 13,000 | gated on `[capabilities] enabled` in `dazzle.toml`; no consumer declares the section; AegisMark's `docs/enterprise-auth-enablement.md` records the capability as "inert" and names go-live as a reviewed architecture change |
| Two-factor auth (TOTP, recovery codes, `/2fa/*` pages) | ≈ 1,100 / ≈ 1,400 | mounted for every app; no consumer declares `security: two_factor`; zero `/2fa` references in any checkout |
| `dazzle init` and the bundled `dazzle.examples` package | ≈ 8,100 (4,700 of it a Vite/`dnr-ui` SPA and a Docker frontend) / 9 test files | no consumer runs `init`; `bootstrap` (MCP) is the documented entry point and does not use it; a bundled SPA contradicts ADR-0011 |
| `/_ops/sse` streaming, `/_site/*` JSON API | ≈ 600 / ≈ 100 | no JS, HM, test or consumer caller beyond registration |
| `fixtures/investigator_smoke` | 0 DSL, 3 files | fixture for the fitness investigator removed in ship B1; zero test references |
| Function clones | 138 clone pairs, 76 exact families (`tests/unit/fixtures/clone_*.json`) | `dazzle fitness clones` |
| Test redundancy | 989 clusters of ≥3 same-shape tests (3,899 tests; ≈ 2,910 collapsible), 21 cross-file clusters (205 tests), 74 implementation mirrors | `tests/audit/redundancy_report.md`, `cross_file_report.md`, `taxonomy_report.md` |
| Test mass by area | `tests/unit` 323k of 351k; largest files `test_parser.py` 3.7k, `test_region_adapter.py` 2.5k, `test_rhythm_mcp.py` 2.1k, `test_validator.py` 1.8k, `test_template_compiler.py` 1.5k | 16,750 test functions, 1,459 parametrised |
| Kept and load-bearing (not candidates) | `http/events` (cyfuture subscribes to the entity bus and runs `EventBusProcessAdapter`), `http/channels` (the email kernel the auth subsystem uses), social OAuth via `authlib` (cyfuture google/github/apple), magic link (AegisMark), S3 storage (AegisMark), `sitespec`/`themespec`/`brandspec`, `/__test__` seed routes (all three), `dazzle pipeline` (AegisMark, cyfuture), `dazzle test` (cyfuture, 14 files) | inventory + `rg` |

Not a cut, noted for the operator: `src/dazzle/examples/simple_task/build/` holds 700 MB of
ignored `node_modules` on disk (safe to delete locally); cyfuture's
`scripts/probe_jinja_usage.py:55` imports the dead `dazzle.ui.runtime` path (consumer action,
added to `FLENSE_CYFUTURE.md`).

### 9.3 Ships

Letters continue from the surgical loop. **D** = needs an operator decision before dispatch;
the rest run on evidence alone, same mechanics as §8.1 (Opus worktree agents, harvest by
cherry-pick, `make ci-fast`, push gate, no bump mid-loop; a `minor` bump closes the phase).

| Ship | Scope | Disposition | Expected Δ (src / tests) |
|---|---|---|---:|
| **AD** (D) | Enterprise auth: `auth/saml_*`, `scim_*`, `oidc_provider`, `enterprise_*`, `connection_*`, `connections`, `leftover_*`, `sso_session`, DNS resolvers, `connection_crypto`, `cli/auth_connection.py`, the `auth.enterprise.*` capability registrations, their tables (drop revision, operator sign-off like `devices`), the `saml` extra and python3-saml/xmlsec | **Park** as DD-013 "Enterprise SSO / SCIM connections"; reopen when AegisMark (or any consumer) declares the capability. Social OAuth (`sso_routes`, `sso_config`, authlib) and magic link stay | −5.5k / −13k |
| **AE** | `/_ops/sse` (`sse_stream.py`), the `/_site/*` JSON API in `site_routes.py`, `/_dazzle/metrics` if the operator confirms the constant document goes (§8.1), `fixtures/investigator_smoke` | Delete | −1k / −0.3k |
| **AF** (D) | `dazzle init`, `dazzle.examples` (bundled `simple_task` with `dnr-ui` SPA, Docker frontend, testspec, generated e2e), `cli/project.py` paths that only serve them | Delete; `bootstrap` + `examples/simple_task` in the repo remain the way a new app starts. If the operator wants `init` kept, it scaffolds from `examples/simple_task` with no bundled copy | −8k / −1k |
| **AG** (D) | Two-factor auth: `routes_2fa`, `two_factor_*`, `leftover_2fa_code`, TOTP/recovery helpers, the `/2fa/*` pages in `site_routes.py`, `security.two_factor` IR | **Park** as DD-014 "Two-factor authentication"; reopen when a consumer declares `security: two_factor`. Alternative the operator may prefer: keep, and make a consumer adopt it in Phase 4 as part of its assurance pack | −1.1k / −1.4k |
| **AH** | Exact clone families (`clone_families.json`): one definition per family, callers updated; clone baseline lowered | Consolidate | −1k / 0 |
| **AI** | Dead-definition ratchet round 2 after AD–AH (vulture ≥60%, verified by `rg` across src/tests/consumers; never a dispatch-table or registry target) | Delete | −1k / −0.5k |
| **AJ–AN** | Test distillation, one ship per area, in this order: (AJ) `test_region_adapter.py` + `tests/unit/render/`; (AK) `tests/unit/http_runtime/` + `test_datatable_handler.py` + `test_query_builder.py` + `test_document_routes.py`; (AL) `tests/unit/mcp/` + `test_rhythm_mcp.py` + `test_sentinel*`; (AM) `test_parser.py` + `test_validator.py` + `test_template_compiler.py` + `tests/unit/test_signing/`; (AN) cross-file clusters → shared parametrised helpers in `tests/unit/helpers/`, and the 74 implementation mirrors rewritten against public behaviour or deleted | Collapse same-shape clusters to parametrised tests; delete tautologies and mirrors; never delete a regression pin (`#nnnn` in the name or docstring) without proving the behaviour is pinned elsewhere | 0 / −40k to −55k |

Rules for AJ–AN, in the brief of every agent: regenerate `tests/audit/` with
`scripts/distill/{classify,cluster,cross_file}.py` after the change; the ship's own cluster
count must fall; `make ci-fast` and the full unit run (`uv run pytest -n auto -m "not e2e"`)
both green; a test removed because another test pins the same behaviour names that test in
the commit body; HM tests (`test_hm_*`, `packages/hatchi-maxchi/tests`) are out of scope.

### 9.4 Decisions needed (before AD, AF, AG are dispatched)

1. **AD — park enterprise auth.** The ADR says park: no consumer declares the capability and
   the only named future consumer has written down that enabling it is a reviewed go-live.
   The design, the schema and the CLI live on in DD-013 and the `archive` branch. Against:
   SSO/SCIM is part of the enterprise sales story for a regulated SaaS. Recommendation: park;
   reopening is a cherry-pick, and a consumer adopting it would do so through the FORCED path
   with a real IdP to test against, which none has today.
2. **AF — delete `dazzle init` and the bundled example.** Recommendation: delete; the wheel
   should not ship a Vite SPA, and `bootstrap` is the entry point. If `init` stays, it
   scaffolds from the repo example without a bundled copy.
3. **AG — park two-factor auth.** Recommendation: park (DD-014) with the explicit note that a
   regulated consumer's assurance pack is the forcing function to bring it back; the
   alternative is to make AegisMark adopt it now under Phase 4.

### 9.5 Targets for this phase

| Measure | After ship AC | Phase 6 target | Note |
|---|---:|---:|---|
| Framework src lines | 339,095 | ≤ 322,000 | AD, AE, AF, AG, AH, AI |
| Test lines | 350,984 | ≤ 295,000 | AJ–AN carry most of it |
| Docs lines in tree | 47,806 | ≤ 48,000 | DD-013/014 add, removed-feature docs go |
| Top-level constructs | 31 | 31 | unchanged |
| Clone families | 76 | ≤ 20 | AH |
| Redundancy clusters ≥3 | 989 | ≤ 600 | AJ–AN |

The §7 targets (≤ 250k src, ≤ 200k tests) stay out of reach without retiring features
consumers use or re-architecting `http/runtime` (`page_routes.py` 3.9k, `server.py` 2.7k,
`auth/store.py` 2.9k are the monoliths); that is Phase 7 material and a product decision.

### 9.6 Mechanics

Same loop as §8.1: the session orchestrates, up to three Opus worktree agents in flight,
harvest by `git cherry-pick --no-commit`, CHANGELOG under Unreleased in house style, mass
baseline lowered per ship (`--force --reason` only when a ship adds lines, e.g. a DD), push
under the push gate, CI checked each wake, one line per wake in `.dazzle/flense-log.md`.
AJ–AN may run concurrently with AD–AI because they touch disjoint files; two distillation
ships never run at once. The phase closes with a `minor` bump, plan §9 updated with the
measured numbers, and `FLENSE_*.md` refreshed if any consumer action results.

### 9.7 Result (2026-10-15, twelve ships, e5b93a20e → ecff20838)

All twelve ships landed on `main` the same day, each gated with `make ci-fast`, pushed under
the push gate, CI green on every pushed tip: AE, AJ, AO (a security fix AE surfaced), AH, AK,
AF, AL, AD, AM, AG, AN, AI. Net −61,286 lines across 628 files (−82,775 / +21,489).

| Measure | After ship AC | Phase 6 target | After ship AI |
|---|---:|---:|---:|
| Framework src lines | 339,095 | ≤ 322,000 | **323,851** (−15,244; target missed by 1.9k) |
| Test lines | 350,984 | ≤ 295,000 | **319,714** (−31,270; tests are now fewer lines than src) |
| Docs lines in tree | 47,806 | ≤ 48,000 | 47,862 |
| Top-level constructs | 31 | 31 | 31 |
| Test functions | 16,750 | — | 14,307 |
| Exact clone families | 76 | ≤ 20 | 36 (the rest are detector false positives, `clones.py:194` drops string-valued AST fields, or deliberate per-class shape — `docs/reference/clone-residue.md`) |
| Redundancy clusters ≥3 | 989 | ≤ 600 | 745 (2,786 tests inside; the five distilled areas are at 0–2) |
| Cross-file clusters / implementation mirrors | 24 / 74 | — | 2 / 11 |
| Framework tables in scope | 30 | — | 23 (revisions 0023 and 0024) |

What the phase found that mattered more than the lines: `/_ops/sse/all` streamed every
tenant's entity events to any client, and `/_ops/sse/events` had no auth dependency and let
the client choose the tenant (AE, AO — both closed); the metrics middleware had never had an
emitter and the observability guide described a Redis stream that never existed (AE); the
wheel shipped a Vite SPA (AF); the enterprise-auth and 2FA code paths were live for every app
with no consumer able to exercise them (AD, AG); the `#1399` "prefer the resolved tenant"
branch read a request attribute nothing sets (AO); `expr_field_dependencies` does not descend
into `IfExpr` (AH finding); a permit-denied list request is not audited where update and
delete are (AN finding); `mint_token` accepts a colon email that `verify_token` always rejects
(AM finding); two sentinel scans saved in the same second order at random (AL finding).

Open for the operator after this phase: drop `memberships.external_id` and its unique index
(AD); drop the four 2FA columns on `users` (AG); drop `email_outbox` and `OutboxRepository`
(AI: never constructed); `devices` (ship O) still unsigned; `process_persistence.save_processes`
has no writer while `app_factory.py:805` reads the store (AI); the file-size error message and
python-magic dependence in `file_storage.py` (AK); `sentinel/store.py` same-second scan
ordering (AL); `spec_analyze` relationship extraction takes articles as targets (AL). The §7
targets (≤ 250k / ≤ 200k) remain Phase 7 material: the runtime monoliths (`page_routes.py`,
`server.py`, `auth/store.py`) and features consumers use.

Consumer actions from this phase are in each `FLENSE_*.md` §2 step 6: `dazzle db upgrade head`
now reaches 0024 (seven empty framework tables dropped), confirm no user row has
`totp_enabled`/`email_otp_enabled` set, and AegisMark's enterprise-auth runbook is obsolete.

## 10. Phase 7 — the third flense (planned 2026-10-15, after v0.118.0)

§9.7 closed with the §7 targets (≤ 250k src, ≤ 200k tests) out of reach of evidence-only
cuts. This phase separates what is left into two piles: the evidence-only remainder, which
dispatches at once, and four product decisions, which wait for the operator. It also records
where evidence-only cutting stops, so the §7 numbers can be reaffirmed or revised.

### 10.1 Principles carried forward, one sharpened

- Everything in §3, §9.1 and ADR-0057 still applies; HaTchi-MaXchi stays exempt.
- **A consumer's production path is a consumer.** cyfuture's `app_factory.py` selects
  `EventBusProcessAdapter` over the Redis bus when Heroku sets `REDIS_URL`; no `.dsl`, test
  or `dazzle.toml` grep shows it. Evidence for runtime subsystems therefore includes the
  consumers' Python entry points and deploy configuration, not only their DSL.
- The runtime monoliths are structure, not mass. Splitting `server.py` or `page_routes.py`
  moves lines; it does not remove them. They leave this programme and go to a separate
  "runtime shape" plan once Phase 4's assurance pack says what the runtime must prove.

### 10.2 Evidence (measured 2026-10-15 against v0.118.0 and the three checkouts)

| Finding | Size (src / tests) | Evidence |
|---|---:|---|
| Runtime event transport: `http/events` (redis_bus 889, postgres_bus 919, outbox 509, framework 508, publisher 473, consumer 401, inbox 396, bus 379, dev_memory 373, tier 264, envelope 246, base 223, null 163), `event_explorer.py` 552, `sse_stream.py` + `sse_wiring.py` 489, `channels/outbox.py` 467 | ≈ 7,800 / ≈ 6,700 | cyfuture subscribes to the in-process `EntityEventBus` (`http/runtime/event_bus.py`, kept) and runs `process` through `EventBusProcessAdapter` on the Redis bus in production; no consumer selects the Postgres bus, declares `live: on`, or reads `_dazzle_event_inbox`; `dev_memory` is test-only; the explorer is a dev-mode route; `OutboxRepository` is never constructed (ship AI) |
| `page_routes.py` 3,902: a 476-line per-field-kind filter family at lines 430–905 (`entity_<kind>_filter_fields`, `leftover_honest_filter_<kind>`, `_parse_list_filter_<kind>_values` for nine kinds) and three persona-override walkers at 1203–1448 | ≈ 700 collapsible | one shape per kind; the clone detector misses it because the bodies differ only in string-valued AST fields (`fitness/clones.py:194`) |
| Zero-importer modules after Phase 6 (static scan re-run) | 2,964 | `core/llm_context` 643, `qa/subscription_vision` 515, `core/design_context` 347, `qa/work_surface_utility` 330, `testing/ux/reconciler` 269, `http/runtime/response_helpers` 262, `core/process/context` 250, `qa/evaluate` 181, `qa/hyperpart_dsl_shapes` 127, `fitness/swallows` 40 |
| `testing/` modules with no importer outside `tests/` once relative imports are counted | ≈ 3,000 | `auth_flows` 660, `walk/actions_api` 428, `ux/reconciler` 269, `viewport_screenshot` 249, `cleanup_manager` 236, `ux/seed_values` 218, `ux/interactions/card_add` 212, `ux_catalogue_manifest` 204; `vendor_mock/*` 1,516 reached only through `test populate` (to confirm). Kept: the eight consumer-imported modules, `fuzz_runtime` (fuzz skill), `ux/contract_checker` (card-safety gate), `tier2_playwright`, `e2e_runner`, `viewport*` (CLI-reached) |
| CLI groups with no consumer reach outside prose and no harness reach | ≈ 1,700 / ≈ 1,500 | `analytics` 260, `representation` 136, `rhythm` 162 (the MCP `rhythm` tool stays: AegisMark names it), `vocab` 316 (examples only), `walk` 460 (cyfuture imports `testing.walk`, not the command), `activity` 133, `claims` 131 (unless it backs `docs claims`, cyfuture 12), `prove` 116 (`scripts/example_agent_prove.sh` and the stems skill; examples only). `doctor` (release-cli workflow), `fragment-audit` (CI), `coverage` (preflight), `spec` (ship skill) stay |
| MCP: 19 tools pinned; `spec_analyze` (handler 1,181 plus `spec_questions` 406, `spec_lifecycles` 424, `domain` if only it reads them) and `project` have zero consumer mentions | ≈ 2,500 / ≈ 1,500 | `docs/api-surface/mcp-tools.txt`; `bootstrap` must be re-pointed if it calls `spec_analyze` (ship C flag) |
| `core/grammar_gen.py` 1,703 reached only from `cli/__init__.py` and two tests | 1,703 / ≈ 300 | no `grammar` group is registered; check what in `cli/__init__.py` imports it |
| Vulture ≥ 60 % after ship AI: 629 function/class/method flags | — | mostly typer-decorated commands and pydantic fields (false positives); the real residue is unread IR attributes (`core/ir/workspaces` 54, `sitespec` 43, `themespec` 21, `test_design` 21, `surfaces` 21, `domain` 21, `process` 17, `governance` 16, `llm` 15, `onboarding` 14, `rhythm` 13) and `testing/step_executor.py` 29 |
| Tests 319,714 lines by the package a file mainly imports | — | `core.ir` 64k (223 files), `http.runtime` 55k, `render.fragment` 27k, no-`dazzle`-import harness/docs/fixture tests 25k, `http.specs` 12.8k, `core.errors` 11.8k. Redundancy: 745 clusters spread over ≈ 400 flat `tests/unit` files (deepest: `test_expression_lang.py` 12, `test_rbac_verifier.py` 7, `test_mapping_executor.py` 6, `test_htmx_details.py` 6, `test_vendor_mock_generator.py` 6, `test_schema_diff.py` 5, `test_org_activation.py` 5, `test_csrf_origin_gate_phase2.py` 5, `test_fidelity_scorer.py` 5, `test_scope_rules.py` 5). Largest undistilled: `test_persona_journey.py` 1,464, `test_workspace_rendering.py` 1,344, `test_mapping_executor.py` 1,338, `test_fidelity_scorer.py` 1,273, `test_events.py` 1,178, `test_qa_trial.py` 1,177, `test_testspec_generator.py` 1,122 (`test_hm_contract_dom_conformance.py` 1,782 is HM, exempt) |
| Monoliths (structure, not mass) | — | `server.py` 2,624 (`DazzleBackendApp` with twenty `_mount_*`/`_wire_*` methods), `page_routes.py` 3,902, `auth/store.py` 1,685 (three mixins on `LazyPgStore` after AH), `cli/db.py` 2,380 (24 commands, consumers use most), `dsl_parser_impl/workspace.py` 3,399 and `entity.py` 3,047 (the grammar) |
| Kept and load-bearing (not candidates) | — | `__test__` routes (pennydreadful 51, AegisMark 12, cyfuture 9), `consent_routes` (`analytics` construct: AegisMark, cyfuture), `audit_routes` no-auth twins (only when auth is off), `task_routes` + `core/process` (cyfuture `process`, hr_records), `sentinel` (`sentinel scan`: AegisMark, cyfuture; MCP 4/6), `signing` (AegisMark), `grant_routes` (both regulated consumers), FTS/search/files/documents/bulk/i18n (consumer-declared or consumer-imported) |

### 10.3 Ships

Letters continue from Phase 6. **D** = needs an operator decision before dispatch; the rest
run on evidence alone with the §9.6 mechanics.

| Ship | Scope | Disposition | Expected Δ (src / tests) |
|---|---|---|---:|
| **AP** | `page_routes.py`: the nine-kind filter family becomes one kind-keyed table; the three persona-override walkers share one walker; `http/runtime/response_helpers.py` (zero importers) and the `site_routes.py` vulture residue go | Consolidate | −1.2k / 0 |
| **AQ** | The ten zero-importer modules and the `testing/` modules with no importer outside `tests/`; each verified by `rg` across src (absolute and relative imports), tests, the three checkouts, skills, hooks, Makefile, CI, and `python -m` entry points; tests that only exercised them go | Delete | −5k / −4k |
| **AR** (D) | Event transport residue: `postgres_bus.py`, `dev_memory.py` (its fake moves into `tests/`), `inbox.py` with `_dazzle_event_inbox`, `event_explorer.py` and its dev route, `sse_stream.py` + `sse_wiring.py` + `/_ops/sse/events` + the workspace `live:` flag, `channels/outbox.py` `OutboxRepository` + `email_outbox`; the Redis bus, `null`, `framework`, `publisher`, `consumer`, `outbox` (`_dazzle_event_outbox`), `EventBusProcessAdapter` and the in-process `EntityEventBus` stay | **Park** into DD-006 (extended from the DSL to the transport); revision 0025 drops `_dazzle_event_inbox` and `email_outbox` — **approved 2026-10-16, landed 06d1be1bb; inbox kept (cyfuture production path)** | −3k / −3k |
| **AS** (D) | CLI groups `analytics`, `representation`, `rhythm` (command only), `vocab`, `walk`, `activity`, `prove` with `scripts/example_agent_prove.sh` (stems skill re-pointed to MCP `knowledge counter_prior`), `claims` unless `docs claims` reads it | Delete — **approved 2026-10-16, landed adb829f75; `analytics` and `representation` kept on evidence** | −1.7k / −1.5k |
| **AT** | MCP `spec_analyze` and `project`, with `spec_questions`, `spec_lifecycles`, `domain` and the `domain_brief` residue if nothing else reads them; `bootstrap` re-pointed; `core/grammar_gen.py` if no registered command reaches it | Delete — **result: all three kept, see §10.7** | 0 / 0 |
| **AU** | Unread IR attributes (vulture residue in `core/ir/*`), each verified against the parser's writes and every reader including the consumers' `dazzle.core.ir` imports (AegisMark 9, cyfuture 5); `testing/step_executor.py` residue; `ir-types` baseline regenerated with a CHANGELOG entry | Delete | −1k / −0.5k |
| **AV** | Distillation: the twenty deepest cluster files | Distil | 0 / −5k |
| **AW** | Distillation: `test_persona_journey.py`, `test_workspace_rendering.py`, `test_mapping_executor.py`, `test_fidelity_scorer.py`, `test_qa_trial.py`, `test_testspec_generator.py` | Distil | 0 / −6k |
| **AX** | The 25k lines of tests with no `dazzle` import: fold duplicate harness gates (docs, agents, stems, drift), delete tests pinning features removed in Phases 3–6, keep one gate per invariant | Distil | 0 / −7k |

Rules for AV–AX as in §9.3; AQ and AS must not remove anything cyfuture's `testing.walk`
path, the fuzz skill or the card-safety gate imports.

### 10.4 Decisions needed (before AR and AS are dispatched)

1. **AR — the event transport.** Recommendation: park. cyfuture's production path keeps the
   Redis bus and `EventBusProcessAdapter`; the Postgres bus, the inbox, the explorer, the
   SSE live push and the email outbox have no consumer in any environment. DD-006 already
   holds the events DSL; it grows a transport section naming the restoring commit. Against:
   `live: on` is a cheap demo feature. The AO fix stays in history either way.
2. **AS — the CLI groups.** Recommendation: delete. `prove` is the only one a skill names;
   re-point the stems skill to the MCP `knowledge counter_prior` call it already lists.
3. **Monoliths.** Recommendation: out of scope for the flense. Write the "runtime shape" plan
   after Phase 4's first assurance pack, so the split follows what the runtime must prove.
4. **§7 end-state targets.** Evidence-only cutting stops near 305k src / 285k tests. The
   remaining ≈ 55k src is consumer-used feature mass (signing, grants, FTS, files, documents,
   i18n, processes, SLA, integrations, LLM) that ADR-0057 keeps. Recommendation: revise the
   programme end state to ≤ 300k / ≤ 250k and move the rest to Phase 4's "what the pack
   reveals" and Phase 5's cost-of-change metric.

**Decisions taken (James, 2026-10-16, "go ahead with the recommendations"):** items 1 and 2
shipped as AR and AS (§10.7). Item 3: the monoliths (`server.py`, `page_routes.py`,
`auth/store.py`, `cli/db.py`) are out of the flense's scope; a separate "runtime shape" plan
is written after Phase 4's first consumer assurance pack lands, so the split follows what
the runtime must prove rather than file size. Item 4: the §7 end state is revised to
≤ 300k src / ≤ 250k tests (the §7 table keeps the old figures for the record); the ≈ 18k src
above that line is feature mass ADR-0057 keeps, and any further reduction is a
feature-retirement decision for the operator, surfaced by Phase 4's "what the pack reveals"
and Phase 5's cost-of-change metric, not by evidence-only cutting. Phase 7 was released as
v0.119.0 (commit b74270f11).

### 10.5 Targets for this phase

| Measure | After v0.118.0 | Phase 7 target | Note |
|---|---:|---:|---|
| Framework src lines | 323,851 | ≤ 308,000 | AP, AQ, AT, AU now; AR, AS on decision |
| Test lines | 319,714 | ≤ 290,000 | AV–AX plus the tests of removed code |
| Docs lines in tree | 47,904 | ≤ 48,500 | DD-006 grows |
| Top-level constructs | 31 | 31 | unchanged |
| Zero-importer modules | 10 | 0 | AQ |
| Redundancy clusters ≥3 | 745 | ≤ 650 | AV–AX |

### 10.6 Mechanics

Same loop as §9.6. AP, AQ, AT and AU run on evidence from dispatch; AV–AX follow once the
code ships land (so they distil tests of surviving code); AR and AS wait for §10.4. The
phase closes with a `minor` bump and §10.7 recording the measured numbers.

### 10.7 Result (2026-10-16, nine ships, 660b0bcf4 → 06d1be1bb)

AT, AQ, AP, AU, AV, AW and AX landed on `main` within a day of v0.118.0; the operator
approved AR and AS on 2026-10-16 ("go ahead with the recommendations") and both landed the
same morning. Each ship was gated with `make ci-fast`, pushed under the push gate, CI green on
every pushed tip (one red on 22f2034ea was an npm registry `ECONNRESET` while the ESLint test
fetched eslint; the test now skips on registry failure and the re-run was green). Net −19,780
lines across 257 files (+10,574 / −30,354).

| Measure | After v0.118.0 | Phase 7 target | After AR |
|---|---:|---:|---:|
| Framework src lines | 323,851 | ≤ 308,000 | **318,122** (−5,729; target missed by 10k — evidence-only cutting is exhausted, see below) |
| Test lines | 319,714 | ≤ 290,000 | **308,818** (−10,896; target not met) |
| Docs lines in tree | 47,904 | ≤ 48,500 | 47,831 |
| Top-level constructs | 31 | 31 | 31 |
| Test functions | 14,307 | — | 13,447 |
| Zero-importer modules | 10 | 0 | 0 (3 deleted, 7 kept with a named reach) |
| Redundancy clusters ≥3 | 745 | ≤ 650 | **626** |
| Cross-file clusters / mirrors | 2 / 11 | — | 4 / 9 |
| Tests importing nothing from `dazzle` | 171 files / 24,907 lines | — | 105 / 17,501 |
| Framework tables in scope | 23 | — | 22 (revision 0025 drops `_dazzle_outbox`) |

What the evidence said, ship by ship: **AT** kept all three candidates (`spec_analyze` is the
`bootstrap` entry point and DD-003 names it; `project` is the only writer of the dev-mode
active project; `grammar_gen.py` is `dazzle grammar`, which generates the grammar reference).
**AQ** deleted 3 of 26 modules: the `testing/` "no importer outside tests" premise in §10.2 was
wrong for every module once relative imports were followed — each sits on a kept command path,
and `vendor_mock` starts with every development `dazzle serve` for `pack:` specs (cyfuture
declares six). **AP** collapsed the nine-kind filter family into one registry (`page_routes.py`
3,902 → 3,700, fuzzed old-vs-new on 40k inputs) and kept `response_helpers.with_toast`, which is
the HaTchi-MaXchi toast contract's server emitter. **AU** removed −54 lines: the vulture residue
in `core/ir` is `model_config`, enum vocabulary the parser builds from strings,
decorator-registered validators and wire formats consumers write. **AV–AX** did the test mass:
−852, −2,022 and −5,343 lines, one gate per invariant for the harness tests.

**AS** removed `dazzle rhythm`, `vocab` and `prove` (with the MCP evaluate/propose/fidelity/
lifecycle implementations only the rhythm command reached) and kept `analytics` (every
consumer's `make assure` pack in `FLENSE_*.md` runs `dazzle analytics audit`) and
`representation` (PARKED DD-001 names it). **AR** parked the Postgres bus, the in-memory dev
bus, the event explorer, SSE live push and the channel `OutboxRepository` into DD-006 and
dropped `_dazzle_outbox` (revision 0025); it kept the event inbox, against §10.2's evidence
line, because `EventFramework` wraps every handler in an `IdempotentConsumer` and cyfuture's
`auth.user.registered → cyfuture-provision` handler runs through it in production. Without
`REDIS_URL` the framework now runs the `NullBus` instead of silently selecting Postgres. The
explorer was a security hole: `/_dazzle/events/*` was mounted in every environment with no
auth dependency, exposing event payloads (emails, usernames, roles) and a DLQ replay POST.

Where the src number stands: evidence-only cutting inside the kept subsystems is exhausted at
≈ 318k. The original §7 end state (≤ 250k / ≤ 200k) and the Phase 7 target (≤ 308k) are not reachable
without retiring features consumers use; §10.4 records the 2026-10-16 decision (end state revised to
≤ 300k / ≤ 250k; monoliths deferred to a runtime-shape plan after Phase 4).

Findings for the operator, from the commit bodies: cyfuture's `themespec.yaml` attention-map
rules are silently dropped by `themespec_loader.py:104-110` (shape mismatch, nothing renders
attention maps); AegisMark writes `ErasurePolicy.PSEUDONYMIZE`, which nothing implements; no
gate bans Alpine `x-*` emission from the typed renderers any more and
`page/runtime/static/test-workspace-perf.html` still carries `x-data`; `MANIFEST.in:13` does
not ship the default favicon `.svg` or `static/css/themes/*.toml`, the `dazzle.page` package-data
keys match nothing and `MANIFEST.in:16` still includes the removed `lsp/grammars`;
`fidelity_scorer.py:789` counts a page whose buttons do not match the trigger as satisfying it;
`workspace_region_computes.py:1316` swallows every attention-condition exception;
`tests/integration/test_runtime_e2e.py:346,364` create a Task without the required `task_type`
(8 pre-existing e2e failures); the other `/_dazzle` debug routes (`debug_routes.py:335`) share
the explorer's unauthenticated-everywhere posture; databases that booted without Redis may hold
orphaned `_dazzle_events`/`_dazzle_consumer_offsets`/`_dazzle_dlq` tables (unsigned, not
dropped); `live: on` was always inert in the browser because `htmx-ext-sse.js` was never
vendored; scene evaluations under `.dazzle/evaluations/` are now never written but still read
by the pipeline's `rhythm(gaps)` step; the complexity baseline is behind HEAD (a
`--write-baseline` would loosen 196 ceilings); the HTML page list never date-normalises filter values while the
REST list does (`page_routes.py` ~2245); cyfuture monkeypatches `testing.walk.actions_api`
(`api_ensure_status`, `playwright_click_api_fallback`), so those names are API; the complexity
baseline has never covered ≈ 40 files; DD-010 cites a `ProcessContext.checkpoints` field that
does not exist; `.agents/skills/cimonitor/SKILL.md:81,85` name two deleted tests.
