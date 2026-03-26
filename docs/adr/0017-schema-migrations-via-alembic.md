# ADR-0017: All Schema Migrations Via Alembic

**Status**: Accepted
**Date**: 2026-03-26
**Relates to**: #712, #713, ADR-0008 (PostgreSQL only)

## Context

Dazzle auto-generates framework entities (FeedbackReport, AIJob, admin platform
entities) at link time. When we add fields to these entities, existing
deployments need schema changes.

We initially built `ensure_framework_entity_columns()` which ran raw
`ALTER TABLE ADD COLUMN IF NOT EXISTS` at startup, bypassing the Alembic
migration system we'd already built. This created a parallel schema
modification path that:

- Didn't create Alembic revision files
- Didn't track changes in `alembic_version`
- Could conflict with Alembic autogenerate
- Didn't follow our own tooling (`dazzle db revision`, `dazzle db upgrade`)

## Decision

**All schema changes — including framework entities — go through Alembic.**

### Rules

1. **No raw DDL at startup.** `create_all()` is acceptable for initial table
   creation (new deployments), but column additions, type changes, and
   constraint modifications must be Alembic migrations.

2. **Framework entity changes → Alembic revision.** When adding fields to
   FeedbackReport, AIJob, or admin entities, generate a migration:
   ```bash
   dazzle db revision -m "add idempotency_key to FeedbackReport"
   dazzle db upgrade
   ```

3. **Virtual entities excluded from SA metadata.** Entities backed by
   non-PostgreSQL stores (SystemHealth, SystemMetric, ProcessRun) must not
   appear in SQLAlchemy MetaData. They are filtered in `build_metadata()`.

4. **`dazzle serve` runs `alembic upgrade head` at startup.** This is
   already implemented — it catches pending migrations before the app starts.

### Migration workflow for developers

```bash
# After changing entity fields in DSL or framework code:
dazzle db revision -m "describe the change"   # autogenerates migration
dazzle db upgrade                              # applies to local DB
git add src/dazzle_back/alembic/versions/      # commit the migration file
```

### What `create_all()` still does

- Creates tables that don't exist yet (first deployment)
- Idempotent — safe to run repeatedly
- Does NOT add columns to existing tables (Alembic's job)

## Consequences

- Framework entity field additions require an Alembic migration file committed
  to the repo, not just an IR change
- Deployments must run `dazzle db upgrade` (or rely on `dazzle serve` auto-upgrade)
- Alembic autogenerate correctly diffs framework entities because they're in
  SA metadata (except virtual entities, which are excluded)
- The `_dazzle_params` table remains a special case — it's framework
  infrastructure, not an entity, and uses `CREATE TABLE IF NOT EXISTS`
