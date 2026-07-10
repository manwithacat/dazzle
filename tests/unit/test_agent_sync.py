"""Integration tests for dazzle agent sync (harness-neutral layout, #1575)."""

import json
import re
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


def test_sync_creates_command_shims_and_portable_skills(minimal_project: Path) -> None:
    from dazzle.services.agent_commands.renderer import sync_to_project

    sync_to_project(minimal_project)
    commands_dir = minimal_project / ".claude" / "commands"
    skills_root = minimal_project / ".agents" / "skills"
    assert commands_dir.is_dir()
    assert skills_root.is_dir()
    # improve and ship should be available (min_entities=1)
    assert (commands_dir / "improve.md").exists()
    assert (commands_dir / "ship.md").exists()
    assert (skills_root / "improve" / "SKILL.md").exists()
    assert (skills_root / "ship" / "SKILL.md").exists()

    # Shims point at portable skill bodies (framework layout parity)
    ship_shim = (commands_dir / "ship.md").read_text()
    assert ".agents/skills/ship/SKILL.md" in ship_shim
    assert "---" not in ship_shim  # shims stay short — no full skill body

    ship_skill = (skills_root / "ship" / "SKILL.md").read_text()
    assert "name: ship" in ship_skill
    assert "dazzle-agent-command:ship:" in ship_skill
    assert "Pre-Flight" in ship_skill or "pre-flight" in ship_skill.lower() or "Ship" in ship_skill


def test_sync_creates_manifest(minimal_project: Path) -> None:
    from dazzle.services.agent_commands.renderer import sync_to_project

    sync_to_project(minimal_project)
    manifest_path = minimal_project / ".claude" / "commands" / ".manifest.json"
    assert manifest_path.exists()
    data = json.loads(manifest_path.read_text())
    assert "dazzle_version" in data
    assert "commands_version" in data
    assert data.get("layout") == "agents-skills-v1"
    assert "improve" in data["commands"]


def test_sync_creates_agents_md(minimal_project: Path) -> None:
    from dazzle.services.agent_commands.renderer import sync_to_project

    sync_to_project(minimal_project)
    assert (minimal_project / "AGENTS.md").exists()
    content = (minimal_project / "AGENTS.md").read_text()
    assert "# AGENTS.md" in content
    assert "## Workflows" in content
    # Workflows index uses bold skill names (same convention as framework AGENTS.md)
    assert "**ship**" in content
    assert ".agents/skills/ship/SKILL.md" in content
    assert "<!-- dazzle-agent-sync:begin -->" in content


def test_sync_preserves_existing_agents_md_policy(minimal_project: Path) -> None:
    from dazzle.services.agent_commands.renderer import sync_to_project

    (minimal_project / "AGENTS.md").write_text(
        "# AGENTS.md\n\n## Project notes\n\nKeep this custom guidance.\n",
        encoding="utf-8",
    )
    sync_to_project(minimal_project)
    content = (minimal_project / "AGENTS.md").read_text()
    assert "Keep this custom guidance." in content
    assert "**ship**" in content
    # Re-sync must not duplicate the managed block
    sync_to_project(minimal_project)
    content2 = (minimal_project / "AGENTS.md").read_text()
    assert content2.count("<!-- dazzle-agent-sync:begin -->") == 1
    assert content2.count("Keep this custom guidance.") == 1


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


def test_sync_writes_thin_claude_md_adapter(minimal_project: Path) -> None:
    from dazzle.services.agent_commands.renderer import sync_to_project

    sync_to_project(minimal_project)
    claude_md = minimal_project / ".claude" / "CLAUDE.md"
    content = claude_md.read_text()
    first = next(ln for ln in content.splitlines() if ln.strip())
    assert re.fullmatch(r"@(\.\./)?AGENTS\.md", first.strip())
    assert "Autonomous Development Commands" in content
    assert ".agents/skills/" in content


def test_sync_appends_to_claude_md(minimal_project: Path) -> None:
    from dazzle.services.agent_commands.renderer import sync_to_project

    claude_md = minimal_project / ".claude" / "CLAUDE.md"
    claude_md.parent.mkdir(parents=True, exist_ok=True)
    claude_md.write_text("# Existing\n\nContent.\n")
    sync_to_project(minimal_project)
    content = claude_md.read_text()
    assert "Existing" in content
    assert "Autonomous Development Commands" in content
    first = next(ln for ln in content.splitlines() if ln.strip())
    assert re.fullmatch(r"@(\.\./)?AGENTS\.md", first.strip())


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
    skills_root = minimal_project / ".agents" / "skills"
    # polish requires 3+ surfaces — minimal project has 0
    assert not (commands_dir / "polish.md").exists()
    assert not (skills_root / "polish").exists()
    # issues requires GitHub remote
    assert not (commands_dir / "issues.md").exists()
    assert not (skills_root / "issues").exists()


def test_blank_template_has_harness_neutral_layout() -> None:
    """Product blank template mirrors the in-repo multi-agent layout (#1575)."""
    from dazzle import __file__ as dazzle_file

    blank = Path(dazzle_file).resolve().parent / "templates" / "blank"
    agents = (blank / "AGENTS.md").read_text()
    assert "Canonical project instructions" in agents
    claude = (blank / ".claude" / "CLAUDE.md").read_text()
    first = next(ln for ln in claude.splitlines() if ln.strip())
    assert re.fullmatch(r"@(\.\./)?AGENTS\.md", first.strip())
    assert len(claude.splitlines()) <= 30
    copilot = (blank / ".github" / "copilot-instructions.md").read_text()
    assert "AGENTS.md" in copilot
    assert len(copilot.splitlines()) <= 25
