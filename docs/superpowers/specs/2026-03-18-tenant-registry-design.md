# Schema-Per-Tenant: Config, Registry, and CLI (Sub-Project 1 of 3)

**Date**: 2026-03-18
**Status**: Design
**Issue**: #531
**Scope**: Sub-project 1 — foundation layer. Sub-project 2 (connection routing middleware) and sub-project 3 (multi-schema migrations) are separate specs.

## Problem

Multi-tenant SaaS apps on Dazzle need hard isolation between tenants. Row-level filtering (scope blocks) handles within-tenant access control, but between-tenant isolation requires schema-level separation — each tenant gets its own PostgreSQL schema with its own copy of all entity tables.

This sub-project adds the configuration, tenant registry, schema provisioning, and CLI commands. It does NOT add request-time routing (sub-project 2) or multi-schema migrations (sub-project 3).

## Design

### Opt-In Configuration

New `[tenant]` section in `dazzle.toml`:

```toml
[tenant]
isolation = "schema"           # "schema" | "none" (default: none)
resolver = "subdomain"         # "subdomain" | "header" | "session"
# header_name = "X-Tenant-ID" # only when resolver = "header"
```

Apps without a `[tenant]` section (or with `isolation = "none"`) behave exactly as today — single `public` schema, no tenant awareness. This is the default for all existing apps.

New `TenantConfig` dataclass in `src/dazzle/core/manifest.py`:

```python
@dataclass
class TenantConfig:
    """Multi-tenant configuration.

    isolation = "none" (default): single-schema, no tenant awareness.
    isolation = "schema": each tenant gets a PostgreSQL schema.
    """
    isolation: str = "none"        # "none" | "schema"
    resolver: str = "subdomain"    # "subdomain" | "header" | "session"
    header_name: str = "X-Tenant-ID"  # only used when resolver = "header"
```

Added to `ProjectManifest` as `tenant: TenantConfig = field(default_factory=TenantConfig)`. Parsed in `load_manifest()` from the `[tenant]` TOML section.

---

### Tenant Registry

A `public.tenants` table stores tenant metadata:

```sql
CREATE TABLE IF NOT EXISTS public.tenants (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    slug TEXT UNIQUE NOT NULL,
    display_name TEXT NOT NULL,
    schema_name TEXT UNIQUE NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

**Schema naming convention:** `tenant_<slug>`. The `tenant_` prefix avoids collisions with PostgreSQL system schemas (`public`, `information_schema`, `pg_catalog`) and any future Dazzle-internal schemas.

**Slug validation:** `^[a-z][a-z0-9_]{1,62}$` — lowercase alpha start, alphanumeric + underscores, 2–63 chars total. This ensures valid PostgreSQL identifiers.

**`TenantRegistry` class** (`src/dazzle/tenant/registry.py`):

```python
class TenantRegistry:
    """CRUD operations on the public.tenants table."""

    def __init__(self, db_url: str) -> None: ...

    def ensure_table(self) -> None:
        """Create the tenants table if it doesn't exist."""

    def create(self, slug: str, display_name: str) -> TenantRecord:
        """Insert a tenant record. Raises if slug already exists."""

    def get(self, slug: str) -> TenantRecord | None:
        """Look up a tenant by slug."""

    def list(self) -> list[TenantRecord]:
        """List all tenants."""

    def update_status(self, slug: str, status: str) -> TenantRecord:
        """Set status to 'active', 'suspended', or 'archived'."""
```

```python
@dataclass
class TenantRecord:
    id: str
    slug: str
    display_name: str
    schema_name: str
    status: str
    created_at: str
    updated_at: str
```

The registry uses synchronous `psycopg2` connections (same as the existing `AuthStore` pattern) since CLI commands are synchronous.

---

### Schema Provisioner

`TenantProvisioner` (`src/dazzle/tenant/provisioner.py`) creates and populates a tenant schema:

```python
class TenantProvisioner:
    """Creates and populates PostgreSQL schemas for tenants."""

    def __init__(self, db_url: str, appspec: AppSpec) -> None: ...

    def provision(self, schema_name: str) -> None:
        """Create schema and all entity + auth tables within it."""

    def schema_exists(self, schema_name: str) -> bool:
        """Check if a schema exists in the database."""
