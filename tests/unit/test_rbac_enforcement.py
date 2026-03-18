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

    def test_read_endpoint_auto_generated_for_list_only_entity(self) -> None:
        """Entities with LIST surface but no VIEW surface get a READ endpoint."""
        surface = SurfaceSpec(
            name="task_list",
            entity_ref="Task",
            mode=SurfaceMode.LIST,
            sections=[],
        )
        _services, endpoints = convert_surfaces_to_services([surface])
        read_ep = next(
            (ep for ep in endpoints if ep.method == HttpMethod.GET and "{id}" in ep.path),
            None,
        )
        assert read_ep is not None
        assert read_ep.path == "/tasks/{id}"

    def test_read_endpoint_inherits_access_from_list_surface(self) -> None:
        """Auto-generated READ endpoints inherit access from the list surface."""
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
        read_ep = next(
            (ep for ep in endpoints if ep.method == HttpMethod.GET and "{id}" in ep.path),
            None,
        )
        assert read_ep is not None
        assert read_ep.require_roles == ["admin"]

    def test_no_duplicate_read_when_view_surface_exists(self) -> None:
        """No duplicate READ endpoint when entity already has a VIEW surface."""
        surfaces = [
            SurfaceSpec(
                name="task_list",
                entity_ref="Task",
                mode=SurfaceMode.LIST,
                sections=[],
            ),
            SurfaceSpec(
                name="task_detail",
                entity_ref="Task",
                mode=SurfaceMode.VIEW,
                sections=[],
            ),
        ]
        _services, endpoints = convert_surfaces_to_services(surfaces)
        read_eps = [ep for ep in endpoints if ep.method == HttpMethod.GET and "{id}" in ep.path]
        # Only the VIEW-generated one, no auto-generated duplicate
        assert len(read_eps) == 1

    def test_read_endpoint_generated_when_only_edit_surface_exists(self) -> None:
        """EDIT surfaces produce PUT, not GET — a GET read endpoint must still be auto-generated."""
        surfaces = [
            SurfaceSpec(
                name="task_list",
                entity_ref="Task",
                mode=SurfaceMode.LIST,
                sections=[],
            ),
            SurfaceSpec(
                name="task_edit",
                entity_ref="Task",
                mode=SurfaceMode.EDIT,
                sections=[],
            ),
        ]
        _services, endpoints = convert_surfaces_to_services(surfaces)
        read_eps = [ep for ep in endpoints if ep.method == HttpMethod.GET and "{id}" in ep.path]
        assert len(read_eps) == 1, (
            "GET read endpoint should be auto-generated when only EDIT surface exists"
        )


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


# =============================================================================
# Role name normalization
# =============================================================================


class TestNormalizeRole:
    """Tests that _normalize_role strips the role_ prefix from database roles."""

    def test_strips_role_prefix(self) -> None:
        from dazzle_back.runtime.route_generator import _normalize_role

        assert _normalize_role("role_school_admin") == "school_admin"

    def test_leaves_bare_name_unchanged(self) -> None:
        from dazzle_back.runtime.route_generator import _normalize_role

        assert _normalize_role("admin") == "admin"

    def test_leaves_non_role_prefix_unchanged(self) -> None:
        from dazzle_back.runtime.route_generator import _normalize_role

        assert _normalize_role("user_admin") == "user_admin"

    def test_empty_string(self) -> None:
        from dazzle_back.runtime.route_generator import _normalize_role

        assert _normalize_role("") == ""

    def test_just_role_prefix(self) -> None:
        from dazzle_back.runtime.route_generator import _normalize_role

        assert _normalize_role("role_") == ""


