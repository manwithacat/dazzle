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
    """Check if this is a genuine HTMX request (HX-Request header present)."""
    from dazzle_back.runtime.htmx_response import HtmxDetails

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
    # Strip trailing ID segment to get list page URL
    from urllib.parse import urlparse

    parsed = urlparse(url)
    parent = parsed.path.rsplit("/", 1)[0] or "/"
    return parent


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
    elif isinstance(result, dict):
        # Plain dicts may contain UUID or other non-JSON-serializable values
        # from the CRUD service layer.  Pre-convert via jsonable_encoder so
        # Starlette's JSONResponse (which uses stdlib json.dumps) doesn't crash.
        from fastapi.encoders import jsonable_encoder

        body = jsonable_encoder(result)
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
# Row-level RBAC helpers
# =============================================================================


def _extract_cedar_row_filters(
    cedar_access_spec: Any,
    user_id: str,
    auth_context: Any | None = None,
) -> dict[str, Any]:
    """Extract SQL-compatible row filters from Cedar permission rules.

    Scans LIST and READ permission rules for field-level conditions that
    reference ``current_user`` and converts them to repository filter syntax.
    Role-only rules (no field condition) are skipped since they grant
    unrestricted access to the operation.

    Returns a dict suitable for merging into the repository's filter kwargs.
    """
    import logging

    _logger = logging.getLogger(__name__)

    permissions = getattr(cedar_access_spec, "permissions", None)
    if not permissions:
        return {}

    # Collect roles from auth_context
    user_roles: set[str] = set()
    if auth_context is not None:
        _user_obj = getattr(auth_context, "user", None)
        if _user_obj:
            for r in getattr(_user_obj, "roles", []):
                user_roles.add(r if isinstance(r, str) else getattr(r, "name", str(r)))

    filters: dict[str, Any] = {}
    has_unrestricted_permit = False

    for rule in permissions:
        op = getattr(rule, "operation", None)
        if op is None:
            continue
        op_val = op.value if hasattr(op, "value") else str(op)

        # Only process LIST and READ rules
        if op_val not in ("list", "read"):
            continue

        effect = getattr(rule, "effect", None)
        if effect is None:
            continue
        effect_val = effect.value if hasattr(effect, "value") else str(effect)
        if effect_val != "permit":
            continue

        condition = getattr(rule, "condition", None)
        if condition is None:
            # Unconditional permit — user has full access, no row filter needed.
            # But only if they pass the role check (if personas specified).
            rule_personas = getattr(rule, "personas", [])
            if rule_personas:
                if user_roles & set(rule_personas):
                    has_unrestricted_permit = True
            else:
                has_unrestricted_permit = True
            continue

        # Check if this rule applies to the user's roles
        rule_personas = getattr(rule, "personas", [])
        if rule_personas and not (user_roles & set(rule_personas)):
            continue

        # Extract field comparison conditions
        _extract_condition_filters(condition, user_id, filters, _logger)

    # If user has any unrestricted permit, don't apply row filters
    if has_unrestricted_permit:
        return {}

    return filters


def _extract_condition_filters(
    condition: Any,
    user_id: str,
    filters: dict[str, Any],
    _logger: Any,
) -> None:
    """Recursively extract SQL filters from an AccessConditionSpec tree.

    Only handles simple comparison conditions with ``current_user`` as the value.
    Complex logical trees with OR are not pushed to SQL (they'd require post-fetch
    filtering which is already handled by the visibility system).
    """
    kind = getattr(condition, "kind", "")

    if kind == "comparison":
        field = getattr(condition, "field", None)
        value = getattr(condition, "value", None)
        op = getattr(condition, "comparison_op", None)
        if op is None:
            op_val = "="
        else:
            op_val = op.value if hasattr(op, "value") else str(op)

        if field and value == "current_user" and op_val in ("=", "eq", "equals"):
            filters[field] = user_id
        elif field and isinstance(value, (str, int, float, bool)) and value != "current_user":
            if op_val in ("=", "eq", "equals"):
                filters[field] = value
            elif op_val in ("!=", "ne", "not_equals"):
                filters[f"{field}__ne"] = value

    elif kind == "logical":
        logical_op = getattr(condition, "logical_op", None)
        if logical_op is None:
            return
        logical_op_val = logical_op.value if hasattr(logical_op, "value") else str(logical_op)

        # Only push AND conditions to SQL; OR needs post-fetch filtering
        if logical_op_val == "and":
            left = getattr(condition, "logical_left", None)
            right = getattr(condition, "logical_right", None)
            if left:
                _extract_condition_filters(left, user_id, filters, _logger)
            if right:
                _extract_condition_filters(right, user_id, filters, _logger)
        # OR and other logical operators require post-fetch filtering
        # which is handled by the visibility system already


