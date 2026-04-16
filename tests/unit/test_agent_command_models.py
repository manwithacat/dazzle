"""Tests for agent command data models and TOML loader."""

import re
from pathlib import Path

from dazzle.cli.agent_commands.loader import DEFINITIONS_DIR, load_all_commands, load_command
from dazzle.cli.agent_commands.models import (
    CommandDefinition,
    CommandStatus,
    LoopConfig,
    MaturityGate,
    SyncManifest,
    ToolsConfig,
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


def test_load_all_commands_finds_six() -> None:
    commands = load_all_commands()
    assert len(commands) == 6
    names = sorted(c.name for c in commands)
    assert names == ["improve", "issues", "polish", "qa", "ship", "spec-sync"]


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
