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


def _seed_demo_data_for_trial(project_dir: Path, site_url: str, test_secret: str) -> None:
    """Seed demo data after the trial server is up (#817).

    ``--fresh-db`` truncates the DB, which left every trial running
    against an empty app — and the agent correctly flagged "no data,
    can't evaluate" every time, swamping real framework feedback.
    This helper runs after :func:`_reset_db_for_trial` and after
    ``launch_interaction_server`` has the app listening, and:

    1. Finds the project's blueprint (``dsl/seeds/demo_data/blueprint.json``
       is the default). If none exists, silently return — trials run
       empty, same as before.
    2. Generates CSV/JSONL data files from the blueprint into a temp
       directory, unless the data directory already contains them.
    3. Authenticates against the running server via the test endpoint
       to get an admin session cookie.
    4. POSTs each entity's rows to the runtime via DemoDataLoader.
    """
    import tempfile

    import httpx

    from dazzle.cli.demo import _find_data_dir
    from dazzle.cli.utils import load_project_appspec
    from dazzle.demo_data.loader import DemoDataLoader, topological_sort_entities
    from dazzle.mcp.server.handlers.demo_data import demo_generate_impl

    blueprint = project_dir / "dsl" / "seeds" / "demo_data" / "blueprint.json"
    existing_data = _find_data_dir(project_dir)

    if not blueprint.exists() and existing_data is None:
        return  # nothing to seed

    try:
        appspec = load_project_appspec(project_dir)
    except Exception as exc:
        typer.echo(f"Seed skipped: could not load appspec ({exc})", err=True)
        return

    # If no pre-generated data exists, generate it into a tempdir so
    # we don't litter the project with gitignored JSONL files.
    if existing_data is None or not any(existing_data.glob("*.jsonl")):
        tmp_root = Path(tempfile.mkdtemp(prefix="dazzle-trial-seed-"))
        try:
            result = demo_generate_impl(
                project_dir, output_format="jsonl", output_dir=str(tmp_root)
            )
            if result.get("status") != "generated":
                typer.echo(
                    f"Seed skipped: demo_generate_impl returned {result.get('status')}",
                    err=True,
                )
                return
            data_dir = Path(result["output_dir"])
        except Exception as exc:
            typer.echo(f"Seed skipped: demo data generation failed ({exc})", err=True)
            return
    else:
        data_dir = existing_data

    # Authenticate as admin via the test endpoint so we can POST as a
    # privileged user. /__test__/authenticate yields a session token.
    headers = {"X-Test-Secret": test_secret} if test_secret else {}
    try:
        with httpx.Client(timeout=10) as client:
            resp = client.post(
                f"{site_url}/__test__/authenticate",
                json={"role": "admin", "username": "admin"},
                headers=headers,
            )
            if resp.status_code != 200:
                typer.echo(
                    f"Seed skipped: admin auth returned {resp.status_code}",
                    err=True,
                )
                return
            token = resp.json().get("session_token") or ""
    except Exception as exc:
        typer.echo(f"Seed skipped: admin auth failed ({exc})", err=True)
        return

    entity_order = topological_sort_entities(appspec.domain.entities)
    with DemoDataLoader(base_url=site_url) as loader:
        client = loader._get_client()
        if token:
            client.cookies.set("dazzle_session", token)
        # Prime the CSRF cookie by making a GET, then sync it onto the
        # X-CSRF-Token header for every subsequent request via an httpx
        # event hook. The CSRF middleware rotates the cookie on POST,
        # so a static header would stop working after the first
        # successful write.
        try:
            client.get("/")
        except Exception:
            pass

        def _sync_csrf(request: httpx.Request) -> None:
            csrf = client.cookies.get("dazzle_csrf")
            if csrf:
                request.headers["X-CSRF-Token"] = csrf

        client.event_hooks = {"request": [_sync_csrf]}
        loader._token = None  # don't use bearer-auth path; cookies are enough

        try:
            report = loader.load_all(data_dir, entity_order)
        except Exception as exc:
            typer.echo(f"Seed skipped: load_all raised {exc}", err=True)
            return

    first_line = report.summary().splitlines()[0]
    typer.echo(f"Seeded demo data: {first_line}")
    # Surface a couple of error examples whenever anything failed —
    # makes infrastructure bugs (auth, CSRF, schema mismatch) visible
    # without spamming the trial log with hundreds of identical
    # validation errors.
    if report.total_failed:
        sample_errors: list[str] = []
        for r in report.results:
            sample_errors.extend(r.errors[:2])
            if len(sample_errors) >= 3:
                break
        for err in sample_errors[:3]:
            typer.echo(f"  seed error: {err[:240]}", err=True)


