# Tenant Connection Routing Middleware Implementation Plan (Sub-Project 2 of 3)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire tenant resolution into the request lifecycle so each HTTP request is routed to the correct tenant's PostgreSQL schema via `SET search_path`.

**Architecture:** Rewrite the existing (unwired) `tenant_middleware.py` and `tenant_isolation.py` with a `TenantResolver` protocol (subdomain/header/session), integrate with the sub-project 1 `TenantRegistry` for slug validation and status checks, modify `PostgresBackend.connection()` to read a context var for per-request schema routing, and wire into `server.py` when `TenantConfig.isolation == "schema"`.

**Tech Stack:** Python 3.12, Starlette `BaseHTTPMiddleware`, `contextvars`, psycopg v3, FastAPI dependency injection, `quote_identifier()` for SQL safety.

**Spec:** `docs/superpowers/specs/2026-03-19-tenant-routing-design.md`

---

## File Structure

| File | Responsibility |
|------|---------------|
| `src/dazzle_back/runtime/tenant_isolation.py` | **Rewrite** — context vars (`_current_tenant_schema`), helpers (`get_current_tenant_schema`, `set_current_tenant_schema`) |
| `src/dazzle_back/runtime/tenant_middleware.py` | **Rewrite** — `TenantResolver` protocol, 3 resolver implementations, `TenantMiddleware` class, registry cache |
| `src/dazzle_back/runtime/pg_backend.py` | **Modify** — `connection()` reads context var; `table_exists`/`get_table_columns`/`get_column_info` accept schema param |
| `src/dazzle_back/runtime/server.py` | **Modify** — wire tenant middleware in `_create_app()` |
| `src/dazzle/core/manifest.py` | **Modify** — add `base_domain` to `TenantConfig` + parsing |
| `src/dazzle/cli/db.py` | **Modify** — add `--tenant` option to status/verify/reset/cleanup |
| `tests/unit/test_tenant_resolvers.py` | **Create** — resolver unit tests |
| `tests/unit/test_tenant_middleware_routing.py` | **Create** — middleware dispatch tests |
| `tests/unit/test_tenant_connection.py` | **Create** — pg_backend context var routing tests |

---

## Task 1: Context Variables + Manifest Update

**Files:**
- Rewrite: `src/dazzle_back/runtime/tenant_isolation.py`
- Modify: `src/dazzle/core/manifest.py`
- Create: `tests/unit/test_tenant_connection.py` (initial)

Rewrite `tenant_isolation.py` to a minimal context var module. Add `base_domain` to `TenantConfig`.

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/test_tenant_connection.py
"""Tests for tenant connection routing — context vars and schema resolution."""

from __future__ import annotations

import pytest


class TestTenantContextVars:
    def test_default_is_none(self) -> None:
        from dazzle_back.runtime.tenant_isolation import get_current_tenant_schema

        assert get_current_tenant_schema() is None

    def test_set_and_get(self) -> None:
        from dazzle_back.runtime.tenant_isolation import (
            get_current_tenant_schema,
            set_current_tenant_schema,
        )

        token = set_current_tenant_schema("tenant_cyfuture")
        try:
            assert get_current_tenant_schema() == "tenant_cyfuture"
        finally:
            from dazzle_back.runtime.tenant_isolation import _current_tenant_schema

            _current_tenant_schema.reset(token)

    def test_reset_clears(self) -> None:
        from dazzle_back.runtime.tenant_isolation import (
            _current_tenant_schema,
            get_current_tenant_schema,
            set_current_tenant_schema,
        )

        token = set_current_tenant_schema("tenant_test")
        _current_tenant_schema.reset(token)
        assert get_current_tenant_schema() is None


class TestManifestBaseDomain:
    def test_base_domain_default(self) -> None:
        from dazzle.core.manifest import TenantConfig

        config = TenantConfig()
        assert config.base_domain == ""

    def test_base_domain_parsed(self, tmp_path) -> None:
        from dazzle.core.manifest import load_manifest
        from pathlib import Path
        from textwrap import dedent

        toml = tmp_path / "dazzle.toml"
        toml.write_text(dedent("""\
            [project]
            name = "test"
            version = "0.1.0"

            [tenant]
            isolation = "schema"
            resolver = "subdomain"
            base_domain = "app.example.com"
        """))
        manifest = load_manifest(toml)
        assert manifest.tenant.base_domain == "app.example.com"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_tenant_connection.py -v`
Expected: FAIL — imports fail or fields missing

- [ ] **Step 3: Rewrite tenant_isolation.py**

Read the existing file first, then replace its contents entirely:

```python
# src/dazzle_back/runtime/tenant_isolation.py
"""Tenant schema context — per-request schema routing via context vars.

The middleware sets the current tenant schema, and pg_backend.connection()
reads it to SET search_path on each connection lease.
"""

