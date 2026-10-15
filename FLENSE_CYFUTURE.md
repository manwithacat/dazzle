# FLENSE_CYFUTURE.md — Phase 4 of the Dazzle flense programme, for an agent working in `/Volumes/SSD/cyfuture` (refreshed 2026-10-14 for Dazzle v0.117.0)

This file is the hand-off from the Dazzle framework to the cyfuture repo. Read it before
touching anything; it is the only brief you get. Framework context lives in the Dazzle
checkout at `/Volumes/SSD/Dazzle`: ADR-0057
(`docs/adr/0057-consumer-forced-growth-and-mass-ratchet.md`), the plan
(`docs/plans/2026-10-11-flense-programme.md`, §4 Phase 4 and §8 Status) and the inventory
(`docs/reference/flense-inventory.md`). Work in this repo only; never edit the framework
from here.

## 0. Why this matters for cyfuture

cyfuture's buyers are accountancy practices and their clients: regulatory filings (HMRC
MTD), KYC/AML, document signing, multi-tenant client data. Dazzle's product thesis
(ADR-0057) is that an app built on it can *demonstrate* that client data is isolated per
tenant, every filing is signed and attributable, and every access is provable. That
demonstration is the **assurance pack**: machine-produced proofs and evidence, committed in
this repo, regenerated and diffed in CI. cyfuture already has the most CI of the three
consumers (`dsl-quality.yml`, `db-migrations.yml`, `hmrc-compliance.yml`, …); the pack is
one more gate beside them.

## 1. Ground truth, measured 2026-10-13 against Dazzle v0.116.0, re-validated 2026-10-14 against v0.117.0

Pin today: `dazzle-dsl[signing,sso] @ git+…@518c02a6e` (the ADR-0057 commit, before the
flense ships). Every proof command below already runs against this checkout with the
v0.116.0 tree.

| Probe | Result |
|---|---|
| `dazzle validate` / `dazzle lint` | identical output on v0.116.0 and on the pinned SHA |
| `dazzle validate` on **v0.117.0** (2026-10-14) | exit 0; new lint lines: 12 `W_DECLARED_NOT_READ` (feedback_widget presentation keys, 8 schedule `catch_up:`/`overlap:`, 3 service `stub:`), 1 `W_UNKNOWN_BLOCK_KEY` (`human_task title:` at app.dsl:13116) — all listed in §2 step 7 |
| `dazzle rbac prove -f json` | `scope_satisfiability` PROVED, `deny_overrides` PROVED, `least_privilege` INFORMATIONAL, `role_hierarchy_acyclic` VACUOUS, `separation_of_duty` VACUOUS; 4 residual notes (EXISTS via `PartnershipMember` / `SoleTrader` abstracted as free booleans) |
| `dazzle rbac matrix -f json` | 11.8k lines; **4 WARNINGs**: role `admin` passes `permit` for `HMRCBusiness.delete`, `HMRCObligation.delete`, `HMRCCalculation.delete`, `HMRCAdjustableSummary.delete` but has no matching `scope` rule — those requests 404 at runtime |
| `dazzle rbac routes` | **1 VIOLATION**: `POST /companycontacts` (`routes/company_contact_join.py`) shadows a generated entity route with no `# dazzle:implements <Entity>.<op> via <param>` binding — it bypasses the entity's permit/scope model; also `routes/signup_page.py` has no callable `handler` |
| `dazzle rbac byte-routes` | OK |
| `dazzle compliance gaps -f iso27001` | **16 gaps**, all tier 3, including the data ones: A.5.9 asset inventory, A.5.12 classification, A.5.13 labelling, A.5.31 legal/regulatory requirements, A.5.34 PII, A.8.11 data masking; plus A.5.8, A.5.24, A.5.26, A.5.28, A.5.29, A.5.37, A.8.15, A.8.16, A.8.17, A.8.29 |
| `dazzle compliance evidence` | **0 classify**, 296 permit, 881 scope, 135 transitions, 8 sla, 8 schedule, 1 process, 6 persona, 5 grant_schema |
| `dazzle analytics audit -f json` | 32 PII name hints, 8 subprocessor rows |
| DSL annotations | 44 `sensitive`, 35 `signed`, 14 `sign`, 1 `tenancy`, 8 `sla`, 11 `service`, 2 `integration`; **no `pii`, no `retention`, no `subprocessor` construct** |

The pattern is clear: cyfuture has the richest scope model of the three apps and the
weakest *evidence* model. Six of the sixteen ISO gaps exist because the DSL never says what
the data is.

