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
| **owner** | `owner_role` (the `dazzle_owner` owns it; the runtime serves as a non-owner) · `n_a` |
| **rls** | `fenced` (ENABLE + FORCE RLS) · `non_fenced` · `not_applicable` |
| plus | `in_baseline` (in the ADR-0044 migration baseline) and `boot_ddl_gated` |

## The three classes — and the rule for each

1. **framework_internal** — the tables in the ADR-0044 migration baseline (auth,
   audit, files, params, process, event inbox/outbox, …). The `dazzle_owner` role owns
   them; under split-ownership RLS the runtime serves as a **non-owner** that cannot run
   `CREATE`/`ALTER`/`CREATE INDEX`. **Rule:** any *independent* boot path that creates
   one of these (a store's `_init_db` / `create_table` / `_ensure`) **must self-gate**
   with `skip_boot_schema_ddl()` — in production the migration owns the schema. Tables
   created only by the orchestrator (`ensure_framework_schema`) need no self-gate; the
   server-level startup call is already gated.

2. **app_entity** — the per-DSL entity tables. Created by the migration engine
   (ADR-0045) the framework generates per app; tenant-scoped entities are RLS-**fenced**.
   Not enumerated here (per-app) — represented as one class row. This class includes
   the persisted entities the linker injects into the AppSpec (`DeployHistory`,
   `SessionInfo`, `AIJob`, `AuditEntry`, `FeedbackReport`, `OnboardingState`): the
   project lineage creates them and they belong in its `SCHEMA_SNAPSHOT` (#1851).

3. **tenant_registry** — `public.tenants` + per-tenant schemas; separate tenant
   lifecycle. One class row.

(The former **ops_db** class — tables on the separate `ops_integration` database —
was retired with the orphaned ops platform in #1525, and the **event_bus_transport**
class — the `{prefix}events` / `{prefix}consumer_offsets` / `{prefix}dlq` tables the
PostgreSQL event bus self-created — went with that bus in flense ship AR; see DD-006.)

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

The posture also partitions a tenant-aware dump (`dazzle db dump`, #1788):
`fenced` tables are restored from every per-tenant dump, `non_fenced` ones (and
`alembic_version`, the tenant root and other unfenced app entities) from the
first dump only. `dazzle.db.tenant_dump.classify_tables` reads the live
`pg_class` flags and refuses the dump when they disagree with the DSL or with
this registry.
4. **Refs resolve** — every creator / boot_entry dotted-ref imports cleanly.

## Tracked debt (`known_ungated_issue`)

A framework-internal table whose independent boot path is **currently ungated** is
registered honestly with a `known_ungated_issue` reference — the contract documents it
as debt (instead of failing) until the fix lands, then the gating test flips red to
remind the fixer to clear the marker.

**Currently: none.** Building the registry surfaced four siblings of #1495, all now
resolved — `refresh_tokens` (#1496), `_grants`/`_grant_events` (#1497), `devices`
(#1498), and `_dazzle_outbox` (#1499, which also joined the ADR-0044 baseline; dropped
by revision `0025_flense_park_event_transport` in flense ship AR). The
mechanism stays in place: any future ungated boot path is registered with a
`known_ungated_issue` until gated.

## Relationship to ADR-0044

ADR-0044 owns *how the baseline is built and parity-gated* (the squash, the shared-DDL
orchestrator, the three-way real-PG parity gate). The registry owns *which artifacts
exist and each one's properties*. `IN_SCOPE_TABLES` is now derived from
`in_baseline_tables()` — the single source.
