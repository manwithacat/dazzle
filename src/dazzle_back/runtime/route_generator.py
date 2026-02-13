"""
Route generator - generates FastAPI routes from EndpointSpec.

This module creates FastAPI routers and routes from backend specifications.
"""

from collections.abc import Callable
from enum import Enum
from typing import Any
from uuid import UUID

from pydantic import BaseModel

from dazzle.core.strings import to_api_plural
from dazzle_back.specs.endpoint import EndpointSpec, HttpMethod
from dazzle_back.specs.service import OperationKind, ServiceSpec

# FastAPI is optional - only import if available
try:
    from fastapi import APIRouter as _APIRouter
    from fastapi import Depends, HTTPException, Query, Request
    from fastapi.responses import HTMLResponse, JSONResponse

    from dazzle_back.runtime.auth import AuthContext
    from dazzle_back.runtime.htmx_response import htmx_trigger_headers

    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False
    _APIRouter = None  # type: ignore
    HTTPException = None  # type: ignore
    Query = None  # type: ignore
    Request = None  # type: ignore
    Depends = None  # type: ignore
    HTMLResponse = None  # type: ignore
    JSONResponse = None  # type: ignore
    AuthContext = None  # type: ignore

# Expose APIRouter name for return-type annotations (the real class is
# imported as _APIRouter to allow a None fallback when FastAPI is absent).
APIRouter = _APIRouter


def _is_htmx_request(request: Any) -> bool:
    """Check if this is an HTMX request that wants HTML fragments."""
    if not hasattr(request, "headers"):
        return False
    return bool(
        request.headers.get("HX-Request") == "true" or request.headers.get("Accept") == "text/html"
    )


def _with_htmx_triggers(
    request: Any, result: Any, entity_name: str, action: str, redirect_url: str | None = None
) -> Any:
    """Wrap a mutation result with HX-Trigger headers for HTMX requests.

    For non-HTMX requests, returns the result unchanged (JSON serialized by FastAPI).
    For HTMX requests, returns a JSONResponse with HX-Trigger headers so the client
    can react to entity mutations (show toasts, refresh lists, etc.).

    Args:
        request: The incoming request.
        result: The mutation result.
        entity_name: Name of the entity (e.g. "Task").
        action: Mutation action ("created", "updated", "deleted").
        redirect_url: Optional URL for HX-Redirect header (post-create navigation).
    """
    if not _is_htmx_request(request):
        return result

    from fastapi.responses import JSONResponse as _JSONResponse

    # Serialize Pydantic models
    if hasattr(result, "model_dump"):
        body = result.model_dump(mode="json")
    else:
        body = result

    headers = htmx_trigger_headers(entity_name, action)
    if redirect_url:
        headers["HX-Redirect"] = redirect_url
    return _JSONResponse(content=body, headers=headers)


async def _parse_request_body(request: Any) -> dict[str, Any]:
    """Parse request body as JSON or form data.

    HTMX forms send JSON when the json-enc extension is loaded, but
    fall back to form-urlencoded otherwise.  Accept both so the API
    works regardless of client encoding.

    Empty string values are converted to None so that optional fields
    (e.g. ref/UUID fields) pass Pydantic validation.
    """
    content_type = (request.headers.get("content-type") or "").lower()
    if "application/x-www-form-urlencoded" in content_type:
        form = await request.form()
        body = dict(form)
    else:
        # Default: JSON (covers application/json and missing header)
        body = await request.json()
    # Convert empty strings to None for optional field validation
    return {k: (None if v == "" else v) for k, v in body.items()}


# =============================================================================
# Route Handler Factory
# =============================================================================


def create_list_handler(
    service: Any,
    _response_schema: type[BaseModel] | None = None,
    access_spec: dict[str, Any] | None = None,
    optional_auth_dep: Callable[..., Any] | None = None,
    require_auth_by_default: bool = False,
) -> Callable[..., Any]:
    """Create a handler for list operations with optional access control.

    Args:
        service: Service instance for data operations
        _response_schema: Response schema (unused, kept for compatibility)
        access_spec: Access control specification for this entity
        optional_auth_dep: FastAPI dependency for optional auth (returns AuthContext)
        require_auth_by_default: If True, require authentication when no access_spec is defined
    """

    if optional_auth_dep is not None:

        async def _auth_handler(
            request: Request,
            auth_context: AuthContext = Depends(optional_auth_dep),
            page: int = Query(1, ge=1, description="Page number"),
            page_size: int = Query(20, ge=1, le=100, description="Items per page"),
            sort: str | None = Query(None, description="Sort field"),
            dir: str = Query("asc", description="Sort direction (asc/desc)"),
            search: str | None = Query(None, description="Search query"),
        ) -> Any:
            is_authenticated = auth_context.is_authenticated
            user_id = str(auth_context.user.id) if auth_context.user else None

            # Deny-default: require authentication when enabled and no explicit access rules
            if require_auth_by_default and not access_spec and not is_authenticated:
                raise HTTPException(
                    status_code=401,
                    detail="Authentication required",
                )

            return await _list_handler_body(
                service,
                access_spec,
                is_authenticated,
                user_id,
                request,
                page,
                page_size,
                sort,
                dir,
                search,
            )

        _auth_handler.__annotations__ = {
            "request": Request,
            "auth_context": AuthContext,
            "page": int,
            "page_size": int,
            "sort": str | None,
            "dir": str,
            "search": str | None,
            "return": Any,
        }
        return _auth_handler

    async def _noauth_handler(
        request: Request,
        page: int = Query(1, ge=1, description="Page number"),
        page_size: int = Query(20, ge=1, le=100, description="Items per page"),
        sort: str | None = Query(None, description="Sort field"),
        dir: str = Query("asc", description="Sort direction (asc/desc)"),
        search: str | None = Query(None, description="Search query"),
    ) -> Any:
        return await _list_handler_body(
            service,
            access_spec,
            False,
            None,
            request,
            page,
            page_size,
            sort,
            dir,
            search,
        )

    _noauth_handler.__annotations__ = {
        "request": Request,
        "page": int,
        "page_size": int,
        "sort": str | None,
        "dir": str,
        "search": str | None,
        "return": Any,
    }
    return _noauth_handler


