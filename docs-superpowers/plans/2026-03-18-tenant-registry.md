# Tenant Registry Implementation Plan (Sub-Project 1 of 3)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add opt-in schema-per-tenant support: `TenantConfig` in manifest, `TenantRegistry` for CRUD on `public.tenants`, `TenantProvisioner` for schema creation, and `dazzle tenant` CLI commands.

**Architecture:** New `src/dazzle/tenant/` package with config validation, a psycopg-based registry operating on `public.tenants`, a provisioner that creates PostgreSQL schemas with fully-qualified DDL, and a Typer CLI group. Manifest gets a new `[tenant]` section. All opt-in — apps without the section behave as today.

**Tech Stack:** Python 3.12, psycopg v3 (dict_row), Typer (CLI), Rich (output tables), `dazzle.db.sql.quote_id()` for SQL identifiers.

**Spec:** `docs/superpowers/specs/2026-03-18-tenant-registry-design.md`

---

## File Structure

| File | Responsibility |
|------|---------------|
| `src/dazzle/core/manifest.py` | **Modify** — add `TenantConfig` dataclass + parse `[tenant]` section |
| `src/dazzle/tenant/__init__.py` | Package init |
| `src/dazzle/tenant/config.py` | Slug validation (`validate_slug()`), schema name derivation, constants |
| `src/dazzle/tenant/registry.py` | `TenantRegistry` + `TenantRecord` — psycopg CRUD on `public.tenants` |
| `src/dazzle/tenant/provisioner.py` | `TenantProvisioner` — CREATE SCHEMA + entity/auth table DDL |
| `src/dazzle/cli/tenant.py` | CLI commands: create, list, status, suspend, activate |
| `src/dazzle/cli/__init__.py` | **Modify** — register `tenant_app` |
| `tests/unit/test_tenant_config.py` | Tests for TenantConfig + slug validation |
| `tests/unit/test_tenant_registry.py` | Tests for TenantRegistry (mocked psycopg) |
| `tests/unit/test_tenant_provisioner.py` | Tests for TenantProvisioner (mocked DDL) |
| `tests/unit/test_cli_tenant.py` | Tests for CLI commands (mocked registry/provisioner) |

---

## Task 1: TenantConfig in Manifest

**Files:**
- Modify: `src/dazzle/core/manifest.py`
- Create: `tests/unit/test_tenant_config.py`

Add `TenantConfig` dataclass and parse the `[tenant]` section.

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/test_tenant_config.py
"""Tests for tenant configuration and slug validation."""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

import pytest

from dazzle.core.manifest import TenantConfig, load_manifest


class TestTenantConfigDefaults:
    def test_default_isolation_is_none(self) -> None:
        config = TenantConfig()
        assert config.isolation == "none"

    def test_default_resolver(self) -> None:
        config = TenantConfig()
        assert config.resolver == "subdomain"

    def test_default_header_name(self) -> None:
        config = TenantConfig()
        assert config.header_name == "X-Tenant-ID"


class TestTenantConfigFromManifest:
    def test_absent_tenant_section_gives_defaults(self, tmp_path: Path) -> None:
        toml = tmp_path / "dazzle.toml"
        toml.write_text(dedent("""\
            [project]
            name = "test"
            version = "0.1.0"
        """))
        manifest = load_manifest(toml)
        assert manifest.tenant.isolation == "none"

    def test_schema_isolation_parsed(self, tmp_path: Path) -> None:
        toml = tmp_path / "dazzle.toml"
        toml.write_text(dedent("""\
            [project]
            name = "test"
            version = "0.1.0"

            [tenant]
            isolation = "schema"
            resolver = "header"
            header_name = "X-Custom-Tenant"
        """))
        manifest = load_manifest(toml)
        assert manifest.tenant.isolation == "schema"
        assert manifest.tenant.resolver == "header"
        assert manifest.tenant.header_name == "X-Custom-Tenant"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_tenant_config.py -v`
Expected: FAIL — `TenantConfig` not found

- [ ] **Step 3: Implement**

In `src/dazzle/core/manifest.py`:

1. Add `TenantConfig` dataclass after `DevConfig` (around line 296):

```python
@dataclass
class TenantConfig:
    """Multi-tenant configuration.

    isolation = "none" (default): single-schema, no tenant awareness.
    isolation = "schema": each tenant gets a PostgreSQL schema.
    """

    isolation: str = "none"  # "none" | "schema"
    resolver: str = "subdomain"  # "subdomain" | "header" | "session"
    header_name: str = "X-Tenant-ID"  # only used when resolver = "header"
