# Production Deployment — Design Spec

**Date:** 2026-03-22
**Status:** Approved
**Scope:** `--production` flag, `dazzle deploy` command group, retire container runtime

## Problem

Dazzle has two deployment paths that have diverged:

1. **`dazzle serve`** — runs the real runtime (full feature set) on the host
2. **Container mode** (`--rebuild`) — runs a stripped-down reimplementation in Docker (11 files, ~1000 lines of duplicated logic) that lacks scope/permit enforcement, graph semantics, state machines, and every other feature added since the container runtime was written

Docker-oriented and Heroku-based developers get a feature-incomplete experience. Every new framework feature must be re-implemented in the container runtime or it doesn't work in production.

## Decision: One Runtime, Multiple Deployment Targets

The real runtime (`dazzle serve`) becomes the universal entry point. Containers install `dazzle-dsl` and run `dazzle serve --production`. The container runtime is retired.

## Three Serve Modes

| Mode | Flag | Who uses it | Infra management |
|------|------|-------------|-----------------|
| Default dev | `dazzle serve` | Mac/Linux devs, zero-setup | Auto-starts Postgres/Redis in Docker |
| Local dev | `dazzle serve --local` | Devs with existing services | User provides DATABASE_URL/REDIS_URL |
| Production | `dazzle serve --production` | Docker, Heroku, cloud | Reads env vars, no dev features |

### `--production` behavior

- Binds `0.0.0.0` (not `127.0.0.1`)
- Reads `PORT` env var (Heroku convention), falls back to `--port` flag
- Requires `DATABASE_URL` env var (fails fast with clear error if missing)
- Disables: auto-reload, test mode, dev mode, Docker infrastructure management
- Enables: structured JSON logging (for log aggregators)
- `REDIS_URL` optional (events/channels disabled if not set)

## `dazzle deploy` Command Group

Generates deployment artifacts. Does not execute them.

### `dazzle deploy dockerfile`

Generates a production Dockerfile:

```dockerfile
FROM python:3.12-slim
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python -c "import httpx; httpx.get('http://localhost:8000/health').raise_for_status()"
CMD ["dazzle", "serve", "--production"]
```

Also generates `requirements.txt` with pinned `dazzle-dsl` version + extras.

Output: `./Dockerfile` + `./requirements.txt`

### `dazzle deploy heroku`

Generates Heroku deployment files:

```
# Procfile
web: dazzle serve --production

# runtime.txt
python-3.12

# requirements.txt
dazzle-dsl==0.46.2
psycopg[binary]>=3.1
redis>=5.0
httpx>=0.24
```

Output: `./Procfile` + `./runtime.txt` + `./requirements.txt`

### `dazzle deploy compose`

Generates a production docker-compose.yml:

```yaml
services:
  app:
    build: .
    ports:
      - "3000:8000"
    environment:
      - DATABASE_URL=postgresql://dazzle:dazzle@postgres:5432/dazzle
      - REDIS_URL=redis://redis:6379
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_started

  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: dazzle
      POSTGRES_PASSWORD: dazzle
      POSTGRES_DB: dazzle
    volumes:
      - pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U dazzle"]
      interval: 5s
      timeout: 5s
      retries: 5

  redis:
    image: redis:7-alpine

volumes:
  pgdata:
```

Output: `./docker-compose.yml` (requires Dockerfile from `dazzle deploy dockerfile`)

## What Gets Retired

| File/Directory | Lines | Reason |
|---|---|---|
| `src/dazzle_ui/runtime/container/` | ~1000 | Entire container runtime — replaced by real runtime |
| `src/dazzle_ui/runtime/docker/runner.py` | 357 | DockerRunner build/run logic — replaced by `dazzle deploy` |
| `src/dazzle_ui/runtime/docker/templates.py` | 123 | Dockerfile templates — replaced by `dazzle deploy dockerfile` |
| `--rebuild` flag on `dazzle serve` | — | No longer needed |

**Total removed:** ~1500 lines of vestigial code.

**Retained:**
- `src/dazzle/cli/runtime_impl/docker.py` — refactored to power `dazzle deploy`
- Dev infrastructure management (Docker Compose for Postgres/Redis in default mode)

## Migration

- `dazzle serve --rebuild` prints: `"Container mode has been replaced. Run 'dazzle deploy dockerfile' to generate a Dockerfile, then build and run it with Docker."`
- Example projects' `build/Dockerfile` files updated to the new pattern
- CHANGELOG entry under `### Removed` for the container runtime

## Error Messages

| Condition | Message |
|---|---|
| `--production` without `DATABASE_URL` | `"--production requires DATABASE_URL environment variable. Set it to your PostgreSQL connection string."` |
| `--production` without DSL files | `"No DSL files found in current directory. Run dazzle serve --production from your project root."` |
| `dazzle serve --rebuild` (deprecated) | `"--rebuild has been removed. Run 'dazzle deploy dockerfile' to generate deployment files."` |

## File Structure

| File | Action | Responsibility |
|------|--------|----------------|
| `src/dazzle/cli/runtime_impl/serve.py` | Modify | Add `--production` flag handling |
| `src/dazzle/cli/deploy.py` | Create | `dazzle deploy dockerfile\|heroku\|compose` commands |
| `src/dazzle_ui/runtime/container/` | Delete | Retired container runtime |
| `src/dazzle_ui/runtime/docker/runner.py` | Delete | Retired DockerRunner |
| `src/dazzle_ui/runtime/docker/templates.py` | Delete | Retired templates |
| `examples/*/build/Dockerfile` | Modify | Update to new pattern |