async def _list_handler_body(
    service: Any,
    access_spec: dict[str, Any] | None,
    is_authenticated: bool,
    user_id: str | None,
    request: Any,
    page: int,
    page_size: int,
    sort: str | None,
    dir: str,
    search: str | None,
) -> Any:
    """Shared list handler logic for both auth and no-auth paths."""
    from dazzle_back.runtime.condition_evaluator import (
        build_visibility_filter,
        filter_records_by_condition,
    )

    # Build visibility filters
    sql_filters, post_filter = build_visibility_filter(access_spec, is_authenticated, user_id)

    # Extract filter[field] params from query string
    filters: dict[str, Any] = {}
    for key, value in request.query_params.items():
        if key.startswith("filter[") and key.endswith("]") and value:
            filters[key[7:-1]] = value

    # Merge visibility filters with user filters
    merged_filters: dict[str, Any] | None = None
    if sql_filters or filters:
        merged_filters = {**(sql_filters or {}), **filters}

    # Build sort list for repository
    sort_list = [f"-{sort}" if dir == "desc" else sort] if sort else None

    # Execute list with filters, sort, and search
    result = await service.execute(
        operation="list",
        page=page,
        page_size=page_size,
        filters=merged_filters,
        sort=sort_list,
        search=search,
    )

    # Apply post-filtering if needed (for OR conditions)
    if post_filter and result and "items" in result:
        context = {"current_user_id": user_id}
        # Convert Pydantic models to dicts for filtering
        items = result["items"]
        if items and hasattr(items[0], "model_dump"):
            items = [item.model_dump() for item in items]
        filtered_items = filter_records_by_condition(items, post_filter, context)
        result["items"] = filtered_items
        result["total"] = len(filtered_items)

    # HTMX content negotiation: return HTML fragment for HX-Request
    if _is_htmx_request(request):
        try:
            from dazzle_ui.runtime.template_renderer import render_fragment

            items = result.get("items", []) if isinstance(result, dict) else []
            # Convert Pydantic models to dicts
            if items and hasattr(items[0], "model_dump"):
                items = [item.model_dump() for item in items]
            # Render table rows fragment with sort/filter state
            html = render_fragment(
                "fragments/table_rows.html",
                table={
                    "rows": items,
                    "columns": request.state.htmx_columns
                    if hasattr(request.state, "htmx_columns")
                    else [],
                    "detail_url_template": getattr(request.state, "htmx_detail_url", None),
                    "entity_name": getattr(request.state, "htmx_entity_name", "Item"),
                    "api_endpoint": str(request.url.path),
                    "sort_field": sort or "",
                    "sort_dir": dir,
                    "filter_values": filters,
                    "page": page,
                    "page_size": page_size,
                    "total": result.get("total", 0) if isinstance(result, dict) else 0,
                    "empty_message": getattr(
                        request.state, "htmx_empty_message", "No items found."
                    ),
                },
            )
            return HTMLResponse(content=html)
        except ImportError:
            pass  # Template renderer not available, fall through to JSON

    return result


