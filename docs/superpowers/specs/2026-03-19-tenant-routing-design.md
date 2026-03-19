# Schema-Per-Tenant: Connection Routing Middleware (Sub-Project 2 of 3)

**Date**: 2026-03-19
**Status**: Design
**Issue**: #531
**Scope**: Sub-project 2 — request-time tenant resolution and schema routing. Depends on sub-project 1 (config, registry, CLI). Sub-project 3 (multi-schema migrations) is a separate spec.

## Problem

Sub-project 1 created the tenant registry and CLI for managing tenant schemas. But the runtime doesn't use them yet — all requests hit the `public` schema. This sub-project wires tenant resolution into the request lifecycle so each request is routed to the correct tenant schema.

## Existing Code

Two files from v0.11.0 (Dec 2025) implement aspirational tenant middleware:
- `src/dazzle_back/runtime/tenant_middleware.py` — middleware factory (header/cookie/query resolution)
- `src/dazzle_back/runtime/tenant_isolation.py` — `TenantDatabaseManager`, context vars

These predate the registry, `TenantConfig`, scope blocks, and the RBAC model. Nothing imports them — they're completely unwired. This sub-project refactors them to integrate with the sub-project 1 registry and the current runtime architecture.

---

## Design

### Tenant Resolver Protocol

```python
class TenantResolver(Protocol):
    def resolve(self, request: Request) -> str | None:
        """Extract tenant slug from request. Returns None if not found."""
```

Three implementations, selected at startup from `TenantConfig.resolver`:

| Resolver | Source | Config |
|---|---|---|
| `SubdomainResolver` | `{slug}.example.com` | Needs `base_domain` in `TenantConfig` |
| `HeaderResolver` | `X-Tenant-ID` header | Uses `TenantConfig.header_name` |
| `SessionResolver` | Auth session cookie | Reads `tenant_slug` from session data |

`SubdomainResolver` requires a new `base_domain` field on `TenantConfig`:

```python
@dataclass
class TenantConfig:
    isolation: str = "none"
    resolver: str = "subdomain"
    header_name: str = "X-Tenant-ID"
    base_domain: str = ""  # NEW: required when resolver = "subdomain"
```

For subdomain resolution: request to `cyfuture.app.example.com` with `base_domain = "app.example.com"` extracts slug `cyfuture`. Requests to the bare `app.example.com` or `localhost` return None (no tenant context — useful for admin/platform routes).

**`base_domain` must be added to `load_manifest()` parsing** alongside the existing `isolation`/`resolver`/`header_name` fields:
```python
base_domain=tenant_data.get("base_domain", ""),
```

**Dev mode:** When `resolver = "subdomain"` and running on localhost, every request would get 400 (no subdomain). For local dev, use `resolver = "header"` and pass `X-Tenant-ID` in requests, or set `DAZZLE_TENANT_SLUG` env var to bypass resolution entirely. The middleware checks this env var first — if set, it skips resolver logic and uses the slug directly.

---

### Middleware

`TenantMiddleware` is a Starlette `BaseHTTPMiddleware` subclass:

```python
class TenantMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, resolver, registry, excluded_paths=None): ...

    async def dispatch(self, request, call_next):
        # 1. Skip excluded paths (health, static, docs)
        # 2. resolver.resolve(request) → slug
        # 3. slug is None → 400
        # 4. registry lookup (cached) → record
        # 5. record is None → 404
        # 6. record.status == "suspended" → 503
        # 7. Set search_path context var + request.state.tenant
        # 8. call_next(request)
```

**Excluded paths:** `/health`, `/docs`, `/openapi.json`, `/static/`, `/auth/login`, `/auth/callback`. These serve platform content that doesn't belong to any tenant.

**Registry cache:** In-memory dict (slug → TenantRecord) with TTL of 60 seconds. Avoids a DB query on every request. The TTL is short enough that `dazzle tenant suspend` takes effect within a minute. Note: the CLI runs in a separate process from `dazzle serve`, so there's no shared in-memory cache — the TTL-based DB re-query is the invalidation mechanism.

---

### Connection Routing

Single connection pool, per-connection `SET search_path`:

1. Middleware resolves tenant → sets `_current_tenant_schema` context var to `"tenant_{slug}"`
2. Modify `PostgresBackend.connection()` to check the `_current_tenant_schema` context var. Currently, `connection()` takes no parameters — `search_path` is an instance-level attribute set at construction time. The change: if the context var is set, use it; else fall back to `self.search_path`; else use `public`.
3. Both the pool path (`self._pool.connection()`) and the direct-connect fallback path need this change.
4. Each connection lease runs `SET search_path TO "tenant_{slug}", public` using `quote_identifier()` on the schema name — **never** string interpolation. The existing `pg_backend.py` already imports `quote_identifier`.
5. `get_persistent_connection()` must NOT read the tenant context var — it's not per-request safe and is used for long-lived connections (migrations, schema introspection).

