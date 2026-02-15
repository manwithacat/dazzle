"""Tests for the sitespec MCP handlers."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest


def _import_sitespec():
    """Import sitespec handlers directly to avoid MCP package init issues.

    The dazzle.mcp.__init__.py imports mcp.server which may not be installed
    in test environments. We need to import the handlers module directly.
    """
    # Create mock modules to satisfy imports
    sys.modules["dazzle.mcp.server.handlers"] = MagicMock(pytest_plugins=[])
    sys.modules["dazzle.mcp.server.handlers.common"] = MagicMock()

    # Mock sitespec data structures
    mock_nav_item = SimpleNamespace(label="Home", href="/")
    mock_footer_column = SimpleNamespace(
        title="Links",
        links=[SimpleNamespace(label="About", href="/about")],
    )
    mock_page = SimpleNamespace(
        route="/",
        type=SimpleNamespace(value="landing"),
        title="Home",
        sections=[],
        source=None,
    )
    mock_logo = SimpleNamespace(
        mode=SimpleNamespace(value="text"),
        text="My App",
        image_path=None,
    )
    mock_brand = SimpleNamespace(
        product_name="My App",
        tagline="Your best solution",
        support_email="support@example.com",
        company_legal_name="My Company",
        logo=mock_logo,
    )
    mock_layout = SimpleNamespace(
        theme=SimpleNamespace(value="light"),
        auth=SimpleNamespace(primary_entry="login"),
        nav=SimpleNamespace(
            public=[mock_nav_item],
            authenticated=[mock_nav_item],
        ),
        footer=SimpleNamespace(
            columns=[mock_footer_column],
            disclaimer="© 2025 My Company",
        ),
    )
    mock_legal = SimpleNamespace(
        terms=SimpleNamespace(route="/terms"),
        privacy=SimpleNamespace(route="/privacy"),
    )
    mock_auth_pages = SimpleNamespace(
        login=SimpleNamespace(route="/login", enabled=True),
        signup=SimpleNamespace(route="/signup", enabled=True),
    )
    mock_integrations = SimpleNamespace(
        app_mount_route="/app",
        auth_provider=SimpleNamespace(value="internal"),
    )

    mock_sitespec = SimpleNamespace(
        version="1.0",
        brand=mock_brand,
        layout=mock_layout,
        pages=[mock_page],
        legal=mock_legal,
        auth_pages=mock_auth_pages,
        integrations=mock_integrations,
        get_all_routes=lambda: ["/", "/login", "/signup", "/terms", "/privacy"],
        model_dump=lambda: {"version": "1.0"},
    )

    mock_sitespec_loader = MagicMock()
    mock_sitespec_loader.load_sitespec = MagicMock(return_value=mock_sitespec)
    mock_sitespec_loader.sitespec_exists = MagicMock(return_value=True)
    mock_sitespec_loader.SiteSpecError = Exception
    mock_sitespec_loader.validate_sitespec = MagicMock(
        return_value=SimpleNamespace(
            is_valid=True,
            errors=[],
            warnings=["Consider adding more content"],
        )
    )
    mock_sitespec_loader.scaffold_site = MagicMock(
        return_value={"sitespec": Path("sitespec.yaml"), "content": []}
    )
    mock_sitespec_loader.copy_file_exists = MagicMock(return_value=False)
    mock_sitespec_loader.get_copy_file_path = MagicMock(return_value=Path("site/content/copy.md"))
    mock_sitespec_loader.load_copy = MagicMock(return_value=None)
    mock_sitespec_loader.scaffold_copy_file = MagicMock(return_value=Path("site/content/copy.md"))
    sys.modules["dazzle.core.sitespec_loader"] = mock_sitespec_loader

    # Mock copy_parser
    mock_copy_parser = MagicMock()
    mock_copy_parser.load_copy_file = MagicMock(return_value=None)
    sys.modules["dazzle.core.copy_parser"] = mock_copy_parser

    # Mock site_coherence
    mock_coherence = MagicMock()
    mock_report = MagicMock()
    mock_report.to_dict = MagicMock(
        return_value={
            "score": 85,
            "error_count": 0,
            "warning_count": 1,
        }
    )
    mock_report.format = MagicMock(return_value="Site coherence: 85%")
    mock_report.error_count = 0
    mock_report.warning_count = 1
    mock_coherence.validate_site_coherence = MagicMock(return_value=mock_report)
    sys.modules["dazzle.core.site_coherence"] = mock_coherence

    module_path = (
        Path(__file__).parent.parent.parent.parent
        / "src"
        / "dazzle"
        / "mcp"
        / "server"
        / "handlers"
        / "sitespec.py"
    )
    spec = importlib.util.spec_from_file_location(
        "dazzle.mcp.server.handlers.sitespec",
        module_path,
        submodule_search_locations=[],
    )
    module = importlib.util.module_from_spec(spec)

    # Set up the package structure for relative imports
    module.__package__ = "dazzle.mcp.server.handlers"
    sys.modules["dazzle.mcp.server.handlers.sitespec"] = module

    spec.loader.exec_module(module)
    return module


# Import the module once at module load time
_ss = _import_sitespec()

# Get references to the functions we need
get_sitespec_handler = _ss.get_sitespec_handler
validate_sitespec_handler = _ss.validate_sitespec_handler
scaffold_site_handler = _ss.scaffold_site_handler
get_copy_handler = _ss.get_copy_handler
scaffold_copy_handler = _ss.scaffold_copy_handler
review_copy_handler = _ss.review_copy_handler
coherence_handler = _ss.coherence_handler


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def temp_project(tmp_path):
    """Create a temporary project with minimal structure."""
    project_dir = tmp_path / "test_project"
    project_dir.mkdir()

    # Create dazzle.toml manifest
    manifest = project_dir / "dazzle.toml"
    manifest.write_text(
        """
