"""
CLI commands for community contribution packaging.

Commands:
- contribution templates: List available contribution templates
- contribution create: Create a contribution package
- contribution validate: Validate a contribution package
- contribution examples: Show example contributions
"""

import json
from pathlib import Path
from typing import Any

import typer

contribution_app = typer.Typer(
    help="Community contribution packaging — create, validate, and share contributions.",
    no_args_is_help=True,
)


@contribution_app.command("templates")
def templates(
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """List available contribution templates."""
    from dazzle.cli._output import format_output
    from dazzle.mcp.server.handlers.contribution import contribution_templates_impl

    result = contribution_templates_impl()

    if json_output:
        typer.echo(format_output(result, as_json=True))
    else:
        typer.secho("\nContribution Templates", bold=True)
        typer.echo("=" * 40)
        for tmpl in result.get("templates", []):
            typer.echo(f"\n  {tmpl['type']}")
            typer.echo(f"    {tmpl['description']}")
            typer.echo(f"    Required: {', '.join(tmpl.get('required_content', []))}")
        typer.echo()
        if result.get("submission_url"):
            typer.echo(f"Submit at: {result['submission_url']}")
        typer.echo()


@contribution_app.command("create")
def create(
    contrib_type: str = typer.Argument(..., help="Contribution type (e.g. api_pack, bug_fix)"),
    title: str = typer.Option("Untitled Contribution", "--title", "-t", help="Contribution title"),
    description: str = typer.Option("", "--description", "-d", help="Contribution description"),
    content_file: Path | None = typer.Option(
        None, "--content", "-c", help="Path to JSON file with contribution content"
    ),
    output_dir: str | None = typer.Option(
        None, "--output-dir", "-o", help="Directory to write generated files"
    ),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Create a contribution package."""
    from dazzle.cli._output import format_output
    from dazzle.mcp.server.handlers.contribution import contribution_create_impl

    content: dict[str, Any] | None = None
    if content_file is not None:
        try:
            content = json.loads(content_file.read_text())
        except Exception as e:
            typer.echo(f"Error reading content file: {e}", err=True)
            raise typer.Exit(code=1)

    result = contribution_create_impl(
        contrib_type=contrib_type,
        title=title,
        description=description,
        content=content,
        output_dir=output_dir,
    )

    if "error" in result:
        typer.echo(f"Error: {result['error']}", err=True)
        raise typer.Exit(code=1)

    if json_output:
        typer.echo(format_output(result, as_json=True))
    else:
        status = result.get("status", "unknown")
        ctype = result.get("type", contrib_type)
        typer.secho(f"\nContribution: {status} ({ctype})", bold=True)

        if result.get("files"):
            typer.echo("\nGenerated files:")
            for fname in result["files"]:
                typer.echo(f"  {fname}")

        if result.get("written_to"):
            written = result["written_to"]
            if isinstance(written, list):
                typer.echo("\nWritten to:")
                for path in written:
                    typer.echo(f"  {path}")
            else:
                typer.echo(f"\nWritten to: {written}")

        if result.get("markdown"):
            typer.echo()
            typer.echo(result["markdown"])

        gh = result.get("github_issue", {})
        if gh.get("fallback"):
            typer.echo(f"\n{gh.get('message', '')}")
            typer.echo(f"Submit manually at: {gh.get('manual_url', '')}")
        elif gh.get("html_url"):
            typer.echo(f"\nGitHub issue created: {gh['html_url']}")

        typer.echo()


@contribution_app.command("validate")
def validate(
    contrib_type: str = typer.Argument(..., help="Contribution type (e.g. api_pack, bug_fix)"),
    content_file: Path | None = typer.Option(
        None, "--content", "-c", help="Path to JSON file with contribution content"
    ),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Validate a contribution package."""
    from dazzle.cli._output import format_output
    from dazzle.mcp.server.handlers.contribution import contribution_validate_impl

    content: dict[str, Any] | None = None
    if content_file is not None:
        try:
            content = json.loads(content_file.read_text())
        except Exception as e:
            typer.echo(f"Error reading content file: {e}", err=True)
            raise typer.Exit(code=1)

    result = contribution_validate_impl(
        contrib_type=contrib_type,
        content=content,
    )

    if "error" in result:
        typer.echo(f"Error: {result['error']}", err=True)
        raise typer.Exit(code=1)

    if json_output:
        typer.echo(format_output(result, as_json=True))
    else:
        if result.get("valid"):
            typer.secho("Valid", fg=typer.colors.GREEN, bold=True)
            typer.echo(result.get("message", ""))
        else:
            typer.secho("Invalid", fg=typer.colors.RED, bold=True)
            missing = result.get("missing_required", [])
            if missing:
                typer.echo(f"Missing required fields: {', '.join(missing)}")


@contribution_app.command("examples")
def examples(
    contrib_type: str = typer.Argument("api_pack", help="Contribution type to show example for"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Show example contributions."""
    from dazzle.cli._output import format_output
    from dazzle.mcp.server.handlers.contribution import contribution_examples_impl

    result = contribution_examples_impl(contrib_type=contrib_type)

    if "error" in result:
        typer.echo(f"Error: {result['error']}", err=True)
        raise typer.Exit(code=1)

    if json_output:
        typer.echo(format_output(result, as_json=True))
    else:
        example = result.get("example", {})
        typer.secho(f"\nExample: {example.get('title', contrib_type)}", bold=True)
        if example.get("description"):
            typer.echo(f"  {example['description']}")
        typer.echo()
        typer.echo(json.dumps(example.get("content", {}), indent=2))
        typer.echo()
        if result.get("usage"):
            typer.echo(result["usage"])
        typer.echo()
