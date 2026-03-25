# ADR-0012: Alembic for Schema Migrations

**Status:** Accepted
**Date:** 2026-03-23

## Context

Dazzle generates SQLAlchemy models from DSL entity definitions. As apps evolve, entity fields change — types widen, columns are added or removed, foreign keys are introduced. The database schema must keep pace with these DSL changes.

The previous hand-rolled `MigrationPlanner` compared old and new `AppSpec` IR trees and emitted raw DDL strings. This approach had critical gaps:

1. **No history** — migrations were applied but not recorded; re-running was destructive
2. **No rollback** — `ALTER TABLE` statements had no corresponding undo operations
3. **Type change gaps** — widening `str(50)` to `str(200)` required manual handling
4. **No diffing standard** — each migration path was bespoke code, not a proven algorithm
5. **Audit trail absent** — production deployments had no migration log

## Decision

Replace `MigrationPlanner` with **Alembic**, SQLAlchemy's official migration tool.

Pipeline: `DSL → SQLAlchemy MetaData → Alembic autogenerate → migration files`

Safe type casts (e.g. `VARCHAR(50)` → `VARCHAR(200)`) are applied automatically. Three operating modes:

| Mode | Trigger | Behaviour |
|------|---------|-----------|
| `dev` | `dazzle serve --local` | Auto-migrate on startup, no confirmation |
| `explicit` | `dazzle db migrate` | Generate and apply migration files |
| `production` | `DAZZLE_ENV=production` | Guard mode — refuse to start if schema is out of date |

### Why Alembic?

| Criterion | Alembic | Custom MigrationPlanner | Manual DDL |
|-----------|---------|------------------------|------------|
| Autogenerate diffing | Yes | Partial | No |
| Rollback support | Yes | No | No |
| Audit trail | Yes (versions table) | No | No |
| Battle-tested | Yes (SQLAlchemy project) | No | No |
| LLM edge case hook | Yes (env.py) | N/A | N/A |

### LLM Cognition for Edge Cases

Alembic autogenerate is deterministic for unambiguous changes. For edge cases — column renames, data migrations, split columns — Alembic emits a stub and Dazzle's LLM integration fills in the migration body. This is the only place LLM cognition is used; all other migrations are fully automated.

## Consequences

### Positive

- Proven diffing algorithm replaces custom code
- Full rollback support via `alembic downgrade`
- `alembic_version` table provides deployment audit trail
- Production guard prevents silent schema drift
- Type widening handled automatically without custom cases

### Negative

- `alembic.ini` and `env.py` must be maintained alongside the project
- Autogenerate does not detect column renames — requires manual annotation or LLM assist
- Migration files are generated artefacts; they must be committed to version control

### Neutral

- `MigrationPlanner` class removed entirely — no compatibility shim
- Existing databases receive a baseline migration on first Alembic run
- `dazzle db reset` bypasses Alembic (dev-only destructive reset remains unchanged)

## Alternatives Considered

### 1. Custom MigrationPlanner (Status Quo)

Continue extending the hand-rolled planner.

**Rejected:** No rollback, no history, bespoke code growing unbounded. Correctness not guaranteed.

### 2. Manual DDL Scripts

Developers write SQL migration files by hand.

**Rejected:** Error-prone, no autogenerate, inconsistent across contributors. Breaks DSL-first principle.

### 3. Flyway / Liquibase

JVM-based migration tools.

**Rejected:** Not Python-native, requires JVM dependency, no SQLAlchemy integration.

## Implementation

See `src/dazzle_back/migrations/` for Alembic environment. `env.py` imports the DSL-derived SQLAlchemy `MetaData` to enable autogenerate. Safe type casts are registered in `alembic/cast_rules.py`.