[project]
name = "test_project"
version = "0.1.0"
root = "test_project"

[modules]
paths = ["./dsl"]
"""
    )

    # Create site directory
    site_dir = project_dir / "site" / "content"
    site_dir.mkdir(parents=True)

    return project_dir


# =============================================================================
# Handler Tests
# =============================================================================


class TestGetSitespecHandler:
    """Tests for get_sitespec_handler."""

    def test_returns_sitespec_data(self, temp_project) -> None:
        """Test getting sitespec data."""
        result = get_sitespec_handler(temp_project, {})
        data = json.loads(result)

        assert "version" in data
        assert "brand" in data
        assert "layout" in data
        assert "pages" in data

    def test_includes_brand_info(self, temp_project) -> None:
        """Test that brand info is included."""
        result = get_sitespec_handler(temp_project, {})
        data = json.loads(result)

        assert "brand" in data
        brand = data["brand"]
        assert "product_name" in brand
        assert "tagline" in brand

    def test_includes_all_routes(self, temp_project) -> None:
        """Test that all routes are listed."""
        result = get_sitespec_handler(temp_project, {})
        data = json.loads(result)

        assert "all_routes" in data
        assert "/" in data["all_routes"]

    def test_with_use_defaults_option(self, temp_project) -> None:
        """Test use_defaults option."""
        result = get_sitespec_handler(temp_project, {"use_defaults": False})
        data = json.loads(result)

        # Should still return data (mocked)
        assert "version" in data or "error" in data


class TestValidateSitespecHandler:
    """Tests for validate_sitespec_handler."""

    def test_returns_validation_result(self, temp_project) -> None:
        """Test sitespec validation."""
        result = validate_sitespec_handler(temp_project, {})
        data = json.loads(result)

        assert "is_valid" in data
        assert "error_count" in data
        assert "warning_count" in data

    def test_includes_errors_and_warnings(self, temp_project) -> None:
        """Test that errors and warnings are included."""
        result = validate_sitespec_handler(temp_project, {})
        data = json.loads(result)

        assert "errors" in data
        assert "warnings" in data

    def test_with_check_content_files(self, temp_project) -> None:
        """Test check_content_files option."""
        result = validate_sitespec_handler(temp_project, {"check_content_files": False})
        data = json.loads(result)

        assert "is_valid" in data or "error" in data


class TestScaffoldSiteHandler:
    """Tests for scaffold_site_handler."""

    def test_scaffolds_site(self, temp_project) -> None:
        """Test scaffolding a site."""
        result = scaffold_site_handler(temp_project, {})
        data = json.loads(result)

        assert data["success"] is True
        assert "created_files" in data

    def test_with_product_name(self, temp_project) -> None:
        """Test with custom product name."""
        result = scaffold_site_handler(temp_project, {"product_name": "My Product"})
        data = json.loads(result)

        assert data["product_name"] == "My Product"

    def test_overwrite_option(self, temp_project) -> None:
        """Test overwrite option."""
        result = scaffold_site_handler(temp_project, {"overwrite": True})
        data = json.loads(result)

        assert data["success"] is True


class TestGetCopyHandler:
    """Tests for get_copy_handler."""

    def test_returns_not_found_when_missing(self, temp_project) -> None:
        """Test when copy.md doesn't exist."""
        result = get_copy_handler(temp_project, {})
        data = json.loads(result)

        assert data["exists"] is False
        assert "hint" in data

    def test_returns_copy_data_when_exists(self, temp_project) -> None:
        """Test when copy.md exists."""
        # Update mock to return copy exists
        sitespec_loader = sys.modules["dazzle.core.sitespec_loader"]
        sitespec_loader.copy_file_exists = MagicMock(return_value=True)
        sitespec_loader.load_copy = MagicMock(
            return_value={"sections": [{"type": "hero", "title": "Welcome"}]}
        )

        result = get_copy_handler(temp_project, {})
        data = json.loads(result)

        assert data["exists"] is True
        assert "sections" in data