# =============================================================================
# Access Control Helpers
# =============================================================================


def _build_access_context(auth_context: Any) -> tuple[Any, Any]:
    """Build (user, AccessRuntimeContext) from an AuthContext.

    Returns (user_or_none, runtime_context) for Cedar policy evaluation.
    """
    from dazzle_back.runtime.access_evaluator import AccessRuntimeContext

    user = auth_context.user if auth_context.is_authenticated else None
    ctx = AccessRuntimeContext(
        user_id=str(user.id) if user else None,
        roles=list(getattr(user, "roles", [])) if user else [],
        is_superuser=getattr(user, "is_superuser", False) if user else False,
    )
    return user, ctx


def _record_to_dict(result: Any) -> dict[str, Any]:
    """Convert a Pydantic model or dict to a plain dict for Cedar evaluation."""
    if hasattr(result, "model_dump"):
        d: dict[str, Any] = result.model_dump()
        return d
    if isinstance(result, dict):
        return result
    return {}


def _compute_field_changes(before: Any, after: Any) -> str | None:
    """Compute a JSON diff of changed fields between two records.

    Returns a JSON string mapping field names to {"old": ..., "new": ...},
    or None if no fields changed.
    """
    import json

    before_dict = _record_to_dict(before)
    after_dict = _record_to_dict(after)

    changes: dict[str, dict[str, Any]] = {}
    all_keys = set(before_dict.keys()) | set(after_dict.keys())
    for key in sorted(all_keys):
        old_val = before_dict.get(key)
        new_val = after_dict.get(key)
        if old_val != new_val:
            changes[key] = {"old": _json_safe(old_val), "new": _json_safe(new_val)}

    if not changes:
        return None
    return json.dumps(changes)


def _json_safe(val: Any) -> Any:
    """Convert a value to a JSON-serializable form."""
    if val is None or isinstance(val, (str, int, float, bool)):
        return val
    return str(val)


async def _log_audit_decision(
    audit_logger: Any,
    request: Any,
    *,
    operation: str,
    entity_name: str,
    entity_id: str | None,
    decision: str,
    matched_policy: str | None,
    policy_effect: str | None,
    user: Any | None,
    evaluation_time_us: int | None = None,
    field_changes: str | None = None,
) -> None:
    """Log an access-control decision to the audit logger."""
    from dazzle_back.runtime.audit_log import create_audit_context_from_request

    audit_ctx = create_audit_context_from_request(request)
    await audit_logger.log_decision(
        operation=operation,
        entity_name=entity_name,
        entity_id=entity_id,
        decision=decision,
        matched_policy=matched_policy,
        policy_effect=policy_effect,
        user_id=str(user.id) if user else None,
        user_email=getattr(user, "email", None) if user else None,
        user_roles=list(getattr(user, "roles", [])) if user else None,
        evaluation_time_us=evaluation_time_us,
        field_changes=field_changes,
        **audit_ctx,
    )


# =============================================================================
# Route Handler Factory
# =============================================================================


# =============================================================================
# Auth wrapper — eliminates cedar / auth / noauth triplication
# =============================================================================


def _wrap_with_auth(
    core_fn: Callable[..., Any],
    *,
    cedar_access_spec: Any | None,
    auth_dep: Callable[..., Any] | None,
    optional_auth_dep: Callable[..., Any] | None,
    require_auth_by_default: bool,
    operation: str,
    entity_name: str,
    audit_logger: Any | None,
    include_field_changes: bool = False,
    needs_pre_read: bool = False,
) -> Callable[..., Any]:
    """Wrap a core handler with cedar / auth / noauth variant selection.

    ``core_fn`` signature must be::

        async def core(id_or_none, request, *, current_user=None, existing=None) -> Any

    For create the first positional arg is *None*; for read/update/delete it
    is the resource UUID.

    ``needs_pre_read`` — if True the wrapper fetches the existing record
    *before* calling ``core_fn`` (required by Cedar update/delete for policy
    evaluation and by auth-mode update/delete for field-change diffs).
    """
    _is_create = operation == "create"

    _use_cedar = cedar_access_spec is not None and optional_auth_dep is not None

    if _use_cedar:
        assert optional_auth_dep is not None  # narrowing for mypy
        return _build_cedar_handler(
            core_fn,
            cedar_access_spec=cedar_access_spec,
            optional_auth_dep=optional_auth_dep,
            operation=operation,
            entity_name=entity_name,
            audit_logger=audit_logger,
            include_field_changes=include_field_changes,
            needs_pre_read=needs_pre_read,
            is_create=_is_create,
        )

    if require_auth_by_default and auth_dep:
        return _build_auth_handler(
            core_fn,
            auth_dep=auth_dep,
            operation=operation,
            entity_name=entity_name,
            audit_logger=audit_logger,
            include_field_changes=include_field_changes,
            needs_pre_read=needs_pre_read,
            is_create=_is_create,
        )

    return _build_noauth_handler(core_fn, is_create=_is_create)


