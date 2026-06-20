"""Shared leaf surface for the CRUD route-generation cluster.

The route-dispatch contracts (`HandlerConfig`, `RouteSpec`) and the request/role/result
helpers that `route_generator` and its satellites (`scope_filters`, `audit_wrap`,
`htmx_render`, `handlers/*`) all reach for. Extracted here as a **leaf** so those
satellites import *down* into this module instead of back *up* into `route_generator` —
which is what broke the import cycle that forced ~18 in-function imports (the only real
SCC in `back/runtime/`; smells round 2026-06-20).

Leaf invariant: this module must NOT import `route_generator` or any of its satellites.
It depends only on fastapi/stdlib/pydantic + `auth`/`htmx_response`/`render` (none cyclic).
`route_generator` re-exports every name here for back-compat importers and patch points.
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any
from uuid import UUID

from fastapi import Request
from pydantic import BaseModel

from dazzle.back.runtime.auth import AuthContext

# _forbidden_detail lives in render/ (#1094) so ui/ page handlers can build the same
# 403 payload without crossing back↔ui. Re-exported here for back-internal call sites.
from dazzle.render.access_messages import _forbidden_detail

if TYPE_CHECKING:
    from dazzle.back.runtime.audit_log import AuditLogger
    from dazzle.back.runtime.service_generator import BaseService
    from dazzle.back.specs.auth import EntityAccessSpec
    from dazzle.core.ir.fk_graph import FKGraph

# Explicit export surface (mypy: makes the re-exported `_forbidden_detail` and the
# leaf symbols a typed public API, so `route_generator` / satellites importing from
# here don't trip implicit-reexport).
__all__ = [
    "HandlerConfig",
    "RouteSpec",
    "_extract_result_id",
    "_forbidden_detail",
    "_htmx_current_url",
    "_htmx_parent_url",
    "_is_htmx_request",
    "_normalize_role",
    "_set_handler_annotations",
    "_wants_html",
]


# ---------------------------------------------------------------------------
# HandlerConfig — stable contract for CRUD factory authorization context (#1011)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class HandlerConfig:
    """Auth + authz + audit context shared across CRUD route handlers.

    Bundles the six concerns every CRUD route handler factory needs in
    a typed, frozen contract. Replaces the per-factory parameter sprawl
    that drifted across read/create/update/delete signatures (~68 edits
    to this tuple in the 3 months before the refactor; #1011).

    The five auth/authz/identity fields are stable across verbs in a
    single dispatch. ``audit_logger`` varies per verb — construct a base
    config once per dispatch, then derive per-verb instances with
    ``dataclasses.replace(base, audit_logger=...)``.

    Composes into :class:`RouteSpec` (the per-route bundle).
    """

    auth_dep: Callable[..., Any] | None = None
    optional_auth_dep: Callable[..., Any] | None = None
    require_auth_by_default: bool = False
    entity_name: str = "Item"
    cedar_access_spec: "EntityAccessSpec | None" = None
    audit_logger: "AuditLogger | None" = None
    # v0.71.19 (#1123): inputs the scope-filter resolver needs at write time so
    # UPDATE/DELETE handlers can enforce `scope: <op>:` rules the same way LIST does.
    fk_graph: "FKGraph | None" = None
    admin_personas: list[str] | None = None


# ---------------------------------------------------------------------------
# RouteSpec — per-route bundle (#1011 closeout)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RouteSpec:
    """Stable per-route contract for CRUD handler factories.

    Wraps :class:`HandlerConfig` (auth/authz/audit) with the resource-,
    schema-, and selection-level fields that recur across two or more
    CRUD verb factories. Each factory accepts a single ``RouteSpec``.

    A field belongs in RouteSpec only when at least two CRUD verbs would
    consume it. Distinct from :class:`dazzle.back.specs.endpoint.EndpointSpec`
    (the static URL/method/service-name spec one layer above): ``RouteSpec``
    is the runtime handler bundle.
    """

    handler: HandlerConfig
    """Auth/authz/audit context (see :class:`HandlerConfig`)."""

    service: "BaseService[Any]"
    """The service that backs this endpoint's data operations."""

    # Schemas (per-verb optional; create/update set input_schema)
    input_schema: type[BaseModel] | None = None
    response_schema: type[BaseModel] | None = None

    # Cross-verb resource fields
    auto_include: list[str] | None = None
    storage_bindings: dict[str, tuple[str, ...]] | None = None
    include_field_changes: bool = False

    # #1218 Option A: when True, DELETE stamps ``deleted_at = NOW()`` via UPDATE
    # instead of a hard DELETE. Set by the route generator from ``entity.soft_delete``.
    soft_delete: bool = False


def _set_handler_annotations(fn: Any, *, with_id: bool = False, with_auth: bool = False) -> None:
    """Set FastAPI-compatible type annotations on a dynamic handler function."""
    ann: dict[str, Any] = {"request": Request, "return": Any}
    if with_id:
        ann["id"] = UUID
    if with_auth:
        ann["auth_context"] = AuthContext
    fn.__annotations__ = ann


def _is_htmx_request(request: Any) -> bool:
    """Check if this is a genuine HTMX request (HX-Request header present)."""
    from dazzle.back.runtime.htmx_response import HtmxDetails

    return HtmxDetails.from_request(request).is_htmx


def _wants_html(request: Any) -> bool:
    """Check if the client wants an HTML response (HTMX or browser navigation)."""
    if _is_htmx_request(request):
        return True
    if hasattr(request, "headers"):
        accept = request.headers.get("Accept", "")
        return "text/html" in accept
    return False


def _htmx_current_url(request: Any) -> str | None:
    """Return the HX-Current-URL header if this is an HTMX request, else None."""
    return request.headers.get("hx-current-url") if _is_htmx_request(request) else None


def _htmx_parent_url(request: Any) -> str | None:
    """Return the parent of HX-Current-URL (e.g. /tasks/abc → /tasks) for post-delete redirect."""
    url = _htmx_current_url(request)
    if not url:
        return None
    from urllib.parse import urlparse

    parsed = urlparse(url)
    parent = parsed.path.rsplit("/", 1)[0] or "/"
    return parent


def _normalize_role(role: str) -> str:
    """Normalize a database role name to match DSL role references.

    Database roles may have a ``role_`` prefix (e.g. ``role_school_admin``)
    while DSL access rules use bare names (e.g. ``role(school_admin)``).
    """
    return role.removeprefix("role_")


def _extract_result_id(result: Any) -> str | None:
    """Extract the id from a create result (Pydantic model or dict)."""
    if hasattr(result, "id"):
        return str(result.id)
    if isinstance(result, dict) and "id" in result:
        return str(result["id"])
    return None
