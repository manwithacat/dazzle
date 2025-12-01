"""
Unit tests for Playwright code generation.

Tests for selector mapping, step code generation, and auth assertion generation.
"""

import pytest

from dazzle.core.ir import (
    FlowAssertion,
    FlowAssertionKind,
    FlowStep,
    FlowStepKind,
)
from dazzle.testing.playwright_codegen import (
    _auth_target_to_selector,
    _generate_step_code,
    _parse_target,
    _target_to_route,
    _target_to_selector,
)


class TestParseTarget:
    """Tests for target parsing."""

    def test_parse_view_target(self) -> None:
        """Test parsing a view target."""
        target_type, target_name = _parse_target("view:task_list")
        assert target_type == "view"
        assert target_name == "task_list"

    def test_parse_field_target(self) -> None:
        """Test parsing a field target."""
        target_type, target_name = _parse_target("field:Task.title")
        assert target_type == "field"
        assert target_name == "Task.title"

    def test_parse_action_target(self) -> None:
        """Test parsing an action target."""
        target_type, target_name = _parse_target("action:Task.create")
        assert target_type == "action"
        assert target_name == "Task.create"

    def test_parse_auth_target(self) -> None:
        """Test parsing an auth target."""
        target_type, target_name = _parse_target("auth:login_button")
        assert target_type == "auth"
        assert target_name == "login_button"

    def test_parse_unknown_target(self) -> None:
        """Test parsing a target without colon."""
        target_type, target_name = _parse_target("unknown")
        assert target_type == "unknown"
        assert target_name == "unknown"


class TestTargetToSelector:
    """Tests for target to selector conversion."""

    def test_view_selector(self) -> None:
        """Test view target to selector."""
        selector = _target_to_selector("view:task_list")
        assert selector == '[data-dazzle-view="task_list"]'

    def test_field_selector(self) -> None:
        """Test field target to selector."""
        selector = _target_to_selector("field:Task.title")
        assert selector == '[data-dazzle-field="title"]'

    def test_action_selector(self) -> None:
        """Test action target to selector."""
        selector = _target_to_selector("action:Task.create")
        assert selector == '[data-dazzle-action="create"]'

    def test_row_selector(self) -> None:
        """Test row target to selector."""
        selector = _target_to_selector("row:Task")
        assert selector == '[data-dazzle-row="Task"]'

    def test_component_selector(self) -> None:
        """Test component target to selector."""
        selector = _target_to_selector("component:TaskList")
        assert selector == '[data-dazzle-component="TaskList"]'

    def test_auth_selector(self) -> None:
        """Test auth target to selector."""
        selector = _target_to_selector("auth:login_button")
        assert selector == '[data-dazzle-auth-action="login"]'

    def test_unknown_selector(self) -> None:
        """Test unknown target to selector (fallback)."""
        selector = _target_to_selector("unknown:something")
        assert selector == '[data-testid="something"]'


class TestAuthTargetToSelector:
    """Tests for auth target to selector conversion."""

    def test_login_button(self) -> None:
        """Test login_button selector."""
        selector = _auth_target_to_selector("login_button")
        assert selector == '[data-dazzle-auth-action="login"]'

    def test_logout_button(self) -> None:
        """Test logout_button selector."""
        selector = _auth_target_to_selector("logout_button")
        assert selector == '[data-dazzle-auth-action="logout"]'

    def test_modal(self) -> None:
        """Test modal selector."""
        selector = _auth_target_to_selector("modal")
        assert selector == "#dz-auth-modal"

    def test_form(self) -> None:
        """Test form selector."""
        selector = _auth_target_to_selector("form")
        assert selector == "#dz-auth-form"

    def test_submit(self) -> None:
        """Test submit selector."""
        selector = _auth_target_to_selector("submit")
        assert selector == "#dz-auth-submit"

    def test_error(self) -> None:
        """Test error selector."""
        selector = _auth_target_to_selector("error")
        assert selector == "#dz-auth-error:not(.hidden)"

    def test_user_indicator(self) -> None:
        """Test user_indicator selector."""
        selector = _auth_target_to_selector("user_indicator")
        assert selector == "[data-dazzle-auth-user]"

    def test_field_email(self) -> None:
        """Test field.email selector."""
        selector = _auth_target_to_selector("field.email")
        assert selector == '#dz-auth-form [name="email"]'

    def test_field_password(self) -> None:
        """Test field.password selector."""
        selector = _auth_target_to_selector("field.password")
        assert selector == '#dz-auth-form [name="password"]'

    def test_toggle_register(self) -> None:
        """Test toggle.register selector."""
        selector = _auth_target_to_selector("toggle.register")
        assert selector == '[data-dazzle-auth-toggle="register"]'

    def test_toggle_login(self) -> None:
        """Test toggle.login selector."""
        selector = _auth_target_to_selector("toggle.login")
        assert selector == '[data-dazzle-auth-toggle="login"]'

    def test_fallback(self) -> None:
        """Test fallback selector for unknown auth target."""
        selector = _auth_target_to_selector("unknown")
        assert selector == '[data-dazzle-auth="unknown"]'


