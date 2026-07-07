"""
Unit tests for the E2E Testing Harness.

Tests for locators, assertions, and flow execution (without Playwright).
"""

import pytest

from dazzle_e2e.locators import parse_semantic_target


class TestSemanticTargetParsing:
    """Tests for semantic target parsing."""

    @pytest.mark.parametrize(
        ("target", "expected_type", "expected_identifier"),
        [
            # Test parsing a view target.
            ("view:task_list", "view", "task_list"),
            # Test parsing a field target.
            ("field:Task.title", "field", "Task.title"),
            # Test parsing an action target.
            ("action:Task.create", "action", "Task.create"),
            # Test parsing an entity target.
            ("entity:Task", "entity", "Task"),
            # Test parsing a row target.
            ("row:Task", "row", "Task"),
            # Test parsing a message target.
            ("message:Task.title", "message", "Task.title"),
            # Test parsing a dialog target.
            ("dialog:confirm", "dialog", "confirm"),
            # Test parsing target with empty identifier.
            ("view:", "view", ""),
        ],
        ids=[
            "test_parse_view_target",
            "test_parse_field_target",
            "test_parse_action_target",
            "test_parse_entity_target",
            "test_parse_row_target",
            "test_parse_message_target",
            "test_parse_dialog_target",
            "test_empty_identifier",
        ],
    )
    def test_parse_semantic_target(
        self, target: str, expected_type: str, expected_identifier: str
    ) -> None:
        """Semantic targets parse into (target_type, identifier) tuples."""
        target_type, identifier = parse_semantic_target(target)
        assert target_type == expected_type
        assert identifier == expected_identifier

    def test_invalid_target_raises(self) -> None:
        """Test that invalid target format raises ValueError."""
        with pytest.raises(ValueError, match="Invalid semantic target format"):
            parse_semantic_target("invalid_target")


class TestFlowResult:
    """Tests for FlowResult dataclass."""

    def test_flow_result_passed(self) -> None:
        """Test creating a passed flow result."""
        from dazzle.core.ir import FlowSpec
        from dazzle_e2e.harness import FlowResult

        flow = FlowSpec(id="test_flow", steps=[])
        result = FlowResult(flow=flow, passed=True)

        assert result.passed is True
        assert result.error is None
        assert result.failed_step is None

    def test_flow_result_failed(self) -> None:
        """Test creating a failed flow result."""
        from dazzle.core.ir import FlowSpec, FlowStep, FlowStepKind
        from dazzle_e2e.harness import FlowResult, StepResult

        flow = FlowSpec(id="test_flow", steps=[])
        step = FlowStep(kind=FlowStepKind.CLICK, target="action:Task.save")
        step_result = StepResult(step=step, passed=False, error="Element not found")

        result = FlowResult(
            flow=flow,
            passed=False,
            step_results=[step_result],
            error="Element not found",
        )

        assert result.passed is False
        assert result.error == "Element not found"
        assert result.failed_step is not None
        assert result.failed_step.error == "Element not found"


class TestStepResult:
    """Tests for StepResult dataclass."""

    def test_step_result_passed(self) -> None:
        """Test creating a passed step result."""
        from dazzle.core.ir import FlowStep, FlowStepKind
        from dazzle_e2e.harness import StepResult

        step = FlowStep(kind=FlowStepKind.CLICK, target="action:Task.create")
        result = StepResult(step=step, passed=True, duration_ms=50.0)

        assert result.passed is True
        assert result.error is None
        assert result.duration_ms == 50.0

    def test_step_result_failed(self) -> None:
        """Test creating a failed step result."""
        from dazzle.core.ir import FlowStep, FlowStepKind
        from dazzle_e2e.harness import StepResult

        step = FlowStep(kind=FlowStepKind.ASSERT, target="entity:Task")
        result = StepResult(step=step, passed=False, error="Entity not found")

        assert result.passed is False
        assert result.error == "Entity not found"


class TestDazzleAdapterURLResolution:
    """Tests for DNR adapter URL resolution."""

    @pytest.mark.parametrize(
        ("view", "expected"),
        [
            ("task_list", "http://localhost:3000/app/task"),
            ("task_create", "http://localhost:3000/app/task/create"),
            ("task_detail", "http://localhost:3000/app/task/{id}"),
            ("task_edit", "http://localhost:3000/app/task/{id}/edit"),
            ("admin_dashboard", "http://localhost:3000/app/admin/dashboard"),
        ],
        ids=[
            "test_resolve_list_view_url",
            "test_resolve_create_view_url",
            "test_resolve_detail_view_url",
            "test_resolve_edit_view_url",
            "test_resolve_dashboard_url",
        ],
    )
    def test_resolve_view_url(self, view: str, expected: str) -> None:
        from dazzle_e2e.adapters.dazzle_adapter import DazzleAdapter

        adapter = DazzleAdapter(base_url="http://localhost:3000")
        assert adapter.resolve_view_url(view) == expected