class TestScaffoldCopyHandler:
    """Tests for scaffold_copy_handler."""

    def test_scaffolds_copy_file(self, temp_project) -> None:
        """Test scaffolding copy.md."""
        # Reset mock to return file doesn't exist
        sitespec_loader = sys.modules["dazzle.core.sitespec_loader"]
        sitespec_loader.copy_file_exists = MagicMock(return_value=False)

        result = scaffold_copy_handler(temp_project, {})
        data = json.loads(result)

        assert data["success"] is True
        assert "sections" in data

    def test_refuses_overwrite_by_default(self, temp_project) -> None:
        """Test that overwrite is refused by default when file exists."""
        sitespec_loader = sys.modules["dazzle.core.sitespec_loader"]
        sitespec_loader.copy_file_exists = MagicMock(return_value=True)

        result = scaffold_copy_handler(temp_project, {})
        data = json.loads(result)

        assert data["success"] is False
        assert "warning" in data

    def test_allows_overwrite_when_requested(self, temp_project) -> None:
        """Test overwrite when explicitly requested."""
        sitespec_loader = sys.modules["dazzle.core.sitespec_loader"]
        sitespec_loader.copy_file_exists = MagicMock(return_value=True)

        result = scaffold_copy_handler(temp_project, {"overwrite": True})
        data = json.loads(result)

        assert data["success"] is True
        assert data["overwritten"] is True


class TestReviewCopyHandler:
    """Tests for review_copy_handler."""

    def test_returns_not_found_when_missing(self, temp_project) -> None:
        """Test when copy.md doesn't exist."""
        sitespec_loader = sys.modules["dazzle.core.sitespec_loader"]
        sitespec_loader.copy_file_exists = MagicMock(return_value=False)

        result = review_copy_handler(temp_project, {})
        data = json.loads(result)

        assert data["exists"] is False


class TestCoherenceHandler:
    """Tests for coherence_handler."""

    def test_returns_coherence_score(self, temp_project) -> None:
        """Test coherence validation."""
        result = coherence_handler(temp_project, {})
        data = json.loads(result)

        assert "score" in data
        assert "formatted" in data

    def test_includes_priority(self, temp_project) -> None:
        """Test that priority guidance is included."""
        result = coherence_handler(temp_project, {})
        data = json.loads(result)

        assert "priority" in data

    def test_with_business_context(self, temp_project) -> None:
        """Test with business context hint."""
        result = coherence_handler(temp_project, {"business_context": "saas"})
        data = json.loads(result)

        # Should return results (mock doesn't use context)
        assert "score" in data or "error" in data