class TestTargetToRoute:
    """Tests for target to route conversion."""

    def test_view_route(self) -> None:
        """Test view target to route."""
        route = _target_to_route("view:task_list")
        assert route == "/task/list"

    def test_view_create_route(self) -> None:
        """Test view create target to route."""
        route = _target_to_route("view:task_create")
        assert route == "/task/create"

    def test_view_edit_route(self) -> None:
        """Test view edit target to route."""
        route = _target_to_route("view:task_edit")
        assert route == "/task/edit"

    def test_direct_path(self) -> None:
        """Test direct path (starts with /)."""
        route = _target_to_route("/")
        assert route == "/"

    def test_direct_path_with_segments(self) -> None:
        """Test direct path with segments."""
        route = _target_to_route("/admin/dashboard")
        assert route == "/admin/dashboard"

    def test_simple_target(self) -> None:
        """Test simple target without underscore."""
        route = _target_to_route("view:dashboard")
        assert route == "/dashboard"


class TestGenerateStepCodeAuthAssertions:
    """Tests for step code generation with auth assertions."""

    def test_is_authenticated_assertion(self) -> None:
        """Test IS_AUTHENTICATED assertion code generation."""
        step = FlowStep(
            kind=FlowStepKind.ASSERT,
            assertion=FlowAssertion(kind=FlowAssertionKind.IS_AUTHENTICATED),
        )
        code = _generate_step_code(step, {})
        assert "Verify user is authenticated" in code
        assert "[data-dazzle-auth-user]" in code
        assert "to_be_visible" in code

    def test_is_not_authenticated_assertion(self) -> None:
        """Test IS_NOT_AUTHENTICATED assertion code generation."""
        step = FlowStep(
            kind=FlowStepKind.ASSERT,
            assertion=FlowAssertion(kind=FlowAssertionKind.IS_NOT_AUTHENTICATED),
        )
        code = _generate_step_code(step, {})
        assert "Verify user is not authenticated" in code
        assert '[data-dazzle-auth-action="login"]' in code
        assert "to_be_visible" in code

    def test_login_succeeded_assertion(self) -> None:
        """Test LOGIN_SUCCEEDED assertion code generation."""
        step = FlowStep(
            kind=FlowStepKind.ASSERT,
            assertion=FlowAssertion(kind=FlowAssertionKind.LOGIN_SUCCEEDED),
        )
        code = _generate_step_code(step, {})
        assert "Verify login succeeded" in code
        assert "#dz-auth-modal" in code
        assert "not_to_be_visible" in code
        assert "[data-dazzle-auth-user]" in code

    def test_login_failed_assertion(self) -> None:
        """Test LOGIN_FAILED assertion code generation."""
        step = FlowStep(
            kind=FlowStepKind.ASSERT,
            assertion=FlowAssertion(kind=FlowAssertionKind.LOGIN_FAILED),
        )
        code = _generate_step_code(step, {})
        assert "Verify login failed with error" in code
        assert "#dz-auth-error" in code
        assert "to_be_visible" in code

    def test_route_protected_assertion(self) -> None:
        """Test ROUTE_PROTECTED assertion code generation."""
        step = FlowStep(
            kind=FlowStepKind.ASSERT,
            assertion=FlowAssertion(kind=FlowAssertionKind.ROUTE_PROTECTED),
        )
        code = _generate_step_code(step, {})
        assert "Verify route is protected" in code
        assert "#dz-auth-modal" in code
        assert '[data-dazzle-auth-action="login"]' in code
        assert "Route should be protected" in code

    def test_has_persona_assertion(self) -> None:
        """Test HAS_PERSONA assertion code generation."""
        step = FlowStep(
            kind=FlowStepKind.ASSERT,
            assertion=FlowAssertion(
                kind=FlowAssertionKind.HAS_PERSONA,
                target="admin",
            ),
        )
        code = _generate_step_code(step, {})
        assert "Verify user has 'admin' persona" in code
        assert '[data-dazzle-persona="admin"]' in code
        assert "to_be_visible" in code