```

2. Add to `ProjectManifest` after `dev: DevConfig`:

```python
    tenant: TenantConfig = field(default_factory=TenantConfig)
```

3. In `load_manifest()`, after the `dev_data` parsing block, add:

```python
    # Parse tenant config
    tenant_data = data.get("tenant", {})
    tenant_config = TenantConfig(
        isolation=tenant_data.get("isolation", "none"),
        resolver=tenant_data.get("resolver", "subdomain"),
        header_name=tenant_data.get("header_name", "X-Tenant-ID"),
    )
```

4. Pass `tenant=tenant_config` to the `ProjectManifest(...)` constructor.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_tenant_config.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/core/manifest.py tests/unit/test_tenant_config.py
git commit -m "feat(tenant): add TenantConfig to manifest (#531)"
```

---

## Task 2: Slug Validation + Config Module

**Files:**
- Create: `src/dazzle/tenant/__init__.py`
- Create: `src/dazzle/tenant/config.py`
- Modify: `tests/unit/test_tenant_config.py` (add slug tests)

- [ ] **Step 1: Write failing tests**

Append to `tests/unit/test_tenant_config.py`:

```python
from dazzle.tenant.config import validate_slug, slug_to_schema_name, SLUG_PATTERN


class TestSlugValidation:
    def test_valid_slug(self) -> None:
        validate_slug("cyfuture_uk")  # should not raise

    def test_valid_single_char_start(self) -> None:
        validate_slug("ab")  # minimum length

    def test_rejects_uppercase(self) -> None:
        with pytest.raises(ValueError, match="Slug must match"):
            validate_slug("CyFuture")

    def test_rejects_starts_with_number(self) -> None:
        with pytest.raises(ValueError, match="Slug must match"):
            validate_slug("1invalid")

    def test_rejects_too_long(self) -> None:
        with pytest.raises(ValueError, match="Slug must match"):
            validate_slug("a" * 57)  # max is 56

    def test_rejects_empty(self) -> None:
        with pytest.raises(ValueError, match="Slug must match"):
            validate_slug("")

    def test_rejects_special_chars(self) -> None:
        with pytest.raises(ValueError, match="Slug must match"):
            validate_slug("my-tenant")  # hyphens not allowed

    def test_max_valid_length(self) -> None:
        validate_slug("a" * 56)  # exactly at limit


class TestSlugToSchemaName:
    def test_prefixes_with_tenant(self) -> None:
        assert slug_to_schema_name("cyfuture") == "tenant_cyfuture"

    def test_total_length_within_pg_limit(self) -> None:
        schema = slug_to_schema_name("a" * 56)
        assert len(schema) <= 63
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_tenant_config.py::TestSlugValidation -v`
Expected: FAIL — module not found

- [ ] **Step 3: Implement**

```python
# src/dazzle/tenant/__init__.py
"""Schema-per-tenant isolation for Dazzle apps."""
```

```python
# src/dazzle/tenant/config.py
"""Tenant configuration helpers — slug validation and schema naming."""

from __future__ import annotations

import re

# Max slug length: 63 (PG identifier limit) - 7 ("tenant_" prefix) = 56
SLUG_PATTERN = re.compile(r"^[a-z][a-z0-9_]{1,55}$")
SCHEMA_PREFIX = "tenant_"


def validate_slug(slug: str) -> None:
    """Validate a tenant slug.

    Raises ValueError if the slug is invalid.
    """
    if not SLUG_PATTERN.match(slug):
        raise ValueError(
            f"Slug must match {SLUG_PATTERN.pattern}. Got: '{slug}'"
        )


def slug_to_schema_name(slug: str) -> str:
    """Convert a tenant slug to a PostgreSQL schema name."""
    return f"{SCHEMA_PREFIX}{slug}"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_tenant_config.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/tenant/__init__.py src/dazzle/tenant/config.py tests/unit/test_tenant_config.py
git commit -m "feat(tenant): add slug validation and schema naming (#531)"
```

