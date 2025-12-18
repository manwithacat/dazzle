"""
Unit tests for MCP process tools.

Tests cover:
- Story coverage analysis
- Process proposal generation
- Process inspection
- Process run listing
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from dazzle.core.ir.process import (
    ProcessSpec,
    ProcessStepSpec,
    ProcessTriggerKind,
    ProcessTriggerSpec,
    StepKind,
)
from dazzle.core.ir.stories import StoryCondition, StorySpec, StoryStatus, StoryTrigger


@pytest.fixture
def mock_app_spec_with_coverage() -> MagicMock:
    """Create a mock AppSpec with stories and processes."""
    app_spec = MagicMock()

    # Create stories
    app_spec.stories = [
        StorySpec(
            story_id="ST-001",
            title="User creates order",
            actor="User",
            trigger=StoryTrigger.FORM_SUBMITTED,
            scope=["Order"],
            then=[StoryCondition(expression="Order is saved to database")],
            status=StoryStatus.ACCEPTED,
        ),
        StorySpec(
            story_id="ST-002",
            title="User confirms order",
            actor="User",
            trigger=StoryTrigger.STATUS_CHANGED,
            scope=["Order"],
            then=[StoryCondition(expression="Order status changes to confirmed")],
            status=StoryStatus.ACCEPTED,
        ),
    ]

    # Create process that implements ST-001
    app_spec.processes = [
        ProcessSpec(
            name="order_creation",
            title="Order Creation Process",
            implements=["ST-001"],
            trigger=ProcessTriggerSpec(
                kind=ProcessTriggerKind.ENTITY_EVENT,
                entity_name="Order",
                event_type="created",
            ),
            steps=[
                ProcessStepSpec(
                    name="save_order",
                    kind=StepKind.SERVICE,
                    service="order_service",
                ),
            ],
        ),
    ]

    return app_spec


@pytest.fixture
def mock_app_spec_no_processes() -> MagicMock:
    """Create a mock AppSpec with stories but no processes."""
    app_spec = MagicMock()

    app_spec.stories = [
        StorySpec(
            story_id="ST-001",
            title="User starts task",
            actor="User",
            trigger=StoryTrigger.STATUS_CHANGED,
            scope=["Task"],
            then=[StoryCondition(expression="Task.started_at is recorded")],
            status=StoryStatus.ACCEPTED,
        ),
        StorySpec(
            story_id="ST-002",
            title="User completes task",
            actor="User",
            trigger=StoryTrigger.STATUS_CHANGED,
            scope=["Task"],
            then=[StoryCondition(expression="User receives notification")],
            status=StoryStatus.ACCEPTED,
        ),
    ]

    app_spec.processes = []

    return app_spec


@pytest.fixture
def mock_app_spec_no_stories() -> MagicMock:
    """Create a mock AppSpec with no stories."""
    app_spec = MagicMock()
    app_spec.stories = []
    app_spec.processes = []
    return app_spec


class TestStoriesCoverage:
    """Tests for stories_coverage handler."""

    def test_coverage_with_processes(
        self, mock_app_spec_with_coverage: MagicMock, tmp_path: Path
    ) -> None:
        """Test coverage analysis with some processes defined."""
        from dazzle.mcp.server.handlers.process import stories_coverage_handler

        with patch(
            "dazzle.mcp.server.handlers.process._load_app_spec",
            return_value=mock_app_spec_with_coverage,
        ):
            result = stories_coverage_handler(tmp_path, {})
            data = json.loads(result)

        assert "error" not in data
        assert data["total_stories"] == 2
        assert data["covered"] >= 1  # ST-001 is covered
        assert data["uncovered"] >= 1  # ST-002 is not covered
        assert len(data["stories"]) == 2

        # Check coverage details
        story_map = {s["story_id"]: s for s in data["stories"]}
        # ST-001 has a process
        assert story_map["ST-001"]["implementing_processes"] == ["order_creation"]
        # ST-002 has no process
        assert story_map["ST-002"]["status"] == "uncovered"

    def test_coverage_without_processes(
        self, mock_app_spec_no_processes: MagicMock, tmp_path: Path
    ) -> None:
        """Test coverage when no processes are defined."""
        from dazzle.mcp.server.handlers.process import stories_coverage_handler

        with patch(
            "dazzle.mcp.server.handlers.process._load_app_spec",
            return_value=mock_app_spec_no_processes,
        ):
            result = stories_coverage_handler(tmp_path, {})
            data = json.loads(result)

        assert "error" not in data
        assert data["total_stories"] == 2
        assert data["uncovered"] == 2
        assert data["coverage_percent"] == 0.0

        for story in data["stories"]:
            assert story["status"] == "uncovered"
            assert "No implementing process" in story["missing_aspects"]

    def test_coverage_no_stories(self, mock_app_spec_no_stories: MagicMock, tmp_path: Path) -> None:
        """Test coverage when no stories exist."""
        from dazzle.mcp.server.handlers.process import stories_coverage_handler

        with patch(
            "dazzle.mcp.server.handlers.process._load_app_spec",
            return_value=mock_app_spec_no_stories,
        ):
            result = stories_coverage_handler(tmp_path, {})
            data = json.loads(result)

        assert "error" in data
        assert "No stories found" in data["error"]


class TestProposeProcesses:
    """Tests for propose_processes_from_stories handler."""

    def test_propose_for_uncovered_stories(
        self, mock_app_spec_no_processes: MagicMock, tmp_path: Path
    ) -> None:
        """Test proposing processes for uncovered stories."""
        from dazzle.mcp.server.handlers.process import propose_processes_handler

        with patch(
            "dazzle.mcp.server.handlers.process._load_app_spec",
            return_value=mock_app_spec_no_processes,
        ):
            result = propose_processes_handler(tmp_path, {})
            data = json.loads(result)

        assert "error" not in data
        assert data["proposed_count"] == 2

        for proposal in data["proposals"]:
            assert "name" in proposal
            assert "title" in proposal
            assert "implements" in proposal
            assert "dsl_code" in proposal
            assert "process" in proposal["dsl_code"]

    def test_propose_for_specific_story(
        self, mock_app_spec_no_processes: MagicMock, tmp_path: Path
    ) -> None:
        """Test proposing process for a specific story."""
        from dazzle.mcp.server.handlers.process import propose_processes_handler

        with patch(
            "dazzle.mcp.server.handlers.process._load_app_spec",
            return_value=mock_app_spec_no_processes,
        ):
            result = propose_processes_handler(tmp_path, {"story_ids": ["ST-001"]})
            data = json.loads(result)

        assert "error" not in data
        assert data["proposed_count"] == 1
        assert data["proposals"][0]["implements"] == ["ST-001"]

    def test_propose_all_covered(
        self, mock_app_spec_with_coverage: MagicMock, tmp_path: Path
    ) -> None:
        """Test proposing when some stories are covered."""
        from dazzle.mcp.server.handlers.process import propose_processes_handler

        with patch(
            "dazzle.mcp.server.handlers.process._load_app_spec",
            return_value=mock_app_spec_with_coverage,
        ):
            result = propose_processes_handler(tmp_path, {})
            data = json.loads(result)

        # ST-002 is still uncovered, so it should propose
        assert "error" not in data
        assert data["proposed_count"] >= 1


class TestListProcesses:
    """Tests for list_processes handler."""

    def test_list_processes(self, mock_app_spec_with_coverage: MagicMock, tmp_path: Path) -> None:
        """Test listing processes."""
        from dazzle.mcp.server.handlers.process import list_processes_handler

        with patch(
            "dazzle.mcp.server.handlers.process._load_app_spec",
            return_value=mock_app_spec_with_coverage,
        ):
            result = list_processes_handler(tmp_path, {})
            data = json.loads(result)

        assert "error" not in data
        assert data["count"] == 1

        proc = data["processes"][0]
        assert proc["name"] == "order_creation"
        assert proc["title"] == "Order Creation Process"
        assert proc["implements"] == ["ST-001"]
        assert proc["step_count"] == 1

    def test_list_processes_empty(
        self, mock_app_spec_no_processes: MagicMock, tmp_path: Path
    ) -> None:
        """Test listing when no processes exist."""
        from dazzle.mcp.server.handlers.process import list_processes_handler

        with patch(
            "dazzle.mcp.server.handlers.process._load_app_spec",
            return_value=mock_app_spec_no_processes,
        ):
            result = list_processes_handler(tmp_path, {})
            data = json.loads(result)

        assert "error" not in data
        assert data["count"] == 0
        assert data["processes"] == []


class TestInspectProcess:
    """Tests for inspect_process handler."""

    def test_inspect_existing_process(
        self, mock_app_spec_with_coverage: MagicMock, tmp_path: Path
    ) -> None:
        """Test inspecting an existing process."""
        from dazzle.mcp.server.handlers.process import inspect_process_handler

        with patch(
            "dazzle.mcp.server.handlers.process._load_app_spec",
            return_value=mock_app_spec_with_coverage,
        ):
            result = inspect_process_handler(tmp_path, {"process_name": "order_creation"})
            data = json.loads(result)

        assert "error" not in data
        assert data["name"] == "order_creation"
        assert data["title"] == "Order Creation Process"
        assert data["implements"] == ["ST-001"]

        # Check linked stories
        assert len(data["linked_stories"]) == 1
        assert data["linked_stories"][0]["story_id"] == "ST-001"

        # Check trigger
        assert data["trigger"]["kind"] == "entity_event"

        # Check steps
        assert len(data["steps"]) == 1
        assert data["steps"][0]["name"] == "save_order"

    def test_inspect_nonexistent_process(
        self, mock_app_spec_with_coverage: MagicMock, tmp_path: Path
    ) -> None:
        """Test inspecting a non-existent process."""
        from dazzle.mcp.server.handlers.process import inspect_process_handler

        with patch(
            "dazzle.mcp.server.handlers.process._load_app_spec",
            return_value=mock_app_spec_with_coverage,
        ):
            result = inspect_process_handler(tmp_path, {"process_name": "nonexistent"})
            data = json.loads(result)

        assert "error" in data
        assert "not found" in data["error"]
        assert "available_processes" in data
        assert "order_creation" in data["available_processes"]

    def test_inspect_without_name(self, tmp_path: Path) -> None:
        """Test inspecting without providing process name."""
        from dazzle.mcp.server.handlers.process import inspect_process_handler

        result = inspect_process_handler(tmp_path, {})
        data = json.loads(result)

        assert "error" in data
        assert "process_name is required" in data["error"]


class TestProcessRunHandlers:
    """Tests for process run handlers."""

    @pytest.fixture
    def mock_empty_adapter(self) -> MagicMock:
        """Create a mock adapter that returns empty results."""
        from unittest.mock import AsyncMock

        adapter = MagicMock()
        adapter.initialize = AsyncMock(return_value=None)
        adapter.list_runs = AsyncMock(return_value=[])
        adapter.get_run = AsyncMock(return_value=None)
        return adapter

    @pytest.mark.asyncio
    async def test_list_runs_empty(self, tmp_path: Path, mock_empty_adapter: MagicMock) -> None:
        """Test listing runs when none exist."""
        from dazzle.mcp.server.handlers.process import _list_runs_async

        with patch(
            "dazzle.mcp.server.handlers.process._get_process_adapter",
            return_value=mock_empty_adapter,
        ):
            result = await _list_runs_async(tmp_path, {})
            data = json.loads(result)

        # Should return empty list, not error
        assert data["count"] == 0
        assert data["runs"] == []

    @pytest.mark.asyncio
    async def test_get_run_not_found(self, tmp_path: Path, mock_empty_adapter: MagicMock) -> None:
        """Test getting a non-existent run."""
        from dazzle.mcp.server.handlers.process import _get_run_async

        with patch(
            "dazzle.mcp.server.handlers.process._get_process_adapter",
            return_value=mock_empty_adapter,
        ):
            result = await _get_run_async(tmp_path, {"run_id": "nonexistent"})
            data = json.loads(result)

        assert "error" in data
        assert "not found" in data["error"]

    def test_get_run_no_id(self, tmp_path: Path) -> None:
        """Test getting run without providing ID."""
        from dazzle.mcp.server.handlers.process import get_process_run_handler

        result = get_process_run_handler(tmp_path, {})
        data = json.loads(result)

        assert "error" in data
        assert "run_id is required" in data["error"]


class TestToolSchemas:
    """Test that tool schemas are properly defined."""

    def test_process_tools_exist(self) -> None:
        """Test that process tools are defined in get_process_tools."""
        from dazzle.mcp.server.tools import get_process_tools

        tools = get_process_tools()
        tool_names = [t.name for t in tools]

        assert "stories_coverage" in tool_names
        assert "propose_processes_from_stories" in tool_names
        assert "list_processes" in tool_names
        assert "inspect_process" in tool_names
        assert "list_process_runs" in tool_names
        assert "get_process_run" in tool_names

    def test_tools_in_all_tools(self) -> None:
        """Test that process tools are included in get_all_tools."""
        from dazzle.mcp.server.tools import get_all_tools

        tools = get_all_tools()
        tool_names = [t.name for t in tools]

        assert "stories_coverage" in tool_names
        assert "propose_processes_from_stories" in tool_names
        assert "list_processes" in tool_names
        assert "inspect_process" in tool_names

    def test_tool_schemas_valid(self) -> None:
        """Test that tool input schemas are valid."""
        from dazzle.mcp.server.tools import get_process_tools

        for tool in get_process_tools():
            assert tool.inputSchema is not None
            assert tool.inputSchema["type"] == "object"
            assert "properties" in tool.inputSchema


class TestHelperFunctions:
    """Tests for helper functions in process handlers."""

    def test_slugify(self) -> None:
        """Test _slugify function."""
        from dazzle.mcp.server.handlers.process import _slugify

        assert _slugify("Hello World") == "hello_world"
        assert _slugify("Test-123-Value") == "test_123_value"
        assert _slugify("  spaced  text  ") == "spaced_text"

    def test_story_id_to_process_name(self) -> None:
        """Test _story_id_to_process_name function."""
        from dazzle.mcp.server.handlers.process import _story_id_to_process_name

        name = _story_id_to_process_name("ST-001", "User creates order")
        assert name.startswith("proc_")
        assert "st_001" in name
        assert "user_creates_order" in name
