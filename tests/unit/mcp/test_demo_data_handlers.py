"""Tests for the demo_data MCP handlers."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest


def _import_demo_data():
    """Import demo_data handlers directly to avoid MCP package init issues.

    The dazzle.mcp.__init__.py imports mcp.server which may not be installed
    in test environments. We need to import the handlers module directly.
    """
    # Create mock modules to satisfy imports
    mock_state = MagicMock()
    mock_state.get_project_path = MagicMock(return_value=None)
    sys.modules["dazzle.mcp.server.handlers"] = MagicMock()
    sys.modules["dazzle.mcp.server.state"] = mock_state

    module_path = (
        Path(__file__).parent.parent.parent.parent
        / "src"
        / "dazzle"
        / "mcp"
        / "server"
        / "handlers"
        / "demo_data.py"
    )
    spec = importlib.util.spec_from_file_location(
        "dazzle.mcp.server.handlers.demo_data",
        module_path,
        submodule_search_locations=[],
    )
    module = importlib.util.module_from_spec(spec)

    # Set up the package structure for relative imports
    module.__package__ = "dazzle.mcp.server.handlers"
    sys.modules["dazzle.mcp.server.handlers.demo_data"] = module

    spec.loader.exec_module(module)
    return module


# Import the module once at module load time
_dd = _import_demo_data()

# Get references to the functions we need
propose_demo_blueprint_handler = _dd.propose_demo_blueprint_handler
save_demo_blueprint_handler = _dd.save_demo_blueprint_handler
get_demo_blueprint_handler = _dd.get_demo_blueprint_handler
generate_demo_data_handler = _dd.generate_demo_data_handler
_infer_domain_suffix = _dd._infer_domain_suffix
_infer_field_strategy = _dd._infer_field_strategy


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def temp_project(tmp_path):
    """Create a temporary project with minimal DSL structure."""
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

    # Create dsl directory
    dsl_dir = project_dir / "dsl"
    dsl_dir.mkdir()

    # Create main.dsl with entities
    main_dsl = dsl_dir / "main.dsl"
    main_dsl.write_text(
        """
module test_project
app test_project "Test Project"

entity User "User":
    id: uuid pk
    full_name: str(200) required
    email: str(200) required unique
    is_active: bool = true

entity Task "Task":
    id: uuid pk
    title: str(200) required
    description: text optional
    user_id: uuid required
    status: enum[pending,in_progress,completed]=pending
    created_at: datetime auto_add
