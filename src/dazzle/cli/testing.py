"""
Semantic E2E testing CLI commands.

Commands for generating and running E2E tests for Dazzle applications.
"""

from pathlib import Path
from typing import Any

import typer

from dazzle.core.errors import DazzleError, ParseError
from dazzle.core.fileset import discover_dsl_files
from dazzle.core.linker import build_appspec
from dazzle.core.lint import lint_appspec
from dazzle.core.manifest import load_manifest
from dazzle.core.parser import parse_modules

test_app = typer.Typer(
    help="Semantic E2E testing commands for Dazzle applications.",
    no_args_is_help=True,
)


@test_app.command("generate")
def test_generate(
    manifest: str = typer.Option("dazzle.toml", "--manifest", "-m"),
    output: str = typer.Option(
        None,
        "--output",
        "-o",
        help="Output file for E2ETestSpec JSON (default: stdout)",
    ),
    include_flows: bool = typer.Option(
        True,
        "--flows/--no-flows",
        help="Include auto-generated CRUD and validation flows",
    ),
    include_fixtures: bool = typer.Option(
        True,
        "--fixtures/--no-fixtures",
        help="Include auto-generated fixtures",
    ),
    format: str = typer.Option(
        "json",
        "--format",
        "-f",
        help="Output format: json (default) or yaml",
    ),
) -> None:
    """
    Generate E2ETestSpec from AppSpec.

    Creates a complete test specification including:
    - CRUD flows for each entity (create, view, update, delete)
    - Validation flows from field constraints
    - Navigation flows for each surface
    - Fixtures from entity schemas
    - Usability and accessibility rules

    Examples:
        dazzle test generate                    # Print to stdout
        dazzle test generate -o tests.json      # Save to file
        dazzle test generate --no-flows         # Skip auto-generated flows
        dazzle test generate --format yaml      # YAML output
    """
    try:
        from dazzle.testing.testspec_generator import generate_e2e_testspec
    except ImportError as e:
        typer.echo(f"E2E testing module not available: {e}", err=True)
        raise typer.Exit(code=1)

    # Load AppSpec
    manifest_path = Path(manifest).resolve()
    root = manifest_path.parent

    try:
        mf = load_manifest(manifest_path)
        dsl_files = discover_dsl_files(root, mf)
        modules = parse_modules(dsl_files)
        appspec = build_appspec(modules, mf.project_root)

        errors, warnings = lint_appspec(appspec)
        for warn in warnings:
            typer.echo(f"WARNING: {warn}", err=True)

        if errors:
            typer.echo("Cannot generate tests; spec has validation errors:", err=True)
            for err in errors:
                typer.echo(f"  ERROR: {err}", err=True)
            raise typer.Exit(code=1)

    except (ParseError, DazzleError) as e:
        typer.echo(f"Error loading spec: {e}", err=True)
        raise typer.Exit(code=1)

    # Generate E2ETestSpec
    testspec = generate_e2e_testspec(appspec)

    # Apply filters if requested
    if not include_flows:
        # Keep only DSL-defined flows (not auto-generated)
        testspec.flows = [f for f in testspec.flows if not getattr(f, "auto_generated", False)]

    if not include_fixtures:
        testspec.fixtures = []

    # Output statistics
    typer.echo(f"Generated E2ETestSpec for '{appspec.name}':", err=True)
    typer.echo(f"  • {len(testspec.fixtures)} fixtures", err=True)
    typer.echo(f"  • {len(testspec.flows)} flows", err=True)
    typer.echo(f"  • {len(testspec.usability_rules)} usability rules", err=True)
    typer.echo(f"  • {len(testspec.a11y_rules)} accessibility rules", err=True)

    # Serialize
    if format == "json":
        content = testspec.model_dump_json(indent=2)
    elif format == "yaml":
        try:
            import yaml

            content = yaml.safe_dump(
                testspec.model_dump(mode="json"),
                default_flow_style=False,
                allow_unicode=True,
            )
        except ImportError:
            typer.echo("YAML output requires PyYAML: pip install pyyaml", err=True)
            raise typer.Exit(code=1)
    else:
        typer.echo(f"Unknown format: {format}", err=True)
        raise typer.Exit(code=1)

    # Output
    if output:
        output_path = Path(output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(content)
        typer.echo(f"  → Saved to {output_path}", err=True)
    else:
        typer.echo(content)


@test_app.command("run")
def test_run(
    manifest: str = typer.Option("dazzle.toml", "--manifest", "-m"),
    priority: str = typer.Option(
        None,
        "--priority",
        "-p",
        help="Run only flows with this priority (high, medium, low)",
    ),
    tag: str = typer.Option(
        None,
        "--tag",
        "-t",
        help="Run only flows with this tag",
    ),
    flow: str = typer.Option(
        None,
        "--flow",
        "-f",
        help="Run only this specific flow by ID",
    ),
    base_url: str = typer.Option(
        "http://localhost:3000",
        "--base-url",
        help="Base URL of the running application",
    ),
    api_url: str = typer.Option(
        "http://localhost:8000",
        "--api-url",
        help="Base URL of the API server",
    ),
    headless: bool = typer.Option(
        True,
        "--headless/--headed",
        help="Run browser in headless mode",
    ),
    timeout: int = typer.Option(
        30000,
        "--timeout",
        help="Default timeout in milliseconds",
    ),
    output: str = typer.Option(
        None,
        "--output",
        "-o",
        help="Output file for test results JSON",
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="Verbose output",
    ),
) -> None:
    """
    Run E2E tests using Playwright.

    Requires the application to be running (use 'dazzle dnr serve --test-mode').

    Examples:
        dazzle test run                             # Run all tests
        dazzle test run --priority high             # Run high-priority only
        dazzle test run --tag crud                  # Run tests tagged 'crud'
        dazzle test run --flow Task_create_valid    # Run specific flow
        dazzle test run --headed                    # Show browser window
    """
    # Check for playwright
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        typer.echo("Playwright not installed. Install with:", err=True)
        typer.echo("  pip install playwright", err=True)
        typer.echo("  playwright install chromium", err=True)
        raise typer.Exit(code=1)

    try:
        from dazzle.testing.testspec_generator import generate_e2e_testspec
        from dazzle_e2e.adapters.dnr import DNRAdapter
    except ImportError as e:
        typer.echo(f"E2E testing modules not available: {e}", err=True)
        raise typer.Exit(code=1)

    # Load AppSpec
    manifest_path = Path(manifest).resolve()
    root = manifest_path.parent

    try:
        mf = load_manifest(manifest_path)
        dsl_files = discover_dsl_files(root, mf)
        modules = parse_modules(dsl_files)
        appspec = build_appspec(modules, mf.project_root)

        errors, _ = lint_appspec(appspec)
        if errors:
            typer.echo("Cannot run tests; spec has validation errors:", err=True)
            for err in errors:
                typer.echo(f"  ERROR: {err}", err=True)
            raise typer.Exit(code=1)

    except (ParseError, DazzleError) as e:
        typer.echo(f"Error loading spec: {e}", err=True)
        raise typer.Exit(code=1)

    # Generate E2ETestSpec
    testspec = generate_e2e_testspec(appspec)

    # Include any DSL-defined flows from appspec
    if appspec.e2e_flows:
        testspec.flows.extend(appspec.e2e_flows)

    # Filter flows
    flows_to_run = testspec.flows

    if flow:
        flows_to_run = [f for f in flows_to_run if f.id == flow]
        if not flows_to_run:
            typer.echo(f"Flow not found: {flow}", err=True)
            typer.echo("Available flows:", err=True)
            for f in testspec.flows[:10]:
                typer.echo(f"  - {f.id}", err=True)
            if len(testspec.flows) > 10:
                typer.echo(f"  ... and {len(testspec.flows) - 10} more", err=True)
            raise typer.Exit(code=1)

    if priority:
        from dazzle.core.ir import FlowPriority

        try:
            priority_enum = FlowPriority(priority)
            flows_to_run = [f for f in flows_to_run if f.priority == priority_enum]
        except ValueError:
            typer.echo(f"Invalid priority: {priority}", err=True)
            typer.echo("Valid priorities: high, medium, low", err=True)
            raise typer.Exit(code=1)

    if tag:
        flows_to_run = [f for f in flows_to_run if tag in f.tags]

    if not flows_to_run:
        typer.echo("No flows match the specified filters.", err=True)
        raise typer.Exit(code=1)

    typer.echo(f"Running {len(flows_to_run)} E2E flows for '{appspec.name}'...")
    typer.echo(f"  • Base URL: {base_url}")
    typer.echo(f"  • API URL: {api_url}")
    typer.echo()

    # Build fixtures dict
    fixtures = {f.id: f for f in testspec.fixtures}

    # Run with Playwright (sync API for CLI)
    results: list[dict[str, Any]] = []
    passed = 0
    failed = 0

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        context = browser.new_context()
        page = context.new_page()
        page.set_default_timeout(timeout)

        # Create adapter
        adapter = DNRAdapter(base_url=base_url, api_url=api_url)

        for flow_spec in flows_to_run:
            if verbose:
                typer.echo(f"Running: {flow_spec.id}...")

            try:
                # Reset test data before each flow
                adapter.reset_sync()

                # Apply preconditions
                if flow_spec.preconditions:
                    if flow_spec.preconditions.fixtures:
                        fixtures_to_seed = [
                            fixtures[fid]
                            for fid in flow_spec.preconditions.fixtures
                            if fid in fixtures
                        ]
                        if fixtures_to_seed:
                            adapter.seed_sync(fixtures_to_seed)

                    if flow_spec.preconditions.authenticated:
                        adapter.authenticate_sync(role=flow_spec.preconditions.user_role)

                    if flow_spec.preconditions.view:
                        url = adapter.resolve_view_url(flow_spec.preconditions.view)
                        page.goto(url)

                # Execute steps
                step_errors: list[str] = []
                for step in flow_spec.steps:
                    try:
                        _execute_step_sync(page, step, adapter, fixtures, timeout)
                    except Exception as e:
                        step_errors.append(f"Step {step.kind.value}: {e}")
                        break

                if step_errors:
                    failed += 1
                    status = "FAIL"
                    error = step_errors[0]
                else:
                    passed += 1
                    status = "PASS"
                    error = None

            except Exception as e:
                failed += 1
                status = "FAIL"
                error = str(e)

            result = {
                "flow_id": flow_spec.id,
                "status": status,
                "error": error,
            }
            results.append(result)

            # Output result
            icon = "✓" if status == "PASS" else "✗"
            color = typer.colors.GREEN if status == "PASS" else typer.colors.RED
            typer.secho(f"  {icon} {flow_spec.id}", fg=color)
            if error and verbose:
                typer.echo(f"    Error: {error}")

        browser.close()

    # Summary
    typer.echo()
    typer.echo(f"Results: {passed} passed, {failed} failed")

    # Output results to file
    if output:
        import json

        output_path = Path(output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(results, indent=2))
        typer.echo(f"Results saved to {output_path}")

    # Exit with error code if any failures
    if failed > 0:
        raise typer.Exit(code=1)


def _execute_step_sync(
    page: Any,
    step: Any,
    adapter: Any,
    fixtures: dict[str, Any],
    timeout: int,
) -> None:
    """Execute a single flow step synchronously."""
    from dazzle.core.ir import FlowStepKind

    if step.kind == FlowStepKind.NAVIGATE:
        if step.target and step.target.startswith("view:"):
            view_id = step.target.split(":", 1)[1]
            url = adapter.resolve_view_url(view_id)
        else:
            url = step.target or adapter.base_url
        page.goto(url)

    elif step.kind == FlowStepKind.FILL:
        if not step.target:
            raise ValueError("Fill step requires target")
        # Build selector from semantic target
        selector = _build_selector(step.target)
        value = _resolve_step_value(step, fixtures)
        page.locator(selector).fill(str(value))

    elif step.kind == FlowStepKind.CLICK:
        if not step.target:
            raise ValueError("Click step requires target")
        selector = _build_selector(step.target)
        page.locator(selector).click()

    elif step.kind == FlowStepKind.WAIT:
        if step.value:
            page.wait_for_timeout(int(step.value))
        elif step.target:
            selector = _build_selector(step.target)
            page.locator(selector).wait_for(state="visible", timeout=timeout)
        else:
            page.wait_for_timeout(1000)

    elif step.kind == FlowStepKind.ASSERT:
        if not step.assertion:
            raise ValueError("Assert step requires assertion")
        _execute_assertion_sync(page, step.assertion, adapter, timeout)

    elif step.kind == FlowStepKind.SNAPSHOT:
        # Just capture state, nothing to do in sync mode
        pass

    else:
        raise ValueError(f"Unknown step kind: {step.kind}")


def _build_selector(target: str) -> str:
    """Build a CSS selector from a semantic target."""
    if target.startswith("view:"):
        view_id = target.split(":", 1)[1]
        return f'[data-dazzle-view="{view_id}"]'
    elif target.startswith("field:"):
        field_id = target.split(":", 1)[1]
        return f'[data-dazzle-field="{field_id}"]'
    elif target.startswith("action:"):
        action_id = target.split(":", 1)[1]
        return f'[data-dazzle-action="{action_id}"]'
    elif target.startswith("entity:"):
        entity_name = target.split(":", 1)[1]
        return f'[data-dazzle-entity="{entity_name}"]'
    elif target.startswith("row:"):
        entity_name = target.split(":", 1)[1]
        return f'[data-dazzle-entity="{entity_name}"]'
    elif target.startswith("message:"):
        target_id = target.split(":", 1)[1]
        return f'[data-dazzle-message="{target_id}"]'
    elif target.startswith("nav:"):
        nav_id = target.split(":", 1)[1]
        return f'[data-dazzle-nav="{nav_id}"]'
    else:
        # Fallback to CSS selector
        return target


def _resolve_step_value(step: Any, fixtures: dict[str, Any]) -> str | int | float | bool:
    """Resolve the value for a fill step."""
    if step.value is not None:
        value: str | int | float | bool = step.value
        return value

    if step.fixture_ref:
        parts = step.fixture_ref.split(".")
        if len(parts) == 2:
            fixture_id, field_name = parts
            if fixture_id in fixtures:
                fixture = fixtures[fixture_id]
                if field_name in fixture.data:
                    result: str | int | float | bool = fixture.data[field_name]
                    return result

    raise ValueError("Could not resolve value for step")


def _execute_assertion_sync(
    page: Any,
    assertion: Any,
    adapter: Any,
    timeout: int,
) -> None:
    """Execute an assertion synchronously."""
    from playwright.sync_api import expect

    from dazzle.core.ir import FlowAssertionKind

    if assertion.kind == FlowAssertionKind.VISIBLE:
        target = assertion.target or ""
        selector = _build_selector(target)
        expect(page.locator(selector)).to_be_visible(timeout=timeout)

    elif assertion.kind == FlowAssertionKind.NOT_VISIBLE:
        target = assertion.target or ""
        selector = _build_selector(target)
        expect(page.locator(selector)).to_be_hidden(timeout=timeout)

    elif assertion.kind == FlowAssertionKind.TEXT_CONTAINS:
        expect(page.locator("body")).to_contain_text(str(assertion.expected), timeout=timeout)

    elif assertion.kind == FlowAssertionKind.ENTITY_EXISTS:
        # Check via API
        entity_name = assertion.target or ""
        if entity_name.startswith("entity:"):
            entity_name = entity_name.split(":", 1)[1]
        count = adapter.get_entity_count_sync(entity_name)
        if count == 0:
            raise AssertionError(f"Expected {entity_name} to exist, but count is 0")

    elif assertion.kind == FlowAssertionKind.ENTITY_NOT_EXISTS:
        entity_name = assertion.target or ""
        if entity_name.startswith("entity:"):
            entity_name = entity_name.split(":", 1)[1]
        count = adapter.get_entity_count_sync(entity_name)
        if count > 0:
            raise AssertionError(f"Expected {entity_name} to not exist, but count is {count}")

    elif assertion.kind == FlowAssertionKind.VALIDATION_ERROR:
        target = assertion.target or ""
        if target.startswith("field:"):
            target = target.split(":", 1)[1]
        selector = f'[data-dazzle-message="{target}"][data-dazzle-message-kind="validation"]'
        expect(page.locator(selector)).to_be_visible(timeout=timeout)

    elif assertion.kind == FlowAssertionKind.REDIRECTS_TO:
        target = assertion.target or ""
        if target.startswith("view:"):
            view_id = target.split(":", 1)[1]
            selector = f'[data-dazzle-view="{view_id}"]'
            expect(page.locator(selector)).to_be_visible(timeout=timeout)

    elif assertion.kind == FlowAssertionKind.COUNT:
        entity_name = assertion.target or ""
        if entity_name.startswith("entity:"):
            entity_name = entity_name.split(":", 1)[1]
        expected = int(assertion.expected) if assertion.expected is not None else 0
        count = adapter.get_entity_count_sync(entity_name)
        if count != expected:
            raise AssertionError(f"Expected {entity_name} count to be {expected}, but was {count}")

    elif assertion.kind == FlowAssertionKind.FIELD_VALUE:
        target = assertion.target or ""
        if target.startswith("field:"):
            target = target.split(":", 1)[1]
        selector = f'[data-dazzle-field="{target}"]'
        expect(page.locator(selector)).to_have_value(str(assertion.expected), timeout=timeout)

    else:
        raise ValueError(f"Unknown assertion kind: {assertion.kind}")


@test_app.command("list")
def test_list(
    manifest: str = typer.Option("dazzle.toml", "--manifest", "-m"),
    priority: str = typer.Option(
        None,
        "--priority",
        "-p",
        help="Filter by priority (high, medium, low)",
    ),
    tag: str = typer.Option(
        None,
        "--tag",
        "-t",
        help="Filter by tag",
    ),
) -> None:
    """
    List available E2E test flows.

    Examples:
        dazzle test list                    # List all flows
        dazzle test list --priority high    # List high-priority flows
        dazzle test list --tag crud         # List flows tagged 'crud'
    """
    try:
        from dazzle.testing.testspec_generator import generate_e2e_testspec
    except ImportError as e:
        typer.echo(f"E2E testing module not available: {e}", err=True)
        raise typer.Exit(code=1)

    # Load AppSpec
    manifest_path = Path(manifest).resolve()
    root = manifest_path.parent

    try:
        mf = load_manifest(manifest_path)
        dsl_files = discover_dsl_files(root, mf)
        modules = parse_modules(dsl_files)
        appspec = build_appspec(modules, mf.project_root)
    except (ParseError, DazzleError) as e:
        typer.echo(f"Error loading spec: {e}", err=True)
        raise typer.Exit(code=1)

    # Generate E2ETestSpec
    testspec = generate_e2e_testspec(appspec)

    # Include any DSL-defined flows
    if appspec.e2e_flows:
        testspec.flows.extend(appspec.e2e_flows)

    # Filter
    flows = testspec.flows

    if priority:
        from dazzle.core.ir import FlowPriority

        try:
            priority_enum = FlowPriority(priority)
            flows = [f for f in flows if f.priority == priority_enum]
        except ValueError:
            typer.echo(f"Invalid priority: {priority}", err=True)
            raise typer.Exit(code=1)

    if tag:
        flows = [f for f in flows if tag in f.tags]

    # Display
    typer.echo(f"E2E Flows for '{appspec.name}' ({len(flows)} total):\n")

    for f in flows:
        priority_color = {
            "high": typer.colors.RED,
            "medium": typer.colors.YELLOW,
            "low": typer.colors.CYAN,
        }.get(f.priority.value, typer.colors.WHITE)

        typer.echo(f"  {f.id}")
        typer.secho(f"    Priority: {f.priority.value}", fg=priority_color)
        if f.description:
            typer.echo(f"    Description: {f.description}")
        if f.tags:
            typer.echo(f"    Tags: {', '.join(f.tags)}")
        typer.echo()
