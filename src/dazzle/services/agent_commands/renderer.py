"""Maturity gate evaluator, template renderer, and project sync for agent commands."""

import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader

from .loader import load_all_commands
from .models import CommandDefinition, CommandStatus, MaturityGate, SyncManifest

logger = logging.getLogger(__name__)

TEMPLATES_DIR: Path = Path(__file__).parent / "templates"


def evaluate_maturity(gate: MaturityGate, ctx: dict[str, Any]) -> tuple[bool, str | None]:
    """Check whether a project meets a command's maturity prerequisites.

    Returns (available, reason). reason is None when available is True.
    """
    if gate.min_entities > 0 and ctx.get("entity_count", 0) < gate.min_entities:
        return False, (
            f"Requires {gate.min_entities}+ entities (project has {ctx.get('entity_count', 0)})"
        )

    if gate.min_surfaces > 0 and ctx.get("surface_count", 0) < gate.min_surfaces:
        return False, (
            f"Requires {gate.min_surfaces}+ surfaces (project has {ctx.get('surface_count', 0)})"
        )

    if gate.min_stories > 0 and ctx.get("story_count", 0) < gate.min_stories:
        return False, (
            f"Requires {gate.min_stories}+ stories (project has {ctx.get('story_count', 0)})"
        )

    if gate.requires_spec_md and not ctx.get("has_spec_md", False):
        return False, "Requires SPEC.md in project root"

    if gate.requires_github_remote and not ctx.get("has_github_remote", False):
        return False, "Requires a GitHub remote configured"

    if gate.requires_running_app and not ctx.get("app_running", False):
        return False, "Requires a running app (dazzle serve)"

    if "validate" in gate.requires and not ctx.get("validate_passes", False):
        return False, "Requires dazzle validate to pass"

    return True, None


def build_project_context(project_root: Path) -> dict[str, Any]:
    """Introspect a Dazzle project directory and return context for rendering."""
    ctx: dict[str, Any] = {
        "entity_count": 0,
        "surface_count": 0,
        "story_count": 0,
        "has_spec_md": False,
        "has_github_remote": False,
        "validate_passes": True,
        "app_running": False,
        "entity_names": [],
        "persona_names": [],
        "surface_names": [],
        "project_name": project_root.name,
    }

    # Check for SPEC.md
    ctx["has_spec_md"] = (project_root / "SPEC.md").exists() or (project_root / "spec.md").exists()

    # Check for GitHub remote
    git_config = project_root / ".git" / "config"
    if git_config.exists():
        try:
            content = git_config.read_text(encoding="utf-8")
            ctx["has_github_remote"] = "github.com" in content
        except Exception:
            pass

    # Try to parse AppSpec for counts
    try:
        from dazzle.core.fileset import discover_dsl_files
        from dazzle.core.linker import build_appspec
        from dazzle.core.manifest import load_manifest
        from dazzle.core.parser import parse_modules

        manifest_path = project_root / "dazzle.toml"
        if manifest_path.exists():
            manifest = load_manifest(manifest_path)
            dsl_files = discover_dsl_files(project_root, manifest)
            if dsl_files:
                modules = parse_modules(dsl_files)
                appspec = build_appspec(modules, manifest.project_root)

                ctx["entity_count"] = len(appspec.domain.entities)
                ctx["surface_count"] = len(appspec.surfaces)
                ctx["story_count"] = len(appspec.stories)
                ctx["entity_names"] = [e.name for e in appspec.domain.entities]
                ctx["surface_names"] = [s.name for s in appspec.surfaces]
                ctx["persona_names"] = [
                    getattr(p, "name", None) or getattr(p, "id", "unknown")
                    for p in appspec.personas
                ]
    except Exception:
        ctx["validate_passes"] = False

    return ctx


def render_skill(cmd: CommandDefinition, ctx: dict[str, Any]) -> str:
    """Render a command's Jinja2 template."""
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        keep_trailing_newline=True,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    template = env.get_template(cmd.template_file)
    return template.render(cmd=cmd, ctx=ctx)


def render_agents_md(
    commands: list[tuple[CommandDefinition, bool, str | None]], ctx: dict[str, Any]
) -> str:
    """Render AGENTS.md from all commands."""
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        keep_trailing_newline=True,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    template = env.get_template("agents_md.j2")
    return template.render(commands=commands, ctx=ctx)


