# Deploying Dazzle to Heroku

## Prerequisites

- [Heroku CLI](https://devcenter.heroku.com/articles/heroku-cli) installed
- Git repository with your Dazzle project
- `dazzle.toml` at the repository root

## Quick Start

```bash
# Create Heroku app
heroku create my-dazzle-app

# Add PostgreSQL and Redis
heroku addons:create heroku-postgresql:essential-0
heroku addons:create heroku-redis:mini

# Set required env vars
heroku config:set DAZZLE_ENV=production
heroku config:set DAZZLE_SECRET_KEY=$(python -c "import secrets; print(secrets.token_urlsafe(32))")

# Deploy
git push heroku main
```

`DATABASE_URL` and `REDIS_URL` are set automatically by the add-ons.

## Procfile

Your repository should contain a `Procfile` at the root:

```
web: uvicorn dazzle_back.runtime.app_factory:create_app_factory --factory --host 0.0.0.0 --port $PORT --workers ${WEB_CONCURRENCY:-4}
```

This uses uvicorn's multi-worker mode. Each worker gets its own process and connection pool.

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `DATABASE_URL` | Yes | (auto) | PostgreSQL URL (set by Heroku Postgres add-on) |
| `REDIS_URL` | Yes | (auto) | Redis URL (set by Heroku Redis add-on) |
| `DAZZLE_ENV` | Yes | `development` | Set to `production` |
| `DAZZLE_SECRET_KEY` | Yes | - | Secret key for sessions and tokens |
| `DAZZLE_DB_POOL_MIN` | No | `2` | Minimum connection pool size |
| `DAZZLE_DB_POOL_MAX` | No | `10` | Maximum connection pool size |
| `WEB_CONCURRENCY` | No | `4` | Number of uvicorn worker processes |

## Connection Pool Tuning

Match `DAZZLE_DB_POOL_MAX` to your Heroku Postgres plan's connection limit:

| Plan | Max Connections | Recommended `DAZZLE_DB_POOL_MAX` |
|------|----------------|----------------------------------|
| Essential-0 | 20 | `4` (with 4 workers = 16 total) |
| Essential-1 | 40 | `8` (with 4 workers = 32 total) |
| Standard-0 | 120 | `10` (with 4 workers = 40 total) |

**Formula**: `DAZZLE_DB_POOL_MAX * WEB_CONCURRENCY < plan_max_connections`

```bash
heroku config:set DAZZLE_DB_POOL_MAX=4 WEB_CONCURRENCY=4
```

## Scaling

Start with a single standard dyno:

```bash
heroku ps:scale web=1:standard-1x
```

Before scaling horizontally, try vertical scaling:

```bash
heroku ps:scale web=1:standard-2x
```

Horizontal scaling works out of the box — each dyno runs independent workers with their own connection pools. The advisory lock on migrations ensures only one worker runs schema changes.

## File Storage

Heroku's filesystem is ephemeral. For file uploads, configure S3:

```bash
heroku config:set DAZZLE_FILE_STORAGE=s3
heroku config:set AWS_ACCESS_KEY_ID=...
heroku config:set AWS_SECRET_ACCESS_KEY=...
heroku config:set AWS_S3_BUCKET=my-dazzle-uploads
```

## Framework Version Pinning

Pin the framework version in `dazzle.toml` to prevent unexpected changes:

```toml
[project]
name = "my-app"
version = "1.0.0"
framework_version = "~0.38"
```

The server refuses to start if the installed version doesn't match.

## Backups

Heroku Postgres provides automatic daily backups. For manual backups:

```bash
# Heroku's built-in backup
heroku pg:backups:capture

# Dazzle's backup (includes uploads and metadata)
heroku run dazzle backup create
heroku run dazzle backup create --output /tmp/backup.tar.gz
```

## Custom Domains and SSL

```bash
heroku domains:add app.example.com
# SSL is automatic with ACM (Automated Certificate Management)
heroku certs:auto:enable
```

## Monitoring

```bash
# Live logs
heroku logs --tail

# Metrics dashboard
heroku open --app my-dazzle-app
# Navigate to "Metrics" tab in Heroku Dashboard
```

## Troubleshooting

**Port already in use**: Heroku assigns `$PORT` dynamically. Never hardcode the port.

**Connection pool exhaustion**: Check `heroku pg:info` for connection count. Reduce `DAZZLE_DB_POOL_MAX` or scale down workers.

**Migration conflicts**: The advisory lock prevents concurrent migrations across workers. If a migration hangs, check `heroku pg:locks`.

**Memory issues**: Monitor with `heroku logs --tail | grep "Memory quota"`. Reduce `WEB_CONCURRENCY` if needed.
