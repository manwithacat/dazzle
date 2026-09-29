"""Tests for MCP server setup and configuration.

Uses direct module import to avoid triggering mcp.server import from dazzle.mcp.__init__.
"""

import importlib.util
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

# ============================================================================
# Direct module import to avoid mcp.server dependency
# ============================================================================

_setup_module = None


def _import_module():
    """Import setup module directly."""
    global _setup_module

    if _setup_module is not None:
        return

    # Mock the MCP server packages to prevent import errors
    _mocked = ["mcp", "mcp.server", "mcp.server.fastmcp"]
    _orig = {k: sys.modules.get(k) for k in _mocked}
    for k in _mocked:
        sys.modules[k] = MagicMock(pytest_plugins=[])

    # Get path to setup.py
    src_path = Path(__file__).parent.parent.parent / "src"
    module_path = src_path / "dazzle" / "mcp" / "setup.py"

    # Import module
    spec = importlib.util.spec_from_file_location(
        "setup_module",
        module_path,
    )
    _setup_module = importlib.util.module_from_spec(spec)
    sys.modules["setup_module"] = _setup_module
    spec.loader.exec_module(_setup_module)

    # Restore sys.modules to prevent pollution of other tests
    for k, v in _orig.items():
        if v is None:
            sys.modules.pop(k, None)
        else:
            sys.modules[k] = v


# Import the module
_import_module()


def get_claude_config_path():
    return _setup_module.get_claude_config_path()


def register_mcp_server(force=False):
    return _setup_module.register_mcp_server(force=force)


def check_mcp_server():
    return _setup_module.check_mcp_server()


class TestGetClaudeConfigPath:
    """Tests for get_claude_config_path function."""

    def test_finds_existing_xdg_config(self, tmp_path):
        """Test that XDG config location is preferred if it exists."""
        # Create XDG directory
        xdg_dir = tmp_path / ".config" / "claude-code"
        xdg_dir.mkdir(parents=True)

        with patch.object(_setup_module.Path, "home", return_value=tmp_path):
            config_path = _setup_module.get_claude_config_path()

        assert config_path == xdg_dir / "mcp_servers.json"

    def test_finds_existing_claude_dir(self, tmp_path):
        """Test that .claude directory is used if it exists."""
        # Create .claude directory
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir(parents=True)

        with patch.object(_setup_module.Path, "home", return_value=tmp_path):
            config_path = _setup_module.get_claude_config_path()

        assert config_path == claude_dir / "mcp_servers.json"

    def test_creates_default_directory(self, tmp_path):
        """Test that default directory is created if none exist."""
        with patch.object(_setup_module.Path, "home", return_value=tmp_path):
            config_path = _setup_module.get_claude_config_path()

        assert config_path == tmp_path / ".claude" / "mcp_servers.json"
        assert config_path.parent.exists()

    def test_prefers_xdg_over_claude(self, tmp_path):
        """Test that XDG location is preferred over .claude."""
        # Create both directories
        xdg_dir = tmp_path / ".config" / "claude-code"
        xdg_dir.mkdir(parents=True)
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir(parents=True)

        with patch.object(_setup_module.Path, "home", return_value=tmp_path):
            config_path = _setup_module.get_claude_config_path()

        # XDG should be preferred
        assert config_path == xdg_dir / "mcp_servers.json"


