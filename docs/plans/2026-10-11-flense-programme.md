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

Known nuisances: the HaTchi-MaXchi prose-drift tests fail when run from the framework root
(pre-existing; they pass in the package's own gate), and `test_api_surface_drift[ir_types]`
is order-dependent after the presentation MCP tests in one process.
