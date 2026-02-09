---
auto_load: true
globs:
  - "**/Procfile"
  - "**/Dockerfile*"
  - "**/heroku*.yml"
  - "**/docker-compose*.yml"
  - "**/.env*"
---

# Deployment Patterns

## PostgreSQL-First Architecture

All infrastructure stores (auth, tokens, ops, device registry, file storage, FTS, health, tenant isolation) require PostgreSQL. Set `DATABASE_URL` environment variable.

```bash
# Local development
export DATABASE_URL="postgresql://localhost:5432/dazzle"

# Heroku
heroku config:set DATABASE_URL=postgresql://...
```

The entity data layer (`SQLiteRepository`) still uses SQLite for local dev but PostgresBackend for production via `DATABASE_URL`.

## Heroku Deployment

```bash
# Deploy
git push heroku main

# Check logs
heroku logs --tail

# Run migrations
heroku run python -m dazzle migrate

# Health check
curl https://app.herokuapp.com/_health
```

### Heroku Gotchas

- `postgres://` URLs must be normalized to `postgresql://` (handled automatically)
- Ephemeral filesystem — don't store files on disk, use S3
- `Procfile` should use `python -m dazzle serve --port $PORT`
- Set `WEB_CONCURRENCY=2` for worker count

## Docker

```bash
# Build and serve
dazzle serve                    # Docker mode (default)
dazzle serve --local            # Without Docker

# Custom port
dazzle serve --port 9000
```

## Health Checks

- `/_health` — aggregated health status
- `/_health/db` — database connectivity
- `/_health/ready` — readiness probe
- `/docs` — OpenAPI documentation