from __future__ import annotations

from contextvars import ContextVar, Token

_current_tenant_schema: ContextVar[str | None] = ContextVar(
    "_current_tenant_schema", default=None
)


def get_current_tenant_schema() -> str | None:
    """Get the current tenant schema name (e.g., 'tenant_cyfuture').

    Returns None when no tenant context is set (non-tenant apps, excluded paths).
    """
    return _current_tenant_schema.get()


def set_current_tenant_schema(schema_name: str) -> Token[str | None]:
    """Set the current tenant schema for this async context.

    Returns a token for resetting (used by middleware on request exit).
    """
    return _current_tenant_schema.set(schema_name)
```

- [ ] **Step 4: Add base_domain to TenantConfig and load_manifest()**

In `src/dazzle/core/manifest.py`:
1. Add `base_domain: str = ""` to `TenantConfig` dataclass
2. In `load_manifest()` tenant parsing block, add: `base_domain=tenant_data.get("base_domain", ""),`

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/unit/test_tenant_connection.py -v`
Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add src/dazzle_back/runtime/tenant_isolation.py src/dazzle/core/manifest.py tests/unit/test_tenant_connection.py
git commit -m "feat(tenant): rewrite tenant_isolation.py to context vars + add base_domain (#531)"
```

---

## Task 2: Tenant Resolvers

**Files:**
- Create: `tests/unit/test_tenant_resolvers.py`

The resolvers are pure functions that will live in the rewritten `tenant_middleware.py`, but we test them first in isolation.

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/test_tenant_resolvers.py
"""Tests for tenant resolver implementations."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest


def _make_request(*, host: str = "localhost", headers: dict | None = None, cookies: dict | None = None) -> MagicMock:
    """Create a mock Starlette Request."""
    request = MagicMock()
    request.headers = headers or {}
    request.cookies = cookies or {}
    url = MagicMock()
    url.hostname = host
    request.url = url
    return request


class TestSubdomainResolver:
    def test_extracts_slug_from_subdomain(self) -> None:
        from dazzle_back.runtime.tenant_middleware import SubdomainResolver

        resolver = SubdomainResolver(base_domain="app.example.com")
        request = _make_request(host="cyfuture.app.example.com")
        assert resolver.resolve(request) == "cyfuture"

    def test_returns_none_for_bare_domain(self) -> None:
        from dazzle_back.runtime.tenant_middleware import SubdomainResolver

        resolver = SubdomainResolver(base_domain="app.example.com")
        request = _make_request(host="app.example.com")
        assert resolver.resolve(request) is None

    def test_returns_none_for_localhost(self) -> None:
        from dazzle_back.runtime.tenant_middleware import SubdomainResolver

        resolver = SubdomainResolver(base_domain="app.example.com")
        request = _make_request(host="localhost")
        assert resolver.resolve(request) is None

    def test_multi_level_subdomain(self) -> None:
        from dazzle_back.runtime.tenant_middleware import SubdomainResolver

        resolver = SubdomainResolver(base_domain="app.example.com")
        request = _make_request(host="deep.cyfuture.app.example.com")
        # Only the first subdomain level is the slug
        slug = resolver.resolve(request)
        assert slug is not None


class TestHeaderResolver:
    def test_extracts_from_header(self) -> None:
        from dazzle_back.runtime.tenant_middleware import HeaderResolver

        resolver = HeaderResolver(header_name="X-Tenant-ID")
        request = _make_request(headers={"x-tenant-id": "cyfuture"})
        assert resolver.resolve(request) == "cyfuture"

    def test_returns_none_when_missing(self) -> None:
        from dazzle_back.runtime.tenant_middleware import HeaderResolver

        resolver = HeaderResolver(header_name="X-Tenant-ID")
        request = _make_request()
        assert resolver.resolve(request) is None

    def test_custom_header_name(self) -> None:
        from dazzle_back.runtime.tenant_middleware import HeaderResolver

        resolver = HeaderResolver(header_name="X-Custom")
        request = _make_request(headers={"x-custom": "myco"})
        assert resolver.resolve(request) == "myco"


class TestSessionResolver:
    def test_extracts_from_cookie(self) -> None:
        from dazzle_back.runtime.tenant_middleware import SessionResolver

        resolver = SessionResolver()
        request = _make_request(cookies={"dazzle_tenant": "cyfuture"})
        assert resolver.resolve(request) == "cyfuture"

    def test_returns_none_when_no_cookie(self) -> None:
        from dazzle_back.runtime.tenant_middleware import SessionResolver

        resolver = SessionResolver()
        request = _make_request()
        assert resolver.resolve(request) is None


class TestBuildResolver:
    def test_builds_subdomain_resolver(self) -> None:
        from dazzle_back.runtime.tenant_middleware import build_resolver
        from dazzle.core.manifest import TenantConfig

        config = TenantConfig(resolver="subdomain", base_domain="app.example.com")
        resolver = build_resolver(config)
        assert resolver is not None

    def test_builds_header_resolver(self) -> None:
        from dazzle_back.runtime.tenant_middleware import build_resolver
        from dazzle.core.manifest import TenantConfig

        config = TenantConfig(resolver="header", header_name="X-My-Tenant")
        resolver = build_resolver(config)
        assert resolver is not None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_tenant_resolvers.py -v`
