"""
Unit tests for the E2E Testing Harness.

Tests for locators, assertions, and flow execution (without Playwright).
"""

import pytest

from dazzle_e2e.locators import parse_semantic_target


class TestSemanticTargetParsing:
    """Tests for semantic target parsing."""

    def test_parse_view_target(self) -> None:
        """Test parsing a view target."""
        target_type, identifier = parse_semantic_target("view:task_list")
        assert target_type == "view"
        assert identifier == "task_list"

    def test_parse_field_target(self) -> None:
        """Test parsing a field target."""
        target_type, identifier = parse_semantic_target("field:Task.title")
        assert target_type == "field"
        assert identifier == "Task.title"

    def test_parse_action_target(self) -> None:
        """Test parsing an action target."""
        target_type, identifier = parse_semantic_target("action:Task.create")
        assert target_type == "action"
        assert identifier == "Task.create"

    def test_parse_entity_target(self) -> None:
        """Test parsing an entity target."""
        target_type, identifier = parse_semantic_target("entity:Task")
        assert target_type == "entity"
        assert identifier == "Task"

    def test_parse_row_target(self) -> None:
        """Test parsing a row target."""
        target_type, identifier = parse_semantic_target("row:Task")
        assert target_type == "row"
        assert identifier == "Task"

    def test_parse_message_target(self) -> None:
        """Test parsing a message target."""
        target_type, identifier = parse_semantic_target("message:Task.title")
        assert target_type == "message"
        assert identifier == "Task.title"

    def test_parse_dialog_target(self) -> None:
        """Test parsing a dialog target."""
        target_type, identifier = parse_semantic_target("dialog:confirm")
        assert target_type == "dialog"
        assert identifier == "confirm"

    def test_invalid_target_raises(self) -> None:
        """Test that invalid target format raises ValueError."""
        with pytest.raises(ValueError, match="Invalid semantic target format"):
            parse_semantic_target("invalid_target")

    def test_empty_identifier(self) -> None:
        """Test parsing target with empty identifier."""
        target_type, identifier = parse_semantic_target("view:")
        assert target_type == "view"
        assert identifier == ""


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


class TestDNRAdapterURLResolution:
    """Tests for DNR adapter URL resolution."""

    def test_resolve_list_view_url(self) -> None:
        """Test resolving a list view URL."""
        from dazzle_e2e.adapters.dnr import DNRAdapter

        adapter = DNRAdapter(base_url="http://localhost:3000")
        url = adapter.resolve_view_url("task_list")

        assert url == "http://localhost:3000/task/list"

    def test_resolve_create_view_url(self) -> None:
        """Test resolving a create view URL."""
        from dazzle_e2e.adapters.dnr import DNRAdapter

        adapter = DNRAdapter(base_url="http://localhost:3000")
        url = adapter.resolve_view_url("task_create")

        assert url == "http://localhost:3000/task/create"

    def test_resolve_detail_view_url(self) -> None:
        """Test resolving a detail view URL."""
        from dazzle_e2e.adapters.dnr import DNRAdapter

        adapter = DNRAdapter(base_url="http://localhost:3000")
        url = adapter.resolve_view_url("task_detail")

        assert url == "http://localhost:3000/task/{id}"

    def test_resolve_edit_view_url(self) -> None:
        """Test resolving an edit view URL."""
        from dazzle_e2e.adapters.dnr import DNRAdapter

        adapter = DNRAdapter(base_url="http://localhost:3000")
        url = adapter.resolve_view_url("task_edit")

        assert url == "http://localhost:3000/task/{id}/edit"

    def test_resolve_dashboard_url(self) -> None:
        """Test resolving a dashboard view URL."""
        from dazzle_e2e.adapters.dnr import DNRAdapter

        adapter = DNRAdapter(base_url="http://localhost:3000")
        url = adapter.resolve_view_url("admin_dashboard")

        assert url == "http://localhost:3000/admin/dashboard"