class TestGenerateStepCodeNavigation:
    """Tests for step code generation with navigation."""

    def test_navigate_to_view(self) -> None:
        """Test navigation to view target."""
        step = FlowStep(
            kind=FlowStepKind.NAVIGATE,
            target="view:task_list",
        )
        code = _generate_step_code(step, {})
        assert "/task/list" in code
        assert "page.goto" in code
        assert "wait_for_load_state" in code

    def test_navigate_to_direct_path(self) -> None:
        """Test navigation to direct path."""
        step = FlowStep(
            kind=FlowStepKind.NAVIGATE,
            target="/",
        )
        code = _generate_step_code(step, {})
        # Should navigate to base_url + "/"
        assert "page.goto" in code
        assert '/"' in code or "/{" in code  # Path should be /

    def test_navigate_to_admin(self) -> None:
        """Test navigation to admin path."""
        step = FlowStep(
            kind=FlowStepKind.NAVIGATE,
            target="/admin/dashboard",
        )
        code = _generate_step_code(step, {})
        assert "/admin/dashboard" in code


class TestGenerateStepCodeAuthActions:
    """Tests for step code generation with auth actions."""

    def test_click_auth_login_button(self) -> None:
        """Test clicking auth login button."""
        step = FlowStep(
            kind=FlowStepKind.CLICK,
            target="auth:login_button",
        )
        code = _generate_step_code(step, {})
        assert '[data-dazzle-auth-action="login"]' in code
        assert ".click()" in code

    def test_click_auth_logout_button(self) -> None:
        """Test clicking auth logout button."""
        step = FlowStep(
            kind=FlowStepKind.CLICK,
            target="auth:logout_button",
        )
        code = _generate_step_code(step, {})
        assert '[data-dazzle-auth-action="logout"]' in code
        assert ".click()" in code

    def test_click_auth_submit(self) -> None:
        """Test clicking auth submit button."""
        step = FlowStep(
            kind=FlowStepKind.CLICK,
            target="auth:submit",
        )
        code = _generate_step_code(step, {})
        assert "#dz-auth-submit" in code
        assert ".click()" in code

    def test_fill_auth_email(self) -> None:
        """Test filling auth email field."""
        step = FlowStep(
            kind=FlowStepKind.FILL,
            target="auth:field.email",
            value="test@example.com",
        )
        code = _generate_step_code(step, {})
        assert '#dz-auth-form [name="email"]' in code
        assert ".fill(" in code
        assert "test@example.com" in code

    def test_fill_auth_password(self) -> None:
        """Test filling auth password field."""
        step = FlowStep(
            kind=FlowStepKind.FILL,
            target="auth:field.password",
            value="secret123",
        )
        code = _generate_step_code(step, {})
        assert '#dz-auth-form [name="password"]' in code
        assert ".fill(" in code
        assert "secret123" in code

    def test_click_auth_toggle_register(self) -> None:
        """Test clicking auth toggle to register mode."""
        step = FlowStep(
            kind=FlowStepKind.CLICK,
            target="auth:toggle.register",
        )
        code = _generate_step_code(step, {})
        assert '[data-dazzle-auth-toggle="register"]' in code
        assert ".click()" in code
