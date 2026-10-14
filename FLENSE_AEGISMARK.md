# FLENSE_AEGISMARK.md — Phase 4 of the Dazzle flense programme, for an agent working in `/Volumes/SSD/AegisMark`

This file is the hand-off from the Dazzle framework to the AegisMark repo. Read it before
touching anything; it is the only brief you get. Framework context lives in the Dazzle
checkout at `/Volumes/SSD/Dazzle`: ADR-0057
(`docs/adr/0057-consumer-forced-growth-and-mass-ratchet.md`), the plan
(`docs/plans/2026-10-11-flense-programme.md`, §4 Phase 4 and §8 Status) and the inventory
(`docs/reference/flense-inventory.md`). Work in this repo only; never edit the framework
from here.

## 0. Why this matters for AegisMark

AegisMark's buyers are state schools and trusts: safeguarding, data protection and
high-stakes formative marking. Dazzle's product thesis (ADR-0057) is that an app built on
it can *demonstrate* to those buyers that their data is secure, auditable and governed. That
demonstration is the **assurance pack**: a set of machine-produced proofs and evidence,
committed in this repo, regenerated and diffed in CI, that a non-technical buyer can be
handed. Today nobody runs it. Phase 4 makes AegisMark the first app that does.

## 1. Ground truth, measured 2026-10-13 against Dazzle v0.116.0

Pin today: `dazzle-dsl[serve,redis,mcp,signing] @ git+…@6a7f34752` (before the flense
ships). Every proof command below already runs cleanly against this checkout with the
v0.116.0 tree, so the pack can be assembled before any DSL changes.

| Probe | Result |
|---|---|
| `dazzle validate` / `dazzle lint` | identical output on v0.116.0 and on the pinned SHA |
| `dazzle rbac prove -f json` | `scope_satisfiability` PROVED, `deny_overrides` PROVED, `least_privilege` INFORMATIONAL, `role_hierarchy_acyclic` VACUOUS, `separation_of_duty` VACUOUS; 12 residual notes (FK paths abstracted as free symbols) |
| `dazzle rbac matrix -f json` | 22.6k lines, 0 warnings |
| `dazzle rbac routes` | "every domain route is matrix-represented", **but** the scan cannot import `pipeline` (`routes/wonde_webhook_health.py`), so part of the route surface was not inspected |
| `dazzle rbac byte-routes` | OK |
| `dazzle compliance gaps -f iso27001` | 10 gaps, all tier 3: A.5.8, A.5.24, A.5.26, A.5.28, A.5.29, A.5.37, A.8.15, A.8.16, A.8.17, A.8.29 |
| `dazzle compliance evidence` | 111 classify, 354 permit, 612 scope, 104 transitions, 10 persona, 5 llm_intent, 3 archetype, 2 grant_schema; 0 sla, 0 process, 0 visible |
| `dazzle analytics audit -f json` | 31 PII name hints, 12 subprocessor rows |
| DSL annotations | 11 `pii`, 10 `retention`, 18 `signed`, 4 `subprocessor`, 1 `tenancy`, 1 `policies` |

## 2. Step 1 — move the pin to v0.117.0 and absorb the releases

v0.116.0 bundles the flense ships and v0.117.0 the surgical loop (CHANGELOG `## [0.116.0]`, `## [0.117.0]`, section *Removed*, plus
*Agent Guidance*). Nothing AegisMark's DSL or Python uses was removed — every removal was
gated on the consumer inventory — but prove it here rather than trust it:

1. In `pyproject.toml` change the git ref to the tag: `…dazzle.git@v0.117.0` (keep the
   extras; `serve`, `redis`, `mcp` and `signing` all still exist). `uv lock && uv sync`.
2. `uv run dazzle validate && uv run dazzle lint` — expect 0 errors and the same
   warnings as before.
3. List every framework import and import each one:
   `grep -rhoE '^(from|import) dazzle[.a-zA-Z_]*' --include='*.py' . | sort -u` then
   `uv run python -c 'import <module>'` for each. Anything missing is a framework bug:
   file it in `manwithacat/dazzle` with label `consumer-forced`, quoting the import.
