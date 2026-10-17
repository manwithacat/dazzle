# Operational Guide

> **Runtime observability** (health endpoints, event subsystem, jobs, dead-letter handling, metrics) is covered in the [Observability Guide](observability.md) — this guide focuses on infrastructure operations (connection pools, migrations, backups).

## Environment Configuration

| Setting | Development | Staging | Production |
|---------|-------------|---------|------------|
| `DAZZLE_ENV` | `development` | `staging` | `production` |
| Test endpoints | Enabled | Enabled | Disabled |
| Dev control plane | Enabled | Disabled | Disabled |
| `DAZZLE_DB_POOL_MIN` | `2` | `2` | `5` |
| `DAZZLE_DB_POOL_MAX` | `10` | `10` | `20` |
| Workers | `1` | `2` | `4+` |

## Framework Version Management

Pin the framework version in `dazzle.toml`:

```toml
[project]
framework_version = "~0.38"
```

The tilde (`~`) allows patch updates within the minor version. The server refuses to start on mismatch.

**Upgrade workflow:**

1. Update `dazzle.toml` with the new constraint
2. `pip install 'dazzle-dsl~=0.39.0'`
3. `dazzle validate` to check DSL compatibility
4. `dazzle serve` to test locally
5. Deploy

## Database Migrations

Dazzle auto-migrates on startup. In multi-worker deployments, a PostgreSQL advisory lock ensures only one worker runs migrations.

**Safe operations** (auto-applied):
- Create new tables
- Add new columns (with defaults)
- Add indexes

**Unsafe operations** (manual only):
- Drop columns
- Change column types
- Rename columns

For manual migrations, use Alembic:

```bash
dazzle db revision --message "add index on email"
dazzle db upgrade
```

**Dry-run** migrations to preview changes:

```bash
dazzle migrate --dry-run
```

## Connection Pooling

The connection pool opens on server startup and closes on shutdown. Configure via environment variables:

```bash
export DAZZLE_DB_POOL_MIN=2    # minimum connections kept open
export DAZZLE_DB_POOL_MAX=10   # maximum connections allowed
```

Total connections = `DAZZLE_DB_POOL_MAX * number_of_workers`. Ensure this stays below your PostgreSQL `max_connections`.

## Backup and Recovery

Without `shared_schema` tenancy, use your Postgres provider's backups
(`pg_dump` / `pg_restore`, or `heroku pg:backups:capture` on Heroku).

With `tenancy: mode: shared_schema`, tenant tables are under `FORCE ROW LEVEL
SECURITY`. A dump taken by a role that RLS filters (the app's only role on
Heroku and similar hosts) either fails (`query would be affected by row-level
security policy`) or, with `--enable-row-security`, writes every tenant table
empty. Use the tenant-aware commands (#1788):

```bash
dazzle db dump --out backups/                   # one tenant-bound dump per tenant + manifest.json
dazzle db restore-check --from backups/<label> \
  --target-url postgresql://…/restore_check --drop-first   # restore and compare every count
```

Run `dump` on a schedule and `restore-check` against a scratch database at
least weekly. When the connected role is a superuser or has `BYPASSRLS`, RLS
would not filter the per-tenant dumps, so `dump` requires `--role <a
NOSUPERUSER NOBYPASSRLS role that can read the tables>`. `dazzle db apply-rls
--check-dumpable` exits 1 when a plain dump of the database cannot work. See
[Heroku](heroku.md#backups).

Back up the uploads directory separately if the app stores files locally.

## Multi-Worker Deployment

Use `--workers` for local multi-worker mode:

```bash
dazzle serve --workers 4
```

For production, use the Procfile with `WEB_CONCURRENCY`:

```
web: uvicorn dazzle_http.runtime.app_factory:create_app_factory --factory --host 0.0.0.0 --port $PORT --workers ${WEB_CONCURRENCY:-4}
```

Each worker runs in a separate process with its own connection pool.

## Performance Tuning

**Connection pool sizing:**
- Start with `min=2, max=10`
- Monitor pool wait times in logs
- Increase if you see "pool exhausted" warnings

**Worker count:**
- CPU-bound: `workers = CPU cores`
- IO-bound (typical for Dazzle): `workers = 2 * CPU cores`
- Start conservative, increase based on monitoring

**Database:**
- Monitor slow queries with `pg_stat_statements`
- Add indexes for frequently filtered/sorted columns
- Use `dazzle migrate --dry-run` to preview schema changes
