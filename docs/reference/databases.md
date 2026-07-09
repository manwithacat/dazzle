# Database Configuration

Dazzle uses PostgreSQL as its database backend. PostgreSQL is required for both development and production.

## Configuration

### Environment Variable (Recommended)

```bash
export DATABASE_URL=postgresql://user:password@localhost:5432/myapp
dazzle serve
```

### CLI Flag

```bash
dazzle serve --database-url postgresql://user:password@localhost:5432/myapp
```

### dazzle.toml

Configure the database URL in your project manifest:

```toml
[database]
url = "postgresql://user:password@localhost:5432/myapp"
# Or use env var indirection:
# url = "env:DATABASE_URL"
```

### `.env` file

`dazzle serve` auto-loads a `.env` file from the project root:

```bash
# .env
DATABASE_URL=postgresql://user:password@localhost:5432/myapp
```

## URL Formats

| `DATABASE_URL` | Notes |
|----------------|-------|
| `postgresql://user:pass@host:5432/db` | Standard format |
| `postgres://user:pass@host:5432/db` | Heroku-style, auto-converted to `postgresql://` |

## Local PostgreSQL Setup

`dazzle serve` connects to whatever `DATABASE_URL` points at. Pick one of the
options below (or a managed instance) — the connection string differs by
platform, so use the one for your OS.

### Using a container (any OS)

Run Postgres in a container you manage (Dazzle no longer starts one for you):

```bash
docker run -d --name dazzle-postgres \
  -e POSTGRES_USER=dazzle \
  -e POSTGRES_PASSWORD=dazzle \
  -e POSTGRES_DB=dazzle \
  -p 5432:5432 \
  postgres:16

export DATABASE_URL=postgresql://dazzle:dazzle@localhost:5432/dazzle
dazzle serve
```

### Using Homebrew (macOS)

Homebrew's Postgres creates a superuser role named after your macOS user and
trusts local connections, so a credential-less URL works:

```bash
brew install postgresql@16
brew services start postgresql@16
createdb dazzle

export DATABASE_URL=postgresql://localhost:5432/dazzle
dazzle serve
```

### Using apt (Debian / Ubuntu)

Stock Debian/Ubuntu is different: `initdb` creates only the `postgres`
superuser and uses `scram-sha-256` (password) auth over TCP — there is **no**
role named after your Linux user, and the credential-less URL above will fail
with `role "<you>" does not exist` or a password error. Create a role + database
explicitly and put the credentials in the URL:

```bash
sudo apt install postgresql
sudo -u postgres createuser -P dazzle     # prompts for a password, e.g. "dazzle"
sudo -u postgres createdb -O dazzle dazzle

export DATABASE_URL=postgresql://dazzle:dazzle@127.0.0.1:5432/dazzle
dazzle serve
```

> **Gotcha:** `psql dazzle` may succeed (peer auth over the Unix socket) while
> `dazzle serve` fails — the app connects over **TCP**, which uses password auth.
> Always include the user + password in `DATABASE_URL` on Linux, and connect via
> `127.0.0.1` rather than the socket.

## Installing PostgreSQL Drivers

Install the `postgres` extra:

```bash
pip install dazzle-dsl[postgres]
```

This installs `psycopg[binary]` (v3) and `psycopg-pool`.

## Auth Database

Dazzle's authentication system can use a separate database via `AUTH_DATABASE_URL`. This is useful for shared auth across multiple Dazzle apps.

| Variable | Purpose | Default |
|----------|---------|---------|
| `DATABASE_URL` | Application data | Required |
| `AUTH_DATABASE_URL` | Auth users and sessions | Falls back to `DATABASE_URL` |

```bash
export DATABASE_URL=postgresql://localhost:5432/myapp
export AUTH_DATABASE_URL=postgresql://localhost:5432/myapp_auth
dazzle serve
```

## Connection Pool