def create_read_handler(
    service: Any,
    _response_schema: type[BaseModel] | None = None,
    auth_dep: Callable[..., Any] | None = None,
    require_auth_by_default: bool = False,
    entity_name: str = "Item",
    audit_logger: Any | None = None,
    cedar_access_spec: Any | None = None,
    optional_auth_dep: Callable[..., Any] | None = None,
) -> Callable[..., Any]:
    """Create a handler for read operations with optional Cedar-style access control."""

    # If we have Cedar access spec with READ rules, use optional auth for evaluation
    _use_cedar = cedar_access_spec is not None and optional_auth_dep is not None

    if _use_cedar:

        async def _read_cedar(
            id: UUID, request: Request, auth_context: AuthContext = Depends(optional_auth_dep)
        ) -> Any:
            from dazzle_back.runtime.access_evaluator import (
                AccessDecision,
                AccessRuntimeContext,
                evaluate_permission,
            )
            from dazzle_back.specs.auth import AccessOperationKind

            result = await service.execute(operation="read", id=id)
            if result is None:
                raise HTTPException(status_code=404, detail="Not found")

            # Build runtime context
            user = auth_context.user if auth_context.is_authenticated else None
            ctx = AccessRuntimeContext(
                user_id=str(user.id) if user else None,
                roles=list(getattr(user, "roles", [])) if user else [],
                is_superuser=getattr(user, "is_superuser", False) if user else False,
            )

            # Evaluate Cedar policy
            record = (
                result.model_dump()
                if hasattr(result, "model_dump")
                else (result if isinstance(result, dict) else {})
            )
            assert cedar_access_spec is not None
            decision: AccessDecision = evaluate_permission(
                cedar_access_spec, AccessOperationKind.READ, record, ctx
            )

            if audit_logger:
                from dazzle_back.runtime.audit_log import create_audit_context_from_request

                audit_ctx = create_audit_context_from_request(request)
                await audit_logger.log_decision(
                    operation="read",
                    entity_name=entity_name,
                    entity_id=str(id),
                    decision="allow" if decision.allowed else "deny",
                    matched_policy=decision.matched_policy,
                    policy_effect=decision.effect,
                    user_id=str(user.id) if user else None,
                    user_email=getattr(user, "email", None) if user else None,
                    user_roles=list(getattr(user, "roles", [])) if user else None,
                    **audit_ctx,
                )

            if not decision.allowed:
                # Return 404 to prevent enumeration
                raise HTTPException(status_code=404, detail="Not found")
            return result

        _read_cedar.__annotations__ = {
            "id": UUID,
            "request": Request,
            "auth_context": AuthContext,
            "return": Any,
        }
        return _read_cedar

    if require_auth_by_default and auth_dep:

        async def _read_auth(
            id: UUID, request: Request, auth_context: AuthContext = Depends(auth_dep)
        ) -> Any:
            result = await service.execute(operation="read", id=id)
            if result is None:
                raise HTTPException(status_code=404, detail="Not found")
            if audit_logger:
                from dazzle_back.runtime.audit_log import create_audit_context_from_request

                ctx = create_audit_context_from_request(request)
                await audit_logger.log_decision(
                    operation="read",
                    entity_name=entity_name,
                    entity_id=str(id),
                    decision="allow",
                    matched_policy="authenticated",
                    policy_effect="permit",
                    user_id=str(auth_context.user.id) if auth_context.user else None,
                    user_email=getattr(auth_context.user, "email", None)
                    if auth_context.user
                    else None,
                    user_roles=list(getattr(auth_context.user, "roles", []))
                    if auth_context.user
                    else None,
                    **ctx,
                )
            return result

        _read_auth.__annotations__ = {
            "id": UUID,
            "request": Request,
            "auth_context": AuthContext,
            "return": Any,
        }
        return _read_auth

    async def _read_noauth(id: UUID, request: Request) -> Any:
        result = await service.execute(operation="read", id=id)
        if result is None:
            raise HTTPException(status_code=404, detail="Not found")
        return result

    _read_noauth.__annotations__ = {"id": UUID, "request": Request, "return": Any}
    return _read_noauth


def _extract_result_id(result: Any) -> str | None:
    """Extract the id from a create result (Pydantic model or dict)."""
    if hasattr(result, "id"):
        return str(result.id)
    if isinstance(result, dict) and "id" in result:
        return str(result["id"])
    return None