## 2. Step 1 — move the pin to v0.117.0 and absorb the releases

v0.116.0 bundles the flense ships and v0.117.0 the surgical loop (CHANGELOG `## [0.116.0]`, `## [0.117.0]`, *Removed* and *Agent
Guidance*). Two removals name cyfuture, both as non-events: the `composition` tool
(cyfuture keeps its own `compositionspec.yaml` script) and the messaging DSL (the SLA
`on_breach: notify` still writes a log line, DD-007 names cyfuture as the forcing
consumer when a real channel is needed). Prove the rest:

1. `pyproject.toml`: `…dazzle.git@v0.117.0` (keep `[signing,sso]`). `uv lock && uv sync`.
2. `uv run dazzle validate && uv run dazzle lint` — 0 errors, same warnings.
3. Import every `dazzle.*` module the app uses:
   `grep -rhoE '^(from|import) dazzle[.a-zA-Z_]*' --include='*.py' . | sort -u`, then import
   each. A missing module is a framework bug: file it `consumer-forced` with the line.
4. Migration: framework revision `0022_flense_park_tables` now **drops**
   `_dazzle_atomic_audit`, `_dazzle_ingest_fingerprint` and `join_requests` (operator
   sign-off 2026-10-13). `uv run dazzle db upgrade head` on dev; make sure
   `db-migrations.yml` and the staging release phase reach the new head. `dazzle db`
   commands no longer read `.dazzle/runtime.json` (#1775): pass `--database-url` or
   `DATABASE_URL` explicitly in `db_ops.yaml`-driven scripts.
5. Unit, integration and HMRC harness workflows green. Commit the pin bump alone.
6. **Absorb the v0.117.0 behaviour changes.** The surgical loop (ships H–AC, 2026-10-13/14)
   is released as v0.117.0; read CHANGELOG `## [0.117.0]` *Agent Guidance* first. What changes
   for a running app:

   - **Grants are enforced as declared (ship Q).** `POST /_dazzle/grants` rejects a grant
     without `expires_at` when the relation declares `expiry: required`, rejects an
     `expires_at` beyond `max_duration`, requires `"confirmed": true` when the relation declares
     `confirmation:`, and lets only `approved_by:` roles approve or reject. `GET /_dazzle/grants`
     now lists only the grants the caller is a party to or may grant/approve (ship AC). Audit
     existing `_grants` rows with a null or over-cap `expires_at`; they stay active until revoked.
   - **Search applies scope rules (ship P) and lifecycle filters (ship AA).** `/_dazzle/fts/{entity}`
     and `/_dazzle/search` ran with no scope; they now apply the list endpoint's permit gate and
     scope resolution, and FTS omits soft-deleted and ended temporal rows. Anonymous callers never
     see rows of an entity with access rules on list, search or single reads (ships AA, AC).
   - **Rich text is sanitised on write (ship T) and the plain-text regex denylist is gone (ship W).**
     Fields a surface renders with `widget=rich_text` pass through the allowlist sanitiser on
     create, update, integration write-backs and the test seed route; a value over the field's cap
     is a 422. Plain `text` values are stored byte-for-byte as sent ("one=two" is no longer
     deleted). After the pin bump run `dazzle db resanitize-rich-text --dry-run`, review the
     per-field counts, then `--apply` (per tenant with `--tenant` under schema isolation).
   - **`dazzle validate` now warns on declarations the runtime does not read (ships R, U, X, Z, AC):**
     `W_DECLARED_NOT_READ`, `W_UNKNOWN_BLOCK_KEY` (typos and removed clauses no longer vanish
     silently, including at the top level), `W_CLAUSE_VALUE_IGNORED`, `W_TENANCY_MODE_UNIMPLEMENTED`,
     `W_GRANT_EXPIRY_CONTRADICTION`, `W_GRANT_APPROVER_UNUSED`. Exit codes are unchanged; treat the
     new lines as a to-do list (the app-specific ones are below).
   - **`tenancy: mode:` is applied (ship R).** Both regulated apps declare `shared_schema`, so nothing
     changes; a non-default mode would switch off partition-key injection and RLS and no runtime
     implements it (it now warns).
   - **Islands are not rendered (DD-011)**; only `entity:` has effect. The locale middleware is
     mounted (ship AB), so `param locale.*` defaults and tenant config reach rendered dates. The
     feedback widget mounts again when `feedback_widget: enabled` is declared (ship AB).
   - **Removed, none used by a consumer:** the `dazzle i18n` CLI and string translation (DD-012),
     `dazzle serve --watch-source`, `dazzle test list|feedback|dsl-generate|dsl-coverage|run-all`,
     six `dazzle e2e` wrappers, the `mobile`, `push`, `sendgrid` and `i18n` extras, the
     `analytics: server_side:` clause, and the `extract_guards` semantics operation is now a no-op
     that always returns `[]` (stories carry no constraints).

7. **cyfuture-specific clean-ups the new lint reveals** (each its own commit, `dazzle validate`
   clean of `W_DECLARED_NOT_READ` / `W_UNKNOWN_BLOCK_KEY` / `W_CLAUSE_VALUE_IGNORED` at the end):

   - `scripts/probe_signing.py` (~line 108) creates an `approve_letter` grant without `expires_at`
     and now gets 422: send one no more than 30 days out.
   - Delete `services/dazzle_datetime_display_patch.py` and its `app_factory.py:50-56` call: the
     locale middleware now applies your tenant `locale.timezone`/`locale.date_format`, the patch
     re-implements what `format_cell` does, and its wrapper drops the `host=` keyword the timeline
     builder passes (it breaks timeline cells).
   - `dsl/app.dsl`: `human_task` `title:` at 13116 warns `W_UNKNOWN_BLOCK_KEY` (remove it); the
     eight schedules' `catch_up:`/`overlap:` (12026–12131) and three services' `stub:`
     (13073–13092) warn `W_DECLARED_NOT_READ` (delete them); `feedback_widget`
     `shortcut:`/`categories:`/`severities:` (17) likewise. `.claude/commands/actions.md:69` calls
     `semantics(operation="extract_guards")`, which now always returns `[]`; drop that step.
   - 23 fields on 15 entities are rich text (`Communication.body`, `MLROFlag.narrative`, the
     `CustomerDueDiligence` EDD fields, …): run `db resanitize-rich-text`.
   - `scripts/probe_jinja_usage.py:55` imports `dazzle.ui.runtime.page_routes`, a path dead since
     ADR-0041 (`dazzle.page.runtime` / `dazzle.http.runtime.page_routes`); fix or delete the probe.
   - `AGENTS.md:130` advertises `dazzle test coverage`, which does not exist; the kept `dazzle test`
     commands are `run`, `dsl-run`, `generate`, `walk`, `create-sessions`, `diff-personas`,
     `verify-story`, `populate`, `agent` and `tier2-generate` (`dazzle test --help`).


## 3. Step 2 — the assurance pack

Add `make assure` writing deterministic artefacts to `assurance/`, committed and diffed.

```bash
set -euo pipefail
mkdir -p assurance
uv run dazzle rbac matrix -f json            > assurance/rbac-matrix.json     # must end with "warnings": []
uv run dazzle rbac prove -f json             > assurance/rbac-prove.json      # non-zero exit on a failed property
uv run dazzle rbac routes                    > assurance/rbac-routes.txt      # must end "0 route(s) escape"
uv run dazzle rbac byte-routes               > assurance/rbac-byte-routes.txt
uv run dazzle rbac report                    > assurance/rbac-report.md
uv run dazzle compliance evidence            > assurance/compliance-evidence.txt
uv run dazzle compliance compile -f iso27001 -o assurance/auditspec-iso27001.json
uv run dazzle compliance compile -f soc2     -o assurance/auditspec-soc2.json
uv run dazzle compliance gaps -f iso27001    > assurance/gaps-iso27001.txt
uv run dazzle compliance gaps -f soc2        > assurance/gaps-soc2.txt
uv run dazzle analytics audit -f json        > assurance/pii-audit.json
uv run dazzle compliance privacy -p . -o assurance/privacy   # privacy policy, cookie policy, ROPA
```

Scope proofs: for every entity reachable from a client-facing persona and every verb with a
`scope:` rule, `uv run dazzle db explain-scope <Entity> <verb>` into
`assurance/scopes/<Entity>.<verb>.txt`, generated from the DSL. Tenancy: the Dazzle fixture
`fixtures/tenant_rls` and `tests/integration/test_scope_runtime_pg.py` show the shape of an
RLS proof against real Postgres; cyfuture's `integration-tests.yml` has the database, so add
the cross-tenant read attempt there as a test that must fail with 404, per entity with
`tenancy`.

CI: extend `dsl-quality.yml` (it already syncs and validates) with `make assure` and
`git diff --exit-code assurance/`; add `assurance/gaps-baseline.json` with a rise-fails
ratchet; `rbac routes` must report zero escapes and `rbac matrix` zero warnings.
Optional with the database: `dazzle rbac access-review --database-url … -f json` as JML
evidence per tenant.

## 4. Step 3 — close what the pack shows, in cyfuture's own terms

1. **Four `admin` delete permits with no scope rule** (`HMRCBusiness`, `HMRCObligation`,
   `HMRCCalculation`, `HMRCAdjustableSummary`). Either add the `scope:` rule with `as:` so
   the permit is real, or remove the permit so the matrix says what the runtime does.
   Filings are the regulated object; an "allowed but 404s" delete is exactly the kind of
   thing an auditor asks about.
2. **`POST /companycontacts` outside the matrix.** Add the
   `# dazzle:implements <Entity>.<op> via <param>` binding to
   `routes/company_contact_join.py`, or call `check_entity_op(...)` inside it. Fix
   `routes/signup_page.py` so the scanner can read it.
3. **Say what the data is.** The DSL has 44 `sensitive` fields and no `classify`, no `pii`,
   no `retention`, no `subprocessor`. The six data-control gaps (A.5.9, A.5.12, A.5.13,
   A.5.31, A.5.34, A.8.11) close by declaring, not by writing documents: `classify` on the
   KYC/AML and filing entities, `pii` on the 32 fields the audit names, `retention` where
   HMRC and AML rules fix a period (the framework warns no sweep runs it; see §5),
   `subprocessor` for HMRC, the signing provider, email and hosting. Regenerate the pack
   after each and watch the gap count fall; it is the evidence of the work.
4. **Separation of duty** is VACUOUS because none is declared. Maker-checker on a filing
   (preparer is not the submitter) and on client money, if any, is the obvious first SoD
   rule; the `invoice_ops` example in the Dazzle repo shows the maker-checker transition
   shape. Role hierarchy likewise if the practice has partner/manager/junior.
5. **Signing.** 35 `signed` fields across filings and engagement letters. Verify against
   `fixtures/signing_validation` in the Dazzle repo that each produces a verifiable chain
   and record it; `dazzle signing init` provisions the CA if the project has none.
6. **Tier-3 organisational gaps.** Incident management, logging, monitoring, clock sync,
   security testing, documented procedures: evidence what cyfuture already has (the HMRC
   harness runs, the staging smoke job, hosting logs) in the form the compiler expects, and
   list the rest as real gaps. Do not invent evidence.
7. **Customer-facing summary.** `assurance/summary.md` for a practice's compliance partner
   and for the firm's own AML officer, rendered with `dazzle compliance render`; DSL refs
   checked by `dazzle compliance validate-citations`.

## 5. What comes back to the framework

File `consumer-forced` issues in `manwithacat/dazzle` for what the pack cannot express.
Expected from this checkout: a `dazzle assure` composite command; a retention sweep once
retention is declared; messaging for `on_breach: notify` if a log line is not enough
(DD-007 names cyfuture — the design is already written, reopen it rather than redesign);
client-money ledger if cyfuture holds it (DD-004). Do **not** reintroduce a parked
construct locally.

## 6. Rules

- Pin by tag, never by `main`. One pin bump per commit.
- Pack outputs are committed and reviewed like code; a diff you cannot explain is a finding.
- No new route in `routes/` that shadows a generated entity route without a
  `# dazzle:implements` binding; `rbac routes` stays at zero escapes.
- Scope rules follow the forms in the Dazzle **dsl-authoring** skill; verify every new
  one with `dazzle db explain-scope`.
- Before non-trivial app code, run the counter-prior check (`knowledge counter_prior
  code_shape="…"` via the Dazzle MCP).
- Keep this file; update §1 when the measured numbers change.

## 7. Done when

- [ ] pin at `v0.117.0`, all workflows green, migrations at the framework head
- [ ] `dazzle validate` emits no `W_DECLARED_NOT_READ` / `W_UNKNOWN_BLOCK_KEY` / `W_CLAUSE_VALUE_IGNORED` line
- [ ] `dazzle db resanitize-rich-text --apply` run per environment; grant clients send `expires_at` and `confirmed`
- [ ] `rbac matrix` 0 warnings, `rbac routes` 0 escapes
- [ ] `make assure` exists, `assurance/` committed, CI fails on drift and on a rising gap count
- [ ] `classify`, `pii`, `retention`, `subprocessor` declared; ISO gaps below 10 and falling
- [ ] SoD declared for filings; `rbac prove` has no VACUOUS property cyfuture's domain needs
- [ ] cross-tenant read test in `integration-tests.yml` per `tenancy` entity
- [ ] `assurance/summary.md` rendered; framework asks filed as `consumer-forced` issues