```

Provisioning steps:
1. `CREATE SCHEMA IF NOT EXISTS "<schema_name>"`
2. `SET search_path TO "<schema_name>"`
3. Create all entity tables (reuse `DatabaseManager.create_tables()` logic with the tenant schema as target)
4. Create auth tables (users, sessions, roles) within the tenant schema
5. Reset `search_path` to default

**Idempotency:** If the registry row exists but the schema is missing (partial failure), re-running `create` provisions the schema. If both exist, reports "already exists."

**All DDL uses `quote_identifier()`** for schema and table names — no string interpolation of user-provided values into SQL.

---

### Auth Model

Auth is per-tenant — each tenant schema has its own users, sessions, and roles tables. A user `james@cyfuture.com` in the `cyfuture` tenant is completely independent from any user in another tenant's schema.

This matches the "hard isolation" goal: no cross-tenant user state, separate audit trails per tenant. If multi-tenant user identity is needed later, it's a separate feature.

---

### CLI Commands

New `dazzle tenant` command group (`src/dazzle/cli/tenant.py`):

```
dazzle tenant create <slug> --display-name "CyFuture UK"
dazzle tenant list
dazzle tenant status <slug>
dazzle tenant suspend <slug>
dazzle tenant activate <slug>
```

**`create`**: Validates slug, creates registry record, provisions schema with all entity + auth tables. Requires `isolation = "schema"` in `dazzle.toml` — errors if tenant mode is not enabled.

**`list`**: Shows all tenants with slug, display name, status, and schema name.

**`status`**: Shows details for one tenant — record metadata + whether the schema exists in the database.

**`suspend`** / **`activate`**: Toggle the `status` field. Suspended tenants will receive 503 responses at the middleware level (sub-project 2 — not implemented here).

**No `remove` / `drop` command.** Deleting a tenant schema is destructive and irreversible. Suspension is the deactivation path. If needed later, a `remove` command should require `--confirm-delete` and dump the schema first.

---

### File Structure

| File | Responsibility |
|------|---------------|
| `src/dazzle/tenant/__init__.py` | Package init |
| `src/dazzle/tenant/config.py` | `TenantConfig` dataclass, slug validation |
| `src/dazzle/tenant/registry.py` | `TenantRegistry` + `TenantRecord` — CRUD on `public.tenants` |
| `src/dazzle/tenant/provisioner.py` | `TenantProvisioner` — schema creation + table provisioning |
| `src/dazzle/cli/tenant.py` | CLI command group (`dazzle tenant create/list/status/suspend/activate`) |
| `src/dazzle/cli/__init__.py` | **Modify** — register `tenant_app` |
| `src/dazzle/core/manifest.py` | **Modify** — add `TenantConfig` + parse `[tenant]` section |

---

### Error Handling

- **Invalid slug:** `"Slug must match ^[a-z][a-z0-9_]{1,62}$. Got: '<slug>'"`
- **Duplicate slug:** `"Tenant '<slug>' already exists"`
- **Tenant not found:** `"Tenant '<slug>' not found"`
- **Tenant mode not enabled:** `"Multi-tenancy not enabled. Add [tenant] isolation = \"schema\" to dazzle.toml"`
- **Schema creation failure:** PostgreSQL error propagated with context (`"Failed to create schema 'tenant_<slug>': <pg_error>"`)

---

### Testing Strategy

| Layer | What to test |
|---|---|
| Config | Parse `TenantConfig` from TOML, defaults when `[tenant]` absent, slug validation |
| Registry | CRUD operations with mocked DB connection |
| Provisioner | Schema creation DDL with mocked connection, idempotency |
| CLI | Typer CliRunner with mocked registry/provisioner |
| Integration | (requires DATABASE_URL) Create tenant, verify schema exists, list tenants |

---

### Non-Goals (this sub-project)

- Connection routing middleware — resolving tenant from request and setting `search_path` (sub-project 2)
- Multi-schema migration runner (sub-project 3)
- `--tenant` flag on `dazzle db status/verify/reset/cleanup` (sub-project 2)
- Cross-tenant queries or analytics views
- Tenant removal / schema dropping