def create_create_handler(
    service: Any,
    input_schema: type[BaseModel],
    _response_schema: type[BaseModel] | None = None,
    auth_dep: Callable[..., Any] | None = None,
    require_auth_by_default: bool = False,
    entity_name: str = "Item",
    entity_slug: str = "",
    audit_logger: Any | None = None,
    cedar_access_spec: Any | None = None,
    optional_auth_dep: Callable[..., Any] | None = None,
) -> Callable[..., Any]:
    """Create a handler for create operations with optional Cedar-style access control."""

    def _build_redirect_url(result: Any) -> str | None:
        if not entity_slug:
            return None
        result_id = _extract_result_id(result)
        if result_id:
            return f"/app/{entity_slug}/{result_id}"
        return None

    _use_cedar = cedar_access_spec is not None and optional_auth_dep is not None

    if _use_cedar:

        async def _create_cedar(
            request: Request, auth_context: AuthContext = Depends(optional_auth_dep)
        ) -> Any:
            from dazzle_back.runtime.access_evaluator import (
                AccessDecision,
                AccessRuntimeContext,
                evaluate_permission,
            )
            from dazzle_back.specs.auth import AccessOperationKind

            user = auth_context.user if auth_context.is_authenticated else None
            ctx = AccessRuntimeContext(
                user_id=str(user.id) if user else None,
                roles=list(getattr(user, "roles", [])) if user else [],
                is_superuser=getattr(user, "is_superuser", False) if user else False,
            )

            assert cedar_access_spec is not None
            decision: AccessDecision = evaluate_permission(
                cedar_access_spec, AccessOperationKind.CREATE, None, ctx
            )

            if audit_logger:
                from dazzle_back.runtime.audit_log import create_audit_context_from_request

                audit_ctx = create_audit_context_from_request(request)
                await audit_logger.log_decision(
                    operation="create",
                    entity_name=entity_name,
                    entity_id=None,
                    decision="allow" if decision.allowed else "deny",
                    matched_policy=decision.matched_policy,
                    policy_effect=decision.effect,
                    user_id=str(user.id) if user else None,
                    user_email=getattr(user, "email", None) if user else None,
                    user_roles=list(getattr(user, "roles", [])) if user else None,
                    **audit_ctx,
                )

            if not decision.allowed:
                raise HTTPException(status_code=403, detail="Forbidden")

            body = await _parse_request_body(request)
            data = input_schema.model_validate(body)
            result = await service.execute(operation="create", data=data)
            return _with_htmx_triggers(
                request, result, entity_name, "created", redirect_url=_build_redirect_url(result)
            )

        _create_cedar.__annotations__ = {
            "request": Request,
            "auth_context": AuthContext,
            "return": Any,
        }
        return _create_cedar

    if require_auth_by_default and auth_dep:

        async def _create_auth(
            request: Request, auth_context: AuthContext = Depends(auth_dep)
        ) -> Any:
            body = await _parse_request_body(request)
            data = input_schema.model_validate(body)
            result = await service.execute(operation="create", data=data)
            if audit_logger:
                from dazzle_back.runtime.audit_log import create_audit_context_from_request

                ctx = create_audit_context_from_request(request)
                await audit_logger.log_decision(
                    operation="create",
                    entity_name=entity_name,
                    entity_id=_extract_result_id(result),
                    decision="allow",
                    matched_policy="authenticated",
                    policy_effect="permit",
                    user_id=str(auth_context.user.id) if auth_context.user else None,
                    user_email=getattr(auth_context.user, "email", None)
                    if auth_context.user
                    else None,
                    user_roles=list(getattr(auth_context.user, "roles", []))
                    if auth_context.user
                    else None,
                    **ctx,
                )
            return _with_htmx_triggers(
                request, result, entity_name, "created", redirect_url=_build_redirect_url(result)
            )

        _create_auth.__annotations__ = {
            "request": Request,
            "auth_context": AuthContext,
            "return": Any,
        }
        return _create_auth

    async def _create_noauth(request: Request) -> Any:
        body = await _parse_request_body(request)
        data = input_schema.model_validate(body)
        result = await service.execute(operation="create", data=data)
        return _with_htmx_triggers(
            request, result, entity_name, "created", redirect_url=_build_redirect_url(result)
        )

    _create_noauth.__annotations__ = {"request": Request, "return": Any}
    return _create_noauth