This is the django-tenants pattern. No pool-per-tenant overhead. Works well for the "manageable number of high-value tenants" use case.

**Schema name safety:** The schema name is `tenant_{slug}` where `slug` passes `^[a-z][a-z0-9_]{1,55}$` validation at registry insertion time. Additionally, `SET search_path` must use `quote_identifier()` for defence-in-depth.

**Introspection queries:** `table_exists()`, `get_table_columns()`, and `get_column_info()` in `pg_backend.py` hardcode `schemaname = 'public'`. These must be updated to use the current tenant schema when set, or accept a `schema` parameter. Without this, `dazzle db verify --tenant` would always inspect `public`.

**Fallback:** When no tenant context is set (excluded paths, non-tenant apps), the default `search_path` (`public`) is used. This is the zero-impact path for existing non-tenant apps.

**Known limitation:** `create_all_tables()` uses SQLAlchemy's `metadata.create_all()` which defaults to `public` schema. This is a sub-project 3 concern — do not use `create_all_tables()` for tenant schema provisioning.

---

### Server Wiring

**Middleware execution order:** Starlette executes middleware in reverse add order (last added = outermost = first to execute). `TenantMiddleware` must execute **before** `AuthMiddleware` — tenant context must be set before auth queries the correct schema. Since auth is set up later (in `_setup_auth()`), adding tenant middleware in `_create_app()` places it correctly in the stack.

In `DazzleBackendApp._create_app()`, after existing middleware:

```python
if manifest.tenant.isolation == "schema":
    resolver = _build_resolver(manifest.tenant)
    registry = TenantRegistry(database_url)
    registry.ensure_table()
    app.add_middleware(
        TenantMiddleware,
        resolver=resolver,
        registry=registry,
        excluded_paths=["/health", "/docs", "/openapi.json", "/static/", "/auth/"],
    )
```

No-op when `isolation == "none"`. Existing apps are completely unaffected.

---

### `--tenant` Flag on `dazzle db` Commands

When `TenantConfig.isolation == "schema"`, the `dazzle db status/verify/reset/cleanup` commands gain a `--tenant <slug>` option:

- **With `--tenant`:** Operations target the tenant's schema (sets `search_path` before running queries)
- **Without `--tenant`:** Operations target `public` schema only (platform tables)

This reuses the existing `dazzle.db` package functions — only the connection setup changes.

---

### Error Responses

| Condition | HTTP Status | Body |
|---|---|---|
| No tenant slug in request | 400 | `{"detail": "Tenant not specified"}` |
| Unknown tenant slug | 404 | `{"detail": "Tenant 'foo' not found"}` |
| Suspended tenant | 503 | `{"detail": "Tenant 'foo' is suspended"}` |

All error responses use FastAPI's standard `{"detail": "..."}` shape with `content-type: application/json`.

---

### File Structure

| File | Responsibility |
|------|---------------|
| `src/dazzle_back/runtime/tenant_middleware.py` | **Rewrite** — `TenantMiddleware`, resolver protocol, three resolver implementations, registry cache |
| `src/dazzle_back/runtime/tenant_isolation.py` | **Rewrite** — context vars for current tenant schema, helper to read tenant from request state |
| `src/dazzle_back/runtime/pg_backend.py` | **Modify** — read `_current_tenant_schema` context var in `connection()` |
| `src/dazzle_back/runtime/server.py` | **Modify** — wire middleware in `_create_app()` when tenant mode enabled |
| `src/dazzle/core/manifest.py` | **Modify** — add `base_domain` field to `TenantConfig` |
| `src/dazzle/cli/db.py` | **Modify** — add `--tenant` option to status/verify/reset/cleanup |
| `tests/unit/test_tenant_resolvers.py` | Resolver unit tests |
| `tests/unit/test_tenant_middleware.py` | Middleware tests (mock registry) |
| `tests/unit/test_tenant_routing.py` | Connection routing tests (mock pg_backend) |

---

### Testing Strategy

| Layer | What to test |
|---|---|
| Resolvers | Each resolver with mock requests — subdomain extraction, header reading, session lookup, None for missing values |
| Middleware | Full dispatch flow — excluded paths bypass, 400/404/503 error cases, happy path sets request.state.tenant |
| Registry cache | TTL expiry, cache hit, invalidation |
| Connection routing | Context var flows to pg_backend, search_path set correctly |
| CLI `--tenant` | Status/verify with `--tenant` flag targets correct schema |

---

### Non-Goals (this sub-project)

- Multi-schema migration runner (sub-project 3)
- Cross-tenant queries or admin dashboards
- Per-tenant connection pooling (single pool is sufficient)
- Automatic tenant provisioning from middleware (use `dazzle tenant create` CLI)
- UI tenant selector / login flow changes
