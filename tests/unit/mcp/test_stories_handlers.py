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
_serialize_entity_summary = _ser.serialize_entity_summary
_serialize_entity_detail = _ser.serialize_entity_detail
_serialize_surface_summary = _ser.serialize_surface_summary
_serialize_surface_detail = _ser.serialize_surface_detail


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


@pytest.fixture
def mock_entity():
    """Create a mock entity object."""
    entity = MagicMock()
    entity.name = "Task"
    entity.title = "Task"
    entity.fields = [
        MagicMock(name="title", type=MagicMock(kind=MagicMock(value="str")), is_required=True),
        MagicMock(name="status", type=MagicMock(kind=MagicMock(value="str")), is_required=False),
    ]
    entity.state_machine = MagicMock()
    entity.state_machine.status_field = "status"
    entity.state_machine.states = ["pending", "in_progress", "completed"]
    entity.state_machine.transitions = [
        MagicMock(from_state="pending", to_state="in_progress", trigger=MagicMock(value="start")),
    ]
    return entity


@pytest.fixture
def mock_surface():
    """Create a mock surface object."""
    surface = MagicMock()
    surface.name = "task_list"
    surface.title = "Tasks"
    surface.entity_ref = "Task"
    surface.mode = MagicMock(value="list")
    surface.sections = []
    return surface


# =============================================================================
# Serialization Tests
# =============================================================================


class TestSerializeStorySummary:
    """Tests for story summary serialization."""

    def test_serializes_basic_fields(self, mock_story) -> None:
        """Test that summary includes essential fields."""
        result = _serialize_story_summary(mock_story)

        assert result["story_id"] == "ST-001"
        assert result["title"] == "User creates a new Task"
        assert result["persona"] == "User"
        assert result["status"] == "draft"
        assert result["entities"] == ["Task"]

    def test_excludes_detailed_fields(self, mock_story) -> None:
        """Test that summary excludes detailed fields."""
        result = _serialize_story_summary(mock_story)

        # Gherkin fields should not be in summary
        assert "given" not in result
        assert "when" not in result
        assert "then" not in result


class TestSerializeStory:
    """Tests for full story serialization."""

    def test_serializes_all_fields(self, mock_story) -> None:
        """Test that full serialization includes Gherkin fields."""
        result = _serialize_story(mock_story)

        assert result["story_id"] == "ST-001"
        assert result["title"] == "User creates a new Task"
        assert result["trigger"] == "form_submitted"
        # Gherkin fields
        assert len(result["given"]) == 1
        assert result["given"][0]["expression"] == "User has permission to create Task"
        assert len(result["then"]) == 1
        assert result["then"][0]["expression"] == "New Task is saved to database"


class TestSerializeEntitySummary:
    """Tests for entity summary serialization."""

    def test_serializes_entity_info(self, mock_entity) -> None:
        """Test entity summary serialization."""
        result = _serialize_entity_summary(mock_entity)

        assert result["name"] == "Task"
        assert result["title"] == "Task"
        assert result["field_count"] == 2
        assert result["has_state_machine"] is True
        assert "states" in result

    def test_handles_no_state_machine(self) -> None:
        """Test entity without state machine."""
        entity = MagicMock()
        entity.name = "User"
        entity.title = "User"
        entity.fields = []
        entity.state_machine = None

        result = _serialize_entity_summary(entity)

        assert result["has_state_machine"] is False
        assert "states" not in result


class TestSerializeEntityDetail:
    """Tests for entity detail serialization."""

    def test_includes_fields(self, mock_entity) -> None:
        """Test that detail includes field information."""
        result = _serialize_entity_detail(mock_entity)

        assert result["name"] == "Task"
        assert "fields" in result
        assert len(result["fields"]) == 2

    def test_includes_state_machine_transitions(self, mock_entity) -> None:
        """Test that state machine includes transitions."""
        result = _serialize_entity_detail(mock_entity)

        assert "state_machine" in result
        sm = result["state_machine"]
        assert sm["field"] == "status"
        assert len(sm["transitions"]) == 1