def _reset_db_for_trial(project_dir: Path) -> None:
    """Truncate entity tables before a trial run (#810).

    Prior ``dazzle qa trial`` runs can leave placeholder rows
    (``Test name 1``, ``UX Edited Value``) in the app's database that
    subsequent trials observe and flag as bugs. This truncates those
    rows while preserving auth — the same behaviour as
    ``dazzle db reset --yes`` but invoked programmatically so we skip
    the interactive confirmation and work against the correct project
    root without requiring a cwd change.
    """
    import os

    from dazzle.cli.db import _resolve_url, _run_with_connection
    from dazzle.cli.utils import load_project_appspec
    from dazzle.db.reset import db_reset_impl

    old_cwd = Path.cwd()
    try:
        os.chdir(project_dir)
        appspec = load_project_appspec(project_dir)
        entities = appspec.domain.entities
        url = _resolve_url("")

        async def _run(conn: Any) -> Any:
            return await db_reset_impl(entities=entities, conn=conn)

        result = asyncio.run(_run_with_connection(project_dir, url, _run, schema=""))
        typer.echo(
            f"Fresh DB: truncated {result['truncated']} tables "
            f"({result['total_rows']:,} rows removed). Auth preserved."
        )
    finally:
        os.chdir(old_cwd)


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
    fresh_db: bool = typer.Option(
        False,
        "--fresh-db",
        help=(
            "Truncate entity tables before starting the server. Prevents the "
            "trial from observing stale rows left behind by prior runs "
            "(placeholder values, old fixture data, etc.). Auth is preserved."
        ),
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

    if fresh_db:
        _reset_db_for_trial(project_dir)

    transcript_sink: dict[str, list[dict[str, Any]]] = {"friction": [], "verdict": []}
    started_at = time.monotonic()

    try:
        from playwright.async_api import async_playwright
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
            test_secret_val = read_runtime_test_secret(project_dir) or ""
        except Exception:
            test_secret_val = ""

        if fresh_db:
            _seed_demo_data_for_trial(project_dir, site_url, test_secret_val)

        async def _run_trial() -> tuple[Any, Any]:
            """Full async path: start browser, authenticate via POST +
            add_cookies, run the agent, tear down. PlaywrightObserver
            expects an async page, so this all has to live under the
            same event loop."""
            import httpx

            async with async_playwright() as pw:
                browser = await pw.chromium.launch(headless=headless)
                context = await browser.new_context()

                # Authenticate via the /__test__/ endpoint (same
                # protocol _authenticate_persona_on_context uses,
                # but awaitable).
                headers = {"X-Test-Secret": test_secret_val} if test_secret_val else {}
                async with httpx.AsyncClient() as http:
                    resp = await http.post(
                        f"{site_url}/__test__/authenticate",
                        json={"role": login_persona, "username": login_persona},
                        headers=headers,
                        timeout=10,
                    )
                if resp.status_code != 200:
                    typer.echo(
                        f"[auth] /__test__/authenticate returned {resp.status_code} "
                        f"(body: {resp.text[:200]!r}). Persona {login_persona!r} may "
                        f"not be a valid role, or test-mode may be disabled.",
                        err=True,
                    )
                    await browser.close()
                    raise typer.Exit(code=2)
                token = resp.json().get("session_token") or resp.json().get("token") or ""
                if token:
                    await context.add_cookies(
                        [{"name": "dazzle_session", "value": token, "url": site_url}]
                    )

                page = await context.new_page()
                observer_inner = PlaywrightObserver(
                    page,
                    include_screenshots=False,
                    capture_console=True,
                )
                executor_inner = PlaywrightExecutor(page)
                agent_inner = DazzleAgent(
                    observer=observer_inner,
                    executor=executor_inner,
                    model=model,
                    use_tool_calls=True,
                )
                mission_inner = build_trial_mission(
                    chosen,
                    base_url=site_url,
                    transcript_sink=transcript_sink,
                )
                typer.echo(
                    f"Starting trial — up to {mission_inner.max_steps} steps, "
                    f"budget {mission_inner.token_budget:,} tokens"
                )
                t = await agent_inner.run(mission_inner)
                await browser.close()
                return t, mission_inner

        transcript, _mission = asyncio.run(_run_trial())

    duration_s = time.monotonic() - started_at

    friction = transcript_sink.get("friction", [])
    verdict_entries = transcript_sink.get("verdict", [])
    verdict = verdict_entries[0]["text"] if verdict_entries else ""

    # Fallback verdict synthesis — trials can run out of max_steps
    # before the LLM calls submit_verdict. The verdict is the most
    # important output, so we guarantee one via a single follow-up
    # LLM call that reads the friction observations and writes a
    # 1-paragraph verdict in the user's voice.
    if not verdict and friction:
        from dazzle.qa.trial_verdict_fallback import synthesize_verdict

        typer.echo("No verdict captured — synthesizing one from recorded friction…")
        verdict = synthesize_verdict(
            user_identity=chosen.get("user_identity", ""),
            business_context=chosen.get("business_context", ""),
            friction=friction,
            model=model,
        )
        if verdict:
            verdict = f"(synthesized from recorded friction — agent ran out of steps)\n\n{verdict}"

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
