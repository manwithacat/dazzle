"""
Grant management API routes.

Exposes CRUD endpoints for runtime RBAC grants so that ``has_grant()``
transition guards become reachable.  Mounted at ``/_dazzle/grants/*``.

Authorization: only roles listed in the relation's ``granted_by`` may create,
cancel or revoke grants. When the relation declares ``approved_by``, only those
roles may approve or reject a pending grant (otherwise ``granted_by`` decides).

Declared relation clauses enforced on create (ADR-0057, flense ship Q):

- ``expiry: required`` — ``expires_at`` must be supplied; ``expiry: none`` —
  ``expires_at`` must not be supplied; ``expiry: optional`` — either.
- ``max_duration: <Nd|Nh|Nm|Ns>`` (or ``param("…")``) — ``expires_at`` must be
  supplied and no later than ``now + max_duration``. There is no implicit
  default expiry: the grammar does not declare one, so a missing value is
  rejected rather than invented.
- ``confirmation: "…"`` — the create body must carry ``"confirmed": true``
  (the acknowledgement of the declared confirmation text).

``principal_label`` and ``revoke_verb`` are presentation-only and are not read
here (no grant UI renders them yet).
"""

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from dazzle.core import ir
from dazzle.core.dsl_parser_impl._lexical import short_duration_seconds
from dazzle.core.ir.grants import GrantExpiryMode
from dazzle.core.ir.params import ParamRef
from dazzle.http.runtime.auth import AuthContext
from dazzle.http.runtime.param_store import resolve_value


def _parse_expires_at(raw: Any) -> datetime | None:
    """Parse a request ``expires_at`` (ISO-8601 string or datetime) to aware UTC.

    A naive timestamp is read as UTC. Raises 422 on an unparseable value.
    """
    if raw is None or raw == "":
        return None
    if isinstance(raw, datetime):
        parsed = raw
    elif isinstance(raw, str):
        try:
            parsed = datetime.fromisoformat(raw)
        except ValueError:
            raise HTTPException(
                status_code=422,
                detail=f"Invalid expires_at '{raw}': expected an ISO-8601 timestamp",
            )
    else:
        raise HTTPException(
            status_code=422, detail="Invalid expires_at: expected an ISO-8601 timestamp"
        )
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed


def _max_duration_seconds(rel: Any, param_resolver: Any = None) -> int | None:
    """Resolve a relation's ``max_duration`` (literal or ``param()``) to seconds.

    Returns ``None`` when the relation declares no cap. A declared cap that does
    not resolve to a ``30s``/``5m``/``2h``/``7d`` duration fails closed (500):
    the declaration exists, so it must not silently stop limiting grants.
    """
    raw = getattr(rel, "max_duration", None)
    if raw is None:
        return None
    value: Any = raw
    if isinstance(raw, ParamRef):
        try:
            value = resolve_value(raw, param_resolver)
        except KeyError:
            value = raw.default
    seconds = short_duration_seconds(str(value)) if value not in (None, "") else None
    if seconds is None:
        raise HTTPException(
            status_code=500,
            detail=(
                f"Grant relation '{rel.name}' declares max_duration {value!r}, which is not "
                "a duration like '30d' — refusing to create an uncapped grant"
            ),
        )
    return seconds


def resolve_grant_expiry(
    rel: Any,
    raw_expires_at: Any,
    *,
    now: datetime | None = None,
    param_resolver: Any = None,
) -> datetime | None:
    """Apply a relation's declared ``expiry`` / ``max_duration`` to a create request.

    Returns the ``expires_at`` to store, or raises ``HTTPException(422)`` when
    the request violates the declaration.
    """
    now = now or datetime.now(UTC)
    expires_at = _parse_expires_at(raw_expires_at)
    mode = GrantExpiryMode(str(getattr(rel, "expiry", GrantExpiryMode.REQUIRED)))

    if mode == GrantExpiryMode.NONE:
        if expires_at is not None:
            raise HTTPException(
                status_code=422,
                detail=f"Relation '{rel.name}' declares 'expiry: none'; expires_at is not allowed",
            )
        return None

    max_seconds = _max_duration_seconds(rel, param_resolver)

    if expires_at is None:
        if mode == GrantExpiryMode.REQUIRED:
            raise HTTPException(
                status_code=422,
                detail=f"Relation '{rel.name}' declares 'expiry: required'; expires_at is required",
            )
        if max_seconds is not None:
            raise HTTPException(
                status_code=422,
                detail=(
                    f"Relation '{rel.name}' declares 'max_duration: {rel.max_duration}'; "
                    "expires_at is required"
                ),
            )
        return None

    if expires_at <= now:
        raise HTTPException(status_code=422, detail="expires_at must be in the future")
    if max_seconds is not None and expires_at > now + timedelta(seconds=max_seconds):
        raise HTTPException(
            status_code=422,
            detail=(
                f"expires_at exceeds the declared max_duration for relation '{rel.name}' "
                f"(latest allowed: {(now + timedelta(seconds=max_seconds)).isoformat()})"
            ),
        )
    return expires_at


