"""
Unit tests for auth flow generation.

Tests the auth_flows module and its integration with testspec_generator.
"""

from dazzle.core.ir import (
    FlowAssertionKind,
    FlowPriority,
    FlowStepKind,
    SurfaceAccessSpec,
)
from dazzle.testing.auth_flows import (
    generate_all_auth_flows,
    generate_auth_fixtures,
    generate_login_invalid_flow,
    generate_login_valid_flow,
    generate_logout_flow,
    generate_persona_access_allowed_flow,
    generate_persona_access_denied_flow,
    generate_protected_route_flow,
    generate_registration_flow,
)


class TestAuthFixtures:
    """Tests for auth fixture generation."""

    def test_basic_fixtures(self):
        """Test that basic auth fixtures are generated."""
        fixtures = generate_auth_fixtures()

        assert len(fixtures) >= 3
        fixture_ids = [f.id for f in fixtures]
        assert "auth_test_user" in fixture_ids
        assert "auth_invalid_credentials" in fixture_ids
        assert "auth_new_user" in fixture_ids

    def test_test_user_fixture(self):
        """Test the standard test user fixture."""
        fixtures = generate_auth_fixtures()
        test_user = next(f for f in fixtures if f.id == "auth_test_user")

        assert test_user.entity == "User"
        assert "email" in test_user.data
        assert "password" in test_user.data
        assert test_user.data["email"] == "test@example.com"

    def test_persona_fixtures(self):
        """Test that persona-specific fixtures are generated."""
        personas = ["admin", "coordinator"]
        fixtures = generate_auth_fixtures(personas)

        fixture_ids = [f.id for f in fixtures]
        assert "auth_user_admin" in fixture_ids
        assert "auth_user_coordinator" in fixture_ids

        admin_fixture = next(f for f in fixtures if f.id == "auth_user_admin")
        assert admin_fixture.data["persona"] == "admin"


class TestLoginFlows:
    """Tests for login flow generation."""

    def test_login_valid_flow_structure(self):
        """Test the valid login flow structure."""
        flow = generate_login_valid_flow()

        assert flow.id == "auth_login_valid"
        assert flow.priority == FlowPriority.HIGH
        assert "auth" in flow.tags
        assert "login" in flow.tags
        assert flow.auto_generated is True

    def test_login_valid_flow_steps(self):
        """Test that valid login flow has correct steps."""
        flow = generate_login_valid_flow()

        # Should start with navigation
        assert flow.steps[0].kind == FlowStepKind.NAVIGATE
        assert flow.steps[0].target == "/"

        # Should click login button
        click_steps = [s for s in flow.steps if s.kind == FlowStepKind.CLICK]
        login_click = next((s for s in click_steps if s.target == "auth:login_button"), None)
        assert login_click is not None

        # Should fill email and password
        fill_steps = [s for s in flow.steps if s.kind == FlowStepKind.FILL]
        assert len(fill_steps) >= 2

        email_fill = next((s for s in fill_steps if s.target == "auth:field.email"), None)
        assert email_fill is not None
        assert email_fill.fixture_ref == "auth_test_user.email"

        # Should assert login succeeded
        assert_steps = [s for s in flow.steps if s.kind == FlowStepKind.ASSERT]
        login_success = next(
            (
                s
                for s in assert_steps
                if s.assertion and s.assertion.kind == FlowAssertionKind.LOGIN_SUCCEEDED
            ),
            None,
        )
        assert login_success is not None

    def test_login_invalid_flow_structure(self):
        """Test the invalid login flow structure."""
        flow = generate_login_invalid_flow()

        assert flow.id == "auth_login_invalid"
        assert "error-handling" in flow.tags

    def test_login_invalid_flow_assertions(self):
        """Test that invalid login flow asserts failure."""
        flow = generate_login_invalid_flow()

        assert_steps = [s for s in flow.steps if s.kind == FlowStepKind.ASSERT]

        # Should assert login failed
        login_failed = next(
            (
                s
                for s in assert_steps
                if s.assertion and s.assertion.kind == FlowAssertionKind.LOGIN_FAILED
            ),
            None,
        )
        assert login_failed is not None

        # Should assert still not authenticated
        not_auth = next(
            (
                s
                for s in assert_steps
                if s.assertion and s.assertion.kind == FlowAssertionKind.IS_NOT_AUTHENTICATED
            ),
            None,
        )
        assert not_auth is not None


class TestLogoutFlow:
    """Tests for logout flow generation."""

    def test_logout_flow_structure(self):
        """Test the logout flow structure."""
        flow = generate_logout_flow()

        assert flow.id == "auth_logout"
        assert flow.priority == FlowPriority.HIGH
        assert "logout" in flow.tags

    def test_logout_flow_preconditions(self):
        """Test that logout flow requires authentication."""
        flow = generate_logout_flow()

        assert flow.preconditions is not None
        assert flow.preconditions.authenticated is True

    def test_logout_flow_assertions(self):
        """Test that logout flow verifies logout success."""
        flow = generate_logout_flow()

        assert_steps = [s for s in flow.steps if s.kind == FlowStepKind.ASSERT]

        # Should assert not authenticated after logout
        not_auth = next(
            (
                s
                for s in assert_steps
                if s.assertion and s.assertion.kind == FlowAssertionKind.IS_NOT_AUTHENTICATED
            ),
            None,
        )
        assert not_auth is not None