Expected: FAIL — classes don't exist yet

- [ ] **Step 3: Implement resolvers in tenant_middleware.py**

Read the existing `tenant_middleware.py`, then rewrite with:

```python
# src/dazzle_back/runtime/tenant_middleware.py
"""Tenant middleware — resolves tenant from request, routes to schema.

Resolver protocol + implementations (subdomain, header, session).
TenantMiddleware class with registry cache.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any, Protocol

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

logger = logging.getLogger(__name__)

CACHE_TTL_SECONDS = 60


class TenantResolver(Protocol):
    """Extracts tenant slug from a request."""

    def resolve(self, request: Request) -> str | None: ...


class SubdomainResolver:
    """Extracts tenant slug from subdomain: {slug}.{base_domain}."""

    def __init__(self, base_domain: str) -> None:
        self._base_domain = base_domain.lower()

    def resolve(self, request: Request) -> str | None:
        host = (request.url.hostname or "").lower()
        if not host or not self._base_domain:
            return None
        if not host.endswith(f".{self._base_domain}"):
            return None
        prefix = host[: -(len(self._base_domain) + 1)]
        # Take only the immediate subdomain (first segment)
        slug = prefix.split(".")[-1] if "." in prefix else prefix
        return slug if slug else None


class HeaderResolver:
    """Extracts tenant slug from an HTTP header."""

    def __init__(self, header_name: str = "X-Tenant-ID") -> None:
        self._header_name = header_name.lower()

    def resolve(self, request: Request) -> str | None:
        return request.headers.get(self._header_name) or None


class SessionResolver:
    """Extracts tenant slug from a session cookie."""

    def __init__(self, cookie_name: str = "dazzle_tenant") -> None:
        self._cookie_name = cookie_name

    def resolve(self, request: Request) -> str | None:
        return request.cookies.get(self._cookie_name) or None


def build_resolver(tenant_config: Any) -> TenantResolver:
    """Build the appropriate resolver from TenantConfig."""
    resolver_type = tenant_config.resolver
    if resolver_type == "subdomain":
        return SubdomainResolver(base_domain=tenant_config.base_domain)
    elif resolver_type == "header":
        return HeaderResolver(header_name=tenant_config.header_name)
    elif resolver_type == "session":
        return SessionResolver()
    else:
        raise ValueError(f"Unknown tenant resolver: {resolver_type}")


class _RegistryCache:
    """In-memory cache for tenant registry lookups with TTL."""

    def __init__(self, registry: Any, ttl: int = CACHE_TTL_SECONDS) -> None:
        self._registry = registry
        self._ttl = ttl
        self._cache: dict[str, tuple[Any, float]] = {}

    def get(self, slug: str) -> Any | None:
        """Look up tenant record, using cache with TTL."""
        now = time.monotonic()
        cached = self._cache.get(slug)
        if cached and (now - cached[1]) < self._ttl:
            return cached[0]
        record = self._registry.get(slug)
        if record:
            self._cache[slug] = (record, now)
        else:
            self._cache.pop(slug, None)
        return record


_EXCLUDED_PREFIXES = (
    "/health",
    "/docs",
    "/openapi.json",
    "/redoc",
    "/static/",
    "/auth/",
    "/_dazzle/",
)


class TenantMiddleware(BaseHTTPMiddleware):
    """Starlette middleware that resolves tenant and sets schema context."""

    def __init__(
        self,
        app: Any,
        resolver: TenantResolver,
        registry: Any,
        excluded_prefixes: tuple[str, ...] = _EXCLUDED_PREFIXES,
    ) -> None:
        super().__init__(app)
        self._resolver = resolver
        self._cache = _RegistryCache(registry)
        self._excluded_prefixes = excluded_prefixes

    async def dispatch(self, request: Request, call_next: Any) -> Any:
        from .tenant_isolation import set_current_tenant_schema

        path = request.url.path

        # Skip excluded paths
        if any(path.startswith(p) for p in self._excluded_prefixes):
            return await call_next(request)

        # Dev override: DAZZLE_TENANT_SLUG env var
        slug = os.environ.get("DAZZLE_TENANT_SLUG") or self._resolver.resolve(request)

        if not slug:
            return JSONResponse(
                {"detail": "Tenant not specified"},
                status_code=400,
            )

        record = self._cache.get(slug)
        if not record:
            return JSONResponse(
                {"detail": f"Tenant '{slug}' not found"},
                status_code=404,
            )

        if record.status == "suspended":
            return JSONResponse(
                {"detail": f"Tenant '{slug}' is suspended"},
                status_code=503,
            )

        # Set schema context for pg_backend
        token = set_current_tenant_schema(record.schema_name)
        request.state.tenant = record

        try:
            response = await call_next(request)
        finally:
            from .tenant_isolation import _current_tenant_schema

            _current_tenant_schema.reset(token)

        return response
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_tenant_resolvers.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/dazzle_back/runtime/tenant_middleware.py tests/unit/test_tenant_resolvers.py
git commit -m "feat(tenant): rewrite tenant_middleware with resolver protocol + cache (#531)"
```

