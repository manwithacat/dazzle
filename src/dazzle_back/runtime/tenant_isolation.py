"""Tenant schema context — per-request schema routing via context vars.

The middleware sets the current tenant schema, and pg_backend.connection()
reads it to SET search_path on each connection lease.
"""

from __future__ import annotations

from contextvars import ContextVar, Token

_current_tenant_schema: ContextVar[str | None] = ContextVar("_current_tenant_schema", default=None)


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
