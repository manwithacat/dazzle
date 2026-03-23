"""
Grant management API routes.

Exposes CRUD endpoints for runtime RBAC grants so that ``has_grant()``
transition guards become reachable.  Mounted at ``/api/grants/*``.

Authorization: only roles listed in the matching ``GrantSchemaSpec.granted_by``
field may create or manage grants.
"""

from __future__ import annotations

from typing import Any

from dazzle_back.runtime._fastapi_compat import (
    FASTAPI_AVAILABLE,
    APIRouter,
    Depends,
    HTTPException,
    Query,
)
from dazzle_back.runtime.auth import AuthContext


def create_grant_routes(
    *,
    conn_factory: Any,
    appspec: Any,
    auth_dep: Any = None,
) -> APIRouter:
    """Create grant management routes.

    Args:
        conn_factory: Callable returning a sqlite3 Connection for GrantStore.
        appspec: The AppSpec for looking up GrantSchemaSpec definitions.
        auth_dep: FastAPI auth dependency that requires authentication.

    Returns:
        FastAPI router with grant endpoints.
    """
    if not FASTAPI_AVAILABLE:
        raise RuntimeError("FastAPI is required for grant routes")

    router = APIRouter(prefix="/api/grants", tags=["Grants"])

    def _get_store() -> Any:
        from dazzle_back.runtime.grant_store import GrantStore

        return GrantStore(conn_factory(), placeholder="%s")

    def _get_user_id(auth_context: AuthContext) -> str:
        if not auth_context or not auth_context.is_authenticated:
            raise HTTPException(status_code=401, detail="Authentication required")
        uid = getattr(auth_context, "user_id", None)
        if not uid:
            raise HTTPException(status_code=401, detail="Authentication required")
        return str(uid)

    def _get_user_roles(auth_context: AuthContext) -> set[str]:
        user = getattr(auth_context, "user", None)
        if not user:
            return set()
        roles: set[str] = set()
        for r in getattr(user, "roles", []):
            roles.add(r if isinstance(r, str) else getattr(r, "name", str(r)))
        return roles

    def _check_granted_by(schema_name: str, user_roles: set[str]) -> None:
        """Verify the caller has a role listed in granted_by for the schema."""
        schema = appspec.get_grant_schema(schema_name) if appspec else None
        if schema is None:
            raise HTTPException(status_code=404, detail=f"Grant schema '{schema_name}' not found")
        allowed = set(schema.granted_by) if schema.granted_by else set()
        if not allowed.intersection(user_roles):
            raise HTTPException(
                status_code=403,
                detail=f"Your role is not authorized to manage grants for '{schema_name}'",
            )

    if auth_dep is not None:

        @router.get("", summary="List grants")  # type: ignore[misc,untyped-decorator,unused-ignore]
        async def list_grants(
            auth_context: AuthContext = Depends(auth_dep),
            scope_entity: str | None = Query(None),
            scope_id: str | None = Query(None),
            principal_id: str | None = Query(None),
            status: str | None = Query(None),
        ) -> dict[str, Any]:
            _get_user_id(auth_context)
            store = _get_store()
            grants = store.list_grants(
                scope_entity=scope_entity,
                scope_id=scope_id,
                principal_id=principal_id,
                status=status,
            )
            return {"grants": grants}

        @router.post("", summary="Create a grant", status_code=201)  # type: ignore[misc,untyped-decorator,unused-ignore]
        async def create_grant(
            body: dict[str, Any],
            auth_context: AuthContext = Depends(auth_dep),
        ) -> dict[str, Any]:
            user_id = _get_user_id(auth_context)
            user_roles = _get_user_roles(auth_context)

            schema_name = body.get("schema_name", "")
            relation = body.get("relation", "")
            principal_id = body.get("principal_id", "")
            scope_entity = body.get("scope_entity", "")
            scope_id = body.get("scope_id", "")

            if not all([schema_name, relation, principal_id, scope_entity, scope_id]):
                raise HTTPException(
                    status_code=422,
                    detail="Required fields: schema_name, relation, principal_id, scope_entity, scope_id",
                )

            _check_granted_by(schema_name, user_roles)

            # Look up approval mode from schema
            schema = appspec.get_grant_schema(schema_name)
            approval_mode = getattr(schema, "approval", "auto") if schema else "auto"

            store = _get_store()
            grant = store.create_grant(
                schema_name=schema_name,
                relation=relation,
                principal_id=principal_id,
                scope_entity=scope_entity,
                scope_id=scope_id,
                granted_by_id=user_id,
                approval_mode=approval_mode,
                expires_at=body.get("expires_at"),
            )
            return {"grant": grant}

        @router.post("/{grant_id}/approve", summary="Approve a pending grant")  # type: ignore[misc,untyped-decorator,unused-ignore]
        async def approve_grant(
            grant_id: str,
            auth_context: AuthContext = Depends(auth_dep),
        ) -> dict[str, Any]:
            user_id = _get_user_id(auth_context)
            store = _get_store()
            try:
                grant = store._get_grant(grant_id)
            except ValueError:
                raise HTTPException(status_code=404, detail="Grant not found")

            user_roles = _get_user_roles(auth_context)
            _check_granted_by(grant["schema_name"], user_roles)

            try:
                result = store.approve_grant(grant_id, user_id)
            except ValueError as e:
                raise HTTPException(status_code=422, detail=str(e))
            return {"grant": result}

        @router.post("/{grant_id}/reject", summary="Reject a pending grant")  # type: ignore[misc,untyped-decorator,unused-ignore]
        async def reject_grant(
            grant_id: str,
            auth_context: AuthContext = Depends(auth_dep),
        ) -> dict[str, Any]:
            user_id = _get_user_id(auth_context)
            store = _get_store()
            try:
                grant = store._get_grant(grant_id)
            except ValueError:
                raise HTTPException(status_code=404, detail="Grant not found")

            user_roles = _get_user_roles(auth_context)
            _check_granted_by(grant["schema_name"], user_roles)

            try:
                result = store.reject_grant(grant_id, user_id)
            except ValueError as e:
                raise HTTPException(status_code=422, detail=str(e))
            return {"grant": result}

        @router.delete("/{grant_id}", summary="Revoke an active grant")  # type: ignore[misc,untyped-decorator,unused-ignore]
        async def revoke_grant(
            grant_id: str,
            auth_context: AuthContext = Depends(auth_dep),
        ) -> dict[str, Any]:
            user_id = _get_user_id(auth_context)
            store = _get_store()
            try:
                grant = store._get_grant(grant_id)
            except ValueError:
                raise HTTPException(status_code=404, detail="Grant not found")

            user_roles = _get_user_roles(auth_context)
            _check_granted_by(grant["schema_name"], user_roles)

            try:
                result = store.revoke_grant(grant_id, user_id)
            except ValueError as e:
                raise HTTPException(status_code=422, detail=str(e))
            return {"grant": result}

    return router
