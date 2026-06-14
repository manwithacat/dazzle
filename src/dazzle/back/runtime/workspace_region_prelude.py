"""Phase 1 of the workspace region handler — auth + identity prelude.

Extracted from ``_workspace_region_handler`` in #1057 cut 11 (v0.67.110).
Runs first for every region request:

1. Enforce ``require_auth`` (raises 401 when missing or unauthenticated).
2. Enforce workspace persona restrictions (raises 403 when the user's
   roles don't intersect ``ws_access.allow_personas``).
3. Resolve the auth subject to a DSL User entity row via email match
   (#480, #588) so downstream scope/filter predicates compare against
   the entity UUID, not the auth UUID.
4. Build the auth_ctx + filter_context downstream phases read,
   including a pre-fetch of active grants for ``has_grant()`` condition
   evaluation (v0.42.0).

Returns a ``RequestUserContext`` dataclass — named-access plumbing
into phases 2-6.
"""

import logging
from dataclasses import dataclass, field
from typing import Any

from dazzle.back.runtime.workspace_context import WorkspaceRegionContext
from dazzle.back.runtime.workspace_user import _resolve_workspace_user

logger = logging.getLogger(__name__)


@dataclass
class RequestUserContext:
    """Resolved auth + identity state for a single region request.

    Built by ``resolve_request_user_context`` from the request +
    ``WorkspaceRegionContext``. Threaded through phases 2-6 of the
    region handler so each downstream step has named access to the
    current-user state without re-resolving it.
    """

    user_id: str | None
    user_entity: dict[str, Any] | None
    auth_ctx_for_filters: Any
    filter_context: dict[str, Any] = field(default_factory=dict)


async def resolve_request_user_context(
    request: Any,
    ctx: WorkspaceRegionContext,
) -> RequestUserContext:
    """Phase 1: auth gate + identity resolution + filter-context build.

    Raises:
        HTTPException(401): when ``ctx.require_auth`` and the request
            has no authenticated user.
        HTTPException(403): when the user's roles don't satisfy
            ``ctx.ws_access.allow_personas`` (and the user isn't
            superuser).

    Returns a ``RequestUserContext`` with everything phases 2-6 need.
    """
    from fastapi import HTTPException

    # Step 1: require_auth gate (#145) — raises 401 / 403 if blocked.
    if ctx.require_auth:
        auth_ctx = None
        if ctx.auth_middleware:
            try:
                auth_ctx = ctx.auth_middleware.get_auth_context(request)
            except Exception:
                logger.warning("Failed to get auth context for region", exc_info=True)
        if not (auth_ctx and auth_ctx.is_authenticated):
            raise HTTPException(status_code=401, detail="Authentication required")

        # Workspace persona gate. Roles use "role_" prefix; persona IDs don't.
        if ctx.ws_access and ctx.ws_access.allow_personas and auth_ctx:
            is_super = auth_ctx.user and auth_ctx.user.is_superuser
            normalized_roles = [r.removeprefix("role_") for r in auth_ctx.roles]
            if not is_super and not any(
                r in ctx.ws_access.allow_personas for r in normalized_roles
            ):
                raise HTTPException(status_code=403, detail="Workspace access denied")

    # Step 2: resolve current user ID for filter expressions
    # (e.g. `reviewer == current_user`). Always attempt resolution
    # when middleware is available, even in test mode where
    # require_auth is False — the user may still be authenticated (#483).
    user_id, user_entity = await _resolve_workspace_user(
        request, ctx.auth_middleware, ctx.repositories, ctx.user_entity_name
    )

    # Step 3: build auth_context for `_extract_condition_filters`
    # (shared with entity scope path). Splice the resolved User
    # entity's attrs into the auth context's preferences so
    # `current_user.<attr>` expressions resolve.
    auth_ctx_for_filters: Any = None
    if ctx.auth_middleware:
        try:
            auth_ctx_for_filters = ctx.auth_middleware.get_auth_context(request)
            if auth_ctx_for_filters and user_entity:
                prefs = getattr(auth_ctx_for_filters, "preferences", None)
                if prefs is None:
                    auth_ctx_for_filters.preferences = {}
                    prefs = auth_ctx_for_filters.preferences
                from uuid import UUID as _UUID

                for k, v in user_entity.items():
                    if k not in prefs and v is not None:
                        prefs[k] = str(v) if isinstance(v, _UUID) else v
                if user_id and "entity_id" not in prefs:
                    prefs["entity_id"] = user_id
        except Exception:
            logger.warning("Failed to get auth context for filter resolution", exc_info=True)

    # Step 4: build filter context for attention signals + grant
    # evaluation. Carries the resolved entity, the entity id, and
    # the context_id selector (v0.38.0).
    filter_context: dict[str, Any] = {}
    if user_id:
        filter_context["current_user_id"] = user_id
    if user_entity:
        filter_context["current_user_entity"] = user_entity
    # #1394: expose the host-resolved tenant for `current_tenant[.attr]` display
    # gates (e.g. `visible_when: current_tenant.kind == trust`).
    from dazzle.back.runtime.tenant_render_context import inject_current_tenant

    inject_current_tenant(filter_context, request)
    context_id = request.query_params.get("context_id")
    if context_id:
        filter_context["current_context"] = context_id

    # Step 5: pre-fetch active grants for `has_grant()` condition
    # evaluation (v0.42.0). Best-effort — grant tables may not
    # exist when no grant_schemas are defined.
    if user_id:
        try:
            from dazzle.back.runtime.grant_store import GrantStore

            db_mgr = None
            if ctx.repositories:
                for repo in ctx.repositories.values():
                    db_mgr = getattr(repo, "db", None)
                    if db_mgr:
                        break
            if db_mgr:
                from uuid import UUID as _UUID

                # #1331: lease a pooled connection scoped to this read. The pool
                # rolls back on return, so this grant lookup (run on every
                # workspace render) never parks the connection idle-in-transaction
                # holding ACCESS SHARE on _grants — the bug the shared
                # get_persistent_connection() caused.
                with db_mgr.connection() as grant_conn:
                    grant_store = GrantStore(grant_conn)
                    active_grants = grant_store.list_grants(
                        principal_id=_UUID(user_id), status="active"
                    )
                filter_context["active_grants"] = active_grants
            else:
                filter_context["active_grants"] = []
        except Exception:
            logger.warning("Could not pre-fetch grants", exc_info=True)
            filter_context["active_grants"] = []

    return RequestUserContext(
        user_id=user_id,
        user_entity=user_entity,
        auth_ctx_for_filters=auth_ctx_for_filters,
        filter_context=filter_context,
    )
