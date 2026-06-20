"""Read/detail handler factory family for generated CRUD routes.

Extracted verbatim from ``route_generator.py`` (#1361 final slice). This is
the READ family: ``create_read_handler``, including the inlined Cedar-READ
wrapper that fetches once through ``_scoped_pre_read`` (scope: read: row
enforcement, #1174), evaluates the permit/forbid policy, audit-logs the
decision, and re-hydrates ``auto_include`` relations.

A leaf module by design: it must not import ``route_generator`` at module
level (``route_generator`` imports ``create_read_handler`` back at module
level so the ``route_generator.<name>`` call sites, importers, and patch
points keep resolving there). The shared route-dispatch surface it needs
(``RouteSpec``, ``_set_handler_annotations``) comes from the ``route_support``
leaf at top level — extracted there in the 2026-06-20 smells round to break the
import cycle that previously forced lazy in-function imports.

NOTE (#1361 slice 3 contract, unchanged here): ``_scoped_pre_read`` is
imported at module level from its real home, ``scope_filters`` — the Cedar
read path resolves it through *this* module's namespace now.

Deliberately NOT named ``*_routes.py`` — the runtime-urls api-surface walker
globs that pattern and this module defines no routes.
"""

from collections.abc import Callable
from datetime import date
from typing import Any
from uuid import UUID

from fastapi import Depends, HTTPException, Request

from dazzle.back.runtime.audit_wrap import (
    _SCOPE_DENY_EFFECT,
    _build_access_context,
    _log_audit_decision,
    _record_to_dict,
    _wrap_with_auth,
)
from dazzle.back.runtime.auth import AuthContext
from dazzle.back.runtime.htmx_render import _render_detail_html
from dazzle.back.runtime.http_errors import require_found

# Shared CRUD route-dispatch surface — from the route_support LEAF (smells round
# 2026-06-20). Was lazily imported from route_generator to dodge an import cycle;
# route_support is a leaf, so these are now plain top-level imports.
from dazzle.back.runtime.route_support import (
    RouteSpec,
    _set_handler_annotations,
)
from dazzle.back.runtime.scope_filters import _scoped_pre_read


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
            from dazzle.back.runtime.audit_log import measure_evaluation_time
            from dazzle.core.access import AccessDecision, AccessOperationKind
            from dazzle.render.access_evaluator import evaluate_permission

            # Apply `scope: read:` row-level enforcement (#1174). Before this,
            # the single-id READ path fetched the row unscoped and only ran the
            # Cedar permit/forbid evaluator — so a role holding `permit: read`
            # plus a `scope: read:` row-filter (e.g. `project.org =
            # current_user.org`) could IDOR-fetch *any* row by id, cross-tenant.
            # `_scoped_pre_read` re-queries through the scope predicate (the
            # same path UPDATE/DELETE use) and returns None — yielding a 404 —
            # when the row is outside the caller's scope.
            assert cedar_access_spec is not None
            result = await _scoped_pre_read(
                service=service,
                operation="read",
                id=id,
                cedar_access_spec=cedar_access_spec,
                auth_context=auth_context,
                entity_name=entity_name,
                fk_graph=fk_graph,
                admin_personas=admin_personas,
            )
            if result is None:
                # Scope filter hid the row (or it does not exist). Record the
                # deny in the audit trail — a scope-denied read is an
                # access-control decision and `audit: all` entities must
                # capture it — then 404 (row-existence opaque to the caller).
                if audit_logger:
                    _u, _ = _build_access_context(auth_context)
                    await _log_audit_decision(
                        audit_logger,
                        request,
                        operation="read",
                        entity_name=entity_name,
                        entity_id=str(id),
                        decision="deny",
                        matched_policy=_SCOPE_DENY_EFFECT,
                        policy_effect=_SCOPE_DENY_EFFECT,
                        user=_u,
                    )
                raise HTTPException(status_code=404, detail="Not found")
            # `_scoped_pre_read` may return a row fetched via the list path,
            # which does not carry `include=auto_include` relations. Re-fetch
            # through the read path so the response shape is unchanged when a
            # scope filter was applied. The re-fetch is intentionally unscoped:
            # scope has already passed for this id above — this only restores
            # the relation hydration the list-path row lacks.
            if auto_include:
                hydrated = await service.execute(operation="read", id=id, include=auto_include)
                if hydrated is not None:
                    result = hydrated

            user, ctx = _build_access_context(auth_context)
            assert cedar_access_spec is not None
            decision: AccessDecision
            decision, eval_us = measure_evaluation_time(
                lambda: evaluate_permission(
                    cedar_access_spec,
                    AccessOperationKind.READ,
                    _record_to_dict(result),
                    ctx,
                    entity_name=entity_name,
                )
            )

            if audit_logger:
                await _log_audit_decision(
                    audit_logger,
                    request,
                    operation="read",
                    entity_name=entity_name,
                    entity_id=str(id),
                    decision="allow" if decision.allowed else "deny",
                    matched_policy=decision.matched_policy,
                    policy_effect=decision.effect,
                    user=user,
                    evaluation_time_us=eval_us,
                )

            if not decision.allowed:
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