def _build_cedar_handler(
    core_fn: Callable[..., Any],
    *,
    cedar_access_spec: Any,
    optional_auth_dep: Callable[..., Any],
    operation: str,
    entity_name: str,
    audit_logger: Any | None,
    include_field_changes: bool,
    needs_pre_read: bool,
    is_create: bool,
) -> Callable[..., Any]:
    """Build a Cedar-policy-checked handler (with or without id param)."""
    from dazzle_back.specs.auth import AccessOperationKind

    _op_kind = getattr(AccessOperationKind, operation.upper())

    async def _cedar_impl(
        id: UUID | None,
        request: Request,
        auth_context: Any,
    ) -> Any:
        from dazzle_back.runtime.access_evaluator import AccessDecision, evaluate_permission
        from dazzle_back.runtime.audit_log import measure_evaluation_time

        # Pre-read for operations that need existing record for policy eval
        existing = None
        if needs_pre_read and id is not None:
            existing = await core_fn.__self_service__.execute(operation="read", id=id)  # type: ignore[attr-defined]
            if existing is None:
                raise HTTPException(status_code=404, detail="Not found")

        user, ctx = _build_access_context(auth_context)
        record_dict = _record_to_dict(existing) if existing is not None else None
        decision: AccessDecision
        decision, eval_us = measure_evaluation_time(
            lambda: evaluate_permission(cedar_access_spec, _op_kind, record_dict, ctx)
        )

        # Create logs both allow+deny before checking; update/delete only log deny on denial
        if is_create and audit_logger:
            await _log_audit_decision(
                audit_logger,
                request,
                operation=operation,
                entity_name=entity_name,
                entity_id=None,
                decision="allow" if decision.allowed else "deny",
                matched_policy=decision.matched_policy,
                policy_effect=decision.effect,
                user=user,
                evaluation_time_us=eval_us,
            )

        if not decision.allowed:
            if not is_create and audit_logger:
                await _log_audit_decision(
                    audit_logger,
                    request,
                    operation=operation,
                    entity_name=entity_name,
                    entity_id=str(id) if id is not None else None,
                    decision="deny",
                    matched_policy=decision.matched_policy,
                    policy_effect=decision.effect,
                    user=user,
                    evaluation_time_us=eval_us,
                )
            raise HTTPException(status_code=403, detail="Forbidden")

        current_user = str(user.id) if user else None
        result = await core_fn(id, request, current_user=current_user, existing=existing)

        # Post-operation audit (create already logged above)
        if not is_create:
            _fc = None
            if include_field_changes and existing is not None:
                after = {} if operation == "delete" else result
                _fc = _compute_field_changes(existing, after)
            if audit_logger:
                await _log_audit_decision(
                    audit_logger,
                    request,
                    operation=operation,
                    entity_name=entity_name,
                    entity_id=str(id) if id is not None else _extract_result_id(result),
                    decision="allow",
                    matched_policy=decision.matched_policy,
                    policy_effect=decision.effect,
                    user=user,
                    evaluation_time_us=eval_us,
                    field_changes=_fc,
                )

        return result

    # Build properly-typed FastAPI handlers with correct signatures
    if is_create:

        async def _cedar_create(
            request: Request, auth_context: AuthContext = Depends(optional_auth_dep)
        ) -> Any:
            return await _cedar_impl(None, request, auth_context)

        _cedar_create.__annotations__ = {
            "request": Request,
            "auth_context": AuthContext,
            "return": Any,
        }
        return _cedar_create

    async def _cedar_with_id(
        id: UUID, request: Request, auth_context: AuthContext = Depends(optional_auth_dep)
    ) -> Any:
        return await _cedar_impl(id, request, auth_context)

    _cedar_with_id.__annotations__ = {
        "id": UUID,
        "request": Request,
        "auth_context": AuthContext,
        "return": Any,
    }
    return _cedar_with_id


