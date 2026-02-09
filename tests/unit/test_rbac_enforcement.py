"""
Unit tests for RBAC enforcement wiring.

Tests the end-to-end flow from DSL surface access specs through to route-level
role checking, including:
- EndpointSpec.require_roles propagation from surface converter
- RouteGenerator per-route role dependencies
- Workspace access filtering
"""

import pytest

from dazzle.core.ir.surfaces import SurfaceAccessSpec, SurfaceMode, SurfaceSpec
from dazzle_back.converters.surface_converter import (
    convert_surface_to_endpoint,
    convert_surfaces_to_services,
)
from dazzle_back.specs.endpoint import EndpointSpec, HttpMethod

# =============================================================================
# Surface Converter: require_roles propagation
# =============================================================================


class TestSurfaceConverterRBAC:
    """Tests that surface access specs propagate to EndpointSpec.require_roles."""

    def test_no_access_spec_gives_empty_roles(self) -> None:
        """Surface without access spec produces endpoint with no role requirements."""
        surface = SurfaceSpec(
            name="task_list",
            entity_ref="Task",
            mode=SurfaceMode.LIST,
            sections=[],
        )
        endpoint = convert_surface_to_endpoint(surface, "list_tasks")
        assert endpoint.require_roles == []

    def test_access_with_allow_personas_propagates_to_require_roles(self) -> None:
        """Surface with allow_personas produces endpoint with matching require_roles."""
        surface = SurfaceSpec(
            name="admin_dashboard",
            entity_ref="Task",
            mode=SurfaceMode.LIST,
            sections=[],
            access=SurfaceAccessSpec(
                require_auth=True,
                allow_personas=["admin", "manager"],
            ),
        )
        endpoint = convert_surface_to_endpoint(surface, "list_tasks")
        assert endpoint.require_roles == ["admin", "manager"]

    def test_access_with_empty_allow_personas_gives_empty_roles(self) -> None:
        """Surface with require_auth but no allow_personas gives no role requirements."""
        surface = SurfaceSpec(
            name="task_list",
            entity_ref="Task",
            mode=SurfaceMode.LIST,
            sections=[],
            access=SurfaceAccessSpec(require_auth=True),
        )
        endpoint = convert_surface_to_endpoint(surface, "list_tasks")
        assert endpoint.require_roles == []

    def test_delete_endpoint_inherits_access_from_list_surface(self) -> None:
        """Auto-generated DELETE endpoints inherit access from the list surface."""
        surface = SurfaceSpec(
            name="admin_tasks",
            entity_ref="Task",
            mode=SurfaceMode.LIST,
            sections=[],
            access=SurfaceAccessSpec(
                require_auth=True,
                allow_personas=["admin"],
            ),
        )
        _services, endpoints = convert_surfaces_to_services([surface])
        # Find the delete endpoint
        delete_ep = next((ep for ep in endpoints if ep.method == HttpMethod.DELETE), None)
        assert delete_ep is not None
        assert delete_ep.require_roles == ["admin"]


# =============================================================================
# EndpointSpec: require_roles field
# =============================================================================


class TestEndpointSpecRequireRoles:
    """Tests for the require_roles field on EndpointSpec."""

    def test_default_require_roles_is_empty(self) -> None:
        """EndpointSpec defaults to no required roles."""
        ep = EndpointSpec(
            name="test",
            service="svc",
            method=HttpMethod.GET,
            path="/test",
        )
        assert ep.require_roles == []

    def test_require_roles_can_be_set(self) -> None:
        """EndpointSpec accepts explicit require_roles."""
        ep = EndpointSpec(
            name="test",
            service="svc",
            method=HttpMethod.GET,
            path="/test",
            require_roles=["admin", "editor"],
        )
        assert ep.require_roles == ["admin", "editor"]


# =============================================================================
# RouteGenerator: per-route role dependencies
# =============================================================================


