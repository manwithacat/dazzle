# ADR-0008: PostgreSQL as the Sole Production Database

**Status:** Accepted
**Date:** 2026-03-24

## Context

Dazzle targets cloud deployments where apps are built from high-level DSL specifications and served by the FastAPI runtime (`src/dazzle_back/`). The runtime requires:

- **Real-time event delivery** via database-level pub/sub
- **Concurrent writes** from multiple request workers
- **Native UUID, TIMESTAMPTZ, and JSONB** column types for the grant store, event system, and audit trail
- **Row-level security** as a future compilation target for scope predicates

Historically the project carried dual SQLite/PostgreSQL code paths in some areas, inherited from early local development. These paths diverged silently and produced subtle, hard-to-reproduce bugs when column type behaviour differed between backends.

The decision to establish a formal predicate algebra (ADR-0009) and a grant-based RBAC system makes this divergence unacceptable: correctness guarantees derived from static analysis must hold at runtime.

## Decision

PostgreSQL is the sole supported production database. All code paths target PostgreSQL exclusively:

- Native `UUID` primary keys — no `VARCHAR(36)` workarounds
- `TIMESTAMPTZ` for all timestamps — no naïve `DATETIME`
- `JSONB` for structured payloads in the event system and grant store
- `LISTEN`/`NOTIFY` for real-time channel delivery
- No SQLite imports, drivers, or conditional branches anywhere in `src/dazzle_back/`

Local development uses PostgreSQL via the default `dazzle serve` Docker stack. No SQLite fallback is provided.

## Consequences

### Positive

- Correctness guarantees from the predicate algebra hold end-to-end
- LISTEN/NOTIFY enables the event channel system without a message broker
- No abstraction layer overhead — queries use PG-specific features freely
- One backend to test, document, and reason about
- Future Postgres RLS compilation of scope predicates is straightforward

### Negative

- Docker required for local development (already the default)
- Contributors cannot run the test suite without a PostgreSQL instance
- Slightly higher barrier to entry than SQLite-backed alternatives

### Neutral

- Heroku Postgres, Supabase, Railway, and managed AWS/GCP offerings all supported
- Migration tooling targets PG dialect only

## Alternatives Considered

### 1. Support Both SQLite and PostgreSQL

Maintain dual code paths, using SQLite for development and tests and PostgreSQL for production.

**Rejected:** Divergence between backends already caused subtle bugs. Correctness proofs from static analysis must hold at runtime; two backends make this impossible to guarantee.

### 2. Lowest-Common-Denominator SQL

Use an ORM abstraction layer with only portable SQL features, avoiding PG-specific types.

**Rejected:** Eliminates LISTEN/NOTIFY (required for channels), native UUID/JSONB (required for grant store), and future RLS compilation. Adds abstraction overhead for no benefit given the single-backend decision.

### 3. SQLite for Development, PG for Production

Use SQLite locally and switch to PG in CI and production.

**Rejected:** Parity failures are detected too late. Type semantics differ in ways that break scope predicate compilation. The Docker stack makes local PG trivial.

## Implementation

- `src/dazzle_back/` uses `asyncpg` directly; no SQLAlchemy dialect switching
- All migrations in `alembic/` target PG dialect
- `pytest` fixtures spin up a PG test database via the Docker Compose test profile
- `dazzle db status|verify|reset` commands are PG-only
