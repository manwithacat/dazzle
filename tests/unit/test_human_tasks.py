"""
Unit tests for human task integration (Phase 4).

Tests:
- TaskContext creation and rendering
- Task API routes
- Task inbox converter
- Escalation scheduler
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from dazzle.core.process.adapter import TaskStatus

# Check if FastAPI is available for route tests
try:
    import fastapi  # noqa: F401

    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False

# =============================================================================
# TaskContext Tests
# =============================================================================


class TestTaskContext:
    """Test TaskContext data class and methods."""

    def test_task_context_creation(self) -> None:
        """Test creating a TaskContext."""
        from dazzle_ui.runtime.task_context import TaskContext, TaskOutcome

        outcomes = [
            TaskOutcome(name="approve", label="Approve", style="primary"),
            TaskOutcome(name="reject", label="Reject", style="danger", confirm="Are you sure?"),
        ]

        context = TaskContext(
            task_id="task-123",
            process_name="approval_process",
            process_run_id="run-456",
            step_name="manager_review",
            surface_name="expense_detail",
            entity_name="Expense",
            entity_id="expense-789",
            due_at=datetime.now(UTC) + timedelta(days=1),
            outcomes=outcomes,
            assignee_id="user-1",
        )

        assert context.task_id == "task-123"
        assert context.process_name == "approval_process"
        assert len(context.outcomes) == 2
        assert context.outcomes[0].name == "approve"
        assert context.outcomes[1].confirm == "Are you sure?"

    def test_is_overdue_false(self) -> None:
        """Test is_overdue returns False for future due date."""
        from dazzle_ui.runtime.task_context import TaskContext

        context = TaskContext(
            task_id="task-1",
            process_name="test",
            process_run_id="run-1",
            step_name="step",
            surface_name="surface",
            entity_name="Entity",
            entity_id="e1",
            due_at=datetime.now(UTC) + timedelta(hours=1),
            outcomes=[],
        )

        assert context.is_overdue is False

    def test_is_overdue_true(self) -> None:
        """Test is_overdue returns True for past due date."""
        from dazzle_ui.runtime.task_context import TaskContext

        context = TaskContext(
            task_id="task-1",
            process_name="test",
            process_run_id="run-1",
            step_name="step",
            surface_name="surface",
            entity_name="Entity",
            entity_id="e1",
            due_at=datetime.now(UTC) - timedelta(hours=1),
            outcomes=[],
        )

        assert context.is_overdue is True

    def test_time_remaining_days(self) -> None:
        """Test time_remaining returns days format."""
        from dazzle_ui.runtime.task_context import TaskContext

        context = TaskContext(
            task_id="task-1",
            process_name="test",
            process_run_id="run-1",
            step_name="step",
            surface_name="surface",
            entity_name="Entity",
            entity_id="e1",
            due_at=datetime.now(UTC) + timedelta(days=3),
            outcomes=[],
        )

        # Could be "2 days" or "3 days" depending on time of day
        assert "day" in context.time_remaining

    def test_time_remaining_hours(self) -> None:
        """Test time_remaining returns hours format."""
        from dazzle_ui.runtime.task_context import TaskContext

        context = TaskContext(
            task_id="task-1",
            process_name="test",
            process_run_id="run-1",
            step_name="step",
            surface_name="surface",
            entity_name="Entity",
            entity_id="e1",
            due_at=datetime.now(UTC) + timedelta(hours=5),
            outcomes=[],
        )

        assert "hour" in context.time_remaining

    def test_time_remaining_overdue(self) -> None:
        """Test time_remaining returns Overdue for past due date."""
        from dazzle_ui.runtime.task_context import TaskContext

        context = TaskContext(
            task_id="task-1",
            process_name="test",
            process_run_id="run-1",
            step_name="step",
            surface_name="surface",
            entity_name="Entity",
            entity_id="e1",
            due_at=datetime.now(UTC) - timedelta(hours=1),
            outcomes=[],
        )

        assert context.time_remaining == "Overdue"

    def test_urgency_critical(self) -> None:
        """Test urgency returns critical for overdue."""
        from dazzle_ui.runtime.task_context import TaskContext

        context = TaskContext(
            task_id="task-1",
            process_name="test",
            process_run_id="run-1",
            step_name="step",
            surface_name="surface",
            entity_name="Entity",
            entity_id="e1",
            due_at=datetime.now(UTC) - timedelta(hours=1),
            outcomes=[],
        )

        assert context.urgency == "critical"

    def test_urgency_high(self) -> None:
        """Test urgency returns high for due within 24 hours."""
        from dazzle_ui.runtime.task_context import TaskContext

        context = TaskContext(
            task_id="task-1",
            process_name="test",
            process_run_id="run-1",
            step_name="step",
            surface_name="surface",
            entity_name="Entity",
            entity_id="e1",
            due_at=datetime.now(UTC) + timedelta(hours=12),
            outcomes=[],
        )

        assert context.urgency == "high"

    def test_urgency_low(self) -> None:
        """Test urgency returns low for due in more than 3 days."""
        from dazzle_ui.runtime.task_context import TaskContext

        context = TaskContext(
            task_id="task-1",
            process_name="test",
            process_run_id="run-1",
            step_name="step",
            surface_name="surface",
            entity_name="Entity",
            entity_id="e1",
            due_at=datetime.now(UTC) + timedelta(days=7),
            outcomes=[],
        )

        assert context.urgency == "low"

    def test_to_dict(self) -> None:
        """Test TaskContext.to_dict() serialization."""
        from dazzle_ui.runtime.task_context import TaskContext, TaskOutcome

        outcomes = [TaskOutcome(name="approve", label="Approve", style="primary")]

        context = TaskContext(
            task_id="task-1",
            process_name="test",
            process_run_id="run-1",
            step_name="step",
            surface_name="surface",
            entity_name="Entity",
            entity_id="e1",
            due_at=datetime.now(UTC) + timedelta(days=1),
            outcomes=outcomes,
        )

        data = context.to_dict()

        assert data["task_id"] == "task-1"
        assert data["process_name"] == "test"
        assert len(data["outcomes"]) == 1
        assert data["outcomes"][0]["name"] == "approve"
        assert "time_remaining" in data
        assert "urgency" in data


# =============================================================================
# Task Inbox Converter Tests
# =============================================================================


class TestTaskInboxConverter:
    """Test TaskInbox workspace region converter."""

    def test_default_config(self) -> None:
        """Test TaskInboxConfig default values."""
        from dazzle_ui.converters.task_inbox import TaskInboxConfig

        config = TaskInboxConfig()

        assert config.filter_status == ["pending", "escalated"]
        assert config.filter_assignee == "current_user"
        assert config.sort_field == "due_at"
        assert len(config.columns) == 6

    def test_convert_default(self) -> None:
        """Test converting with default config."""
        from dazzle_ui.converters.task_inbox import TaskInboxConverter

        converter = TaskInboxConverter()
        spec = converter.convert()

        assert spec["type"] == "task_inbox"
        assert spec["component"] == "TaskInbox"
        assert "filter" in spec["props"]
        assert "columns" in spec["props"]
        assert spec["data_source"]["endpoint"] == "/api/tasks"

    def test_convert_with_custom_filter(self) -> None:
        """Test converting with custom filter config."""
        from dazzle_ui.converters.task_inbox import TaskInboxConverter

        converter = TaskInboxConverter()
        spec = converter.convert(
            region_config={
                "filter_status": ["completed"],
                "filter_assignee": "all",
            }
        )

        assert spec["props"]["filter"]["status"] == ["completed"]
        assert spec["props"]["filter"]["assignee"] == "all"

    def test_generate_task_inbox_html(self) -> None:
        """Test generating task inbox HTML."""
        from dazzle_ui.converters.task_inbox import (
            TaskInboxConverter,
            generate_task_inbox_html,
        )

        converter = TaskInboxConverter()
        spec = converter.convert()
        html = generate_task_inbox_html(spec)

        assert 'class="task-inbox"' in html
        assert 'data-component="TaskInbox"' in html
        assert "<thead>" in html
        assert "My Tasks" in html


# =============================================================================
# Site Renderer Task Context Tests
# =============================================================================


class TestSiteRendererTaskContext:
    """Test task context rendering functions."""

    def test_render_task_context_script_none(self) -> None:
        """Test render_task_context_script returns empty for None."""
        from dazzle_ui.runtime.site_renderer import render_task_context_script

        result = render_task_context_script(None)
        assert result == ""

    def test_render_task_context_script(self) -> None:
        """Test render_task_context_script generates script tag."""
        from dazzle_ui.runtime.site_renderer import render_task_context_script
        from dazzle_ui.runtime.task_context import TaskContext, TaskOutcome

        outcomes = [TaskOutcome(name="approve", label="Approve", style="primary")]

        context = TaskContext(
            task_id="task-1",
            process_name="test",
            process_run_id="run-1",
            step_name="step",
            surface_name="surface",
            entity_name="Entity",
            entity_id="e1",
            due_at=datetime.now(UTC) + timedelta(days=1),
            outcomes=outcomes,
        )

        result = render_task_context_script(context)

        assert '<script type="application/json" id="task-context">' in result
        assert '"task_id": "task-1"' in result
        assert "task-header.js" in result

    def test_render_task_surface_page(self) -> None:
        """Test render_task_surface_page generates full page."""
        from dazzle_ui.runtime.site_renderer import render_task_surface_page
        from dazzle_ui.runtime.task_context import TaskContext, TaskOutcome

        outcomes = [TaskOutcome(name="approve", label="Approve", style="primary")]

        context = TaskContext(
            task_id="task-1",
            process_name="test",
            process_run_id="run-1",
            step_name="Review Step",
            surface_name="review_surface",
            entity_name="Entity",
            entity_id="e1",
            due_at=datetime.now(UTC) + timedelta(days=1),
            outcomes=outcomes,
        )

        result = render_task_surface_page(
            surface_name="review_surface",
            entity_id="e1",
            task_context=context,
            surface_html="<div>Surface content</div>",
            product_name="Test App",
        )

        assert "<!DOCTYPE html>" in result
        assert "Task: Review Step" in result
        assert "Test App" in result
        assert "<div>Surface content</div>" in result
        assert 'data-surface="review_surface"' in result


# =============================================================================
# Process Manager Task Methods Tests
# =============================================================================


class TestProcessManagerTasks:
    """Test ProcessManager task-related methods."""

    @pytest.fixture
    def mock_adapter(self) -> MagicMock:
        """Create mock adapter."""
        adapter = MagicMock()
        adapter.list_tasks = AsyncMock(return_value=[])
        adapter.get_task = AsyncMock(return_value=None)
        adapter.complete_task = AsyncMock()
        adapter.reassign_task = AsyncMock()
        return adapter

    def test_process_manager_init(self, mock_adapter: MagicMock) -> None:
        """Test ProcessManager initialization without AppSpec."""
        from dazzle_back.runtime.process_manager import ProcessManager

        manager = ProcessManager(adapter=mock_adapter)

        assert manager._adapter == mock_adapter
        assert manager._process_specs == []

    @pytest.mark.asyncio
    async def test_list_tasks_no_filter(self, mock_adapter: MagicMock) -> None:
        """Test listing tasks without filter."""
        from dazzle_back.runtime.process_manager import ProcessManager

        mock_adapter.list_tasks = AsyncMock(return_value=[])
        manager = ProcessManager(adapter=mock_adapter)

        tasks = await manager.list_tasks()

        mock_adapter.list_tasks.assert_called_once()
        assert tasks == []

    @pytest.mark.asyncio
    async def test_list_tasks_with_status_filter(self, mock_adapter: MagicMock) -> None:
        """Test listing tasks with status filter."""
        from dazzle_back.runtime.process_manager import ProcessManager

        # Create mock tasks
        pending_task = MagicMock()
        pending_task.status = TaskStatus.PENDING

        completed_task = MagicMock()
        completed_task.status = TaskStatus.COMPLETED

        mock_adapter.list_tasks = AsyncMock(return_value=[pending_task, completed_task])
        manager = ProcessManager(adapter=mock_adapter)

        tasks = await manager.list_tasks(status=TaskStatus.PENDING)

        assert len(tasks) == 1
        assert tasks[0].status == TaskStatus.PENDING

    @pytest.mark.asyncio
    async def test_complete_task(self, mock_adapter: MagicMock) -> None:
        """Test completing a task."""
        from dazzle_back.runtime.process_manager import ProcessManager

        manager = ProcessManager(adapter=mock_adapter)

        await manager.complete_task(
            task_id="task-1",
            outcome="approve",
            outcome_data={"note": "Approved"},
        )

        mock_adapter.complete_task.assert_called_once_with(
            "task-1", "approve", {"note": "Approved"}, None
        )

    @pytest.mark.asyncio
    async def test_reassign_task(self, mock_adapter: MagicMock) -> None:
        """Test reassigning a task."""
        from dazzle_back.runtime.process_manager import ProcessManager

        manager = ProcessManager(adapter=mock_adapter)

        await manager.reassign_task(
            task_id="task-1",
            new_assignee_id="user-2",
            reason="Vacation",
        )

        mock_adapter.reassign_task.assert_called_once_with("task-1", "user-2", "Vacation")

    def test_get_process_spec_not_found(self, mock_adapter: MagicMock) -> None:
        """Test get_process_spec returns None when not found."""
        from dazzle_back.runtime.process_manager import ProcessManager

        manager = ProcessManager(adapter=mock_adapter)

        result = manager.get_process_spec("nonexistent")

        assert result is None


# =============================================================================
# Task API Routes Tests
# =============================================================================


@pytest.mark.skipif(not FASTAPI_AVAILABLE, reason="FastAPI not installed")
class TestTaskRoutes:
    """Test task API route handlers."""


# =============================================================================
# Integration Tests
# =============================================================================