class TestRegistrationFlow:
    """Tests for registration flow generation."""

    def test_registration_flow_structure(self):
        """Test the registration flow structure."""
        flow = generate_registration_flow()

        assert flow.id == "auth_registration"
        assert "registration" in flow.tags

    def test_registration_flow_fills_name(self):
        """Test that registration flow fills display name."""
        flow = generate_registration_flow()

        fill_steps = [s for s in flow.steps if s.kind == FlowStepKind.FILL]

        name_fill = next((s for s in fill_steps if s.target == "auth:field.display_name"), None)
        assert name_fill is not None


class TestProtectedRouteFlows:
    """Tests for protected route flow generation."""

    def test_protected_route_flow(self):
        """Test protected route flow generation."""
        flow = generate_protected_route_flow("admin_panel", "Admin Panel")

        assert flow.id == "auth_protected_admin_panel"
        assert "protected-route" in flow.tags

        # Should not be authenticated
        assert flow.preconditions is not None
        assert flow.preconditions.authenticated is False

        # Should assert route is protected
        assert_steps = [s for s in flow.steps if s.kind == FlowStepKind.ASSERT]
        route_protected = next(
            (
                s
                for s in assert_steps
                if s.assertion and s.assertion.kind == FlowAssertionKind.ROUTE_PROTECTED
            ),
            None,
        )
        assert route_protected is not None


class TestPersonaAccessFlows:
    """Tests for persona-based access flow generation."""

    def test_persona_allowed_flow(self):
        """Test persona allowed access flow."""
        flow = generate_persona_access_allowed_flow("admin", "admin_dashboard", "Admin Dashboard")

        assert flow.id == "auth_persona_admin_admin_dashboard_allowed"
        assert "rbac" in flow.tags
        assert "admin" in flow.tags

        # Should require authentication with specific persona
        assert flow.preconditions is not None
        assert flow.preconditions.authenticated is True
        assert flow.preconditions.user_role == "admin"

    def test_persona_denied_flow(self):
        """Test persona denied access flow."""
        flow = generate_persona_access_denied_flow(
            "volunteer", "admin_dashboard", "Admin Dashboard"
        )

        assert flow.id == "auth_persona_volunteer_admin_dashboard_denied"

        # Should assert route is protected (access denied)
        assert_steps = [s for s in flow.steps if s.kind == FlowStepKind.ASSERT]
        route_protected = next(
            (
                s
                for s in assert_steps
                if s.assertion and s.assertion.kind == FlowAssertionKind.ROUTE_PROTECTED
            ),
            None,
        )
        assert route_protected is not None


class TestGenerateAllAuthFlows:
    """Tests for the main auth flow generation function."""

    def test_basic_auth_flows(self):
        """Test that basic auth flows are generated."""
        fixtures, flows = generate_all_auth_flows(allow_registration=True)

        assert len(fixtures) >= 3
        assert len(flows) >= 4

        flow_ids = [f.id for f in flows]
        assert "auth_login_valid" in flow_ids
        assert "auth_login_invalid" in flow_ids
        assert "auth_logout" in flow_ids
        assert "auth_registration" in flow_ids

    def test_without_registration(self):
        """Test auth flows without registration enabled."""
        fixtures, flows = generate_all_auth_flows(allow_registration=False)

        flow_ids = [f.id for f in flows]
        assert "auth_login_valid" in flow_ids
        assert "auth_registration" not in flow_ids

    def test_with_protected_surfaces(self):
        """Test auth flows with protected surfaces."""
        protected_surfaces = [
            (
                "admin_panel",
                "Admin Panel",
                SurfaceAccessSpec(
                    require_auth=True,
                    allow_personas=["admin"],
                ),
            ),
        ]

        fixtures, flows = generate_all_auth_flows(
            allow_registration=True,
            protected_surfaces=protected_surfaces,
        )

        flow_ids = [f.id for f in flows]

        # Should have protected route test
        assert "auth_protected_admin_panel" in flow_ids

        # Should have persona access test
        assert "auth_persona_admin_admin_panel_allowed" in flow_ids

        # Should have admin user fixture
        fixture_ids = [f.id for f in fixtures]
        assert "auth_user_admin" in fixture_ids


class TestSurfaceAccessSpec:
    """Tests for SurfaceAccessSpec model."""

    def test_default_values(self):
        """Test default values for SurfaceAccessSpec."""
        spec = SurfaceAccessSpec()

        assert spec.require_auth is False
        assert spec.allow_personas == []
        assert spec.deny_personas == []
        assert spec.redirect_unauthenticated == "/"

    def test_with_personas(self):
        """Test SurfaceAccessSpec with personas."""
        spec = SurfaceAccessSpec(
            require_auth=True,
            allow_personas=["admin", "coordinator"],
            deny_personas=["guest"],
        )

        assert spec.require_auth is True
        assert "admin" in spec.allow_personas
        assert "guest" in spec.deny_personas