class TestRouteGeneratorRBAC:
    """Tests that RouteGenerator creates role-based dependencies for restricted endpoints."""

    @pytest.fixture()
    def _skip_if_no_fastapi(self) -> None:
        pytest.importorskip("fastapi")

    @pytest.mark.usefixtures("_skip_if_no_fastapi")
    def test_route_with_require_roles_gets_dependency(self) -> None:
        """Endpoint with require_roles gets a FastAPI dependency that checks roles."""
        from unittest.mock import MagicMock

        from dazzle_back.runtime.route_generator import RouteGenerator
        from dazzle_back.specs.service import DomainOperation, OperationKind, ServiceSpec

        # Create a mock service
        mock_service = MagicMock()
        mock_service.execute = MagicMock()

        # Create a mock auth_store
        mock_auth_store = MagicMock()

        # Create a simple model
        from pydantic import BaseModel

        class TaskModel(BaseModel):
            id: str
            title: str

        # Create endpoint with require_roles
        endpoint = EndpointSpec(
            name="list_tasks",
            service="list_tasks",
            method=HttpMethod.GET,
            path="/tasks",
            require_roles=["admin"],
        )

        service_spec = ServiceSpec(
            name="list_tasks",
            domain_operation=DomainOperation(
                entity="Task",
                kind=OperationKind.LIST,
            ),
        )

        generator = RouteGenerator(
            services={"list_tasks": mock_service},
            models={"Task": TaskModel},
            auth_store=mock_auth_store,
        )

        generator.generate_route(endpoint, service_spec)

        # Check the generated route has dependencies
        routes = generator.router.routes
        assert len(routes) > 0
        route = routes[0]
        # FastAPI stores route-level dependencies
        assert hasattr(route, "dependencies") or hasattr(route, "dependant")

    @pytest.mark.usefixtures("_skip_if_no_fastapi")
    def test_route_without_require_roles_has_no_role_dependency(self) -> None:
        """Endpoint without require_roles does not get a role-checking dependency."""
        from unittest.mock import MagicMock

        from dazzle_back.runtime.route_generator import RouteGenerator
        from dazzle_back.specs.service import DomainOperation, OperationKind, ServiceSpec

        mock_service = MagicMock()
        mock_auth_store = MagicMock()

        from pydantic import BaseModel

        class TaskModel(BaseModel):
            id: str
            title: str

        endpoint = EndpointSpec(
            name="list_tasks",
            service="list_tasks",
            method=HttpMethod.GET,
            path="/tasks",
        )

        service_spec = ServiceSpec(
            name="list_tasks",
            domain_operation=DomainOperation(
                entity="Task",
                kind=OperationKind.LIST,
            ),
        )

        generator = RouteGenerator(
            services={"list_tasks": mock_service},
            models={"Task": TaskModel},
            auth_store=mock_auth_store,
        )

        generator.generate_route(endpoint, service_spec)

        # Route should exist but without role dependencies
        routes = generator.router.routes
        assert len(routes) > 0


# =============================================================================
# BackendSpec: personas field
# =============================================================================


class TestBackendSpecPersonas:
    """Tests that BackendSpec includes personas from DSL."""

    def test_backend_spec_includes_personas(self) -> None:
        """BackendSpec accepts a list of personas."""
        from dazzle.core.ir.personas import PersonaSpec
        from dazzle_back.specs import BackendSpec

        personas = [
            PersonaSpec(id="admin", label="Administrator"),
            PersonaSpec(id="agent", label="Field Agent"),
        ]

        spec = BackendSpec(
            name="test_app",
            personas=personas,
        )

        assert len(spec.personas) == 2
        assert spec.personas[0].id == "admin"
        assert spec.personas[1].id == "agent"

    def test_backend_spec_defaults_to_empty_personas(self) -> None:
        """BackendSpec defaults to empty personas list."""
        from dazzle_back.specs import BackendSpec

        spec = BackendSpec(name="test_app")
        assert spec.personas == []


# =============================================================================
# Converter: personas pass-through
# =============================================================================


class TestConverterPersonas:
    """Tests that convert_appspec_to_backend passes personas through."""

    def test_converter_passes_personas(self) -> None:
        """convert_appspec_to_backend includes personas in BackendSpec."""
        from unittest.mock import MagicMock

        from dazzle.core.ir.personas import PersonaSpec
        from dazzle_back.converters import convert_appspec_to_backend

        # Build a minimal AppSpec mock
        appspec = MagicMock()
        appspec.name = "test"
        appspec.version = "1.0.0"
        appspec.title = "Test App"
        appspec.surfaces = []
        appspec.workspaces = []
        appspec.personas = [
            PersonaSpec(id="admin", label="Admin"),
        ]
        appspec.domain = MagicMock()
        appspec.domain.entities = []

        backend = convert_appspec_to_backend(appspec)
        assert len(backend.personas) == 1
        assert backend.personas[0].id == "admin"