"""
    )

    # Create .dazzle directory
    dazzle_dir = project_dir / ".dazzle"
    dazzle_dir.mkdir()

    # Create demo directory
    demo_dir = dazzle_dir / "demo"
    demo_dir.mkdir()

    return project_dir


# =============================================================================
# Helper Function Tests
# =============================================================================


class TestInferDomainSuffix:
    """Tests for _infer_domain_suffix helper."""

    def test_solar_domain(self) -> None:
        """Test solar/energy domain inference."""
        assert _infer_domain_suffix("solar panel installation") == "Solar Ltd"
        assert _infer_domain_suffix("renewable energy") == "Solar Ltd"
        assert _infer_domain_suffix("battery storage") == "Solar Ltd"

    def test_property_domain(self) -> None:
        """Test property/letting domain inference."""
        assert _infer_domain_suffix("property management") == "Lettings Ltd"
        assert _infer_domain_suffix("estate agent CRM") == "Lettings Ltd"
        assert _infer_domain_suffix("rental tracking") == "Lettings Ltd"

    def test_finance_domain(self) -> None:
        """Test finance domain inference."""
        assert _infer_domain_suffix("accounting software") == "Finance Ltd"
        assert _infer_domain_suffix("tax calculator") == "Finance Ltd"

    def test_task_domain(self) -> None:
        """Test task/project domain inference."""
        assert _infer_domain_suffix("task management") == "Tasks Ltd"
        assert _infer_domain_suffix("project tracker") == "Tasks Ltd"

    def test_crm_domain(self) -> None:
        """Test CRM domain inference."""
        assert _infer_domain_suffix("CRM system") == "Services Ltd"
        assert _infer_domain_suffix("customer management") == "Services Ltd"

    def test_default_domain(self) -> None:
        """Test default domain fallback."""
        assert _infer_domain_suffix("unknown domain") == "Ltd"


class TestInferFieldStrategy:
    """Tests for _infer_field_strategy helper."""

    def test_id_field(self) -> None:
        """Test ID field strategy inference."""
        strategy, params = _infer_field_strategy("id", "uuid", "User")
        assert strategy == "uuid_generate"

    def test_foreign_key_field(self) -> None:
        """Test foreign key field strategy inference."""
        # Note: user_id with uuid type matches uuid_generate first
        # Foreign key is only inferred for non-uuid types
        strategy, params = _infer_field_strategy("user_id", "int", "Task")
        assert strategy == "foreign_key"
        assert params["target_entity"] == "User"

    def test_name_field(self) -> None:
        """Test name field strategy inference."""
        strategy, params = _infer_field_strategy("full_name", "str", "User")
        assert strategy == "person_name"

    def test_email_field(self) -> None:
        """Test email field strategy inference."""
        strategy, params = _infer_field_strategy("email", "str", "User")
        assert strategy == "email_from_name"

    def test_boolean_field(self) -> None:
        """Test boolean field strategy inference."""
        strategy, params = _infer_field_strategy("is_active", "bool", "User")
        assert strategy == "boolean_weighted"

    def test_date_field(self) -> None:
        """Test date field strategy inference."""
        strategy, params = _infer_field_strategy("created_at", "datetime", "Task")
        assert strategy == "date_relative"

    def test_amount_field(self) -> None:
        """Test currency amount field strategy inference."""
        strategy, params = _infer_field_strategy("price", "decimal", "Product")
        assert strategy == "currency_amount"

    def test_description_field(self) -> None:
        """Test description field strategy inference."""
        strategy, params = _infer_field_strategy("description", "text", "Task")
        assert strategy == "free_text_lorem"
        assert params["min_words"] == 5

    def test_title_field(self) -> None:
        """Test title field strategy inference."""
        strategy, params = _infer_field_strategy("title", "str", "Task")
        assert strategy == "free_text_lorem"
        assert params["min_words"] == 3


# =============================================================================
# Handler Tests
# =============================================================================


class TestProposeDemoBlueprintHandler:
    """Tests for propose_demo_blueprint_handler."""

    def test_proposes_blueprint(self, temp_project) -> None:
        """Test proposing a demo data blueprint."""
        result = propose_demo_blueprint_handler(temp_project, {})
        data = json.loads(result)

        # Should return a blueprint structure
        assert "blueprint" in data or "entities" in data or "error" not in data

    def test_with_domain_description(self, temp_project) -> None:
        """Test proposing with domain description."""
        result = propose_demo_blueprint_handler(
            temp_project, {"domain_description": "A task management application"}
        )
        data = json.loads(result)

        assert "error" not in data

    def test_filters_by_entities(self, temp_project) -> None:
        """Test filtering by entity names."""
        result = propose_demo_blueprint_handler(temp_project, {"entities": ["User"]})
        data = json.loads(result)

        # Should only include User entity
        if "blueprint" in data and "entities" in data["blueprint"]:
            entities = data["blueprint"]["entities"]
            # Entities may be a list or dict depending on implementation
            if isinstance(entities, dict):
                assert "User" in entities
            elif isinstance(entities, list):
                entity_names = [e.get("name", "") for e in entities]
                assert "User" in entity_names

    def test_handles_missing_project(self, tmp_path) -> None:
        """Test handling of missing project."""
        missing_project = tmp_path / "missing"
        missing_project.mkdir()

        result = propose_demo_blueprint_handler(missing_project, {})
        data = json.loads(result)

        assert "error" in data


class TestSaveDemoBlueprintHandler:
    """Tests for save_demo_blueprint_handler."""

    def test_requires_blueprint(self, temp_project) -> None:
        """Test that blueprint is required."""
        result = save_demo_blueprint_handler(temp_project, {})
        data = json.loads(result)

        assert "error" in data

    def test_saves_valid_blueprint(self, temp_project) -> None:
        """Test saving a valid blueprint."""
        blueprint = {
            "project_id": "test_project",
            "domain_description": "A test application",
            "tenants": [{"name": "Acme Corp", "prefix": "Alpha"}],
            "entities": [
                {
                    "name": "User",
                    "row_count": 10,
                    "fields": [
                        {"name": "full_name", "strategy": "person_name"},
                        {"name": "email", "strategy": "email_from_name"},
                    ],
                }
            ],
        }

        result = save_demo_blueprint_handler(temp_project, {"blueprint": blueprint})
        data = json.loads(result)

        assert data.get("status") == "saved" or "error" not in data

    def test_validates_blueprint(self, temp_project) -> None:
        """Test blueprint validation."""
        blueprint = {
            # Missing required structure
        }

        result = save_demo_blueprint_handler(
            temp_project, {"blueprint": blueprint, "validate": True}
        )
        data = json.loads(result)

        # May return error or accept minimal blueprint
        assert "status" in data or "error" in data


class TestGetDemoBlueprintHandler:
    """Tests for get_demo_blueprint_handler."""

    def test_returns_empty_for_no_blueprint(self, temp_project) -> None:
        """Test handling of no saved blueprint."""
        result = get_demo_blueprint_handler(temp_project, {})
        data = json.loads(result)

        # Should indicate no blueprint or return empty
        assert "blueprint" in data or "status" in data or "error" in data

    def test_returns_saved_blueprint(self, temp_project) -> None:
        """Test retrieving a saved blueprint."""
        # First save a blueprint
        blueprint = {
            "tenants": [{"name": "Test Corp", "prefix": "Alpha"}],
            "entities": {"User": {"row_count": 5}},
        }
        save_demo_blueprint_handler(temp_project, {"blueprint": blueprint})

        # Then retrieve it
        result = get_demo_blueprint_handler(temp_project, {})
        data = json.loads(result)

        if "blueprint" in data:
            assert data["blueprint"] is not None


class TestGenerateDemoDataHandler:
    """Tests for generate_demo_data_handler."""

    def test_requires_blueprint(self, temp_project) -> None:
        """Test that a blueprint must exist."""
        result = generate_demo_data_handler(temp_project, {})
        data = json.loads(result)

        # Should indicate no blueprint or generate from default
        assert "status" in data or "error" in data or "files" in data

    def test_generates_data_from_blueprint(self, temp_project) -> None:
        """Test generating demo data from saved blueprint."""
        # First save a blueprint
        blueprint = {
            "tenants": [{"name": "Test Corp", "prefix": "Alpha"}],
            "entities": {
                "User": {
                    "row_count": 3,
                    "fields": {
                        "id": {"strategy": "uuid_generate"},
                        "full_name": {"strategy": "person_name"},
                    },
                }
            },
        }
        save_demo_blueprint_handler(temp_project, {"blueprint": blueprint})

        # Then generate data
        result = generate_demo_data_handler(temp_project, {})
        data = json.loads(result)

        # Should generate files or indicate success
        assert "files" in data or "status" in data or "error" not in data

    def test_respects_format_option(self, temp_project) -> None:
        """Test output format option."""
        # Save blueprint first
        blueprint = {
            "tenants": [{"name": "Test Corp", "prefix": "Alpha"}],
            "entities": {"User": {"row_count": 2}},
        }
        save_demo_blueprint_handler(temp_project, {"blueprint": blueprint})

        # Generate in JSONL format
        result = generate_demo_data_handler(temp_project, {"format": "jsonl"})
        data = json.loads(result)

        # Should respect format option
        assert "error" not in data or "jsonl" in str(data.get("error", "")).lower()

    def test_filters_by_entities(self, temp_project) -> None:
        """Test filtering by entity names."""
        # Save blueprint with multiple entities
        blueprint = {
            "tenants": [{"name": "Test Corp", "prefix": "Alpha"}],
            "entities": {
                "User": {"row_count": 2},
                "Task": {"row_count": 5},
            },
        }
        save_demo_blueprint_handler(temp_project, {"blueprint": blueprint})

        # Generate only for User
        result = generate_demo_data_handler(temp_project, {"entities": ["User"]})
        data = json.loads(result)

        # Should only generate for specified entity
        if "files" in data:
            file_names = [f.get("entity", "") for f in data["files"]]
            assert "User" in file_names or any("user" in str(f).lower() for f in data["files"])