Dazzle uses [`psycopg_pool.ConnectionPool`](https://www.psycopg.org/psycopg3/docs/advanced/pool.html) for the main request-handler connections, and dedicated long-lived `psycopg.AsyncConnection` instances for the event framework. Both share the same `DATABASE_URL`.

### Config

| Variable | Default | Description |
|---|---|---|
| `DAZZLE_DB_POOL_MIN` | `2` | Connections kept open even when idle |
| `DAZZLE_DB_POOL_MAX` | `10` | Hard ceiling on the main pool |

The event-framework connections (outbox publisher + consumer listeners) are **not** in the main pool — they're 1-3 additional long-lived connections per server process. Reserve headroom when sizing the pool against the Postgres server's `max_connections`.

**Per-process connection count budget** (rule of thumb):

```
DAZZLE_DB_POOL_MAX            (main pool ceiling)
+ 2-3                          (event framework: 1 outbox publisher + 1-2 listener consumers)
+ 1-2                          (transient migration / schema-create on startup)
= ~14 connections per `dazzle serve` process
```

Multiply by `WEB_CONCURRENCY` (uvicorn workers) for total cluster footprint.

### Local PostgreSQL

Default `max_connections = 100` on a stock Postgres install is plenty for a single Dazzle dev server. No tuning needed.

If you run **multiple example apps simultaneously** (e.g. for cross-app testing), each gets its own database AND its own server process. With 5 example apps × 14 connections = 70 connections — still under 100. If you push into the limit, either:

- Lower `DAZZLE_DB_POOL_MAX` per project (e.g. `DAZZLE_DB_POOL_MAX=4`)
- Raise `max_connections` in `postgresql.conf` (requires server restart): `max_connections = 200`

### Heroku Postgres

Heroku Postgres plans have per-tier connection ceilings — they're the dominant constraint for production deployments. **Always set `DAZZLE_DB_POOL_MAX * WEB_CONCURRENCY < plan_max_connections - 5`** (the `-5` leaves headroom for `psql` debug sessions, `heroku pg:psql`, and event-framework connections).

| Plan | `max_connections` | Recommended `DAZZLE_DB_POOL_MAX` (with 4 workers) | Notes |
|---|---:|---:|---|
| Essential-0 | 20 | `2` | Tight — 2 × 4 = 8, plus 4 event-framework × 4 workers = 16; consider 1 worker only |
| Essential-1 | 40 | `5` | 5 × 4 = 20, + 16 event = 36; comfortable |
| Standard-0 | 120 | `15` | 15 × 4 = 60, + 16 event = 76; room to spare |
| Standard-2+ | 400+ | `25` | Generous |

On the smallest Heroku plans, also consider `WEB_CONCURRENCY=1` (single worker per dyno) and scale horizontally with `heroku ps:scale web=N` — that way each dyno's footprint is small and connection accounting is linear.

### Heroku TCP timeouts

Heroku terminates idle TCP after **30 minutes** of inactivity. The default `psycopg_pool` does **not** detect and reconnect — a queued idle connection picked up after 30 min will hit `OperationalError: server closed the connection unexpectedly` on the first query.

For production deployments, set `pool_recycle` (TBD — currently not exposed; if you hit this, file an issue referencing #1072 follow-ups).

### Diagnostic commands

```bash
# Heroku
heroku pg:info                                          # show current connection count + plan limit
heroku pg:psql -c "SELECT count(*) FROM pg_stat_activity WHERE datname = current_database();"

# Local
psql -d <dbname> -c "SELECT count(*) FROM pg_stat_activity WHERE datname = '<dbname>';"
psql -d <dbname> -c "SHOW max_connections;"

# Inspect idle-in-transaction sessions (the #1072 Bug A diagnostic)
psql -d <dbname> -c "SELECT pid, state, query FROM pg_stat_activity WHERE datname='<dbname>' AND state LIKE 'idle in transaction%';"
```

### What pool-related symptoms look like

| Symptom | Likely cause | Fix |
|---|---|---|
| `psycopg_pool.PoolTimeout` after ~30s | Pool exhausted — too many concurrent in-flight requests | Increase `DAZZLE_DB_POOL_MAX` until error stops or you hit `max_connections - 5` |
| `FATAL: too many clients already` | Cluster-wide ceiling hit | Lower `DAZZLE_DB_POOL_MAX * WEB_CONCURRENCY * dyno_count` below `max_connections` |
| `server closed the connection unexpectedly` | TCP idle-killed by Heroku / DBaaS provider | (See "Heroku TCP timeouts" above) |
| `CREATE INDEX ... waiting` indefinitely | A separate process holds `idle in transaction` on the table | `pg_terminate_backend(pid)` the offender; root-cause the leak |

## Schema Management

Dazzle automatically creates and migrates database tables on startup. No manual migration step is required for development.

- **Schema changes**: Adding entities or fields to your DSL and restarting the server applies the new schema. Dazzle uses `CREATE TABLE IF NOT EXISTS` and `ALTER TABLE ADD COLUMN` for non-destructive migrations.
- **Production migrations**: Use `dazzle db` commands (Alembic) for controlled schema changes in production.

## CI / Testing

To run the Dazzle test suite against PostgreSQL:

```bash
# Start a test database
docker run -d --name dazzle-test-pg \
  -e POSTGRES_USER=dazzle \
  -e POSTGRES_PASSWORD=dazzle_test \
  -e POSTGRES_DB=dazzle_test \
  -p 5432:5432 \
  postgres:16

# Run tests
DATABASE_URL=postgresql://dazzle:dazzle_test@localhost:5432/dazzle_test \
  pytest -m "not e2e" -x
```

The `-x` flag fails fast on the first error, which is useful for catching backend-specific issues.

The `dsl_test run` command tests a running server via HTTP and is backend-agnostic — it works with whatever database the server is configured to use.
