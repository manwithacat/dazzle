"""Tests for the stories MCP handlers."""

import importlib.util
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest


def _import_stories():
    """Import stories handlers directly to avoid MCP package init issues.

    The dazzle.mcp.__init__.py imports mcp.server which may not be installed
    in test environments. We need to import the handlers module directly.
    """
    # Create mock modules to satisfy imports
    mock_state = MagicMock()
    sys.modules["dazzle.mcp.server.handlers"] = MagicMock(pytest_plugins=[])

    # Build a common mock with real implementations for DSL loading
    from types import ModuleType

    from dazzle.core.fileset import discover_dsl_files
    from dazzle.core.linker import build_appspec
    from dazzle.core.manifest import load_manifest
    from dazzle.core.parser import parse_modules

    common_mock = ModuleType("dazzle.mcp.server.handlers.common")

    def _extract_progress(args=None):
        ctx = MagicMock()
        ctx.log_sync = MagicMock()
        return ctx

    def _load_project_appspec(project_root):
        manifest = load_manifest(project_root / "dazzle.toml")
        dsl_files = discover_dsl_files(project_root, manifest)
        modules = parse_modules(dsl_files)
        return build_appspec(modules, manifest.project_root)

    def _error_response(msg):
        return json.dumps({"error": msg})

    def _unknown_op_response(operation, tool):
        return json.dumps({"error": f"Unknown {tool} operation: {operation}"})

    common_mock.error_response = _error_response
    common_mock.unknown_op_response = _unknown_op_response
    common_mock.extract_progress = _extract_progress
    common_mock.load_project_appspec = _load_project_appspec

    def _handler_error_json(fn):
        """Decorator that catches exceptions and returns JSON error."""
        from functools import wraps

        @wraps(fn)
        def wrapper(*a, **kw):
            try:
                return fn(*a, **kw)
            except Exception as exc:
                return json.dumps({"error": str(exc)})

        return wrapper

    common_mock.handler_error_json = _handler_error_json
    common_mock.wrap_handler_errors = _handler_error_json
    sys.modules["dazzle.mcp.server.handlers.common"] = common_mock
    sys.modules["dazzle.mcp.server.state"] = mock_state
    sys.modules.setdefault("dazzle.mcp", MagicMock(pytest_plugins=[]))
    sys.modules.setdefault("dazzle.mcp.server", MagicMock(pytest_plugins=[]))
    sys.modules.setdefault("dazzle.mcp.server.progress", MagicMock(pytest_plugins=[]))

    # Pre-load the serializers module so stories.py's `from .serializers import ...` resolves
    handlers_dir = (
        Path(__file__).parent.parent.parent.parent
        / "src"
        / "dazzle"
        / "mcp"
        / "server"
        / "handlers"
    )
    ser_path = handlers_dir / "serializers.py"
    ser_spec = importlib.util.spec_from_file_location(
        "dazzle.mcp.server.handlers.serializers",
        ser_path,
    )
    ser_mod = importlib.util.module_from_spec(ser_spec)
    sys.modules["dazzle.mcp.server.handlers.serializers"] = ser_mod
    ser_spec.loader.exec_module(ser_mod)

    # Attach serializers to the handlers mock so relative import resolves
    sys.modules["dazzle.mcp.server.handlers"].serializers = ser_mod

    module_path = (
        Path(__file__).parent.parent.parent.parent
        / "src"
        / "dazzle"
        / "mcp"
        / "server"
        / "handlers"
        / "stories.py"
    )
    spec = importlib.util.spec_from_file_location(
        "dazzle.mcp.server.handlers.stories",
        module_path,
    )
    module = importlib.util.module_from_spec(spec)

    # Set up the package structure for relative imports
    sys.modules["dazzle.mcp.server.handlers.stories"] = module

    spec.loader.exec_module(module)
    return module


# Import the module once at module load time
_stories = _import_stories()

# Get references to the functions we need
get_dsl_spec_handler = _stories.get_dsl_spec_handler
get_stories_handler = _stories.get_stories_handler
# Serializers are in the shared serializers module (loaded during _import_stories)
_ser = sys.modules["dazzle.mcp.server.handlers.serializers"]
_serialize_story_summary = _ser.serialize_story_summary
_serialize_story = _ser.serialize_story


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

    # Create main.dsl
    main_dsl = dsl_dir / "main.dsl"
    main_dsl.write_text(
        """
module test_project
app test_project "Test Project"

entity Task "Task":
    id: uuid pk
    title: str(200) required
    status: enum[pending,in_progress,completed]=pending

    transitions:
        pending -> in_progress
        in_progress -> completed

entity Note "Note":
    id: uuid pk
    body: str(200)

surface task_list "Tasks":
    uses entity Task
    mode: list
    section main:
        field title "Title"
"""
    )

    # Create .dazzle directory
    dazzle_dir = project_dir / ".dazzle"
    dazzle_dir.mkdir()

    return project_dir