---

## Task 3: TenantRegistry

**Files:**
- Create: `src/dazzle/tenant/registry.py`
- Create: `tests/unit/test_tenant_registry.py`

CRUD operations on the `public.tenants` table using psycopg v3.

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/test_tenant_registry.py
"""Tests for TenantRegistry — CRUD on public.tenants."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from dazzle.tenant.registry import TenantRecord, TenantRegistry


class TestTenantRecord:
    def test_fields(self) -> None:
        record = TenantRecord(
            id="uuid-1",
            slug="cyfuture",
            display_name="CyFuture UK",
            schema_name="tenant_cyfuture",
            status="active",
            created_at="2026-01-01T00:00:00Z",
            updated_at="2026-01-01T00:00:00Z",
        )
        assert record.slug == "cyfuture"
        assert record.schema_name == "tenant_cyfuture"


class TestTenantRegistryCreate:
    @patch("dazzle.tenant.registry.psycopg")
    def test_create_tenant(self, mock_psycopg: MagicMock) -> None:
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.__enter__.return_value = mock_conn
        mock_conn.__exit__.return_value = False
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_conn.cursor.return_value.__exit__.return_value = False
        mock_cursor.fetchone.return_value = {
            "id": "uuid-1",
            "slug": "cyfuture",
            "display_name": "CyFuture UK",
            "schema_name": "tenant_cyfuture",
            "status": "active",
            "created_at": "2026-01-01",
            "updated_at": "2026-01-01",
        }
        mock_psycopg.connect.return_value = mock_conn

        registry = TenantRegistry("postgresql://localhost/test")
        record = registry.create("cyfuture", "CyFuture UK")

        assert record.slug == "cyfuture"
        assert record.schema_name == "tenant_cyfuture"
        assert mock_cursor.execute.called

    @patch("dazzle.tenant.registry.psycopg")
    def test_create_validates_slug(self, mock_psycopg: MagicMock) -> None:
        registry = TenantRegistry("postgresql://localhost/test")
        with pytest.raises(ValueError, match="Slug must match"):
            registry.create("INVALID", "Bad Tenant")


class TestTenantRegistryList:
    @patch("dazzle.tenant.registry.psycopg")
    def test_list_tenants(self, mock_psycopg: MagicMock) -> None:
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.__enter__.return_value = mock_conn
        mock_conn.__exit__.return_value = False
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_conn.cursor.return_value.__exit__.return_value = False
        mock_cursor.fetchall.return_value = [
            {
                "id": "uuid-1", "slug": "cyfuture", "display_name": "CyFuture UK",
                "schema_name": "tenant_cyfuture", "status": "active",
                "created_at": "2026-01-01", "updated_at": "2026-01-01",
            },
        ]
        mock_psycopg.connect.return_value = mock_conn

        registry = TenantRegistry("postgresql://localhost/test")
        tenants = registry.list()

        assert len(tenants) == 1
        assert tenants[0].slug == "cyfuture"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_tenant_registry.py -v`
Expected: FAIL — module not found

- [ ] **Step 3: Implement**

```python
# src/dazzle/tenant/registry.py
"""Tenant registry — CRUD on public.tenants table."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

try:
    import psycopg
    from psycopg.rows import dict_row
except ImportError:
    psycopg = None  # type: ignore[assignment]
    dict_row = None  # type: ignore[assignment]

from .config import slug_to_schema_name, validate_slug

logger = logging.getLogger(__name__)

_CREATE_TABLE_SQL = """\
CREATE TABLE IF NOT EXISTS public.tenants (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    slug TEXT UNIQUE NOT NULL,
    display_name TEXT NOT NULL,
    schema_name TEXT UNIQUE NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
)"""

_INSERT_SQL = """\
INSERT INTO public.tenants (slug, display_name, schema_name)
VALUES (%s, %s, %s)
RETURNING id, slug, display_name, schema_name, status, created_at, updated_at"""

_SELECT_BY_SLUG = """\
SELECT id, slug, display_name, schema_name, status, created_at, updated_at
FROM public.tenants WHERE slug = %s"""

_SELECT_ALL = """\
SELECT id, slug, display_name, schema_name, status, created_at, updated_at
FROM public.tenants ORDER BY created_at"""

