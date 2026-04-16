"""Tests for agent command data models, TOML loader, and renderer."""

import re
from pathlib import Path

from dazzle.services.agent_commands.loader import DEFINITIONS_DIR, load_all_commands, load_command
from dazzle.services.agent_commands.models import (
    CommandDefinition,
    CommandStatus,
    LoopConfig,
    MaturityGate,
    SyncManifest,
    ToolsConfig,
)
from dazzle.services.agent_commands.renderer import (
    TEMPLATES_DIR,
    evaluate_maturity,
    render_agents_md,
    render_claude_md_section,
    render_skill,
)

SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+$")


def test_maturity_gate_defaults() -> None:
    gate = MaturityGate()
    assert gate.min_entities == 0
    assert gate.min_surfaces == 0
    assert gate.min_stories == 0
    assert gate.requires_running_app is False
    assert gate.requires_github_remote is False
    assert gate.requires_spec_md is False
    assert gate.requires == []


def test_loop_config_fields() -> None:
    lc = LoopConfig(
        backlog_file="agent/backlog.md",
        log_file="agent/log.md",
        lock_file="agent/lock",
        max_cycles=10,
        stale_lock_minutes=15,
    )
    assert lc.backlog_file == "agent/backlog.md"
    assert lc.log_file == "agent/log.md"
    assert lc.lock_file == "agent/lock"
    assert lc.max_cycles == 10
    assert lc.stale_lock_minutes == 15


def test_command_definition_full() -> None:
    cmd = CommandDefinition(
        name="improve",
        version="1.0.0",
        title="Improve",
        description="Autonomous improvement loop.",
        pattern="loop",
        maturity=MaturityGate(min_entities=1, requires=["validate"]),
        loop=LoopConfig(backlog_file="agent/improve-backlog.md"),
        tools=ToolsConfig(mcp=["dsl.lint"], cli=["dazzle validate"]),
        template_file="improve.md.j2",
    )
    assert cmd.name == "improve"
    assert cmd.pattern == "loop"
    assert cmd.maturity.min_entities == 1
    assert cmd.loop is not None
    assert cmd.loop.backlog_file == "agent/improve-backlog.md"
    assert "dsl.lint" in cmd.tools.mcp
    assert cmd.template_file == "improve.md.j2"


def test_command_definition_one_shot() -> None:
    cmd = CommandDefinition(
        name="ship",
        version="1.0.0",
        title="Ship",
        description="One-shot ship.",
        pattern="one-shot",
        maturity=MaturityGate(min_entities=1),
        loop=None,
        template_file="ship.md.j2",
    )
    assert cmd.pattern == "one-shot"
    assert cmd.loop is None


def test_sync_manifest() -> None:
    manifest = SyncManifest(
        dazzle_version="0.55.0",
        commands_version="1.0.0",
        synced_at="2026-04-16T12:00:00Z",
        commands={
            "improve": CommandStatus(version="1.0.0", available=True),
            "ship": CommandStatus(version="1.0.0", available=False, reason="validation failed"),
        },
    )
    assert manifest.dazzle_version == "0.55.0"
    assert manifest.commands["improve"].available is True
    assert manifest.commands["ship"].reason == "validation failed"


def test_load_command_from_toml(tmp_path: Path) -> None:
    toml_content = """\
[command]
name = "test-cmd"
version = "2.0.0"
title = "Test Command"
description = "A test command."
pattern = "loop"

[maturity]
min_entities = 3
requires = ["validate", "lint"]

[loop]
backlog_file = "agent/test-backlog.md"
log_file = "agent/test-log.md"
lock_file = "agent/test.lock"
max_cycles = 25
stale_lock_minutes = 10

[tools]
mcp = ["dsl.lint"]
cli = ["dazzle validate"]

[skill_template]
file = "test-cmd.md.j2"
"""
    p = tmp_path / "test.toml"
    p.write_text(toml_content, encoding="utf-8")
    cmd = load_command(p)

    assert cmd.name == "test-cmd"
    assert cmd.version == "2.0.0"
    assert cmd.pattern == "loop"
    assert cmd.maturity.min_entities == 3
    assert cmd.maturity.requires == ["validate", "lint"]
    assert cmd.loop is not None
    assert cmd.loop.backlog_file == "agent/test-backlog.md"
    assert cmd.loop.max_cycles == 25
    assert cmd.tools.mcp == ["dsl.lint"]
    assert cmd.template_file == "test-cmd.md.j2"


