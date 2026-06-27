# DB Artifacts

Every database artifact the framework manages is declared once, in the **DB-artifact
registry** (`dazzle.db.artifact_registry`). This page is the agent-readable entry
point: read it (or run `dazzle inspect db-artifacts`) before adding a table, boot-DDL,
or RLS to the framework. The registry is the source of truth; an **executable
contract** (`tests/unit/test_db_artifact_contract.py`) enforces the invariants below.

See also: ADR-0047 (this registry) · ADR-0044 (the migration-baseline mechanism) ·
#1495 (the bug class this governs).

## Why this exists

Diagnosing a database bug used to mean reconstructing five orthogonal facts per table
from scattered ADRs and code comments. The registry collapses that into one lookup.

```bash
dazzle inspect db-artifacts                       # the live per-table table
dazzle inspect db-artifacts --json                # machine-readable
dazzle inspect db-artifacts --class ops_db        # filter by class
```

## The five dimensions

Each artifact declares:

| Dimension | Meaning |
|---|---|
| **class** | which family it belongs to (below) |
| **creator** | the function that issues the `CREATE TABLE/INDEX` DDL |
| **boot_entry** | the *independent* startup path that runs the creator at every boot (or `None` if it is created only by the orchestrator) |
| **owner** | `owner_role` (the `dazzle_owner` owns it; the runtime serves as a non-owner) · `runtime_self` (the creating connection owns it) |
| **rls** | `fenced` (ENABLE + FORCE RLS) · `non_fenced` · `not_applicable` |
| plus | `in_baseline` (in the ADR-0044 migration baseline) and `boot_ddl_gated` |

## The five classes — and the rule for each

1. **framework_internal** — the tables in the ADR-0044 migration baseline (auth,
   audit, files, params, process, event inbox/outbox, …). The `dazzle_owner` role owns
   them; under split-ownership RLS the runtime serves as a **non-owner** that cannot run
   `CREATE`/`ALTER`/`CREATE INDEX`. **Rule:** any *independent* boot path that creates
   one of these (a store's `_init_db` / `create_table` / `_ensure`) **must self-gate**
   with `skip_boot_schema_ddl()` — in production the migration owns the schema. Tables
   created only by the orchestrator (`ensure_framework_schema`) need no self-gate; the
   server-level startup call is already gated.

2. **event_bus_transport** — the `{prefix}events` / `{prefix}consumer_offsets` /
   `{prefix}dlq` tables created by `PostgresBus`. **Excluded** from the baseline (dynamic
   prefix); they **self-create** on their own connection. Not subject to the non-owner
   posture.

3. **ops_db** — tables on the separate `ops_integration` database (deployment history,
   spec versions, analytics, …). Own lifecycle, separate connection; not app-DB tables.

4. **app_entity** — the per-DSL entity tables. Created by the migration engine
   (ADR-0045) the framework generates per app; tenant-scoped entities are RLS-**fenced**.
   Not enumerated here (per-app) — represented as one class row.

5. **tenant_registry** — `public.tenants` + per-tenant schemas; separate tenant
   lifecycle. One class row.

## The gating rule (the #1495 class)

The bug class #1495 governs: a framework-internal table's **independent boot path runs
`CREATE INDEX` ungated**, which raises `InsufficientPrivilege` for the non-owner runtime
role under split-ownership RLS — even when the index already exists. The fix is always
the same one-line gate:

```python
def _init_db(self) -> None:
    if skip_boot_schema_ddl():       # production: the migration owns the schema
        logger.info("… migrations own the schema (#1495).")
        return
    ...  # CREATE TABLE / CREATE INDEX
```

## What the contract enforces (so the registry can't rot)

`tests/unit/test_db_artifact_contract.py` (static, no DB) asserts:

1. **Gating invariant** — every registered `boot_entry` that is `boot_ddl_gated`
   actually *guards* with `if skip_boot_schema_ddl(): return/raise` (AST-checked).
2. **Completeness sweep** — every function in the framework tree (tests excluded) that
   issues an app-DB `CREATE TABLE/INDEX` is *registered* (some artifact's creator /
   boot_entry) or in an explicit, reasoned allowlist. A new ungated path is therefore
   **un-shippable** — it fails CI until registered, which forces the gating decision.
3. **RLS posture** — the framework never RLS-fences its own internal tables (RLS is
   app-entity-only); any `fenced` framework row would fail.
4. **Refs resolve** — every creator / boot_entry dotted-ref imports cleanly.

## Tracked debt (`known_ungated_issue`)

A framework-internal table whose independent boot path is **currently ungated** is
registered honestly with a `known_ungated_issue` reference — the contract documents it
as debt (instead of failing) until the fix lands, then the gating test flips red to
remind the fixer to clear the marker. Current tracked siblings of #1495:

| Table | Issue |
|---|---|
| `refresh_tokens` | #1496 |
| `_grants` / `_grant_events` | #1497 |
| `devices` | #1498 |
| `_dazzle_outbox` | #1499 (also: missing from the ADR-0044 baseline) |

## Relationship to ADR-0044

ADR-0044 owns *how the baseline is built and parity-gated* (the squash, the shared-DDL
orchestrator, the three-way real-PG parity gate). The registry owns *which artifacts
exist and each one's properties*. `IN_SCOPE_TABLES` is now derived from
`in_baseline_tables()` — the single source.