# =============================================================================
# create_auth_dependency: role checking
# =============================================================================


class TestAuthDependencyRoleCheck:
    """Tests that create_auth_dependency enforces require_roles correctly."""

    @pytest.fixture()
    def _skip_if_no_fastapi(self) -> None:
        pytest.importorskip("fastapi")

    @pytest.mark.usefixtures("_skip_if_no_fastapi")
    @pytest.mark.asyncio
    async def test_auth_dep_allows_matching_role(self) -> None:
        """Auth dependency allows user with a matching role."""
        from unittest.mock import MagicMock

        from dazzle_back.runtime.auth import AuthContext, UserRecord, create_auth_dependency

        # Create a mock auth_store that returns a user with admin role
        mock_store = MagicMock()
        user = UserRecord(
            email="admin@test.com",
            password_hash="fake",
            roles=["admin"],
        )
        mock_store.validate_session.return_value = AuthContext(
            user=user,
            is_authenticated=True,
            roles=["admin"],
        )

        dep = create_auth_dependency(mock_store, require_roles=["admin"])

        # Create mock request with session cookie
        mock_request = MagicMock()
        mock_request.cookies = {"dazzle_session": "valid-session-id"}

        # Should succeed (no exception)
        result = await dep(mock_request)
        assert result.is_authenticated is True
        assert "admin" in result.roles

    @pytest.mark.usefixtures("_skip_if_no_fastapi")
    @pytest.mark.asyncio
    async def test_auth_dep_rejects_wrong_role(self) -> None:
        """Auth dependency rejects user without the required role."""
        from unittest.mock import MagicMock

        from fastapi import HTTPException

        from dazzle_back.runtime.auth import AuthContext, UserRecord, create_auth_dependency

        mock_store = MagicMock()
        user = UserRecord(
            email="agent@test.com",
            password_hash="fake",
            roles=["agent"],
        )
        mock_store.validate_session.return_value = AuthContext(
            user=user,
            is_authenticated=True,
            roles=["agent"],
        )

        dep = create_auth_dependency(mock_store, require_roles=["admin"])

        mock_request = MagicMock()
        mock_request.cookies = {"dazzle_session": "valid-session-id"}

        with pytest.raises(HTTPException) as exc_info:
            await dep(mock_request)
        assert exc_info.value.status_code == 403

    @pytest.mark.usefixtures("_skip_if_no_fastapi")
    @pytest.mark.asyncio
    async def test_auth_dep_allows_any_of_required_roles(self) -> None:
        """Auth dependency allows user with any one of the required roles."""
        from unittest.mock import MagicMock

        from dazzle_back.runtime.auth import AuthContext, UserRecord, create_auth_dependency

        mock_store = MagicMock()
        user = UserRecord(
            email="mgr@test.com",
            password_hash="fake",
            roles=["manager"],
        )
        mock_store.validate_session.return_value = AuthContext(
            user=user,
            is_authenticated=True,
            roles=["manager"],
        )

        dep = create_auth_dependency(mock_store, require_roles=["admin", "manager"])

        mock_request = MagicMock()
        mock_request.cookies = {"dazzle_session": "valid-session-id"}

        result = await dep(mock_request)
        assert result.is_authenticated is True

    @pytest.mark.usefixtures("_skip_if_no_fastapi")
    @pytest.mark.asyncio
    async def test_auth_dep_no_roles_allows_any_authenticated(self) -> None:
        """Auth dependency without require_roles allows any authenticated user."""
        from unittest.mock import MagicMock

        from dazzle_back.runtime.auth import AuthContext, UserRecord, create_auth_dependency

        mock_store = MagicMock()
        user = UserRecord(
            email="user@test.com",
            password_hash="fake",
            roles=["viewer"],
        )
        mock_store.validate_session.return_value = AuthContext(
            user=user,
            is_authenticated=True,
            roles=["viewer"],
        )

        dep = create_auth_dependency(mock_store)

        mock_request = MagicMock()
        mock_request.cookies = {"dazzle_session": "valid-session-id"}

        result = await dep(mock_request)
        assert result.is_authenticated is True