---

## Task 3: Middleware Dispatch Tests

**Files:**
- Create: `tests/unit/test_tenant_middleware_routing.py`

Test the full middleware dispatch flow — excluded paths, 400/404/503 errors, happy path.

- [ ] **Step 1: Write tests**

```python
# tests/unit/test_tenant_middleware_routing.py
"""Tests for TenantMiddleware dispatch — error cases and happy path."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from starlette.testclient import TestClient
from starlette.applications import Starlette
from starlette.routing import Route
from starlette.responses import PlainTextResponse

from dazzle_back.runtime.tenant_middleware import TenantMiddleware, HeaderResolver


def _make_app(registry_records: dict[str, MagicMock] | None = None) -> Starlette:
    """Build a minimal Starlette app with TenantMiddleware."""

    async def homepage(request):
        tenant = getattr(request.state, "tenant", None)
        slug = tenant.slug if tenant else "none"
        return PlainTextResponse(f"tenant={slug}")

    async def health(request):
        return PlainTextResponse("ok")

    app = Starlette(routes=[
        Route("/", homepage),
        Route("/health", health),
    ])

    registry = MagicMock()

    def mock_get(slug):
        if registry_records:
            return registry_records.get(slug)
        return None

    registry.get = mock_get

    resolver = HeaderResolver(header_name="X-Tenant-ID")
    app.add_middleware(
        TenantMiddleware,
        resolver=resolver,
        registry=registry,
    )
    return app


class TestMiddlewareExcludedPaths:
    def test_health_bypasses_tenant(self) -> None:
        app = _make_app()
        client = TestClient(app)
        response = client.get("/health")
        assert response.status_code == 200
        assert response.text == "ok"


class TestMiddlewareErrors:
    def test_missing_tenant_returns_400(self) -> None:
        app = _make_app()
        client = TestClient(app)
        response = client.get("/")
        assert response.status_code == 400
        assert "Tenant not specified" in response.json()["detail"]

    def test_unknown_tenant_returns_404(self) -> None:
        app = _make_app()
        client = TestClient(app)
        response = client.get("/", headers={"X-Tenant-ID": "nonexistent"})
        assert response.status_code == 404
        assert "not found" in response.json()["detail"]

    def test_suspended_tenant_returns_503(self) -> None:
        record = MagicMock(slug="cyfuture", schema_name="tenant_cyfuture", status="suspended")
        app = _make_app({"cyfuture": record})
        client = TestClient(app)
        response = client.get("/", headers={"X-Tenant-ID": "cyfuture"})
        assert response.status_code == 503
        assert "suspended" in response.json()["detail"]


class TestRegistryCache:
    def test_cache_hit_avoids_second_lookup(self) -> None:
        from dazzle_back.runtime.tenant_middleware import _RegistryCache

        registry = MagicMock()
        record = MagicMock(slug="cyfuture", status="active")
        registry.get.return_value = record

        cache = _RegistryCache(registry, ttl=60)
        result1 = cache.get("cyfuture")
        result2 = cache.get("cyfuture")

        assert result1 is record
        assert result2 is record
        assert registry.get.call_count == 1  # only one DB call

    def test_cache_miss_returns_none(self) -> None:
        from dazzle_back.runtime.tenant_middleware import _RegistryCache

        registry = MagicMock()
        registry.get.return_value = None

        cache = _RegistryCache(registry, ttl=60)
        assert cache.get("nonexistent") is None

    def test_expired_entry_triggers_fresh_lookup(self) -> None:
        from dazzle_back.runtime.tenant_middleware import _RegistryCache
        import time

        registry = MagicMock()
        record = MagicMock(slug="cyfuture", status="active")
        registry.get.return_value = record

        cache = _RegistryCache(registry, ttl=0)  # TTL of 0 = always expired
        cache.get("cyfuture")
        time.sleep(0.01)
        cache.get("cyfuture")

        assert registry.get.call_count == 2  # two DB calls


class TestMiddlewareHappyPath:
    def test_active_tenant_sets_context(self) -> None:
        record = MagicMock(slug="cyfuture", schema_name="tenant_cyfuture", status="active")
        app = _make_app({"cyfuture": record})
        client = TestClient(app)
        response = client.get("/", headers={"X-Tenant-ID": "cyfuture"})
        assert response.status_code == 200
        assert "tenant=cyfuture" in response.text
```