_UPDATE_STATUS = """\
UPDATE public.tenants SET status = %s, updated_at = now()
WHERE slug = %s
RETURNING id, slug, display_name, schema_name, status, created_at, updated_at"""


@dataclass
class TenantRecord:
    """A row from the public.tenants table."""

    id: str
    slug: str
    display_name: str
    schema_name: str
    status: str
    created_at: str
    updated_at: str


def _row_to_record(row: dict[str, Any]) -> TenantRecord:
    return TenantRecord(
        id=str(row["id"]),
        slug=row["slug"],
        display_name=row["display_name"],
        schema_name=row["schema_name"],
        status=row["status"],
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
    )


class TenantRegistry:
    """CRUD operations on the public.tenants table."""

    def __init__(self, db_url: str) -> None:
        self._db_url = db_url

    def _connect(self) -> Any:
        return psycopg.connect(self._db_url, row_factory=dict_row)

    def ensure_table(self) -> None:
        """Create the tenants table if it doesn't exist."""
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(_CREATE_TABLE_SQL)
            conn.commit()

    def create(self, slug: str, display_name: str) -> TenantRecord:
        """Insert a tenant record. Raises ValueError for invalid slugs."""
        validate_slug(slug)
        schema_name = slug_to_schema_name(slug)
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(_INSERT_SQL, (slug, display_name, schema_name))
                row = cur.fetchone()
            conn.commit()
        return _row_to_record(row)

    def get(self, slug: str) -> TenantRecord | None:
        """Look up a tenant by slug."""
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(_SELECT_BY_SLUG, (slug,))
                row = cur.fetchone()
        return _row_to_record(row) if row else None

    def list(self) -> list[TenantRecord]:
        """List all tenants."""
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(_SELECT_ALL)
                rows = cur.fetchall()
        return [_row_to_record(r) for r in rows]

    def update_status(self, slug: str, status: str) -> TenantRecord:
        """Set status to 'active', 'suspended', or 'archived'."""
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(_UPDATE_STATUS, (status, slug))
                row = cur.fetchone()
            conn.commit()
        if row is None:
            raise ValueError(f"Tenant '{slug}' not found")
        return _row_to_record(row)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_tenant_registry.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/tenant/registry.py tests/unit/test_tenant_registry.py
git commit -m "feat(tenant): add TenantRegistry with CRUD operations (#531)"
```

---

## Task 4: TenantProvisioner

**Files:**
- Create: `src/dazzle/tenant/provisioner.py`
- Create: `tests/unit/test_tenant_provisioner.py`

Creates a PostgreSQL schema and entity+auth tables within it using fully-qualified names.

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/test_tenant_provisioner.py
"""Tests for TenantProvisioner — schema creation and table provisioning."""

from __future__ import annotations

from unittest.mock import MagicMock, call, patch

import pytest

from dazzle.tenant.provisioner import TenantProvisioner


class TestSchemaCreation:
    @patch("dazzle.tenant.provisioner.psycopg")
    def test_creates_schema(self, mock_psycopg: MagicMock) -> None:
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.__enter__.return_value = mock_conn
        mock_conn.__exit__.return_value = False
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_conn.cursor.return_value.__exit__.return_value = False
        mock_psycopg.connect.return_value = mock_conn

        # Mock appspec with one entity
        appspec = MagicMock()
        entity = MagicMock()
        entity.name = "Task"
        entity.fields = []
        appspec.domain.entities = [entity]

        provisioner = TenantProvisioner("postgresql://localhost/test", appspec)
        provisioner.provision("tenant_cyfuture")

        # Check CREATE SCHEMA was called
        executed_sqls = [str(c) for c in mock_cursor.execute.call_args_list]
        assert any("CREATE SCHEMA" in s and "tenant_cyfuture" in s for s in executed_sqls)

    @patch("dazzle.tenant.provisioner.psycopg")
    def test_schema_exists_check(self, mock_psycopg: MagicMock) -> None:
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.__enter__.return_value = mock_conn
        mock_conn.__exit__.return_value = False
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_conn.cursor.return_value.__exit__.return_value = False
        mock_cursor.fetchone.return_value = {"exists": True}
        mock_psycopg.connect.return_value = mock_conn

        provisioner = TenantProvisioner("postgresql://localhost/test", MagicMock())
        assert provisioner.schema_exists("tenant_cyfuture") is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_tenant_provisioner.py -v`
