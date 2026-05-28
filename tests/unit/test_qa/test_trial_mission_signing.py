"""Tests for signing tools in trial mission."""

from dazzle.agent.core import AgentTool
from dazzle.agent.missions.trial import build_trial_mission


def test_baseline_tools_present():
    """Verify baseline trial tools are always present."""
    mission = build_trial_mission(
        scenario={"name": "t", "tasks": []},
        base_url="http://localhost:3000",
        transcript_sink={},
        signing_tools=None,
    )
    names = {t.name for t in mission.tools}
    assert "record_friction" in names
    assert "submit_verdict" in names


def test_signing_tools_appended_when_provided():
    """Verify signing tools are appended when provided."""
    fake = _make_fake_tool("open_signing_link")
    mission = build_trial_mission(
        scenario={"name": "t", "tasks": []},
        base_url="http://localhost:3000",
        transcript_sink={},
        signing_tools=[fake],
    )
    assert "open_signing_link" in {t.name for t in mission.tools}


def test_multiple_signing_tools():
    """Verify multiple signing tools can be provided."""
    tools = [
        _make_fake_tool("open_signing_link"),
        _make_fake_tool("check_signature_status"),
    ]
    mission = build_trial_mission(
        scenario={"name": "t", "tasks": []},
        base_url="http://localhost:3000",
        transcript_sink={},
        signing_tools=tools,
    )
    names = {t.name for t in mission.tools}
    assert "open_signing_link" in names
    assert "check_signature_status" in names
    # Baseline tools still present
    assert "record_friction" in names
    assert "submit_verdict" in names


def test_signing_flow_guidance_in_system_prompt_when_tools_present():
    """System prompt must contain signing-flow guidance when signing tools are provided."""
    fake = _make_fake_tool("open_signing_link")
    mission = build_trial_mission(
        scenario={"name": "t", "tasks": []},
        base_url="http://localhost:3000",
        transcript_sink={},
        signing_tools=[fake],
    )
    assert "Signing flow" in mission.system_prompt
    assert "Do NOT use the navigate or click tools" in mission.system_prompt


def test_no_signing_guidance_when_tools_absent():
    """System prompt must NOT contain signing-flow guidance when signing_tools is None."""
    mission = build_trial_mission(
        scenario={"name": "t", "tasks": []},
        base_url="http://localhost:3000",
        transcript_sink={},
        signing_tools=None,
    )
    assert "Signing flow" not in mission.system_prompt


def _make_fake_tool(name: str) -> AgentTool:
    """Construct an AgentTool for testing."""
    return AgentTool(
        name=name,
        description="Test tool",
        schema={"type": "object", "properties": {}},
        handler=lambda: "ok",
    )
