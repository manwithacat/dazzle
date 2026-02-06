"""
Tests for community contribution packaging MCP handler.

Uses direct module import to avoid triggering mcp.server import from dazzle.mcp.__init__.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock

# ============================================================================
# Direct module import to avoid mcp.server dependency
# ============================================================================

_contribution_module = None
_handlers_consolidated_module = None


def _import_modules():
    """Import contribution module directly. handlers_consolidated is tested via contribution."""
    global _contribution_module, _handlers_consolidated_module

    if _contribution_module is not None:
        return

    # Mock the MCP server packages to prevent import errors
    _mocked = [
        "mcp",
        "mcp.server",
        "mcp.server.fastmcp",
        "mcp.server.stdio",
        "dazzle.mcp.server.handlers",
        "dazzle.mcp.server.github_issues",
        "dazzle.mcp",
    ]
    _orig = {k: sys.modules.get(k) for k in _mocked}
    for k in _mocked:
        sys.modules[k] = MagicMock(pytest_plugins=[])

    # Mock the github_issues module that contribution.py imports lazily
    github_issues_mock = MagicMock()
    github_issues_mock.gh_auth_guidance = MagicMock(
        return_value={"authenticated": False, "message": "Test mode"}
    )
    github_issues_mock.create_github_issue = MagicMock(return_value=None)
    sys.modules["dazzle.mcp.server.github_issues"] = github_issues_mock

    # Mock dazzle.mcp to prevent its __init__ from running
    dazzle_mcp_mock = MagicMock()
    dazzle_mcp_mock.server = MagicMock()
    dazzle_mcp_mock.server.github_issues = github_issues_mock
    sys.modules["dazzle.mcp"] = dazzle_mcp_mock

    # Get path to contribution.py
    src_path = Path(__file__).parent.parent.parent / "src"
    contribution_path = src_path / "dazzle" / "mcp" / "server" / "handlers" / "contribution.py"

    # Import contribution module
    spec = importlib.util.spec_from_file_location(
        "contribution_module",
        contribution_path,
    )
    _contribution_module = importlib.util.module_from_spec(spec)
    sys.modules["contribution_module"] = _contribution_module
    spec.loader.exec_module(_contribution_module)

    # Restore sys.modules to prevent pollution of other tests.
    # Keep github_issues and dazzle.mcp mocked — the handler does lazy
    # imports (``from dazzle.mcp.server.github_issues import ...``) at
    # call time and needs these mocks to persist during test execution.
    _keep_mocked = {"dazzle.mcp.server.github_issues", "dazzle.mcp"}
    for k, v in _orig.items():
        if k in _keep_mocked:
            continue
        if v is None:
            sys.modules.pop(k, None)
        else:
            sys.modules[k] = v

    # Create a mock consolidated module that dispatches to contribution handlers
    _handlers_consolidated_module = MagicMock()

    def _mock_handle_contribution(arguments):
        operation = arguments.get("operation", "")
        if operation == "templates":
            return _contribution_module.templates_handler(arguments)
        elif operation == "create":
            return _contribution_module.create_handler(arguments)
        elif operation == "validate":
            return _contribution_module.validate_handler(arguments)
        elif operation == "examples":
            return _contribution_module.examples_handler(arguments)
        else:
            return json.dumps({"error": f"Unknown operation: {operation}"})

    _handlers_consolidated_module.handle_contribution = _mock_handle_contribution


# Import the modules
_import_modules()


def templates_handler(params):
    return _contribution_module.templates_handler(params)


def examples_handler(params):
    return _contribution_module.examples_handler(params)


def validate_handler(params):
    return _contribution_module.validate_handler(params)


def create_handler(params):
    return _contribution_module.create_handler(params)


def handle_contribution(params):
    return _handlers_consolidated_module.handle_contribution(params)


class TestTemplatesHandler:
    """Tests for templates operation."""

    def test_returns_all_contribution_types(self) -> None:
        """Templates operation returns all 5 contribution types."""
        result = templates_handler({})
        data = json.loads(result)

        assert "templates" in data
        assert len(data["templates"]) == 5

        types = [t["type"] for t in data["templates"]]
        assert "api_pack" in types
        assert "ui_pattern" in types
        assert "bug_fix" in types
        assert "dsl_pattern" in types
        assert "feature_request" in types

    def test_includes_submission_url(self) -> None:
        """Templates include GitHub submission URL."""
        result = templates_handler({})
        data = json.loads(result)

        assert "submission_url" in data
        assert "github.com" in data["submission_url"]


class TestExamplesHandler:
    """Tests for examples operation."""

    def test_returns_api_pack_example(self) -> None:
        """Returns example for api_pack type."""
        result = examples_handler({"type": "api_pack"})
        data = json.loads(result)

        assert data["type"] == "api_pack"
        assert "example" in data
        assert "content" in data["example"]

    def test_returns_bug_fix_example(self) -> None:
        """Returns example for bug_fix type."""
        result = examples_handler({"type": "bug_fix"})
        data = json.loads(result)

        assert data["type"] == "bug_fix"
        assert "example" in data

    def test_returns_ui_pattern_example(self) -> None:
        """Returns example for ui_pattern type."""
        result = examples_handler({"type": "ui_pattern"})
        data = json.loads(result)

        assert data["type"] == "ui_pattern"

    def test_returns_dsl_pattern_example(self) -> None:
        """Returns example for dsl_pattern type."""
        result = examples_handler({"type": "dsl_pattern"})
        data = json.loads(result)

        assert data["type"] == "dsl_pattern"

    def test_returns_feature_request_example(self) -> None:
        """Returns example for feature_request type."""
        result = examples_handler({"type": "feature_request"})
        data = json.loads(result)

        assert data["type"] == "feature_request"

    def test_unknown_type_returns_error(self) -> None:
        """Unknown type returns error."""
        result = examples_handler({"type": "unknown_type"})
        data = json.loads(result)

        assert "error" in data


class TestValidateHandler:
    """Tests for validate operation."""

    def test_valid_api_pack(self) -> None:
        """Valid api_pack content passes validation."""
        result = validate_handler(
            {
                "type": "api_pack",
                "content": {
                    "provider": "TestProvider",
                    "category": "testing",
                    "base_url": "https://api.test.com",
                },
            }
        )
        data = json.loads(result)

        assert data["valid"] is True

    def test_missing_required_fields(self) -> None:
        """Missing required fields fails validation."""
        result = validate_handler(
            {
                "type": "api_pack",
                "content": {
                    "provider": "TestProvider",
                    # Missing category and base_url
                },
            }
        )
        data = json.loads(result)

        assert data["valid"] is False
        assert "missing_required" in data
        assert "category" in data["missing_required"]
        assert "base_url" in data["missing_required"]

    def test_missing_type_returns_error(self) -> None:
        """Missing type returns error."""
        result = validate_handler({"content": {}})
        data = json.loads(result)

        assert "error" in data

    def test_unknown_type_returns_error(self) -> None:
        """Unknown type returns error."""
        result = validate_handler({"type": "unknown", "content": {}})
        data = json.loads(result)

        assert "error" in data


class TestCreateHandler:
    """Tests for create operation."""

    def test_creates_api_pack_without_output(self) -> None:
        """Creates api_pack contribution in memory."""
        result = create_handler(
            {
                "type": "api_pack",
                "title": "Test API Pack",
                "description": "A test API integration",
                "content": {
                    "provider": "TestProvider",
                    "category": "testing",
                    "base_url": "https://api.test.com",
                },
            }
        )
        data = json.loads(result)

        assert data["status"] == "generated"
        assert data["type"] == "api_pack"
        assert "files" in data
        assert len(data["files"]) == 2  # TOML + Markdown

    def test_creates_api_pack_with_output(self, tmp_path: Path) -> None:
        """Creates api_pack contribution and writes to disk."""
        result = create_handler(
            {
                "type": "api_pack",
                "title": "Test API Pack",
                "description": "A test API integration",
                "content": {
                    "provider": "TestProvider",
                    "category": "testing",
                    "base_url": "https://api.test.com",
                },
                "output_dir": str(tmp_path),
            }
        )
        data = json.loads(result)

        assert data["status"] == "generated"
        assert "written_to" in data
        assert len(data["written_to"]) == 2

        # Verify files were created
        toml_file = tmp_path / "testprovider_testing.toml"
        md_file = tmp_path / "testprovider_testing_CONTRIBUTION.md"
        assert toml_file.exists()
        assert md_file.exists()

    def test_creates_bug_fix(self) -> None:
        """Creates bug_fix contribution."""
        result = create_handler(
            {
                "type": "bug_fix",
                "title": "Fix pagination bug",
                "description": "Pagination resets on filter clear",
                "content": {
                    "reproduction_steps": ["Step 1", "Step 2"],
                    "expected": "Stay on current page",
                    "actual": "Reset to page 1",
                },
            }
        )
        data = json.loads(result)

        assert data["status"] == "generated"
        assert data["type"] == "bug_fix"
        assert "markdown" in data

    def test_creates_ui_pattern(self) -> None:
        """Creates ui_pattern contribution."""
        result = create_handler(
            {
                "type": "ui_pattern",
                "title": "Collapsible sidebar",
                "description": "Add collapsible sidebar",
                "content": {
                    "use_case": "Small screens",
                    "current_behavior": "Always expanded",
                    "proposed_behavior": "Collapsible",
                },
            }
        )
        data = json.loads(result)

        assert data["status"] == "generated"
        assert data["type"] == "ui_pattern"

    def test_creates_dsl_pattern(self) -> None:
        """Creates dsl_pattern contribution."""
        result = create_handler(
            {
                "type": "dsl_pattern",
                "title": "Approval workflow",
                "description": "Multi-step approval",
                "content": {
                    "pattern_type": "workflow",
                    "dsl_code": "entity Request:\n  status: enum[draft,pending,approved]",
                },
            }
        )
        data = json.loads(result)

        assert data["status"] == "generated"
        assert data["type"] == "dsl_pattern"

    def test_creates_feature_request(self) -> None:
        """Creates feature_request contribution."""
        result = create_handler(
            {
                "type": "feature_request",
                "title": "GraphQL support",
                "description": "Generate GraphQL schema",
                "content": {
                    "motivation": "Teams need GraphQL",
                    "proposed_solution": "Add graphql mode",
                },
            }
        )
        data = json.loads(result)

        assert data["status"] == "generated"
        assert data["type"] == "feature_request"

    def test_missing_type_returns_error(self) -> None:
        """Missing type returns error."""
        result = create_handler({"title": "Test"})
        data = json.loads(result)

        assert "error" in data

    def test_invalid_type_returns_error(self) -> None:
        """Invalid type returns error."""
        result = create_handler({"type": "invalid"})
        data = json.loads(result)

        assert "error" in data


class TestConsolidatedHandler:
    """Tests for the consolidated handler dispatch."""

    def test_dispatches_templates(self) -> None:
        """Dispatches to templates handler."""
        result = handle_contribution({"operation": "templates"})
        data = json.loads(result)

        assert "templates" in data

    def test_dispatches_create(self) -> None:
        """Dispatches to create handler."""
        result = handle_contribution(
            {
                "operation": "create",
                "type": "feature_request",
                "title": "Test",
                "content": {"motivation": "Test", "proposed_solution": "Test"},
            }
        )
        data = json.loads(result)

        assert data["status"] == "generated"

    def test_dispatches_validate(self) -> None:
        """Dispatches to validate handler."""
        result = handle_contribution(
            {
                "operation": "validate",
                "type": "bug_fix",
                "content": {
                    "reproduction_steps": ["Step 1"],
                    "expected": "X",
                    "actual": "Y",
                },
            }
        )
        data = json.loads(result)

        assert data["valid"] is True

    def test_dispatches_examples(self) -> None:
        """Dispatches to examples handler."""
        result = handle_contribution({"operation": "examples", "type": "api_pack"})
        data = json.loads(result)

        assert "example" in data

    def test_unknown_operation_returns_error(self) -> None:
        """Unknown operation returns error."""
        result = handle_contribution({"operation": "unknown"})
        data = json.loads(result)

        assert "error" in data
        assert "unknown" in data["error"].lower()


class TestApiPackContent:
    """Tests for API pack content generation."""

    def test_toml_contains_pack_info(self, tmp_path: Path) -> None:
        """Generated TOML contains pack metadata."""
        create_handler(
            {
                "type": "api_pack",
                "title": "Stripe Payments",
                "description": "Process payments via Stripe",
                "content": {
                    "provider": "Stripe",
                    "category": "payments",
                    "base_url": "https://api.stripe.com",
                    "docs_url": "https://stripe.com/docs",
                },
                "output_dir": str(tmp_path),
            }
        )

        toml_content = (tmp_path / "stripe_payments.toml").read_text()

        assert "[pack]" in toml_content
        assert 'provider = "Stripe"' in toml_content
        assert 'category = "payments"' in toml_content

    def test_toml_contains_operations(self, tmp_path: Path) -> None:
        """Generated TOML contains operations."""
        create_handler(
            {
                "type": "api_pack",
                "title": "Test API",
                "description": "Test",
                "content": {
                    "provider": "Test",
                    "category": "test",
                    "base_url": "https://api.test.com",
                    "operations": {
                        "list_items": {"method": "GET", "path": "/items"},
                        "create_item": {"method": "POST", "path": "/items"},
                    },
                },
                "output_dir": str(tmp_path),
            }
        )

        toml_content = (tmp_path / "test_test.toml").read_text()

        assert "[operations]" in toml_content
        assert "list_items" in toml_content
        assert "create_item" in toml_content

    def test_markdown_contains_submission_link(self, tmp_path: Path) -> None:
        """Generated markdown contains GitHub submission link."""
        create_handler(
            {
                "type": "api_pack",
                "title": "Test API",
                "description": "Test",
                "content": {
                    "provider": "Test",
                    "category": "test",
                    "base_url": "https://api.test.com",
                },
                "output_dir": str(tmp_path),
            }
        )

        md_content = (tmp_path / "test_test_CONTRIBUTION.md").read_text()

        assert "github.com" in md_content
        assert "api-pack" in md_content
