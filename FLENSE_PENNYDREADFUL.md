# FLENSE_PENNYDREADFUL.md — Phase 4 of the Dazzle flense programme, for an agent working in `/Volumes/SSD/pennydreadful`

This file is the hand-off from the Dazzle framework to the pennydreadful repo. Read it
before touching anything; it is the only brief you get. Framework context lives in the
Dazzle checkout at `/Volumes/SSD/Dazzle`: ADR-0057
(`docs/adr/0057-consumer-forced-growth-and-mass-ratchet.md`), the plan
(`docs/plans/2026-10-11-flense-programme.md`, §4 Phase 4 and §8 Status) and the inventory
(`docs/reference/flense-inventory.md`). Work in this repo only; never edit the framework
from here.

## 0. Why this matters for pennydreadful

pennydreadful is publishing: IP and authorship verification, royalties, rights auctions. It
is not a regulated consumer in the sense AegisMark and cyfuture are, so the assurance pack
is **advisory** here, not a CI gate on day one. pennydreadful matters to the framework for a
different reason: it is the named forcing consumer for two parked designs — the events DSL
(DD-006, ordered or replayable bid streams for rights auctions) and the ledger
(DD-004, royalties). The flense removed both from the framework; the designs are written
down and wait for a real need. Your job is to make the pack run, fix what is obviously
wrong, and, if auctions or royalties need the parked machinery, say so precisely rather
than build it locally.

## 1. Ground truth, measured 2026-10-13 against Dazzle v0.116.0

Pin today: `[tool.uv.sources] dazzle-dsl = { git = …, rev = "edfbb31db…" }` (before the
flense ships). No CI workflow exists in this repo. Every proof command below already runs
against this checkout with the v0.116.0 tree.

| Probe | Result |
|---|---|
| `dazzle validate` / `dazzle lint` | identical output on v0.116.0 and on the pinned SHA |
| `dazzle rbac prove -f json` | `scope_satisfiability` PROVED, `deny_overrides` PROVED, `least_privilege` INFORMATIONAL, `role_hierarchy_acyclic` VACUOUS, `separation_of_duty` VACUOUS; 16 residual notes (FK paths such as `bundle.work.author` abstracted as free symbols) |
| `dazzle rbac matrix -f json` | 7.6k lines; **WARNING: persona `agent` is not referenced in any permission rule** |
| `dazzle rbac routes` / `byte-routes` | OK |
| `dazzle compliance gaps -f iso27001` | 10 gaps, all tier 3 (organisational): A.5.8, A.5.24, A.5.26, A.5.28, A.5.29, A.5.37, A.8.15, A.8.16, A.8.17, A.8.29 |
| `dazzle compliance evidence` | 0 classify, 144 permit, 271 scope, 35 transitions, 16 story, 5 persona, 6 llm_intent |
| `dazzle analytics audit -f json` | 3 PII name hints, 8 subprocessor rows |
| DSL | `guide` ×2, `llm_intent` ×6, `persona` ×5; no `pii`, `signed`, `retention`, `tenancy`, `subprocessor` |

## 2. Step 1 — move the pin to v0.116.0 and absorb the release

v0.116.0 bundles the flense ships (CHANGELOG `## [0.116.0]`, *Removed* and *Agent
Guidance*). One removal names pennydreadful as a non-event: the framework GraphQL BFF is
gone, and pennydreadful's `/graphql` is its own Strawberry schema (`graphql_schema.py`),
untouched. Prove the rest:

1. `pyproject.toml` `[tool.uv.sources]`: replace `rev = "…"` with `tag = "v0.116.0"`.
   `uv lock && uv sync`. If the app relied on the removed `graphql` extra for strawberry,
   add strawberry as a direct dependency.
2. `uv run dazzle validate && uv run dazzle lint` — 0 errors, same warnings.
3. Import every `dazzle.*` module the app uses
   (`grep -rhoE '^(from|import) dazzle[.a-zA-Z_]*' --include='*.py' . | sort -u`, then
   import each). A missing module is a framework bug: file it `consumer-forced`.