def test_load_command_one_shot_no_loop(tmp_path: Path) -> None:
    toml_content = """\
[command]
name = "quick"
version = "1.0.0"
title = "Quick"
description = "A one-shot command."
pattern = "one-shot"

[maturity]
requires_spec_md = true

[tools]
mcp = ["dsl.validate"]

[skill_template]
file = "quick.md.j2"
"""
    p = tmp_path / "quick.toml"
    p.write_text(toml_content, encoding="utf-8")
    cmd = load_command(p)

    assert cmd.pattern == "one-shot"
    assert cmd.loop is None
    assert cmd.maturity.requires_spec_md is True


def test_definitions_dir_exists() -> None:
    assert DEFINITIONS_DIR.is_dir(), f"{DEFINITIONS_DIR} is not a directory"


def test_load_all_commands_finds_definitions() -> None:
    commands = load_all_commands()
    assert len(commands) >= 1


def test_load_all_commands_finds_all_definitions() -> None:
    commands = load_all_commands()
    assert len(commands) == 7
    names = sorted(c.name for c in commands)
    assert names == [
        "explore",
        "improve",
        "issues",
        "polish",
        "qa",
        "ship",
        "spec-sync",
    ]


def test_all_definitions_have_valid_versions() -> None:
    commands = load_all_commands()
    for cmd in commands:
        assert SEMVER_RE.match(cmd.version), (
            f"Command {cmd.name!r} has invalid version {cmd.version!r}"
        )


def test_all_loop_commands_have_backlog_files() -> None:
    commands = load_all_commands()
    loop_commands = [c for c in commands if c.pattern == "loop"]
    assert len(loop_commands) > 0, "Expected at least one loop command"
    for cmd in loop_commands:
        assert cmd.loop is not None, f"Loop command {cmd.name!r} has no loop config"
        assert cmd.loop.backlog_file.startswith("agent/"), (
            f"Command {cmd.name!r} backlog_file should start with 'agent/'"
        )


def test_all_commands_have_template_files() -> None:
    commands = load_all_commands()
    for cmd in commands:
        assert cmd.template_file.endswith(".md.j2"), (
            f"Command {cmd.name!r} template_file {cmd.template_file!r} should end with '.md.j2'"
        )


# ---------------------------------------------------------------------------
# Maturity gate tests
# ---------------------------------------------------------------------------


def _make_project_context(**overrides: object) -> dict:
    """Build a minimal project context dict with sensible defaults."""
    ctx: dict = {
        "entity_count": 5,
        "surface_count": 5,
        "story_count": 5,
        "has_spec_md": True,
        "has_github_remote": True,
        "validate_passes": True,
        "app_running": True,
        "entity_names": ["Task"],
        "persona_names": ["admin"],
        "surface_names": ["task_list"],
        "project_name": "test_project",
    }
    ctx.update(overrides)
    return ctx


def test_evaluate_maturity_all_met() -> None:
    gate = MaturityGate(min_entities=1)
    ctx = _make_project_context(entity_count=3)
    available, reason = evaluate_maturity(gate, ctx)
    assert available is True
    assert reason is None


def test_evaluate_maturity_entities_unmet() -> None:
    gate = MaturityGate(min_entities=2)
    ctx = _make_project_context(entity_count=1)
    available, reason = evaluate_maturity(gate, ctx)
    assert available is False
    assert reason is not None
    assert "entities" in reason


def test_evaluate_maturity_surfaces_unmet() -> None:
    gate = MaturityGate(min_surfaces=3)
    ctx = _make_project_context(surface_count=1)
    available, reason = evaluate_maturity(gate, ctx)
    assert available is False
    assert reason is not None
    assert "surfaces" in reason


