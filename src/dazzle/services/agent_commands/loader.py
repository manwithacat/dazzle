"""TOML loader for agent command definitions."""

import tomllib
from pathlib import Path

from .models import CommandDefinition, LoopConfig, MaturityGate, ToolsConfig

DEFINITIONS_DIR: Path = Path(__file__).parent / "definitions"


def load_command(path: Path) -> CommandDefinition:
    """Parse a single TOML file into a CommandDefinition."""
    data = tomllib.loads(path.read_text(encoding="utf-8"))

    cmd = data.get("command", {})
    mat = data.get("maturity", {})
    loop_data = data.get("loop", None)
    tools_data = data.get("tools", {})
    tmpl = data.get("skill_template", {})

    maturity = MaturityGate(
        min_entities=mat.get("min_entities", 0),
        min_surfaces=mat.get("min_surfaces", 0),
        min_stories=mat.get("min_stories", 0),
        requires_running_app=mat.get("requires_running_app", False),
        requires_github_remote=mat.get("requires_github_remote", False),
        requires_spec_md=mat.get("requires_spec_md", False),
        requires=mat.get("requires", []),
    )

    loop: LoopConfig | None = None
    if loop_data is not None:
        loop = LoopConfig(
            backlog_file=loop_data.get("backlog_file", ""),
            log_file=loop_data.get("log_file", ""),
            lock_file=loop_data.get("lock_file", ""),
            max_cycles=loop_data.get("max_cycles", 50),
            stale_lock_minutes=loop_data.get("stale_lock_minutes", 30),
        )

    tools = ToolsConfig(
        mcp=tools_data.get("mcp", []),
        cli=tools_data.get("cli", []),
    )

    return CommandDefinition(
        name=cmd.get("name", ""),
        version=cmd.get("version", ""),
        title=cmd.get("title", ""),
        description=cmd.get("description", ""),
        pattern=cmd.get("pattern", "one-shot"),
        maturity=maturity,
        loop=loop,
        tools=tools,
        template_file=tmpl.get("file", ""),
    )


def load_all_commands() -> list[CommandDefinition]:
    """Load all .toml command definitions from the definitions directory."""
    if not DEFINITIONS_DIR.is_dir():
        return []
    paths = sorted(DEFINITIONS_DIR.glob("*.toml"))
    return [load_command(p) for p in paths]
