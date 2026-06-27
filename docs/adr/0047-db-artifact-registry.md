# ADR-0047 — The DB-artifact registry is the single source of truth for DB-artifact metadata

**Status:** Accepted (2026-06-27)
**Builds on:** ADR-0044 (framework migration baseline — the *construction + parity* mechanism), ADR-0045 (snapshot-diff engine), ADR-0017 (Alembic for all schema), ADR-0008 (PostgreSQL-only), ADR-0036/0037 (tenant hierarchy + membership), ADR-0005 (no new singletons)
**Origin:** #1495 (events + process consumer ran ungated boot-DDL → `InsufficientPrivilege` under a non-owner role) and its siblings #1496/#1497/#1498/#1499.

## Decision

Every database artifact the framework manages is declared once, in a pure-data
registry `dazzle.db.artifact_registry` (`DB_ARTIFACTS`). Each artifact declares its
**class**, **creator**, **boot_entry** (the independent startup path that must self-gate,
or `None`), **owner**, **RLS posture**, **baseline membership**, and **boot-DDL
gating**. The registry is the single source of the in-scope framework table set —
`framework_schema_snapshot.IN_SCOPE_TABLES` and the real-PG parity test now both derive
from `in_baseline_tables()` (collapsing a previously triplicated, hand-synced list).

An **executable contract** (`tests/unit/test_db_artifact_contract.py`, static, no DB)
enforces the invariants so the registry cannot rot:

1. **Gating invariant** — every registered `boot_entry` marked `boot_ddl_gated`
   actually *guards* with `if skip_boot_schema_ddl(): return/raise` (AST-checked
   structurally, not by name presence).
2. **Completeness sweep** — every function in the framework tree (tests excluded) that
   issues an app-DB `CREATE TABLE/INDEX` is registered (some artifact's creator /
   boot_entry) or in an explicit, function-level, reasoned allowlist. A new ungated
   boot-DDL path is therefore **un-shippable** — it fails CI until registered, which
   forces the gating decision. The allowlist *is* the excluded-classes list made
   executable.
3. **RLS posture** — the framework never RLS-fences its own internal tables.
4. **Refs resolve** — every creator / boot_entry dotted-ref imports.

Surfaces: `dazzle inspect db-artifacts` (the live per-table lens) and
`docs/reference/db-artifacts.md` (the rules). A `known_ungated_issue` field records a
currently-ungated boot path as tracked debt (the contract documents it instead of
failing; the gating test flips red when the fix lands).

## Context and problem

Diagnosing #1495 required reconstructing five orthogonal facts per table (class,
creator, owner, RLS posture, gating) from scattered ADRs, code comments, and the
emergent behaviour of which function happened to call `skip_boot_schema_ddl()`. The
core enumerable fact — the in-scope table list — was triplicated across
`framework_schema.py`, `framework_schema_snapshot.py`, and the parity test, kept in
sync by hand. Nothing asserted the gating invariant, so the #1495 class shipped and
surfaced only in production logs. Building the registry's contract immediately surfaced
four more latent siblings (#1496/#1497/#1498/#1499), one of which (`_dazzle_outbox`,
#1499) is also missing from the ADR-0044 baseline.

## Consequences

- A new framework table, or a new app-DB boot-DDL path, must register in the registry
  (and decide its gating) or CI fails — the #1495 class is structurally un-shippable.
- `IN_SCOPE_TABLES` has one source; the three hand-synced copies are gone.
- The registry restates some facts that live in DDL (creator dotted-strings); the
  contract (refs-resolve + gating) makes those un-rottable.
- Out of scope (deliberately): no rewrite of the orchestrator DDL; the RLS check is
  static against the generator (live RLS drift stays with `dazzle db verify`); per-app
  entity tables and per-tenant schemas are represented as class-descriptor rows, not
  enumerated.

## Relationship to ADR-0044

ADR-0044 is **not superseded** — there is no reversal, and its three-way parity gate
still catches orchestrator↔baseline drift. Its scope is *narrowed and made explicit*:
ADR-0044 owns *how the baseline is constructed and parity-gated* (the squash, the
shared-DDL orchestrator, the real-PG three-way gate); ADR-0047 owns *which artifacts
exist and each one's metadata*. The boundary is clean — no two documents claim the
in-scope set.

## Rejected

- **A descriptive baseline only** (snapshot + text-diff, like the api-surface family) —
  it flags "something changed" but proves no invariant; a new ungated path could ship
  if the author regenerated the baseline without noticing. The executable contract is
  strictly stronger.
- **A read-only lens that infers properties from code** — fragile (gating inferred
  heuristically) and leaves the triplicated list in place.
- **Folding the decision into ADR-0044** — would rewrite an immutable decision record
  and re-merge the two concerns the boundary deliberately separates.