@pytest.fixture
def mock_story():
    """Create a mock StorySpec object with Gherkin fields."""
    from dazzle.core.ir.stories import StoryCondition, StorySpec, StoryStatus, StoryTrigger

    return StorySpec(
        story_id="ST-001",
        title="User creates a new Task",
        persona="User",
        trigger=StoryTrigger.FORM_SUBMITTED,
        entities=["Task"],
        given=[StoryCondition(expression="User has permission to create Task")],
        when=[],
        then=[StoryCondition(expression="New Task is saved to database")],
        status=StoryStatus.DRAFT,
    )


# =============================================================================
# Serialization Tests
# =============================================================================


def test_serialize_story_summary_is_compact(mock_story) -> None:
    """The summary carries identity, persona, status and entities — no Gherkin."""
    assert _serialize_story_summary(mock_story) == {
        "story_id": "ST-001",
        "title": "User creates a new Task",
        "persona": "User",
        "status": "draft",
        "entities": ["Task"],
    }


def test_serialize_story_includes_gherkin(mock_story) -> None:
    result = _serialize_story(mock_story)
    assert result["story_id"] == "ST-001"
    assert result["trigger"] == "form_submitted"
    assert [c["expression"] for c in result["given"]] == ["User has permission to create Task"]
    assert [c["expression"] for c in result["then"]] == ["New Task is saved to database"]


# =============================================================================
# Handler Tests
# =============================================================================


def test_get_dsl_spec_summaries(temp_project) -> None:
    """Default call returns compact entity/surface summaries; states appear only
    for entities with a state machine."""
    data = json.loads(get_dsl_spec_handler(temp_project, {}))
    assert data["app_name"] == "test_project"
    assert data["project_path"] == str(temp_project)
    entities = {e["name"]: e for e in data["entities"]}
    assert entities["Task"]["field_count"] == 3
    assert entities["Task"]["has_state_machine"] is True
    assert entities["Task"]["states"] == ["pending", "in_progress", "completed"]
    assert entities["Note"]["has_state_machine"] is False
    assert "states" not in entities["Note"]
    # Framework admin surfaces (``_admin_*``) are linked in alongside the app's own.
    (task_list,) = [s for s in data["surfaces"] if s["name"] == "task_list"]
    assert task_list == {"name": "task_list", "title": "Tasks", "entity": "Task", "mode": "list"}


def test_get_dsl_spec_details_for_named_items(temp_project) -> None:
    data = json.loads(
        get_dsl_spec_handler(
            temp_project, {"entity_names": ["Task"], "surface_names": ["task_list"]}
        )
    )
    (task,) = data["entities"]
    assert [f["name"] for f in task["fields"]] == ["id", "title", "status"]
    assert task["state_machine"]["field"] == "status"
    assert len(task["state_machine"]["transitions"]) == 2
    (surface,) = data["surfaces"]
    assert [sec["name"] for sec in surface["sections"]] == ["main"]


def test_get_dsl_spec_missing_project(tmp_path) -> None:
    assert "error" in json.loads(get_dsl_spec_handler(tmp_path, {}))


_STORY_DSL = """
story ST-001 "Test Story":
  {status}persona: User
  trigger: form_submitted
  entities: [Task]
  given:
    - "User has permission"
  then:
    - "Task is saved"
"""


def test_get_stories_empty(temp_project) -> None:
    assert json.loads(get_stories_handler(temp_project, {}))["count"] == 0


@pytest.mark.parametrize(
    ("status_filter", "count"),
    [
        pytest.param("accepted", 1, id="matching-status"),
        pytest.param("draft", 0, id="other-status"),
    ],
)
def test_get_stories_status_filter(temp_project, status_filter: str, count: int) -> None:
    (temp_project / "dsl" / "stories.dsl").write_text(
        _STORY_DSL.format(status="status: accepted\n  ")
    )
    data = json.loads(get_stories_handler(temp_project, {"status_filter": status_filter}))
    assert data["count"] == count


def test_get_stories_full_details_for_story_ids(temp_project) -> None:
    (temp_project / "dsl" / "stories.dsl").write_text(_STORY_DSL.format(status=""))
    data = json.loads(get_stories_handler(temp_project, {"story_ids": ["ST-001"]}))
    assert data["count"] == 1
    assert [c["expression"] for c in data["stories"][0]["given"]] == ["User has permission"]
