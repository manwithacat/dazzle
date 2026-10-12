"""CLI sub-app for documentation generation, validation, and maintenance."""

from pathlib import Path

import typer

from dazzle.core.docs_gen import (
    check_docs_coverage,
    generate_reference_docs,
    inject_readme_feature_table,
    write_reference_docs,
)

docs_app = typer.Typer(
    help="Documentation generation, validation, and maintenance.",
    no_args_is_help=True,
)

# #1638 job claim registry (docs maturity SSOT — not RBAC claim_ledger)
from dazzle.cli.claims import claims_app  # noqa: E402

docs_app.add_typer(claims_app, name="claims")


@docs_app.command("generate")
def docs_generate(
    output_dir: Path | None = typer.Option(
        None,
        "--output-dir",
        "-o",
        help="Output directory (defaults to docs/reference/)",
    ),
    stdout: bool = typer.Option(
        False,
        "--stdout",
        help="Print all pages to stdout instead of writing files.",
    ),
    readme: bool = typer.Option(
        True,
        "--readme/--no-readme",
        help="Also update README.md feature table.",
    ),
) -> None:
    """Regenerate reference docs from knowledge base TOML files."""
    import dazzle.mcp.server.docs_inventory  # noqa: F401 — registers the mcp_tools auto-source

    if stdout:
        docs = generate_reference_docs()
        for slug, content in sorted(docs.items()):
            typer.echo(f"--- {slug}.md ---")
            typer.echo(content)
            typer.echo()
    else:
        paths = write_reference_docs(output_dir)
        for p in paths:
            typer.echo(f"  Written: {p}")
        if readme:
            updated = inject_readme_feature_table()
            if updated:
                typer.echo("  Updated: README.md (feature table)")
        typer.secho(f"\nDone — {len(paths)} reference doc(s) generated.", bold=True)


@docs_app.command("check")
def docs_check() -> None:
    """Validate TOML coverage. Exits non-zero if errors found."""

    issues = check_docs_coverage()
    if not issues:
        typer.secho(
            "All concepts have doc_page assignments. No issues found.",
            fg=typer.colors.GREEN,
        )
        raise typer.Exit(code=0)

    errors = []
    warnings = []
    for issue in issues:
        if issue.startswith("ERROR"):
            typer.secho(f"  {issue}", fg=typer.colors.RED)
            errors.append(issue)
        else:
            typer.secho(f"  {issue}", fg=typer.colors.YELLOW)
            warnings.append(issue)

    typer.echo(f"\n{len(errors)} error(s), {len(warnings)} warning(s)")
    if errors:
        raise typer.Exit(code=1)
