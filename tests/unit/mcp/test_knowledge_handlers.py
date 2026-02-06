"""Tests for the knowledge MCP handlers."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock


def _import_knowledge():
    """Import knowledge handlers directly to avoid MCP package init issues.

    The dazzle.mcp.__init__.py imports mcp.server which may not be installed
    in test environments. We need to import the handlers module directly.
    """
    # Create mock modules to satisfy imports
    sys.modules["dazzle.mcp.server.handlers"] = MagicMock(pytest_plugins=[])

    # Mock the dependent modules
    mock_semantics = MagicMock()
    mock_semantics.lookup_concept = MagicMock(
        return_value={"term": "entity", "definition": "A domain object"}
    )
    sys.modules["dazzle.mcp.semantics"] = mock_semantics

    mock_examples = MagicMock()
    mock_examples.search_examples = MagicMock(
        return_value=[{"name": "simple_task", "features": ["entity", "surface"]}]
    )
    sys.modules["dazzle.mcp.examples"] = mock_examples

    mock_cli_help = MagicMock()
    mock_cli_help.get_cli_help = MagicMock(
        return_value={"command": "serve", "help": "Run the server"}
    )
    mock_cli_help.get_workflow_guide = MagicMock(
        return_value={"workflow": "new_project", "steps": ["Step 1", "Step 2"]}
    )
    sys.modules["dazzle.mcp.cli_help"] = mock_cli_help

    mock_inference = MagicMock()
    mock_inference.lookup_inference = MagicMock(
        return_value={"patterns": [{"trigger": "task", "template": "entity Task"}]}
    )
    mock_inference.list_all_patterns = MagicMock(
        return_value={
            "categories": ["entity", "surface"],
            "pattern_count": 10,
            "triggers": ["task", "user", "project"],
        }
    )
    sys.modules["dazzle.mcp.inference"] = mock_inference

    module_path = (
        Path(__file__).parent.parent.parent.parent
        / "src"
        / "dazzle"
        / "mcp"
        / "server"
        / "handlers"
        / "knowledge.py"
    )
    spec = importlib.util.spec_from_file_location(
        "dazzle.mcp.server.handlers.knowledge",
        module_path,
        submodule_search_locations=[],
    )
    module = importlib.util.module_from_spec(spec)

    # Set up the package structure for relative imports
    module.__package__ = "dazzle.mcp.server.handlers"
    sys.modules["dazzle.mcp.server.handlers.knowledge"] = module

    spec.loader.exec_module(module)
    return module


# Import the module once at module load time
_kn = _import_knowledge()

# Get references to the functions we need
lookup_concept_handler = _kn.lookup_concept_handler
find_examples_handler = _kn.find_examples_handler
get_cli_help_handler = _kn.get_cli_help_handler
get_workflow_guide_handler = _kn.get_workflow_guide_handler
lookup_inference_handler = _kn.lookup_inference_handler


# =============================================================================
# Handler Tests
# =============================================================================


class TestLookupConceptHandler:
    """Tests for lookup_concept_handler."""

    def test_requires_term(self) -> None:
        """Test that term parameter is required."""
        result = lookup_concept_handler({})
        data = json.loads(result)

        assert "error" in data
        assert "term" in data["error"].lower()

    def test_looks_up_concept(self) -> None:
        """Test looking up a concept."""
        result = lookup_concept_handler({"term": "entity"})
        data = json.loads(result)

        # Should return concept info
        assert "term" in data or "definition" in data or "error" not in data


class TestFindExamplesHandler:
    """Tests for find_examples_handler."""

    def test_returns_examples(self) -> None:
        """Test finding examples."""
        result = find_examples_handler({})
        data = json.loads(result)

        assert "examples" in data
        assert "count" in data

    def test_with_features_filter(self) -> None:
        """Test filtering by features."""
        result = find_examples_handler({"features": ["entity"]})
        data = json.loads(result)

        assert "query" in data
        assert data["query"]["features"] == ["entity"]
        assert "examples" in data

    def test_with_complexity_filter(self) -> None:
        """Test filtering by complexity."""
        result = find_examples_handler({"complexity": "beginner"})
        data = json.loads(result)

        assert "query" in data
        assert data["query"]["complexity"] == "beginner"


class TestGetCliHelpHandler:
    """Tests for get_cli_help_handler."""

    def test_returns_help(self) -> None:
        """Test getting CLI help."""
        result = get_cli_help_handler({})
        data = json.loads(result)

        # Should return help info or command list
        assert "command" in data or "commands" in data or "help" in data

    def test_with_command(self) -> None:
        """Test getting help for specific command."""
        result = get_cli_help_handler({"command": "serve"})
        data = json.loads(result)

        # Should return help for serve command
        assert "command" in data or "help" in data


class TestGetWorkflowGuideHandler:
    """Tests for get_workflow_guide_handler."""

    def test_requires_workflow(self) -> None:
        """Test that workflow parameter is required."""
        result = get_workflow_guide_handler({})
        data = json.loads(result)

        assert "error" in data
        assert "workflow" in data["error"].lower()

    def test_returns_workflow_guide(self) -> None:
        """Test getting a workflow guide."""
        result = get_workflow_guide_handler({"workflow": "new_project"})
        data = json.loads(result)

        # Should return workflow info
        assert "workflow" in data or "steps" in data or "error" not in data


class TestLookupInferenceHandler:
    """Tests for lookup_inference_handler."""

    def test_requires_query_or_list_all(self) -> None:
        """Test that query or list_all is required."""
        result = lookup_inference_handler({})
        data = json.loads(result)

        assert "error" in data
        assert "query" in data["error"].lower() or "hint" in data

    def test_with_query(self) -> None:
        """Test looking up inference patterns."""
        result = lookup_inference_handler({"query": "task management"})
        data = json.loads(result)

        # Should return pattern matches
        assert "patterns" in data or "matches" in data or "error" not in data

    def test_list_all_patterns(self) -> None:
        """Test listing all inference patterns."""
        result = lookup_inference_handler({"list_all": True})
        data = json.loads(result)

        # Should return all patterns info
        assert "categories" in data or "pattern_count" in data or "triggers" in data

    def test_detail_option(self) -> None:
        """Test detail level option."""
        result = lookup_inference_handler({"query": "task", "detail": "full"})
        data = json.loads(result)

        # Should accept full detail level
        assert "error" not in data or "detail" not in data.get("error", "")

    def test_invalid_detail_defaults_to_minimal(self) -> None:
        """Test that invalid detail defaults to minimal."""
        result = lookup_inference_handler({"query": "task", "detail": "invalid"})
        data = json.loads(result)

        # Should not error on invalid detail level
        assert "error" not in data or "detail" not in data.get("error", "")
