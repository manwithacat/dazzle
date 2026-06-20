"""Read/detail handler factory family for generated CRUD routes.

Extracted verbatim from ``route_generator.py`` (#1361 final slice). This is
the READ family: ``create_read_handler``. The Cedar-READ enforcement (scope:
read: row enforcement #1174, permit/forbid eval, audit, ``auto_include``
re-hydration) was relocated to the transport-agnostic core
``access.gated.gated_read`` (#1422) so the page layer calls the same core
in-process instead of self-fetching this endpoint over loopback HTTP. The
``_read_cedar`` wrapper here is now a thin adapter: build the AccessContext,
call ``gated_read``, map ``RecordNotFound`` → 404, render the detail HTML.

A leaf module by design: it must not import ``route_generator`` at module
level (``route_generator`` imports ``create_read_handler`` back at module
level so the ``route_generator.<name>`` call sites, importers, and patch
points keep resolving there). The shared route-dispatch surface it needs
(``RouteSpec``, ``_set_handler_annotations``) comes from the ``route_support``
leaf at top level — extracted there in the 2026-06-20 smells round to break the
import cycle that previously forced lazy in-function imports.

Deliberately NOT named ``*_routes.py`` — the runtime-urls api-surface walker
globs that pattern and this module defines no routes.
"""

from collections.abc import Callable
from datetime import date
from typing import Any
from uuid import UUID

from fastapi import Depends, HTTPException, Request

from dazzle.http.runtime.audit_wrap import (
    _wrap_with_auth,
)
from dazzle.http.runtime.auth import AuthContext
from dazzle.http.runtime.htmx_render import _render_detail_html
from dazzle.http.runtime.http_errors import require_found

# Shared CRUD route-dispatch surface — from the route_support LEAF (smells round
# 2026-06-20). Was lazily imported from route_generator to dodge an import cycle;
# route_support is a leaf, so these are now plain top-level imports.
from dazzle.http.runtime.route_support import (
    RouteSpec,
    _set_handler_annotations,
)


def create_read_handler(spec: "RouteSpec") -> Callable[..., Any]:
    """Create a handler for read operations with optional Cedar-style access control.

    See :class:`RouteSpec` for the per-route contract (#1011).
    """

    service = spec.service
    auto_include = spec.auto_include
    auth_dep = spec.handler.auth_dep
    optional_auth_dep = spec.handler.optional_auth_dep
    require_auth_by_default = spec.handler.require_auth_by_default
    entity_name = spec.handler.entity_name
    audit_logger = spec.handler.audit_logger
    cedar_access_spec = spec.handler.cedar_access_spec

    async def _core(
        id: UUID,
        request: Request,
        *,
        current_user: str | None = None,
        existing: Any = None,
        **_extra: Any,
    ) -> Any:
        # #1223 Phase 3a.iv (read-path follow-up): honour `?as_of=YYYY-MM-DD`
        # on the single-row read endpoint for temporal entities. List + aggregate
        # paths already handle this via the __as_of filter dict key (v0.71.164);
        # read() doesn't take a filters dict so as_of threads through as a
        # service-execute kwarg. Repository.read consumes it directly.
        _entity_spec = getattr(service, "entity_spec", None)
        _entity_temporal = _entity_spec.temporal if _entity_spec is not None else None
        _read_kwargs: dict[str, Any] = {"include": auto_include}
        if _entity_temporal is not None:
            _as_of_raw = request.query_params.get(_entity_temporal.as_of_param)
            if _as_of_raw:
                try:
                    _read_kwargs["as_of"] = date.fromisoformat(_as_of_raw)
                except ValueError:
                    raise HTTPException(
                        status_code=400,
                        detail=(
                            f"Invalid {_entity_temporal.as_of_param}={_as_of_raw!r}: "
                            f"expected YYYY-MM-DD"
                        ),
                    )
        result = require_found(await service.execute(operation="read", id=id, **_read_kwargs))
        html = _render_detail_html(request, result, entity_name)
        return html if html is not None else result

    # READ is special: Cedar needs the *fetched* record for policy eval, but
    # the core already does the fetch.  The generic wrapper's pre-read would
    # double-fetch.  So for Cedar-READ we inline a lightweight wrapper that
    # fetches once, evaluates, then returns.
    _use_cedar = cedar_access_spec is not None and optional_auth_dep is not None
    fk_graph = spec.handler.fk_graph
    admin_personas = spec.handler.admin_personas
    if _use_cedar:

        async def _read_cedar(
            id: UUID, request: Request, auth_context: AuthContext = Depends(optional_auth_dep)
        ) -> Any:
            # Thin adapter (#1422): the scope+permit enforcement and the data
            # fetch were relocated, verbatim, into the transport-agnostic core
            # `gated_read`. The page layer now calls the same core in-process
            # instead of self-fetching this endpoint over loopback HTTP. This
            # route keeps only the HTTP shaping: build the access context, call
            # the core, map a denied/missing result to 404 (READ keeps
            # row-existence opaque), and render the detail HTML.
            from dazzle.http.runtime.access.gated import (
                RecordNotFound,
                access_context_from,
                gated_read,
            )

            assert cedar_access_spec is not None
            access = access_context_from(
                auth_context=auth_context,
                entity_name=entity_name,
                cedar_access_spec=cedar_access_spec,
                fk_graph=fk_graph,
                admin_personas=admin_personas,
            )
            try:
                result = await gated_read(
                    service,
                    access,
                    id,
                    include=auto_include,
                    audit_logger=audit_logger,
                    request=request,
                )
            except RecordNotFound:
                raise HTTPException(status_code=404, detail="Not found")
            html = _render_detail_html(request, result, entity_name)
            return html if html is not None else result

        _set_handler_annotations(_read_cedar, with_id=True, with_auth=True)
        return _read_cedar

    # Non-cedar: use the generic wrapper (no pre-read needed)
    return _wrap_with_auth(
        _core,
        service=service,
        cedar_access_spec=None,
        auth_dep=auth_dep,
        optional_auth_dep=optional_auth_dep,
        require_auth_by_default=require_auth_by_default,
        operation="read",
        entity_name=entity_name,
        audit_logger=audit_logger,
    )