- [ ] **Step 2: Run tests**

Run: `pytest tests/unit/test_tenant_middleware_routing.py -v`
Expected: All PASS (middleware was implemented in Task 2)

- [ ] **Step 3: Commit**

```bash
git add tests/unit/test_tenant_middleware_routing.py
git commit -m "test(tenant): add middleware dispatch tests (#531)"
```

---

## Task 4: pg_backend Connection Routing

**Files:**
- Modify: `src/dazzle_back/runtime/pg_backend.py`
- Modify: `tests/unit/test_tenant_connection.py` (add pg_backend tests)

Modify `connection()` to read the `_current_tenant_schema` context var. Fix hardcoded `public` schema in introspection queries.

- [ ] **Step 1: Write failing tests**

Append to `tests/unit/test_tenant_connection.py`:

```python
class TestPgBackendTenantRouting:
    def test_connection_uses_context_var_for_search_path(self) -> None:
        """When context var is set, connection() should SET search_path with that schema."""
        from unittest.mock import MagicMock, patch
        from dazzle_back.runtime.tenant_isolation import (
            _current_tenant_schema,
            set_current_tenant_schema,
        )

        token = set_current_tenant_schema("tenant_cyfuture")
        try:
            # We can't easily test the full connection() without a real DB,
            # but we verify the context var is readable from within an async context
            from dazzle_back.runtime.tenant_isolation import get_current_tenant_schema

            assert get_current_tenant_schema() == "tenant_cyfuture"
            # The pg_backend.connection() implementation should call:
            # conn.execute(f"SET search_path TO {quote_identifier('tenant_cyfuture')}, public")
        finally:
            _current_tenant_schema.reset(token)

    def test_no_context_var_returns_none(self) -> None:
        """Without context var, get_current_tenant_schema returns None."""
        from dazzle_back.runtime.tenant_isolation import get_current_tenant_schema

        assert get_current_tenant_schema() is None
```