Expected: FAIL — module not found

- [ ] **Step 3: Implement**

```python
# src/dazzle/tenant/provisioner.py
"""Tenant schema provisioner — creates PostgreSQL schemas with entity tables."""

from __future__ import annotations

import logging
from typing import Any

try:
    import psycopg
    from psycopg.rows import dict_row
except ImportError:
    psycopg = None  # type: ignore[assignment]
    dict_row = None  # type: ignore[assignment]

from dazzle.db.sql import quote_id

logger = logging.getLogger(__name__)


class TenantProvisioner:
    """Creates and populates PostgreSQL schemas for tenants."""

    def __init__(self, db_url: str, appspec: Any) -> None:
        self._db_url = db_url
        self._appspec = appspec

    def _connect(self) -> Any:
        return psycopg.connect(self._db_url, row_factory=dict_row)

    def provision(self, schema_name: str) -> None:
        """Create schema and all entity tables within it.

        Uses fully-qualified table names (schema.table) — no SET search_path.
        """
        quoted_schema = quote_id(schema_name)

        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(f"CREATE SCHEMA IF NOT EXISTS {quoted_schema}")

                # Create entity tables in the tenant schema
                for entity in self._appspec.domain.entities:
                    table = f"{quoted_schema}.{quote_id(entity.name)}"
                    # Minimal table creation — just the entity name for now.
                    # Full column DDL reuse from pg_backend is deferred to
                    # sub-project 2 when connection routing makes it testable.
                    cur.execute(
                        f"CREATE TABLE IF NOT EXISTS {table} "
                        f"(id UUID PRIMARY KEY DEFAULT gen_random_uuid())"
                    )

            conn.commit()
        logger.info("Provisioned schema %s with %d tables", schema_name, len(self._appspec.domain.entities))

    def schema_exists(self, schema_name: str) -> bool:
        """Check if a schema exists in the database."""
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT EXISTS(SELECT 1 FROM information_schema.schemata WHERE schema_name = %s) AS exists",
                    (schema_name,),
                )
                row = cur.fetchone()
        return bool(row and row.get("exists"))
```

**Note:** The provisioner creates minimal tables (just PK) for now. Full column DDL reuse from `pg_backend.create_table()` and auth table creation (users, sessions, roles) are deferred to sub-project 2 when the connection routing middleware makes them testable end-to-end. The spec lists auth tables as a provisioning step, but importing `pg_backend` or `AuthStore` DDL from the `dazzle` package would create cross-package dependencies. The schema structure and entity stubs are what this sub-project validates.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_tenant_provisioner.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/tenant/provisioner.py tests/unit/test_tenant_provisioner.py
git commit -m "feat(tenant): add TenantProvisioner for schema creation (#531)"
```

---

## Task 5: CLI Commands

**Files:**
- Create: `src/dazzle/cli/tenant.py`
- Modify: `src/dazzle/cli/__init__.py`
- Create: `tests/unit/test_cli_tenant.py`

Add `dazzle tenant create/list/status/suspend/activate` commands.

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/test_cli_tenant.py
"""Tests for dazzle tenant CLI commands."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from dazzle.cli.tenant import tenant_app

runner = CliRunner()


class TestTenantCreate:
    @patch("dazzle.cli.tenant._get_provisioner")
    @patch("dazzle.cli.tenant._get_registry")
    @patch("dazzle.cli.tenant._check_tenant_enabled")
    def test_create_success(
        self, mock_check: MagicMock, mock_reg: MagicMock, mock_prov: MagicMock
    ) -> None:
        registry = MagicMock()
        registry.create.return_value = MagicMock(
            slug="cyfuture", display_name="CyFuture UK",
            schema_name="tenant_cyfuture", status="active",
        )
        mock_reg.return_value = registry
        provisioner = MagicMock()
        mock_prov.return_value = provisioner

        result = runner.invoke(tenant_app, ["create", "cyfuture", "--display-name", "CyFuture UK"])
        assert result.exit_code == 0
        assert "cyfuture" in result.output
        registry.ensure_table.assert_called_once()
        registry.create.assert_called_once_with("cyfuture", "CyFuture UK")
        provisioner.provision.assert_called_once_with("tenant_cyfuture")


class TestTenantList:
    @patch("dazzle.cli.tenant._get_registry")
    @patch("dazzle.cli.tenant._check_tenant_enabled")
    def test_list_tenants(self, mock_check: MagicMock, mock_reg: MagicMock) -> None:
        registry = MagicMock()
        registry.list.return_value = [
            MagicMock(slug="cyfuture", display_name="CyFuture UK",
                      schema_name="tenant_cyfuture", status="active"),
        ]
        mock_reg.return_value = registry

        result = runner.invoke(tenant_app, ["list"])
        assert result.exit_code == 0
        assert "cyfuture" in result.output


class TestTenantSuspend:
    @patch("dazzle.cli.tenant._get_registry")
    @patch("dazzle.cli.tenant._check_tenant_enabled")
    def test_suspend_tenant(self, mock_check: MagicMock, mock_reg: MagicMock) -> None:
        registry = MagicMock()
        registry.update_status.return_value = MagicMock(slug="cyfuture", status="suspended")
        mock_reg.return_value = registry

        result = runner.invoke(tenant_app, ["suspend", "cyfuture"])
        assert result.exit_code == 0
        registry.update_status.assert_called_once_with("cyfuture", "suspended")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_cli_tenant.py -v`
