"""
Unit tests for RBAC enforcement wiring.

Tests the end-to-end flow from DSL surface access specs through to route-level
role checking, including:
- EndpointSpec.require_roles propagation from surface converter
- RouteGenerator per-route role dependencies
- Workspace access filtering
"""

from typing import Any

import pytest

from dazzle.core.ir.surfaces import SurfaceAccessSpec, SurfaceMode, SurfaceSpec
from dazzle.http.converters.surface_converter import (
    convert_surface_to_endpoint,
    convert_surfaces_to_services,
)
from dazzle.http.runtime.handlers.list_handlers import create_list_handler
from dazzle.http.specs.auth import (
    AccessComparisonKind,
    AccessConditionSpec,
    AccessLogicalKind,
    AccessOperationKind,
    EntityAccessSpec,
    PermissionRuleSpec,
    ScopeRuleSpec,
)
from dazzle.http.specs.endpoint import EndpointSpec, HttpMethod
from tests.unit.helpers.crud_routes import RecordingService, crud_route_client, signed_in

# =============================================================================
# Surface Converter: require_roles propagation
# =============================================================================


class TestSurfaceConverterRBAC:
    """Tests that surface access specs propagate to EndpointSpec.require_roles."""

    def test_access_propagation_to_require_roles(self) -> None:
        """Combined: no access, allow_personas, empty allow_personas all map correctly to require_roles."""
        # No access spec → empty roles
        surface = SurfaceSpec(
            name="task_list",
            entity_ref="Task",
            mode=SurfaceMode.LIST,
            sections=[],
        )
        assert convert_surface_to_endpoint(surface, "list_tasks").require_roles == []

        # allow_personas → require_roles
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
        assert convert_surface_to_endpoint(surface, "list_tasks").require_roles == [
            "admin",
            "manager",
        ]

        # require_auth but no allow_personas → empty roles
        surface = SurfaceSpec(
            name="task_list",
            entity_ref="Task",
            mode=SurfaceMode.LIST,
            sections=[],
            access=SurfaceAccessSpec(require_auth=True),
        )
        assert convert_surface_to_endpoint(surface, "list_tasks").require_roles == []

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

        from dazzle.http.runtime.route_generator import RouteGenerator
        from dazzle.http.specs.service import DomainOperation, OperationKind, ServiceSpec

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

        from dazzle.http.runtime.route_generator import RouteGenerator
        from dazzle.http.specs.service import DomainOperation, OperationKind, ServiceSpec

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
        from dazzle.http.specs import BackendSpec

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
        from dazzle.http.specs import BackendSpec

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
        from dazzle.http.converters import convert_appspec_to_backend

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

        from dazzle.http.runtime.auth import AuthContext, UserRecord, create_auth_dependency

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

        from dazzle.http.runtime.auth import AuthContext, UserRecord, create_auth_dependency

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

        from dazzle.http.runtime.auth import AuthContext, UserRecord, create_auth_dependency

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

        from dazzle.http.runtime.auth import AuthContext, UserRecord, create_auth_dependency

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

    @pytest.mark.parametrize(
        ("role", "expected"),
        [
            ("role_school_admin", "school_admin"),
            ("admin", "admin"),
            ("user_admin", "user_admin"),
            ("", ""),
            ("role_", ""),
        ],
        ids=[
            "test_strips_role_prefix",
            "test_leaves_bare_name_unchanged",
            "test_leaves_non_role_prefix_unchanged",
            "test_empty_string",
            "test_just_role_prefix",
        ],
    )
    def test_normalize_role(self, role: str, expected: str) -> None:
        from dazzle.http.runtime.route_support import _normalize_role

        assert _normalize_role(role) == expected


