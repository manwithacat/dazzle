"""CLI: ``dazzle docs claims`` — job claim registry check (#1638 PR3)."""

from __future__ import annotations

import json
from pathlib import Path

import typer

from dazzle.cli.utils import load_project_appspec, project_root_from_manifest
from dazzle.testing.walk.claims import (
    ClaimsLoadError,
    check_registry,
    discover_registry_path,
    load_registry,
)

claims_app = typer.Typer(
    name="claims",
    help="Job claim registry (docs maturity SSOT; not RBAC claim_ledger). #1638",
    no_args_is_help=True,
)


@claims_app.command("check")
def claims_check(
    manifest: str = typer.Option("dazzle.toml", "--manifest", "-m"),
    registry: str | None = typer.Option(
        None,
        "--registry",
        "-r",
        help="Path to job_claims.yaml (default: fixtures/ or docs/ candidates)",
    ),
    run: bool = typer.Option(
        False,
        "--run",
        help="Also execute walks for verified+ claims (needs live app)",
    ),
    base_url: str | None = typer.Option(
        None,
        "--base-url",
        "-u",
        help="App URL when --run (default: registry base_url_default or localhost)",
    ),
    no_appspec: bool = typer.Option(False, "--no-appspec"),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """Check job claims against docs paths, scene walks, and optional live run.

    Lifecycle: draft → documented → verified → sensible → filmed → evergreen.
    Statuses verified+ require a walk binding and a loadable walk file.
    With ``--run``, those walks are executed (SessionManager auth).

    Examples:
        dazzle docs claims check -m examples/simple_task/dazzle.toml
        dazzle docs claims check -m examples/simple_task/dazzle.toml --run -u http://127.0.0.1:8000
    """
    root = project_root_from_manifest(manifest)
    reg_path = discover_registry_path(
        root,
        Path(registry) if registry else None,
    )
    if reg_path is None:
        typer.echo(
            "No job claim registry found. Tried:\n"
            "  fixtures/job_claims.yaml\n"
            "  docs/job_claims.yaml\n"
            "  docs/internal/maturity.yaml\n"
            "Pass --registry PATH or add fixtures/job_claims.yaml",
            err=True,
        )
        raise typer.Exit(code=1)

    try:
        reg = load_registry(reg_path)
    except ClaimsLoadError as e:
        typer.echo(str(e), err=True)
        raise typer.Exit(code=1)

    appspec = None
    if not no_appspec:
        try:
            appspec = load_project_appspec(root)
        except Exception as e:
            typer.echo(f"Warning: AppSpec load failed ({e}); schema-only checks", err=True)

    result = check_registry(
        reg,
        project_root=root,
        appspec=appspec,
        run_walks=run,
        base_url=base_url,
    )

    if json_output:
        typer.echo(
            json.dumps(
                {
                    "registry": result.registry_path,
                    "guides": result.guides,
                    "ok": result.ok,
                    "errors": len(result.errors),
                    "warnings": len(result.warnings),
                    "walk_results": result.walk_results,
                    "issues": [
                        {
                            "guide_id": i.guide_id,
                            "level": i.level,
                            "code": i.code,
                            "message": i.message,
                        }
                        for i in result.issues
                    ],
                },
                indent=2,
            )
        )
    else:
        typer.echo(
            f"Registry: {result.registry_path}\n"
            f"Guides: {result.guides}  "
            f"errors={len(result.errors)}  warnings={len(result.warnings)}"
        )
        for i in result.issues:
            typer.echo(i.format(), err=(i.level == "error"))
        if result.ok and not result.warnings:
            typer.secho("claims check clean", fg=typer.colors.GREEN)
        elif result.ok:
            typer.secho("claims check clean (with warnings)", fg=typer.colors.YELLOW)

    raise typer.Exit(code=0 if result.ok else 1)
