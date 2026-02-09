"""Tests for row-level access enforcement in route handlers.

Validates that Cedar-style access evaluation is wired into read/create/update/delete
handlers, including 404 vs 403 semantics for enumeration prevention.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest

pytest.importorskip("fastapi")

from pydantic import BaseModel

from dazzle_back.runtime.route_generator import (
    create_create_handler,
    create_delete_handler,
    create_read_handler,
    create_update_handler,
)
from dazzle_back.specs.auth import (
    AccessConditionSpec,
    AccessOperationKind,
    AccessPolicyEffect,
    EntityAccessSpec,
    PermissionRuleSpec,
)

# =============================================================================
# Helpers
# =============================================================================


class TaskModel(BaseModel):
    id: str
    title: str
    owner_id: str
    status: str = "active"


class TaskUpdate(BaseModel):
    title: str | None = None


def _make_service(records: dict[str, dict] | None = None):
    """Create a mock service that returns given records."""
    records = records or {}
    service = AsyncMock()

    async def _execute(operation="read", **kwargs):
        if operation == "read":
            record_id = str(kwargs.get("id", ""))
            rec = records.get(record_id)
            if rec is None:
                return None
            return TaskModel(**rec)
        elif operation == "create":
            return TaskModel(id=str(uuid4()), title="new", owner_id="user-1")
        elif operation == "update":
            record_id = str(kwargs.get("id", ""))
            rec = records.get(record_id)
            if rec is None:
                return None
            return TaskModel(**rec)
        elif operation == "delete":
            return kwargs.get("id") in [UUID(k) for k in records]
        return None

    service.execute = AsyncMock(side_effect=_execute)
    return service


def _make_auth_context(user_id="user-1", roles=None, is_superuser=False):
    """Create a mock AuthContext."""
    ctx = MagicMock()
    ctx.is_authenticated = user_id is not None
    user = MagicMock()
    user.id = user_id
    user.roles = roles or []
    user.is_superuser = is_superuser
    user.email = f"{user_id}@test.com" if user_id else None
    ctx.user = user if user_id else None
    return ctx


def _make_optional_auth_dep(auth_context):
    """Create a mock optional auth dependency."""

    async def dep(request):
        return auth_context

    return dep


def _make_request(method="GET", path="/tasks"):
    request = MagicMock()
    request.headers = {"content-type": "application/json"}
    request.client = MagicMock()
    request.client.host = "127.0.0.1"
    request.url = MagicMock()
    request.url.path = path
    request.method = method
    request.json = AsyncMock(return_value={"title": "updated"})
    return request


def _permit_rule(op, condition=None):
    return PermissionRuleSpec(
        operation=op,
        effect=AccessPolicyEffect.PERMIT,
        condition=condition,
    )


def _forbid_rule(op, condition=None):
    return PermissionRuleSpec(
        operation=op,
        effect=AccessPolicyEffect.FORBID,
        condition=condition,
    )


def _role_check(role_name):
    return AccessConditionSpec(kind="role_check", role_name=role_name)


def _owner_check():
    from dazzle_back.specs.auth import AccessComparisonKind

    return AccessConditionSpec(
        kind="comparison",
        field="owner_id",
        comparison_op=AccessComparisonKind.EQUALS,
        value="current_user",
    )


# =============================================================================
# READ handler — 404 on denial (enumeration prevention)
# =============================================================================


class TestReadHandlerCedar:
    @pytest.mark.asyncio
    async def test_read_allowed_by_cedar(self) -> None:
        """User with correct role can read."""
        record_id = str(uuid4())
        service = _make_service(
            {record_id: {"id": record_id, "title": "Test", "owner_id": "user-1"}}
        )
        auth_ctx = _make_auth_context(roles=["admin"])
        spec = EntityAccessSpec(
            permissions=[_permit_rule(AccessOperationKind.READ, _role_check("admin"))]
        )

        handler = create_read_handler(
            service,
            cedar_access_spec=spec,
            optional_auth_dep=_make_optional_auth_dep(auth_ctx),
            entity_name="Task",
        )

        request = _make_request()
        result = await handler(UUID(record_id), request, auth_ctx)
        assert result.title == "Test"

    @pytest.mark.asyncio
    async def test_read_denied_returns_404(self) -> None:
        """User without permission gets 404 (not 403) to prevent enumeration."""
        from fastapi import HTTPException

        record_id = str(uuid4())
        service = _make_service(
            {record_id: {"id": record_id, "title": "Secret", "owner_id": "user-2"}}
        )
        auth_ctx = _make_auth_context(user_id="user-1", roles=["viewer"])
        spec = EntityAccessSpec(
            permissions=[_permit_rule(AccessOperationKind.READ, _owner_check())]
        )

        handler = create_read_handler(
            service,
            cedar_access_spec=spec,
            optional_auth_dep=_make_optional_auth_dep(auth_ctx),
            entity_name="Task",
        )

        request = _make_request()
        with pytest.raises(HTTPException) as exc_info:
            await handler(UUID(record_id), request, auth_ctx)
        assert exc_info.value.status_code == 404  # NOT 403


# =============================================================================
# CREATE handler — Cedar evaluation
# =============================================================================


class TestCreateHandlerCedar:
    @pytest.mark.asyncio
    async def test_create_allowed_by_cedar(self) -> None:
        service = _make_service()
        auth_ctx = _make_auth_context(roles=["editor"])
        spec = EntityAccessSpec(
            permissions=[_permit_rule(AccessOperationKind.CREATE, _role_check("editor"))]
        )

        handler = create_create_handler(
            service,
            TaskUpdate,
            cedar_access_spec=spec,
            optional_auth_dep=_make_optional_auth_dep(auth_ctx),
            entity_name="Task",
        )

        request = _make_request(method="POST")
        result = await handler(request, auth_ctx)
        assert result is not None

    @pytest.mark.asyncio
    async def test_create_denied_returns_403(self) -> None:
        from fastapi import HTTPException

        service = _make_service()
        auth_ctx = _make_auth_context(roles=["viewer"])
        spec = EntityAccessSpec(
            permissions=[_permit_rule(AccessOperationKind.CREATE, _role_check("editor"))]
        )

        handler = create_create_handler(
            service,
            TaskUpdate,
            cedar_access_spec=spec,
            optional_auth_dep=_make_optional_auth_dep(auth_ctx),
            entity_name="Task",
        )

        request = _make_request(method="POST")
        with pytest.raises(HTTPException) as exc_info:
            await handler(request, auth_ctx)
        assert exc_info.value.status_code == 403


# =============================================================================
# UPDATE handler — Cedar evaluation against existing record
# =============================================================================


class TestUpdateHandlerCedar:
    @pytest.mark.asyncio
    async def test_update_allowed_by_owner(self) -> None:
        record_id = str(uuid4())
        service = _make_service(
            {record_id: {"id": record_id, "title": "Test", "owner_id": "user-1"}}
        )
        auth_ctx = _make_auth_context(user_id="user-1")
        spec = EntityAccessSpec(
            permissions=[_permit_rule(AccessOperationKind.UPDATE, _owner_check())]
        )

        handler = create_update_handler(
            service,
            TaskUpdate,
            cedar_access_spec=spec,
            optional_auth_dep=_make_optional_auth_dep(auth_ctx),
            entity_name="Task",
        )

        request = _make_request(method="PUT")
        result = await handler(UUID(record_id), request, auth_ctx)
        assert result is not None

    @pytest.mark.asyncio
    async def test_update_denied_returns_403(self) -> None:
        from fastapi import HTTPException

        record_id = str(uuid4())
        service = _make_service(
            {record_id: {"id": record_id, "title": "Test", "owner_id": "user-2"}}
        )
        auth_ctx = _make_auth_context(user_id="user-1")
        spec = EntityAccessSpec(
            permissions=[_permit_rule(AccessOperationKind.UPDATE, _owner_check())]
        )

        handler = create_update_handler(
            service,
            TaskUpdate,
            cedar_access_spec=spec,
            optional_auth_dep=_make_optional_auth_dep(auth_ctx),
            entity_name="Task",
        )

        request = _make_request(method="PUT")
        with pytest.raises(HTTPException) as exc_info:
            await handler(UUID(record_id), request, auth_ctx)
        assert exc_info.value.status_code == 403


# =============================================================================
# DELETE handler — Cedar evaluation against existing record
# =============================================================================


class TestDeleteHandlerCedar:
    @pytest.mark.asyncio
    async def test_delete_allowed_by_role(self) -> None:
        record_id = str(uuid4())
        service = _make_service(
            {record_id: {"id": record_id, "title": "Test", "owner_id": "user-1"}}
        )
        auth_ctx = _make_auth_context(roles=["admin"])
        spec = EntityAccessSpec(
            permissions=[_permit_rule(AccessOperationKind.DELETE, _role_check("admin"))]
        )

        handler = create_delete_handler(
            service,
            cedar_access_spec=spec,
            optional_auth_dep=_make_optional_auth_dep(auth_ctx),
            entity_name="Task",
        )

        request = _make_request(method="DELETE")
        # Note: the delete handler returns htmx triggers dict
        result = await handler(UUID(record_id), request, auth_ctx)
        assert result is not None

    @pytest.mark.asyncio
    async def test_delete_denied_returns_403(self) -> None:
        from fastapi import HTTPException

        record_id = str(uuid4())
        service = _make_service(
            {record_id: {"id": record_id, "title": "Test", "owner_id": "user-1"}}
        )
        auth_ctx = _make_auth_context(roles=["viewer"])
        spec = EntityAccessSpec(
            permissions=[_permit_rule(AccessOperationKind.DELETE, _role_check("admin"))]
        )

        handler = create_delete_handler(
            service,
            cedar_access_spec=spec,
            optional_auth_dep=_make_optional_auth_dep(auth_ctx),
            entity_name="Task",
        )

        request = _make_request(method="DELETE")
        with pytest.raises(HTTPException) as exc_info:
            await handler(UUID(record_id), request, auth_ctx)
        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_delete_nonexistent_returns_404(self) -> None:
        from fastapi import HTTPException

        service = _make_service({})
        auth_ctx = _make_auth_context(roles=["admin"])
        spec = EntityAccessSpec(
            permissions=[_permit_rule(AccessOperationKind.DELETE, _role_check("admin"))]
        )

        handler = create_delete_handler(
            service,
            cedar_access_spec=spec,
            optional_auth_dep=_make_optional_auth_dep(auth_ctx),
            entity_name="Task",
        )

        request = _make_request(method="DELETE")
        with pytest.raises(HTTPException) as exc_info:
            await handler(uuid4(), request, auth_ctx)
        assert exc_info.value.status_code == 404


# =============================================================================
# Forbid takes precedence in handlers
# =============================================================================


class TestForbidInHandlers:
    @pytest.mark.asyncio
    async def test_forbid_overrides_permit_in_delete(self) -> None:
        """Even admin with permit rule is blocked by forbid rule."""
        from fastapi import HTTPException

        record_id = str(uuid4())
        service = _make_service(
            {record_id: {"id": record_id, "title": "Test", "owner_id": "user-1"}}
        )
        auth_ctx = _make_auth_context(roles=["admin", "intern"])
        spec = EntityAccessSpec(
            permissions=[
                _permit_rule(AccessOperationKind.DELETE, _role_check("admin")),
                _forbid_rule(AccessOperationKind.DELETE, _role_check("intern")),
            ]
        )

        handler = create_delete_handler(
            service,
            cedar_access_spec=spec,
            optional_auth_dep=_make_optional_auth_dep(auth_ctx),
            entity_name="Task",
        )

        request = _make_request(method="DELETE")
        with pytest.raises(HTTPException) as exc_info:
            await handler(UUID(record_id), request, auth_ctx)
        assert exc_info.value.status_code == 403