def create_update_handler(
    service: Any,
    input_schema: type[BaseModel],
    _response_schema: type[BaseModel] | None = None,
    auth_dep: Callable[..., Any] | None = None,
    require_auth_by_default: bool = False,
    entity_name: str = "Item",
    audit_logger: Any | None = None,
    cedar_access_spec: Any | None = None,
    optional_auth_dep: Callable[..., Any] | None = None,
) -> Callable[..., Any]:
    """Create a handler for update operations with optional Cedar-style access control."""

    _use_cedar = cedar_access_spec is not None and optional_auth_dep is not None

    if _use_cedar:

        async def _update_cedar(
            id: UUID, request: Request, auth_context: AuthContext = Depends(optional_auth_dep)
        ) -> Any:
            from dazzle_back.runtime.access_evaluator import (
                AccessDecision,
                AccessRuntimeContext,
                evaluate_permission,
            )
            from dazzle_back.specs.auth import AccessOperationKind

            # Fetch existing record for condition evaluation
            existing = await service.execute(operation="read", id=id)
            if existing is None:
                raise HTTPException(status_code=404, detail="Not found")

            user = auth_context.user if auth_context.is_authenticated else None
            ctx = AccessRuntimeContext(
                user_id=str(user.id) if user else None,
                roles=list(getattr(user, "roles", [])) if user else [],
                is_superuser=getattr(user, "is_superuser", False) if user else False,
            )

            record = (
                existing.model_dump()
                if hasattr(existing, "model_dump")
                else (existing if isinstance(existing, dict) else {})
            )
            assert cedar_access_spec is not None
            decision: AccessDecision = evaluate_permission(
                cedar_access_spec, AccessOperationKind.UPDATE, record, ctx
            )

            if audit_logger:
                from dazzle_back.runtime.audit_log import create_audit_context_from_request

                audit_ctx = create_audit_context_from_request(request)
                await audit_logger.log_decision(
                    operation="update",
                    entity_name=entity_name,
                    entity_id=str(id),
                    decision="allow" if decision.allowed else "deny",
                    matched_policy=decision.matched_policy,
                    policy_effect=decision.effect,
                    user_id=str(user.id) if user else None,
                    user_email=getattr(user, "email", None) if user else None,
                    user_roles=list(getattr(user, "roles", [])) if user else None,
                    **audit_ctx,
                )

            if not decision.allowed:
                raise HTTPException(status_code=403, detail="Forbidden")

            body = await _parse_request_body(request)
            data = input_schema.model_validate(body)
            result = await service.execute(operation="update", id=id, data=data)
            if result is None:
                raise HTTPException(status_code=404, detail="Not found")
            return _with_htmx_triggers(request, result, entity_name, "updated")

        _update_cedar.__annotations__ = {
            "id": UUID,
            "request": Request,
            "auth_context": AuthContext,
            "return": Any,
        }
        return _update_cedar

    if require_auth_by_default and auth_dep:

        async def _update_auth(
            id: UUID, request: Request, auth_context: AuthContext = Depends(auth_dep)
        ) -> Any:
            body = await _parse_request_body(request)
            data = input_schema.model_validate(body)
            result = await service.execute(operation="update", id=id, data=data)
            if result is None:
                raise HTTPException(status_code=404, detail="Not found")
            if audit_logger:
                from dazzle_back.runtime.audit_log import create_audit_context_from_request

                ctx = create_audit_context_from_request(request)
                await audit_logger.log_decision(
                    operation="update",
                    entity_name=entity_name,
                    entity_id=str(id),
                    decision="allow",
                    matched_policy="authenticated",
                    policy_effect="permit",
                    user_id=str(auth_context.user.id) if auth_context.user else None,
                    user_email=getattr(auth_context.user, "email", None)
                    if auth_context.user
                    else None,
                    user_roles=list(getattr(auth_context.user, "roles", []))
                    if auth_context.user
                    else None,
                    **ctx,
                )
            return _with_htmx_triggers(request, result, entity_name, "updated")

        _update_auth.__annotations__ = {
            "id": UUID,
            "request": Request,
            "auth_context": AuthContext,
            "return": Any,
        }
        return _update_auth

    async def _update_noauth(id: UUID, request: Request) -> Any:
        body = await _parse_request_body(request)
        data = input_schema.model_validate(body)
        result = await service.execute(operation="update", id=id, data=data)
        if result is None:
            raise HTTPException(status_code=404, detail="Not found")
        return _with_htmx_triggers(request, result, entity_name, "updated")

    _update_noauth.__annotations__ = {"id": UUID, "request": Request, "return": Any}
    return _update_noauth


