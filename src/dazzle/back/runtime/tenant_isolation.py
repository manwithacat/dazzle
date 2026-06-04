"""Tenant context — per-request schema routing + RLS tenant id via context vars.

Two independent context vars, both read by ``pg_backend.connection()`` on each
connection lease:

  * ``_current_tenant_schema`` — schema-per-tenant routing (``SET search_path``),
    set by ``TenantMiddleware``.
  * ``_current_tenant_id`` — the ``shared_schema`` RLS tenant discriminator,
    used to set the ``dazzle.tenant_id`` GUC (``set_config(..., true)``) so the
    PostgreSQL row-level-security fence (RLS tenancy Phase B) scopes the leased
    connection to the authenticated user's tenant. Set per request from the auth
    dependency (after ``current_user`` resolves, before the handler queries).
"""

from contextvars import ContextVar, Token

_current_tenant_schema: ContextVar[str | None] = ContextVar("_current_tenant_schema", default=None)
_current_tenant_id: ContextVar[str | None] = ContextVar("_current_tenant_id", default=None)


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


def get_current_tenant_id() -> str | None:
    """Get the current RLS tenant id (the partition-key value) for this context.

    Returns None when no tenant id is bound — unauthenticated requests, system
    paths, or apps without ``shared_schema`` tenancy. ``connection()`` then sets
    no ``dazzle.tenant_id`` GUC, so the RLS fence denies (fail-closed).
    """
    return _current_tenant_id.get()


def set_current_tenant_id(tenant_id: str) -> Token[str | None]:
    """Bind the RLS tenant id for this async context.

    Returns a token for resetting. ``connection()`` reads this at lease time to
    set the per-transaction ``dazzle.tenant_id`` GUC.
    """
    return _current_tenant_id.set(tenant_id)
