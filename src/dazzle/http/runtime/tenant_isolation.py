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
  * ``_current_rls_user_attrs`` — the per-request resolved ``current_user.*``
    attribute map for the intra-tenant scope policies (RLS tenancy Phase C). Keyed
    by the **bare attr name** (``"id"``, ``"school_id"``, …) → value;
    ``connection()`` sets one ``set_config('dazzle.user_<attr>', value, true)`` GUC
    per entry (the ``dazzle.user_`` prefix comes from the shared
    ``rls_schema.USER_GUC_PREFIX``) so the per-verb scope policies'
    ``current_setting('dazzle.user_<attr>', true)`` resolves. An
    attr that can't be resolved is simply absent from the map → its GUC stays
    unset → that predicate denies (fail-closed). Set per request from the same
    auth dependency that binds ``_current_tenant_id``.

A small process-global registry (``register_rls_user_attr_names`` /
``get_rls_user_attr_names``) records the *app-wide* set of referenced attr names —
the union of ``collect_user_attr_refs`` over every scoped entity's rules, computed
once at startup. The auth dependency reads it to know which attrs to resolve per
request without re-walking the predicate trees; it is read-only after startup
(derived config, not mutable runtime state — distinct from an ADR-0005 singleton).
"""

from contextvars import ContextVar, Token

_current_tenant_schema: ContextVar[str | None] = ContextVar("_current_tenant_schema", default=None)
_current_tenant_id: ContextVar[str | None] = ContextVar("_current_tenant_id", default=None)
# #1394: the host-resolved tenant id (``request.state.tenant.id`` from the #1289
# tenant_host resolver). DELIBERATELY separate from ``_current_tenant_id`` (the RLS
# row-tenancy discriminator) — the two can diverge, and ``current_tenant`` scope
# predicates bind THIS one via the ``dazzle.host_tenant_id`` GUC / CurrentTenantRef.
_current_host_tenant_id: ContextVar[str | None] = ContextVar(
    "_current_host_tenant_id", default=None
)
_current_rls_user_attrs: ContextVar[dict[str, str] | None] = ContextVar(
    "_current_rls_user_attrs", default=None
)

# App-wide set of ``current_user`` attr names referenced by any scope policy,
# registered once at startup (see ``register_rls_user_attr_names``). Empty when
# the app has no shared_schema scope rules → the per-request bind is a no-op.
_rls_user_attr_names: frozenset[str] = frozenset()


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


def get_current_host_tenant_id() -> str | None:
    """Get the host-resolved tenant id for this context (#1394).

    Returns None when no host tenant is bound — non-tenant requests, apex hosts,
    or apps without ``tenant_host``. ``connection()`` then sets no
    ``dazzle.host_tenant_id`` GUC and the marker resolvers deny, so a
    ``current_tenant`` scope predicate fails closed.
    """
    return _current_host_tenant_id.get()


def set_current_host_tenant_id(tenant_id: str) -> Token[str | None]:
    """Bind the host-resolved tenant id for this async context (#1394).

    Returns a token for resetting (tenant middleware sets this from
    ``request.state.tenant.id`` and resets it on request exit).
    """
    return _current_host_tenant_id.set(tenant_id)


def get_current_rls_user_attrs() -> dict[str, str]:
    """Get the per-request resolved ``current_user.*`` GUC map (Phase C).

    Keys are the bare attr name (``"id"``, ``"school_id"``, …; ``connection()``
    prefixes each with ``dazzle.user_`` from the shared constant); values are the
    resolved scalar strings. Returns an
    empty dict when nothing is bound — no scope policies, unauthenticated
    requests, or a non-``shared_schema`` app — and ``connection()`` then sets no
    ``dazzle.user_*`` GUCs (each scope predicate that needs one denies).
    """
    return _current_rls_user_attrs.get() or {}


def set_current_rls_user_attrs(attrs: dict[str, str]) -> Token[dict[str, str] | None]:
    """Bind the per-request ``current_user.*`` GUC map for this async context.

    Returns a token for resetting. ``connection()`` reads this at lease time and
    sets one transaction-scoped ``set_config('dazzle.user_<attr>', value, true)``
    per entry, alongside ``dazzle.tenant_id``.
    """
    return _current_rls_user_attrs.set(attrs)


def register_rls_user_attr_names(names: set[str]) -> None:
    """Record the app-wide set of scope-referenced ``current_user`` attr names.

    Called once at startup with the union of
    :func:`~dazzle.http.runtime.predicate_compiler.collect_user_attr_refs` over
    every scoped entity's rules. The auth dependency reads it (via
    :func:`get_rls_user_attr_names`) to know which attrs to resolve per request
    without re-walking predicate trees. An empty set (non-``shared_schema`` or no
    scope rules) makes the per-request bind a no-op.
    """
    global _rls_user_attr_names
    _rls_user_attr_names = frozenset(names)


def get_rls_user_attr_names() -> frozenset[str]:
    """Return the app-wide set of scope-referenced ``current_user`` attr names."""
    return _rls_user_attr_names