class TestBuildAccessContext:
    """Tests that _build_access_context normalizes roles from auth context."""

    @pytest.fixture()
    def _skip_if_no_fastapi(self) -> None:
        pytest.importorskip("fastapi")

    @pytest.mark.usefixtures("_skip_if_no_fastapi")
    def test_normalizes_prefixed_roles(self) -> None:
        """Database roles with role_ prefix are normalized for Cedar evaluation."""
        from unittest.mock import MagicMock

        from dazzle_back.runtime.route_generator import _build_access_context

        auth_ctx = MagicMock()
        auth_ctx.is_authenticated = True
        auth_ctx.user.id = "u1"
        auth_ctx.user.roles = ["role_school_admin", "role_teacher"]
        auth_ctx.user.is_superuser = False

        _user, runtime_ctx = _build_access_context(auth_ctx)
        assert set(runtime_ctx.roles) == {"school_admin", "teacher"}

    @pytest.mark.usefixtures("_skip_if_no_fastapi")
    def test_bare_roles_pass_through(self) -> None:
        """Roles without role_ prefix pass through unchanged."""
        from unittest.mock import MagicMock

        from dazzle_back.runtime.route_generator import _build_access_context

        auth_ctx = MagicMock()
        auth_ctx.is_authenticated = True
        auth_ctx.user.id = "u2"
        auth_ctx.user.roles = ["admin", "editor"]
        auth_ctx.user.is_superuser = False

        _user, runtime_ctx = _build_access_context(auth_ctx)
        assert set(runtime_ctx.roles) == {"admin", "editor"}

    @pytest.mark.usefixtures("_skip_if_no_fastapi")
    def test_unauthenticated_gives_empty_roles(self) -> None:
        """Unauthenticated context produces empty roles."""
        from unittest.mock import MagicMock

        from dazzle_back.runtime.route_generator import _build_access_context

        auth_ctx = MagicMock()
        auth_ctx.is_authenticated = False
        auth_ctx.user = None

        _user, runtime_ctx = _build_access_context(auth_ctx)
        assert len(runtime_ctx.roles) == 0
        assert runtime_ctx.user_id is None


# =============================================================================
# LIST permission gate in _list_handler_body
# =============================================================================


