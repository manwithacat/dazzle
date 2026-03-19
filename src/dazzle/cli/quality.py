"""Quality pipeline scaffolding for agent-driven quality workflows."""

from pathlib import Path

import typer
from rich.console import Console

quality_app = typer.Typer(help="Quality pipeline scaffolding.", no_args_is_help=True)
console = Console()


@quality_app.command("init")
def init_command() -> None:
    """Scaffold quality pipeline commands into .claude/commands/."""
    # 1. Parse DSL to get personas, workspaces, entities
    from dazzle.cli.utils import load_project_appspec

    project_root = Path.cwd().resolve()
    appspec = load_project_appspec(project_root)

    # 2. Extract context from appspec
    personas = [p.id for p in (appspec.personas or [])]
    workspaces = [w.name for w in (appspec.workspaces or [])]
    entities = [e.name for e in appspec.domain.entities]

    # Build persona -> workspace table
    workspace_table_lines = ["| Persona | Workspace |", "|---------|-----------|"]
    for ws in appspec.workspaces or []:
        ws_personas = getattr(ws, "personas", []) or []
        for p in ws_personas:
            p_name = p if isinstance(p, str) else getattr(p, "name", str(p))
            workspace_table_lines.append(f"| {p_name} | {ws.name} |")

    # Site URL from sitespec or default
    site_url = "http://localhost:3000"

    placeholders = {
        "persona_list": (
            "\n".join(f"- {p}" for p in personas) if personas else "- (no personas defined)"
        ),
        "workspace_list": (
            "\n".join(f"- {w}" for w in workspaces) if workspaces else "- (no workspaces defined)"
        ),
        "entity_list": (
            "\n".join(f"- {e}" for e in entities) if entities else "- (no entities defined)"
        ),
        "entity_count": str(len(entities)),
        "persona_workspace_table": "\n".join(workspace_table_lines),
        "site_url": site_url,
    }

    # 3. Read templates and interpolate
    templates_dir = Path(__file__).parent / "quality_templates"
    output_dir = project_root / ".claude" / "commands"
    output_dir.mkdir(parents=True, exist_ok=True)

    written = []
    for template_file in sorted(templates_dir.glob("*.md")):
        content = template_file.read_text()
        for key, value in placeholders.items():
            content = content.replace("{" + key + "}", value)

        output_path = output_dir / template_file.name
        output_path.write_text(content)
        written.append(template_file.name)

    # 4. Report
    console.print("\n[green]Quality pipeline scaffolded to .claude/commands/[/green]")
    for name in sorted(written):
        console.print(f"  [dim]\u2022[/dim] {name}")
    console.print("\n[dim]Run /nightly, /actions, /ux-actions, or /quality in Claude Code.[/dim]")
