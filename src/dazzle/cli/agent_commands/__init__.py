"""Agent-first development commands for Dazzle projects."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import typer

agent_app = typer.Typer(
    name="agent",
    help="Agent-first development commands.",
    no_args_is_help=True,
)


@agent_app.command("sync")
def sync_command(
    project: Path = typer.Option(
        Path("."),
        "--project",
        "-p",
        help="Project root directory.",
    ),
) -> None:
    """Sync agent commands from the Dazzle framework to the project.

    Writes .claude/commands/*.md, AGENTS.md, and seeds agent/ backlog files.
    Idempotent — safe to run repeatedly.
    """
    project = project.resolve()
    if not (project / "dazzle.toml").exists():
        typer.echo(f"Error: {project} does not contain a dazzle.toml", err=True)
        raise typer.Exit(code=1)

    from dazzle.services.agent_commands.renderer import sync_to_project

    manifest = sync_to_project(project)

    available = sum(1 for cs in manifest.commands.values() if cs.available)
    total = len(manifest.commands)
    typer.echo(f"Synced {available}/{total} agent commands to {project}")
    for name, cs in sorted(manifest.commands.items()):
        status = "available" if cs.available else f"unavailable ({cs.reason})"
        typer.echo(f"  /{name}: {status}")


def _run(cmd: list[str], cwd: Path) -> tuple[int, str, str]:
    """Run a subprocess, returning (returncode, stdout, stderr)."""
    try:
        result = subprocess.run(  # noqa: S603 — args are constructed from fixed tokens
            cmd, cwd=str(cwd), capture_output=True, text=True, check=False
        )
        return result.returncode, result.stdout, result.stderr
    except FileNotFoundError as e:
        return 127, "", f"command not found: {e}"


def _seed_improve_backlog(project: Path) -> list[dict[str, Any]]:
    """Collect gaps for the /improve backlog from lint + validate.

    Each gap is ``{kind, description, status, attempts, notes}``. Runs
    synchronous subprocess calls against the project's ``dazzle`` CLI.
    """
    gaps: list[dict[str, Any]] = []

    rc, out, err = _run(["dazzle", "validate"], cwd=project)
    if rc != 0:
        for line in (out + err).splitlines():
            line = line.strip()
            if not line or line.startswith("Error:") is False:
                continue
            gaps.append(
                {
                    "kind": "validation",
                    "description": line.removeprefix("Error:").strip(),
                    "status": "PENDING",
                    "attempts": 0,
                    "notes": "from `dazzle validate`",
                }
            )

    rc, out, err = _run(["dazzle", "lint"], cwd=project)
    for line in (out + err).splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        # Heuristic: treat any line containing 'warning' or '[lint]' as a finding.
        low = stripped.lower()
        if "warning" in low or "[lint]" in low or stripped.startswith("- "):
            gaps.append(
                {
                    "kind": "lint",
                    "description": stripped.lstrip("- ").strip(),
                    "status": "PENDING",
                    "attempts": 0,
                    "notes": "from `dazzle lint`",
                }
            )

    return gaps


def _seed_polish_backlog(project: Path) -> list[dict[str, Any]]:
    """Collect gaps for the /polish backlog from ux verify + composition audit."""
    gaps: list[dict[str, Any]] = []

    rc, out, err = _run(["dazzle", "ux", "verify", "--contracts"], cwd=project)
    for line in (out + err).splitlines():
        stripped = line.strip()
        if "fail" in stripped.lower() or stripped.startswith("- "):
            gaps.append(
                {
                    "kind": "ux_contract",
                    "description": stripped.lstrip("- ").strip(),
                    "status": "PENDING",
                    "attempts": 0,
                    "notes": "from `dazzle ux verify --contracts`",
                }
            )

    return gaps


_SEEDERS: dict[str, Any] = {
    "improve": _seed_improve_backlog,
    "polish": _seed_polish_backlog,
}


def _write_backlog_markdown(path: Path, title: str, gaps: list[dict[str, Any]]) -> None:
    """Render a gap list as a markdown table, preserving existing content."""
    lines = [f"# {title} — Backlog", ""]
    lines.append("| # | Gap Type | Description | Status | Attempts | Notes |")
    lines.append("|---|----------|-------------|--------|----------|-------|")
    for idx, gap in enumerate(gaps, start=1):
        cells = [
            str(idx),
            gap["kind"],
            gap["description"].replace("|", r"\|"),
            gap["status"],
            str(gap["attempts"]),
            gap["notes"],
        ]
        lines.append("| " + " | ".join(cells) + " |")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


@agent_app.command("seed")
def seed_command(
    command_name: str = typer.Argument(..., help="Agent command to seed (improve | polish)"),
    project: Path = typer.Option(Path("."), "--project", "-p", help="Project root directory."),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Print the gaps without writing the backlog file"
    ),
) -> None:
    """Seed an agent command's backlog from lint / validate / audit output.

    Replaces the previous manual flow where the outer assistant had to
    parse JSON out of `dazzle validate` and friends (#788). Writes the
    command's configured ``backlog_file`` in place.
    """
    seeder = _SEEDERS.get(command_name)
    if seeder is None:
        typer.echo(
            f"Error: no seeder for {command_name!r} (known: {', '.join(sorted(_SEEDERS))})",
            err=True,
        )
        raise typer.Exit(code=2)

    project = project.resolve()
    if not (project / "dazzle.toml").exists():
        typer.echo(f"Error: {project} does not contain a dazzle.toml", err=True)
        raise typer.Exit(code=1)

    from dazzle.services.agent_commands.loader import load_all_commands

    cmd = next((c for c in load_all_commands() if c.name == command_name), None)
    if cmd is None or cmd.loop is None:
        typer.echo(f"Error: {command_name!r} is not a loop-pattern command", err=True)
        raise typer.Exit(code=2)

    gaps = seeder(project)

    if dry_run:
        typer.echo(json.dumps({"command": command_name, "gaps": gaps}, indent=2))
        return

    backlog_path = project / cmd.loop.backlog_file
    _write_backlog_markdown(backlog_path, cmd.title, gaps)
    typer.echo(f"Seeded {len(gaps)} gap(s) to {backlog_path}")


@agent_app.command("signals")
def signals_command(
    source: str = typer.Option(
        ...,
        "--source",
        help="Loop identifier (e.g. improve, polish). Used as emit source + consume marker.",
    ),
    emit: str = typer.Option(
        "",
        "--emit",
        help="Signal kind to emit. Mutually exclusive with --consume.",
    ),
    payload: str = typer.Option(
        "",
        "--payload",
        help="JSON payload for --emit. Defaults to `{}`.",
    ),
    consume: bool = typer.Option(
        False,
        "--consume",
        help="List signals since the source's last run, then mark the run.",
    ),
    kind: str = typer.Option(
        "",
        "--kind",
        help="With --consume: filter by signal kind.",
    ),
) -> None:
    """Emit or consume cross-loop signals (#788).

    Signals live in ``.dazzle/signals/`` (a flat-file bus) and are how
    loops like /improve and /polish coordinate without direct calls.
    """
    from dazzle.cli.runtime_impl import ux_cycle_signals as bus

    if emit and consume:
        typer.echo("Error: --emit and --consume are mutually exclusive", err=True)
        raise typer.Exit(code=2)

    if emit:
        try:
            payload_dict = json.loads(payload) if payload else {}
        except json.JSONDecodeError as e:
            typer.echo(f"Error: --payload is not valid JSON: {e}", err=True)
            raise typer.Exit(code=2) from e
        if not isinstance(payload_dict, dict):
            typer.echo("Error: --payload must decode to a JSON object", err=True)
            raise typer.Exit(code=2)
        bus.emit(source, emit, payload_dict)
        typer.echo(f"Emitted {source}:{emit}")
        return

    if consume:
        signals = bus.since_last_run(source, kind=kind or None)
        if not signals:
            typer.echo(f"No new signals for {source}")
        else:
            typer.echo(f"{len(signals)} new signal(s) for {source}:")
            for sig in signals:
                typer.echo(
                    f"  {sig.timestamp:.0f}  {sig.source}:{sig.kind}  {json.dumps(sig.payload)}"
                )
        bus.mark_run(source)
        return

    typer.echo("Error: must specify either --emit or --consume", err=True)
    raise typer.Exit(code=2)
