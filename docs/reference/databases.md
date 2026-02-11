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

### Docker Compose

When using `dazzle serve` (Docker mode), set the variable in your shell or a `.env` file:

```bash
# .env
DATABASE_URL=postgresql://user:password@db:5432/myapp
```

## URL Formats

| `DATABASE_URL` | Notes |
|----------------|-------|
| `postgresql://user:pass@host:5432/db` | Standard format |
| `postgres://user:pass@host:5432/db` | Heroku-style, auto-converted to `postgresql://` |

## Local PostgreSQL Setup

### Using Docker (Quickest)

```bash
docker run -d --name dazzle-postgres \
  -e POSTGRES_USER=dazzle \
  -e POSTGRES_PASSWORD=dazzle \
  -e POSTGRES_DB=dazzle \
  -p 5432:5432 \
  postgres:16

export DATABASE_URL=postgresql://dazzle:dazzle@localhost:5432/dazzle
dazzle serve --local
```

### Using Homebrew (macOS)

```bash
brew install postgresql@16
brew services start postgresql@16
createdb dazzle

export DATABASE_URL=postgresql://localhost:5432/dazzle
dazzle serve --local
```

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
dazzle serve --local
```

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