4. Migration: framework revision `0022_flense_park_tables` now **drops**
   `_dazzle_atomic_audit`, `_dazzle_ingest_fingerprint` and `join_requests`.
   `uv run dazzle db upgrade head` on dev; pennydreadful keeps its own `migrations/`, so
   check how the framework chain is merged there (the Dazzle doc
   `docs/reference/migrations.md` covers the #1309 merge and the #1689 extra-head case).
   `dazzle db` commands no longer read `.dazzle/runtime.json` (#1775).
5. `tests/` green. Commit the pin bump alone.

## 3. Step 2 — the assurance pack (advisory)

Add `make assure` writing to `assurance/` and commit the output. Same recipe as the
regulated consumers, so the three packs are comparable:

```bash
set -euo pipefail
mkdir -p assurance
uv run dazzle rbac matrix -f json            > assurance/rbac-matrix.json
uv run dazzle rbac prove -f json             > assurance/rbac-prove.json
uv run dazzle rbac routes                    > assurance/rbac-routes.txt
uv run dazzle rbac byte-routes               > assurance/rbac-byte-routes.txt
uv run dazzle rbac report                    > assurance/rbac-report.md
uv run dazzle compliance evidence            > assurance/compliance-evidence.txt
uv run dazzle compliance compile -f iso27001 -o assurance/auditspec-iso27001.json
uv run dazzle compliance gaps -f iso27001    > assurance/gaps-iso27001.txt
uv run dazzle analytics audit -f json        > assurance/pii-audit.json
uv run dazzle compliance privacy -p . -o assurance/privacy
```

Create the repo's first workflow, `.github/workflows/assure.yml`: `uv sync --frozen`,
`dazzle validate`, `dazzle lint`, `make assure`, `git diff --exit-code assurance/`. Keep
`rbac prove`'s exit code as the one hard gate; let the gap count report rather than fail
until the operator says otherwise.

## 4. Step 3 — what is obviously wrong, and what the domain actually needs

1. **Persona `agent` is unreferenced.** Either it has permissions (literary agents acting
   for authors is a real role in rights auctions) and the DSL is missing them, or it is dead
   and should go. Decide from `SPEC.md` and the stories; the matrix must stop warning.
2. **Authorship verification is a signing problem.** The DSL has no `signed` field. If
   pennydreadful claims to verify authorship, the claim of authorship on a `Work` (and the
   acceptance of a rights offer) should be `signed`, so the chain is verifiable the same
   way cyfuture's filings are. Provision with `dazzle signing init`; shape in the Dazzle
   repo under `fixtures/signing_validation` and `examples/support_tickets`.
3. **Residual notes.** 16 FK paths are abstracted as free symbols (`bundle.work.author`,
   `work_id.author`, …). Where the scope rule's meaning is "the author of the work in this
   bundle", declare the FK path form from the **dsl-authoring** skill so the proof is
   discharged rather than assumed; verify each with `dazzle db explain-scope`.
4. **PII and subprocessors.** Three PII hints and eight subprocessor rows; authors' bank
   details for royalties will be PII the moment royalties exist. Declare `pii` now on the
   author-identity fields and `subprocessor` for the payment and email providers.
5. **Royalties and auctions — the forcing test.** If the next feature needs double-entry
   royalty accounting, do not build a ledger in `app/`: read DD-004 (the DSL design is
   parked verbatim there), write the `consumer-forced` issue with the entity names and
   invariants, and the framework reopens the DD as `FORCED`. The same for an ordered,
   replayable bid stream: DD-006. The Postgres and Redis event buses still exist in the
   framework; only the DSL constructs over them were parked.

## 5. What comes back to the framework

`consumer-forced` issues in `manwithacat/dazzle`: the DD-004 / DD-006 forcing issues above
when real; a `dazzle assure` composite command; anything in §2 step 3 that fails to import.

## 6. Rules

- Pin by tag, never by `main`. One pin bump per commit.
- Pack outputs are committed; a diff you cannot explain is a finding.
- No parked construct reimplemented locally; the DD is the design, the issue is the lever.
- Before non-trivial app code, run the counter-prior check (`knowledge counter_prior
  code_shape="…"` via the Dazzle MCP).
- Keep this file; update §1 when the measured numbers change.

## 7. Done when

- [ ] pin at `v0.116.0`, tests green, migrations at the framework head
- [ ] `assure.yml` exists and is green; `assurance/` committed
- [ ] `rbac matrix` 0 warnings (persona `agent` resolved)
- [ ] authorship and offer acceptance `signed`, or a written decision why not
- [ ] `pii` / `subprocessor` declared for author identity and payment providers
- [ ] DD-004 / DD-006 forcing issues filed if royalties or auctions are next, with entities and invariants named
