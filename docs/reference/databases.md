# Database Configuration

Dazzle supports SQLite and PostgreSQL as database backends. SQLite is used by default for development; PostgreSQL is recommended for production.

## Backend Selection

Dazzle selects the database backend based on the `DATABASE_URL` environment variable:

| `DATABASE_URL` | Backend | Notes |
|----------------|---------|-------|
| Not set | SQLite | File stored in project directory (`data/app.db`) |
| `sqlite:///path/to/db` | SQLite | Explicit SQLite path |
| `postgresql://...` | PostgreSQL | Requires `psycopg` (v3) |
| `postgres://...` | PostgreSQL | Heroku-style URL, auto-converted to `postgresql://` |

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
pip install dazzle[postgres]
```

This installs `psycopg[binary]` (v3) and `psycopg-pool`.

## Auth Database

Dazzle's authentication system can use a separate database via `AUTH_DATABASE_URL`. This is useful for shared auth across multiple Dazzle apps.

| Variable | Purpose | Default |
|----------|---------|---------|
| `DATABASE_URL` | Application data | SQLite (`data/app.db`) |
| `AUTH_DATABASE_URL` | Auth users and sessions | Falls back to `DATABASE_URL` |

```bash
export DATABASE_URL=postgresql://localhost:5432/myapp
export AUTH_DATABASE_URL=postgresql://localhost:5432/myapp_auth
dazzle serve --local
```

## Schema Management

Dazzle automatically creates and migrates database tables on startup. No manual migration step is required.

- **SQLite → PostgreSQL**: Set `DATABASE_URL` and restart. Tables are created automatically. Existing SQLite data is not migrated — use standard tools (`pgloader`, custom scripts) if you need to transfer data.
- **Schema changes**: Adding entities or fields to your DSL and restarting the server applies the new schema. Dazzle uses `CREATE TABLE IF NOT EXISTS` and `ALTER TABLE ADD COLUMN` for non-destructive migrations.

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
