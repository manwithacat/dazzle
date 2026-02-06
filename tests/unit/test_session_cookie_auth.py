"""
Tests for session cookie authentication in CRUD routes.

Verifies that CRUD handlers properly authenticate requests via FastAPI's
Depends() system using auth dependency factories from auth.py.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest

pytest.importorskip("fastapi", reason="FastAPI required for handler tests")

from fastapi import FastAPI, HTTPException, Request  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from pydantic import BaseModel  # noqa: E402

from dazzle_back.runtime.route_generator import (  # noqa: E402
    create_create_handler,
    create_delete_handler,
    create_list_handler,
    create_read_handler,
)


@dataclass
class FakeAuthContext:
    """Minimal auth context for testing."""

    is_authenticated: bool = False
    user: Any = None
    roles: list[str] = field(default_factory=list)
    permissions: list[str] = field(default_factory=list)


@dataclass
class FakeUser:
    id: UUID = field(default_factory=uuid4)


def _make_request(cookies: dict[str, str] | None = None) -> MagicMock:
    """Create a minimal fake Request object."""
    request = MagicMock()
    request.cookies = cookies or {}
    request.headers = {}
    request.query_params = {}
    return request


class TestCrudHandlerAuth:
    """Test CRUD handler auth using the route_generator functions with Depends() interface."""

    @pytest.fixture
    def authenticated_context(self):
        return FakeAuthContext(is_authenticated=True, user=FakeUser())

    @pytest.fixture
    def unauthenticated_context(self):
        return FakeAuthContext(is_authenticated=False)

    @pytest.fixture
    def mock_service(self):
        service = MagicMock()
        service.execute = AsyncMock(return_value={"id": str(uuid4()), "title": "Test"})
        return service

    @pytest.fixture
    def auth_dep(self, authenticated_context):
        """An async auth dependency that returns an authenticated context."""

        async def dep(request: Any) -> Any:
            return authenticated_context

        return dep

    @pytest.fixture
    def optional_auth_dep(self, authenticated_context):
        """An async optional auth dependency that returns an authenticated context."""

        async def dep(request: Any) -> Any:
            return authenticated_context

        return dep

    @pytest.fixture
    def optional_auth_dep_unauth(self, unauthenticated_context):
        """An async optional auth dependency that returns an unauthenticated context."""

        async def dep(request: Any) -> Any:
            return unauthenticated_context

        return dep

    # --- LIST tests ---

    @pytest.mark.asyncio
    async def test_list_handler_authenticates_with_session(
        self, mock_service, optional_auth_dep, authenticated_context
    ):
        """List handler should succeed when auth context is authenticated."""
        handler = create_list_handler(
            service=mock_service,
            optional_auth_dep=optional_auth_dep,
            require_auth_by_default=True,
        )
        request = _make_request({"session_id": "valid"})
        # Bypass Depends() — pass auth_context directly (standard FastAPI unit test practice)
        result = await handler(
            request=request,
            auth_context=authenticated_context,
            page=1,
            page_size=20,
            sort=None,
            dir="asc",
            search=None,
        )
        assert result is not None
        mock_service.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_list_handler_rejects_without_session(
        self, mock_service, optional_auth_dep_unauth, unauthenticated_context
    ):
        """List handler should reject when auth context is unauthenticated."""
        handler = create_list_handler(
            service=mock_service,
            optional_auth_dep=optional_auth_dep_unauth,
            require_auth_by_default=True,
        )
        request = _make_request()

        with pytest.raises(HTTPException) as exc_info:
            await handler(
                request=request,
                auth_context=unauthenticated_context,
                page=1,
                page_size=20,
                sort=None,
                dir="asc",
                search=None,
            )
        assert exc_info.value.status_code == 401

    # --- READ tests ---

    @pytest.mark.asyncio
    async def test_read_handler_authenticates_with_session(
        self, mock_service, auth_dep, authenticated_context
    ):
        """Read handler should succeed when auth context is authenticated."""
        handler = create_read_handler(
            service=mock_service,
            auth_dep=auth_dep,
            require_auth_by_default=True,
        )
        result = await handler(
            id=uuid4(), request=_make_request(), auth_context=authenticated_context
        )
        assert result is not None

    @pytest.mark.asyncio
    async def test_read_handler_no_auth_required(self, mock_service):
        """Read handler with no auth dep should work without auth_context param."""
        handler = create_read_handler(service=mock_service)
        result = await handler(id=uuid4(), request=_make_request())
        assert result is not None

    # --- CREATE tests ---

    @pytest.mark.asyncio
    async def test_create_handler_authenticates_with_session(
        self, mock_service, auth_dep, authenticated_context
    ):
        """Create handler should succeed when auth context is authenticated."""

        class FakeInput(BaseModel):
            title: str = "Test"

        mock_service.execute = AsyncMock(return_value={"id": str(uuid4()), "title": "Test"})
        handler = create_create_handler(
            service=mock_service,
            input_schema=FakeInput,
            auth_dep=auth_dep,
            require_auth_by_default=True,
        )
        request = _make_request({"session_id": "valid"})
        request.headers = {"content-type": "application/json"}
        request.json = AsyncMock(return_value={"title": "Test"})
        result = await handler(request=request, auth_context=authenticated_context)
        assert result is not None

    # --- DELETE tests ---

    @pytest.mark.asyncio
    async def test_delete_handler_authenticates_with_session(
        self, mock_service, auth_dep, authenticated_context
    ):
        """Delete handler should succeed when auth context is authenticated."""
        mock_service.execute = AsyncMock(return_value=True)
        handler = create_delete_handler(
            service=mock_service,
            auth_dep=auth_dep,
            require_auth_by_default=True,
        )
        result = await handler(
            id=uuid4(), request=_make_request(), auth_context=authenticated_context
        )
        assert result == {"deleted": True}

    # --- No-auth handler tests ---

    @pytest.mark.asyncio
    async def test_list_handler_no_auth(self, mock_service):
        """List handler with no auth dep should work without auth_context param."""
        handler = create_list_handler(service=mock_service)
        request = _make_request()
        result = await handler(
            request=request,
            page=1,
            page_size=20,
            sort=None,
            dir="asc",
            search=None,
        )
        assert result is not None
        mock_service.execute.assert_called_once()


class TestDependsIntegration:
    """Integration test verifying Depends() actually resolves through FastAPI's DI."""

    @pytest.mark.asyncio
    async def test_list_handler_depends_resolves(self):
        """Depends(optional_auth_dep) should be resolved by FastAPI's TestClient."""
        user = FakeUser()
        auth_ctx = FakeAuthContext(is_authenticated=True, user=user)

        async def fake_optional_auth(request: Request) -> FakeAuthContext:
            return auth_ctx

        service = MagicMock()
        service.execute = AsyncMock(
            return_value={"items": [{"id": "1", "title": "Test"}], "total": 1}
        )

        handler = create_list_handler(
            service=service,
            optional_auth_dep=fake_optional_auth,
            require_auth_by_default=True,
        )

        app = FastAPI()
        app.get("/test")(handler)
        client = TestClient(app)
        response = client.get("/test")
        assert response.status_code == 200
        assert response.json()["total"] == 1

    @pytest.mark.asyncio
    async def test_read_handler_depends_rejects_unauth(self):
        """Depends(auth_dep) should raise 401 when the dependency raises."""

        async def strict_auth_dep(request: Request) -> None:
            raise HTTPException(status_code=401, detail="Not authenticated")

        service = MagicMock()
        service.execute = AsyncMock(return_value={"id": "1"})

        handler = create_read_handler(
            service=service,
            auth_dep=strict_auth_dep,
            require_auth_by_default=True,
        )

        app = FastAPI()
        app.get("/test/{id}")(handler)
        client = TestClient(app)
        response = client.get(f"/test/{uuid4()}")
        assert response.status_code == 401
