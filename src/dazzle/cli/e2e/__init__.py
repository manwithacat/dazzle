"""
E2E testing CLI commands.

Viewport assertions (``run-viewport``), persona journeys (``journey``) and
the ``env`` sub-group.
"""

import json
from pathlib import Path
from typing import Any

import typer

from dazzle.core.appspec_loader import load_project_appspec

e2e_app = typer.Typer(
    help="E2E testing with UX coverage tracking.",
    no_args_is_help=True,
)

from dazzle.cli.e2e.env import env_app as _env_app  # noqa: E402

e2e_app.add_typer(_env_app, name="env")


# ---------------------------------------------------------------------------
# Viewport testing
# ---------------------------------------------------------------------------


@e2e_app.command("run-viewport")
def e2e_run_viewport(
    manifest: str = typer.Option("dazzle.toml", "--manifest", "-m"),
    headless: bool = typer.Option(
        True, "--headless/--no-headless", help="Run browser in headless mode"
    ),
    viewports: str = typer.Option(
        None, "--viewports", help="Viewport names (comma-separated, e.g. mobile,tablet,desktop)"
    ),
    persona_id: str = typer.Option(None, "--persona", help="Persona ID to test as"),
    capture_screenshots: bool = typer.Option(
        False, "--screenshots", help="Capture screenshots during tests"
    ),
    update_baselines: bool = typer.Option(
        False, "--update-baselines", help="Update baseline screenshots"
    ),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Run viewport assertions against a running app.

    Examples:
        dazzle e2e run-viewport
        dazzle e2e run-viewport --viewports mobile,tablet
        dazzle e2e run-viewport --persona admin --screenshots
        dazzle e2e run-viewport --no-headless --json
    """
    from dazzle.cli._output import format_output
    from dazzle.cli.common import resolve_project
    from dazzle.mcp.server.handlers.viewport_testing import run_viewport_tests_impl

    root = resolve_project(manifest)
    viewport_list = [v.strip() for v in viewports.split(",")] if viewports else None
    raw = run_viewport_tests_impl(
        project_path=root,
        headless=headless,
        viewports=viewport_list,
        persona_id=persona_id,
        capture_screenshots=capture_screenshots,
        update_baselines=update_baselines,
    )
    result: dict[str, Any] = json.loads(raw)
    typer.echo(format_output(result, as_json=json_output))
    # #1295 — exit non-zero on real failures/errors so the CI gate can bite.
    # Today the run-viewport step is advisory (`continue-on-error` + `|| true`),
    # so this is inert there; it makes the eventual advisory→blocking flip a
    # pure workflow change (drop those two) rather than a silent always-pass.
    # A clean run with only SKIPPED (persona-unreachable) pages still exits 0 —
    # skips aren't failures.
    if result.get("error") or result.get("total_failed", 0) > 0:
        raise typer.Exit(code=1)


# ---------------------------------------------------------------------------
# Journey testing
# ---------------------------------------------------------------------------


def _check_playwright() -> bool:
    """Check if Playwright is importable."""
    try:
        import importlib

        importlib.import_module("playwright.async_api")
        return True
    except ImportError:
        return False


def _check_deployment(url: str) -> tuple[bool, str]:
    """Check if deployment is reachable."""
    try:
        import httpx

        resp = httpx.get(url, timeout=10, follow_redirects=True)
        if resp.status_code < 400:
            return True, "OK"
        return False, f"HTTP {resp.status_code}"
    except Exception as exc:
        return False, str(exc)


def _journey_preflight(url: str, project_root: Path) -> None:
    """Run preflight checks before journey testing."""
    if not _check_playwright():
        typer.echo(
            "Error: Playwright is required for journey testing. "
            "Install with: pip install playwright && playwright install chromium",
            err=True,
        )
        raise typer.Exit(code=2)

    creds_path = project_root / ".dazzle" / "test_personas.toml"
    if not creds_path.exists():
        typer.echo(
            f"Error: {creds_path} not found. "
            "Run 'dazzle demo propose' to generate test credentials, "
            "or create the file manually.",
            err=True,
        )
        raise typer.Exit(code=2)

    ok, msg = _check_deployment(url)
    if not ok:
        typer.echo(f"Error: Deployment at {url} is not reachable ({msg}).", err=True)
        raise typer.Exit(code=2)


@e2e_app.command("journey")
def journey_command(
    url: str = typer.Option(..., "--url", help="Base URL of the deployment"),
    personas: str = typer.Option(
        "all", "--personas", help="Comma-separated persona names or 'all'"
    ),
    phase: str = typer.Option("all", "--phase", help="'all', 'explore', or 'verify'"),
    output_dir: str = typer.Option("", "--output-dir", help="Override output directory"),
    headless: bool = typer.Option(True, "--headless/--no-headless"),
    manifest: str = typer.Option("dazzle.toml", "--manifest", "-m"),
) -> None:
    """Run persona-driven E2E journey testing against a live deployment.

    Two-phase execution: deterministic workspace exploration (Phase 1)
    followed by LLM-assisted story verification (Phase 2).

    Examples:
        dazzle e2e journey --url https://myapp.herokuapp.com
        dazzle e2e journey --url http://localhost:3000 --personas teacher,student
        dazzle e2e journey --url https://staging.example.com --phase explore
    """
    import asyncio

    from dazzle.cli.common import resolve_project

    project_root = resolve_project(manifest)
    _journey_preflight(url, project_root)

    asyncio.run(_run_journey(url, personas, phase, output_dir, headless, project_root))


async def _run_journey(
    url: str,
    personas_arg: str,
    phase: str,
    output_dir_arg: str,
    headless: bool,
    project_root: Path,
) -> None:
    """Async orchestrator for the journey command."""
    from datetime import date

    from dazzle.agent.journey_analyser import analyse_sessions
    from dazzle.agent.journey_credentials import load_credentials
    from dazzle.agent.journey_models import JourneySession
    from dazzle.agent.journey_writer import SessionWriter
    from dazzle.agent.missions.journey import (
        build_navigation_plan,
        run_phase1_exploration,
        run_phase2_verification,
    )

    # Parse AppSpec
    appspec = load_project_appspec(project_root)

    # Load credentials
    persona_filter = None if personas_arg == "all" else [p.strip() for p in personas_arg.split(",")]
    credentials = load_credentials(project_root, persona_filter=persona_filter)

    if not credentials:
        typer.echo("No matching personas found in test_personas.toml.", err=True)
        raise typer.Exit(code=2)

    # Set up output directory
    if output_dir_arg:
        out_dir = Path(output_dir_arg)
    else:
        out_dir = project_root / ".dazzle" / "test_sessions" / date.today().isoformat()

    writer = SessionWriter(out_dir)

    # Get stories per persona
    stories_by_persona: dict[str, list[Any]] = {}
    for story in appspec.stories:
        for persona in appspec.personas:
            pid = persona.id
            # Simple heuristic: story is available to all personas
            # TODO: refine with story persona assignments when available
            stories_by_persona.setdefault(pid, []).append(story)

    typer.echo(f"Journey testing {len(credentials)} persona(s) against {url}")
    typer.echo(f"Output: {out_dir}\n")

    sessions: list[JourneySession] = []
    personas_failed: list[str] = []

    # Import Playwright
    from playwright.async_api import async_playwright

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=headless)

        for persona_id, creds in credentials.items():
            typer.echo(f"--- Persona: {persona_id} ---")
            context = await browser.new_context()
            page = await context.new_page()

            phase1_steps = []

            # Phase 1: Explore
            if phase in ("all", "explore"):
                plan = build_navigation_plan(appspec, persona_id)
                typer.echo(f"  Phase 1: {len(plan)} targets")
                phase1_steps = await run_phase1_exploration(
                    plan=plan,
                    page=page,
                    credentials=creds,
                    persona=persona_id,
                    writer=writer,
                    base_url=url,
                )
                pass_count = sum(1 for s in phase1_steps if s.verdict.value == "pass")
                fail_count = len(phase1_steps) - pass_count
                typer.echo(f"  Phase 1 done: {pass_count} pass, {fail_count} other")

                # Check if login failed
                login_failed = any(
                    s.action == "login" and s.verdict.value == "fail" for s in phase1_steps
                )
                if login_failed:
                    typer.secho(f"  Login failed for {persona_id}", fg=typer.colors.RED)
                    personas_failed.append(persona_id)
                    await context.close()
                    continue

            elif phase == "verify":
                # Load prior explore data
                try:
                    prior = writer.load_session(persona_id)
                    phase1_steps = prior.steps
                except FileNotFoundError:
                    typer.secho(
                        f"  Warning: No explore data for {persona_id} — skipping",
                        fg=typer.colors.YELLOW,
                    )
                    await context.close()
                    continue

            # Phase 2: Verify
            if phase in ("all", "verify"):
                persona_stories = stories_by_persona.get(persona_id, [])
                if persona_stories:
                    typer.echo(f"  Phase 2: {len(persona_stories)} stories")
                    phase2_steps = await run_phase2_verification(
                        persona=persona_id,
                        stories=persona_stories,
                        phase1_steps=phase1_steps,
                        page=page,
                        writer=writer,
                        base_url=url,
                    )
                    typer.echo(f"  Phase 2 done: {len(phase2_steps)} steps")
                else:
                    typer.echo(f"  Phase 2 skipped: no stories for {persona_id}")

            await context.close()

            # Build session from all steps for this persona
            try:
                session = writer.load_session(persona_id)
                sessions.append(session)
            except FileNotFoundError:
                pass

        await browser.close()

    writer.close()

    # Analysis
    typer.echo("\nRunning cross-persona analysis...")
    import dazzle

    analysis = analyse_sessions(
        sessions=sessions,
        dazzle_version=getattr(dazzle, "__version__", "0.44.0"),
        deployment_url=url,
    )
    writer.write_analysis(analysis)

    # Report
    try:
        from dazzle.agent.journey_reporter import render_report

        report_path = out_dir / "report.html"
        render_report(sessions, analysis, report_path)
        typer.echo(f"Report: {report_path}")
    except Exception as exc:
        typer.echo(f"Warning: Could not generate HTML report: {exc}", err=True)

    # Summary
    typer.echo(f"\n{'=' * 50}")
    typer.echo("Journey Testing Summary")
    typer.echo(f"{'=' * 50}")
    typer.echo(f"Personas tested: {len(sessions)}")
    typer.echo(f"Personas failed login: {len(personas_failed)}")
    total_steps = sum(len(s.steps) for s in sessions)
    typer.echo(f"Total steps: {total_steps}")
    if analysis.cross_persona_patterns:
        typer.echo(f"Cross-persona patterns: {len(analysis.cross_persona_patterns)}")
    if analysis.recommendations:
        typer.echo(f"Recommendations: {len(analysis.recommendations)}")
    typer.echo(f"Output: {out_dir}")
