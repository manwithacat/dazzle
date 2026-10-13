"""
Unit tests for human task integration (Phase 4).

Tests:
- Task API routes
- Task inbox converter
- Escalation scheduler
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from dazzle.core.process.adapter import TaskStatus

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
        from dazzle.http.runtime.process_manager import ProcessManager

        manager = ProcessManager(adapter=mock_adapter)

        assert manager._adapter == mock_adapter
        assert manager._process_specs == []

    @pytest.mark.asyncio
    async def test_list_tasks_no_filter(self, mock_adapter: MagicMock) -> None:
        """Test listing tasks without filter."""
        from dazzle.http.runtime.process_manager import ProcessManager

        mock_adapter.list_tasks = AsyncMock(return_value=[])
        manager = ProcessManager(adapter=mock_adapter)

        tasks = await manager.list_tasks()

        mock_adapter.list_tasks.assert_called_once()
        assert tasks == []

    @pytest.mark.asyncio
    async def test_list_tasks_with_status_filter(self, mock_adapter: MagicMock) -> None:
        """Test listing tasks with status filter."""
        from dazzle.http.runtime.process_manager import ProcessManager

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
        from dazzle.http.runtime.process_manager import ProcessManager

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
        from dazzle.http.runtime.process_manager import ProcessManager

        manager = ProcessManager(adapter=mock_adapter)

        await manager.reassign_task(
            task_id="task-1",
            new_assignee_id="user-2",
            reason="Vacation",
        )

        mock_adapter.reassign_task.assert_called_once_with("task-1", "user-2", "Vacation")

    def test_get_process_spec_not_found(self, mock_adapter: MagicMock) -> None:
        """Test get_process_spec returns None when not found."""
        from dazzle.http.runtime.process_manager import ProcessManager

        manager = ProcessManager(adapter=mock_adapter)

        result = manager.get_process_spec("nonexistent")

        assert result is None


# =============================================================================
# Task API Routes Tests
# =============================================================================


class TestTaskRoutes:
    """Test task API route handlers."""


# =============================================================================
# Integration Tests
# =============================================================================
