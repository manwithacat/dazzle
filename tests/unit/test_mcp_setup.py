"""Tests for MCP server setup and configuration."""

import json
from unittest.mock import patch

from dazzle.mcp.setup import (
    check_mcp_server,
    get_claude_config_path,
    register_mcp_server,
)


class TestGetClaudeConfigPath:
    """Tests for get_claude_config_path function."""

    def test_finds_existing_xdg_config(self, tmp_path):
        """Test that XDG config location is preferred if it exists."""
        # Create XDG directory
        xdg_dir = tmp_path / ".config" / "claude-code"
        xdg_dir.mkdir(parents=True)

        with patch("dazzle.mcp.setup.Path.home", return_value=tmp_path):
            config_path = get_claude_config_path()

        assert config_path == xdg_dir / "mcp_servers.json"

    def test_finds_existing_claude_dir(self, tmp_path):
        """Test that .claude directory is used if it exists."""
        # Create .claude directory
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir(parents=True)

        with patch("dazzle.mcp.setup.Path.home", return_value=tmp_path):
            config_path = get_claude_config_path()

        assert config_path == claude_dir / "mcp_servers.json"

    def test_creates_default_directory(self, tmp_path):
        """Test that default directory is created if none exist."""
        with patch("dazzle.mcp.setup.Path.home", return_value=tmp_path):
            config_path = get_claude_config_path()

        assert config_path == tmp_path / ".claude" / "mcp_servers.json"
        assert config_path.parent.exists()

    def test_prefers_xdg_over_claude(self, tmp_path):
        """Test that XDG location is preferred over .claude."""
        # Create both directories
        xdg_dir = tmp_path / ".config" / "claude-code"
        xdg_dir.mkdir(parents=True)
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir(parents=True)

        with patch("dazzle.mcp.setup.Path.home", return_value=tmp_path):
            config_path = get_claude_config_path()

        # XDG should be preferred
        assert config_path == xdg_dir / "mcp_servers.json"


class TestRegisterMcpServer:
    """Tests for register_mcp_server function."""

    def test_creates_new_config(self, tmp_path):
        """Test creating a new MCP server config."""
        config_path = tmp_path / ".claude" / "mcp_servers.json"
        config_path.parent.mkdir(parents=True)

        with patch("dazzle.mcp.setup.get_claude_config_path", return_value=config_path):
            success = register_mcp_server()

        assert success
        assert config_path.exists()

        # Verify config content
        config = json.loads(config_path.read_text())
        assert "mcpServers" in config
        assert "dazzle" in config["mcpServers"]
        assert config["mcpServers"]["dazzle"]["args"] == ["-m", "dazzle.mcp"]
        assert config["mcpServers"]["dazzle"]["autoStart"] is True

    def test_merges_with_existing_config(self, tmp_path):
        """Test merging with existing MCP server config."""
        config_path = tmp_path / ".claude" / "mcp_servers.json"
        config_path.parent.mkdir(parents=True)

        # Create existing config with another server
        existing_config = {"mcpServers": {"other-server": {"command": "other", "args": []}}}
        config_path.write_text(json.dumps(existing_config))

        with patch("dazzle.mcp.setup.get_claude_config_path", return_value=config_path):
            success = register_mcp_server()

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

        with patch("dazzle.mcp.setup.get_claude_config_path", return_value=config_path):
            success = register_mcp_server(force=False)

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

        with patch("dazzle.mcp.setup.get_claude_config_path", return_value=config_path):
            success = register_mcp_server(force=True)

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

        with patch("dazzle.mcp.setup.get_claude_config_path", return_value=config_path):
            success = register_mcp_server()

        assert success

        # Should create valid config
        config = json.loads(config_path.read_text())
        assert "mcpServers" in config
        assert "dazzle" in config["mcpServers"]

    def test_returns_false_when_no_config_path(self):
        """Test that False is returned when config path cannot be determined."""
        with patch("dazzle.mcp.setup.get_claude_config_path", return_value=None):
            success = register_mcp_server()

        assert not success


class TestCheckMcpServer:
    """Tests for check_mcp_server function."""

    def test_not_registered_when_no_config(self, tmp_path):
        """Test status when no config file exists."""
        config_path = tmp_path / ".claude" / "mcp_servers.json"

        with patch("dazzle.mcp.setup.get_claude_config_path", return_value=config_path):
            status = check_mcp_server()

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

        with patch("dazzle.mcp.setup.get_claude_config_path", return_value=config_path):
            status = check_mcp_server()

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

        with patch("dazzle.mcp.setup.get_claude_config_path", return_value=config_path):
            status = check_mcp_server()

        assert status["status"] == "registered"
        assert status["registered"] is True
        assert status["server_command"] == "/usr/bin/python3 -m dazzle.mcp"
        assert isinstance(status["tools"], list)

    def test_handles_invalid_json(self, tmp_path):
        """Test handling of invalid JSON in config file."""
        config_path = tmp_path / ".claude" / "mcp_servers.json"
        config_path.parent.mkdir(parents=True)

        config_path.write_text("{invalid json")

        with patch("dazzle.mcp.setup.get_claude_config_path", return_value=config_path):
            status = check_mcp_server()

        assert status["status"] == "error"
        assert "error" in status

    def test_enumerates_tools(self, tmp_path):
        """Test that tools are enumerated when registered."""
        config_path = tmp_path / ".claude" / "mcp_servers.json"
        config_path.parent.mkdir(parents=True)

        config = {"mcpServers": {"dazzle": {"command": "python", "args": ["-m", "dazzle.mcp"]}}}
        config_path.write_text(json.dumps(config))

        with patch("dazzle.mcp.setup.get_claude_config_path", return_value=config_path):
            status = check_mcp_server()

        # Should have at least the core tools
        assert len(status["tools"]) > 0
        assert "validate_dsl" in status["tools"]
        assert "build" in status["tools"]
        assert "inspect_entity" in status["tools"]