def create_delete_handler(
    service: Any,
    auth_dep: Callable[..., Any] | None = None,
    require_auth_by_default: bool = False,
    entity_name: str = "Item",
    audit_logger: Any | None = None,
    cedar_access_spec: Any | None = None,
    optional_auth_dep: Callable[..., Any] | None = None,
) -> Callable[..., Any]:
    """Create a handler for delete operations with optional Cedar-style access control."""

    _use_cedar = cedar_access_spec is not None and optional_auth_dep is not None

    if _use_cedar:

        async def _delete_cedar(
            id: UUID, request: Request, auth_context: AuthContext = Depends(optional_auth_dep)
        ) -> Any:
            from dazzle_back.runtime.access_evaluator import (
                AccessDecision,
                AccessRuntimeContext,
                evaluate_permission,
            )
            from dazzle_back.specs.auth import AccessOperationKind

            # Fetch existing record for condition evaluation
            existing = await service.execute(operation="read", id=id)
            if existing is None:
                raise HTTPException(status_code=404, detail="Not found")

            user = auth_context.user if auth_context.is_authenticated else None
            ctx = AccessRuntimeContext(
                user_id=str(user.id) if user else None,
                roles=list(getattr(user, "roles", [])) if user else [],
                is_superuser=getattr(user, "is_superuser", False) if user else False,
            )

            record = (
                existing.model_dump()
                if hasattr(existing, "model_dump")
                else (existing if isinstance(existing, dict) else {})
            )
            assert cedar_access_spec is not None
            decision: AccessDecision = evaluate_permission(
                cedar_access_spec, AccessOperationKind.DELETE, record, ctx
            )

            if audit_logger:
                from dazzle_back.runtime.audit_log import create_audit_context_from_request

                audit_ctx = create_audit_context_from_request(request)
                await audit_logger.log_decision(
                    operation="delete",
                    entity_name=entity_name,
                    entity_id=str(id),
                    decision="allow" if decision.allowed else "deny",
                    matched_policy=decision.matched_policy,
                    policy_effect=decision.effect,
                    user_id=str(user.id) if user else None,
                    user_email=getattr(user, "email", None) if user else None,
                    user_roles=list(getattr(user, "roles", [])) if user else None,
                    **audit_ctx,
                )

            if not decision.allowed:
                raise HTTPException(status_code=403, detail="Forbidden")

            result = await service.execute(operation="delete", id=id)
            if not result:
                raise HTTPException(status_code=404, detail="Not found")
            return _with_htmx_triggers(request, {"deleted": True}, entity_name, "deleted")

        _delete_cedar.__annotations__ = {
            "id": UUID,
            "request": Request,
            "auth_context": AuthContext,
            "return": Any,
        }
        return _delete_cedar

    if require_auth_by_default and auth_dep:

        async def _delete_auth(
            id: UUID, request: Request, auth_context: AuthContext = Depends(auth_dep)
        ) -> Any:
            result = await service.execute(operation="delete", id=id)
            if not result:
                raise HTTPException(status_code=404, detail="Not found")
            if audit_logger:
                from dazzle_back.runtime.audit_log import create_audit_context_from_request

                ctx = create_audit_context_from_request(request)
                await audit_logger.log_decision(
                    operation="delete",
                    entity_name=entity_name,
                    entity_id=str(id),
                    decision="allow",
                    matched_policy="authenticated",
                    policy_effect="permit",
                    user_id=str(auth_context.user.id) if auth_context.user else None,
                    user_email=getattr(auth_context.user, "email", None)
                    if auth_context.user
                    else None,
                    user_roles=list(getattr(auth_context.user, "roles", []))
                    if auth_context.user
                    else None,
                    **ctx,
                )
            return _with_htmx_triggers(request, {"deleted": True}, entity_name, "deleted")

        _delete_auth.__annotations__ = {
            "id": UUID,
            "request": Request,
            "auth_context": AuthContext,
            "return": Any,
        }
        return _delete_auth

    async def _delete_noauth(id: UUID, request: Request) -> Any:
        result = await service.execute(operation="delete", id=id)
        if not result:
            raise HTTPException(status_code=404, detail="Not found")
        return _with_htmx_triggers(request, {"deleted": True}, entity_name, "deleted")

    _delete_noauth.__annotations__ = {"id": UUID, "request": Request, "return": Any}
    return _delete_noauth


def create_custom_handler(
    service: Any,
    input_schema: type[BaseModel] | None = None,
) -> Callable[..., Any]:
    """Create a handler for custom operations."""
    if input_schema:

        async def handler_with_input(request: Request) -> Any:
            body = await request.json()
            data = input_schema.model_validate(body)
            result = await service.execute(**data.model_dump())
            return result

        # Override annotations with the proper type so FastAPI recognizes it
        handler_with_input.__annotations__ = {"request": Request, "return": Any}

        return handler_with_input
    else:

        async def handler_no_input() -> Any:
            result = await service.execute()
            return result

        return handler_no_input


# =============================================================================
# Route Generator
# =============================================================================


