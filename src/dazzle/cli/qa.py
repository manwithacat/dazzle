"""CLI sub-app for the Dazzle visual QA toolkit."""

from __future__ import annotations

import asyncio
from pathlib import Path

import typer

qa_app = typer.Typer(
    help="QA toolkit — visual quality evaluation and screenshot capture.",
    no_args_is_help=True,
)


def _resolve_project_dir(app: str | None) -> Path:
    """Resolve the project directory from --app flag or cwd.

    If *app* is given, looks for ``examples/{app}/`` starting from cwd, then
    falls back to the dazzle package root.  Otherwise returns cwd.
    """
    if app is None:
        return Path.cwd()

    # Try cwd/examples/{app}
    candidate = Path.cwd() / "examples" / app
    if candidate.is_dir():
        return candidate

    # Try relative to the dazzle package root
    try:
        import dazzle

        pkg_root = Path(dazzle.__file__).resolve().parents[2]
        candidate = pkg_root / "examples" / app
        if candidate.is_dir():
            return candidate
    except Exception:
        pass

    typer.echo(f"App directory not found for '{app}'", err=True)
    raise typer.Exit(code=1)


@qa_app.command("visual")
def qa_visual(
    url: str | None = typer.Option(None, "--url", "-u", help="URL of a running app"),
    app: str | None = typer.Option(None, "--app", "-a", help="Example app name (e.g. simple_task)"),
    as_json: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Run visual QA: capture screenshots and evaluate with Claude Vision."""
    from dazzle.cli.utils import load_project_appspec
    from dazzle.qa.capture import build_capture_plan, capture_screenshots
    from dazzle.qa.evaluate import ClaudeEvaluator
    from dazzle.qa.models import QAReport
    from dazzle.qa.report import deduplicate, format_json, format_table
    from dazzle.qa.server import AppConnection, wait_for_ready

    project_dir = _resolve_project_dir(app)

    # Load AppSpec
    try:
        appspec = load_project_appspec(project_dir)
    except Exception as e:
        typer.echo(f"Failed to load AppSpec: {e}", err=True)
        raise typer.Exit(code=1)

    app_name: str = str(getattr(appspec, "name", None) or project_dir.name)

    # Build capture plan
    targets = build_capture_plan(appspec)
    if not targets:
        typer.echo("No capture targets found (no workspaces or personas defined).", err=True)
        raise typer.Exit(code=1)

    if url is None:
        typer.echo(
            "--url is required. Start the app in another terminal first:\n"
            f"  dazzle e2e env start {app or '<example>'}\n"
            "Then pass its URL:\n"
            "  dazzle qa visual --url http://localhost:8981 ...",
            err=True,
        )
        raise typer.Exit(code=2)

    api_url_resolved = url.replace(":3000", ":8000") if ":3000" in url else url
    connection = AppConnection(
        site_url=url,
        api_url=api_url_resolved,
        process=None,
    )

    all_findings = []
    try:
        typer.echo("Waiting for server to be ready…")
        ready = asyncio.run(wait_for_ready(connection.api_url))
        if not ready:
            typer.echo("Server did not become ready in time.", err=True)
            raise typer.Exit(code=1)

        # Capture screenshots
        typer.echo(f"Capturing {len(targets)} screen(s)…")
        screens = asyncio.run(
            capture_screenshots(
                targets,
                site_url=connection.site_url,
                api_url=connection.api_url,
                project_dir=project_dir,
            )
        )

        if not screens:
            typer.echo("No screenshots captured.", err=True)
            raise typer.Exit(code=1)

        # Evaluate each screen
        evaluator = ClaudeEvaluator()
        typer.echo(f"Evaluating {len(screens)} screen(s) with Claude Vision…")
        for screen in screens:
            findings = evaluator.evaluate(screen)
            all_findings.extend(findings)

    finally:
        connection.stop()

    # Deduplicate findings and build report
    deduped = deduplicate(all_findings)
    report = QAReport(app=app_name, findings=deduped)

    # Format output
    if as_json:
        typer.echo(format_json(report))
    else:
        typer.echo(format_table(report))

    # Exit code 1 if any high findings
    if report.high_count > 0:
        raise typer.Exit(code=1)


@qa_app.command("capture")
def qa_capture(
    url: str | None = typer.Option(None, "--url", "-u", help="URL of a running app"),
    app: str | None = typer.Option(None, "--app", "-a", help="Example app name (e.g. simple_task)"),
    persona: str | None = typer.Option(
        None, "--persona", "-p", help="Restrict capture to a single persona"
    ),
) -> None:
    """Capture screenshots only — no LLM evaluation needed."""
    from dazzle.cli.utils import load_project_appspec
    from dazzle.qa.capture import build_capture_plan, capture_screenshots
    from dazzle.qa.server import AppConnection, wait_for_ready

    project_dir = _resolve_project_dir(app)

    # Load AppSpec
    try:
        appspec = load_project_appspec(project_dir)
    except Exception as e:
        typer.echo(f"Failed to load AppSpec: {e}", err=True)
        raise typer.Exit(code=1)

    # Build capture plan
    targets = build_capture_plan(appspec)
    if not targets:
        typer.echo("No capture targets found (no workspaces or personas defined).", err=True)
        raise typer.Exit(code=1)

    # Filter by persona if requested
    if persona:
        targets = [t for t in targets if t.persona == persona]
        if not targets:
            typer.echo(f"No targets found for persona '{persona}'.", err=True)
            raise typer.Exit(code=1)

    if url is None:
        typer.echo(
            "--url is required. Start the app in another terminal first:\n"
            f"  dazzle e2e env start {app or '<example>'}\n"
            "Then pass its URL:\n"
            "  dazzle qa capture --url http://localhost:8981 ...",
            err=True,
        )
        raise typer.Exit(code=2)

    api_url_resolved = url.replace(":3000", ":8000") if ":3000" in url else url
    connection = AppConnection(
        site_url=url,
        api_url=api_url_resolved,
        process=None,
    )

    try:
        typer.echo("Waiting for server to be ready…")
        ready = asyncio.run(wait_for_ready(connection.api_url))
        if not ready:
            typer.echo("Server did not become ready in time.", err=True)
            raise typer.Exit(code=1)

        # Capture screenshots
        typer.echo(f"Capturing {len(targets)} screen(s)…")
        screens = asyncio.run(
            capture_screenshots(
                targets,
                site_url=connection.site_url,
                api_url=connection.api_url,
                project_dir=project_dir,
            )
        )

    finally:
        connection.stop()

    if not screens:
        typer.echo("No screenshots captured.", err=True)
        raise typer.Exit(code=1)

    # Print paths of captured screenshots
    for screen in screens:
        typer.echo(str(screen.screenshot))