def test_evaluate_maturity_spec_md_required() -> None:
    gate = MaturityGate(requires_spec_md=True)
    ctx = _make_project_context(has_spec_md=False)
    available, reason = evaluate_maturity(gate, ctx)
    assert available is False
    assert reason is not None
    assert "SPEC.md" in reason


def test_evaluate_maturity_github_remote_required() -> None:
    gate = MaturityGate(requires_github_remote=True)
    ctx = _make_project_context(has_github_remote=False)
    available, reason = evaluate_maturity(gate, ctx)
    assert available is False
    assert reason is not None
    assert "GitHub" in reason


def test_evaluate_maturity_validate_required() -> None:
    gate = MaturityGate(requires=["validate"])
    ctx = _make_project_context(validate_passes=False)
    available, reason = evaluate_maturity(gate, ctx)
    assert available is False
    assert reason is not None
    assert "validate" in reason.lower()


def test_evaluate_maturity_empty_gate_always_available() -> None:
    gate = MaturityGate()
    ctx = _make_project_context(
        entity_count=0,
        surface_count=0,
        story_count=0,
        has_spec_md=False,
        has_github_remote=False,
        validate_passes=False,
        app_running=False,
    )
    available, reason = evaluate_maturity(gate, ctx)
    assert available is True
    assert reason is None


# ---------------------------------------------------------------------------
# Template tests
# ---------------------------------------------------------------------------

_EXPECTED_TEMPLATES = [
    "improve.md.j2",
    "qa.md.j2",
    "spec_sync.md.j2",
    "ship.md.j2",
    "polish.md.j2",
    "issues.md.j2",
    "agents_md.j2",
    "claude_md_section.j2",
]


def test_all_templates_exist() -> None:
    for name in _EXPECTED_TEMPLATES:
        path = TEMPLATES_DIR / name
        assert path.exists(), f"Template {name} not found at {path}"


def test_render_improve_skill() -> None:
    cmd = CommandDefinition(
        name="improve",
        version="1.0.0",
        title="Improve",
        description="Autonomous improvement loop.",
        pattern="loop",
        maturity=MaturityGate(min_entities=1),
        loop=LoopConfig(
            backlog_file="agent/improve-backlog.md",
            log_file="agent/improve-log.md",
            lock_file="agent/improve.lock",
            max_cycles=50,
        ),
        tools=ToolsConfig(mcp=["dsl.lint"], cli=["dazzle validate"]),
        template_file="improve.md.j2",
    )
    ctx = _make_project_context()
    output = render_skill(cmd, ctx)
    assert "Autonomous Improvement Loop" in output
    assert "agent/improve-backlog.md" in output
    assert "dsl.lint" in output


def test_render_agents_md() -> None:
    cmd = CommandDefinition(
        name="improve",
        version="1.0.0",
        title="Improve",
        description="Autonomous improvement loop.",
        pattern="loop",
        maturity=MaturityGate(min_entities=1),
        loop=LoopConfig(backlog_file="agent/improve-backlog.md"),
        tools=ToolsConfig(mcp=["dsl.lint"]),
        template_file="improve.md.j2",
    )
    commands = [(cmd, True, None)]
    ctx = _make_project_context()
    output = render_agents_md(commands, ctx)
    assert "# Agent Commands" in output
    assert "/improve" in output


def test_render_claude_md_section() -> None:
    cmd = CommandDefinition(
        name="improve",
        version="1.0.0",
        title="Improve",
        description="Autonomous improvement loop.",
        pattern="loop",
        maturity=MaturityGate(min_entities=1),
        loop=LoopConfig(backlog_file="agent/improve-backlog.md"),
        tools=ToolsConfig(mcp=["dsl.lint"]),
        template_file="improve.md.j2",
    )
    commands = [(cmd, True, None)]
    ctx = _make_project_context()
    output = render_claude_md_section(commands, ctx)
    assert "## Autonomous Development Commands" in output
    assert "Agent Tool Convention" in output
