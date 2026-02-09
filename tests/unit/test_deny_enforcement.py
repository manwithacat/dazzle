"""Tests for deny_personas wiring through endpoint → route → 403.

Validates that deny_roles on EndpointSpec produces a FastAPI dependency
that returns 403 when the user has a denied role.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

pytest.importorskip("fastapi")

from dazzle_back.runtime.auth import create_deny_dependency
from dazzle_back.specs.endpoint import EndpointSpec, HttpMethod

# =============================================================================
# create_deny_dependency
# =============================================================================


class TestCreateDenyDependency:
    def test_returns_callable(self) -> None:
        auth_store = MagicMock()
        dep = create_deny_dependency(auth_store, deny_roles=["intern"])
        assert callable(dep)

    @pytest.mark.asyncio
    async def test_allows_user_without_denied_role(self) -> None:
        from dazzle_back.runtime.auth import AuthContext

        auth_store = MagicMock()
        # validate_session is sync and returns AuthContext
        auth_store.validate_session = MagicMock(
            return_value=AuthContext(
                is_authenticated=True,
                roles=["editor"],
            )
        )

        dep = create_deny_dependency(auth_store, deny_roles=["intern"])
        request = MagicMock()
        request.cookies = {"dazzle_session": "valid-session-id"}

        result = await dep(request)
        assert result is not None
        assert result.is_authenticated

    @pytest.mark.asyncio
    async def test_denies_user_with_denied_role(self) -> None:
        from fastapi import HTTPException

        from dazzle_back.runtime.auth import AuthContext

        auth_store = MagicMock()
        auth_store.validate_session = MagicMock(
            return_value=AuthContext(
                is_authenticated=True,
                roles=["intern", "viewer"],
            )
        )

        dep = create_deny_dependency(auth_store, deny_roles=["intern"])
        request = MagicMock()
        request.cookies = {"dazzle_session": "valid-session-id"}

        with pytest.raises(HTTPException) as exc_info:
            await dep(request)
        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_allows_unauthenticated(self) -> None:
        """Unauthenticated users pass through (no denied role to check)."""
        from dazzle_back.runtime.auth import AuthContext

        auth_store = MagicMock()
        auth_store.validate_session = MagicMock(return_value=AuthContext(is_authenticated=False))

        dep = create_deny_dependency(auth_store, deny_roles=["intern"])
        request = MagicMock()
        request.cookies = {"dazzle_session": "expired-session"}

        result = await dep(request)
        assert not result.is_authenticated


# =============================================================================
# EndpointSpec deny_roles
# =============================================================================


class TestEndpointDenyRoles:
    def test_endpoint_has_deny_roles(self) -> None:
        ep = EndpointSpec(
            name="delete_task",
            service="delete_task",
            method=HttpMethod.DELETE,
            path="/tasks/{id}",
            deny_roles=["intern"],
        )
        assert ep.deny_roles == ["intern"]

    def test_endpoint_default_no_deny_roles(self) -> None:
        ep = EndpointSpec(
            name="list_tasks",
            service="list_tasks",
            method=HttpMethod.GET,
            path="/tasks",
        )
        assert ep.deny_roles == []


# =============================================================================
# Surface → Endpoint deny_personas propagation
# =============================================================================


class TestSurfaceDenyPropagation:
    def test_deny_personas_to_deny_roles(self) -> None:
        """Surface access.deny_personas should propagate to EndpointSpec.deny_roles."""
        from dazzle.core.ir import (
            SurfaceMode,
            SurfaceSection,
            SurfaceSpec,
        )
        from dazzle.core.ir.surfaces import SurfaceAccessSpec
        from dazzle_back.converters.surface_converter import convert_surface_to_endpoint

        surface = SurfaceSpec(
            name="task_list",
            title="Tasks",
            entity_ref="Task",
            mode=SurfaceMode.LIST,
            sections=[SurfaceSection(name="main", title="Main", elements=[])],
            access=SurfaceAccessSpec(
                allow_personas=["admin", "editor"],
                deny_personas=["intern"],
            ),
        )
        endpoint = convert_surface_to_endpoint(surface, "list_tasks")
        assert "intern" in endpoint.deny_roles
        assert "admin" in endpoint.require_roles
        assert "editor" in endpoint.require_roles
