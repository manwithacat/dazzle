"""Tests for the knowledge MCP handlers."""

import importlib.util
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from tests.unit.mcp.conftest import install_handlers_common_mock


def _import_knowledge():
    """Import knowledge handlers directly to avoid MCP package init issues.

    The dazzle.mcp.__init__.py imports mcp.server which may not be installed
    in test environments. We need to import the handlers module directly.
    """
    # Create mock modules to satisfy imports

    sys.modules["dazzle.mcp.server.handlers"] = MagicMock(pytest_plugins=[])
    install_handlers_common_mock()

    # Mock the dependent modules
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
    )
    module = importlib.util.module_from_spec(spec)
    module._test_mocks = {  # type: ignore[attr-defined]
        "examples": mock_examples,
        "cli_help": mock_cli_help,
        "inference": mock_inference,
    }

    # Set up the package structure for relative imports
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


_MOCKS = _kn._test_mocks


# =============================================================================
# Handler Tests
# =============================================================================


# Required-argument guards answer with an error naming the missing argument.
@pytest.mark.parametrize(
    ("handler", "missing"),
    [
        pytest.param(lookup_concept_handler, "term", id="concept-requires-term"),
        pytest.param(get_workflow_guide_handler, "workflow", id="workflow-requires-workflow"),
        pytest.param(lookup_inference_handler, "query", id="inference-requires-query-or-list-all"),
    ],
)
def test_required_argument_error(handler, missing: str) -> None:
    data = json.loads(handler({}))
    assert missing in data["error"].lower()


def test_lookup_concept_forwards_term() -> None:
    assert json.loads(lookup_concept_handler({"term": "entity"}))["term"] == "entity"


@pytest.mark.parametrize(
    "args",
    [
        pytest.param({}, id="no-filter"),
        pytest.param({"features": ["entity"]}, id="features-filter"),
        pytest.param({"complexity": "beginner"}, id="complexity-filter"),
    ],
)
def test_find_examples_echoes_query_and_counts(args: dict) -> None:
    data = json.loads(find_examples_handler(args))
    assert data["query"] == {
        "features": args.get("features"),
        "complexity": args.get("complexity"),
    }
    assert data["examples"] == [{"name": "simple_task", "features": ["entity", "surface"]}]
    assert data["count"] == 1
    _MOCKS["examples"].search_examples.assert_called_with(
        features=args.get("features"), complexity=args.get("complexity")
    )


@pytest.mark.parametrize("command", [None, "serve"], ids=["overview", "command"])
def test_cli_help_forwards_command(command: str | None) -> None:
    args = {"command": command} if command else {}
    data = json.loads(get_cli_help_handler(args))
    assert data == {"command": "serve", "help": "Run the server"}
    _MOCKS["cli_help"].get_cli_help.assert_called_with(command)


def test_workflow_guide_forwards_workflow() -> None:
    data = json.loads(get_workflow_guide_handler({"workflow": "new_project"}))
    assert data == {"workflow": "new_project", "steps": ["Step 1", "Step 2"]}
    _MOCKS["cli_help"].get_workflow_guide.assert_called_with("new_project")


def test_inference_list_all_returns_catalogue() -> None:
    data = json.loads(lookup_inference_handler({"list_all": True}))
    assert data["pattern_count"] == 10


# ``detail`` is forwarded when valid and normalised to "minimal" otherwise.
@pytest.mark.parametrize(
    ("args", "detail"),
    [
        pytest.param({"query": "task management"}, "minimal", id="default-minimal"),
        pytest.param({"query": "task", "detail": "full"}, "full", id="full-forwarded"),
        pytest.param({"query": "task", "detail": "invalid"}, "minimal", id="invalid-to-minimal"),
    ],
)
def test_inference_query_detail(args: dict, detail: str) -> None:
    data = json.loads(lookup_inference_handler(args))
    assert data == {"patterns": [{"trigger": "task", "template": "entity Task"}]}
    _MOCKS["inference"].lookup_inference.assert_called_with(args["query"], detail=detail)
