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

## 7. Targets (end of Phase 3)

| Measure | Now | Target |
|---|---|---|
| Framework src lines | 477k | ≤ 250k |
| Test lines | 426k | ≤ 200k, zero harness-only gates |
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