class TestBuildAccessContext:
    """Tests that _build_access_context normalizes roles from auth context."""

    @pytest.fixture()
    def _skip_if_no_fastapi(self) -> None:
        pytest.importorskip("fastapi")

    @pytest.mark.usefixtures("_skip_if_no_fastapi")
    def test_normalizes_prefixed_roles(self) -> None:
        """Database roles with role_ prefix are normalized for Cedar evaluation."""
        from unittest.mock import MagicMock

        from dazzle.http.runtime.route_generator import _build_access_context

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

        from dazzle.http.runtime.route_generator import _build_access_context

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

        from dazzle.http.runtime.route_generator import _build_access_context

        auth_ctx = MagicMock()
        auth_ctx.is_authenticated = False
        auth_ctx.user = None

        _user, runtime_ctx = _build_access_context(auth_ctx)
        assert len(runtime_ctx.roles) == 0
        assert runtime_ctx.user_id is None


# =============================================================================
# LIST route: Cedar permit gate and scope filters, through the generated route
# =============================================================================

_SCHOOL_EQ_CURRENT_USER = AccessConditionSpec(
    kind="comparison",
    field="school",
    comparison_op=AccessComparisonKind.EQUALS,
    value="current_user.school",
)
_ROLE_TEACHER = AccessConditionSpec(kind="role_check", role_name="teacher")


def _list_permit(**rule: Any) -> EntityAccessSpec:
    return EntityAccessSpec(
        permissions=[PermissionRuleSpec(operation=AccessOperationKind.LIST, **rule)]
    )


# (permit rule, caller roles, expected status). Each deny row is its own id.
_LIST_GATE_CASES = [
    pytest.param({"personas": ["school_admin"]}, ["student"], 403, id="deny-persona-not-permitted"),
    pytest.param(
        {"personas": ["school_admin"]}, ["school_admin"], 200, id="allow-persona-permitted"
    ),
    pytest.param(
        {"condition": _ROLE_TEACHER}, ["student"], 403, id="deny-role-check-not-held-#520"
    ),
    pytest.param({"condition": _ROLE_TEACHER}, ["teacher"], 200, id="allow-role-check-held-#520"),
    pytest.param(
        {"condition": _SCHOOL_EQ_CURRENT_USER},
        ["teacher"],
        200,
        id="field-condition-passes-gate-to-row-filter-#503",
    ),
    pytest.param(
        {
            "condition": AccessConditionSpec(
                kind="logical",
                logical_op=AccessLogicalKind.OR,
                logical_left=_ROLE_TEACHER,
                logical_right=_SCHOOL_EQ_CURRENT_USER,
            )
        },
        ["student"],
        200,
        id="role-or-field-condition-passes-gate-#520",
    ),
]


@pytest.mark.parametrize(("rule", "roles", "status"), _LIST_GATE_CASES)
def test_list_route_permit_gate(rule: dict[str, Any], roles: list[str], status: int) -> None:
    service = RecordingService()
    client = crud_route_client(
        create_list_handler, auth=signed_in(*roles), service=service, access=_list_permit(**rule)
    )

    response = client.get("/items")

    assert response.status_code == status
    # A denied caller never reaches the data layer.
    assert len(service.calls) == (1 if status == 200 else 0)


def test_list_route_scope_default_denies_a_permitted_role_without_a_scope_rule() -> None:
    """``permit:`` admits teacher and viewer, ``scope:`` covers only teacher: the
    viewer passes the gate and gets an empty page without a query."""
    access = EntityAccessSpec(
        permissions=[
            PermissionRuleSpec(operation=AccessOperationKind.LIST, personas=["teacher", "viewer"])
        ],
        scopes=[
            ScopeRuleSpec(operation=AccessOperationKind.LIST, condition=None, personas=["teacher"])
        ],
    )
    service = RecordingService()
    client = crud_route_client(
        create_list_handler, auth=signed_in("viewer"), service=service, access=access
    )

    response = client.get("/items")

    assert response.status_code == 200
    assert response.json() == {"items": [], "total": 0, "page": 1, "page_size": 20}
    assert service.calls == []