class RouteGenerator:
    """
    Generates FastAPI routes from endpoint specifications.

    Creates routes with appropriate HTTP methods, paths, and handlers.
    """

    def __init__(
        self,
        services: dict[str, Any],
        models: dict[str, type[BaseModel]],
        schemas: dict[str, dict[str, type[BaseModel]]] | None = None,
        entity_access_specs: dict[str, dict[str, Any]] | None = None,
        auth_dep: Callable[..., Any] | None = None,
        optional_auth_dep: Callable[..., Any] | None = None,
        require_auth_by_default: bool = False,
        auth_store: Any | None = None,
        audit_logger: Any | None = None,
        cedar_access_specs: dict[str, Any] | None = None,
    ):
        """
        Initialize the route generator.

        Args:
            services: Dictionary mapping service names to service instances
            models: Dictionary mapping entity names to Pydantic models
            schemas: Optional dictionary with create/update schemas per entity
            entity_access_specs: Optional dictionary mapping entity names to access specs
            auth_dep: FastAPI dependency that requires authentication (raises 401)
            optional_auth_dep: FastAPI dependency for optional auth (returns empty AuthContext)
            require_auth_by_default: If True, require auth for all routes when no access spec
            auth_store: AuthStore instance for creating per-route role-based dependencies
            audit_logger: Optional AuditLogger for recording access decisions
            cedar_access_specs: Optional dict of entity_name -> EntityAccessSpec for Cedar evaluation
        """
        if not FASTAPI_AVAILABLE:
            raise RuntimeError("FastAPI is not installed. Install with: pip install fastapi")

        self.services = services
        self.models = models
        self.schemas = schemas or {}
        self.entity_access_specs = entity_access_specs or {}
        self.auth_dep = auth_dep
        self.optional_auth_dep = optional_auth_dep
        self.require_auth_by_default = require_auth_by_default
        self.auth_store = auth_store
        self.audit_logger = audit_logger
        self.cedar_access_specs = cedar_access_specs or {}
        self._router = _APIRouter()

    def generate_route(
        self,
        endpoint: EndpointSpec,
        service_spec: ServiceSpec | None = None,
    ) -> None:
        """
        Generate a single route from an endpoint specification.

        Args:
            endpoint: Endpoint specification
            service_spec: Optional service specification for type hints
        """
        service = self.services.get(endpoint.service)
        if not service:
            raise ValueError(f"Service not found: {endpoint.service}")

        # Determine entity name for schemas
        entity_name = None
        is_crud_service = False

        if service_spec:
            entity_name = service_spec.domain_operation.entity
            is_crud_service = service_spec.is_crud

        # Get schemas for the entity
        entity_schemas = self.schemas.get(entity_name or "", {})
        model = self.models.get(entity_name or "")

        # For CRUD services, determine operation from HTTP method
        # For non-CRUD services, use the service's domain_operation.kind
        operation_kind = None
        if service_spec and not is_crud_service:
            operation_kind = service_spec.domain_operation.kind

        # Create appropriate handler based on HTTP method (primary) or operation kind (secondary)
        handler: Callable[..., Any]

        # Derive entity slug for post-create redirect
        _entity_slug = (entity_name or "").lower().replace("_", "-")

        # Resolve audit logger and Cedar access spec for this entity
        _audit = self.audit_logger
        _cedar_spec = self.cedar_access_specs.get(entity_name or "")

        # POST -> CREATE
        if endpoint.method == HttpMethod.POST or operation_kind == OperationKind.CREATE:
            create_schema = entity_schemas.get("create", model)
            if create_schema:
                handler = create_create_handler(
                    service,
                    create_schema,
                    model,
                    auth_dep=self.auth_dep,
                    require_auth_by_default=self.require_auth_by_default,
                    entity_name=entity_name or "Item",
                    entity_slug=_entity_slug,
                    audit_logger=_audit,
                    cedar_access_spec=_cedar_spec,
                    optional_auth_dep=self.optional_auth_dep,
                )
                self._add_route(endpoint, handler, response_model=model)
            else:
                raise ValueError(f"No create schema for endpoint: {endpoint.name}")

        # GET with {id} -> READ
        elif (
            endpoint.method == HttpMethod.GET and "{id}" in endpoint.path
        ) or operation_kind == OperationKind.READ:
            handler = create_read_handler(
                service,
                model,
                auth_dep=self.auth_dep,
                require_auth_by_default=self.require_auth_by_default,
                entity_name=entity_name or "Item",
                audit_logger=_audit,
                cedar_access_spec=_cedar_spec,
                optional_auth_dep=self.optional_auth_dep,
            )
            self._add_route(endpoint, handler, response_model=model)

        # GET without {id} -> LIST
        elif (
            endpoint.method == HttpMethod.GET and "{id}" not in endpoint.path
        ) or operation_kind == OperationKind.LIST:
            # Get access spec for this entity
            access_spec = self.entity_access_specs.get(entity_name or "")
            handler = create_list_handler(
                service,
                model,
                access_spec=access_spec,
                optional_auth_dep=self.optional_auth_dep,
                require_auth_by_default=self.require_auth_by_default,
            )
            self._add_route(endpoint, handler, response_model=None)

        # PUT/PATCH -> UPDATE
        elif (
            endpoint.method in (HttpMethod.PUT, HttpMethod.PATCH)
            or operation_kind == OperationKind.UPDATE
        ):
            update_schema = entity_schemas.get("update", model)
            if update_schema:
                handler = create_update_handler(
                    service,
                    update_schema,
                    model,
                    auth_dep=self.auth_dep,
                    require_auth_by_default=self.require_auth_by_default,
                    entity_name=entity_name or "Item",
                    audit_logger=_audit,
                    cedar_access_spec=_cedar_spec,
                    optional_auth_dep=self.optional_auth_dep,
                )
                self._add_route(endpoint, handler, response_model=model)
            else:
                raise ValueError(f"No update schema for endpoint: {endpoint.name}")

        # DELETE -> DELETE
        elif endpoint.method == HttpMethod.DELETE or operation_kind == OperationKind.DELETE:
            handler = create_delete_handler(
                service,
                auth_dep=self.auth_dep,
                require_auth_by_default=self.require_auth_by_default,
                entity_name=entity_name or "Item",
                audit_logger=_audit,
                cedar_access_spec=_cedar_spec,
                optional_auth_dep=self.optional_auth_dep,
            )
            self._add_route(endpoint, handler, response_model=None)

        else:
            # Custom operation
            handler = create_custom_handler(service)
            self._add_route(endpoint, handler, response_model=None)

    def _add_route(
        self,
        endpoint: EndpointSpec,
        handler: Callable[..., Any],
        response_model: type[BaseModel] | None = None,
    ) -> None:
        """Add a route to the router."""
        # Map HTTP methods to router methods
        method_map = {
            HttpMethod.GET: self._router.get,
            HttpMethod.POST: self._router.post,
            HttpMethod.PUT: self._router.put,
            HttpMethod.PATCH: self._router.patch,
            HttpMethod.DELETE: self._router.delete,
        }

        router_method = method_map.get(endpoint.method)
        if not router_method:
            raise ValueError(f"Unsupported HTTP method: {endpoint.method}")

        # Convert path parameters from {id} to FastAPI format
        path = endpoint.path

        # Build route decorator kwargs
        route_kwargs: dict[str, Any] = {
            "summary": endpoint.description or endpoint.name,
            "tags": endpoint.tags or [],
        }

        if response_model:
            route_kwargs["response_model"] = response_model

        # Add role-based dependencies (RBAC)
        dependencies: list[Any] = []
        if endpoint.require_roles and self.auth_store:
            from dazzle_back.runtime.auth import create_auth_dependency

            role_dep = create_auth_dependency(self.auth_store, require_roles=endpoint.require_roles)
            dependencies.append(Depends(role_dep))

        if endpoint.deny_roles and self.auth_store:
            from dazzle_back.runtime.auth import create_deny_dependency

            deny_dep = create_deny_dependency(self.auth_store, deny_roles=endpoint.deny_roles)
            dependencies.append(Depends(deny_dep))

        if dependencies:
            route_kwargs["dependencies"] = dependencies

        # Add the route
        router_method(path, **route_kwargs)(handler)

    def generate_all_routes(
        self,
        endpoints: list[EndpointSpec],
        service_specs: dict[str, ServiceSpec] | None = None,
    ) -> APIRouter:
        """
        Generate routes for all endpoints.

        Args:
            endpoints: List of endpoint specifications
            service_specs: Optional dictionary mapping service names to specs

        Returns:
            FastAPI router with all routes
        """
        service_specs = service_specs or {}

        for endpoint in endpoints:
            service_spec = service_specs.get(endpoint.service)
            self.generate_route(endpoint, service_spec)

        return self._router

    @property
    def router(self) -> APIRouter:
        """Get the generated router."""
        return self._router


