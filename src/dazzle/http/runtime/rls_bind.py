"""RLS GUC binding — the single resolver for ``dazzle.tenant_id`` / ``dazzle.user_<attr>``.

A leaf by design (#1772): it imports only ``tenant_isolation`` (the contextvars),
``rls_schema`` (the GUC names) and — under ``TYPE_CHECKING`` — ``auth.models``. So
``scope_filters``, ``auth.dependencies``, the page / workspace seams and app code
can all import it at module top without the ``scope_filters → auth →
dependencies`` cycle that previously forced function-local imports.

Three layers, one truth:

* :func:`resolve_user_attribute` — the ``current_user.<attr>`` resolver the
  app-layer scope filters use (moved here from ``scope_filters``).
* :func:`resolve_rls_gucs` — the per-request GUC set (tenant + scope attrs) for an
  ``AuthContext``, with the fail-closed accept rule. Everything below derives from it.
* :func:`bind_rls_context` sets the per-request contextvars the framework's leased
  connection reads (``pg_backend.connection()``); :func:`bind_rls` sets the same
  GUCs directly on an **app-owned** DB-API connection (custom routes / renderers
  that open their own psycopg / psycopg2 connection).
"""

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Protocol

from dazzle.http.runtime.rls_schema import TENANT_GUC, USER_GUC_PREFIX
from dazzle.http.runtime.tenant_isolation import (
    get_current_rls_user_attrs,
    get_current_tenant_id,
    get_rls_user_attr_names,
    set_current_rls_user_attrs,
    set_current_tenant_id,
)

if TYPE_CHECKING:
    from dazzle.http.runtime.auth.models import AuthContext

__all__ = [
    "RBAC_DENY",
    "RlsBinding",
    "bind_rls",
    "bind_rls_context",
    "resolve_rls_gucs",
    "resolve_user_attribute",
]

RBAC_DENY = "__RBAC_DENY__"
"""Sentinel for an unresolvable ``current_user.<attr>`` — callers deny on it."""

# The set_config SQL below spells the tenant GUC literally; keep it pinned to the
# name the fence DDL reads (same drift guard pg_backend carries).
assert TENANT_GUC == "dazzle.tenant_id", (
    f"TENANT_GUC ({TENANT_GUC!r}) drifted from the set_config literal in bind_rls."
)

_SCALAR = str | int | float | bool


class DbApiConnection(Protocol):
    """The DB-API surface :func:`bind_rls` needs: ``cursor()`` (psycopg2 or psycopg3)."""

    def cursor(self) -> Any: ...


@dataclass(frozen=True)
class RlsBinding:
    """The RLS GUC values resolved for one principal.

    ``tenant_id`` is the ``dazzle.tenant_id`` value (``None`` → left unbound, the
    fence denies). ``user_attrs`` maps the bare attr name to its value; each entry
    becomes ``dazzle.user_<attr>``. Absent entries stay unbound (fail-closed).
    """

    tenant_id: str | None = None
    user_attrs: dict[str, str] = field(default_factory=dict)


def resolve_user_attribute(attr_name: str, auth_context: "AuthContext | None") -> Any:
    """Resolve a ``current_user.<attr_name>`` reference to a concrete value.

    ``tenant_id`` resolves ONLY from the active membership (auth Plan 1d): the
    membership's ``partition_root_id`` when a non-empty string (#1463 — a leaf
    membership in a hierarchy binds the root the rows are partitioned at), else
    ``str(membership.tenant_id)``; no membership → :data:`RBAC_DENY` (no
    preferences fallback).

    Any other attr: ``UserRecord.<attr>`` scalar → ``UserRecord.<attr>_id`` scalar
    → ``preferences[attr]`` → ``preferences[attr_id]`` (a ``None`` preference is
    missing, #591) → :data:`RBAC_DENY` so the caller injects an impossible filter
    (deny-by-default).
    """
    if auth_context is None:
        return RBAC_DENY

    if attr_name == "tenant_id":
        membership = getattr(auth_context, "active_membership", None)
        if membership is not None and getattr(membership, "tenant_id", None):
            partition_root = getattr(membership, "partition_root_id", None)
            if isinstance(partition_root, str) and partition_root:
                return partition_root
            return str(membership.tenant_id)
        return RBAC_DENY

    user = getattr(auth_context, "user", None)

    # 1. Built-in UserRecord fields. Only scalar primitives — rejects
    # MagicMock/object auto-attribute hits and non-serialisable values.
    if user is not None:
        user_val = getattr(user, attr_name, None)
        if isinstance(user_val, _SCALAR):
            return str(user_val)
        user_val_id = getattr(user, f"{attr_name}_id", None)
        if isinstance(user_val_id, _SCALAR):
            return str(user_val_id)

    # 2. Preferences dict. None values are missing — they must not bypass the
    # deny sentinel (#591).
    prefs: dict[str, str] = getattr(auth_context, "preferences", {}) or {}
    if attr_name in prefs and prefs[attr_name] is not None:
        return prefs[attr_name]
    attr_id_key = f"{attr_name}_id"
    if attr_id_key in prefs and prefs[attr_id_key] is not None:
        return prefs[attr_id_key]

    return RBAC_DENY


