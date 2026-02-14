"""CLI sub-app for documentation maintenance powered by LLM synthesis."""

from __future__ import annotations

import json
from pathlib import Path

import typer

docs_app = typer.Typer(
    help="Documentation maintenance powered by LLM synthesis.",
    no_args_is_help=True,
)

ALL_TARGETS = ["changelog", "readme", "mkdocs"]

DEFAULT_REPO = "manwithacat/dazzle"


def _resolve_root() -> Path:
    """Find the project root (directory containing CHANGELOG.md or dazzle.toml)."""
    cwd = Path.cwd()
    for marker in ("CHANGELOG.md", "dazzle.toml", "pyproject.toml"):
        if (cwd / marker).exists():
            return cwd
    return cwd


@docs_app.command("update")
def docs_update(
    since: str | None = typer.Option(
        None,
        "--since",
        "-s",
        help='Cutoff: date (2026-02-01), tag (v0.25.0), relative ("14 days"), or omit for latest tag.',
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Show diffs without writing files.",
    ),
    yes: bool = typer.Option(
        False,
        "--yes",
        "-y",
        help="Skip confirmation prompt.",
    ),
    format_: str = typer.Option(
        "table",
        "--format",
        "-f",
        help="Output format: table or json.",
    ),
    target: list[str] | None = typer.Option(
        None,
        "--target",
        "-t",
        help="Doc targets to update (changelog, readme, mkdocs). Repeatable. Default: all.",
    ),
    repo: str = typer.Option(
        DEFAULT_REPO,
        "--repo",
        help="GitHub owner/repo.",
    ),
) -> None:
    """Scan closed GitHub issues and generate documentation updates via LLM."""
    from dazzle.docs_update.models import UpdatePlan
    from dazzle.docs_update.scanner import resolve_since, scan_closed_issues
    from dazzle.docs_update.synthesizer import classify_issues, generate_patches
    from dazzle.docs_update.updater import generate_diff

    project_root = _resolve_root()
    targets = [t.lower() for t in target] if target else ALL_TARGETS

    # Validate targets
    for t in targets:
        if t not in ALL_TARGETS:
            typer.secho(
                f"Unknown target: {t}. Choose from: {', '.join(ALL_TARGETS)}",
                fg=typer.colors.RED,
                err=True,
            )
            raise typer.Exit(code=1)

    # --- Step 1: Resolve since date ---
    typer.echo("Resolving cutoff date...")
    try:
        since_date = resolve_since(since, repo)
    except RuntimeError as e:
        typer.secho(f"Error: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)
    typer.echo(f"  Scanning issues closed after: {since_date}")

    # --- Step 2: Scan issues ---
    typer.echo("Scanning closed GitHub issues...")
    try:
        issues = scan_closed_issues(since_date, repo)
    except RuntimeError as e:
        typer.secho(f"Error: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

    if not issues:
        typer.secho("No closed issues found in the given range.", fg=typer.colors.YELLOW)
        raise typer.Exit(code=0)

    typer.echo(f"  Found {len(issues)} closed issues")

    # --- Step 3: Initialize LLM ---
    typer.echo("Initializing LLM client...")
    try:
        from dazzle.llm.api_client import LLMAPIClient

        llm = LLMAPIClient()
    except (ValueError, ImportError) as e:
        typer.secho(f"LLM initialization failed: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)

    # --- Step 4: Classify issues ---
    typer.echo("Classifying issues via LLM...")
    issues = classify_issues(issues, llm.complete)

    relevant = [i for i in issues if i.category and i.category.value != "internal"]
    skipped = [i.number for i in issues if not i.category or i.category.value == "internal"]

    typer.echo(f"  {len(relevant)} relevant, {len(skipped)} internal/skipped")

    if not relevant:
        typer.secho("No relevant issues to document.", fg=typer.colors.YELLOW)
        raise typer.Exit(code=0)

    # --- Step 5: Generate patches ---
    typer.echo(f"Generating patches for: {', '.join(targets)}...")
    patches = generate_patches(issues, targets, project_root, llm.complete)

    if not patches:
        typer.secho("No documentation changes needed.", fg=typer.colors.YELLOW)
        raise typer.Exit(code=0)

    # --- Step 6: Build plan ---
    plan = UpdatePlan(
        issues_scanned=len(issues),
        issues_relevant=len(relevant),
        patches=patches,
        skipped_issues=skipped,
    )

    # --- Step 7: Display results ---
    if format_ == "json":
        typer.echo(json.dumps(plan.model_dump(), indent=2))
        if dry_run:
            raise typer.Exit(code=0)
    else:
        typer.secho("\nDocumentation Update Plan", bold=True)
        typer.echo(f"  Issues scanned:  {plan.issues_scanned}")
        typer.echo(f"  Issues relevant: {plan.issues_relevant}")
        typer.echo(f"  Patches:         {len(plan.patches)}")
        typer.echo()

        for patch in plan.patches:
            typer.secho(f"  [{patch.target}] {patch.section}", fg=typer.colors.CYAN, bold=True)
            typer.echo(f"    File: {patch.file_path}")
            typer.echo(f"    Reason: {patch.reason}")
            typer.echo(f"    Issues: {', '.join(f'#{n}' for n in patch.issues)}")

            diff = generate_diff(patch.original, patch.proposed, Path(patch.file_path).name)
            if diff:
                typer.echo()
                for line in diff.splitlines():
                    if line.startswith("+") and not line.startswith("+++"):
                        typer.secho(f"    {line}", fg=typer.colors.GREEN)
                    elif line.startswith("-") and not line.startswith("---"):
                        typer.secho(f"    {line}", fg=typer.colors.RED)
                    else:
                        typer.echo(f"    {line}")
            typer.echo()

    if dry_run:
        typer.secho("Dry run — no files written.", fg=typer.colors.YELLOW)
        raise typer.Exit(code=0)

    # --- Step 8: Confirm and apply ---
    if not yes:
        confirm = typer.confirm("Apply these changes?")
        if not confirm:
            typer.echo("Aborted.")
            raise typer.Exit(code=0)

    applied = 0
    for patch in plan.patches:
        path = Path(patch.file_path)
        path.write_text(patch.proposed)
        typer.secho(f"  Updated: {path}", fg=typer.colors.GREEN)
        applied += 1

    typer.secho(f"\nDone — {applied} file(s) updated.", bold=True)
