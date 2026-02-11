"""Tests for the MCP discovery handler."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def tmp_project(tmp_path: Path) -> Path:
    """Create a minimal project directory with dazzle.toml."""
    (tmp_path / "dazzle.toml").write_text('[project]\nname = "test"\n')
    (tmp_path / ".dazzle").mkdir()
    return tmp_path


@pytest.fixture
def mock_appspec() -> MagicMock:
    """Create a mock AppSpec."""
    from types import SimpleNamespace

    entity = SimpleNamespace(
        name="Task",
        title="Task",
        fields=[
            SimpleNamespace(name="id", type="uuid", constraints=None),
            SimpleNamespace(name="title", type="str", constraints=None),
        ],
        state_machine=None,
    )
    surface = SimpleNamespace(
        name="task_list",
        title="Task List",
        mode="list",
        entity="Task",
        sections=[],
    )
    persona = SimpleNamespace(name="admin", description="Administrator")

    appspec = SimpleNamespace(
        name="test_app",
        domain=SimpleNamespace(entities=[entity]),
        surfaces=[surface],
        personas=[persona],
        workspaces=[],
        processes=[],
        experiences=[],
    )
    return appspec


# =============================================================================
# Tests: Consolidated Handler Registration
# =============================================================================


class TestDiscoveryRegistration:
    def test_registered_in_consolidated_handlers(self) -> None:
        """Discovery handler is registered in the dispatch table."""
        from dazzle.mcp.server.handlers_consolidated import CONSOLIDATED_TOOL_HANDLERS

        assert "discovery" in CONSOLIDATED_TOOL_HANDLERS

    def test_tool_definition_exists(self) -> None:
        """Discovery tool has a schema definition."""
        from dazzle.mcp.server.tools_consolidated import get_consolidated_tools

        tools = get_consolidated_tools()
        discovery_tools = [t for t in tools if t.name == "discovery"]
        assert len(discovery_tools) == 1

    def test_tool_has_operations(self) -> None:
        """Discovery tool schema has the expected operations."""
        from dazzle.mcp.server.tools_consolidated import get_consolidated_tools

        tools = get_consolidated_tools()
        discovery_tool = next(t for t in tools if t.name == "discovery")
        ops = discovery_tool.inputSchema["properties"]["operation"]["enum"]
        assert set(ops) == {
            "run",
            "report",
            "compile",
            "emit",
            "status",
            "verify_all_stories",
            "coherence",
        }


# =============================================================================
# Tests: Run Operation
# =============================================================================


class TestRunDiscovery:
    @patch("dazzle.mcp.server.handlers.discovery._load_appspec")
    @patch("dazzle.mcp.server.handlers.discovery._populate_kg_for_discovery")
    def test_run_returns_mission_spec(
        self,
        mock_kg: MagicMock,
        mock_load: MagicMock,
        mock_appspec: MagicMock,
        tmp_project: Path,
    ) -> None:
        from dazzle.mcp.server.handlers.discovery import run_discovery_handler

        mock_load.return_value = mock_appspec
        mock_kg.return_value = None

        result = json.loads(run_discovery_handler(tmp_project, {}))
        assert result["status"] == "ready"
        assert result["mission"]["persona"] == "admin"
        assert result["mission"]["name"] == "discovery:admin"

    @patch("dazzle.mcp.server.handlers.discovery._load_appspec")
    @patch("dazzle.mcp.server.handlers.discovery._populate_kg_for_discovery")
    def test_run_with_custom_persona(
        self,
        mock_kg: MagicMock,
        mock_load: MagicMock,
        mock_appspec: MagicMock,
        tmp_project: Path,
    ) -> None:
        from dazzle.mcp.server.handlers.discovery import run_discovery_handler

        mock_load.return_value = mock_appspec
        mock_kg.return_value = None

        result = json.loads(run_discovery_handler(tmp_project, {"persona": "viewer"}))
        assert result["mission"]["persona"] == "viewer"
        assert result["mission"]["name"] == "discovery:viewer"

    @patch("dazzle.mcp.server.handlers.discovery._load_appspec")
    @patch("dazzle.mcp.server.handlers.discovery._populate_kg_for_discovery")
    def test_run_includes_dsl_summary(
        self,
        mock_kg: MagicMock,
        mock_load: MagicMock,
        mock_appspec: MagicMock,
        tmp_project: Path,
    ) -> None:
        from dazzle.mcp.server.handlers.discovery import run_discovery_handler

        mock_load.return_value = mock_appspec
        mock_kg.return_value = None

        result = json.loads(run_discovery_handler(tmp_project, {}))
        assert result["dsl_summary"]["entities"] == 1
        assert result["dsl_summary"]["surfaces"] == 1
        assert result["dsl_summary"]["personas"] == 1

    @patch("dazzle.mcp.server.handlers.discovery._load_appspec")
    @patch("dazzle.mcp.server.handlers.discovery._populate_kg_for_discovery")
    def test_run_includes_tools(
        self,
        mock_kg: MagicMock,
        mock_load: MagicMock,
        mock_appspec: MagicMock,
        tmp_project: Path,
    ) -> None:
        from dazzle.mcp.server.handlers.discovery import run_discovery_handler

        mock_load.return_value = mock_appspec
        mock_kg.return_value = None

        result = json.loads(run_discovery_handler(tmp_project, {}))
        tool_names = {t["name"] for t in result["mission"]["tools"]}
        assert tool_names == {"observe_gap", "query_dsl", "check_adjacency", "list_surfaces"}

    @patch("dazzle.mcp.server.handlers.discovery._load_appspec")
    def test_run_handles_dsl_error(
        self,
        mock_load: MagicMock,
        tmp_project: Path,
    ) -> None:
        from dazzle.mcp.server.handlers.discovery import run_discovery_handler

        mock_load.side_effect = Exception("Parse error")

        result = json.loads(run_discovery_handler(tmp_project, {}))
        assert "error" in result
        assert "Parse error" in result["error"]

    @patch("dazzle.mcp.server.handlers.discovery._load_appspec")
    @patch("dazzle.mcp.server.handlers.discovery._populate_kg_for_discovery")
    def test_run_with_kg(
        self,
        mock_kg: MagicMock,
        mock_load: MagicMock,
        mock_appspec: MagicMock,
        tmp_project: Path,
    ) -> None:
        from dazzle.mcp.server.handlers.discovery import run_discovery_handler

        mock_load.return_value = mock_appspec
        mock_kg.return_value = MagicMock()  # KG available

        result = json.loads(run_discovery_handler(tmp_project, {}))
        assert result["kg_available"] is True


# =============================================================================
# Tests: Report Operation
# =============================================================================


class TestDiscoveryReport:
    def test_report_no_reports(self, tmp_project: Path) -> None:
        from dazzle.mcp.server.handlers.discovery import get_discovery_report_handler

        result = json.loads(get_discovery_report_handler(tmp_project, {}))
        assert "error" in result

    def test_report_with_session_id(self, tmp_project: Path) -> None:
        from dazzle.mcp.server.handlers.discovery import get_discovery_report_handler

        # Create a report
        report_dir = tmp_project / ".dazzle" / "discovery"
        report_dir.mkdir(parents=True)
        report_data = {
            "mission_name": "discovery:admin",
            "outcome": "completed",
            "observations": [{"title": "Missing delete"}],
        }
        (report_dir / "test_session.json").write_text(json.dumps(report_data))

        result = json.loads(
            get_discovery_report_handler(tmp_project, {"session_id": "test_session"})
        )
        assert result["mission_name"] == "discovery:admin"
        assert result["outcome"] == "completed"

    def test_report_missing_session(self, tmp_project: Path) -> None:
        from dazzle.mcp.server.handlers.discovery import get_discovery_report_handler

        report_dir = tmp_project / ".dazzle" / "discovery"
        report_dir.mkdir(parents=True)

        result = json.loads(
            get_discovery_report_handler(tmp_project, {"session_id": "nonexistent"})
        )
        assert "error" in result

    def test_report_list_available(self, tmp_project: Path) -> None:
        from dazzle.mcp.server.handlers.discovery import get_discovery_report_handler

        report_dir = tmp_project / ".dazzle" / "discovery"
        report_dir.mkdir(parents=True)
        for i in range(3):
            (report_dir / f"session_{i}.json").write_text(
                json.dumps(
                    {
                        "mission_name": f"discovery:admin_{i}",
                        "outcome": "completed",
                        "step_count": i + 1,
                        "observations": [],
                        "started_at": f"2026-02-0{i + 1}",
                    }
                )
            )

        result = json.loads(get_discovery_report_handler(tmp_project, {}))
        assert "reports" in result
        assert len(result["reports"]) == 3


# =============================================================================
# Tests: Status Operation
# =============================================================================


# =============================================================================
# Tests: Compile Operation
# =============================================================================


class TestCompileDiscovery:
    def test_compile_no_reports(self, tmp_project: Path) -> None:
        from dazzle.mcp.server.handlers.discovery import compile_discovery_handler

        result = json.loads(compile_discovery_handler(tmp_project, {}))
        assert "error" in result

    def test_compile_no_observations(self, tmp_project: Path) -> None:
        from dazzle.mcp.server.handlers.discovery import compile_discovery_handler

        report_dir = tmp_project / ".dazzle" / "discovery"
        report_dir.mkdir(parents=True)
        (report_dir / "empty.json").write_text(
            json.dumps({"mission_name": "test", "observations": []})
        )

        result = json.loads(compile_discovery_handler(tmp_project, {"session_id": "empty"}))
        assert result["proposals"] == []
        assert "No observations" in result["message"]

    def test_compile_with_observations(self, tmp_project: Path) -> None:
        from dazzle.mcp.server.handlers.discovery import compile_discovery_handler

        report_dir = tmp_project / ".dazzle" / "discovery"
        report_dir.mkdir(parents=True)
        (report_dir / "test_session.json").write_text(
            json.dumps(
                {
                    "mission_name": "discovery:admin",
                    "observations": [
                        {
                            "category": "missing_crud",
                            "severity": "high",
                            "title": "No delete for Task",
                            "description": "Task has no delete surface",
                            "location": "/tasks",
                            "related_artefacts": ["entity:Task"],
                        },
                        {
                            "category": "ux_issue",
                            "severity": "medium",
                            "title": "Missing validation",
                            "description": "Form lacks required field markers",
                            "location": "/tasks/new",
                            "related_artefacts": ["surface:task_form"],
                        },
                    ],
                }
            )
        )

        result = json.loads(
            compile_discovery_handler(
                tmp_project, {"session_id": "test_session", "persona": "admin"}
            )
        )
        assert result["total_proposals"] == 2
        assert result["persona"] == "admin"
        assert "report_markdown" in result
        assert "# Discovery Report" in result["report_markdown"]

    def test_compile_uses_latest_report(self, tmp_project: Path) -> None:
        from dazzle.mcp.server.handlers.discovery import compile_discovery_handler

        report_dir = tmp_project / ".dazzle" / "discovery"
        report_dir.mkdir(parents=True)
        # Create two reports
        import time

        (report_dir / "old_report.json").write_text(
            json.dumps({"observations": [{"category": "gap", "severity": "low", "title": "old"}]})
        )
        time.sleep(0.01)  # Ensure different mtime
        (report_dir / "new_report.json").write_text(
            json.dumps({"observations": [{"category": "gap", "severity": "high", "title": "new"}]})
        )

        result = json.loads(compile_discovery_handler(tmp_project, {}))
        assert result["session_id"] == "new_report"

    def test_tool_has_compile_operation(self) -> None:
        from dazzle.mcp.server.tools_consolidated import get_consolidated_tools

        tools = get_consolidated_tools()
        discovery_tool = next(t for t in tools if t.name == "discovery")
        ops = discovery_tool.inputSchema["properties"]["operation"]["enum"]
        assert "compile" in ops


class TestDiscoveryStatus:
    @patch("dazzle.mcp.server.handlers.discovery._load_appspec")
    def test_status_with_valid_dsl(
        self,
        mock_load: MagicMock,
        mock_appspec: MagicMock,
        tmp_project: Path,
    ) -> None:
        from dazzle.mcp.server.handlers.discovery import discovery_status_handler

        mock_load.return_value = mock_appspec

        result = json.loads(discovery_status_handler(tmp_project, {}))
        assert result["dsl_valid"] is True
        assert result["entities"] == 1
        assert result["surfaces"] == 1

    @patch("dazzle.mcp.server.handlers.discovery._load_appspec")
    def test_status_with_invalid_dsl(
        self,
        mock_load: MagicMock,
        tmp_project: Path,
    ) -> None:
        from dazzle.mcp.server.handlers.discovery import discovery_status_handler

        mock_load.side_effect = Exception("No dazzle.toml")

        result = json.loads(discovery_status_handler(tmp_project, {}))
        assert result["dsl_valid"] is False
        assert "dsl_error" in result

    def test_status_reports_count(self, tmp_project: Path) -> None:
        from dazzle.mcp.server.handlers.discovery import discovery_status_handler

        report_dir = tmp_project / ".dazzle" / "discovery"
        report_dir.mkdir(parents=True)
        (report_dir / "session_1.json").write_text("{}")
        (report_dir / "session_2.json").write_text("{}")

        with patch("dazzle.mcp.server.handlers.discovery._load_appspec") as mock_load:
            mock_load.side_effect = Exception("skip")
            result = json.loads(discovery_status_handler(tmp_project, {}))

        assert result["reports_count"] == 2


# =============================================================================
# Tests: Save Report
# =============================================================================


class TestSaveReport:
    def test_save_creates_file(self, tmp_project: Path) -> None:
        from dazzle.mcp.server.handlers.discovery import save_discovery_report

        transcript = {
            "mission_name": "discovery:admin",
            "outcome": "completed",
            "observations": [],
        }
        path = save_discovery_report(tmp_project, transcript)
        assert path.exists()
        data = json.loads(path.read_text())
        assert data["mission_name"] == "discovery:admin"

    def test_save_creates_directory(self, tmp_path: Path) -> None:
        from dazzle.mcp.server.handlers.discovery import save_discovery_report

        # No .dazzle/discovery/ exists
        path = save_discovery_report(tmp_path, {"test": True})
        assert path.exists()
        assert path.parent.name == "discovery"


# =============================================================================
# Tests: Consolidated Dispatch
# =============================================================================


class TestConsolidatedDispatch:
    @patch("dazzle.mcp.server.handlers_consolidated._resolve_project")
    @patch("dazzle.mcp.server.handlers.discovery.run_discovery_handler")
    def test_dispatch_run(
        self,
        mock_run: MagicMock,
        mock_resolve: MagicMock,
        tmp_project: Path,
    ) -> None:
        from dazzle.mcp.server.handlers_consolidated import handle_discovery

        mock_resolve.return_value = tmp_project
        mock_run.return_value = '{"status": "ready"}'

        result = handle_discovery({"operation": "run"})
        assert result == '{"status": "ready"}'

    @patch("dazzle.mcp.server.handlers_consolidated._resolve_project")
    def test_dispatch_unknown_operation(
        self,
        mock_resolve: MagicMock,
        tmp_project: Path,
    ) -> None:
        from dazzle.mcp.server.handlers_consolidated import handle_discovery

        mock_resolve.return_value = tmp_project

        result = json.loads(handle_discovery({"operation": "invalid"}))
        assert "error" in result
        assert "Unknown" in result["error"]

    @patch("dazzle.mcp.server.handlers_consolidated._resolve_project")
    def test_dispatch_no_project(self, mock_resolve: MagicMock) -> None:
        from dazzle.mcp.server.handlers_consolidated import handle_discovery

        mock_resolve.return_value = None

        result = json.loads(handle_discovery({"operation": "run"}))
        assert "error" in result
