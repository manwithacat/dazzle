"""Unit tests for the cycle 198 Path γ explore spike handler.

These tests exercise the MCP handler's plumbing (session extraction,
env loading, error paths) without actually running ModeRunner +
DazzleAgent. The real end-to-end test of Path γ happens via an actual
MCP call after the Dazzle MCP server is restarted and the new
``discovery.explore`` operation is reachable.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_missing_mcp_session_returns_error() -> None:
    """When no progress context carries an MCP session, handler reports it clearly."""
    from dazzle.mcp.server.handlers.discovery.explore_spike import (
        discovery_explore_spike_handler,
    )

    result_json = await discovery_explore_spike_handler(
        Path("/tmp/unused"), {"example_name": "contact_manager"}
    )
    result = json.loads(result_json)

    assert result["spike"] == "cycle-198-path-gamma"
    assert "error" in result
    assert "MCP session" in result["error"]


@pytest.mark.asyncio
async def test_missing_mcp_session_on_empty_progress_ctx() -> None:
    """progress_ctx present but session attribute is None → same error path."""
    from dazzle.mcp.server.handlers.discovery.explore_spike import (
        discovery_explore_spike_handler,
    )

    progress_ctx = MagicMock()
    progress_ctx.session = None
    result_json = await discovery_explore_spike_handler(
        Path("/tmp/unused"),
        {"example_name": "contact_manager", "_progress": progress_ctx},
    )
    result = json.loads(result_json)
    assert "error" in result


@pytest.mark.asyncio
async def test_missing_example_directory_returns_error(tmp_path: Path) -> None:
    """If DAZZLE_PROJECT_ROOT points somewhere without the example, report it."""
    from dazzle.mcp.server.handlers.discovery.explore_spike import (
        discovery_explore_spike_handler,
    )

    progress_ctx = MagicMock()
    progress_ctx.session = MagicMock()  # non-None sentinel

    with patch.dict("os.environ", {"DAZZLE_PROJECT_ROOT": str(tmp_path)}):
        result_json = await discovery_explore_spike_handler(
            tmp_path,
            {"example_name": "nonexistent", "_progress": progress_ctx},
        )

    result = json.loads(result_json)
    assert "error" in result
    assert "example directory not found" in result["error"]


@pytest.mark.asyncio
async def test_happy_path_passes_session_to_run_explore_strategy(tmp_path: Path) -> None:
    """Handler extracts session + env + calls run_explore_strategy with mcp_session.

    Mocks ModeRunner and run_explore_strategy to avoid booting a real subprocess.
    """
    from dazzle.cli.runtime_impl.ux_cycle_impl.explore_strategy import ExploreOutcome
    from dazzle.mcp.server.handlers.discovery.explore_spike import (
        discovery_explore_spike_handler,
    )

    # Fake outcome returned from the mocked strategy
    fake_outcome = ExploreOutcome(
        strategy="EXPLORE/missing_contracts",
        summary="path-gamma test: 1 persona, 5 steps, 0 proposals",
        degraded=False,
        proposals=[],
        findings=[],
        blocked_personas=[],
        steps_run=5,
        tokens_used=10000,
        raw_proposals_by_persona={"user": 0},
    )

    # Stand up a minimal example directory so the env-load branch doesn't error
    example_name = "contact_manager"
    example_root = tmp_path / "examples" / example_name
    example_root.mkdir(parents=True)
    (example_root / ".env").write_text("DATABASE_URL=postgres://test\nREDIS_URL=redis://test\n")

    # Mock the session as a sentinel — the handler just needs to see it non-None
    sentinel_session = MagicMock(name="mcp-session-sentinel")
    progress_ctx = MagicMock()
    progress_ctx.session = sentinel_session

    # Mock ModeRunner as an async context manager
    mock_conn = MagicMock()
    mock_conn.site_url = "http://localhost:3000"
    mock_conn.api_url = "http://localhost:3000"

    class _FakeModeRunner:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return mock_conn

        async def __aexit__(self, exc_type, exc, tb):
            return None

    with (
        patch.dict("os.environ", {"DAZZLE_PROJECT_ROOT": str(tmp_path)}),
        patch("dazzle.e2e.runner.ModeRunner", new=_FakeModeRunner),
        patch(
            "dazzle.cli.runtime_impl.ux_cycle_impl.explore_strategy.run_explore_strategy",
            new=AsyncMock(return_value=fake_outcome),
        ) as mock_run,
    ):
        result_json = await discovery_explore_spike_handler(
            tmp_path,
            {
                "example_name": example_name,
                "persona_id": "user",
                "_progress": progress_ctx,
            },
        )

    # Verify the run was called with Path γ kwargs
    call_kwargs = mock_run.call_args.kwargs
    assert call_kwargs["mcp_session"] is sentinel_session
    assert call_kwargs["use_tool_calls"] is False
    assert call_kwargs["personas"] == ["user"]

    # Verify the returned JSON shape
    result = json.loads(result_json)
    assert result["spike"] == "cycle-198-path-gamma"
    assert result["example"] == example_name
    assert result["persona_arg"] == "user"
    assert result["degraded"] is False
    assert result["steps_run"] == 5
    assert result["tokens_used"] == 10000
