"""CLI sub-app for the Dazzle visual QA toolkit."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

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


@qa_app.command("trial")
def qa_trial(
    app: str | None = typer.Option(None, "--app", "-a", help="Example app name (defaults to cwd)"),
    scenario: str | None = typer.Option(
        None, "--scenario", "-s", help="Scenario name from trial.toml (defaults to first)"
    ),
    output: Path | None = typer.Option(
        None, "--output", "-o", help="Report output path (default: dev_docs/qa-trial-*.md)"
    ),
    headless: bool = typer.Option(
        True, "--headless/--headed", help="Run browser headless (default) or visible"
    ),
    model: str | None = typer.Option(
        None, "--model", help="Override LLM model (default: Claude Sonnet)"
    ),
) -> None:
    """Run a qualitative business-user trial of a Dazzle app.

    Puts an LLM in the shoes of a real business user evaluating this
    software. The LLM attempts meaningful tasks and records friction —
    things that would make a real user hesitate to recommend the
    software. Output is a markdown report for human triage, NOT a
    pass/fail CI gate.

    Requires ``trial.toml`` in the app directory declaring at least
    one scenario. See ``examples/support_tickets/trial.toml`` for
    format.

    Example:

        cd examples/support_tickets
        dazzle qa trial
        # → dev_docs/qa-trial-<scenario>-<timestamp>.md

    """
    import sys
    import time
    import tomllib

    from dazzle.agent.core import DazzleAgent
    from dazzle.agent.executor import PlaywrightExecutor
    from dazzle.agent.missions.trial import build_trial_mission
    from dazzle.agent.observer import PlaywrightObserver
    from dazzle.cli.runtime_impl.ports import read_runtime_test_secret
    from dazzle.cli.ux_interactions import _authenticate_persona_on_context
    from dazzle.qa.trial_report import build_trial_report, render_trial_report
    from dazzle.testing.ux.interactions.server_fixture import launch_interaction_server

    project_dir = _resolve_project_dir(app)
    trial_path = project_dir / "trial.toml"

    if not trial_path.exists():
        typer.echo(
            f"No trial.toml at {trial_path}. Create one to declare scenarios — "
            "see examples/support_tickets/trial.toml for format.",
            err=True,
        )
        raise typer.Exit(code=2)

    try:
        trial_cfg = tomllib.loads(trial_path.read_text())
    except tomllib.TOMLDecodeError as exc:
        typer.echo(f"trial.toml parse failed: {exc}", err=True)
        raise typer.Exit(code=2) from exc

    scenarios = trial_cfg.get("scenario", [])
    if not scenarios:
        typer.echo(f"No [[scenario]] entries in {trial_path}", err=True)
        raise typer.Exit(code=2)

    if scenario:
        chosen = next((s for s in scenarios if s.get("name") == scenario), None)
        if chosen is None:
            names = [s.get("name", "?") for s in scenarios]
            typer.echo(
                f"Scenario '{scenario}' not found. Available: {', '.join(names)}",
                err=True,
            )
            raise typer.Exit(code=2)
    else:
        chosen = scenarios[0]

    scenario_name = chosen.get("name", "unnamed")
    login_persona = chosen.get("login_persona", "")
    if not login_persona:
        typer.echo(
            f"Scenario '{scenario_name}' has no login_persona. "
            "Set login_persona to the DSL persona ID to trial as.",
            err=True,
        )
        raise typer.Exit(code=2)

    typer.echo(f"Trial scenario: {scenario_name} (as persona {login_persona})")

    transcript_sink: dict[str, list[dict[str, Any]]] = {"friction": [], "verdict": []}
    started_at = time.monotonic()

    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        typer.echo(
            "Playwright is not installed. Install with: pip install 'dazzle-dsl[e2e]' "
            "or pip install 'playwright>=1.40'",
            err=True,
        )
        raise typer.Exit(code=2) from exc

    with launch_interaction_server(project_dir) as conn:
        site_url = conn.site_url
        try:
            test_secret = read_runtime_test_secret(project_dir)
        except Exception:
            test_secret = ""

        # Playwright lives in a sync context; the agent run itself is
        # async, so we bridge via asyncio.run inside the sync block.
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=headless)
            context = browser.new_context()
            _authenticate_persona_on_context(context, site_url, login_persona, test_secret or "")
            page = context.new_page()

            observer = PlaywrightObserver(
                page,
                include_screenshots=False,
                capture_console=True,
            )
            executor = PlaywrightExecutor(page)
            agent = DazzleAgent(
                observer=observer,
                executor=executor,
                model=model,
                use_tool_calls=True,
            )

            mission = build_trial_mission(
                chosen,
                base_url=site_url,
                transcript_sink=transcript_sink,
            )

            typer.echo(
                f"Starting trial — up to {mission.max_steps} steps, "
                f"budget {mission.token_budget:,} tokens"
            )
            transcript = asyncio.run(agent.run(mission))
            browser.close()

    duration_s = time.monotonic() - started_at

    friction = transcript_sink.get("friction", [])
    verdict_entries = transcript_sink.get("verdict", [])
    verdict = verdict_entries[0]["text"] if verdict_entries else ""

    report = build_trial_report(
        scenario_name=scenario_name,
        user_identity=chosen.get("user_identity", ""),
        friction=friction,
        verdict=verdict,
        step_count=len(transcript.steps),
        duration_seconds=duration_s,
        tokens_used=transcript.tokens_used,
        outcome=transcript.outcome,
    )
    rendered = render_trial_report(report)

    if output is None:
        dev_docs = project_dir / "dev_docs"
        dev_docs.mkdir(exist_ok=True)
        stamp = report.generated_at.strftime("%Y%m%d-%H%M%S")
        output = dev_docs / f"qa-trial-{scenario_name}-{stamp}.md"
    else:
        output.parent.mkdir(parents=True, exist_ok=True)

    output.write_text(rendered)
    typer.echo(
        f"\nTrial complete. {len(friction)} friction observation(s) recorded. Report: {output}",
        file=sys.stdout,
    )