class TestBaseAdapterURLResolution:
    """Tests for base adapter URL resolution."""

    def test_resolve_action_url(self) -> None:
        """Test resolving an action URL."""
        from dazzle_e2e.adapters.dazzle_adapter import DazzleAdapter

        adapter = DazzleAdapter(
            base_url="http://localhost:3000",
            api_url="http://localhost:8000",
        )
        url = adapter.resolve_action_url("Task.create")

        assert url == "http://localhost:8000/task/create"

    def test_urls_strip_trailing_slash(self) -> None:
        """Test that URLs have trailing slashes stripped."""
        from dazzle_e2e.adapters.dazzle_adapter import DazzleAdapter

        adapter = DazzleAdapter(
            base_url="http://localhost:3000/",
            api_url="http://localhost:8000/",
        )

        assert adapter.base_url == "http://localhost:3000"
        assert adapter.api_url == "http://localhost:8000"


class TestFlowRunnerValueResolution:
    """Tests for FlowRunner value resolution."""

    def test_resolve_literal_value(self) -> None:
        """Test resolving a literal value."""
        from unittest.mock import MagicMock

        from dazzle.core.ir import FlowStep, FlowStepKind
        from dazzle_e2e.harness import FlowRunner

        # Create mock page and adapter
        page = MagicMock()
        adapter = MagicMock()

        runner = FlowRunner(page, adapter)
        step = FlowStep(kind=FlowStepKind.FILL, target="field:Task.title", value="Test Value")

        result = runner._resolve_value(step)
        assert result == "Test Value"

    def test_resolve_fixture_ref_from_data(self) -> None:
        """Test resolving a fixture reference from seeded data."""
        from unittest.mock import MagicMock

        from dazzle.core.ir import FlowStep, FlowStepKind
        from dazzle_e2e.harness import FlowRunner

        page = MagicMock()
        adapter = MagicMock()

        runner = FlowRunner(page, adapter)
        runner._fixture_data = {
            "Task_valid": {"id": "uuid-123", "title": "Seeded Task"},
        }

        step = FlowStep(
            kind=FlowStepKind.FILL,
            target="field:Task.title",
            fixture_ref="Task_valid.title",
        )

        result = runner._resolve_value(step)
        assert result == "Seeded Task"

    def test_resolve_fixture_ref_from_spec(self) -> None:
        """Test resolving a fixture reference from fixture spec."""
        from unittest.mock import MagicMock

        from dazzle.core.ir import FixtureSpec, FlowStep, FlowStepKind
        from dazzle_e2e.harness import FlowRunner

        page = MagicMock()
        adapter = MagicMock()

        fixtures = {
            "Task_valid": FixtureSpec(
                id="Task_valid",
                entity="Task",
                data={"title": "Fixture Task"},
            ),
        }

        runner = FlowRunner(page, adapter, fixtures)

        step = FlowStep(
            kind=FlowStepKind.FILL,
            target="field:Task.title",
            fixture_ref="Task_valid.title",
        )

        result = runner._resolve_value(step)
        assert result == "Fixture Task"

    def test_resolve_missing_value_raises(self) -> None:
        """Test that missing value raises ValueError."""
        from unittest.mock import MagicMock

        from dazzle.core.ir import FlowStep, FlowStepKind
        from dazzle_e2e.harness import FlowRunner

        page = MagicMock()
        adapter = MagicMock()

        runner = FlowRunner(page, adapter)
        step = FlowStep(kind=FlowStepKind.FILL, target="field:Task.title")

        with pytest.raises(ValueError, match="Could not resolve value"):
            runner._resolve_value(step)


