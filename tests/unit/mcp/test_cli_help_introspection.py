"""Tests for CLI help auto-introspection.

Verifies that the typer app tree is walked correctly and the public
``get_cli_help()`` API keeps its backward-compatible shape.
"""

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
    # v0.71.23 (#1120): `inspect` moved from a top-level command to a
    # typer group with subcommands (renderers / primitives / routes /
    # oauth-providers / api / project). The introspection helper only
    # captures leaves, not groups, so `inspect` no longer shows up at
    # the top level — its subcommands live in SUB_COMMANDS below.
    TOP_LEVEL = [
        "serve", "validate", "lint",
        "doctor", "grammar", "build",
    ]
    # fmt: on

    SUB_COMMANDS = [
        # v0.71.23 (#1120): inspect subcommands.
        "inspect project",
        "inspect renderers",
        "inspect primitives",
        "inspect routes",
        "inspect oauth-providers",
        "test generate",
        "test run",
        "test populate",
        "test dsl-run",
        "test agent",
        "test verify-story",
        "pipeline run",
        "story propose",
        "mcp run",
        "mcp setup",
        "deploy plan",
        "auth create-user",
        "auth list-users",
        "db revision",
        "db upgrade",
    ]

    NESTED = [
        "test walk list",
        "test walk validate",
        "test walk run",
    ]

    @pytest.mark.parametrize("cmd", TOP_LEVEL + SUB_COMMANDS + NESTED)
    def test_command_discovered(self, commands: dict, cmd: str) -> None:
        """Top-level leaves, group sub-commands and nested-group leaves are all walked."""
        assert cmd in commands, f"command '{cmd}' not found"

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

    def test_every_command_has_metadata(self, commands: dict) -> None:
        for name, info in commands.items():
            assert {"description", "category", "syntax"} <= info.keys(), name
            assert info["syntax"].startswith("dazzle "), name

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

    # Exact names resolve, with or without the ``dazzle`` prefix, including
    # sub-commands of groups.
    @pytest.mark.parametrize(
        ("query", "command"),
        [
            pytest.param("serve", "serve", id="top-level"),
            pytest.param("validate", "validate", id="top-level-validate"),
            pytest.param("dazzle serve", "serve", id="dazzle-prefix-stripped"),
            pytest.param("pipeline run", "pipeline run", id="sub-command-pipeline-run"),
            pytest.param("story propose", "story propose", id="sub-command-story-propose"),
        ],
    )
    def test_found(self, query: str, command: str) -> None:
        result = get_cli_help(query)
        assert result["found"] is True
        assert result["command"] == command
        assert {"description", "options", "syntax"} <= result.keys()

    @pytest.mark.parametrize("query", ["nonexistent", "xyznonexistentcommand12345"])
    def test_not_found_lists_available_commands(self, query: str) -> None:
        result = get_cli_help(query)
        assert result["found"] is False
        assert result["available_commands"]

    def test_partial_match_suggestions(self) -> None:
        result = get_cli_help("val")
        assert result["found"] is False
        assert any(m["command"] == "validate" for m in result["matches"])


# ===========================================================================
# search_commands()
# ===========================================================================


class TestSearchCommands:
    """Verify the search_commands() helper used by MCP and the CLI search cmd."""

    def test_search_by_name_ranks_name_hit_with_name_bonus(self) -> None:
        from dazzle.mcp.cli_help import search_commands

        results = search_commands("serve")
        for r in results:
            assert {"command", "description", "category", "score"} <= r.keys()
        serve_hits = [r for r in results if r["command"] == "serve"]
        assert serve_hits, "Expected 'serve' in results"
        # "serve" appears literally in the command name: name bonus is >= 3.
        assert serve_hits[0]["score"] >= 3

    def test_search_no_results(self) -> None:
        from dazzle.mcp.cli_help import search_commands

        assert search_commands("xyznonexistent999") == []

    def test_results_sorted_by_score_descending(self) -> None:
        from dazzle.mcp.cli_help import search_commands

        results = search_commands("test")
        assert len(results) > 1
        scores = [r["score"] for r in results]
        assert scores == sorted(scores, reverse=True)

    def test_search_category_match(self) -> None:
        from dazzle.mcp.cli_help import search_commands

        # "Runtime" is a category — searching for it returns that category's commands.
        assert "Runtime" in {r["category"] for r in search_commands("Runtime")}
