# Alembic Migration System — Design Spec

**Date:** 2026-03-23
**Status:** Approved
**Scope:** Replace hand-rolled migration planner with Alembic, add safe type casting, tenant support
**Issue:** #625

## Problem

Dazzle's hand-rolled `MigrationPlanner` (~300 lines) reimplements schema diffing poorly:
- Type changes are detected but never applied (`CHANGE_TYPE` has no SQL generation)
- No rollback capability
- No migration history or audit trail
- No per-tenant schema migration support
- The #624 type mapping fix means new schemas are correct, but existing schemas have ~70% of columns as TEXT

## Decision: Replace with Alembic

Alembic is SQLAlchemy's own migration tool. We already have SA models via `sa_schema.py`. Alembic provides everything our hand-rolled code doesn't: autogenerate diffing, type change detection, upgrade/downgrade, migration history, and schema targeting.

## Philosophy

**Deterministic where unambiguous.** DSL → schema mapping is a pure function. If the DSL changes, the required migration is calculable without human intervention. Safe type casts (text→uuid, text→date, etc.) are applied automatically. Unsafe changes are flagged for review.

**LLM cognition for edge cases only.** Column renames (which Alembic can't distinguish from drop+add) and data migrations are the only cases that might need human or LLM judgment. Everything else is deterministic.

## Architecture

```
DSL → Parser → IR → build_metadata() → SA MetaData
                                            ↓
                                    Alembic autogenerate
                                            ↓
                                    diff against live DB
                                            ↓
                                    Migration file (.py)
                                            ↓
                                    upgrade() / downgrade()
```

## Three Modes

| Mode | Trigger | Behavior |
|------|---------|----------|
| Dev auto-migrate | `dazzle serve` startup | Generate + apply safe migrations silently |
| Explicit migrate | `dazzle db migrate` | Generate + apply with full output |
| Production guard | `dazzle serve --production` | Refuse to start if pending migrations exist |

## Safe Cast Registry

A lookup table of type conversions that Postgres can perform losslessly:

```python
SAFE_CASTS: dict[tuple[str, str], str] = {
    ("TEXT", "UUID"): "{col}::uuid",
    ("TEXT", "DATE"): "{col}::date",
    ("TEXT", "TIMESTAMPTZ"): "{col}::timestamptz",
    ("TEXT", "JSONB"): "{col}::jsonb",
    ("TEXT", "BOOLEAN"): "{col}::boolean",
    ("TEXT", "INTEGER"): "{col}::integer",
    ("DOUBLE PRECISION", "NUMERIC"): "",  # lossless widening
}
```

Alembic's `compare_type` callback detects type mismatches. A post-processing pass on the generated operations injects `USING <cast>` clauses for safe casts and marks unsafe changes. If a type change is not in `SAFE_CASTS`:
- **Dev mode:** skipped with a logged warning (schema drifts until explicitly resolved)
- **Production mode:** blocked until explicitly resolved via `dazzle db migrate`

## CLI Commands

### `dazzle db migrate`

Generate and apply pending migrations.

```bash
dazzle db migrate                  # Generate + apply (all changes including safe casts)
dazzle db migrate --check          # Dry-run: diff DSL spec against live DB, show mismatches
dazzle db migrate --sql            # Print SQL without applying
dazzle db migrate --tenant X       # Apply to specific tenant schema
dazzle db migrate --all-tenants    # Apply to all tenant schemas in sequence
```

`--check` doubles as the schema comparison tool requested in #625 — it diffs the DSL-derived schema against the live DB and reports all mismatches without generating or applying a migration file.

The original `--fix-types` flag from #625 is subsumed by the general `migrate` command — Alembic's autogenerate detects type mismatches as part of the normal diff. There's no need for a separate flag because type corrections are just another kind of migration step.

### `dazzle db rollback`

Revert migrations.

```bash
dazzle db rollback             # Undo last migration
dazzle db rollback <revision>  # Downgrade to specific revision
dazzle db rollback --tenant X  # Undo for tenant schema
```

### `dazzle db status`

Show current migration state (already exists, enhanced with Alembic revision info and per-tenant status).

## Migration Files

Stored in `migrations/versions/` (project root, committed to git). Each migration is an auto-generated Python file:

```python
"""add_priority_field_to_task

Revision ID: a1b2c3d4
Revises: e5f6g7h8
"""
from alembic import op
import sqlalchemy as sa

def upgrade():
    op.add_column('Task', sa.Column('priority', sa.Text()))

def downgrade():
    op.drop_column('Task', 'priority')
```

Migration files are committed to version control. This follows Alembic/Django convention — shared migration history ensures all developers and CI have the same baseline. The `.dazzle/` directory is already gitignored for other artifacts, so migrations live at a project-level `migrations/` directory instead (alongside `dsl/`).

## Alembic Environment

Configured programmatically — no `alembic.ini`. The environment module (`alembic_env.py`) provides:

- `target_metadata()` — builds SA MetaData from current DSL via `build_metadata(entities)`
- `run_migrations_online()` — connects to DATABASE_URL, runs migration with schema targeting
- Tenant support: wraps migration execution in `SET search_path TO <schema>, public`

## Serve Integration

In `serve.py`, after infrastructure validation:

**Dev mode (`dazzle serve`):**
1. Run Alembic autogenerate
2. If changes detected: apply safe migrations, log summary
3. If unsafe changes: skip them, log warning, continue

**Production mode (`dazzle serve --production`):**
1. Run Alembic `current()` check
2. If head matches: proceed
3. If pending migrations: exit with error message directing to `dazzle db migrate`

## What Gets Retired

| File/Code | Lines | Replacement |
|---|---|---|
| `MigrationPlanner` class | ~200 | Alembic autogenerate |
| `_plan_entity_migration()` | ~100 | Alembic autogenerate |
| `_generate_create_table_sql()` | ~30 | Alembic `op.create_table()` |
| `_generate_add_column_sql()` | ~15 | Alembic `op.add_column()` |
| `_generate_column_def()` | ~25 | SA column types via `sa_schema.py` |
| `auto_migrate()` function | ~40 | Alembic upgrade |

**Total removed:** ~400 lines of hand-rolled migration code.

**Retained:**
- `MigrationAction` enum, `MigrationStep`, `MigrationPlan` — used by CLI reporting
- `get_table_schema()` — used by MCP `db status` tool
- `SAFE_CASTS` registry — new, used by Alembic hook

## Error Messages

| Condition | Message |
|---|---|
| Dev serve, safe migration | `  Auto-migrated: 3 columns type-corrected (text→uuid)` |
| Dev serve, unsafe change | `  Warning: column 'price' type change (integer→text) skipped. Run 'dazzle db migrate' to review.` |
| Production, pending migrations | `Cannot start in production mode: 2 pending migrations. Run 'dazzle db migrate' first.` |
| `dazzle db migrate --check` | Table of planned changes with safe/unsafe markers |
| `dazzle db rollback`, no history | `No migrations to roll back.` |

## Deferred

These items from #625 are acknowledged but deferred to future work:

- **Canary tenant strategy** — migrate one tenant first, validate, then roll out. Implementable as a wrapper around `--tenant X` but not needed until there are many tenants.
- **`money(CUR)` type mapping** — `money(CUR)` already expands to `_minor` (integer) + `_currency` (text) columns at the IR level. The migration system handles these as normal columns. If we want `numeric(12,2)` instead, that's a separate DSL type mapping change.
- **Cross-tenant consistency checks** — detecting drift between tenant schemas. Can be built on top of `--check` by running it against each tenant and comparing results. Deferred until multi-tenant deployments are common.

## Dependencies

- `alembic>=1.13` — added as a required dependency (not optional)
- `sqlalchemy>=2.0` — already a dependency

## File Structure

| File | Action | Responsibility |
|------|--------|----------------|
| `src/dazzle_back/runtime/alembic_env.py` | Create | Programmatic Alembic environment |
| `src/dazzle_back/runtime/migrations.py` | Modify | Retire MigrationPlanner, add SAFE_CASTS |
| `src/dazzle_back/runtime/sa_schema.py` | Keep | Authoritative schema bridge (already fixed in #624) |
| `src/dazzle/cli/db.py` | Modify | Add `migrate`, `rollback` subcommands |
| `src/dazzle/cli/runtime_impl/serve.py` | Modify | Integrate auto-migrate on dev startup |
| `pyproject.toml` | Modify | Add `alembic` dependency |
| `tests/unit/test_safe_casts.py` | Create | Test safe cast registry |
| `tests/integration/test_alembic_migrate.py` | Create | Integration test with real Postgres |

## Testing

- Unit: SAFE_CASTS registry produces valid USING clauses
- Unit: Alembic env builds correct MetaData from DSL entities
- Integration: create TEXT columns, run migration, verify type correction
- Integration: add DSL field, run migration, verify column appears
- Integration: rollback reverts the last change
- Integration: tenant schema migration applies to correct schema
