"""Tests for the feedback MCP handlers."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest


def _import_feedback():
    """Import feedback handlers directly to avoid MCP package init issues.

    The dazzle.mcp.__init__.py imports mcp.server which may not be installed
    in test environments. We need to import the handlers module directly.
    """
    # Create mock modules to satisfy imports
    mock_state = MagicMock()
    mock_state.get_project_path = MagicMock(return_value=Path("/tmp/test_project"))
    sys.modules["dazzle.mcp.server.handlers"] = MagicMock(pytest_plugins=[])
    sys.modules["dazzle.mcp.server.state"] = mock_state

    # Create mock feedback entry
    mock_entry = MagicMock()
    mock_entry.model_dump = MagicMock(
        return_value={
            "id": "abc12345",
            "timestamp": "2025-01-01T00:00:00Z",
            "message": "Test feedback",
            "category": "Bug Report",
            "route": "/tasks",
            "status": "new",
        }
    )

    # Mock FeedbackLogger
    mock_feedback_logger = MagicMock()
    mock_feedback_logger.list_feedback = MagicMock(return_value=[mock_entry])
    mock_feedback_logger.get_feedback = MagicMock(return_value=mock_entry)
    mock_feedback_logger.update_feedback_status = MagicMock(return_value=True)
    mock_feedback_logger.get_summary = MagicMock(
        return_value={
            "total": 5,
            "unaddressed": 3,
            "by_status": {"new": 2, "acknowledged": 1},
            "by_category": {"Bug Report": 2, "Feature Request": 1},
        }
    )

    mock_control_plane = MagicMock()
    mock_control_plane.FeedbackLogger = MagicMock(return_value=mock_feedback_logger)
    sys.modules["dazzle_back.runtime.control_plane"] = mock_control_plane

    # Mock github_issues
    mock_github = MagicMock()
    mock_github.gh_auth_guidance = MagicMock(
        return_value={"status": "authenticated", "user": "test"}
    )
    sys.modules["dazzle.mcp.server.github_issues"] = mock_github

    module_path = (
        Path(__file__).parent.parent.parent.parent
        / "src"
        / "dazzle"
        / "mcp"
        / "server"
        / "handlers"
        / "feedback.py"
    )
    spec = importlib.util.spec_from_file_location(
        "dazzle.mcp.server.handlers.feedback",
        module_path,
        submodule_search_locations=[],
    )
    module = importlib.util.module_from_spec(spec)

    # Set up the package structure for relative imports
    module.__package__ = "dazzle.mcp.server.handlers"
    sys.modules["dazzle.mcp.server.handlers.feedback"] = module

    spec.loader.exec_module(module)
    return module


# Import the module once at module load time
_fb = _import_feedback()

# Get references to the functions we need
list_feedback_handler = _fb.list_feedback_handler
get_feedback_handler = _fb.get_feedback_handler
update_feedback_handler = _fb.update_feedback_handler
get_feedback_summary_handler = _fb.get_feedback_summary_handler


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def temp_project(tmp_path):
    """Create a temporary project with feedback directory."""
    project_dir = tmp_path / "test_project"
    project_dir.mkdir()

    # Create .dazzle/feedback directory
    feedback_dir = project_dir / ".dazzle" / "feedback"
    feedback_dir.mkdir(parents=True)

    return project_dir


# =============================================================================
# Handler Tests
# =============================================================================


class TestListFeedbackHandler:
    """Tests for list_feedback_handler."""

    @pytest.mark.asyncio
    async def test_lists_feedback(self, temp_project) -> None:
        """Test listing feedback entries."""
        result = await list_feedback_handler(project_path=str(temp_project))

        assert "count" in result
        assert "entries" in result
        assert "filters" in result

    @pytest.mark.asyncio
    async def test_filters_by_status(self, temp_project) -> None:
        """Test filtering by status."""
        result = await list_feedback_handler(status="new", project_path=str(temp_project))

        assert result["filters"]["status"] == "new"

    @pytest.mark.asyncio
    async def test_filters_by_category(self, temp_project) -> None:
        """Test filtering by category."""
        result = await list_feedback_handler(category="Bug Report", project_path=str(temp_project))

        assert result["filters"]["category"] == "Bug Report"

    @pytest.mark.asyncio
    async def test_respects_limit(self, temp_project) -> None:
        """Test limit parameter."""
        result = await list_feedback_handler(limit=5, project_path=str(temp_project))

        assert result["filters"]["limit"] == 5


class TestGetFeedbackHandler:
    """Tests for get_feedback_handler."""

    @pytest.mark.asyncio
    async def test_gets_feedback_by_id(self, temp_project) -> None:
        """Test getting feedback by ID."""
        result = await get_feedback_handler(feedback_id="abc12345", project_path=str(temp_project))

        assert "feedback" in result
        assert result["feedback"]["id"] == "abc12345"

    @pytest.mark.asyncio
    async def test_returns_error_for_not_found(self, temp_project) -> None:
        """Test error when feedback not found."""
        # Modify the mock to return None for get_feedback
        mock_logger_instance = MagicMock()
        mock_logger_instance.get_feedback = MagicMock(return_value=None)

        # Access the mocked control_plane module we set up during import
        control_plane_mock = sys.modules["dazzle_back.runtime.control_plane"]
        original_logger = control_plane_mock.FeedbackLogger
        control_plane_mock.FeedbackLogger = MagicMock(return_value=mock_logger_instance)

        try:
            result = await get_feedback_handler(
                feedback_id="notfound", project_path=str(temp_project)
            )

            assert "error" in result
            assert "not found" in result["error"].lower()
        finally:
            control_plane_mock.FeedbackLogger = original_logger


class TestUpdateFeedbackHandler:
    """Tests for update_feedback_handler."""

    @pytest.mark.asyncio
    async def test_updates_status(self, temp_project) -> None:
        """Test updating feedback status."""
        result = await update_feedback_handler(
            feedback_id="abc12345", status="acknowledged", project_path=str(temp_project)
        )

        assert result["status"] == "updated"
        assert result["new_status"] == "acknowledged"

    @pytest.mark.asyncio
    async def test_rejects_invalid_status(self, temp_project) -> None:
        """Test rejection of invalid status."""
        result = await update_feedback_handler(
            feedback_id="abc12345", status="invalid_status", project_path=str(temp_project)
        )

        assert "error" in result
        assert "invalid" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_accepts_notes(self, temp_project) -> None:
        """Test adding notes to update."""
        result = await update_feedback_handler(
            feedback_id="abc12345",
            status="addressed",
            notes="Fixed in PR #123",
            project_path=str(temp_project),
        )

        assert result["notes"] == "Fixed in PR #123"

    @pytest.mark.asyncio
    async def test_valid_statuses(self, temp_project) -> None:
        """Test all valid statuses are accepted."""
        for status in ["new", "acknowledged", "addressed", "wont_fix"]:
            result = await update_feedback_handler(
                feedback_id="abc12345", status=status, project_path=str(temp_project)
            )

            assert result["status"] == "updated"
            assert result["new_status"] == status


class TestGetFeedbackSummaryHandler:
    """Tests for get_feedback_summary_handler."""

    @pytest.mark.asyncio
    async def test_returns_summary(self, temp_project) -> None:
        """Test getting feedback summary."""
        result = await get_feedback_summary_handler(project_path=str(temp_project))

        assert "total" in result
        assert "by_status" in result or "unaddressed" in result

    @pytest.mark.asyncio
    async def test_includes_guidance(self, temp_project) -> None:
        """Test that guidance is included."""
        result = await get_feedback_summary_handler(project_path=str(temp_project))

        assert "guidance" in result

    @pytest.mark.asyncio
    async def test_includes_github_workflow(self, temp_project) -> None:
        """Test that GitHub workflow info is included."""
        result = await get_feedback_summary_handler(project_path=str(temp_project))

        assert "github_issue_workflow" in result

    @pytest.mark.asyncio
    async def test_includes_local_log_path(self, temp_project) -> None:
        """Test that local log path is included."""
        result = await get_feedback_summary_handler(project_path=str(temp_project))

        assert "local_log" in result
        assert "feedback.jsonl" in result["local_log"]
