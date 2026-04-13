"""Tests for the Pass 2b behavioural proxy dispatcher."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from dazzle.agent.core import Mission
from dazzle.fitness.proxy import run_proxy_mission


@pytest.mark.asyncio
async def test_proxy_builds_free_roam_mission_and_runs_agent() -> None:
    agent = MagicMock()
    agent.run = AsyncMock(return_value="transcript")

    ledger = MagicMock()
    ledger.current_step.return_value = None

    persona = MagicMock(id="support_agent", name="support_agent")

    result = await run_proxy_mission(
        agent=agent,
        persona=persona,
        intent="triage the oldest open ticket",
        step_budget=20,
        ledger=ledger,
    )

    assert agent.run.await_count == 1
    mission_arg = agent.run.await_args.args[0]
    assert isinstance(mission_arg, Mission)
    assert mission_arg.name.startswith("fitness.free_roam")
    assert "support_agent" in mission_arg.name
    assert "triage the oldest open ticket" in mission_arg.system_prompt
    assert "EXPECT" in mission_arg.system_prompt
    assert "ACTION" in mission_arg.system_prompt
    assert "OBSERVE" in mission_arg.system_prompt
    assert mission_arg.max_steps == 20
    assert result == "transcript"