class TestAuthTargetParsing:
    """Tests for auth target parsing in get_locator_for_target."""

    def test_parse_auth_login_button(self) -> None:
        """Test parsing auth:login_button target."""
        from dazzle_e2e.locators import parse_semantic_target

        target_type, identifier = parse_semantic_target("auth:login_button")
        assert target_type == "auth"
        assert identifier == "login_button"

    def test_parse_auth_logout_button(self) -> None:
        """Test parsing auth:logout_button target."""
        from dazzle_e2e.locators import parse_semantic_target

        target_type, identifier = parse_semantic_target("auth:logout_button")
        assert target_type == "auth"
        assert identifier == "logout_button"

    def test_parse_auth_field(self) -> None:
        """Test parsing auth:field.email target."""
        from dazzle_e2e.locators import parse_semantic_target

        target_type, identifier = parse_semantic_target("auth:field.email")
        assert target_type == "auth"
        assert identifier == "field.email"

    def test_parse_auth_toggle(self) -> None:
        """Test parsing auth:toggle.register target."""
        from dazzle_e2e.locators import parse_semantic_target

        target_type, identifier = parse_semantic_target("auth:toggle.register")
        assert target_type == "auth"
        assert identifier == "toggle.register"


class TestAuthLocatorMapping:
    """Tests for _get_auth_locator function — auth-target → CSS-selector map."""

    @pytest.mark.parametrize(
        ("identifier", "expected_selector"),
        [
            ("login_button", '[data-dazzle-auth-action="login"]'),
            ("logout_button", '[data-dazzle-auth-action="logout"]'),
            ("modal", "#dz-auth-modal"),
            ("form", "#dz-auth-form"),
            ("submit", "#dz-auth-submit"),
            ("error", "#dz-auth-error:not(.hidden):not([hidden])"),
            ("user_indicator", "[data-dazzle-auth-user]"),
            ("field.email", '#dz-auth-form [name="email"]'),
            ("field.password", '#dz-auth-form [name="password"]'),
            ("toggle.register", '[data-dazzle-auth-toggle="register"]'),
        ],
        ids=[
            "login_button",
            "logout_button",
            "modal",
            "form",
            "submit",
            "error",
            "user_indicator",
            "field_email",
            "field_password",
            "toggle_register",
        ],
    )
    def test_get_auth_locator(self, identifier: str, expected_selector: str) -> None:
        from unittest.mock import MagicMock

        from dazzle_e2e.locators import DazzleLocators, _get_auth_locator

        page = MagicMock()
        locators = DazzleLocators(page)
        result = _get_auth_locator(locators, identifier)

        page.locator.assert_called_once_with(expected_selector)
        assert result == page.locator.return_value

    def test_get_auth_locator_unknown_raises(self) -> None:
        from unittest.mock import MagicMock

        from dazzle_e2e.locators import DazzleLocators, _get_auth_locator

        page = MagicMock()
        locators = DazzleLocators(page)

        with pytest.raises(ValueError, match="Unknown auth identifier"):
            _get_auth_locator(locators, "unknown")


class TestGetLocatorForAuthTarget:
    """Tests for get_locator_for_target with auth targets."""

    def test_get_locator_for_auth_login_button(self) -> None:
        """Test get_locator_for_target with auth:login_button."""
        from unittest.mock import MagicMock

        from dazzle_e2e.locators import DazzleLocators, get_locator_for_target

        page = MagicMock()
        locators = DazzleLocators(page)
        result = get_locator_for_target(locators, "auth:login_button")

        page.locator.assert_called_once_with('[data-dazzle-auth-action="login"]')
        assert result == page.locator.return_value

    def test_get_locator_for_auth_field(self) -> None:
        """Test get_locator_for_target with auth:field.email."""
        from unittest.mock import MagicMock

        from dazzle_e2e.locators import DazzleLocators, get_locator_for_target

        page = MagicMock()
        locators = DazzleLocators(page)
        result = get_locator_for_target(locators, "auth:field.email")

        page.locator.assert_called_once_with('#dz-auth-form [name="email"]')
        assert result == page.locator.return_value


class TestE2EPackageImports:
    """Tests for E2E package imports."""

    def test_import_locators(self) -> None:
        """Test importing locators."""
        from dazzle_e2e import DazzleLocators

        assert DazzleLocators is not None

    def test_import_assertions(self) -> None:
        """Test importing assertions."""
        from dazzle_e2e import DazzleAssertions

        assert DazzleAssertions is not None

    def test_import_harness(self) -> None:
        """Test importing harness components."""
        from dazzle_e2e import FlowRunner, run_flow

        assert FlowRunner is not None
        assert run_flow is not None

    def test_import_adapters(self) -> None:
        """Test importing adapters."""
        from dazzle_e2e.adapters import BaseAdapter, DazzleAdapter

        assert BaseAdapter is not None
        assert DazzleAdapter is not None
