# Operational Guide

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
4. `dazzle serve --local` to test locally
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

### Create a backup

```bash
dazzle backup create                          # default: backup-{project}-{timestamp}.tar.gz
dazzle backup create --output /path/backup.tar.gz
dazzle backup create --data-only              # skip uploads directory
dazzle backup create --dry-run                # preview what would be backed up
```

### Restore from backup

```bash
dazzle backup restore --from backup-myapp-20260310.tar.gz
dazzle backup restore --from backup.tar.gz --dry-run    # preview
```

### What's in a backup

- Database dump (pg_dump, data-only)
- Uploads directory (if present)
- Metadata: project name, framework version, timestamp

## Multi-Worker Deployment

Use `--workers` for local multi-worker mode:

```bash
dazzle serve --local --workers 4
```

For production, use the Procfile with `WEB_CONCURRENCY`:

```
web: uvicorn dazzle_back.runtime.app_factory:create_app_factory --factory --host 0.0.0.0 --port $PORT --workers ${WEB_CONCURRENCY:-4}
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
