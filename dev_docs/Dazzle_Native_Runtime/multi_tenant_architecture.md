# DNR Multi-Tenant Architecture Evaluation

**Date**: 2025-11-28
**Status**: Design Phase
**Author**: Claude (AI Assistant)

---

## Overview

This document evaluates approaches for implementing multi-tenant applications in DNR, including row-level security (RLS), schema-level isolation, and database-per-tenant models.

---

## Multi-Tenancy Patterns

### 1. Row-Level Security (Shared Tables)

**How it works**: All tenants share the same tables, with a `tenant_id` column filtering data.

```sql
-- Every table has tenant_id
CREATE TABLE tasks (
    id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL,  -- Added automatically
    title TEXT,
    owner_id UUID,
    ...
);

-- Queries automatically filtered
SELECT * FROM tasks WHERE tenant_id = ? AND ...
```

**Pros**:
- Simple to implement
- Works with SQLite
- Single database to manage
- Easy migrations (one schema)

**Cons**:
- Risk of data leakage if filter forgotten
- Noisy neighbor issues (one tenant's heavy usage affects others)
- Complex queries with many joins
- No true isolation

**SQLite Implementation**: ✅ **Feasible**
- Add `tenant_id` column to all tables
- Modify repository to inject tenant context
- Filter all queries automatically

### 2. Schema-Level Isolation (PostgreSQL)

**How it works**: Each tenant gets their own PostgreSQL schema within one database.

```sql
-- Tenant 1's data
CREATE SCHEMA tenant_abc123;
CREATE TABLE tenant_abc123.tasks (...);

-- Tenant 2's data
CREATE SCHEMA tenant_xyz789;
CREATE TABLE tenant_xyz789.tasks (...);

-- Query routing via search_path
SET search_path TO tenant_abc123;
SELECT * FROM tasks;  -- Queries tenant_abc123.tasks
```

**Pros**:
- True logical isolation
- Easy per-tenant backup/restore
- Can grant schema-level permissions
- Clean separation of data
- PostgreSQL's Row Level Security for additional protection

**Cons**:
- PostgreSQL only (not SQLite)
- Schema migrations more complex (apply to N schemas)
- Connection pool management per schema
- More operational overhead

**SQLite Implementation**: ❌ **Not Feasible**
- SQLite has no schema concept
- Would need database-per-tenant instead

### 3. Database-Per-Tenant

**How it works**: Each tenant gets their own database file/instance.

```
.dazzle/
  tenants/
    abc123/data.db
    xyz789/data.db
    ...
```

**Pros**:
- Complete isolation
- Easy backup/delete per tenant
- No risk of data leakage
- Works with SQLite
- Independent scaling

**Cons**:
- Many database connections
- Complex routing layer
- Migrations across all databases
- Resource overhead (connections, files)

**SQLite Implementation**: ✅ **Feasible**
- Create database file per tenant
- Route connections based on tenant context

---

## Recommended Approach: Hybrid Strategy

Given DNR's goals (simplicity for dev, production-ready), I recommend a **tiered approach**:

### Tier 1: Row-Level Security (Default, SQLite)

For most use cases and development:

```python
# Automatic tenant filtering
class TenantAwareRepository(SQLiteRepository[T]):
    def __init__(self, ..., tenant_context: TenantContext):
        self.tenant_id = tenant_context.tenant_id

    async def list(self, ...):
        # Automatically inject tenant filter
        filters = filters or {}
        filters["tenant_id"] = self.tenant_id
        return await super().list(..., filters=filters)

    async def create(self, data: dict):
        # Automatically set tenant_id
        data["tenant_id"] = self.tenant_id
        return await super().create(data)
```

### Tier 2: PostgreSQL with RLS (Production)

For production deployments needing more isolation:

```python
# PostgreSQL Row Level Security
class PostgresRepository(BaseRepository[T]):
    async def setup_rls(self):
        """Enable RLS on table."""
        await self.execute(f"""
            ALTER TABLE {self.table_name} ENABLE ROW LEVEL SECURITY;

            CREATE POLICY tenant_isolation ON {self.table_name}
                USING (tenant_id = current_setting('app.tenant_id')::uuid);
        """)

    async def set_tenant_context(self, tenant_id: UUID):
        """Set tenant context for current connection."""
        await self.execute(
            f"SET app.tenant_id = '{tenant_id}'"
        )
```

### Tier 3: Schema Isolation (Enterprise)

For enterprise with strict isolation requirements:

```python
# Schema-per-tenant
class SchemaIsolatedRepository(PostgresRepository[T]):
    def __init__(self, ..., tenant_schema: str):
        self.schema = tenant_schema

    async def ensure_schema(self):
        """Create schema if not exists."""
        await self.execute(f"CREATE SCHEMA IF NOT EXISTS {self.schema}")

    async def switch_schema(self):
        """Switch to tenant schema."""
        await self.execute(f"SET search_path TO {self.schema}")
```

---

## Implementation Plan

### Phase 1: Row-Level Security (SQLite) - Week 7-8

**Goal**: Basic multi-tenant support for development.

```python
# 1. Tenant Context
class TenantContext(BaseModel):
    tenant_id: UUID | None = None
    user_id: UUID | None = None

    @property
    def is_tenant_scoped(self) -> bool:
        return self.tenant_id is not None

# 2. Access Rules DSL
"""
entity Task:
    owner: ref User required

    access:
        create: authenticated
        read: owner = current_user
        update: owner = current_user
        delete: owner = current_user
"""

# 3. Policy Enforcement
class AccessPolicy:
    entity: str
    operation: Literal["create", "read", "update", "delete"]
    condition: str  # "owner = current_user" or "tenant_id = current_tenant"

    def evaluate(self, context: TenantContext, record: dict) -> bool:
        """Evaluate if access is allowed."""
        ...
```

**Deliverables**:
- `TenantContext` model
- `TenantAwareRepository` with automatic filtering
- Owner-based access rules (current_user checks)
- 20+ tests for RLS

### Phase 2: PostgreSQL Support - Week 9-10

**Goal**: Add PostgreSQL as optional backend with native RLS.

```python
# Database abstraction
class DatabaseBackend(Protocol):
    async def connect(self) -> None: ...
    async def execute(self, sql: str, params: tuple) -> Any: ...
    async def create_table(self, entity: EntitySpec) -> None: ...

# SQLite backend (existing)
class SQLiteBackend(DatabaseBackend): ...

# PostgreSQL backend (new)
class PostgresBackend(DatabaseBackend):
    def __init__(self, connection_string: str):
        self.pool: asyncpg.Pool | None = None

    async def connect(self):
        self.pool = await asyncpg.create_pool(self.connection_string)

    async def setup_rls(self, table: str):
        """Enable PostgreSQL Row Level Security."""
        ...
```

**Deliverables**:
- `PostgresBackend` implementation
- Native RLS support
- Connection pooling
- Migration support for Postgres
- Docker Compose for local Postgres

### Phase 3: Schema Isolation (Optional) - Future

For enterprise use cases requiring strict tenant isolation.

---

## Database Selection Strategy

```python
# In BackendSpec or dazzle.toml
class DatabaseConfig(BaseModel):
    backend: Literal["sqlite", "postgres"] = "sqlite"

    # SQLite options
    sqlite_path: str = ".dazzle/data.db"

    # PostgreSQL options
    postgres_url: str | None = None
    postgres_pool_size: int = 10

    # Multi-tenant options
    tenant_mode: Literal["none", "row_level", "schema", "database"] = "none"
```

```toml
# dazzle.toml
[database]
backend = "postgres"
postgres_url = "postgresql://localhost/myapp"
tenant_mode = "row_level"
```

---

## Owner-Based Access (Simpler Alternative)

For many apps, full multi-tenancy is overkill. "Owner-based" access is simpler:

```python
# Simple owner check
class OwnerPolicy:
    """Check if current user owns the record."""

    owner_field: str = "owner_id"  # Field that stores owner UUID

    def can_read(self, record: dict, user_id: UUID) -> bool:
        return record.get(self.owner_field) == user_id

    def can_update(self, record: dict, user_id: UUID) -> bool:
        return record.get(self.owner_field) == user_id

    def can_delete(self, record: dict, user_id: UUID) -> bool:
        return record.get(self.owner_field) == user_id
```

This handles 80% of use cases without tenant complexity.

---

## PostgreSQL Local Development

For developers who need PostgreSQL features:

### Option 1: Docker Compose (Recommended)

```yaml
# docker-compose.yml (auto-generated)
version: '3.8'
services:
  db:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: dazzle
      POSTGRES_USER: dazzle
      POSTGRES_PASSWORD: dazzle
    ports:
      - "5432:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data

volumes:
  pgdata:
```

```bash
# CLI command
dazzle dnr serve --db postgres
# Auto-starts Docker container if not running
```

### Option 2: Embedded PostgreSQL

Using `postgresql-embedded` or similar:

```python
# Auto-download and run PostgreSQL
async def start_embedded_postgres():
    from postgresql_embedded import PostgreSQL

    pg = PostgreSQL()
    await pg.install()  # Downloads if needed
    await pg.start()
    return pg.connection_string()
```

### Option 3: Cloud PostgreSQL

For production-like development:

```toml
# dazzle.toml
[database]
backend = "postgres"
postgres_url = "${DATABASE_URL}"  # From .env
```

---

## Recommendation Summary

| Use Case | Database | Tenant Mode | Complexity |
|----------|----------|-------------|------------|
| Development/Prototyping | SQLite | none | Simple |
| Single-tenant SaaS | SQLite or Postgres | none | Simple |
| Multi-user app | SQLite or Postgres | owner-based | Medium |
| Multi-tenant SaaS | PostgreSQL | row_level | Medium |
| Enterprise multi-tenant | PostgreSQL | schema | Complex |
| Strict compliance | PostgreSQL | database | Complex |

**Default Path**:
1. Start with SQLite + owner-based access
2. If multi-tenant needed, add `tenant_id` column + RLS
3. If production scale needed, migrate to PostgreSQL
4. If strict isolation needed, use schema isolation

---

## Next Steps

1. **Implement Owner-Based Access** (This week)
   - Add `owner_id` field detection
   - Repository filters for owner checks
   - Tests for access control

2. **Add Tenant Context** (Next week)
   - `TenantContext` model
   - Automatic `tenant_id` injection
   - Middleware for tenant resolution

3. **PostgreSQL Backend** (Week 9-10)
   - `asyncpg` integration
   - Connection pooling
   - Native RLS support

4. **DSL Syntax for Access Rules** (Future)
   - Parse `access:` blocks in entity definitions
   - Generate policies from DSL
