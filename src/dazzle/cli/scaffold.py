"""#1605 D3 — CLI scaffold for domain-logic closed loop (ADR-0002 write path).

Commands:
- dazzle scaffold service <name>
- dazzle scaffold story <ST-id>
- dazzle scaffold process-step <process> <step>
"""

from __future__ import annotations

from pathlib import Path

import typer

from dazzle.cli.utils import load_project_appspec

scaffold_app = typer.Typer(
    help="Scaffold domain-logic files from DSL (agent closed loop #1605). Writes disk.",
    no_args_is_help=True,
)


def _display_path(path: Path, root: Path) -> str:
    """Pretty path for CLI echo — relative when under *root*, else absolute.

    Absolute ``--output`` (e.g. ``/tmp/…`` for dry exercise) is a valid write
    target; ``Path.relative_to`` must not crash after a successful write.
    """
    try:
        return str(path.resolve().relative_to(root.resolve()))
    except ValueError:
        return str(path.resolve())


@scaffold_app.command("service")
def scaffold_service(
    name: str = typer.Argument(..., help="Domain service name from DSL"),
    output_dir: str = typer.Option("services", "--output", "-o"),
    force: bool = typer.Option(False, "--force", "-f"),
    manifest: str = typer.Option("dazzle.toml", "--manifest", "-m"),
) -> None:
    """Write services/<name>.py skeleton matching the DSL service block."""
    root = Path(manifest).resolve().parent
    appspec = load_project_appspec(root)
    svc = None
    for s in appspec.domain_services or []:
        if s.name == name:
            svc = s
            break
    if svc is None:
        typer.echo(f"No domain service '{name}' in DSL.", err=True)
        raise typer.Exit(1)

    out = Path(output_dir)
    if not out.is_absolute():
        out = root / out
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"{name}.py"
    if path.exists() and not force:
        typer.echo(f"Exists: {path} (use --force)", err=True)
        raise typer.Exit(1)

    inputs = ", ".join(f.name for f in (svc.inputs or []))
    body = f'''"""Domain service: {svc.title or name}

Scaffolded by `dazzle scaffold service {name}` (#1605).
Replace NotImplementedError with real logic; keep the function name stable
so process steps and executed_by: service.{name} keep resolving.
"""

from __future__ import annotations

from typing import Any


def {name}({inputs or "*args, **kwargs"}) -> dict[str, Any]:
    """{svc.description or svc.title or name}"""
    raise NotImplementedError(
        "Scaffolded service — implement domain logic for {name}"
    )
'''
    path.write_text(body, encoding="utf-8")
    typer.echo(f"Wrote {_display_path(path, root)}")
    typer.echo(f"Bind stories with: executed_by: service.{name}")
    typer.echo("Prove with: dazzle prove story <ST-id>  # or agent(operation=prove)")


@scaffold_app.command("story")
def scaffold_story(
    story_id: str = typer.Argument(..., help="Story id e.g. ST-001"),
    output: str = typer.Option(
        "dsl/story_handlers.py",
        "--output",
        "-o",
        help="Handler module to append to",
    ),
    manifest: str = typer.Option("dazzle.toml", "--manifest", "-m"),
) -> None:
    """Append a handler stub + print binding checklist for a story."""
    root = Path(manifest).resolve().parent
    appspec = load_project_appspec(root)
    story = next((s for s in (appspec.stories or []) if s.story_id == story_id), None)
    if story is None:
        typer.echo(f"Story {story_id} not found.", err=True)
        raise typer.Exit(1)

    path = root / output
    path.parent.mkdir(parents=True, exist_ok=True)
    fn = story_id.lower().replace("-", "_")
    stub = f'''

def handle_{fn}(ctx: dict) -> dict:
    """Handler scaffold for {story_id}: {story.title}

    Bind with one of:
      executed_by: service.<name>
      executed_by: process.<name>.step.<step>
      executed_by: surface.<name>
      executed_by: host_route METHOD /path
      narrative_only: true
    """
    raise NotImplementedError({story_id!r} + " handler not implemented")
'''
    if path.exists() and f"handle_{fn}" in path.read_text(encoding="utf-8"):
        typer.echo(f"Handler handle_{fn} already in {_display_path(path, root)}")
    else:
        if not path.exists():
            path.write_text(
                '"""Story handlers — scaffolded by dazzle scaffold story."""\n',
                encoding="utf-8",
            )
        with path.open("a", encoding="utf-8") as f:
            f.write(stub)
        typer.echo(f"Appended handle_{fn} to {_display_path(path, root)}")

    typer.echo("--- checklist ---")
    typer.echo(f"1. Edit stories.dsl: bind {story_id} via executed_by or narrative_only")
    typer.echo("2. Implement handler / service / process step")
    typer.echo(f"3. dazzle prove story {story_id}")
    typer.echo("4. agent(operation=context) — confirm binding_gate pass")


@scaffold_app.command("process-step")
def scaffold_process_step(
    process: str = typer.Argument(..., help="Process name"),
    step: str = typer.Argument(..., help="Step name"),
    manifest: str = typer.Option("dazzle.toml", "--manifest", "-m"),
) -> None:
    """Print scaffold checklist for a process step (service wiring)."""
    root = Path(manifest).resolve().parent
    appspec = load_project_appspec(root)
    proc = next((p for p in (appspec.processes or []) if p.name == process), None)
    if proc is None:
        typer.echo(f"Process '{process}' not found.", err=True)
        raise typer.Exit(1)
    step_obj = next((s for s in (proc.steps or []) if getattr(s, "name", None) == step), None)
    if step_obj is None:
        typer.echo(f"Step '{step}' not on process '{process}'.", err=True)
        raise typer.Exit(1)

    svc = getattr(step_obj, "service", None) or getattr(step_obj, "service_ref", None)
    typer.echo(f"Process {process} step {step}")
    typer.echo(f"  kind: {getattr(step_obj, 'kind', None)}")
    typer.echo(f"  service: {svc}")
    typer.echo("--- checklist ---")
    if svc:
        typer.echo(f"1. dazzle scaffold service {svc}")
        typer.echo(f"2. Implement services/{svc}.py")
    else:
        typer.echo("1. Declare service: on the step in processes.dsl")
        typer.echo("2. dazzle scaffold service <name>")
    typer.echo(f"3. Bind stories: executed_by: process.{process}.step.{step}")
    typer.echo("4. dazzle prove story <ST-id>")