# =============================================================================
# Convenience Functions
# =============================================================================


def generate_crud_routes(
    entity_name: str,
    service: Any,
    model: type[BaseModel],
    create_schema: type[BaseModel],
    update_schema: type[BaseModel],
    prefix: str | None = None,
    tags: list[str | Enum] | None = None,
) -> APIRouter:
    """
    Generate standard CRUD routes for an entity.

    This is a convenience function for quickly creating RESTful routes.

    Args:
        entity_name: Name of the entity
        service: CRUD service instance
        model: Pydantic model for the entity
        create_schema: Schema for create operations
        update_schema: Schema for update operations
        prefix: Optional URL prefix (defaults to /entity_name)
        tags: Optional tags for grouping in OpenAPI docs

    Returns:
        FastAPI router with CRUD routes
    """
    if not FASTAPI_AVAILABLE:
        raise RuntimeError("FastAPI is not installed. Install with: pip install fastapi")

    router = _APIRouter()
    prefix = prefix or f"/{to_api_plural(entity_name)}"
    tags = tags or [entity_name]

    # List
    @router.get(prefix, tags=tags, summary=f"List {entity_name}s")
    async def list_items(
        page: int = Query(1, ge=1),
        page_size: int = Query(20, ge=1, le=100),
    ) -> Any:
        return await service.execute(operation="list", page=page, page_size=page_size)

    # Read
    @router.get(f"{prefix}/{{id}}", tags=tags, summary=f"Get {entity_name}", response_model=model)
    async def get_item(id: UUID) -> Any:
        result = await service.execute(operation="read", id=id)
        if result is None:
            raise HTTPException(status_code=404, detail="Not found")
        return result

    # Create
    @router.post(prefix, tags=tags, summary=f"Create {entity_name}", response_model=model)
    async def create_item(request: Request, data: create_schema) -> Any:  # type: ignore
        result = await service.execute(operation="create", data=data)
        return _with_htmx_triggers(request, result, entity_name, "created")

    # Update
    @router.put(
        f"{prefix}/{{id}}", tags=tags, summary=f"Update {entity_name}", response_model=model
    )
    async def update_item(id: UUID, request: Request, data: update_schema) -> Any:  # type: ignore
        result = await service.execute(operation="update", id=id, data=data)
        if result is None:
            raise HTTPException(status_code=404, detail="Not found")
        return _with_htmx_triggers(request, result, entity_name, "updated")

    # Delete
    @router.delete(f"{prefix}/{{id}}", tags=tags, summary=f"Delete {entity_name}")
    async def delete_item(id: UUID, request: Request) -> Any:
        result = await service.execute(operation="delete", id=id)
        if not result:
            raise HTTPException(status_code=404, detail="Not found")
        return _with_htmx_triggers(request, {"deleted": True}, entity_name, "deleted")

    return router
