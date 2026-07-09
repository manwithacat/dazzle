"""
Deployment commands for DAZZLE CLI.

Target-agnostic infrastructure planning (`plan`) plus Heroku/uv-buildpack file
generation (`heroku`). Dazzle apps deploy as a single core process; provisioning
of backing services is the operator's concern.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Annotated

import typer
from rich.console import Console
from rich.table import Table

from dazzle.core.fileset import discover_dsl_files
from dazzle.core.linker import build_appspec
from dazzle.core.manifest import load_manifest
from dazzle.core.parser import parse_modules
from dazzle.core.renderer_registry import known_renderer_names

if TYPE_CHECKING:
    from dazzle.core.ir import AppSpec

deploy_app = typer.Typer(
    help="Plan infrastructure + generate buildpack (Heroku) deploy files",
    no_args_is_help=True,
)

console = Console()


def _load_spec(project_dir: Path) -> AppSpec:
    """Load and parse the AppSpec from a project directory."""

    # Load manifest and discover DSL files
    manifest_path = (project_dir / "dazzle.toml").resolve()
    root = manifest_path.parent
    manifest = load_manifest(manifest_path)
    dsl_files = discover_dsl_files(root, manifest)

    if not dsl_files:
        console.print("[red]No DSL files found in project[/red]")
        raise typer.Exit(1)

    modules = parse_modules(dsl_files)
    spec = build_appspec(
        modules,
        manifest.project_root,
        known_renderers=known_renderer_names(manifest),
    )

    return spec


@deploy_app.command(name="plan")
def deploy_plan(
    project_dir: Annotated[
        Path,
        typer.Option(
            "--project",
            "-p",
            help="Project directory containing DSL files",
            exists=True,
            file_okay=False,
            dir_okay=True,
        ),
    ] = Path("."),
    fmt: Annotated[
        str,
        typer.Option("--format", "-f", help="Output format: text (default) or json"),
    ] = "text",
) -> None:
    """
    Show the infrastructure an app needs — target-agnostic.

    Infers, from the DSL alone, what backing services the app requires
    (database, cache, queue, workers, storage, ledger cluster, …) and which
    environment variables its host must provide. Provision these however you
    like (managed services, your own containers) and deploy the app as a core
    process (see `dazzle deploy heroku`).
    """
    from dazzle.deploy import build_infra_plan

    with console.status("Parsing DSL files..."):
        spec = _load_spec(project_dir)

    plan = build_infra_plan(spec)

    if fmt == "json":
        import json as _json

        console.print_json(_json.dumps(plan.to_dict()))
        return
    if fmt != "text":
        console.print(f"[red]Unknown --format {fmt!r}. Use 'text' or 'json'.[/red]")
        raise typer.Exit(2)

    console.print(f"\n[bold]Deployment plan[/bold] — [cyan]{plan.app_name}[/cyan]\n")

    if plan.is_stateless:
        console.print("[green]Stateless — no backing infrastructure required.[/green]")
    else:
        table = Table(title="Infrastructure required")
        table.add_column("Component", style="cyan")
        table.add_column("Needs", style="white")
        table.add_column("Required", style="green")
        for c in plan.components:
            detail = c.summary + (f" — {c.detail}" if c.detail else "")
            table.add_row(c.kind, detail, "yes" if c.required else "optional")
        console.print(table)
        console.print()

        console.print("[bold]Environment variables the host must provide:[/bold]")
        for var in plan.required_env_vars:
            console.print(f"  • {var}")
        console.print()

    for note in plan.notes:
        console.print(f"[dim]{note}[/dim]")


# ---------------------------------------------------------------------------
# Production deployment artifact generators (v0.47)
# ---------------------------------------------------------------------------


def generate_deploy_requirements(version: str) -> str:
    """Generate requirements.txt pinned to the current dazzle-dsl version.

    Uses the ``[serve]`` extra: a deployed app runs ``dazzle serve --production``,
    which needs uvicorn — that lives in ``[serve]``, not the core deps, so a bare
    ``dazzle-dsl`` pin can't actually start the server.
    """
    return f"""dazzle-dsl[serve]=={version}
psycopg[binary]>=3.2
redis>=5.0
httpx>=0.24
"""


def generate_heroku_files(version: str) -> tuple[str, str, str]:
    """Generate the legacy pip-based Heroku deployment files.

    Returns:
        (procfile, runtime_txt, requirements_txt)
    """
    procfile = "web: dazzle serve --production\n"
    runtime = "python-3.14\n"
    requirements = generate_deploy_requirements(version)
    return procfile, runtime, requirements


def generate_heroku_pyproject(app_name: str, version: str) -> str:
    """Generate a minimal ``pyproject.toml`` for Heroku's uv buildpack.

    A deployed Dazzle app is DSL files + ``dazzle.toml``; its only Python
    dependency is ``dazzle-dsl[serve]`` (which provides ``dazzle serve``).
    ``[tool.uv] package = false`` marks this a non-packaged (virtual) project so
    uv installs the dependencies without trying to build the app itself.

    Heroku's uv path activates when ``pyproject.toml`` + ``uv.lock`` +
    ``.python-version`` are present and ``requirements.txt``/``runtime.txt`` are
    absent — see ``dazzle deploy heroku`` and ``docs/guides/heroku.md``.
    """
    return f'''[project]
name = "{app_name}"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    "dazzle-dsl[serve]=={version}",
    "psycopg[binary]>=3.2",
    "redis>=5.0",
    "httpx>=0.24",
]

[tool.uv]
# DSL app, not a Python package — install deps only, don't build a wheel.
package = false
'''


def generate_python_version_file() -> str:
    """Generate the ``.python-version`` file Heroku's uv path reads (and uv locally)."""
    return "3.14\n"