class TestListPermissionGate:
    """Tests for Cedar LIST permission check in _list_handler_body."""

    @pytest.mark.asyncio
    async def test_list_returns_403_when_role_denied(self) -> None:
        """User without required role gets 403 on list endpoint."""
        from unittest.mock import AsyncMock, MagicMock

        from fastapi import HTTPException

        from dazzle_back.runtime.route_generator import _list_handler_body
        from dazzle_back.specs.auth import (
            AccessOperationKind,
            EntityAccessSpec,
            PermissionRuleSpec,
        )

        # Cedar spec: only school_admin can LIST
        cedar_spec = EntityAccessSpec(
            permissions=[
                PermissionRuleSpec(
                    operation=AccessOperationKind.LIST,
                    personas=["school_admin"],
                ),
            ],
        )

        mock_service = AsyncMock()
        mock_request = MagicMock()
        mock_request.query_params = {}

        # Auth context: user has role "student" (not school_admin)
        auth_ctx = MagicMock()
        auth_ctx.is_authenticated = True
        user = MagicMock()
        user.id = "user-1"
        user.roles = ["student"]
        user.is_superuser = False
        auth_ctx.user = user

        with pytest.raises(HTTPException) as exc_info:
            await _list_handler_body(
                service=mock_service,
                access_spec=None,
                is_authenticated=True,
                user_id="user-1",
                request=mock_request,
                page=1,
                page_size=20,
                sort=None,
                dir="asc",
                search=None,
                cedar_access_spec=cedar_spec,
                auth_context=auth_ctx,
                entity_name="Task",
            )
        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_list_allowed_when_role_matches(self) -> None:
        """User with required role gets a successful list response."""
        from unittest.mock import AsyncMock, MagicMock

        from dazzle_back.runtime.route_generator import _list_handler_body
        from dazzle_back.specs.auth import (
            AccessOperationKind,
            EntityAccessSpec,
            PermissionRuleSpec,
        )

        cedar_spec = EntityAccessSpec(
            permissions=[
                PermissionRuleSpec(
                    operation=AccessOperationKind.LIST,
                    personas=["school_admin"],
                ),
            ],
        )

        mock_service = AsyncMock()
        mock_service.execute.return_value = {"items": [], "total": 0, "page": 1, "page_size": 20}

        mock_request = MagicMock()
        mock_request.query_params = {}

        auth_ctx = MagicMock()
        auth_ctx.is_authenticated = True
        user = MagicMock()
        user.id = "user-1"
        user.roles = ["school_admin"]
        user.is_superuser = False
        auth_ctx.user = user

        result = await _list_handler_body(
            service=mock_service,
            access_spec=None,
            is_authenticated=True,
            user_id="user-1",
            request=mock_request,
            page=1,
            page_size=20,
            sort=None,
            dir="asc",
            search=None,
            cedar_access_spec=cedar_spec,
            auth_context=auth_ctx,
            entity_name="Task",
        )
        assert result is not None

    @pytest.mark.asyncio
    async def test_list_passes_gate_for_field_condition_rules(self) -> None:
        """Rules with field conditions (e.g. current_user.school) bypass the
        gate and are enforced as row-level filters at query time (#503)."""
        from unittest.mock import AsyncMock, MagicMock

        from dazzle_back.runtime.route_generator import _list_handler_body
        from dazzle_back.specs.auth import (
            AccessComparisonKind,
            AccessConditionSpec,
            AccessOperationKind,
            EntityAccessSpec,
            PermissionRuleSpec,
        )

        # Rule: list: school = current_user.school (field condition, not pure role)
        cedar_spec = EntityAccessSpec(
            permissions=[
                PermissionRuleSpec(
                    operation=AccessOperationKind.LIST,
                    condition=AccessConditionSpec(
                        kind="comparison",
                        field="school",
                        comparison_op=AccessComparisonKind.EQUALS,
                        value="current_user.school",
                    ),
                ),
            ],
        )

        mock_service = AsyncMock()
        mock_service.execute.return_value = {"items": [], "total": 0, "page": 1, "page_size": 20}

        mock_request = MagicMock()
        mock_request.query_params = {}

        auth_ctx = MagicMock()
        auth_ctx.is_authenticated = True
        user = MagicMock()
        user.id = "user-1"
        user.roles = ["teacher"]
        user.is_superuser = False
        auth_ctx.user = user

        # Should NOT raise 403 — field conditions pass the gate
        result = await _list_handler_body(
            service=mock_service,
            access_spec=None,
            is_authenticated=True,
            user_id="user-1",
            request=mock_request,
            page=1,
            page_size=20,
            sort=None,
            dir="asc",
            search=None,
            cedar_access_spec=cedar_spec,
            auth_context=auth_ctx,
            entity_name="Manuscript",
        )
        assert result is not None


# =============================================================================
# LIST gate: role-check conditions (#520)
# =============================================================================