Expected: FAIL — module not found

- [ ] **Step 3: Implement CLI**

```python
# src/dazzle/cli/tenant.py
"""Tenant management CLI commands."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import typer
from rich.console import Console
from rich.table import Table

tenant_app = typer.Typer(
    help="Multi-tenant schema management",
    no_args_is_help=True,
)

console = Console()


def _check_tenant_enabled() -> None:
    """Raise if tenant isolation is not enabled."""
    from dazzle.core.manifest import load_manifest

    toml_path = Path("dazzle.toml").resolve()
    if not toml_path.exists():
        console.print("[red]No dazzle.toml found.[/red]")
        raise typer.Exit(1)

    manifest = load_manifest(toml_path)
    if manifest.tenant.isolation != "schema":
        console.print(
            '[red]Multi-tenancy not enabled. '
            'Add [tenant] isolation = "schema" to dazzle.toml[/red]'
        )
        raise typer.Exit(1)


def _get_registry() -> Any:
    """Create a TenantRegistry from manifest config."""
    from dazzle.core.manifest import load_manifest, resolve_database_url
    from dazzle.tenant.registry import TenantRegistry

    manifest = load_manifest(Path("dazzle.toml").resolve())
    db_url = resolve_database_url(manifest)
    return TenantRegistry(db_url)


def _get_provisioner() -> Any:
    """Create a TenantProvisioner from manifest config."""
    from dazzle.cli.utils import load_project_appspec
    from dazzle.core.manifest import load_manifest, resolve_database_url
    from dazzle.tenant.provisioner import TenantProvisioner

    project_root = Path.cwd().resolve()
    manifest = load_manifest(project_root / "dazzle.toml")
    db_url = resolve_database_url(manifest)
    appspec = load_project_appspec(project_root)
    return TenantProvisioner(db_url, appspec)


@tenant_app.command(name="create")
def create_command(
    slug: str = typer.Argument(help="Tenant slug (lowercase, alphanumeric + underscores)"),
    display_name: str = typer.Option(..., "--display-name", "-d", help="Human-readable tenant name"),
) -> None:
    """Create a new tenant with its own database schema."""
    _check_tenant_enabled()
    registry = _get_registry()
    provisioner = _get_provisioner()

    registry.ensure_table()

    try:
        record = registry.create(slug, display_name)
    except Exception as e:
        console.print(f"[red]Failed to create tenant: {e}[/red]")
        raise typer.Exit(1)

    try:
        provisioner.provision(record.schema_name)
    except Exception as e:
        console.print(f"[red]Schema provisioning failed: {e}[/red]")
        raise typer.Exit(1)

    console.print(f"[green]Tenant created:[/green] {record.slug}")
    console.print(f"  Schema: {record.schema_name}")
    console.print(f"  Display: {record.display_name}")


@tenant_app.command(name="list")
def list_command() -> None:
    """List all tenants."""
    _check_tenant_enabled()
    registry = _get_registry()
    registry.ensure_table()

    tenants = registry.list()
    if not tenants:
        console.print("No tenants found.")
        return

    table = Table(title="Tenants")
    table.add_column("Slug")
    table.add_column("Display Name")
    table.add_column("Schema")
    table.add_column("Status")

    for t in tenants:
        table.add_row(t.slug, t.display_name, t.schema_name, t.status)

    console.print(table)


@tenant_app.command(name="status")
def status_command(
    slug: str = typer.Argument(help="Tenant slug"),
) -> None:
    """Show details for a tenant."""
    _check_tenant_enabled()
    registry = _get_registry()

    record = registry.get(slug)
    if not record:
        console.print(f"[red]Tenant '{slug}' not found.[/red]")
        raise typer.Exit(1)

    console.print(f"Slug:         {record.slug}")
    console.print(f"Display Name: {record.display_name}")
    console.print(f"Schema:       {record.schema_name}")
    console.print(f"Status:       {record.status}")
    console.print(f"Created:      {record.created_at}")
    console.print(f"Updated:      {record.updated_at}")


@tenant_app.command(name="suspend")
def suspend_command(
    slug: str = typer.Argument(help="Tenant slug to suspend"),
) -> None:
    """Suspend a tenant (returns 503 at middleware)."""
    _check_tenant_enabled()
    registry = _get_registry()

    try:
        record = registry.update_status(slug, "suspended")
        console.print(f"[yellow]Tenant '{record.slug}' suspended.[/yellow]")
    except ValueError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1)


@tenant_app.command(name="activate")
def activate_command(
    slug: str = typer.Argument(help="Tenant slug to activate"),
) -> None:
    """Activate a suspended tenant."""
    _check_tenant_enabled()
    registry = _get_registry()

    try:
        record = registry.update_status(slug, "active")
        console.print(f"[green]Tenant '{record.slug}' activated.[/green]")
    except ValueError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1)
```

