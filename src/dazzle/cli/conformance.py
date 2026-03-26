"""CLI commands for DSL conformance testing.

Commands:
  dazzle conformance generate  — Generate conformance TOML files from DSL
  dazzle conformance summary   — Print conformance coverage summary
  dazzle conformance run       — Run conformance tests via pytest
  dazzle conformance execute   — Run HTTP conformance session against PostgreSQL
"""

import subprocess
from pathlib import Path

import typer

conformance_app = typer.Typer(help="DSL conformance testing.", no_args_is_help=True)


@conformance_app.command()
def generate(
    project_root: str = typer.Option(".", "--project-root", "-p", help="Project root directory."),
    output_dir: str = typer.Option(
        "",
        "--output-dir",
        "-o",
        help="Output directory for TOML files (default: <project-root>/.dazzle/conformance).",
    ),
) -> None:
    """Generate conformance test scenario TOML files from the DSL."""
    from dazzle.conformance.generator import generate_toml_files
    from dazzle.conformance.plugin import collect_conformance_cases

    root = Path(project_root).resolve()
    out = Path(output_dir).resolve() if output_dir else root / ".dazzle" / "conformance"

    typer.echo(f"Loading DSL from {root} ...")
    try:
        cases, _fixtures = collect_conformance_cases(root)
    except FileNotFoundError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    typer.echo(f"Derived {len(cases)} conformance case(s).")
    written = generate_toml_files(cases, out)
    typer.echo(f"Wrote {len(written)} TOML file(s) to {out}:")
    for path in written:
        typer.echo(f"  {path.name}")


@conformance_app.command()
def summary(
    project_root: str = typer.Option(".", "--project-root", "-p", help="Project root directory."),
) -> None:
    """Print conformance coverage summary."""
    from dazzle.conformance.plugin import build_conformance_report, collect_conformance_cases

    root = Path(project_root).resolve()

    typer.echo(f"Loading DSL from {root} ...")
    try:
        cases, _fixtures = collect_conformance_cases(root)
    except FileNotFoundError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    report = build_conformance_report(cases)

    typer.echo("")
    typer.echo(f"Total cases : {report['total_cases']}")
    typer.echo("")

    typer.echo("Scope types:")
    for scope_type, count in sorted(report["scope_types"].items()):
        typer.echo(f"  {scope_type:<20} {count}")

    typer.echo("")
    typer.echo("Entities:")
    for entity, count in sorted(report["entities"].items()):
        typer.echo(f"  {entity:<30} {count} case(s)")


@conformance_app.command()
def run(
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Pass -v to pytest."),
) -> None:
    """Run conformance tests via pytest."""
    cmd = ["pytest", "-m", "conformance"]
    if verbose:
        cmd.append("-v")
    result = subprocess.run(cmd)
    raise typer.Exit(code=result.returncode)


@conformance_app.command()
def execute(
    project_root: str = typer.Option(".", "--project-root", "-p", help="Project root directory."),
    database_url: str = typer.Option(
        "",
        "--database-url",
        "-d",
        help="PostgreSQL URL (default: CONFORMANCE_DATABASE_URL env var).",
    ),
) -> None:
    """Run HTTP conformance session against a live PostgreSQL database.

    Boots the app in-process, seeds deterministic fixture data, runs all
    derived conformance cases as HTTP assertions, and reports pass/fail.
    """
    import asyncio

    from dazzle.conformance.plugin import run_conformance_session

    root = Path(project_root).resolve()
    db_url = database_url or None

    typer.echo(f"Running conformance execution against {root} ...")

    try:
        report = asyncio.run(run_conformance_session(root, database_url=db_url))
    except FileNotFoundError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    except RuntimeError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    typer.echo("")
    typer.echo(f"Total:  {report['total']}")
    typer.echo(f"Passed: {report['passed']}")
    typer.echo(f"Failed: {report['failed']}")
    typer.echo(f"Rate:   {report['pass_rate']:.0%}")

    if report["failures"]:
        typer.echo("")
        typer.echo("Failures:")
        for f in report["failures"]:
            typer.echo(f"  {f['test_id']}: {f['error']}")

    if report["failed"] > 0:
        raise typer.Exit(code=1)