def _accept(value: Any) -> str | None:
    """A GUC value is bindable only as a non-empty, non-deny string (companion §6.3)."""
    if isinstance(value, str) and value and value != RBAC_DENY:
        return value
    return None


def resolve_rls_gucs(auth_context: "AuthContext | None") -> RlsBinding:
    """Resolve the RLS GUCs for ``auth_context`` — the single truth for every binder.

    Unauthenticated (or ``None``) → nothing. Otherwise ``tenant_id`` via
    :func:`resolve_user_attribute` and one entry per app-wide scope-referenced attr
    (``get_rls_user_attr_names()``, registered at startup). Deny-sentinel, empty and
    non-string values are omitted → their GUC stays unset → the fence / predicate
    denies (an empty-string GUC would also be a hard ``::uuid`` cast error). Attrs
    bind even when the tenant is unresolvable — the fence denies regardless.
    """
    if auth_context is None or not getattr(auth_context, "is_authenticated", False):
        return RlsBinding()
    tenant_id = _accept(resolve_user_attribute("tenant_id", auth_context))
    user_attrs: dict[str, str] = {}
    for attr in get_rls_user_attr_names():
        value = _accept(resolve_user_attribute(attr, auth_context))
        if value is not None:
            user_attrs[attr] = value
    return RlsBinding(tenant_id=tenant_id, user_attrs=user_attrs)


def bind_rls_context(auth_context: "AuthContext | None") -> str | None:
    """Bind the per-request RLS contextvars from ``auth_context``.

    ``pg_backend.connection()`` reads these at lease time and sets
    ``dazzle.tenant_id`` + each ``dazzle.user_<attr>`` per transaction, so any
    framework repository / service call made after this binds the fence. The auth
    dependencies call it; so must any seam that self-authenticates (page
    in-process path, workspace regions, a route override calling a framework
    service). Resolved entries only — an unresolved tenant / empty attr map leaves
    the contextvar untouched. asyncio gives each request task its own contextvar
    copy, so the binding dies with the task. Returns the bound tenant id or ``None``.
    """
    binding = resolve_rls_gucs(auth_context)
    if binding.tenant_id is not None:
        set_current_tenant_id(binding.tenant_id)
    if binding.user_attrs:
        set_current_rls_user_attrs(dict(binding.user_attrs))
    return binding.tenant_id


def bind_rls(
    conn: DbApiConnection,
    auth: "AuthContext | None" = None,
    *,
    session: bool = False,
) -> str | None:
    """Set ``dazzle.tenant_id`` + ``dazzle.user_<attr>`` on an app-owned DB connection.

    For custom routes / renderers that open their own psycopg (or psycopg2)
    connection instead of using the framework's per-request lease: without the GUCs
    the ``shared_schema`` tenant fence denies every fenced row. Same resolution and
    fail-closed rules as the framework (:func:`resolve_rls_gucs`).

    * ``auth`` given → resolve from it.
    * ``auth`` omitted → copy the current request's bound contextvars verbatim
      (what the auth dependency / :func:`bind_rls_context` already set — the right
      call inside a renderer that has no ``request``).

    ``session=False`` (default) uses ``set_config(..., true)`` — transaction-local,
    exactly what the framework does on its own lease. **On an autocommit connection
    that binds nothing past the single ``SELECT``** (fail-closed but silent: every
    fenced query then returns 0 rows); open a transaction first, or pass
    ``session=True`` for ``set_config(..., false)`` on a short-lived per-request
    connection that spans several transactions. Never use ``session=True`` on a
    pooled connection that is returned to a pool shared across principals.

    Values (and user-attr GUC names) are only ever bind parameters. Returns the
    bound tenant id, or ``None`` when no tenant was bound.
    """
    if auth is not None:
        binding = resolve_rls_gucs(auth)
        tenant_id = binding.tenant_id
        user_attrs = binding.user_attrs
    else:
        tenant_id = _accept(get_current_tenant_id())
        # Verbatim copy: the map may carry keys beyond the registered attr names
        # (e.g. ``id`` / ``entity_id`` spliced in by the workspace prelude, #1626).
        user_attrs = {
            attr: value
            for attr, value in get_current_rls_user_attrs().items()
            if _accept(value) is not None
        }
    is_local = not session
    with conn.cursor() as cur:
        if tenant_id is not None:
            cur.execute(
                "SELECT set_config('dazzle.tenant_id', %s, %s)",  # nosemgrep
                (tenant_id, is_local),
            )
        for attr, value in user_attrs.items():
            cur.execute(
                "SELECT set_config(%s, %s, %s)",  # nosemgrep
                (f"{USER_GUC_PREFIX}{attr}", value, is_local),
            )
    return tenant_id