def _build_auth_handler(
    core_fn: Callable[..., Any],
    *,
    auth_dep: Callable[..., Any],
    operation: str,
    entity_name: str,
    audit_logger: Any | None,
    include_field_changes: bool,
    needs_pre_read: bool,
    is_create: bool,
) -> Callable[..., Any]:
    """Build an authenticated handler (with or without id param)."""

    async def _auth_impl(
        id: UUID | None,
        request: Request,
        auth_context: Any,
    ) -> Any:
        user = auth_context.user
        current_user = str(user.id) if user else None

        # Pre-read for field-change diffs
        existing = None
        if needs_pre_read and include_field_changes and audit_logger and id is not None:
            existing = await core_fn.__self_service__.execute(operation="read", id=id)  # type: ignore[attr-defined]

        result = await core_fn(id, request, current_user=current_user, existing=existing)

        _fc = None
        if existing is not None:
            after = {} if operation == "delete" else result
            _fc = _compute_field_changes(existing, after)
        if audit_logger:
            await _log_audit_decision(
                audit_logger,
                request,
                operation=operation,
                entity_name=entity_name,
                entity_id=str(id) if id is not None else _extract_result_id(result),
                decision="allow",
                matched_policy="authenticated",
                policy_effect="permit",
                user=user,
                field_changes=_fc,
            )
        return result

    if is_create:

        async def _auth_create(
            request: Request, auth_context: AuthContext = Depends(auth_dep)
        ) -> Any:
            return await _auth_impl(None, request, auth_context)

        _auth_create.__annotations__ = {
            "request": Request,
            "auth_context": AuthContext,
            "return": Any,
        }
        return _auth_create

    async def _auth_with_id(
        id: UUID, request: Request, auth_context: AuthContext = Depends(auth_dep)
    ) -> Any:
        return await _auth_impl(id, request, auth_context)

    _auth_with_id.__annotations__ = {
        "id": UUID,
        "request": Request,
        "auth_context": AuthContext,
        "return": Any,
    }
    return _auth_with_id


def _build_noauth_handler(
    core_fn: Callable[..., Any],
    *,
    is_create: bool,
) -> Callable[..., Any]:
    """Build an unauthenticated handler (with or without id param)."""
    if is_create:

        async def _noauth_create(request: Request) -> Any:
            return await core_fn(None, request, current_user=None, existing=None)

        _noauth_create.__annotations__ = {"request": Request, "return": Any}
        return _noauth_create

    async def _noauth_with_id(id: UUID, request: Request) -> Any:
        return await core_fn(id, request, current_user=None, existing=None)

    _noauth_with_id.__annotations__ = {"id": UUID, "request": Request, "return": Any}
    return _noauth_with_id


