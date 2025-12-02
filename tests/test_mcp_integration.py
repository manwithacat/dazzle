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


def _start_mcp_server() -> subprocess.Popen:
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


def _initialize_server(proc: subprocess.Popen) -> dict:
    """Initialize MCP server and return the response."""
    response = send_jsonrpc(
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

    return response


@pytest.mark.slow
class TestMCPServerIntegration:
    """Integration tests that launch the server as a subprocess.

    Uses a class-scoped fixture to share one subprocess across all tests,
    significantly reducing test overhead.
    """

    @pytest.fixture(scope="class")
    def mcp_server(self):
        """Start a shared MCP server subprocess for the test class."""
        proc = _start_mcp_server()
        _initialize_server(proc)
        yield proc
        proc.terminate()
        proc.wait(timeout=5)

    @pytest.fixture(scope="class")
    def request_id_counter(self):
        """Shared counter to ensure unique request IDs across tests."""
        return {"id": 10}  # Start at 10 to avoid conflicts with initialization

    def test_server_starts_and_responds_to_initialize(self):
        """Test that server starts and responds to MCP initialize request."""
        # This test needs its own server to test initialization
        proc = _start_mcp_server()
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

    def test_tools_list(self, mcp_server, request_id_counter):
        """Test that server returns list of tools."""
        request_id_counter["id"] += 1
        response = send_jsonrpc(mcp_server, "tools/list", {}, id=request_id_counter["id"])

        assert response["jsonrpc"] == "2.0"
        assert "result" in response
        assert "tools" in response["result"]

        tools = response["result"]["tools"]
        tool_names = [t["name"] for t in tools]

        # Check expected tools exist
        assert "validate_dsl" in tool_names
        assert "list_modules" in tool_names
        assert "inspect_entity" in tool_names

    def test_tool_call_validate_dsl(self, mcp_server, request_id_counter):
        """Test calling the validate_dsl tool."""
        request_id_counter["id"] += 1
        response = send_jsonrpc(
            mcp_server,
            "tools/call",
            {"name": "validate_dsl", "arguments": {}},
            id=request_id_counter["id"],
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

    def test_no_stdout_corruption(self):
        """Test that no non-JSON output goes to stdout."""
        # This test needs its own server to verify clean startup
        proc = _start_mcp_server()
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

        from dazzle.mcp.server import list_tools_handler

        tools = asyncio.run(list_tools_handler())

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
        from dazzle.mcp.server.state import _detect_dev_environment

        # PROJECT_ROOT is the Dazzle dev environment
        assert _detect_dev_environment(PROJECT_ROOT) is True

        # An example project should NOT be detected as dev env
        example_path = PROJECT_ROOT / "examples" / "simple_task"
        if example_path.exists():
            assert _detect_dev_environment(example_path) is False

    def test_discover_example_projects(self):
        """Test that example projects are discovered."""
        from dazzle.mcp.server.state import _discover_example_projects

        projects = _discover_example_projects(PROJECT_ROOT)

        # Should find at least some example projects
        assert len(projects) > 0

        # Each project should have a valid path
        for _name, path in projects.items():
            assert path.is_dir()
            assert (path / "dazzle.toml").exists()

    def test_dev_mode_initialization(self):
        """Test dev mode initialization."""
        from dazzle.mcp.server import state as mcp_state

        # Initialize dev mode with project root
        mcp_state.init_dev_mode(PROJECT_ROOT)

        # Should be in dev mode
        assert mcp_state.is_dev_mode() is True

        # Should have discovered projects
        assert len(mcp_state.get_available_projects()) > 0

        # Should have auto-selected first project
        assert mcp_state.get_active_project() is not None
        assert mcp_state.get_active_project() in mcp_state.get_available_projects()

    def test_dev_mode_tools_available(self):
        """Test that dev mode tools are available when in dev mode."""
        import asyncio

        from dazzle.mcp.server import list_tools_handler
        from dazzle.mcp.server.state import init_dev_mode

        # Ensure dev mode is initialized
        init_dev_mode(PROJECT_ROOT)

        tools = asyncio.run(list_tools_handler())
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

        from dazzle.mcp.server import call_tool
        from dazzle.mcp.server.state import init_dev_mode

        init_dev_mode(PROJECT_ROOT)

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

        from dazzle.mcp.server import call_tool
        from dazzle.mcp.server import state as mcp_state

        mcp_state.init_dev_mode(PROJECT_ROOT)

        # Get a project to select
        project_names = list(mcp_state.get_available_projects().keys())
        assert len(project_names) > 0

        # Select a project
        target_project = project_names[-1]  # Pick last one (different from auto-selected first)
        result = asyncio.run(call_tool("select_project", {"project_name": target_project}))

        data = json.loads(result[0].text)
        assert data["status"] == "selected"
        assert data["project"] == target_project

    def test_select_project_invalid(self):
        """Test selecting an invalid project."""
        import asyncio

        from dazzle.mcp.server import call_tool
        from dazzle.mcp.server.state import init_dev_mode

        init_dev_mode(PROJECT_ROOT)

        result = asyncio.run(call_tool("select_project", {"project_name": "nonexistent_project"}))

        data = json.loads(result[0].text)
        assert "error" in data
        assert "not found" in data["error"]
        assert "available_projects" in data

    def test_get_active_project_tool(self):
        """Test the get_active_project tool."""
        import asyncio

        from dazzle.mcp.server import call_tool
        from dazzle.mcp.server.state import init_dev_mode

        init_dev_mode(PROJECT_ROOT)

        result = asyncio.run(call_tool("get_active_project", {}))

        data = json.loads(result[0].text)
        assert data["mode"] == "dev"
        assert "active_project" in data
        assert data["active_project"] is not None

    @pytest.mark.slow
    def test_validate_all_projects_tool(self):
        """Test the validate_all_projects tool."""
        import asyncio

        from dazzle.mcp.server import call_tool
        from dazzle.mcp.server.state import init_dev_mode

        init_dev_mode(PROJECT_ROOT)

        result = asyncio.run(call_tool("validate_all_projects", {}))

        data = json.loads(result[0].text)
        assert "summary" in data
        assert "projects" in data
        assert data["summary"]["total"] > 0

    def test_validate_dsl_in_dev_mode(self):
        """Test that validate_dsl works with active project in dev mode."""
        import asyncio

        from dazzle.mcp.server import call_tool
        from dazzle.mcp.server.state import init_dev_mode

        init_dev_mode(PROJECT_ROOT)

        result = asyncio.run(call_tool("validate_dsl", {}))

        data = json.loads(result[0].text)
        # Should have project context in dev mode
        assert "project" in data or "status" in data


@pytest.mark.slow
class TestMCPDevModeIntegration:
    """Integration tests for dev mode via subprocess.

    Uses a class-scoped fixture to share one subprocess across all tests,
    significantly reducing test overhead.
    """

    @pytest.fixture(scope="class")
    def mcp_server(self):
        """Start a shared MCP server subprocess for the test class."""
        proc = _start_mcp_server()
        _initialize_server(proc)
        yield proc
        proc.terminate()
        proc.wait(timeout=5)

    @pytest.fixture(scope="class")
    def request_id_counter(self):
        """Shared counter to ensure unique request IDs across tests."""
        return {"id": 10}

    def test_dev_mode_tools_via_subprocess(self, mcp_server, request_id_counter):
        """Test that dev mode tools are exposed via subprocess."""
        request_id_counter["id"] += 1
        response = send_jsonrpc(mcp_server, "tools/list", {}, id=request_id_counter["id"])

        tools = response["result"]["tools"]
        tool_names = [t["name"] for t in tools]

        # Dev mode tools should be present
        assert "list_projects" in tool_names
        assert "select_project" in tool_names
        assert "get_active_project" in tool_names
        assert "validate_all_projects" in tool_names

    def test_list_projects_via_subprocess(self, mcp_server, request_id_counter):
        """Test list_projects tool via subprocess."""
        request_id_counter["id"] += 1
        response = send_jsonrpc(
            mcp_server,
            "tools/call",
            {"name": "list_projects", "arguments": {}},
            id=request_id_counter["id"],
        )

        content = response["result"]["content"]
        data = json.loads(content[0]["text"])

        assert data["mode"] == "dev"
        assert len(data["projects"]) > 0

    def test_project_workflow_via_subprocess(self, mcp_server, request_id_counter):
        """Test full project selection workflow via subprocess."""
        # 1. List projects
        request_id_counter["id"] += 1
        response = send_jsonrpc(
            mcp_server,
            "tools/call",
            {"name": "list_projects", "arguments": {}},
            id=request_id_counter["id"],
        )
        projects_data = json.loads(response["result"]["content"][0]["text"])
        project_names = [p["name"] for p in projects_data["projects"]]

        # 2. Select a project
        request_id_counter["id"] += 1
        response = send_jsonrpc(
            mcp_server,
            "tools/call",
            {"name": "select_project", "arguments": {"project_name": project_names[0]}},
            id=request_id_counter["id"],
        )
        select_data = json.loads(response["result"]["content"][0]["text"])
        assert select_data["status"] == "selected"

        # 3. Validate the selected project
        request_id_counter["id"] += 1
        response = send_jsonrpc(
            mcp_server,
            "tools/call",
            {"name": "validate_dsl", "arguments": {}},
            id=request_id_counter["id"],
        )
        validate_data = json.loads(response["result"]["content"][0]["text"])
        assert "status" in validate_data


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