def _heroku_app_name(output_path: Path) -> str:
    """Derive a PEP 508-valid project name from the output directory name."""
    import re

    raw = output_path.resolve().name or "dazzle-app"
    name = re.sub(r"[^a-zA-Z0-9._-]+", "-", raw).strip("-._").lower()
    return name or "dazzle-app"


def _run_uv_lock(output_path: Path) -> bool:
    """Run ``uv lock`` in *output_path* to produce ``uv.lock``.

    Best-effort: returns ``False`` (without raising) when uv is unavailable or the
    resolution fails, so the caller can fall back to printing manual instructions.
    """
    import shutil
    import subprocess

    if shutil.which("uv") is None:
        return False
    try:
        result = subprocess.run(
            ["uv", "lock"],
            cwd=str(output_path),
            capture_output=True,
            text=True,
            timeout=300,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return result.returncode == 0


def _get_dazzle_version() -> str:
    """Get the installed dazzle-dsl version."""
    try:
        from importlib.metadata import version

        return version("dazzle-dsl")
    except Exception:
        return "0.0.0"


@deploy_app.command(name="heroku")
def deploy_heroku_cmd(
    output_dir: Annotated[
        Path,
        typer.Option("--output", "-o", help="Directory to write Heroku files"),
    ] = Path("."),
    pip: Annotated[
        bool,
        typer.Option(
            "--pip",
            help="Emit the legacy pip path (requirements.txt + runtime.txt) instead of uv.",
        ),
    ] = False,
) -> None:
    """Generate Heroku deployment files.

    Defaults to Heroku's uv buildpack (``pyproject.toml`` + ``uv.lock`` +
    ``.python-version`` + ``Procfile``), which gives reproducible, hash-pinned
    builds. Pass ``--pip`` for the legacy ``requirements.txt`` + ``runtime.txt``
    path. See ``docs/guides/heroku.md``.

    Example:
        dazzle deploy heroku
        git add Procfile pyproject.toml uv.lock .python-version
        git commit -m "deploy config" && git push heroku main
    """
    version = _get_dazzle_version()
    output_path = Path(output_dir).resolve()

    if pip:
        procfile, runtime, requirements = generate_heroku_files(version)
        (output_path / "Procfile").write_text(procfile, encoding="utf-8")
        (output_path / "runtime.txt").write_text(runtime, encoding="utf-8")
        (output_path / "requirements.txt").write_text(requirements, encoding="utf-8")
        console.print(f"Generated {output_path / 'Procfile'}")
        console.print(f"Generated {output_path / 'runtime.txt'}")
        console.print(f"Generated {output_path / 'requirements.txt'}")
    else:
        app_name = _heroku_app_name(output_path)
        (output_path / "Procfile").write_text("web: dazzle serve --production\n", encoding="utf-8")
        (output_path / "pyproject.toml").write_text(
            generate_heroku_pyproject(app_name, version), encoding="utf-8"
        )
        (output_path / ".python-version").write_text(
            generate_python_version_file(), encoding="utf-8"
        )
        console.print(f"Generated {output_path / 'Procfile'}")
        console.print(f"Generated {output_path / 'pyproject.toml'}")
        console.print(f"Generated {output_path / '.python-version'}")

        # Heroku's uv path needs uv.lock present; generate it now if uv is around.
        if _run_uv_lock(output_path):
            console.print(f"Generated {output_path / 'uv.lock'}")
        else:
            console.print(
                "[yellow]Could not run `uv lock` (uv not found or offline). "
                "Run `uv lock` in this directory before deploying.[/yellow]"
            )

        # Heroku's uv path is rejected if a competing package-manager file exists.
        stale = [
            f
            for f in ("requirements.txt", "runtime.txt", "Pipfile", "poetry.lock")
            if (output_path / f).exists()
        ]
        if stale:
            console.print(
                f"[yellow]Heroku's uv buildpack requires these be removed first: "
                f"{', '.join(stale)}[/yellow]"
            )

    console.print()
    console.print("[bold]Next steps:[/bold]")
    console.print("  heroku create myapp")
    console.print("  heroku addons:create heroku-postgresql")
    console.print("  heroku addons:create heroku-redis")
    if not pip:
        console.print("  git add Procfile pyproject.toml uv.lock .python-version")
    console.print("  git push heroku main")
