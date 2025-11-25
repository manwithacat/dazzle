"""
Integration tests for DAZZLE MCP server.

These tests mimic how Claude Code connects to the MCP server as a subprocess
communicating via JSON-RPC over stdio.
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

# Get the project root
PROJECT_ROOT = Path(__file__).parent.parent
PYTHON_PATH = sys.executable


def send_jsonrpc(proc: subprocess.Popen, method: str, params: dict = None, id: int = 1) -> dict:
    """Send a JSON-RPC message and get the response."""
    message = {
        "jsonrpc": "2.0",
        "id": id,
        "method": method,
    }
    if params is not None:
        message["params"] = params

    # Send message
    proc.stdin.write(json.dumps(message) + "\n")
    proc.stdin.flush()

    # Read response
    response_line = proc.stdout.readline()
    if not response_line:
        stderr = proc.stderr.read()
        raise RuntimeError(f"No response received. stderr: {stderr}")

    return json.loads(response_line)


class TestMCPServerIntegration:
    """Integration tests that launch the server as a subprocess."""

    def start_server(self) -> subprocess.Popen:
        """Start the MCP server as a subprocess."""
        proc = subprocess.Popen(
            [PYTHON_PATH, "-m", "dazzle.mcp", "--working-dir", str(PROJECT_ROOT)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,  # Line buffered
        )
        return proc

    def test_server_starts_and_responds_to_initialize(self):
        """Test that server starts and responds to MCP initialize request."""
        proc = self.start_server()
        try:
            response = send_jsonrpc(
                proc,
                "initialize",
                {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "test", "version": "1.0"},
                },
            )

            assert response["jsonrpc"] == "2.0"
            assert response["id"] == 1
            assert "result" in response
            assert "serverInfo" in response["result"]
            assert response["result"]["serverInfo"]["name"] == "dazzle"
        finally:
            proc.terminate()
            proc.wait(timeout=5)

    def test_tools_list(self):
        """Test that server returns list of tools."""
        proc = self.start_server()
        try:
            # First initialize
            send_jsonrpc(
                proc,
                "initialize",
                {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "test", "version": "1.0"},
                },
            )

            # Send initialized notification
            proc.stdin.write(
                json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}) + "\n"
            )
            proc.stdin.flush()

            # List tools
            response = send_jsonrpc(proc, "tools/list", {}, id=2)

            assert response["jsonrpc"] == "2.0"
            assert "result" in response
            assert "tools" in response["result"]

            tools = response["result"]["tools"]
            tool_names = [t["name"] for t in tools]

            # Check expected tools exist
            assert "validate_dsl" in tool_names
            assert "list_modules" in tool_names
            assert "inspect_entity" in tool_names
        finally:
            proc.terminate()
            proc.wait(timeout=5)

    def test_tool_call_validate_dsl(self):
        """Test calling the validate_dsl tool."""
        proc = self.start_server()
        try:
            # Initialize
            send_jsonrpc(
                proc,
                "initialize",
                {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "test", "version": "1.0"},
                },
            )

            # Send initialized notification
            proc.stdin.write(
                json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}) + "\n"
            )
            proc.stdin.flush()

            # Call tool
            response = send_jsonrpc(
                proc,
                "tools/call",
                {"name": "validate_dsl", "arguments": {}},
                id=2,
            )

            assert response["jsonrpc"] == "2.0"
            assert "result" in response

            # Result should contain content
            content = response["result"]["content"]
            assert len(content) > 0
            assert content[0]["type"] == "text"

            # Parse the JSON result
            result_data = json.loads(content[0]["text"])
            # Should have either status: valid or status: error
            assert "status" in result_data
        finally:
            proc.terminate()
            proc.wait(timeout=5)

    def test_no_stdout_corruption(self):
        """Test that no non-JSON output goes to stdout."""
        proc = self.start_server()
        try:
            # Send initialize
            response = send_jsonrpc(
                proc,
                "initialize",
                {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "test", "version": "1.0"},
                },
            )

            # Response should be valid JSON (no corruption)
            assert response["jsonrpc"] == "2.0"

            # stderr may have logging, but stdout should only have JSON
            # The fact that json.loads worked on the response proves no corruption
        finally:
            proc.terminate()
            proc.wait(timeout=5)


class TestMCPServerUnit:
    """Unit tests for server components."""

    def test_list_tools_async(self):
        """Test list_tools returns expected tools."""
        import asyncio

        from dazzle.mcp.server import list_tools

        tools = asyncio.run(list_tools())

        assert len(tools) >= 7
        tool_names = [t.name for t in tools]
        assert "validate_dsl" in tool_names
        assert "list_modules" in tool_names
        assert "inspect_entity" in tool_names
        assert "inspect_surface" in tool_names
        assert "build" in tool_names
        assert "analyze_patterns" in tool_names
        assert "lint_project" in tool_names

    def test_call_tool_unknown(self):
        """Test calling unknown tool returns error."""
        import asyncio

        from dazzle.mcp.server import call_tool

        result = asyncio.run(call_tool("unknown_tool", {}))

        assert len(result) == 1
        assert result[0].type == "text"
        data = json.loads(result[0].text)
        assert "error" in data
        assert "Unknown tool" in data["error"]


class TestMCPDevMode:
    """Tests for MCP server dev mode functionality."""

    def test_detect_dev_environment(self):
        """Test that dev environment is correctly detected."""
        from dazzle.mcp.server import _detect_dev_environment

        # PROJECT_ROOT is the Dazzle dev environment
        assert _detect_dev_environment(PROJECT_ROOT) is True

        # An example project should NOT be detected as dev env
        example_path = PROJECT_ROOT / "examples" / "simple_task"
        if example_path.exists():
            assert _detect_dev_environment(example_path) is False

    def test_discover_example_projects(self):
        """Test that example projects are discovered."""
        from dazzle.mcp.server import _discover_example_projects

        projects = _discover_example_projects(PROJECT_ROOT)

        # Should find at least some example projects
        assert len(projects) > 0

        # Each project should have a valid path
        for _name, path in projects.items():
            assert path.is_dir()
            assert (path / "dazzle.toml").exists()

    def test_dev_mode_initialization(self):
        """Test dev mode initialization."""
        import dazzle.mcp.server as mcp_server

        # Initialize dev mode with project root
        mcp_server._init_dev_mode(PROJECT_ROOT)

        # Should be in dev mode
        assert mcp_server.is_dev_mode() is True

        # Should have discovered projects (access module-level vars directly)
        assert len(mcp_server._available_projects) > 0

        # Should have auto-selected first project
        assert mcp_server._active_project is not None
        assert mcp_server._active_project in mcp_server._available_projects

    def test_dev_mode_tools_available(self):
        """Test that dev mode tools are available when in dev mode."""
        import asyncio

        from dazzle.mcp.server import _init_dev_mode, list_tools

        # Ensure dev mode is initialized
        _init_dev_mode(PROJECT_ROOT)

        tools = asyncio.run(list_tools())
        tool_names = [t.name for t in tools]

        # Dev mode tools should be present
        assert "list_projects" in tool_names
        assert "select_project" in tool_names
        assert "get_active_project" in tool_names
        assert "validate_all_projects" in tool_names

        # Regular tools should also be present
        assert "validate_dsl" in tool_names
        assert "list_modules" in tool_names

    def test_list_projects_tool(self):
        """Test the list_projects tool."""
        import asyncio

        from dazzle.mcp.server import _init_dev_mode, call_tool

        _init_dev_mode(PROJECT_ROOT)

        result = asyncio.run(call_tool("list_projects", {}))

        assert len(result) == 1
        data = json.loads(result[0].text)

        assert data["mode"] == "dev"
        assert "projects" in data
        assert len(data["projects"]) > 0
        assert data["active_project"] is not None

    def test_select_project_tool(self):
        """Test the select_project tool."""
        import asyncio

        import dazzle.mcp.server as mcp_server

        mcp_server._init_dev_mode(PROJECT_ROOT)

        # Get a project to select
        project_names = list(mcp_server._available_projects.keys())
        assert len(project_names) > 0

        # Select a project
        target_project = project_names[-1]  # Pick last one (different from auto-selected first)
        result = asyncio.run(
            mcp_server.call_tool("select_project", {"project_name": target_project})
        )

        data = json.loads(result[0].text)
        assert data["status"] == "selected"
        assert data["project"] == target_project

    def test_select_project_invalid(self):
        """Test selecting an invalid project."""
        import asyncio

        from dazzle.mcp.server import _init_dev_mode, call_tool

        _init_dev_mode(PROJECT_ROOT)

        result = asyncio.run(call_tool("select_project", {"project_name": "nonexistent_project"}))

        data = json.loads(result[0].text)
        assert "error" in data
        assert "not found" in data["error"]
        assert "available_projects" in data

    def test_get_active_project_tool(self):
        """Test the get_active_project tool."""
        import asyncio

        from dazzle.mcp.server import _init_dev_mode, call_tool

        _init_dev_mode(PROJECT_ROOT)

        result = asyncio.run(call_tool("get_active_project", {}))

        data = json.loads(result[0].text)
        assert data["mode"] == "dev"
        assert "active_project" in data
        assert data["active_project"] is not None

    def test_validate_all_projects_tool(self):
        """Test the validate_all_projects tool."""
        import asyncio

        from dazzle.mcp.server import _init_dev_mode, call_tool

        _init_dev_mode(PROJECT_ROOT)

        result = asyncio.run(call_tool("validate_all_projects", {}))

        data = json.loads(result[0].text)
        assert "summary" in data
        assert "projects" in data
        assert data["summary"]["total"] > 0

    def test_validate_dsl_in_dev_mode(self):
        """Test that validate_dsl works with active project in dev mode."""
        import asyncio

        from dazzle.mcp.server import _init_dev_mode, call_tool

        _init_dev_mode(PROJECT_ROOT)

        result = asyncio.run(call_tool("validate_dsl", {}))

        data = json.loads(result[0].text)
        # Should have project context in dev mode
        assert "project" in data or "status" in data


class TestMCPDevModeIntegration:
    """Integration tests for dev mode via subprocess."""

    def start_server(self) -> subprocess.Popen:
        """Start the MCP server as a subprocess pointing to Dazzle root (dev mode)."""
        proc = subprocess.Popen(
            [PYTHON_PATH, "-m", "dazzle.mcp", "--working-dir", str(PROJECT_ROOT)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        return proc

    def test_dev_mode_tools_via_subprocess(self):
        """Test that dev mode tools are exposed via subprocess."""
        proc = self.start_server()
        try:
            # Initialize
            send_jsonrpc(
                proc,
                "initialize",
                {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "test", "version": "1.0"},
                },
            )

            proc.stdin.write(
                json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}) + "\n"
            )
            proc.stdin.flush()

            # List tools
            response = send_jsonrpc(proc, "tools/list", {}, id=2)

            tools = response["result"]["tools"]
            tool_names = [t["name"] for t in tools]

            # Dev mode tools should be present
            assert "list_projects" in tool_names
            assert "select_project" in tool_names
            assert "get_active_project" in tool_names
            assert "validate_all_projects" in tool_names

        finally:
            proc.terminate()
            proc.wait(timeout=5)

    def test_list_projects_via_subprocess(self):
        """Test list_projects tool via subprocess."""
        proc = self.start_server()
        try:
            # Initialize
            send_jsonrpc(
                proc,
                "initialize",
                {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "test", "version": "1.0"},
                },
            )

            proc.stdin.write(
                json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}) + "\n"
            )
            proc.stdin.flush()

            # Call list_projects
            response = send_jsonrpc(
                proc,
                "tools/call",
                {"name": "list_projects", "arguments": {}},
                id=2,
            )

            content = response["result"]["content"]
            data = json.loads(content[0]["text"])

            assert data["mode"] == "dev"
            assert len(data["projects"]) > 0

        finally:
            proc.terminate()
            proc.wait(timeout=5)

    def test_project_workflow_via_subprocess(self):
        """Test full project selection workflow via subprocess."""
        proc = self.start_server()
        try:
            # Initialize
            send_jsonrpc(
                proc,
                "initialize",
                {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "test", "version": "1.0"},
                },
            )

            proc.stdin.write(
                json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}) + "\n"
            )
            proc.stdin.flush()

            # 1. List projects
            response = send_jsonrpc(
                proc,
                "tools/call",
                {"name": "list_projects", "arguments": {}},
                id=2,
            )
            projects_data = json.loads(response["result"]["content"][0]["text"])
            project_names = [p["name"] for p in projects_data["projects"]]

            # 2. Select a project
            response = send_jsonrpc(
                proc,
                "tools/call",
                {"name": "select_project", "arguments": {"project_name": project_names[0]}},
                id=3,
            )
            select_data = json.loads(response["result"]["content"][0]["text"])
            assert select_data["status"] == "selected"

            # 3. Validate the selected project
            response = send_jsonrpc(
                proc,
                "tools/call",
                {"name": "validate_dsl", "arguments": {}},
                id=4,
            )
            validate_data = json.loads(response["result"]["content"][0]["text"])
            assert "status" in validate_data

        finally:
            proc.terminate()
            proc.wait(timeout=5)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