def render_claude_md_section(
    commands: list[tuple[CommandDefinition, bool, str | None]], ctx: dict[str, Any]
) -> str:
    """Render the section to append to .claude/CLAUDE.md."""
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        keep_trailing_newline=True,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    template = env.get_template("claude_md_section.j2")
    return template.render(commands=commands, ctx=ctx)


def sync_to_project(project_root: Path) -> SyncManifest:
    """Sync agent commands to a Dazzle project directory.

    1. Build project context
    2. Load and evaluate all commands
    3. Write command files, AGENTS.md, CLAUDE.md section, and manifest
    """
    from dazzle import __version__ as dazzle_version

    ctx = build_project_context(project_root)
    all_commands = load_all_commands()

    # Evaluate maturity for each command
    evaluated: list[tuple[CommandDefinition, bool, str | None]] = []
    statuses: dict[str, CommandStatus] = {}
    for cmd in all_commands:
        available, reason = evaluate_maturity(cmd.maturity, ctx)
        evaluated.append((cmd, available, reason))
        statuses[cmd.name] = CommandStatus(version=cmd.version, available=available, reason=reason)

    # 3. Create .claude/commands/ directory
    commands_dir = project_root / ".claude" / "commands"
    commands_dir.mkdir(parents=True, exist_ok=True)

    # 4. Write command files for available commands
    for cmd, available, _reason in evaluated:
        if not available:
            continue
        content = render_skill(cmd, ctx)
        header = f"<!-- dazzle-agent-command:{cmd.name}:v{cmd.version} -->\n"
        cmd_path = commands_dir / f"{cmd.name}.md"
        cmd_path.write_text(header + content, encoding="utf-8")

    # 5. Create agent/ directory
    agent_dir = project_root / "agent"
    agent_dir.mkdir(parents=True, exist_ok=True)

    # 6. Seed empty backlog/log files for loop commands (don't overwrite)
    for cmd, _available, _reason in evaluated:
        if cmd.loop is None:
            continue
        for file_attr in ("backlog_file", "log_file"):
            rel_path = getattr(cmd.loop, file_attr, "")
            if not rel_path:
                continue
            full_path = project_root / rel_path
            full_path.parent.mkdir(parents=True, exist_ok=True)
            if not full_path.exists():
                full_path.write_text(
                    f"# {cmd.title} — {file_attr.replace('_', ' ').title()}\n",
                    encoding="utf-8",
                )

    # 7. Write AGENTS.md at project root
    agents_md = render_agents_md(evaluated, ctx)
    (project_root / "AGENTS.md").write_text(agents_md, encoding="utf-8")

    # 8. Append section to .claude/CLAUDE.md (idempotent)
    claude_md_path = project_root / ".claude" / "CLAUDE.md"
    marker = "<!-- dazzle-agent-commands -->"
    section = render_claude_md_section(evaluated, ctx)

    if claude_md_path.exists():
        existing = claude_md_path.read_text(encoding="utf-8")
        if marker not in existing:
            claude_md_path.write_text(
                existing.rstrip() + "\n\n" + marker + "\n" + section,
                encoding="utf-8",
            )
    else:
        claude_md_path.parent.mkdir(parents=True, exist_ok=True)
        claude_md_path.write_text(marker + "\n" + section, encoding="utf-8")

    # 9. Write .claude/commands/.manifest.json
    synced_at = datetime.now(UTC).isoformat()
    manifest_data = {
        "dazzle_version": dazzle_version,
        "commands_version": "1.0.0",
        "synced_at": synced_at,
        "commands": {
            name: {
                "version": cs.version,
                "available": cs.available,
                "reason": cs.reason,
            }
            for name, cs in statuses.items()
        },
    }
    manifest_path = commands_dir / ".manifest.json"
    manifest_path.write_text(json.dumps(manifest_data, indent=2) + "\n", encoding="utf-8")

    # 10. Return SyncManifest
    return SyncManifest(
        dazzle_version=dazzle_version,
        commands_version="1.0.0",
        synced_at=synced_at,
        commands=statuses,
    )
