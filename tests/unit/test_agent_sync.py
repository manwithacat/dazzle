"""Integration tests for dazzle agent sync."""

import json
from pathlib import Path

import pytest


@pytest.fixture
def minimal_project(tmp_path: Path) -> Path:
    """Minimal project with one entity — enough for improve/ship to be available."""
    dsl_dir = tmp_path / "dsl"
    dsl_dir.mkdir()
    (dsl_dir / "app.dsl").write_text(
        'module test\napp test "Test App"\n\n'
        'entity Task "Task":\n  id: uuid pk\n  title: str(200) required\n'
    )
    (tmp_path / "dazzle.toml").write_text(
        '[project]\nname = "test"\nroot = "test"\n\n[modules]\npaths = ["./dsl"]\n'
    )
    (tmp_path / "SPEC.md").write_text("# Test App\n\nA simple task manager.\n" * 10)
    return tmp_path


def test_sync_creates_command_files(minimal_project: Path) -> None:
    from dazzle.services.agent_commands.renderer import sync_to_project

    sync_to_project(minimal_project)
    commands_dir = minimal_project / ".claude" / "commands"
    assert commands_dir.is_dir()
    # improve and ship should be available (min_entities=1)
    assert (commands_dir / "improve.md").exists()
    assert (commands_dir / "ship.md").exists()


def test_sync_creates_manifest(minimal_project: Path) -> None:
    from dazzle.services.agent_commands.renderer import sync_to_project

    sync_to_project(minimal_project)
    manifest_path = minimal_project / ".claude" / "commands" / ".manifest.json"
    assert manifest_path.exists()
    data = json.loads(manifest_path.read_text())
    assert "dazzle_version" in data
    assert "commands_version" in data
    assert "improve" in data["commands"]


def test_sync_creates_agents_md(minimal_project: Path) -> None:
    from dazzle.services.agent_commands.renderer import sync_to_project

    sync_to_project(minimal_project)
    assert (minimal_project / "AGENTS.md").exists()
    content = (minimal_project / "AGENTS.md").read_text()
    assert "Agent Commands" in content


def test_sync_seeds_backlog_files(minimal_project: Path) -> None:
    from dazzle.services.agent_commands.renderer import sync_to_project

    sync_to_project(minimal_project)
    assert (minimal_project / "agent" / "improve-backlog.md").exists()
    assert (minimal_project / "agent" / "improve-log.md").exists()


def test_sync_is_idempotent(minimal_project: Path) -> None:
    from dazzle.services.agent_commands.renderer import sync_to_project

    sync_to_project(minimal_project)
    first = (minimal_project / "AGENTS.md").read_text()
    sync_to_project(minimal_project)
    second = (minimal_project / "AGENTS.md").read_text()
    assert first == second


def test_sync_preserves_existing_backlogs(minimal_project: Path) -> None:
    from dazzle.services.agent_commands.renderer import sync_to_project

    sync_to_project(minimal_project)
    backlog = minimal_project / "agent" / "improve-backlog.md"
    backlog.write_text("| 1 | lint | DONE |\n")
    sync_to_project(minimal_project)
    assert "DONE" in backlog.read_text()


def test_sync_appends_to_claude_md(minimal_project: Path) -> None:
    from dazzle.services.agent_commands.renderer import sync_to_project

    claude_md = minimal_project / ".claude" / "CLAUDE.md"
    claude_md.parent.mkdir(parents=True, exist_ok=True)
    claude_md.write_text("# Existing\n\nContent.\n")
    sync_to_project(minimal_project)
    content = claude_md.read_text()
    assert "Existing" in content
    assert "Autonomous Development Commands" in content


def test_sync_does_not_duplicate_claude_md_section(minimal_project: Path) -> None:
    from dazzle.services.agent_commands.renderer import sync_to_project

    sync_to_project(minimal_project)
    sync_to_project(minimal_project)
    claude_md = minimal_project / ".claude" / "CLAUDE.md"
    content = claude_md.read_text()
    assert content.count("## Autonomous Development Commands") == 1


def test_unavailable_commands_not_written(minimal_project: Path) -> None:
    from dazzle.services.agent_commands.renderer import sync_to_project

    sync_to_project(minimal_project)
    commands_dir = minimal_project / ".claude" / "commands"
    # polish requires 3+ surfaces — minimal project has 0
    assert not (commands_dir / "polish.md").exists()
    # issues requires GitHub remote
    assert not (commands_dir / "issues.md").exists()