class TestSerializeSurfaceSummary:
    """Tests for surface summary serialization."""

    def test_serializes_surface_info(self, mock_surface) -> None:
        """Test surface summary serialization."""
        result = _serialize_surface_summary(mock_surface)

        assert result["name"] == "task_list"
        assert result["title"] == "Tasks"
        assert result["entity"] == "Task"
        assert result["mode"] == "list"


class TestSerializeSurfaceDetail:
    """Tests for surface detail serialization."""

    def test_includes_sections(self) -> None:
        """Test that detail includes section information."""
        surface = MagicMock()
        surface.name = "task_form"
        surface.title = "Task Form"
        surface.entity_ref = "Task"
        surface.mode = MagicMock(value="detail")

        section = MagicMock()
        section.name = "main"
        section.fields = [MagicMock(name="title", title="Title")]
        surface.sections = [section]

        result = _serialize_surface_detail(surface)

        assert "sections" in result
        assert len(result["sections"]) == 1
        assert result["sections"][0]["name"] == "main"


# =============================================================================
# Helper Function Tests
# =============================================================================


# =============================================================================
# Handler Tests
# =============================================================================


class TestGetDslSpecHandler:
    """Tests for get_dsl_spec_handler."""

    def test_returns_spec_summary(self, temp_project) -> None:
        """Test getting DSL spec summary."""
        result = get_dsl_spec_handler(temp_project, {})
        data = json.loads(result)

        assert "project_path" in data
        assert "app_name" in data
        assert "entities" in data
        assert "surfaces" in data

    def test_returns_entity_detail_when_requested(self, temp_project) -> None:
        """Test getting specific entity details."""
        result = get_dsl_spec_handler(temp_project, {"entity_names": ["Task"]})
        data = json.loads(result)

        assert "entities" in data
        # Should return detail, not summary
        if data.get("entities"):
            entity = data["entities"][0]
            assert "fields" in entity  # Detail has fields

    def test_handles_missing_project(self, tmp_path) -> None:
        """Test handling of missing project."""
        missing_project = tmp_path / "missing"
        missing_project.mkdir()

        result = get_dsl_spec_handler(missing_project, {})
        data = json.loads(result)

        assert "error" in data


class TestGetStoriesHandler:
    """Tests for get_stories_handler."""

    def test_returns_empty_for_no_stories(self, temp_project) -> None:
        """Test handling of no stories."""
        result = get_stories_handler(temp_project, {})
        data = json.loads(result)

        assert "count" in data
        assert data["count"] == 0

    def test_filters_by_status(self, temp_project) -> None:
        """Test filtering stories by status."""
        # Write a story DSL file with accepted status
        dsl_dir = temp_project / "dsl"
        stories_dsl = dsl_dir / "stories.dsl"
        stories_dsl.write_text(
            """
story ST-001 "Test Story":
  status: accepted
  persona: User
  trigger: form_submitted
  entities: [Task]
  given:
    - "User has permission"
  then:
    - "Task is saved"
"""
        )

        # Get only accepted stories
        result = get_stories_handler(temp_project, {"status_filter": "accepted"})
        data = json.loads(result)

        assert data["count"] == 1

    def test_returns_full_details_for_story_ids(self, temp_project) -> None:
        """Test getting full story details by ID."""
        # Write a story DSL file
        dsl_dir = temp_project / "dsl"
        stories_dsl = dsl_dir / "stories.dsl"
        stories_dsl.write_text(
            """
story ST-001 "Test Story":
  persona: User
  trigger: form_submitted
  entities: [Task]
  given:
    - "User has permission"
  then:
    - "Task is saved"
"""
        )

        result = get_stories_handler(temp_project, {"story_ids": ["ST-001"]})
        data = json.loads(result)

        assert data["count"] == 1
        story = data["stories"][0]
        # Full details should include Gherkin fields
        assert "given" in story
        assert len(story["given"]) == 1