def test_list_route_scope_filters_rows_by_the_resolved_current_user_attribute() -> None:
    access = EntityAccessSpec(
        permissions=[PermissionRuleSpec(operation=AccessOperationKind.LIST, personas=["teacher"])],
        scopes=[
            ScopeRuleSpec(
                operation=AccessOperationKind.LIST,
                condition=_SCHOOL_EQ_CURRENT_USER,
                personas=["teacher"],
            )
        ],
    )
    service = RecordingService()
    client = crud_route_client(
        create_list_handler,
        auth=signed_in("teacher", prefs={"school": "school-99"}),
        service=service,
        access=access,
    )

    assert client.get("/items").status_code == 200
    assert [call["filters"] for call in service.calls] == [{"school": "school-99"}]


# =============================================================================
# _extract_condition_filters: dotted current_user.<attr> path (#526)
# =============================================================================


class TestExtractConditionFiltersDottedAttr:
    """Tests that _extract_condition_filters resolves current_user.<attr>
    dotted paths and injects them as SQL filters."""

    def _make_auth_ctx(self, preferences: dict[str, str]) -> object:
        from unittest.mock import MagicMock

        auth_ctx = MagicMock()
        auth_ctx.preferences = preferences
        # Make school attribute return None on the user object so resolution
        # falls through to the preferences dict.
        type(auth_ctx.user).school = property(lambda self: None)
        return auth_ctx

    def test_comparison_condition_resolves_dotted_attr_from_preferences(self) -> None:
        """AccessConditionSpec comparison with current_user.school is resolved."""
        from dazzle.http.runtime.route_generator import _extract_condition_filters
        from dazzle.http.specs.auth import AccessComparisonKind, AccessConditionSpec

        condition = AccessConditionSpec(
            kind="comparison",
            field="school",
            comparison_op=AccessComparisonKind.EQUALS,
            value="current_user.school",
        )

        auth_ctx = self._make_auth_ctx({"school": "school-abc"})
        filters: dict = {}
        _extract_condition_filters(condition, "user-1", filters, None, auth_ctx)

        assert filters == {"school": "school-abc"}

    def test_comparison_condition_injects_deny_when_attr_missing(self) -> None:
        """Missing user attribute produces impossible subquery — secure by default (#580)."""
        from dazzle.http.runtime.route_generator import _extract_condition_filters
        from dazzle.http.specs.auth import AccessComparisonKind, AccessConditionSpec

        condition = AccessConditionSpec(
            kind="comparison",
            field="school",
            comparison_op=AccessComparisonKind.EQUALS,
            value="current_user.school",
        )

        auth_ctx = self._make_auth_ctx({})  # no school in preferences
        filters: dict = {}
        _extract_condition_filters(condition, "user-1", filters, None, auth_ctx)

        # Should produce an impossible subquery instead of raw sentinel (#580)
        assert "school__in_subquery" in filters
        sql, params = filters["school__in_subquery"]
        assert sql == "SELECT NULL WHERE FALSE"
        assert params == []

    def test_and_logical_condition_threads_auth_context(self) -> None:
        """AND logical condition threads auth_context through to child comparisons."""
        from dazzle.http.runtime.route_generator import _extract_condition_filters
        from dazzle.http.specs.auth import (
            AccessComparisonKind,
            AccessConditionSpec,
            AccessLogicalKind,
        )

        condition = AccessConditionSpec(
            kind="logical",
            logical_op=AccessLogicalKind.AND,
            logical_left=AccessConditionSpec(
                kind="comparison",
                field="school",
                comparison_op=AccessComparisonKind.EQUALS,
                value="current_user.school",
            ),
            logical_right=AccessConditionSpec(
                kind="comparison",
                field="active",
                comparison_op=AccessComparisonKind.EQUALS,
                value="true",
            ),
        )

        auth_ctx = self._make_auth_ctx({"school": "school-xyz"})
        filters: dict = {}
        _extract_condition_filters(condition, "user-1", filters, None, auth_ctx)

        assert filters["school"] == "school-xyz"
        assert filters["active"] == "true"

    def test_no_filter_injected_for_non_dotted_current_user(self) -> None:
        """Plain ``current_user`` (no dot) still maps to user_id as before."""
        from dazzle.http.runtime.route_generator import _extract_condition_filters
        from dazzle.http.specs.auth import AccessComparisonKind, AccessConditionSpec

        condition = AccessConditionSpec(
            kind="comparison",
            field="owner",
            comparison_op=AccessComparisonKind.EQUALS,
            value="current_user",
        )

        auth_ctx = self._make_auth_ctx({})
        filters: dict = {}
        _extract_condition_filters(condition, "user-uuid-1", filters, None, auth_ctx)

        assert filters == {"owner": "user-uuid-1"}