def require_grant_confirmation(rel: Any, body: dict[str, Any]) -> None:
    """Reject a create that omits ``"confirmed": true`` on a relation declaring ``confirmation:``."""
    text = getattr(rel, "confirmation", None)
    if text and body.get("confirmed") is not True:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Relation '{rel.name}' requires confirmation (\"{text}\"); "
                'resend with "confirmed": true'
            ),
        )


def create_grant_routes(
    *,
    db_manager: Any,
    appspec: ir.AppSpec,
    auth_dep: Any = None,
) -> APIRouter:
    """Create grant management routes.

    Args:
        db_manager: Database backend exposing ``.connection()`` (a context
            manager that leases a pooled connection and rolls back on return).
        appspec: The AppSpec for looking up GrantSchemaSpec definitions.
        auth_dep: FastAPI auth dependency that requires authentication.

    Returns:
        FastAPI router with grant endpoints.
    """
    router = APIRouter(prefix="/_dazzle/grants", tags=["Grants"])

    @contextmanager
    def _store() -> Iterator[Any]:
        """Lease a pooled connection for the duration of one grant operation.

        #1331: GrantStore must run on a short-lived pooled connection, not the
        shared app-lifetime get_persistent_connection(). Its writes commit
        explicitly (and persist); any read that didn't commit is rolled back by
        the pool on return, so the connection never parks idle-in-transaction
        holding ACCESS SHARE on _grants. A single lease spans the whole handler,
        so read-then-write routes (approve/reject/cancel/revoke) stay on one
        connection.
        """
        from dazzle.http.runtime.grant_store import GrantStore

        with db_manager.connection() as conn:
            yield GrantStore(conn)

    def _get_user_id(auth_context: AuthContext) -> str:
        if not auth_context or not auth_context.is_authenticated:
            raise HTTPException(status_code=401, detail="Authentication required")
        uid = getattr(auth_context, "user_id", None)
        if not uid:
            raise HTTPException(status_code=401, detail="Authentication required")
        return str(uid)

    def _parse_uuid(value: str, field_name: str) -> UUID:
        try:
            return UUID(value)
        except (ValueError, AttributeError):
            raise HTTPException(status_code=422, detail=f"Invalid UUID for {field_name}")

    def _get_user_roles(auth_context: AuthContext) -> set[str]:
        user = getattr(auth_context, "user", None)
        if not user:
            return set()
        roles: set[str] = set()
        for r in getattr(user, "roles", []):
            roles.add(r if isinstance(r, str) else getattr(r, "name", str(r)))
        return roles

    def _extract_roles(expr: Any) -> set[str]:
        """Extract role names from a ConditionExpr tree."""
        roles: set[str] = set()
        if expr is None:
            return roles
        if getattr(expr, "role_check", None):
            roles.add(expr.role_check.role_name)
        if getattr(expr, "left", None):
            roles |= _extract_roles(expr.left)
        if getattr(expr, "right", None):
            roles |= _extract_roles(expr.right)
        return roles

    def _get_relation_spec(schema_name: str, relation_name: str) -> Any:
        """Look up a GrantRelationSpec by schema and relation name."""
        from dazzle.http.runtime.http_errors import require_found

        schema = require_found(
            appspec.get_grant_schema(schema_name) if appspec else None,
            f"Grant schema '{schema_name}' not found",
        )
        rel = require_found(
            next((r for r in schema.relations if r.name == relation_name), None),
            f"Relation '{relation_name}' not found in grant schema '{schema_name}'",
        )
        return rel

    def _check_approved_by(schema_name: str, relation_name: str, user_roles: set[str]) -> None:
        """Verify the caller may decide (approve/reject) a pending grant.

        A relation's ``approved_by`` names the deciding roles; without it the
        ``granted_by`` roles decide (the pre-ship-Q behaviour).
        """
        rel = _get_relation_spec(schema_name, relation_name)
        if getattr(rel, "approved_by", None) is None:
            _check_granted_by(schema_name, relation_name, user_roles)
            return
        if not _extract_roles(rel.approved_by).intersection(user_roles):
            raise HTTPException(
                status_code=403,
                detail=(
                    f"Your role is not authorized to approve grants for "
                    f"'{schema_name}.{relation_name}' (approved_by)"
                ),
            )

    def _check_granted_by(schema_name: str, relation_name: str, user_roles: set[str]) -> None:
        """Verify the caller has a role listed in granted_by for the relation."""
        rel = _get_relation_spec(schema_name, relation_name)
        allowed = _extract_roles(rel.granted_by)
        if not allowed.intersection(user_roles):
            raise HTTPException(
                status_code=403,
                detail=f"Your role is not authorized to manage grants for '{schema_name}'",
            )

    if auth_dep is not None:

        @router.get("", summary="List grants")
        async def list_grants(
            auth_context: AuthContext = Depends(auth_dep),
            scope_entity: str | None = Query(None),
            scope_id: str | None = Query(None),
            principal_id: str | None = Query(None),
            status: str | None = Query(None),
        ) -> dict[str, Any]:
            _get_user_id(auth_context)
            with _store() as store:
                grants = store.list_grants(
                    scope_entity=scope_entity,
                    scope_id=_parse_uuid(scope_id, "scope_id") if scope_id else None,
                    principal_id=(
                        _parse_uuid(principal_id, "principal_id") if principal_id else None
                    ),
                    status=status,
                )
            return {"grants": grants}

        @router.post("", summary="Create a grant", status_code=201)
        async def create_grant(
            request: Request,
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

            _check_granted_by(schema_name, relation, user_roles)

            # Look up approval mode from relation spec
            rel_spec = _get_relation_spec(schema_name, relation)
            approval_mode = str(rel_spec.approval) if rel_spec.approval else "auto"
            require_grant_confirmation(rel_spec, body)
            expires_at = resolve_grant_expiry(
                rel_spec,
                body.get("expires_at"),
                param_resolver=getattr(request.app.state, "param_resolver", None),
            )

            with _store() as store:
                grant = store.create_grant(
                    schema_name=schema_name,
                    relation=relation,
                    principal_id=principal_id,
                    scope_entity=scope_entity,
                    scope_id=scope_id,
                    granted_by_id=user_id,
                    approval_mode=approval_mode,
                    expires_at=expires_at,
                )
            return {"grant": grant}

        @router.post("/{grant_id}/approve", summary="Approve a pending grant")
        async def approve_grant(
            grant_id: str,
            auth_context: AuthContext = Depends(auth_dep),
        ) -> dict[str, Any]:
            user_id = _get_user_id(auth_context)
            with _store() as store:
                try:
                    grant = store._get_grant(grant_id)
                except ValueError:
                    raise HTTPException(status_code=404, detail="Grant not found")

                user_roles = _get_user_roles(auth_context)
                _check_approved_by(grant["schema_name"], grant["relation"], user_roles)

                try:
                    result = store.approve_grant(grant_id, user_id)
                except ValueError as e:
                    raise HTTPException(status_code=422, detail=str(e))
            return {"grant": result}

        @router.post("/{grant_id}/reject", summary="Reject a pending grant")
        async def reject_grant(
            grant_id: str,
            auth_context: AuthContext = Depends(auth_dep),
        ) -> dict[str, Any]:
            user_id = _get_user_id(auth_context)
            with _store() as store:
                try:
                    grant = store._get_grant(grant_id)
                except ValueError:
                    raise HTTPException(status_code=404, detail="Grant not found")

                user_roles = _get_user_roles(auth_context)
                _check_approved_by(grant["schema_name"], grant["relation"], user_roles)

                try:
                    result = store.reject_grant(grant_id, user_id)
                except ValueError as e:
                    raise HTTPException(status_code=422, detail=str(e))
            return {"grant": result}

        @router.post("/{grant_id}/cancel", summary="Cancel a pending grant")
        async def cancel_grant(
            grant_id: str,
            auth_context: AuthContext = Depends(auth_dep),
        ) -> dict[str, Any]:
            user_id = _get_user_id(auth_context)
            parsed_id = _parse_uuid(grant_id, "grant_id")
            with _store() as store:
                try:
                    grant = store._get_grant(parsed_id)
                except ValueError:
                    raise HTTPException(status_code=404, detail="Grant not found")

                user_roles = _get_user_roles(auth_context)
                _check_granted_by(grant["schema_name"], grant["relation"], user_roles)

                try:
                    result = store.cancel_grant(parsed_id, UUID(user_id))
                except ValueError as e:
                    raise HTTPException(status_code=422, detail=str(e))
            return {"grant": result}

        @router.delete("/{grant_id}", summary="Revoke an active grant")
        async def revoke_grant(
            grant_id: str,
            auth_context: AuthContext = Depends(auth_dep),
        ) -> dict[str, Any]:
            user_id = _get_user_id(auth_context)
            with _store() as store:
                try:
                    grant = store._get_grant(grant_id)
                except ValueError:
                    raise HTTPException(status_code=404, detail="Grant not found")

                user_roles = _get_user_roles(auth_context)
                _check_granted_by(grant["schema_name"], grant["relation"], user_roles)

                try:
                    result = store.revoke_grant(grant_id, user_id)
                except ValueError as e:
                    raise HTTPException(status_code=422, detail=str(e))
            return {"grant": result}

    return router