class TestRegisterMcpServer:
    """Tests for register_mcp_server function."""

    def test_creates_new_config(self, tmp_path):
        """Test creating a new MCP server config."""
        config_path = tmp_path / ".claude" / "mcp_servers.json"
        config_path.parent.mkdir(parents=True)

        with patch.object(_setup_module, "get_claude_config_path", return_value=config_path):
            success = _setup_module.register_mcp_server()

        assert success
        assert config_path.exists()

        # Verify config content
        config = json.loads(config_path.read_text())
        assert "mcpServers" in config
        assert "dazzle" in config["mcpServers"]
        assert config["mcpServers"]["dazzle"]["args"] == ["-m", "dazzle.mcp"]
        assert config["mcpServers"]["dazzle"]["autoStart"] is True

    def test_scoped_servers_pin_distinct_project_roots(self, tmp_path):
        config_path = tmp_path / "mcp_servers.json"
        projects = [tmp_path / "one" / "app", tmp_path / "two" / "app"]
        for project in projects:
            project.mkdir(parents=True)
            (project / "dazzle.toml").write_text("[project]\nname = 'app'\n")

        with patch.object(_setup_module, "get_claude_config_path", return_value=config_path):
            for project in projects:
                assert _setup_module.register_mcp_server(working_dir=project)

        servers = json.loads(config_path.read_text())["mcpServers"]
        assert len(servers) == 2
        assert {tuple(server["args"][-2:]) for server in servers.values()} == {
            ("--working-dir", str(project)) for project in projects
        }

    def test_scoped_server_accepts_framework_checkout(self, tmp_path):
        config_path = tmp_path / "mcp_servers.json"
        (tmp_path / "src" / "dazzle").mkdir(parents=True)
        (tmp_path / "examples").mkdir()

        with patch.object(_setup_module, "get_claude_config_path", return_value=config_path):
            assert _setup_module.register_mcp_server(working_dir=tmp_path)

        server = next(iter(json.loads(config_path.read_text())["mcpServers"].values()))
        assert server["args"][-2:] == ["--working-dir", str(tmp_path)]

    def test_scoped_server_can_replace_global_entry(self, tmp_path):
        config_path = tmp_path / "mcp_servers.json"
        config_path.write_text(
            json.dumps({"mcpServers": {"dazzle": {"command": "old-python", "args": []}}})
        )
        project = tmp_path / "project"
        project.mkdir()
        (project / "dazzle.toml").write_text("[project]\nname = 'project'\n")

        with patch.object(_setup_module, "get_claude_config_path", return_value=config_path):
            assert _setup_module.register_mcp_server(working_dir=project, name="dazzle", force=True)

        servers = json.loads(config_path.read_text())["mcpServers"]
        assert list(servers) == ["dazzle"]
        assert servers["dazzle"]["args"][-2:] == ["--working-dir", str(project)]

    def test_merges_with_existing_config(self, tmp_path):
        """Test merging with existing MCP server config."""
        config_path = tmp_path / ".claude" / "mcp_servers.json"
        config_path.parent.mkdir(parents=True)

        # Create existing config with another server
        existing_config = {"mcpServers": {"other-server": {"command": "other", "args": []}}}
        config_path.write_text(json.dumps(existing_config))

        with patch.object(_setup_module, "get_claude_config_path", return_value=config_path):
            success = _setup_module.register_mcp_server()

        assert success

        # Verify both servers are present
        config = json.loads(config_path.read_text())
        assert "other-server" in config["mcpServers"]
        assert "dazzle" in config["mcpServers"]

    def test_does_not_overwrite_without_force(self, tmp_path, capsys):
        """Test that existing DAZZLE config is not overwritten without force."""
        config_path = tmp_path / ".claude" / "mcp_servers.json"
        config_path.parent.mkdir(parents=True)

        # Create existing DAZZLE config
        existing_config = {
            "mcpServers": {
                "dazzle": {
                    "command": "custom-python",
                    "args": ["-m", "dazzle.mcp"],
                    "customField": "should-be-preserved",
                }
            }
        }
        config_path.write_text(json.dumps(existing_config))

        with patch.object(_setup_module, "get_claude_config_path", return_value=config_path):
            success = _setup_module.register_mcp_server(force=False)

        assert success

        # Verify config was not changed
        config = json.loads(config_path.read_text())
        assert config["mcpServers"]["dazzle"]["command"] == "custom-python"
        assert "customField" in config["mcpServers"]["dazzle"]

        # Check that message was printed
        captured = capsys.readouterr()
        assert "already registered" in captured.out

    def test_overwrites_with_force(self, tmp_path):
        """Test that existing DAZZLE config is overwritten with force=True."""
        config_path = tmp_path / ".claude" / "mcp_servers.json"
        config_path.parent.mkdir(parents=True)

        # Create existing DAZZLE config
        existing_config = {
            "mcpServers": {
                "dazzle": {
                    "command": "custom-python",
                    "args": ["-m", "dazzle.mcp"],
                    "customField": "should-be-removed",
                }
            }
        }
        config_path.write_text(json.dumps(existing_config))

        with patch.object(_setup_module, "get_claude_config_path", return_value=config_path):
            success = _setup_module.register_mcp_server(force=True)

        assert success

        # Verify config was updated
        config = json.loads(config_path.read_text())
        assert "customField" not in config["mcpServers"]["dazzle"]
        # Should have new autoStart field
        assert config["mcpServers"]["dazzle"]["autoStart"] is True

    def test_handles_invalid_json(self, tmp_path):
        """Test handling of invalid JSON in existing config."""
        config_path = tmp_path / ".claude" / "mcp_servers.json"
        config_path.parent.mkdir(parents=True)

        # Write invalid JSON
        config_path.write_text("{invalid json")

        with patch.object(_setup_module, "get_claude_config_path", return_value=config_path):
            success = _setup_module.register_mcp_server()

        assert success

        # Should create valid config
        config = json.loads(config_path.read_text())
        assert "mcpServers" in config
        assert "dazzle" in config["mcpServers"]

    def test_returns_false_when_no_config_path(self):
        """Test that False is returned when config path cannot be determined."""
        with patch.object(_setup_module, "get_claude_config_path", return_value=None):
            success = _setup_module.register_mcp_server()

        assert not success


