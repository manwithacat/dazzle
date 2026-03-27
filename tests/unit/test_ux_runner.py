"""Tests for Playwright interaction runner (unit-level, no browser)."""

from dazzle.testing.ux.runner import (
    InteractionRunner,
    _build_page_url,
)


class TestBuildPageUrl:
    def test_list_surface_url(self) -> None:
        url = _build_page_url("task_list", "Task", "list", "http://localhost:3000")
        assert url == "http://localhost:3000/app/task"

    def test_workspace_url(self) -> None:
        url = _build_page_url(
            "", "", "workspace", "http://localhost:3000", workspace="teacher_dashboard"
        )
        assert url == "http://localhost:3000/workspace/teacher_dashboard"


class TestRunnerConfig:
    def test_runner_init(self) -> None:
        runner = InteractionRunner(
            site_url="http://localhost:3000",
            api_url="http://localhost:8000",
        )
        assert runner.site_url == "http://localhost:3000"
        assert runner.api_url == "http://localhost:8000"