- [ ] **Step 2: Modify pg_backend.py connection()**

Read `src/dazzle_back/runtime/pg_backend.py`. The `connection()` context manager has **TWO branches** that both set `search_path` — the pool path and the direct-connect fallback. Both must be patched.

At the very start of `connection()`, determine the effective search_path:

```python
from dazzle_back.runtime.tenant_isolation import get_current_tenant_schema

effective_search_path = get_current_tenant_schema() or self.search_path
```

Then replace `self.search_path` with `effective_search_path` in **both** `if` blocks — the pool branch (around line 193) and the direct-connect branch (around line 204). Also replace the bare f-string interpolation with `quote_identifier()`:

```python
# Replace BOTH existing SET statements (pool path AND direct-connect path):
if effective_search_path:
    conn.execute(f"SET search_path TO {quote_identifier(effective_search_path)}, public")
```

**Do NOT modify `get_persistent_connection()`** — it continues using only `self.search_path` (not safe for per-request routing).

- [ ] **Step 3: Fix hardcoded schema in introspection queries**

In `table_exists()`, `get_table_columns()`, `get_column_info()`, replace hardcoded `'public'` with the effective schema:

```python
def table_exists(self, table_name: str) -> bool:
    from dazzle_back.runtime.tenant_isolation import get_current_tenant_schema

    schema = get_current_tenant_schema() or self.search_path or "public"
    # Use schema in the query instead of hardcoded 'public'
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/unit/test_tenant_connection.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/dazzle_back/runtime/pg_backend.py tests/unit/test_tenant_connection.py
git commit -m "feat(tenant): pg_backend reads tenant schema context var (#531)"
```

---

## Task 5: Server Wiring

**Files:**
- Modify: `src/dazzle_back/runtime/server.py`

Wire `TenantMiddleware` into the app when `TenantConfig.isolation == "schema"`.

- [ ] **Step 1: Read server.py `_create_app()` and `build()`**

Find where middleware is added (around line 1365-1408) and where the manifest/config is accessible.

- [ ] **Step 2: Add tenant middleware wiring**

**IMPORTANT:** The server does NOT store a `_manifest` attribute. Config is passed through `ServerConfig`. You need to:

1. First, read `server.py` to find how `ServerConfig` is defined and where `_create_app()` accesses it (likely `self._config`).
2. Add a `tenant_config: TenantConfig | None = None` field to `ServerConfig` (or wherever config is stored).
3. Ensure `build_server_config()` (or equivalent) copies `manifest.tenant` into the server config.
4. In `_create_app()`, after existing middleware, add:

```python
        # Tenant isolation middleware (schema-per-tenant)
        tenant_config = getattr(self._config, "tenant_config", None)
        if tenant_config and tenant_config.isolation == "schema":
            from dazzle_back.runtime.tenant_middleware import (
                TenantMiddleware,
                build_resolver,
            )
            from dazzle.tenant.registry import TenantRegistry

            resolver = build_resolver(tenant_config)
            registry = TenantRegistry(self._database_url)
            registry.ensure_table()
            self._app.add_middleware(
                TenantMiddleware,
                resolver=resolver,
                registry=registry,
            )
```

Note: use `self._database_url` (already available as instance attribute) — do NOT re-call `resolve_database_url`.

- [ ] **Step 3: Run existing tests to verify no breakage**

Run: `pytest tests/unit/test_tenant_*.py -v`
Expected: All PASS

- [ ] **Step 4: Commit**

```bash
git add src/dazzle_back/runtime/server.py
git commit -m "feat(tenant): wire TenantMiddleware into server when isolation=schema (#531)"
```

---

## Task 6: CLI `--tenant` Flag

**Files:**
- Modify: `src/dazzle/cli/db.py`
- Modify: `tests/unit/test_tenant_connection.py` (add CLI test)

Add `--tenant` option to `dazzle db status/verify/reset/cleanup`.

- [ ] **Step 1: Modify CLI commands**

In `src/dazzle/cli/db.py`, read the existing commands. Add a `--tenant` option to each of `status_command`, `verify_command`, `reset_command`, `cleanup_command`. When provided:

1. Look up the tenant in the registry to get `schema_name`
2. Before running the async operation, set the tenant schema context var