class TestCheckMcpServer:
    """Tests for check_mcp_server function."""

    def test_not_registered_when_no_config(self, tmp_path):
        """Test status when no config file exists."""
        config_path = tmp_path / ".claude" / "mcp_servers.json"

        with patch.object(_setup_module, "get_claude_config_path", return_value=config_path):
            status = _setup_module.check_mcp_server()

        assert status["status"] == "not_registered"
        assert status["registered"] is False
        assert status["config_path"] == str(config_path)
        assert status["server_command"] is None

    def test_not_registered_when_no_dazzle_entry(self, tmp_path):
        """Test status when config exists but no DAZZLE entry."""
        config_path = tmp_path / ".claude" / "mcp_servers.json"
        config_path.parent.mkdir(parents=True)

        config = {"mcpServers": {"other-server": {"command": "other", "args": []}}}
        config_path.write_text(json.dumps(config))

        with patch.object(_setup_module, "get_claude_config_path", return_value=config_path):
            status = _setup_module.check_mcp_server()

        assert status["status"] == "not_registered"
        assert status["registered"] is False

    def test_registered_when_dazzle_entry_exists(self, tmp_path):
        """Test status when DAZZLE is registered."""
        config_path = tmp_path / ".claude" / "mcp_servers.json"
        config_path.parent.mkdir(parents=True)

        config = {
            "mcpServers": {"dazzle": {"command": "/usr/bin/python3", "args": ["-m", "dazzle.mcp"]}}
        }
        config_path.write_text(json.dumps(config))

        with patch.object(_setup_module, "get_claude_config_path", return_value=config_path):
            status = _setup_module.check_mcp_server()

        assert status["status"] == "registered"
        assert status["registered"] is True
        assert status["server_command"] == "/usr/bin/python3 -m dazzle.mcp"
        assert isinstance(status["tools"], list)

    def test_handles_invalid_json(self, tmp_path):
        """Test handling of invalid JSON in config file."""
        config_path = tmp_path / ".claude" / "mcp_servers.json"
        config_path.parent.mkdir(parents=True)

        config_path.write_text("{invalid json")

        with patch.object(_setup_module, "get_claude_config_path", return_value=config_path):
            status = _setup_module.check_mcp_server()

        assert status["status"] == "error"
        assert "error" in status

    def test_enumerates_tools(self, tmp_path):
        """Test that tools are enumerated when registered."""
        config_path = tmp_path / ".claude" / "mcp_servers.json"
        config_path.parent.mkdir(parents=True)

        config = {"mcpServers": {"dazzle": {"command": "python", "args": ["-m", "dazzle.mcp"]}}}
        config_path.write_text(json.dumps(config))

        with patch.object(_setup_module, "get_claude_config_path", return_value=config_path):
            status = _setup_module.check_mcp_server()

        # Should have at least the core consolidated tools
        assert len(status["tools"]) > 0
        assert "dsl" in status["tools"]
        assert "story" in status["tools"]
        assert "status" in status["tools"]

    def test_scoped_registration_resolves_for_working_dir(self, tmp_path):
        """Scoped `dazzle setup --working-dir` must be found by `mcp check`.

        Registration writes a project-scoped ``dazzle-<project>-<hash>`` entry;
        the checker has to resolve that same name for the requested root.
        """
        config_path = tmp_path / ".claude" / "mcp_servers.json"
        config_path.parent.mkdir(parents=True)

        project = tmp_path / "my_app"
        project.mkdir()
        (project / "dazzle.toml").write_text("")

        scoped = _setup_module._registration_server_name(project.resolve(), None)
        assert scoped is not None
        assert scoped != "dazzle"

        config_path.write_text(
            json.dumps(
                {"mcpServers": {scoped: {"command": "python", "args": ["-m", "dazzle.mcp"]}}}
            )
        )

        with patch.object(_setup_module, "get_claude_config_path", return_value=config_path):
            status = _setup_module.check_mcp_server(working_dir=project)

        assert status["registered"] is True
        assert status["status"] == "registered"
        assert status["server_name"] == scoped

    def test_bare_check_does_not_match_scoped_entry(self, tmp_path):
        """Without a working dir only the global ``dazzle`` key is recognised."""
        config_path = tmp_path / ".claude" / "mcp_servers.json"
        config_path.parent.mkdir(parents=True)

        project = tmp_path / "my_app"
        project.mkdir()
        (project / "dazzle.toml").write_text("")

        scoped = _setup_module._registration_server_name(project.resolve(), None)
        config_path.write_text(
            json.dumps(
                {"mcpServers": {scoped: {"command": "python", "args": ["-m", "dazzle.mcp"]}}}
            )
        )

        with patch.object(_setup_module, "get_claude_config_path", return_value=config_path):
            status = _setup_module.check_mcp_server()

        assert status["registered"] is False

    def test_global_entry_still_found_with_working_dir(self, tmp_path):
        """A global registration remains visible when a working dir is given."""
        config_path = tmp_path / ".claude" / "mcp_servers.json"
        config_path.parent.mkdir(parents=True)

        project = tmp_path / "my_app"
        project.mkdir()
        (project / "dazzle.toml").write_text("")

        config_path.write_text(
            json.dumps(
                {"mcpServers": {"dazzle": {"command": "python", "args": ["-m", "dazzle.mcp"]}}}
            )
        )

        with patch.object(_setup_module, "get_claude_config_path", return_value=config_path):
            status = _setup_module.check_mcp_server(working_dir=project)

        assert status["registered"] is True
        assert status["server_name"] == "dazzle"

    def test_register_then_check_round_trip(self, tmp_path):
        """End-to-end: the documented setup -> check sequence reports registered."""
        config_path = tmp_path / ".claude" / "mcp_servers.json"
        config_path.parent.mkdir(parents=True)

        project = tmp_path / "my_app"
        project.mkdir()
        (project / "dazzle.toml").write_text("")

        with patch.object(_setup_module, "get_claude_config_path", return_value=config_path):
            assert _setup_module.register_mcp_server(working_dir=project) is True
            status = _setup_module.check_mcp_server(working_dir=project)

        assert status["registered"] is True
        assert str(project.resolve()) in status["server_command"]
