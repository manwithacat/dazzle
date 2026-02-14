"""Tests for CLI help auto-introspection.

Verifies that the typer app tree is walked correctly and the public
``get_cli_help()`` API keeps its backward-compatible shape.
"""

from __future__ import annotations

import pytest

from dazzle.mcp.cli_help import (
    MCP_TOOL_MAP,
    _get_commands,
    get_cli_help,
)

# ---------------------------------------------------------------------------
# Fixture: the introspected command dict (built once per session)
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def commands() -> dict:
    """Return the full introspected command dict."""
    return _get_commands()


# ===========================================================================
# Introspection completeness
# ===========================================================================


class TestIntrospectionCompleteness:
    """Verify every known command is discovered."""

    # fmt: off
    TOP_LEVEL = [
        "serve", "init", "validate", "lint", "inspect", "layout-plan",
        "analyze-spec", "example", "doctor", "workshop", "grammar",
        "build", "info", "stop", "rebuild", "logs", "status",
    ]
    # fmt: on

    SUB_COMMANDS = [
        "test generate",
        "test run",
        "test list",
        "test dsl-run",
        "test agent",
        "test run-all",
        "pipeline run",
        "composition audit",
        "composition report",
        "discovery coherence",
        "stubs generate",
        "stubs list",
        "story propose",
        "pitch scaffold",
        "pitch generate",
        "pitch validate",
        "kg export",
        "kg import",
        "lsp run",
        "lsp check",
        "mcp run",
        "mcp setup",
        "specs openapi",
        "specs asyncapi",
        "deploy generate",
        "deploy plan",
        "vocab init",
        "vocab list",
        "e2e run",
        "e2e run-all",
        "e2e clean",
        "auth create-user",
        "auth list-users",
        "db revision",
        "db upgrade",
        "events tail",
        "events status",
        "dlq list",
        "outbox status",
        "process-migrate status",
    ]

    NESTED = [
        "test feedback record-regression",
        "test feedback summary",
        "test feedback patterns",
    ]

    @pytest.mark.parametrize("cmd", TOP_LEVEL)
    def test_top_level_discovered(self, commands: dict, cmd: str) -> None:
        assert cmd in commands, f"top-level command '{cmd}' not found"

    @pytest.mark.parametrize("cmd", SUB_COMMANDS)
    def test_sub_command_discovered(self, commands: dict, cmd: str) -> None:
        assert cmd in commands, f"sub-command '{cmd}' not found"

    @pytest.mark.parametrize("cmd", NESTED)
    def test_nested_group_discovered(self, commands: dict, cmd: str) -> None:
        assert cmd in commands, f"nested command '{cmd}' not found"

    def test_total_command_count(self, commands: dict) -> None:
        # We know there are ~100+ commands.  Use a conservative lower bound
        # so the test doesn't break every time a new command is added.
        assert len(commands) >= 80, (
            f"Expected >= 80 commands, got {len(commands)}: {sorted(commands)}"
        )


# ===========================================================================
# Data quality
# ===========================================================================


class TestDataQuality:
    """Each entry must have minimum viable metadata."""

    def test_every_command_has_description(self, commands: dict) -> None:
        for name, info in commands.items():
            assert "description" in info, f"'{name}' missing description"

    def test_every_command_has_category(self, commands: dict) -> None:
        for name, info in commands.items():
            assert "category" in info, f"'{name}' missing category"

    def test_every_command_has_syntax(self, commands: dict) -> None:
        for name, info in commands.items():
            assert "syntax" in info, f"'{name}' missing syntax"
            assert info["syntax"].startswith("dazzle ")

    def test_serve_has_options(self, commands: dict) -> None:
        serve = commands["serve"]
        opts = serve.get("options", {})
        flag_keys = " ".join(opts.keys())
        assert "--port" in flag_keys or "-p" in flag_keys

    def test_mcp_tool_fields(self, commands: dict) -> None:
        for cmd_name, mcp_tool in MCP_TOOL_MAP.items():
            if cmd_name in commands:
                assert commands[cmd_name].get("mcp_tool") == mcp_tool

    def test_enrichments_merged(self, commands: dict) -> None:
        # serve should have the hand-written 'output' dict
        assert "output" in commands["serve"]
        assert commands["serve"]["output"]["ui_url"] == "http://localhost:3000"
        # init should have 'creates'
        assert "creates" in commands["init"]
        # lint should have 'checks'
        assert "checks" in commands["lint"]

    def test_pipeline_run_has_examples(self, commands: dict) -> None:
        info = commands.get("pipeline run", {})
        examples = info.get("examples", [])
        assert any("dazzle pipeline run" in e for e in examples)


# ===========================================================================
# Backward compatibility (public get_cli_help API)
# ===========================================================================


class TestGetCliHelp:
    """``get_cli_help()`` keeps the same return shape as the old static dict."""

    def test_overview_shape(self) -> None:
        result = get_cli_help(None)
        assert result["overview"] is True
        assert "categories" in result
        assert isinstance(result["categories"], dict)
        assert "quick_reference" in result
        assert "primary_command" in result
        assert result["primary_command"] == "dazzle serve"

    def test_found_command(self) -> None:
        result = get_cli_help("serve")
        assert result["found"] is True
        assert result["command"] == "serve"
        assert "description" in result
        assert "options" in result
        assert "syntax" in result

    def test_not_found(self) -> None:
        result = get_cli_help("nonexistent")
        assert result["found"] is False
        assert "available_commands" in result

    def test_dazzle_prefix_stripped(self) -> None:
        result = get_cli_help("dazzle serve")
        assert result["found"] is True
        assert result["command"] == "serve"

    def test_partial_match_suggestions(self) -> None:
        result = get_cli_help("val")
        assert result["found"] is False
        assert "suggestions" in result
        assert "validate" in result["suggestions"]

    def test_new_commands_found(self) -> None:
        for cmd in ("pipeline run", "composition audit", "discovery coherence"):
            result = get_cli_help(cmd)
            assert result["found"] is True, f"'{cmd}' should be found"

    def test_sub_command_prefix_suggests(self) -> None:
        # Querying just "composition" should return suggestions including
        # "composition audit" and "composition report".
        result = get_cli_help("composition")
        if not result.get("found"):
            suggestions = result.get("suggestions", [])
            assert any("composition" in s for s in suggestions)