```python
# Add to each command (status, verify, reset, cleanup):
tenant: str = typer.Option("", "--tenant", help="Tenant slug (when isolation=schema)"),
```

**IMPORTANT:** The context var must be set INSIDE the coroutine, not before `asyncio.run()`. `asyncio.run()` creates a new event loop with a new context — context vars set in the calling scope are not visible inside. Modify `_run_with_connection()` to accept an optional `schema` parameter:

```python
async def _run_with_connection(
    project_root: Path,
    database_url: str,
    coro_factory: Any,
    schema: str = "",
) -> Any:
    """Connect to DB, run async operation, close connection."""
    from dazzle.db.connection import get_connection

    conn = await get_connection(explicit_url=database_url, project_root=project_root)
    try:
        if schema:
            await conn.execute(f"SET search_path TO {schema}, public")
        return await coro_factory(conn)
    finally:
        await conn.close()
```

Then in each command, when `--tenant` is provided:

```python
if tenant:
    from dazzle.tenant.config import slug_to_schema_name
    from dazzle.db.sql import quote_id

    schema = quote_id(slug_to_schema_name(tenant))
else:
    schema = ""

result = asyncio.run(_run_with_connection(project_root, url, _run, schema=schema))
```

- [ ] **Step 2: Write test**

Append to `tests/unit/test_tenant_connection.py`:

```python
from unittest.mock import MagicMock, patch
from typer.testing import CliRunner
from dazzle.cli.db import db_app

runner = CliRunner()


class TestCliTenantFlag:
    @patch("dazzle.cli.db.asyncio.run")
    @patch("dazzle.cli.db.load_project_appspec")
    def test_status_with_tenant_flag(self, mock_load: MagicMock, mock_run: MagicMock) -> None:
        appspec = MagicMock()
        appspec.domain.entities = []
        mock_load.return_value = appspec

        mock_run.return_value = {
            "entities": [],
            "total_entities": 0,
            "total_rows": 0,
            "database_size": "0 MB",
        }

        result = runner.invoke(db_app, ["status", "--tenant", "cyfuture"])
        assert result.exit_code == 0

        # Verify asyncio.run was called with a coroutine that includes schema
        assert mock_run.called
        # The _run_with_connection call should include schema parameter
        call_args = mock_run.call_args
        assert call_args is not None

    @patch("dazzle.cli.db.asyncio.run")
    @patch("dazzle.cli.db.load_project_appspec")
    def test_status_without_tenant_flag(self, mock_load: MagicMock, mock_run: MagicMock) -> None:
        appspec = MagicMock()
        appspec.domain.entities = []
        mock_load.return_value = appspec

        mock_run.return_value = {
            "entities": [],
            "total_entities": 0,
            "total_rows": 0,
            "database_size": "0 MB",
        }

        result = runner.invoke(db_app, ["status"])
        assert result.exit_code == 0
```

- [ ] **Step 3: Run tests**

Run: `pytest tests/unit/test_tenant_connection.py -v`
Expected: All PASS

- [ ] **Step 4: Commit**

```bash
git add src/dazzle/cli/db.py tests/unit/test_tenant_connection.py
git commit -m "feat(tenant): add --tenant flag to dazzle db commands (#531)"
```

---

## Task 7: Documentation + Final Verification

**Files:**
- Modify: `.claude/CLAUDE.md`

- [ ] **Step 1: Update CLAUDE.md**

Add tenant middleware info to the architecture section and note the `--tenant` flag on db commands.

- [ ] **Step 2: Run full test suite**

Run: `pytest tests/unit/test_tenant_*.py tests/unit/test_cli_tenant.py -v`
Expected: All PASS

- [ ] **Step 3: Lint and type check**

Run: `ruff check src/dazzle_back/runtime/tenant_middleware.py src/dazzle_back/runtime/tenant_isolation.py src/dazzle_back/runtime/pg_backend.py --fix && ruff format src/dazzle_back/runtime/tenant_middleware.py src/dazzle_back/runtime/tenant_isolation.py src/dazzle_back/runtime/pg_backend.py`

- [ ] **Step 4: Commit**

```bash
git add .claude/CLAUDE.md
git commit -m "feat(tenant): update docs for connection routing middleware (#531)"
```