- [ ] **Step 4: Register in CLI**

In `src/dazzle/cli/__init__.py`, add import and registration following the existing pattern:

```python
from dazzle.cli.tenant import tenant_app  # add with other imports
app.add_typer(tenant_app, name="tenant")  # add with other registrations
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/unit/test_cli_tenant.py -v`
Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add src/dazzle/cli/tenant.py src/dazzle/cli/__init__.py tests/unit/test_cli_tenant.py
git commit -m "feat(tenant): add dazzle tenant CLI commands (#531)"
```

---

## Task 6: Package Exports + Documentation

**Files:**
- Modify: `src/dazzle/tenant/__init__.py`
- Modify: `.claude/CLAUDE.md`

- [ ] **Step 1: Update `__init__.py`**

```python
# src/dazzle/tenant/__init__.py
"""Schema-per-tenant isolation for Dazzle apps.

Opt-in via dazzle.toml:
    [tenant]
    isolation = "schema"
    resolver = "subdomain"
"""

from .config import SLUG_PATTERN, slug_to_schema_name, validate_slug
from .provisioner import TenantProvisioner
from .registry import TenantRecord, TenantRegistry

__all__ = [
    "SLUG_PATTERN",
    "TenantProvisioner",
    "TenantRecord",
    "TenantRegistry",
    "slug_to_schema_name",
    "validate_slug",
]
```

- [ ] **Step 2: Update CLAUDE.md**

Add `dazzle tenant create|list|status|suspend|activate` to the CLI commands section.

- [ ] **Step 3: Run full test suite**

Run: `pytest tests/unit/test_tenant_*.py tests/unit/test_cli_tenant.py -v`
Expected: All PASS

- [ ] **Step 4: Lint and type check**

Run: `ruff check src/dazzle/tenant/ src/dazzle/cli/tenant.py --fix && ruff format src/dazzle/tenant/ src/dazzle/cli/tenant.py`
Run: `mypy src/dazzle/tenant/`

- [ ] **Step 5: Commit**

```bash
git add src/dazzle/tenant/__init__.py .claude/CLAUDE.md
git commit -m "feat(tenant): finalize package exports and docs (#531)"
```