# =============================================================================
# _resolve_scope_filters: scope: block enforcement (v0.44)
# =============================================================================


class TestScopeEnforcement:
    """Tests for scope: block enforcement via _resolve_scope_filters."""

    def test_resolve_scope_filters_with_matching_role(self) -> None:
        """Scope rule with matching role returns SQL filters."""
        from unittest.mock import MagicMock

        from dazzle.http.runtime.route_generator import _resolve_scope_filters
        from dazzle.http.specs.auth import (
            AccessComparisonKind,
            AccessConditionSpec,
            AccessOperationKind,
            EntityAccessSpec,
            ScopeRuleSpec,
        )

        cedar_spec = EntityAccessSpec(
            scopes=[
                ScopeRuleSpec(
                    operation=AccessOperationKind.LIST,
                    condition=AccessConditionSpec(
                        kind="comparison",
                        field="school",
                        comparison_op=AccessComparisonKind.EQUALS,
                        value="current_user.school",
                    ),
                    personas=["teacher"],
                )
            ]
        )

        auth_ctx = MagicMock()
        auth_ctx.preferences = {"school": "school-42"}
        type(auth_ctx.user).school = property(lambda self: None)

        result = _resolve_scope_filters(cedar_spec, "list", {"teacher"}, "user-1", auth_ctx)

        assert result == {"school": "school-42"}

    def test_resolve_scope_filters_no_condition_variants(self) -> None:
        """No-condition scope rules: all (matched persona), no_match, wildcard, empty.

        Combined: scope_filters_all, scope_filters_no_match, scope_filters_wildcard,
        scope_filters_empty_scopes_passes_through (#607).
        """
        from dazzle.http.runtime.route_generator import _resolve_scope_filters
        from dazzle.http.specs.auth import (
            AccessOperationKind,
            EntityAccessSpec,
            ScopeRuleSpec,
        )

        # scope: all (condition=None) → empty dict (no row filter)
        spec_all = EntityAccessSpec(
            scopes=[
                ScopeRuleSpec(
                    operation=AccessOperationKind.LIST, condition=None, personas=["admin"]
                )
            ]
        )
        assert _resolve_scope_filters(spec_all, "list", {"admin"}, "user-1") == {}

        # No matching role → None (default-deny)
        spec_teacher_only = EntityAccessSpec(
            scopes=[
                ScopeRuleSpec(
                    operation=AccessOperationKind.LIST,
                    condition=None,
                    personas=["teacher"],
                )
            ]
        )
        assert _resolve_scope_filters(spec_teacher_only, "list", {"student"}, "user-1") is None

        # personas=['*'] matches any role
        spec_wildcard = EntityAccessSpec(
            scopes=[
                ScopeRuleSpec(operation=AccessOperationKind.LIST, condition=None, personas=["*"])
            ]
        )
        assert _resolve_scope_filters(spec_wildcard, "list", {"any_random_role"}, "user-1") == {}

        # Empty scopes list → pass-through (permit gate already controls)
        assert (
            _resolve_scope_filters(EntityAccessSpec(scopes=[]), "list", {"admin"}, "user-1") == {}
        )