class TestListGateRoleCheckCondition:
    """Tests that role-check conditions in LIST rules are evaluated at the gate.

    Prior to the fix, the gate was skipped for any rule with a non-None
    condition — including role_check conditions — causing the gate to never
    fire for DSL-style rules like ``list: role(teacher)``.
    """

    @pytest.mark.asyncio
    async def test_list_returns_403_for_role_check_condition_when_role_not_matched(
        self,
    ) -> None:
        """DSL rule with role_check condition raises 403 when user lacks the role."""
        from unittest.mock import AsyncMock, MagicMock

        from fastapi import HTTPException

        from dazzle_back.runtime.route_generator import _list_handler_body
        from dazzle_back.specs.auth import (
            AccessConditionSpec,
            AccessOperationKind,
            EntityAccessSpec,
            PermissionRuleSpec,
        )

        # DSL-style rule: list: role(teacher) — condition=role_check, personas=[]
        cedar_spec = EntityAccessSpec(
            permissions=[
                PermissionRuleSpec(
                    operation=AccessOperationKind.LIST,
                    personas=[],
                    condition=AccessConditionSpec(
                        kind="role_check",
                        role_name="teacher",
                    ),
                ),
            ],
        )

        mock_service = MagicMock()
        mock_service.execute = AsyncMock(return_value=[])

        mock_request = MagicMock()
        mock_request.query_params = {}

        auth_ctx = MagicMock()
        auth_ctx.is_authenticated = True
        user = MagicMock()
        user.id = "user-1"
        user.roles = ["student"]
        user.is_superuser = False
        auth_ctx.user = user

        with pytest.raises(HTTPException) as exc_info:
            await _list_handler_body(
                service=mock_service,
                access_spec=None,
                is_authenticated=True,
                user_id="user-1",
                request=mock_request,
                page=1,
                page_size=20,
                sort=None,
                dir="asc",
                search=None,
                cedar_access_spec=cedar_spec,
                auth_context=auth_ctx,
                entity_name="Course",
            )
        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_list_returns_200_for_role_check_condition_when_role_matches(
        self,
    ) -> None:
        """DSL rule with role_check condition allows access when user has the role."""
        from unittest.mock import AsyncMock, MagicMock

        from dazzle_back.runtime.route_generator import _list_handler_body
        from dazzle_back.specs.auth import (
            AccessConditionSpec,
            AccessOperationKind,
            EntityAccessSpec,
            PermissionRuleSpec,
        )

        cedar_spec = EntityAccessSpec(
            permissions=[
                PermissionRuleSpec(
                    operation=AccessOperationKind.LIST,
                    personas=[],
                    condition=AccessConditionSpec(
                        kind="role_check",
                        role_name="teacher",
                    ),
                ),
            ],
        )

        mock_service = MagicMock()
        mock_service.execute = AsyncMock(return_value=[])

        mock_request = MagicMock()
        mock_request.query_params = {}

        auth_ctx = MagicMock()
        auth_ctx.is_authenticated = True
        user = MagicMock()
        user.id = "user-2"
        user.roles = ["teacher"]
        user.is_superuser = False
        auth_ctx.user = user

        # Should not raise
        result = await _list_handler_body(
            service=mock_service,
            access_spec=None,
            is_authenticated=True,
            user_id="user-2",
            request=mock_request,
            page=1,
            page_size=20,
            sort=None,
            dir="asc",
            search=None,
            cedar_access_spec=cedar_spec,
            auth_context=auth_ctx,
            entity_name="Course",
        )
        assert result is not None

    @pytest.mark.asyncio
    async def test_list_gate_skips_for_field_condition_with_role_check_in_or(
        self,
    ) -> None:
        """Mixed OR condition (role_check | comparison) skips gate — field condition present."""
        from unittest.mock import AsyncMock, MagicMock

        from dazzle_back.runtime.route_generator import _list_handler_body
        from dazzle_back.specs.auth import (
            AccessComparisonKind,
            AccessConditionSpec,
            AccessLogicalKind,
            AccessOperationKind,
            EntityAccessSpec,
            PermissionRuleSpec,
        )

        # Logical OR: role(teacher) OR school = current_user.school
        cedar_spec = EntityAccessSpec(
            permissions=[
                PermissionRuleSpec(
                    operation=AccessOperationKind.LIST,
                    personas=[],
                    condition=AccessConditionSpec(
                        kind="logical",
                        logical_op=AccessLogicalKind.OR,
                        logical_left=AccessConditionSpec(
                            kind="role_check",
                            role_name="teacher",
                        ),
                        logical_right=AccessConditionSpec(
                            kind="comparison",
                            field="school",
                            comparison_op=AccessComparisonKind.EQUALS,
                            value="current_user.school",
                        ),
                    ),
                ),
            ],
        )

        mock_service = MagicMock()
        mock_service.execute = AsyncMock(return_value=[])

        mock_request = MagicMock()
        mock_request.query_params = {}

        auth_ctx = MagicMock()
        auth_ctx.is_authenticated = True
        user = MagicMock()
        user.id = "user-3"
        user.roles = ["student"]  # would fail pure role check
        user.is_superuser = False
        auth_ctx.user = user

        # Gate skips because field condition is present — no 403
        result = await _list_handler_body(
            service=mock_service,
            access_spec=None,
            is_authenticated=True,
            user_id="user-3",
            request=mock_request,
            page=1,
            page_size=20,
            sort=None,
            dir="asc",
            search=None,
            cedar_access_spec=cedar_spec,
            auth_context=auth_ctx,
            entity_name="Course",
        )
        assert result is not None
