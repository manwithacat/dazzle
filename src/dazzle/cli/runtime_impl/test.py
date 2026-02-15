"""
Dazzle test command.

Run tests for a Dazzle application.
"""

from __future__ import annotations

import json as json_module
import logging
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import typer

from dazzle.core.errors import DazzleError, ParseError
from dazzle.core.fileset import discover_dsl_files
from dazzle.core.linker import build_appspec
from dazzle.core.lint import lint_appspec
from dazzle.core.manifest import load_manifest
from dazzle.core.parser import parse_modules

logger = logging.getLogger(__name__)


def check_command(
    manifest: str = typer.Option("dazzle.toml", "--manifest", "-m"),
    api_only: bool = typer.Option(
        False,
        "--api-only",
        help="Run only API contract tests (no UI tests)",
    ),
    e2e: bool = typer.Option(
        False,
        "--e2e",
        help="Run E2E tests with Playwright (requires app running or --start-server)",
    ),
    benchmark: bool = typer.Option(
        False,
        "--benchmark",
        help="Run performance benchmarks",
    ),
    a11y: bool = typer.Option(
        False,
        "--a11y",
        help="Run accessibility checks (requires Playwright)",
    ),
    a11y_level: str = typer.Option(
        "AA",
        "--a11y-level",
        help="WCAG level to check: A, AA, or AAA (default: AA)",
    ),
    start_server: bool = typer.Option(
        True,
        "--start-server/--no-start-server",
        help="Automatically start server for testing (default: true)",
    ),
    port: int = typer.Option(
        8000,
        "--port",
        "-p",
        help="API server port",
    ),
    ui_port: int = typer.Option(
        3000,
        "--ui-port",
        help="UI server port (for E2E tests)",
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="Verbose output",
    ),
    output: str = typer.Option(
        None,
        "--output",
        "-o",
        help="Output file for test results JSON",
    ),
) -> None:
    """
    Run tests for a Dazzle application.

    This command provides comprehensive testing for Dazzle apps:
    - API contract tests: Validates all endpoints against the spec
    - E2E tests: Runs Playwright-based UI tests (with --e2e)
    - Benchmarks: Performance testing with latency/throughput metrics (with --benchmark)
    - Accessibility: WCAG compliance checks using axe-core (with --a11y)

    The server is automatically started in test mode for the duration of tests.

    Examples:
        dazzle check                       # Run API tests (starts server)
        dazzle check --api-only            # Run only API contract tests
        dazzle check --e2e                 # Include E2E UI tests
        dazzle check --benchmark           # Run performance benchmarks
        dazzle check --a11y                # Run WCAG AA accessibility checks
        dazzle check --a11y --a11y-level A # Run WCAG Level A checks only
        dazzle check --no-start-server     # Use already-running server
        dazzle check -o results.json       # Save results to file
    """
    # Load and build AppSpec
    manifest_path = Path(manifest).resolve()
    root = manifest_path.parent

    try:
        mf = load_manifest(manifest_path)
        dsl_files = discover_dsl_files(root, mf)
        modules = parse_modules(dsl_files)
        appspec = build_appspec(modules, mf.project_root)

        # Validate
        errors, warnings = lint_appspec(appspec)
        if errors:
            typer.echo("Cannot run tests; spec has validation errors:", err=True)
            for err in errors:
                typer.echo(f"  ERROR: {err}", err=True)
            raise typer.Exit(code=1)

        for warn in warnings:
            if verbose:
                typer.echo(f"WARNING: {warn}")

    except (ParseError, DazzleError) as e:
        typer.echo(f"Error loading spec: {e}", err=True)
        raise typer.Exit(code=1)

    # Convert to BackendSpec for API testing
    try:
        from dazzle_back.converters import convert_appspec_to_backend
    except ImportError as e:
        typer.echo(f"Dazzle backend not available: {e}", err=True)
        raise typer.Exit(code=1)

    backend_spec = convert_appspec_to_backend(appspec)

    typer.echo(f"Testing Dazzle application: {appspec.name}")
    typer.echo(f"  • {len(backend_spec.entities)} entities")
    typer.echo(f"  • {len(backend_spec.endpoints)} endpoints")
    typer.echo()

    # Start server if requested
    server_process = None
    api_url = f"http://localhost:{port}"

    if start_server:
        # Determine if we need the UI (for E2E or a11y tests)
        need_ui = e2e or a11y
        if need_ui:
            typer.echo("Starting Dazzle server with UI in test mode...")
        else:
            typer.echo("Starting Dazzle server in test mode...")

        # Use subprocess to start the server
        # Note: serve uses --port for frontend (3000) and --api-port for API (8000)
        if need_ui:
            # Full server with UI
            cmd = [
                sys.executable,
                "-m",
                "dazzle.cli",
                "serve",
                "--local",
                "--port",
                str(ui_port),  # Frontend port
                "--api-port",
                str(port),  # API port
                "--test-mode",
                "-m",
                str(manifest_path),
            ]
        else:
            # Backend only
            cmd = [
                sys.executable,
                "-m",
                "dazzle.cli",
                "serve",
                "--local",
                "--backend-only",
                "--port",
                str(port),  # API port (used as main port in backend-only mode)
                "--test-mode",
                "-m",
                str(manifest_path),
            ]

        server_process = subprocess.Popen(
            cmd,
            cwd=root,
            stdout=subprocess.PIPE if not verbose else None,
            stderr=subprocess.PIPE if not verbose else None,
        )

        # Wait for server to be ready
        max_wait = 30.0
        waited = 0.0
        while waited < max_wait:
            try:
                import urllib.request

                with urllib.request.urlopen(f"{api_url}/health", timeout=1) as resp:
                    if resp.status == 200:
                        break
            except Exception:
                logger.debug("Waiting for API server to start", exc_info=True)
            time.sleep(0.5)
            waited += 0.5

        if waited >= max_wait:
            typer.echo("Server failed to start within timeout", err=True)
            if server_process:
                server_process.terminate()
            raise typer.Exit(code=1)

        typer.echo(f"  API ready at {api_url}")

        # Wait for UI to be ready if needed
        if need_ui:
            import urllib.request

            ui_url = f"http://localhost:{ui_port}"
            ui_waited = 0.0
            while ui_waited < max_wait:
                try:
                    with urllib.request.urlopen(ui_url, timeout=1) as resp:
                        if resp.status == 200:
                            break
                except Exception:
                    logger.debug("Waiting for UI server to start", exc_info=True)
                time.sleep(0.5)
                ui_waited += 0.5

            if ui_waited >= max_wait:
                typer.secho(
                    f"  Warning: UI at {ui_url} not responding",
                    fg=typer.colors.YELLOW,
                )
            else:
                typer.echo(f"  UI ready at {ui_url}")

        typer.echo()

    results: dict[str, Any] = {
        "app_name": appspec.name,
        "api_tests": [],
        "e2e_tests": [],
        "a11y_results": None,
        "summary": {
            "api_passed": 0,
            "api_failed": 0,
            "e2e_passed": 0,
            "e2e_failed": 0,
            "a11y_violations": 0,
            "a11y_passed": True,
        },
    }

    try:
        # Import test runners from separate module
        from dazzle.cli.runtime_testing import (
            run_accessibility_checks,
            run_api_contract_tests,
            run_benchmarks,
            run_e2e_tests,
        )

        # Run API contract tests
        typer.echo("Running API contract tests...")
        api_results = run_api_contract_tests(backend_spec, api_url, verbose)
        results["api_tests"] = api_results["tests"]
        results["summary"]["api_passed"] = api_results["passed"]
        results["summary"]["api_failed"] = api_results["failed"]

        typer.echo(f"  API tests: {api_results['passed']} passed, {api_results['failed']} failed")

        # Run E2E tests if requested
        if e2e and not api_only:
            typer.echo()
            typer.echo("Running E2E tests...")
            e2e_results = run_e2e_tests(
                manifest_path, api_url, f"http://localhost:{ui_port}", verbose
            )
            results["e2e_tests"] = e2e_results["tests"]
            results["summary"]["e2e_passed"] = e2e_results["passed"]
            results["summary"]["e2e_failed"] = e2e_results["failed"]

            typer.echo(
                f"  E2E tests: {e2e_results['passed']} passed, {e2e_results['failed']} failed"
            )

        # Run benchmarks if requested
        if benchmark:
            typer.echo()
            typer.echo("Running performance benchmarks...")
            bench_results = run_benchmarks(backend_spec, api_url, verbose)
            results["benchmarks"] = bench_results

            # Display benchmark summary
            typer.echo(f"  Cold start:    {bench_results['cold_start_ms']:.0f}ms")
            typer.echo(f"  Latency p50:   {bench_results['latency_p50_ms']:.1f}ms")
            typer.echo(f"  Latency p95:   {bench_results['latency_p95_ms']:.1f}ms")
            typer.echo(f"  Latency p99:   {bench_results['latency_p99_ms']:.1f}ms")
            typer.echo(f"  Throughput:    {bench_results['throughput_rps']:.0f} req/s")

        # Run accessibility checks if requested
        if a11y and not api_only:
            typer.echo()
            typer.echo(f"Running WCAG {a11y_level.upper()} accessibility checks...")
            a11y_results = run_accessibility_checks(
                f"http://localhost:{ui_port}",
                a11y_level.upper(),
                appspec,
                verbose,
            )
            results["a11y_results"] = a11y_results
            results["summary"]["a11y_violations"] = a11y_results["violation_count"]
            results["summary"]["a11y_passed"] = a11y_results["passed"]

            # Display a11y summary
            if a11y_results["passed"]:
                typer.secho(
                    f"  No WCAG {a11y_level.upper()} violations found!",
                    fg=typer.colors.GREEN,
                )
            else:
                typer.secho(
                    f"  {a11y_results['violation_count']} WCAG "
                    f"{a11y_level.upper()} violation(s) found",
                    fg=typer.colors.YELLOW,
                )
                if verbose and a11y_results.get("violations"):
                    for v in a11y_results["violations"][:5]:  # Show first 5
                        typer.echo(f"    - {v['id']}: {v['impact']} - {v['help']}")

    finally:
        # Stop server if we started it
        if server_process:
            server_process.terminate()
            try:
                server_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                server_process.kill()

    # Summary
    typer.echo()
    total_passed = results["summary"]["api_passed"] + results["summary"]["e2e_passed"]
    total_failed = results["summary"]["api_failed"] + results["summary"]["e2e_failed"]
    a11y_violations = results["summary"]["a11y_violations"]
    a11y_passed = results["summary"]["a11y_passed"]

    if total_failed == 0 and a11y_passed:
        typer.secho(f"✓ All {total_passed} tests passed!", fg=typer.colors.GREEN)
    elif total_failed == 0 and not a11y_passed:
        typer.secho(
            f"✓ All {total_passed} tests passed, but {a11y_violations} a11y violation(s)",
            fg=typer.colors.YELLOW,
        )
    else:
        msg = f"✗ {total_passed} passed, {total_failed} failed"
        if a11y_violations > 0:
            msg += f", {a11y_violations} a11y violation(s)"
        typer.secho(msg, fg=typer.colors.RED)

    # Output results to file
    if output:
        output_path = Path(output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json_module.dumps(results, indent=2))
        typer.echo(f"Results saved to {output_path}")

    if total_failed > 0:
        raise typer.Exit(code=1)
