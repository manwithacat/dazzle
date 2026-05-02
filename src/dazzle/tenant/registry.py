"""Tenant registry — CRUD on public.tenants table."""

from __future__ import annotations  # required: forward reference

import json
import logging
from dataclasses import dataclass, field
from typing import Any

try:
    import psycopg
    from psycopg.rows import dict_row
    from psycopg.types.json import Jsonb
except ImportError:
    psycopg = None  # type: ignore[assignment]
    dict_row = None  # type: ignore[assignment]
    Jsonb = None  # type: ignore[assignment,misc]

from .config import slug_to_schema_name, validate_slug

logger = logging.getLogger(__name__)

_CREATE_TABLE_SQL = """\
CREATE TABLE IF NOT EXISTS public.tenants (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    slug TEXT UNIQUE NOT NULL,
    display_name TEXT NOT NULL,
    schema_name TEXT UNIQUE NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    config JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
)"""

# #957 cycle 7 — idempotent column add for upgraded deployments. Tables
# created before cycle 7 don't have `config`; this back-fills it without
# breaking the existing-table path or affecting fresh installs.
_ALTER_ADD_CONFIG_SQL = (
    "ALTER TABLE public.tenants ADD COLUMN IF NOT EXISTS config JSONB NOT NULL DEFAULT '{}'::jsonb"
)

_INSERT_SQL = """\
INSERT INTO public.tenants (slug, display_name, schema_name)
VALUES (%s, %s, %s)
RETURNING id, slug, display_name, schema_name, status, config, created_at, updated_at"""

_SELECT_BY_SLUG = """\
SELECT id, slug, display_name, schema_name, status, config, created_at, updated_at
FROM public.tenants WHERE slug = %s"""

_SELECT_ALL = """\
SELECT id, slug, display_name, schema_name, status, config, created_at, updated_at
FROM public.tenants ORDER BY created_at"""

_UPDATE_STATUS = """\
UPDATE public.tenants SET status = %s, updated_at = now()
WHERE slug = %s
RETURNING id, slug, display_name, schema_name, status, config, created_at, updated_at"""

_UPDATE_CONFIG = """\
UPDATE public.tenants SET config = %s, updated_at = now()
WHERE slug = %s
RETURNING id, slug, display_name, schema_name, status, config, created_at, updated_at"""


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
    # #957 cycle 7 — per-tenant configuration (locale, theme, feature
    # flags). Schema declared in `tenancy: per_tenant_config:` on the
    # AppSpec; raw values stored as JSONB and coerced via
    # `dazzle.tenant.config_coercion` at read time.
    config: dict[str, Any] = field(default_factory=dict)


def _row_to_record(row: dict[str, Any]) -> TenantRecord:
    raw_config = row.get("config") or {}
    # JSONB returns dict natively; if a legacy text column is present
    # (shouldn't happen, but defensive) parse it.
    if isinstance(raw_config, str):
        try:
            raw_config = json.loads(raw_config)
        except (json.JSONDecodeError, TypeError):
            raw_config = {}
    return TenantRecord(
        id=str(row["id"]),
        slug=row["slug"],
        display_name=row["display_name"],
        schema_name=row["schema_name"],
        status=row["status"],
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
        config=dict(raw_config) if isinstance(raw_config, dict) else {},
    )


class TenantRegistry:
    """CRUD operations on the public.tenants table."""

    def __init__(self, db_url: str) -> None:
        self._db_url = db_url

    def _connect(self) -> Any:
        return psycopg.connect(self._db_url, row_factory=dict_row)

    def ensure_table(self) -> None:
        """Create the tenants table if it doesn't exist.

        Also runs the cycle-7 idempotent ALTER to back-fill the
        `config` column on tables created before this version. Both
        statements are idempotent — safe to call repeatedly at boot.
        """
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(_CREATE_TABLE_SQL)
                cur.execute(_ALTER_ADD_CONFIG_SQL)
            conn.commit()

    def update_config(self, slug: str, config: dict[str, Any]) -> TenantRecord:
        """Replace the per-tenant configuration JSON for ``slug``.

        Caller is responsible for type-coercing values to the schema
        declared in `tenancy: per_tenant_config:` (use
        :func:`dazzle.tenant.config_coercion.coerce_config`). The
        registry stores the dict verbatim as JSONB.
        """
        if Jsonb is None:
            raise RuntimeError("psycopg is required to update tenant config")
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(_UPDATE_CONFIG, (Jsonb(config), slug))
                row = cur.fetchone()
            conn.commit()
        if row is None:
            raise ValueError(f"Tenant '{slug}' not found")
        return _row_to_record(row)

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