class TestBaseAdapterURLResolution:
    """Tests for base adapter URL resolution."""

    def test_resolve_action_url(self) -> None:
        """Test resolving an action URL."""
        from dazzle_e2e.adapters.dnr import DNRAdapter

        adapter = DNRAdapter(
            base_url="http://localhost:3000",
            api_url="http://localhost:8000",
        )
        url = adapter.resolve_action_url("Task.create")

        assert url == "http://localhost:8000/task/create"

    def test_urls_strip_trailing_slash(self) -> None:
        """Test that URLs have trailing slashes stripped."""
        from dazzle_e2e.adapters.dnr import DNRAdapter

        adapter = DNRAdapter(
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
    """Tests for _get_auth_locator function."""

    def test_get_auth_locator_login_button(self) -> None:
        """Test getting auth locator for login_button."""
        from unittest.mock import MagicMock

        from dazzle_e2e.locators import DazzleLocators, _get_auth_locator

        page = MagicMock()
        locators = DazzleLocators(page)
        result = _get_auth_locator(locators, "login_button")

        page.locator.assert_called_once_with('[data-dazzle-auth-action="login"]')
        assert result == page.locator.return_value

    def test_get_auth_locator_logout_button(self) -> None:
        """Test getting auth locator for logout_button."""
        from unittest.mock import MagicMock

        from dazzle_e2e.locators import DazzleLocators, _get_auth_locator

        page = MagicMock()
        locators = DazzleLocators(page)
        result = _get_auth_locator(locators, "logout_button")

        page.locator.assert_called_once_with('[data-dazzle-auth-action="logout"]')
        assert result == page.locator.return_value

    def test_get_auth_locator_modal(self) -> None:
        """Test getting auth locator for modal."""
        from unittest.mock import MagicMock

        from dazzle_e2e.locators import DazzleLocators, _get_auth_locator

        page = MagicMock()
        locators = DazzleLocators(page)
        result = _get_auth_locator(locators, "modal")

        page.locator.assert_called_once_with("#dz-auth-modal")
        assert result == page.locator.return_value

    def test_get_auth_locator_form(self) -> None:
        """Test getting auth locator for form."""
        from unittest.mock import MagicMock

        from dazzle_e2e.locators import DazzleLocators, _get_auth_locator

        page = MagicMock()
        locators = DazzleLocators(page)
        result = _get_auth_locator(locators, "form")

        page.locator.assert_called_once_with("#dz-auth-form")
        assert result == page.locator.return_value

    def test_get_auth_locator_submit(self) -> None:
        """Test getting auth locator for submit button."""
        from unittest.mock import MagicMock

        from dazzle_e2e.locators import DazzleLocators, _get_auth_locator

        page = MagicMock()
        locators = DazzleLocators(page)
        result = _get_auth_locator(locators, "submit")

        page.locator.assert_called_once_with("#dz-auth-submit")
        assert result == page.locator.return_value

    def test_get_auth_locator_error(self) -> None:
        """Test getting auth locator for error message."""
        from unittest.mock import MagicMock

        from dazzle_e2e.locators import DazzleLocators, _get_auth_locator

        page = MagicMock()
        locators = DazzleLocators(page)
        result = _get_auth_locator(locators, "error")

        page.locator.assert_called_once_with("#dz-auth-error:not(.hidden)")
        assert result == page.locator.return_value

    def test_get_auth_locator_user_indicator(self) -> None:
        """Test getting auth locator for user indicator."""
        from unittest.mock import MagicMock

        from dazzle_e2e.locators import DazzleLocators, _get_auth_locator

        page = MagicMock()
        locators = DazzleLocators(page)
        result = _get_auth_locator(locators, "user_indicator")

        page.locator.assert_called_once_with("[data-dazzle-auth-user]")
        assert result == page.locator.return_value

    def test_get_auth_locator_field_email(self) -> None:
        """Test getting auth locator for field.email."""
        from unittest.mock import MagicMock

        from dazzle_e2e.locators import DazzleLocators, _get_auth_locator

        page = MagicMock()
        locators = DazzleLocators(page)
        result = _get_auth_locator(locators, "field.email")

        page.locator.assert_called_once_with('#dz-auth-form [name="email"]')
        assert result == page.locator.return_value

    def test_get_auth_locator_field_password(self) -> None:
        """Test getting auth locator for field.password."""
        from unittest.mock import MagicMock

        from dazzle_e2e.locators import DazzleLocators, _get_auth_locator

        page = MagicMock()
        locators = DazzleLocators(page)
        result = _get_auth_locator(locators, "field.password")

        page.locator.assert_called_once_with('#dz-auth-form [name="password"]')
        assert result == page.locator.return_value

    def test_get_auth_locator_toggle_register(self) -> None:
        """Test getting auth locator for toggle.register."""
        from unittest.mock import MagicMock

        from dazzle_e2e.locators import DazzleLocators, _get_auth_locator

        page = MagicMock()
        locators = DazzleLocators(page)
        result = _get_auth_locator(locators, "toggle.register")

        page.locator.assert_called_once_with('[data-dazzle-auth-toggle="register"]')
        assert result == page.locator.return_value

    def test_get_auth_locator_unknown_raises(self) -> None:
        """Test that unknown auth identifier raises ValueError."""
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
        from dazzle_e2e.adapters import BaseAdapter, DNRAdapter

        assert BaseAdapter is not None
        assert DNRAdapter is not None