4. Migration: framework revision `0022_flense_park_tables` now **drops**
   `_dazzle_atomic_audit`, `_dazzle_ingest_fingerprint` and `join_requests` (operator
   sign-off 2026-10-13). AegisMark merged the framework chain under #1309, so
   `uv run dazzle db upgrade head` applies the extra framework head (#1689). Run it on
   the dev database, then confirm `scripts/test_db_setup.sh` (used by `tests.yml`) reaches
   the same head. `dazzle db` commands no longer read `.dazzle/runtime.json` (#1775, the bug
   AegisMark hit): pass `--database-url` or `DATABASE_URL` explicitly.
5. Full test suite green. Commit the pin bump on its own, as the CHANGELOG here records
   framework bumps.

## 3. Step 2 — the assurance pack

Add a `make assure` target (or `scripts/assure.sh`) that writes deterministic artefacts to
`assurance/` and commits them. Every JSON output is sorted and stable so `git diff` is the
review surface.

```bash
set -euo pipefail
mkdir -p assurance
uv run dazzle rbac matrix -f json            > assurance/rbac-matrix.json
uv run dazzle rbac prove -f json             > assurance/rbac-prove.json      # non-zero exit on a failed property
uv run dazzle rbac routes                    > assurance/rbac-routes.txt
uv run dazzle rbac byte-routes               > assurance/rbac-byte-routes.txt
uv run dazzle rbac report                    > assurance/rbac-report.md
uv run dazzle compliance evidence            > assurance/compliance-evidence.txt
uv run dazzle compliance compile -f iso27001 -o assurance/auditspec-iso27001.json
uv run dazzle compliance compile -f soc2     -o assurance/auditspec-soc2.json
uv run dazzle compliance gaps -f iso27001    > assurance/gaps-iso27001.txt
uv run dazzle compliance gaps -f soc2        > assurance/gaps-soc2.txt
uv run dazzle analytics audit -f json        > assurance/pii-audit.json
uv run dazzle compliance privacy -p . -o assurance/privacy   # privacy policy, cookie policy, ROPA from the AppSpec
```

Then the scope proofs. For every entity that carries a `pii` field or a `retention`
clause, and for every verb with a `scope:` rule, record
`uv run dazzle db explain-scope <Entity> <verb>` into `assurance/scopes/<Entity>.<verb>.txt`.
Generate the list from the DSL rather than by hand so a new entity cannot be missed.

CI (`.github/workflows/tests.yml` already has Postgres):

- a job that runs `make assure` and fails on `git diff --exit-code assurance/`;
- a gaps ratchet: `assurance/gaps-baseline.json` holds the count per framework; a rise
  fails the build, a fall rewrites the baseline;
- `dazzle rbac prove` exit code is already a gate; keep it so.
- optional, needs the DB: `uv run dazzle rbac access-review --database-url "$TEST_DATABASE_URL" -f json`
  against the migrated CI database, as the JML (joiner/mover/leaver) evidence.

## 4. Step 3 — close what the pack shows, in AegisMark's own terms

Work these in order; each is a commit with the regenerated `assurance/` diff.

1. **Make the route scan real.** `rbac routes` could not import `pipeline`. Run it with the
   app on `PYTHONPATH` (or fix the import in `routes/wonde_webhook_health.py`) until the
   scan reports every override; a route the scanner cannot read is a route outside the
   proof.
2. **Safeguarding data boundary.** For each of the 11 `pii` fields and every entity a
   `student`, `parent` or `safeguarding` persona touches, the `explain-scope` output must
   show the predicate that stops a teacher in one school reading another school's pupils.
   Any entity where the proof relies on a "free symbol" (the 12 residual notes name the FK
   paths) is a place to either declare the FK path explicitly in the scope rule or
   accept the note in writing in `assurance/README.md`.
3. **Separation of duty and role hierarchy** are VACUOUS because the DSL declares none.
   High-stakes marking needs at least one: the person who marks is not the person who
   moderates, and the person who approves a data export is not its requester. Declare them
   in the DSL so the property becomes PROVED rather than vacuous.
4. **Retention.** Ten `retention` clauses are declared; the framework warns that no sweep
   runs them (CHANGELOG 0.116.0, ship F). Decide per entity whether a retention sweep is
   an app job (AegisMark runs Heroku Scheduler) and document the control in
   `assurance/README.md`; if the framework should own it, file a `consumer-forced` issue
   naming the entities and periods.
5. **Signing.** 18 `signed` fields cover marks and reports. Verify against the framework
   fixture shape `fixtures/signing_validation` in the Dazzle repo that each signed field
   produces a verifiable chain (`dazzle signing init` provisions the CA if the project has
   none) and record the verification in the pack.
6. **Tier-3 ISO gaps.** The ten gaps are organisational controls (incident management,
   logging, monitoring, clock sync, security testing, documented procedures). Each is either
   evidenced by something AegisMark already has (Heroku logs, the `tests.yml` run, this
   pack itself for A.8.29) — then write the evidence file the compiler expects — or it is a
   real gap to list for the operator. Do not invent evidence.
7. **Customer-facing summary.** `dazzle compliance render` turns a markdown document into a
   branded PDF. Write `assurance/summary.md` for a school's data-protection officer: what is
   proved, what is evidenced, what is a known gap; cite DSL refs (`DSL ref: Entity.construct`)
   and check them with `dazzle compliance validate-citations`.

## 5. What comes back to the framework

File an issue in `manwithacat/dazzle`, label `consumer-forced`, for anything the pack cannot
express. Expected candidates, judged from this checkout: a single `dazzle assure` command
composing the steps above; a retention sweep; a route scanner that honours the app's
import path; `least_privilege` moving from INFORMATIONAL to a proof. Do **not** reintroduce
parked constructs (`job`, `atomic`, events, messaging — see the DDs in
`docs/decisions/`); if AegisMark needs one, the issue names the need and the DD is the
place the design already lives.

## 6. Rules

- Pin by tag, never by `main`. One pin bump per commit, recorded in this repo's CHANGELOG.
- The pack's outputs are committed and reviewed like code. A diff you cannot explain is a
  finding, not noise.
- No new Python in `routes/` or `pipeline/` that bypasses `permit`/`scope`
  (`rbac routes` must stay clean; a shadowing override needs a `# dazzle:implements` binding).
- Before non-trivial app code, run the counter-prior check the Dazzle AGENTS.md describes
  (`knowledge counter_prior code_shape="…"` via the Dazzle MCP).
- Keep this file; update §1 when the measured numbers change, so the next agent inherits
  the real state.

## 7. Done when

- [ ] pin at `v0.117.0`, tests green, `db upgrade head` at the framework head
- [ ] `make assure` exists, `assurance/` committed, CI fails on drift and on a rising gap count
- [ ] `rbac routes` scans every override (no import errors)
- [ ] `rbac prove`: no VACUOUS property that AegisMark's domain needs; residual notes accepted in writing
- [ ] `assurance/summary.md` rendered and readable by a DPO
- [ ] framework asks filed as `consumer-forced` issues with the pack output attached

## 8. Framework changes on `main` after v0.116.0 that need action here

The surgical loop that followed the release (ships H–AC on 2026-10-13/14) was released
as **v0.117.0** on 2026-10-14 (CHANGELOG `## [0.117.0]`, read its *Agent Guidance* first). It
changed behaviour your app relies on. Pin to v0.117.0 — it carries everything in v0.116.0 —
and treat the items below as part of Step 1.

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

**AegisMark-specific lines from the loop:**
- Clients creating `acting_hod` or `cover_access` grants must send `expires_at` (≤ 90 d / ≤ 30 d)
  and `"confirmed": true`. `department_observer.granted_by`'s `has_grant("acting_hod", department)`
  term is now evaluated (ship AA).
- `dsl/app.dsl` ~12935–12993: ten stray `scope:` blocks after a `rhythm` were never parsed and
  now warn `W_UNKNOWN_BLOCK_KEY`; delete them. `llm_config` `artifact_store:` (3223) and
  `entity_card_config` `scope_param:` (10907) warn `W_DECLARED_NOT_READ`; grant
  `principal_label:`/`revoke_verb:` are still presentation-only.
- Re-enable the `feedback_widget` commented out at `dsl/app.dsl:99–106` (dazzle#869 is fixed and
  mounting is now idempotent).
- 42 fields on 26 entities are rich text (`ConsentTemplate.body_html`, `SafeguardingConcern.*`,
  `Question.*`, `MarkingResult.*`, …): run `db resanitize-rich-text` with priority on
  `SafeguardingConcern` and `ConsentTemplate`.
- `AGENTS.md:442` advertises `dazzle test coverage`, which does not exist; the kept commands
  are `dazzle test run` and `dazzle test dsl-coverage`.