def create_list_handler(
    service: Any,
    _response_schema: type[BaseModel] | None = None,
    access_spec: dict[str, Any] | None = None,
    optional_auth_dep: Callable[..., Any] | None = None,
    require_auth_by_default: bool = False,
    select_fields: list[str] | None = None,
    json_projection: list[str] | None = None,
    auto_include: list[str] | None = None,
    htmx_columns: list[dict[str, Any]] | None = None,
    htmx_detail_url: str | None = None,
    htmx_entity_name: str = "Item",
    htmx_empty_message: str = "No items found.",
    cedar_access_spec: Any | None = None,
    audit_logger: Any | None = None,
    entity_name: str = "Item",
    search_fields: list[str] | None = None,
) -> Callable[..., Any]:
    """Create a handler for list operations with optional access control.

    Args:
        service: Service instance for data operations
        _response_schema: Response schema (unused, kept for compatibility)
        access_spec: Access control specification for this entity
        optional_auth_dep: FastAPI dependency for optional auth (returns AuthContext)
        require_auth_by_default: If True, require authentication when no access_spec is defined
        select_fields: Optional field projection for SQL queries
        json_projection: Optional field names to include in JSON API responses (#360)
        auto_include: Optional relation names to auto-eager-load (prevents N+1)
        htmx_columns: Column definitions for HTMX table row rendering
        htmx_detail_url: Detail URL template for row click navigation
        htmx_entity_name: Entity name for HTMX rendering context
        htmx_empty_message: Message when no items found
        audit_logger: Optional AuditLogger for recording list access decisions
        entity_name: Entity name for audit logging
        search_fields: Optional field names for LIKE-based search (#361)
    """

    def _inject_htmx_meta(request: Request) -> None:
        """Set HTMX rendering metadata on request.state for table row fragments."""
        if htmx_columns is not None:
            request.state.htmx_columns = htmx_columns
        if htmx_detail_url is not None:
            request.state.htmx_detail_url = htmx_detail_url
        request.state.htmx_entity_name = htmx_entity_name
        request.state.htmx_empty_message = htmx_empty_message

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

            _inject_htmx_meta(request)
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
                select_fields=select_fields,
                json_projection=json_projection,
                auto_include=auto_include,
                cedar_access_spec=cedar_access_spec,
                auth_context=auth_context,
                audit_logger=audit_logger,
                entity_name=entity_name,
                user=auth_context.user if auth_context and auth_context.is_authenticated else None,
                search_fields=search_fields,
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
        _inject_htmx_meta(request)
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
            select_fields=select_fields,
            json_projection=json_projection,
            auto_include=auto_include,
            audit_logger=audit_logger,
            entity_name=entity_name,
            search_fields=search_fields,
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
    select_fields: list[str] | None = None,
    json_projection: list[str] | None = None,
    auto_include: list[str] | None = None,
    cedar_access_spec: Any | None = None,
    auth_context: Any | None = None,
    audit_logger: Any | None = None,
    entity_name: str = "Item",
    user: Any | None = None,
    search_fields: list[str] | None = None,
) -> Any:
    """Shared list handler logic for both auth and no-auth paths."""
    from dazzle_back.runtime.condition_evaluator import (
        build_visibility_filter,
        filter_records_by_condition,
    )

    # Build visibility filters
    sql_filters, post_filter = build_visibility_filter(access_spec, is_authenticated, user_id)

    # Apply row-level filters from Cedar permission rules (v0.33.0)
    if cedar_access_spec and is_authenticated and user_id:
        cedar_filters = _extract_cedar_row_filters(cedar_access_spec, user_id, auth_context)
        if cedar_filters:
            sql_filters = {**(sql_filters or {}), **cedar_filters}

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
        select_fields=select_fields,
        include=auto_include,
        search_fields=search_fields,
    )

    # Audit log the list access
    if audit_logger:
        await _log_audit_decision(
            audit_logger,
            request,
            operation="list",
            entity_name=entity_name,
            entity_id=None,
            decision="allow",
            matched_policy="authenticated" if is_authenticated else "public",
            policy_effect="permit",
            user=user,
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

    # Browser navigation: redirect to UI list page (#356)
    if _wants_html(request) and not _is_htmx_request(request):
        from starlette.responses import RedirectResponse

        _slug = entity_name.lower().replace("_", "-")
        redirect_url = f"/app/{_slug}"
        if request.query_params:
            redirect_url += f"?{request.url.query}"
        return RedirectResponse(url=redirect_url, status_code=302)

    # HTMX content negotiation: return HTML fragment for HX-Request
    if _is_htmx_request(request):
        try:
            from dazzle_back.runtime.htmx_response import HtmxDetails
            from dazzle_ui.runtime.template_renderer import render_fragment

            htmx = HtmxDetails.from_request(request)

            # Derive table_id from HX-Target (e.g. "dt-tasks-body" → "dt-tasks")
            table_id = "dt-table"
            if htmx.target and htmx.target.endswith("-body"):
                table_id = htmx.target.removesuffix("-body")

            items = result.get("items", []) if isinstance(result, dict) else []
            # Convert Pydantic models to dicts
            if items and hasattr(items[0], "model_dump"):
                items = [item.model_dump() for item in items]

            total = result.get("total", 0) if isinstance(result, dict) else 0
            table_dict = {
                "rows": items,
                "columns": request.state.htmx_columns
                if hasattr(request.state, "htmx_columns")
                else [],
                "detail_url_template": getattr(request.state, "htmx_detail_url", None),
                "entity_name": getattr(request.state, "htmx_entity_name", "Item"),
                "api_endpoint": str(request.url.path),
                "table_id": table_id,
                "sort_field": sort or "",
                "sort_dir": dir,
                "filter_values": filters,
                "page": page,
                "page_size": page_size,
                "total": total,
                "empty_message": getattr(request.state, "htmx_empty_message", "No items found."),
            }

            # Render table rows
            html = render_fragment("fragments/table_rows.html", table=table_dict)

            # Check if table uses infinite scroll mode
            pagination_mode = getattr(request.state, "htmx_pagination_mode", "pages")

            if pagination_mode == "infinite":
                # Append sentinel row for infinite scroll (triggers on revealed)
                sentinel_html = render_fragment("fragments/table_sentinel.html", table=table_dict)
                html += sentinel_html
            else:
                # Append OOB pagination so buttons stay in sync after
                # sort/filter/search/page changes
                pagination_html = render_fragment(
                    "fragments/table_pagination.html", table=table_dict
                )
                html += (
                    f'<div id="{table_id}-pagination" hx-swap-oob="true">{pagination_html}</div>'
                )

            return HTMLResponse(content=html)
        except ImportError:
            pass  # Template renderer not available, fall through to JSON

    # Apply field projection to JSON responses (#360)
    if json_projection and result and isinstance(result, dict) and "items" in result:
        allowed = set(json_projection)
        projected_items = []
        for item in result["items"]:
            if hasattr(item, "model_dump"):
                d = item.model_dump(mode="json")
            elif isinstance(item, dict):
                d = item
            else:
                projected_items.append(item)
                continue
            projected_items.append({k: v for k, v in d.items() if k in allowed})
        result = {**result, "items": projected_items}

    return result


def _render_detail_html(request: Any, result: Any, entity_name: str) -> Any:
    """Render a detail view for HTMX or browser requests.

    - HTMX request → bare HTML fragment (for partial swap)
    - Direct browser navigation → full page with app shell (#349)
    - API client (JSON) → None (let FastAPI serialize)
    """
    if not _wants_html(request):
        return None
    try:
        from dazzle_ui.runtime.template_renderer import render_fragment

        # Convert Pydantic model to dict
        if hasattr(result, "model_dump"):
            item = result.model_dump(mode="json")
        elif isinstance(result, dict):
            from fastapi.encoders import jsonable_encoder

            item = jsonable_encoder(result)
        else:
            return None

        fragment_html = render_fragment(
            "fragments/detail_fields.html",
            item=item,
            entity_name=entity_name,
        )

        if _is_htmx_request(request):
            # HTMX partial swap: return bare fragment
            return HTMLResponse(content=fragment_html)

        # Direct browser navigation: wrap fragment in a full page (#349)
        from dazzle_ui.runtime.template_renderer import get_jinja_env

        env = get_jinja_env()
        wrapper_source = (  # noqa: UP031
            "{%% extends 'layouts/single_column.html' %%}{%% block content %%}%s{%% endblock %%}"
        ) % fragment_html
        full_html = env.from_string(wrapper_source).render(
            page_title=f"{entity_name} Detail",
        )
        return HTMLResponse(content=full_html)
    except ImportError:
        return None  # Template renderer not available
    except Exception:
        return None  # Fragment not found or render error


def create_read_handler(
    service: Any,
    _response_schema: type[BaseModel] | None = None,
    auth_dep: Callable[..., Any] | None = None,
    require_auth_by_default: bool = False,
    entity_name: str = "Item",
    audit_logger: Any | None = None,
    cedar_access_spec: Any | None = None,
    optional_auth_dep: Callable[..., Any] | None = None,
    auto_include: list[str] | None = None,
) -> Callable[..., Any]:
    """Create a handler for read operations with optional Cedar-style access control."""

    async def _core(
        id: UUID, request: Request, *, current_user: str | None = None, existing: Any = None
    ) -> Any:
        result = await service.execute(operation="read", id=id, include=auto_include)
        if result is None:
            raise HTTPException(status_code=404, detail="Not found")
        html = _render_detail_html(request, result, entity_name)
        return html if html is not None else result

    # READ is special: Cedar needs the *fetched* record for policy eval, but
    # the core already does the fetch.  The generic wrapper's pre-read would
    # double-fetch.  So for Cedar-READ we inline a lightweight wrapper that
    # fetches once, evaluates, then returns.
    _use_cedar = cedar_access_spec is not None and optional_auth_dep is not None
    if _use_cedar:

        async def _read_cedar(
            id: UUID, request: Request, auth_context: AuthContext = Depends(optional_auth_dep)
        ) -> Any:
            from dazzle_back.runtime.access_evaluator import AccessDecision, evaluate_permission
            from dazzle_back.runtime.audit_log import measure_evaluation_time
            from dazzle_back.specs.auth import AccessOperationKind

            result = await service.execute(operation="read", id=id, include=auto_include)
            if result is None:
                raise HTTPException(status_code=404, detail="Not found")

            user, ctx = _build_access_context(auth_context)
            assert cedar_access_spec is not None
            decision: AccessDecision
            decision, eval_us = measure_evaluation_time(
                lambda: evaluate_permission(
                    cedar_access_spec, AccessOperationKind.READ, _record_to_dict(result), ctx
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

        _read_cedar.__annotations__ = {
            "id": UUID,
            "request": Request,
            "auth_context": AuthContext,
            "return": Any,
        }
        return _read_cedar

    # Non-cedar: use the generic wrapper (no pre-read needed)
    _core.__self_service__ = service  # type: ignore[attr-defined]
    return _wrap_with_auth(
        _core,
        cedar_access_spec=None,
        auth_dep=auth_dep,
        optional_auth_dep=optional_auth_dep,
        require_auth_by_default=require_auth_by_default,
        operation="read",
        entity_name=entity_name,
        audit_logger=audit_logger,
    )


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

    async def _core(
        _id: Any, request: Request, *, current_user: str | None = None, existing: Any = None
    ) -> Any:
        body = await _parse_request_body(request)
        data = input_schema.model_validate(body)
        result = await service.execute(operation="create", data=data)
        return _with_htmx_triggers(
            request, result, entity_name, "created", redirect_url=_build_redirect_url(result)
        )

    _core.__self_service__ = service  # type: ignore[attr-defined]
    return _wrap_with_auth(
        _core,
        cedar_access_spec=cedar_access_spec,
        auth_dep=auth_dep,
        optional_auth_dep=optional_auth_dep,
        require_auth_by_default=require_auth_by_default,
        operation="create",
        entity_name=entity_name,
        audit_logger=audit_logger,
    )


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
    include_field_changes: bool = False,
) -> Callable[..., Any]:
    """Create a handler for update operations with optional Cedar-style access control."""

    async def _core(
        id: UUID, request: Request, *, current_user: str | None = None, existing: Any = None
    ) -> Any:
        body = await _parse_request_body(request)
        data = input_schema.model_validate(body)
        kwargs: dict[str, Any] = {"operation": "update", "id": id, "data": data}
        if current_user is not None:
            kwargs["current_user"] = current_user
        result = await service.execute(**kwargs)
        if result is None:
            raise HTTPException(status_code=404, detail="Not found")
        return _with_htmx_triggers(
            request, result, entity_name, "updated", redirect_url=_htmx_current_url(request)
        )

    _core.__self_service__ = service  # type: ignore[attr-defined]
    return _wrap_with_auth(
        _core,
        cedar_access_spec=cedar_access_spec,
        auth_dep=auth_dep,
        optional_auth_dep=optional_auth_dep,
        require_auth_by_default=require_auth_by_default,
        operation="update",
        entity_name=entity_name,
        audit_logger=audit_logger,
        include_field_changes=include_field_changes,
        needs_pre_read=True,
    )


def create_delete_handler(
    service: Any,
    auth_dep: Callable[..., Any] | None = None,
    require_auth_by_default: bool = False,
    entity_name: str = "Item",
    audit_logger: Any | None = None,
    cedar_access_spec: Any | None = None,
    optional_auth_dep: Callable[..., Any] | None = None,
    include_field_changes: bool = False,
) -> Callable[..., Any]:
    """Create a handler for delete operations with optional Cedar-style access control."""

    async def _core(
        id: UUID, request: Request, *, current_user: str | None = None, existing: Any = None
    ) -> Any:
        result = await service.execute(operation="delete", id=id)
        if not result:
            raise HTTPException(status_code=404, detail="Not found")
        return _with_htmx_triggers(
            request,
            {"deleted": True},
            entity_name,
            "deleted",
            redirect_url=_htmx_parent_url(request),
        )

    _core.__self_service__ = service  # type: ignore[attr-defined]
    return _wrap_with_auth(
        _core,
        cedar_access_spec=cedar_access_spec,
        auth_dep=auth_dep,
        optional_auth_dep=optional_auth_dep,
        require_auth_by_default=require_auth_by_default,
        operation="delete",
        entity_name=entity_name,
        audit_logger=audit_logger,
        include_field_changes=include_field_changes,
        needs_pre_read=True,
    )


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
        entity_list_projections: dict[str, list[str]] | None = None,
        entity_search_fields: dict[str, list[str]] | None = None,
        entity_auto_includes: dict[str, list[str]] | None = None,
        entity_htmx_meta: dict[str, dict[str, Any]] | None = None,
        entity_audit_configs: dict[str, Any] | None = None,
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
            entity_list_projections: Optional dict mapping entity names to projected field lists
            entity_auto_includes: Optional dict mapping entity names to auto-eager-loaded relations
            entity_htmx_meta: Optional dict mapping entity names to HTMX rendering metadata
            entity_audit_configs: Optional dict of entity_name -> AuditConfig for per-entity filtering
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
        self.entity_list_projections = entity_list_projections or {}
        self.entity_search_fields = entity_search_fields or {}
        self.entity_auto_includes = entity_auto_includes or {}
        self.entity_htmx_meta = entity_htmx_meta or {}
        self.entity_audit_configs = entity_audit_configs or {}
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
        _cedar_spec = self.cedar_access_specs.get(entity_name or "")
        _audit_config = self.entity_audit_configs.get(entity_name or "")
        # Per-entity audit gate: if entity has an AuditConfig, respect its
        # `enabled` flag. Entities with Cedar access specs always get audit
        # logging (access-decision logging). Entities with no audit config
        # and no Cedar spec get no logging.
        _audit_enabled = False
        if _audit_config and getattr(_audit_config, "enabled", False):
            _audit_enabled = True
        elif _cedar_spec is not None:
            # Cedar entities always log access decisions
            _audit_enabled = True
        _audit = self.audit_logger if _audit_enabled else None
        # Pre-compute which operations this entity wants audited (empty = all)
        _audit_ops: set[str] = set()
        if _audit_config and getattr(_audit_config, "operations", None):
            _audit_ops = {str(op) for op in _audit_config.operations}
        # Check whether to capture field-level diffs for update/delete
        _include_fc = bool(_audit_config and getattr(_audit_config, "include_field_changes", False))

        def _audit_for(op: str) -> Any:
            """Return the audit logger if this operation should be audited."""
            if _audit is None:
                return None
            if _audit_ops and op not in _audit_ops:
                return None
            return _audit

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
                    audit_logger=_audit_for("create"),
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
            includes = self.entity_auto_includes.get(entity_name or "")
            handler = create_read_handler(
                service,
                model,
                auth_dep=self.auth_dep,
                require_auth_by_default=self.require_auth_by_default,
                entity_name=entity_name or "Item",
                audit_logger=_audit_for("read"),
                cedar_access_spec=_cedar_spec,
                optional_auth_dep=self.optional_auth_dep,
                auto_include=includes,
            )
            self._add_route(endpoint, handler, response_model=None)

        # GET without {id} -> LIST
        elif (
            endpoint.method == HttpMethod.GET and "{id}" not in endpoint.path
        ) or operation_kind == OperationKind.LIST:
            # Get access spec for this entity
            access_spec = self.entity_access_specs.get(entity_name or "")
            # Get field projection for this entity (from view-backed list surfaces)
            projection = self.entity_list_projections.get(entity_name or "")
            # Get search fields for this entity (from surface config)
            _search_fields = self.entity_search_fields.get(entity_name or "")
            # Get auto-include refs for this entity (prevents N+1 queries)
            includes = self.entity_auto_includes.get(entity_name or "")
            # Get HTMX rendering metadata (columns, detail URL, etc.)
            _htmx = self.entity_htmx_meta.get(entity_name or "", {})
            handler = create_list_handler(
                service,
                model,
                access_spec=access_spec,
                optional_auth_dep=self.optional_auth_dep,
                require_auth_by_default=self.require_auth_by_default,
                select_fields=projection,
                json_projection=projection,
                auto_include=includes,
                htmx_columns=_htmx.get("columns"),
                htmx_detail_url=_htmx.get("detail_url"),
                htmx_entity_name=_htmx.get("entity_name", entity_name or "Item"),
                htmx_empty_message=_htmx.get("empty_message", "No items found."),
                cedar_access_spec=_cedar_spec,
                audit_logger=_audit_for("list"),
                entity_name=entity_name or "Item",
                search_fields=_search_fields,
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
                    audit_logger=_audit_for("update"),
                    cedar_access_spec=_cedar_spec,
                    optional_auth_dep=self.optional_auth_dep,
                    include_field_changes=_include_fc,
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
                audit_logger=_audit_for("delete"),
                cedar_access_spec=_cedar_spec,
                optional_auth_dep=self.optional_auth_dep,
                include_field_changes=_include_fc,
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
        return _with_htmx_triggers(
            request, result, entity_name, "updated", redirect_url=_htmx_current_url(request)
        )

    # Delete
    @router.delete(f"{prefix}/{{id}}", tags=tags, summary=f"Delete {entity_name}")
    async def delete_item(id: UUID, request: Request) -> Any:
        result = await service.execute(operation="delete", id=id)
        if not result:
            raise HTTPException(status_code=404, detail="Not found")
        return _with_htmx_triggers(
            request,
            {"deleted": True},
            entity_name,
            "deleted",
            redirect_url=_htmx_parent_url(request),
        )

    return router
