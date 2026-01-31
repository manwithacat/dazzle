"""
Unit tests for Playwright code generation.

Tests for selector mapping, step code generation, and auth assertion generation.
Refactored to use parameterization for reduced redundancy.
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

    @pytest.mark.parametrize(
        "input_target,expected_type,expected_name",
        [
            ("view:task_list", "view", "task_list"),
            ("field:Task.title", "field", "Task.title"),
            ("action:Task.create", "action", "Task.create"),
            ("auth:login_button", "auth", "login_button"),
            ("unknown", "unknown", "unknown"),
        ],
        ids=["view", "field", "action", "auth", "unknown"],
    )
    def test_parse_target(self, input_target: str, expected_type: str, expected_name: str) -> None:
        """Test target parsing for various target types."""
        target_type, target_name = _parse_target(input_target)
        assert target_type == expected_type
        assert target_name == expected_name


class TestTargetToSelector:
    """Tests for target to selector conversion."""

    @pytest.mark.parametrize(
        "target,expected_fragment",
        [
            ("view:task_list", '[data-dazzle-view="task_list"]'),
            ("field:Task.title", '[data-dazzle-field="title"]'),
            ("action:Task.create", "data-dazzle-action"),
            ("row:Task", '[data-dazzle-row="Task"]'),
            ("component:TaskList", '[data-dazzle-component="TaskList"]'),
            ("auth:login_button", '[data-dazzle-auth-action="login"]'),
            ("unknown:something", '[data-testid="something"]'),
        ],
        ids=["view", "field", "action", "row", "component", "auth", "unknown"],
    )
    def test_target_to_selector(self, target: str, expected_fragment: str) -> None:
        """Test target to selector conversion for various target types."""
        selector = _target_to_selector(target)
        assert expected_fragment in selector


class TestAuthTargetToSelector:
    """Tests for auth target to selector conversion."""

    @pytest.mark.parametrize(
        "auth_target,expected_selector",
        [
            ("login_button", '[data-dazzle-auth-action="login"]'),
            ("logout_button", '[data-dazzle-auth-action="logout"]'),
            ("modal", "#dz-auth-modal"),
            ("form", "#dz-auth-form"),
            ("submit", "#dz-auth-submit"),
            ("error", "#dz-auth-error:not(.hidden)"),
            ("user_indicator", "[data-dazzle-auth-user]"),
            ("field.email", '#dz-auth-form [name="email"]'),
            ("field.password", '#dz-auth-form [name="password"]'),
            ("toggle.register", '[data-dazzle-auth-toggle="register"]'),
            ("toggle.login", '[data-dazzle-auth-toggle="login"]'),
            ("unknown", '[data-dazzle-auth="unknown"]'),
        ],
        ids=[
            "login_button",
            "logout_button",
            "modal",
            "form",
            "submit",
            "error",
            "user_indicator",
            "field.email",
            "field.password",
            "toggle.register",
            "toggle.login",
            "fallback",
        ],
    )
    def test_auth_target_to_selector(self, auth_target: str, expected_selector: str) -> None:
        """Test auth target to selector conversion."""
        selector = _auth_target_to_selector(auth_target)
        assert selector == expected_selector


class TestTargetToRoute:
    """Tests for target to route conversion."""

    @pytest.mark.parametrize(
        "target,expected_route",
        [
            ("view:task_list", "/task"),
            ("view:task_create", "/task/create"),
            ("view:task_edit", "/task/test-id/edit"),
            ("/", "/"),
            ("/admin/dashboard", "/admin/dashboard"),
            ("view:dashboard", "/dashboard"),
        ],
        ids=[
            "view_list",
            "view_create",
            "view_edit",
            "direct_root",
            "direct_path",
            "simple_view",
        ],
    )
    def test_target_to_route(self, target: str, expected_route: str) -> None:
        """Test target to route conversion."""
        route = _target_to_route(target)
        assert route == expected_route


class TestGenerateStepCodeAuthAssertions:
    """Tests for step code generation with auth assertions."""

    @pytest.mark.parametrize(
        "assertion_kind,expected_fragments",
        [
            (
                FlowAssertionKind.IS_AUTHENTICATED,
                ["Verify user is authenticated", "[data-dazzle-auth-user]", "to_be_visible"],
            ),
            (
                FlowAssertionKind.IS_NOT_AUTHENTICATED,
                [
                    "Verify user is not authenticated",
                    '[data-dazzle-auth-action="login"]',
                    "to_be_visible",
                ],
            ),
            (
                FlowAssertionKind.LOGIN_SUCCEEDED,
                [
                    "Verify login succeeded",
                    "#dz-auth-modal",
                    "not_to_be_visible",
                    "[data-dazzle-auth-user]",
                ],
            ),
            (
                FlowAssertionKind.LOGIN_FAILED,
                ["Verify login failed with error", "#dz-auth-error", "to_be_visible"],
            ),
            (
                FlowAssertionKind.ROUTE_PROTECTED,
                [
                    "Verify route is protected",
                    "#dz-auth-modal",
                    '[data-dazzle-auth-action="login"]',
                    "Route should be protected",
                ],
            ),
        ],
        ids=[
            "is_authenticated",
            "is_not_authenticated",
            "login_succeeded",
            "login_failed",
            "route_protected",
        ],
    )
    def test_auth_assertion_code_generation(
        self, assertion_kind: FlowAssertionKind, expected_fragments: list[str]
    ) -> None:
        """Test auth assertion code generation."""
        step = FlowStep(
            kind=FlowStepKind.ASSERT,
            assertion=FlowAssertion(kind=assertion_kind),
        )
        code = _generate_step_code(step, {})
        for fragment in expected_fragments:
            assert fragment in code, f"Expected '{fragment}' in generated code"

    def test_has_persona_assertion(self) -> None:
        """Test HAS_PERSONA assertion code generation (requires target param)."""
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

    @pytest.mark.parametrize(
        "target,expected_fragments",
        [
            ("view:task_list", ["/task", "page.goto", "wait_for_load_state"]),
            ("/admin/dashboard", ["/admin/dashboard"]),
        ],
        ids=["view_target", "admin_path"],
    )
    def test_navigate_step_code(self, target: str, expected_fragments: list[str]) -> None:
        """Test navigation step code generation."""
        step = FlowStep(
            kind=FlowStepKind.NAVIGATE,
            target=target,
        )
        code = _generate_step_code(step, {})
        for fragment in expected_fragments:
            assert fragment in code, f"Expected '{fragment}' in generated code"

    def test_navigate_to_root(self) -> None:
        """Test navigation to root path."""
        step = FlowStep(
            kind=FlowStepKind.NAVIGATE,
            target="/",
        )
        code = _generate_step_code(step, {})
        assert "page.goto" in code
        # Path should be / somewhere in the code
        assert '/"' in code or "/{" in code


class TestGenerateStepCodeAuthActions:
    """Tests for step code generation with auth actions."""

    @pytest.mark.parametrize(
        "target,expected_selector",
        [
            ("auth:login_button", '[data-dazzle-auth-action="login"]'),
            ("auth:logout_button", '[data-dazzle-auth-action="logout"]'),
            ("auth:submit", "#dz-auth-submit"),
            ("auth:toggle.register", '[data-dazzle-auth-toggle="register"]'),
        ],
        ids=["login", "logout", "submit", "toggle_register"],
    )
    def test_click_auth_element(self, target: str, expected_selector: str) -> None:
        """Test clicking auth elements."""
        step = FlowStep(
            kind=FlowStepKind.CLICK,
            target=target,
        )
        code = _generate_step_code(step, {})
        assert expected_selector in code
        assert ".click()" in code

    @pytest.mark.parametrize(
        "target,field_selector,value",
        [
            ("auth:field.email", '#dz-auth-form [name="email"]', "test@example.com"),
            ("auth:field.password", '#dz-auth-form [name="password"]', "secret123"),
        ],
        ids=["email", "password"],
    )
    def test_fill_auth_field(self, target: str, field_selector: str, value: str) -> None:
        """Test filling auth fields."""
        step = FlowStep(
            kind=FlowStepKind.FILL,
            target=target,
            value=value,
        )
        code = _generate_step_code(step, {})
        assert field_selector in code
        assert ".fill(" in code
        assert value in code
