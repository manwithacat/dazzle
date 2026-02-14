"""
Semantic E2E testing CLI commands.

Commands for generating and running E2E tests for Dazzle applications.
"""

import os
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
    help=(
        "Testing commands for Dazzle apps. Tier 1: 'dsl-run' (API). "
        "Tier 2: 'playwright' (scripted UI). Tier 3: 'agent' (LLM-powered)."
    ),
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
    - State machine transition flows (valid/invalid transitions) [v0.13.0]
    - Computed field verification flows [v0.13.0]
    - Access control flows (permission granted/denied) [v0.13.0]
    - Reference integrity flows (valid/invalid refs) [v0.13.0]
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
        help="Base URL of the running application (ignored with --auto-server)",
    ),
    api_url: str = typer.Option(
        "http://localhost:8000",
        "--api-url",
        help="Base URL of the API server (ignored with --auto-server)",
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
    auto_server: bool = typer.Option(
        True,
        "--auto-server/--no-auto-server",
        help="Automatically start and stop DNR server (default: True)",
    ),
) -> None:
    """
    Run E2E tests using Playwright.

    By default, automatically starts the DNR server, runs tests, and stops the server.
    Use --no-auto-server to require a manually started server.

    Examples:
        dazzle test run                             # Auto-start server, run all tests
        dazzle test run --priority high             # Run high-priority only
        dazzle test run --tag crud                  # Run tests tagged 'crud'
        dazzle test run --flow Task_create_valid    # Run specific flow
        dazzle test run --headed                    # Show browser window
        dazzle test run --no-auto-server            # Require running server
    """
    # Check for playwright
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        typer.echo("Playwright not installed. Install with:", err=True)
        typer.echo("  pip install playwright", err=True)
        typer.echo("  playwright install chromium", err=True)
        raise typer.Exit(code=1)

    # If auto_server is enabled, use E2ERunner for full lifecycle management
    if auto_server:
        from dazzle.testing.e2e_runner import E2ERunner, E2ERunOptions, format_e2e_report

        manifest_path = Path(manifest).resolve()
        root = manifest_path.parent

        runner = E2ERunner(root)

        # Check Playwright browsers
        playwright_ok, playwright_msg = runner.ensure_playwright()
        if not playwright_ok:
            typer.echo(playwright_msg, err=True)
            raise typer.Exit(code=1)

        options = E2ERunOptions(
            headless=headless,
            priority=priority,
            tag=tag,
            flow_id=flow,
            timeout=timeout,
        )

        if verbose:
            typer.echo("Starting E2E test run with auto-server...")
            typer.echo(f"  Project: {root}")

        result = runner.run_all(options)

        # Output results
        if verbose:
            typer.echo(format_e2e_report(result))
        else:
            if result.error:
                typer.secho(f"ERROR: {result.error}", fg=typer.colors.RED, err=True)
            else:
                for flow_result in result.flows:
                    icon = "✓" if flow_result.status == "passed" else "✗"
                    color = (
                        typer.colors.GREEN if flow_result.status == "passed" else typer.colors.RED
                    )
                    typer.secho(f"  {icon} {flow_result.flow_id}", fg=color)
                    if flow_result.error and verbose:
                        typer.echo(f"    Error: {flow_result.error}")

                typer.echo()
                typer.echo(f"Results: {result.passed} passed, {result.failed} failed")

        # Output to file if requested
        if output:
            import json

            output_path = Path(output)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(json.dumps(result.to_dict(), indent=2))
            typer.echo(f"Results saved to {output_path}")

        # Exit with appropriate code
        if result.error or result.failed > 0:
            raise typer.Exit(code=1)
        return

    # Legacy mode: --no-auto-server requires running server
    try:
        from dazzle.testing.testspec_generator import generate_e2e_testspec
        from dazzle_e2e.adapters.dazzle_adapter import DazzleAdapter
    except ImportError as e:
        typer.echo(f"E2E testing modules not available: {e}", err=True)
        typer.echo("Note: Use --auto-server (default) for built-in server management", err=True)
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
        adapter = DazzleAdapter(base_url=base_url, api_url=api_url)

        for flow_spec in flows_to_run:
            if verbose:
                typer.echo(f"Running: {flow_spec.id}...")

            try:
                # Reset test data before each flow
                adapter.reset_sync()

                # Apply preconditions
                if flow_spec.preconditions:
                    if flow_spec.preconditions.fixtures:
                        fixtures_to_seed = _resolve_fixture_deps(
                            flow_spec.preconditions.fixtures,
                            fixtures,
                        )
                        if fixtures_to_seed:
                            adapter.seed_sync(fixtures_to_seed)

                    if flow_spec.preconditions.authenticated:
                        adapter.authenticate_sync(role=flow_spec.preconditions.user_role)

                    if flow_spec.preconditions.view:
                        url = adapter.resolve_view_url(flow_spec.preconditions.view)
                        page.goto(url)

                # Execute steps
                step_errors: list[str] = []
                created_ids = getattr(adapter, "_fixture_ids", None)
                for step in flow_spec.steps:
                    try:
                        _execute_step_sync(
                            page,
                            step,
                            adapter,
                            fixtures,
                            timeout,
                            created_ids,
                        )
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

            test_result: dict[str, Any] = {
                "flow_id": flow_spec.id,
                "status": status,
                "error": error,
            }
            results.append(test_result)

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


def _resolve_fixture_deps(
    fixture_ids: list[str],
    all_fixtures: dict[str, Any],
) -> list[Any]:
    """Resolve fixture dependencies, returning ordered list with deps first."""
    resolved: list[str] = []
    seen: set[str] = set()

    def _add(fid: str) -> None:
        if fid in seen or fid not in all_fixtures:
            return
        seen.add(fid)
        fixture = all_fixtures[fid]
        # Add ref dependencies first
        for ref_fixture_id in getattr(fixture, "refs", {}).values():
            _add(ref_fixture_id)
        resolved.append(fid)

    for fid in fixture_ids:
        _add(fid)

    return [all_fixtures[fid] for fid in resolved]


def _execute_step_sync(
    page: Any,
    step: Any,
    adapter: Any,
    fixtures: dict[str, Any],
    timeout: int,
    created_ids: dict[str, str] | None = None,
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
        page.wait_for_load_state("networkidle")

    elif step.kind == FlowStepKind.FILL:
        if not step.target:
            raise ValueError("Fill step requires target")
        # Build selector from semantic target
        selector = _build_selector(step.target)
        value = _resolve_step_value(step, fixtures, created_ids)

        # Use appropriate method based on field type
        field_type = getattr(step, "field_type", None)
        if field_type == "enum":
            # Enum/dropdown fields use select_option
            page.locator(selector).select_option(str(value))
        elif field_type == "ref":
            # Ref fields may be <select> or <input> depending on template
            el = page.locator(selector).first
            tag = el.evaluate("e => e.tagName.toLowerCase()")
            if tag == "select":
                el.select_option(str(value))
            else:
                el.fill(str(value))
        elif field_type == "bool":
            # Checkbox fields use set_checked
            page.locator(selector).set_checked(bool(value))
        else:
            # Text/number/other fields use fill
            page.locator(selector).fill(str(value))

    elif step.kind == FlowStepKind.CLICK:
        if not step.target:
            raise ValueError("Click step requires target")
        selector = _build_selector(step.target)
        # Use .first to handle multiple matches (e.g., header button + form button)
        page.locator(selector).first.click()
        # Wait for any navigation or network activity to settle
        page.wait_for_load_state("networkidle")

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
        # Strip Entity. prefix if present
        if "." in field_id:
            field_id = field_id.split(".", 1)[1]
        return f'[data-dazzle-field="{field_id}"], [name="{field_id}"]'
    elif target.startswith("action:"):
        action_id = target.split(":", 1)[1]
        # For save/create/update/submit actions, use a flexible selector
        if "." in action_id:
            entity, action = action_id.split(".", 1)
            if action in ("save", "create", "submit"):
                return (
                    f'[data-dazzle-action="{action_id}"],'
                    f' [data-dazzle-action="{entity}.create"],'
                    f' button[type="submit"]'
                )
            if action == "update":
                return f'[data-dazzle-action="{action_id}"], button[type="submit"]'
            if action == "delete":
                return f'[data-dazzle-action="{action_id}"], button:has-text("Delete")'
            if action == "edit":
                return f'[data-dazzle-action="{action_id}"], a:has-text("Edit")'
            return f'[data-dazzle-action="{action_id}"], [data-dazzle-action="{action}"]'
        return f'[data-dazzle-action="{action_id}"]'
    elif target.startswith("entity:"):
        entity_name = target.split(":", 1)[1]
        return f'[data-dazzle-entity="{entity_name}"]'
    elif target.startswith("row:"):
        entity_name = target.split(":", 1)[1]
        return f'[data-dazzle-row="{entity_name}"], tbody tr'
    elif target.startswith("message:"):
        target_id = target.split(":", 1)[1]
        return f'[data-dazzle-message="{target_id}"]'
    elif target.startswith("nav:"):
        nav_id = target.split(":", 1)[1]
        return f'[data-dazzle-nav="{nav_id}"]'
    else:
        # Fallback to CSS selector
        return target


def _resolve_step_value(
    step: Any,
    fixtures: dict[str, Any],
    created_ids: dict[str, str] | None = None,
) -> str | int | float | bool:
    """Resolve the value for a fill step."""
    if step.value is not None:
        value: str | int | float | bool = step.value
        return value

    if step.fixture_ref:
        parts = step.fixture_ref.split(".")
        if len(parts) == 2:
            fixture_id, field_name = parts
            # Check created IDs first (for .id lookups after seeding)
            if field_name == "id" and created_ids and fixture_id in created_ids:
                return created_ids[fixture_id]
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

    # v0.13.0 assertion kinds
    elif assertion.kind == FlowAssertionKind.STATE_TRANSITION_ALLOWED:
        # Check that the entity's status field matches expected value
        # After transition, verify via API count or page content
        target = assertion.target or ""  # e.g., "Task.status"
        expected_state = str(assertion.expected) if assertion.expected else ""
        if "." in target:
            entity_name, field_name = target.split(".", 1)
        else:
            entity_name, field_name = target, "status"
        # Verify via API snapshot - more reliable than page content
        try:
            snapshot = adapter.snapshot_sync()
            entities_data = snapshot.get("entities", {}).get(entity_name, [])
            found = any(str(e.get(field_name, "")) == expected_state for e in entities_data)
            if not found:
                raise AssertionError(
                    f"Expected {entity_name}.{field_name} = '{expected_state}', "
                    f"but no matching entity found"
                )
        except AttributeError:
            # Fallback to page text if adapter has no snapshot_sync
            expect(page.locator("body")).to_contain_text(expected_state, timeout=timeout)

    elif assertion.kind == FlowAssertionKind.STATE_TRANSITION_BLOCKED:
        # Check that the entity's status field still has the original value
        target = assertion.target or ""  # e.g., "Task.status"
        original_state = str(assertion.expected) if assertion.expected else ""
        if "." in target:
            entity_name, field_name = target.split(".", 1)
        else:
            entity_name, field_name = target, "status"
        try:
            snapshot = adapter.snapshot_sync()
            entities_data = snapshot.get("entities", {}).get(entity_name, [])
            found = any(str(e.get(field_name, "")) == original_state for e in entities_data)
            if not found:
                raise AssertionError(
                    f"Expected {entity_name}.{field_name} = '{original_state}' "
                    f"(unchanged), but no matching entity found"
                )
        except AttributeError:
            expect(page.locator("body")).to_contain_text(original_state, timeout=timeout)

    elif assertion.kind == FlowAssertionKind.COMPUTED_VALUE:
        # Check that computed field has expected value
        target = assertion.target or ""
        if target.startswith("field:"):
            target = target.split(":", 1)[1]
        selector = f'[data-dazzle-field="{target}"][data-dazzle-computed="true"]'
        # For computed fields, we check the text content
        if assertion.expected is not None:
            expect(page.locator(selector)).to_contain_text(str(assertion.expected), timeout=timeout)
        else:
            expect(page.locator(selector)).to_be_visible(timeout=timeout)

    elif assertion.kind == FlowAssertionKind.PERMISSION_GRANTED:
        # Check that operation was allowed (form/action is accessible)
        target = assertion.target or ""  # e.g., "Document.create"
        # Should NOT see a permission denied message
        selector = f'[data-dazzle-message="{target}"][data-dazzle-message-kind="permission_denied"]'
        expect(page.locator(selector)).to_be_hidden(timeout=timeout)

    elif assertion.kind == FlowAssertionKind.PERMISSION_DENIED:
        # Check that operation was denied (403 or access denied message)
        target = assertion.target or ""  # e.g., "Document.create"
        # Should see a permission denied message or be redirected to login
        denied_selector = (
            f'[data-dazzle-message="{target}"][data-dazzle-message-kind="permission_denied"]'
        )
        auth_modal_selector = "[data-dazzle-auth-modal]"
        # Either permission denied message OR auth modal should be visible
        combined = f"{denied_selector}, {auth_modal_selector}"
        expect(page.locator(combined).first).to_be_visible(timeout=timeout)

    elif assertion.kind == FlowAssertionKind.REF_VALID:
        # Check that reference was accepted (no validation error)
        target = assertion.target or ""  # e.g., "Task.project_id"
        error_selector = f'[data-dazzle-message="{target}"][data-dazzle-message-kind="validation"]'
        expect(page.locator(error_selector)).to_be_hidden(timeout=timeout)

    elif assertion.kind == FlowAssertionKind.REF_INVALID:
        # Check that invalid reference shows validation error
        target = assertion.target or ""  # e.g., "Task.project_id"
        error_selector = f'[data-dazzle-message="{target}"][data-dazzle-message-kind="validation"]'
        expect(page.locator(error_selector)).to_be_visible(timeout=timeout)

    # Auth-related assertion kinds (v0.3.3)
    elif assertion.kind == FlowAssertionKind.IS_AUTHENTICATED:
        # Check for authenticated user indicator
        selector = '[data-dazzle-auth="authenticated"]'
        expect(page.locator(selector)).to_be_visible(timeout=timeout)

    elif assertion.kind == FlowAssertionKind.IS_NOT_AUTHENTICATED:
        # Check that user is not authenticated (login button visible, etc.)
        selector = '[data-dazzle-auth="unauthenticated"]'
        expect(page.locator(selector)).to_be_visible(timeout=timeout)

    elif assertion.kind == FlowAssertionKind.LOGIN_SUCCEEDED:
        # Check that login succeeded (should be on dashboard or no error)
        error_selector = '[data-dazzle-message-kind="auth_error"]'
        expect(page.locator(error_selector)).to_be_hidden(timeout=timeout)

    elif assertion.kind == FlowAssertionKind.LOGIN_FAILED:
        # Check that login failed (error message visible)
        error_selector = '[data-dazzle-message-kind="auth_error"]'
        expect(page.locator(error_selector)).to_be_visible(timeout=timeout)

    elif assertion.kind == FlowAssertionKind.ROUTE_PROTECTED:
        # Check that accessing route shows auth modal or redirects
        auth_modal_selector = "[data-dazzle-auth-modal]"
        expect(page.locator(auth_modal_selector)).to_be_visible(timeout=timeout)

    elif assertion.kind == FlowAssertionKind.HAS_PERSONA:
        # Check that user has specific persona/role
        expected_persona = assertion.expected or ""
        selector = f'[data-dazzle-persona="{expected_persona}"]'
        expect(page.locator(selector)).to_be_visible(timeout=timeout)

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


# ============================================================================
# Feedback Loop Commands (v0.13.0)
# ============================================================================

feedback_app = typer.Typer(
    help="Test feedback loop commands for tracking regressions and corrections.",
    no_args_is_help=True,
)
test_app.add_typer(feedback_app, name="feedback")


@feedback_app.command("record-regression")
def feedback_record_regression(
    test_id: str = typer.Option(..., "--test-id", "-t", help="ID of the failing test"),
    test_path: str = typer.Option(..., "--test-path", "-p", help="Path to the test file"),
    failure_message: str = typer.Option(..., "--message", "-m", help="Error message from the test"),
    failure_type: str = typer.Option(
        "assertion",
        "--type",
        help="Type: assertion, timeout, crash, flaky, infrastructure, "
        "selector_not_found, navigation_error, auth_error",
    ),
    example: str = typer.Option(..., "--example", "-e", help="Name of the example project"),
    manifest: str = typer.Option("dazzle.toml", "--manifest"),
) -> None:
    """
    Record a test regression for tracking.

    Examples:
        dazzle test feedback record-regression -t TD-001 -p tests/e2e/test_crud.py \\
            -m "Element not found" --type selector_not_found -e support_tickets
    """
    from dazzle.testing.feedback import FailureType, record_regression

    manifest_path = Path(manifest).resolve()
    root = manifest_path.parent

    try:
        ft = FailureType(failure_type)
    except ValueError:
        typer.echo(f"Invalid failure type: {failure_type}", err=True)
        typer.echo(f"Valid types: {', '.join(f.value for f in FailureType)}", err=True)
        raise typer.Exit(code=1)

    regression = record_regression(
        project_root=root,
        test_id=test_id,
        test_path=test_path,
        failure_message=failure_message,
        failure_type=ft,
        example_name=example,
    )

    typer.secho(f"Recorded regression: {regression.regression_id}", fg=typer.colors.GREEN)
    typer.echo(f"  Test: {test_id}")
    typer.echo(f"  Type: {failure_type}")
    typer.echo(f"  Status: {regression.status.value}")


@feedback_app.command("add-correction")
def feedback_add_correction(
    regression_id: str = typer.Option(
        ..., "--regression", "-r", help="Regression ID being fixed (e.g., REG-001)"
    ),
    problem: str = typer.Option(..., "--problem", "-p", help="Description of what was wrong"),
    change_type: str = typer.Option(
        "test_fix",
        "--type",
        "-t",
        help="Type: test_fix, dsl_fix, prompt_fix, infrastructure",
    ),
    files: str = typer.Option(None, "--files", "-f", help="Comma-separated list of files changed"),
    pattern: str = typer.Option(
        None, "--pattern", help="Reusable pattern identified from this fix"
    ),
    prompt_improvement: str = typer.Option(
        None, "--prompt", help="Suggested improvement to test design prompt"
    ),
    manifest: str = typer.Option("dazzle.toml", "--manifest"),
) -> None:
    """
    Record a correction that fixed a regression.

    Examples:
        dazzle test feedback add-correction -r REG-001 \\
            -p "Test assumed button text 'Save', actual was 'Submit'" \\
            --type test_fix \\
            -f "tests/e2e/test_crud.py" \\
            --pattern "Prefer semantic selectors over text content"
    """
    from dazzle.testing.feedback import ChangeType, record_correction

    manifest_path = Path(manifest).resolve()
    root = manifest_path.parent

    try:
        ct = ChangeType(change_type)
    except ValueError:
        typer.echo(f"Invalid change type: {change_type}", err=True)
        typer.echo(f"Valid types: {', '.join(c.value for c in ChangeType)}", err=True)
        raise typer.Exit(code=1)

    files_list = [f.strip() for f in files.split(",")] if files else []

    correction = record_correction(
        project_root=root,
        regression_id=regression_id,
        problem_description=problem,
        change_type=ct,
        files_changed=files_list,
        pattern_identified=pattern,
        prompt_improvement=prompt_improvement,
    )

    typer.secho(f"Recorded correction: {correction.correction_id}", fg=typer.colors.GREEN)
    typer.echo(f"  For regression: {regression_id}")
    typer.echo(f"  Change type: {change_type}")
    if pattern:
        typer.secho(f"  Pattern: {pattern}", fg=typer.colors.CYAN)
    if prompt_improvement:
        typer.secho(f"  Prompt suggestion: {prompt_improvement}", fg=typer.colors.YELLOW)


@feedback_app.command("list-regressions")
def feedback_list_regressions(
    status: str = typer.Option(
        None, "--status", "-s", help="Filter by status: open, investigating, resolved, wontfix"
    ),
    manifest: str = typer.Option("dazzle.toml", "--manifest"),
) -> None:
    """
    List recorded regressions.

    Examples:
        dazzle test feedback list-regressions
        dazzle test feedback list-regressions --status open
    """
    from dazzle.testing.feedback import RegressionStatus, get_regressions_by_status

    manifest_path = Path(manifest).resolve()
    root = manifest_path.parent

    status_filter = None
    if status:
        try:
            status_filter = RegressionStatus(status)
        except ValueError:
            typer.echo(f"Invalid status: {status}", err=True)
            raise typer.Exit(code=1)

    regressions = get_regressions_by_status(root, status_filter)

    if not regressions:
        typer.echo("No regressions found.")
        return

    typer.echo(f"Regressions ({len(regressions)} total):\n")

    status_colors = {
        "open": typer.colors.RED,
        "investigating": typer.colors.YELLOW,
        "resolved": typer.colors.GREEN,
        "wontfix": typer.colors.BRIGHT_BLACK,
    }

    for reg in regressions:
        color = status_colors.get(reg.status.value, typer.colors.WHITE)
        typer.echo(f"  {reg.regression_id}")
        typer.echo(f"    Test: {reg.test_id}")
        typer.secho(f"    Status: {reg.status.value}", fg=color)
        typer.echo(f"    Type: {reg.failure_type.value}")
        typer.echo(f"    Example: {reg.example_name}")
        if reg.root_cause:
            typer.echo(f"    Root cause: {reg.root_cause}")
        typer.echo()


@feedback_app.command("summary")
def feedback_summary(
    manifest: str = typer.Option("dazzle.toml", "--manifest"),
) -> None:
    """
    Show feedback loop summary statistics.

    Examples:
        dazzle test feedback summary
    """
    from dazzle.testing.feedback import get_feedback_summary

    manifest_path = Path(manifest).resolve()
    root = manifest_path.parent

    summary = get_feedback_summary(root)

    typer.secho("Feedback Loop Summary", bold=True)
    typer.echo()

    typer.echo("Regressions:")
    typer.echo(f"  Total: {summary.total_regressions}")
    if summary.open_regressions > 0:
        typer.secho(f"  Open: {summary.open_regressions}", fg=typer.colors.RED)
    else:
        typer.echo(f"  Open: {summary.open_regressions}")
    typer.secho(f"  Resolved: {summary.resolved_regressions}", fg=typer.colors.GREEN)
    typer.echo()

    typer.echo("Corrections:")
    typer.echo(f"  Total: {summary.total_corrections}")
    typer.secho(f"  Patterns identified: {summary.patterns_identified}", fg=typer.colors.CYAN)
    typer.secho(
        f"  Prompt improvements suggested: {summary.prompt_improvements_suggested}",
        fg=typer.colors.YELLOW,
    )
    typer.echo()

    if summary.top_failure_types:
        typer.echo("Top failure types:")
        for ft, count in summary.top_failure_types:
            typer.echo(f"  {ft}: {count}")
        typer.echo()

    if summary.prompt_versions:
        typer.echo("Prompt versions by tool:")
        for tool, count in summary.prompt_versions.items():
            typer.echo(f"  {tool}: {count} versions")


@feedback_app.command("patterns")
def feedback_patterns(
    manifest: str = typer.Option("dazzle.toml", "--manifest"),
) -> None:
    """
    List identified patterns from corrections.

    These are reusable insights that can help improve test design.

    Examples:
        dazzle test feedback patterns
    """
    from dazzle.testing.feedback import get_pattern_insights

    manifest_path = Path(manifest).resolve()
    root = manifest_path.parent

    patterns = get_pattern_insights(root)

    if not patterns:
        typer.echo("No patterns identified yet.")
        typer.echo("Patterns are recorded when adding corrections with --pattern flag.")
        return

    typer.secho("Identified Patterns", bold=True)
    typer.echo()

    for i, pattern in enumerate(patterns, 1):
        typer.secho(f"  {i}. {pattern}", fg=typer.colors.CYAN)


@feedback_app.command("prompt-suggestions")
def feedback_prompt_suggestions(
    manifest: str = typer.Option("dazzle.toml", "--manifest"),
) -> None:
    """
    List suggested prompt improvements from corrections.

    These suggestions can help improve LLM test design quality.

    Examples:
        dazzle test feedback prompt-suggestions
    """
    from dazzle.testing.feedback import get_prompt_improvements

    manifest_path = Path(manifest).resolve()
    root = manifest_path.parent

    suggestions = get_prompt_improvements(root)

    if not suggestions:
        typer.echo("No prompt improvements suggested yet.")
        typer.echo("Suggestions are recorded when adding corrections with --prompt flag.")
        return

    typer.secho("Prompt Improvement Suggestions", bold=True)
    typer.echo()

    for i, suggestion in enumerate(suggestions, 1):
        typer.secho(f"  {i}. {suggestion}", fg=typer.colors.YELLOW)


# ============================================================================
# DSL-Driven Test Commands (v0.18.0)
# ============================================================================


@test_app.command("dsl-generate")
def dsl_generate(
    manifest: str = typer.Option("dazzle.toml", "--manifest", "-m"),
    output: str = typer.Option(
        None,
        "--output",
        "-o",
        help="Output directory for generated tests (default: .dazzle/tests)",
    ),
    format: str = typer.Option(
        "json",
        "--format",
        "-f",
        help="Output format: json (default) or yaml",
    ),
) -> None:
    """
    Generate tests from DSL/AppSpec definitions.

    This command analyzes your DSL files and generates comprehensive tests
    covering CRUD operations, state machines, personas, validation, and more.

    Unlike Playwright E2E tests, these tests run against the API without
    requiring a browser. They're faster and can be run in CI/CD pipelines.

    Examples:
        dazzle test dsl-generate                          # Generate to .dazzle/tests
        dazzle test dsl-generate -o tests/dsl             # Custom output directory
        dazzle test dsl-generate --format yaml            # YAML output
    """
    try:
        from dazzle.testing.dsl_test_generator import (
            generate_tests_from_dsl,
            save_generated_tests,
        )
    except ImportError as e:
        typer.echo(f"DSL testing module not available: {e}", err=True)
        raise typer.Exit(code=1)

    # Load AppSpec
    manifest_path = Path(manifest).resolve()
    root = manifest_path.parent

    if not (root / "dazzle.toml").exists():
        typer.echo(f"No dazzle.toml found in {root}", err=True)
        raise typer.Exit(code=1)

    # Generate tests (the function handles loading appspec internally)
    typer.echo(f"Generating tests from DSL in {root}...")

    try:
        from dazzle.cli.activity import cli_activity

        with cli_activity(root, "dsl_test", "generate"):
            test_suite = generate_tests_from_dsl(root)
    except Exception as e:
        typer.echo(f"Error generating tests: {e}", err=True)
        raise typer.Exit(code=1)

    # Show coverage
    coverage = test_suite.coverage
    typer.echo()
    typer.secho("Coverage Analysis:", bold=True)
    typer.echo(f"  • Entities: {len(coverage.entities_covered)}/{coverage.entities_total}")
    typer.echo(
        f"  • State Machines: {len(coverage.state_machines_covered)}"
        f"/{coverage.state_machines_total}"
    )
    typer.echo(f"  • Personas: {len(coverage.personas_covered)}/{coverage.personas_total}")
    typer.echo(f"  • Workspaces: {len(coverage.workspaces_covered)}/{coverage.workspaces_total}")
    if coverage.events_total > 0:
        typer.echo(f"  • Events: {len(coverage.events_covered)}/{coverage.events_total}")
    if coverage.processes_total > 0:
        typer.echo(f"  • Processes: {len(coverage.processes_covered)}/{coverage.processes_total}")
    typer.echo()

    # Show test categories (from tags)
    typer.secho("Generated Tests:", bold=True)
    categories: dict[str, int] = {}
    for design in test_suite.designs:
        # Get category from tags (first tag that's not generic)
        tags = design.get("tags", [])
        cat = next((t for t in tags if t not in ("generated", "dsl-derived")), "other")
        categories[cat] = categories.get(cat, 0) + 1

    for cat, count in sorted(categories.items()):
        typer.echo(f"  • {cat}: {count} tests")
    typer.echo(f"  Total: {len(test_suite.designs)} tests")
    typer.echo()

    # Save tests using the module's save function
    output_file = save_generated_tests(root, test_suite)
    typer.secho(f"Tests saved to {output_file}", fg=typer.colors.GREEN)


@test_app.command("tier2-generate")
def tier2_generate(
    manifest: str = typer.Option("dazzle.toml", "--manifest", "-m"),
    output: str = typer.Option(
        None,
        "--output",
        "-o",
        help="Output directory for generated tests (default: tests/e2e)",
    ),
    scenario: str = typer.Option(
        None,
        "--scenario",
        "-s",
        help="Default scenario to use for state setup",
    ),
) -> None:
    """
    [TIER 2] Generate Playwright tests from DSL surfaces.

    This command analyzes your DSL surfaces and generates deterministic
    Playwright test scripts using the semantic DOM contract (data-dazzle-*
    attributes) for reliable element selection.

    Unlike Tier 1 API tests, these tests run in a browser and verify the
    full UI interaction flow. Unlike Tier 3 agent tests, these are scripted
    and don't use LLM interpretation.

    Generated tests:
    - CRUD flows for surfaces (create, edit, view, list modes)
    - Delete confirmation flows
    - Scenario-based state setup via dev control plane

    Selectors use data-dazzle-* attributes:
    - data-dazzle-view="surface_name"
    - data-dazzle-field="field_name"
    - data-dazzle-action="Entity.action"
    - data-dazzle-table="EntityName"
    - data-dazzle-row="row_id"

    Examples:
        dazzle test tier2-generate                    # Generate to tests/e2e
        dazzle test tier2-generate -o my-tests        # Custom output directory
        dazzle test tier2-generate -s active_tickets  # Use specific scenario
    """
    try:
        from dazzle.testing.tier2_playwright import generate_tier2_tests_for_app
    except ImportError as e:
        typer.echo(f"Tier 2 testing module not available: {e}", err=True)
        raise typer.Exit(code=1)

    # Load AppSpec
    manifest_path = Path(manifest).resolve()
    root = manifest_path.parent

    if not (root / "dazzle.toml").exists():
        typer.echo(f"No dazzle.toml found in {root}", err=True)
        raise typer.Exit(code=1)

    # Determine output directory
    output_dir = Path(output) if output else None

    typer.echo(f"Generating Tier 2 Playwright tests from DSL in {root}...")

    try:
        output_file = generate_tier2_tests_for_app(root, output_dir, scenario)
        typer.secho(f"Tier 2 tests generated: {output_file}", fg=typer.colors.GREEN)
        typer.echo()
        typer.echo("Run tests with:")
        typer.echo(f"  pytest {output_file} -m tier2")
    except Exception as e:
        typer.echo(f"Error generating tests: {e}", err=True)
        raise typer.Exit(code=1)


@test_app.command("dsl-run")
def dsl_run(
    manifest: str = typer.Option("dazzle.toml", "--manifest", "-m"),
    regenerate: bool = typer.Option(
        False,
        "--regenerate",
        "-r",
        help="Regenerate tests from DSL before running",
    ),
    output: str = typer.Option(
        None,
        "--output",
        "-o",
        help="Output file for test results JSON",
    ),
    timeout: int = typer.Option(
        30,
        "--timeout",
        "-t",
        help="Server startup timeout in seconds (increase for large projects)",
    ),
    base_url: str = typer.Option(
        None,
        "--base-url",
        "-b",
        help="Base URL of a running server (local or remote). Skips auto-starting a local server.",
    ),
    email: str = typer.Option(
        None,
        "--email",
        help="Test user email for remote server auth. Overrides DAZZLE_TEST_EMAIL.",
    ),
    password: str = typer.Option(
        None,
        "--password",
        help="Test user password for remote server auth. Overrides DAZZLE_TEST_PASSWORD.",
    ),
    format: str = typer.Option(
        "table",
        "--format",
        "-f",
        help="Output format: table (default) or json",
    ),
) -> None:
    """
    [Tier 1] Run API-based tests against a DNR server.

    Fast, deterministic tests generated from your DSL. Use this for:
    - CRUD operations (create, read, update, delete)
    - Field validation
    - API response checks
    - State machine transitions

    Tests are auto-generated and cached for performance. No browser required.

    By default, starts a local server automatically. Use --base-url to target
    a remote deployment instead.

    Examples:
        dazzle test dsl-run                    # Run all tests (local server)
        dazzle test dsl-run --regenerate       # Regenerate and run
        dazzle test dsl-run -o results.json    # Save results to file
        dazzle test dsl-run --timeout 120      # Allow 2 min for server startup
        dazzle test dsl-run --format json      # JSON output for CI
        dazzle test dsl-run --base-url https://staging.example.com  # Remote server
        dazzle test dsl-run -b https://staging.example.com --email user@example.com --password secret
    """
    import json

    try:
        from dazzle.testing.unified_runner import UnifiedTestRunner
    except ImportError as e:
        typer.echo(f"DSL testing module not available: {e}", err=True)
        raise typer.Exit(code=1)

    manifest_path = Path(manifest).resolve()
    root = manifest_path.parent

    if not (root / "dazzle.toml").exists():
        typer.echo(f"No dazzle.toml found in {root}", err=True)
        raise typer.Exit(code=1)

    json_mode = format == "json"

    # Forward --email / --password to environment for SessionManager + DazzleClient
    if email:
        os.environ["DAZZLE_TEST_EMAIL"] = email
    if password:
        os.environ["DAZZLE_TEST_PASSWORD"] = password

    # Preflight check for remote servers
    if base_url:
        from dazzle.mcp.server.handlers.preflight import check_server_reachable

        if not json_mode:
            typer.echo(f"Checking server at {base_url}...")
        preflight_err = check_server_reachable(base_url)
        if preflight_err:
            err_data = json.loads(preflight_err)
            typer.echo(f"Server not reachable: {err_data.get('error', base_url)}", err=True)
            if err_data.get("hint"):
                typer.echo(f"Hint: {err_data['hint']}", err=True)
            raise typer.Exit(code=1)

    if not json_mode:
        if base_url:
            typer.echo(f"Running DSL tests against {base_url}...")
        else:
            typer.echo(f"Running DSL tests for project at {root}...")
        typer.echo()

    try:
        from dazzle.cli.activity import cli_activity

        with cli_activity(root, "dsl_test", "run_all"):
            runner = UnifiedTestRunner(root, server_timeout=timeout, base_url=base_url)

            # Run all tests
            result = runner.run_all(generate=True, force_generate=regenerate)

        if json_mode:
            typer.echo(json.dumps(result.to_dict(), indent=2))
        else:
            # Show results
            summary = result.get_summary()
            summary["total_tests"]
            passed = summary["passed"]
            failed = summary["failed"]
            skipped = summary.get("skipped", 0)
            pass_rate = summary["success_rate"]
            runnable = passed + failed

            typer.echo()
            if skipped > 0:
                typer.secho(
                    f"Results: {passed}/{runnable} passed ({pass_rate:.1f}%), {skipped} skipped",
                    bold=True,
                )
            else:
                typer.secho(f"Results: {passed}/{runnable} passed ({pass_rate:.1f}%)", bold=True)

            if failed == 0:
                typer.secho("All tests passed!", fg=typer.colors.GREEN)
            else:
                typer.secho(f"{failed} tests failed", fg=typer.colors.RED)

        # Output results to file
        if output:
            output_path = Path(output)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(json.dumps(result.to_dict(), indent=2))
            if not json_mode:
                typer.echo(f"Results saved to {output_path}")

        # Exit with error code if any failures
        summary = result.get_summary()
        if summary["failed"] > 0:
            raise typer.Exit(code=1)

    except typer.Exit:
        raise
    except Exception as e:
        typer.echo(f"Error running tests: {e}", err=True)
        raise typer.Exit(code=1)


@test_app.command("dsl-coverage")
def dsl_coverage(
    manifest: str = typer.Option("dazzle.toml", "--manifest", "-m"),
    format: str = typer.Option(
        "table",
        "--format",
        "-f",
        help="Output format: table (default), json, or markdown",
    ),
    detailed: bool = typer.Option(
        False,
        "--detailed",
        "-d",
        help="Show detailed coverage by entity/persona",
    ),
) -> None:
    """
    Show test coverage for DSL constructs.

    Analyzes your DSL and shows what percentage is covered by generated tests.
    Useful for identifying gaps in test coverage.

    Examples:
        dazzle test dsl-coverage                          # Table output
        dazzle test dsl-coverage --detailed               # Show per-entity details
        dazzle test dsl-coverage --format markdown        # Markdown for docs
        dazzle test dsl-coverage --format json            # JSON for CI
    """
    import json

    try:
        from dazzle.testing.dsl_test_generator import generate_tests_from_dsl
    except ImportError as e:
        typer.echo(f"DSL testing module not available: {e}", err=True)
        raise typer.Exit(code=1)

    manifest_path = Path(manifest).resolve()
    root = manifest_path.parent

    if not (root / "dazzle.toml").exists():
        typer.echo(f"No dazzle.toml found in {root}", err=True)
        raise typer.Exit(code=1)

    try:
        from dazzle.cli.activity import cli_activity

        with cli_activity(root, "dsl_test", "coverage"):
            test_suite = generate_tests_from_dsl(root)
    except Exception as e:
        typer.echo(f"Error generating tests: {e}", err=True)
        raise typer.Exit(code=1)

    coverage = test_suite.coverage

    # Calculate overall coverage
    total_constructs = (
        coverage.entities_total
        + coverage.state_machines_total
        + coverage.personas_total
        + coverage.workspaces_total
        + coverage.events_total
        + coverage.processes_total
    )
    tested_constructs = (
        len(coverage.entities_covered)
        + len(coverage.state_machines_covered)
        + len(coverage.personas_covered)
        + len(coverage.workspaces_covered)
        + len(coverage.events_covered)
        + len(coverage.processes_covered)
    )
    overall_pct = (tested_constructs / total_constructs * 100) if total_constructs > 0 else 0

    if format == "json":
        # JSON output for CI
        result = {
            "overall_coverage": overall_pct,
            "total_constructs": total_constructs,
            "tested_constructs": tested_constructs,
            "total_tests": len(test_suite.designs),
            "categories": {
                "entities": {
                    "total": coverage.entities_total,
                    "tested": len(coverage.entities_covered),
                    "coverage": (len(coverage.entities_covered) / coverage.entities_total * 100)
                    if coverage.entities_total > 0
                    else 0,
                },
                "state_machines": {
                    "total": coverage.state_machines_total,
                    "tested": len(coverage.state_machines_covered),
                    "coverage": (
                        len(coverage.state_machines_covered) / coverage.state_machines_total * 100
                    )
                    if coverage.state_machines_total > 0
                    else 0,
                },
                "personas": {
                    "total": coverage.personas_total,
                    "tested": len(coverage.personas_covered),
                    "coverage": (len(coverage.personas_covered) / coverage.personas_total * 100)
                    if coverage.personas_total > 0
                    else 0,
                },
                "workspaces": {
                    "total": coverage.workspaces_total,
                    "tested": len(coverage.workspaces_covered),
                    "coverage": (len(coverage.workspaces_covered) / coverage.workspaces_total * 100)
                    if coverage.workspaces_total > 0
                    else 0,
                },
                "events": {
                    "total": coverage.events_total,
                    "tested": len(coverage.events_covered),
                    "coverage": (len(coverage.events_covered) / coverage.events_total * 100)
                    if coverage.events_total > 0
                    else 0,
                },
                "processes": {
                    "total": coverage.processes_total,
                    "tested": len(coverage.processes_covered),
                    "coverage": (len(coverage.processes_covered) / coverage.processes_total * 100)
                    if coverage.processes_total > 0
                    else 0,
                },
            },
            "dsl_hash": test_suite.dsl_hash,
        }
        typer.echo(json.dumps(result, indent=2))

    elif format == "markdown":
        # Markdown output for docs
        typer.echo(f"# Test Coverage Report: {test_suite.project_name}")
        typer.echo()
        typer.echo(
            f"**Overall Coverage:** {overall_pct:.1f}%"
            f" ({tested_constructs}/{total_constructs} constructs)"
        )
        typer.echo(f"**Total Tests:** {len(test_suite.designs)}")
        typer.echo()
        typer.echo("## Coverage by Category")
        typer.echo()
        typer.echo("| Category | Total | Tested | Coverage |")
        typer.echo("|----------|-------|--------|----------|")

        rows = [
            ("Entities", coverage.entities_total, len(coverage.entities_covered)),
            ("State Machines", coverage.state_machines_total, len(coverage.state_machines_covered)),
            ("Personas", coverage.personas_total, len(coverage.personas_covered)),
            ("Workspaces", coverage.workspaces_total, len(coverage.workspaces_covered)),
            ("Events", coverage.events_total, len(coverage.events_covered)),
            ("Processes", coverage.processes_total, len(coverage.processes_covered)),
        ]

        for name, total, tested in rows:
            if total > 0:
                pct = tested / total * 100
                typer.echo(f"| {name} | {total} | {tested} | {pct:.1f}% |")

        typer.echo()
        typer.echo(f"*DSL Hash: `{test_suite.dsl_hash[:12]}`*")

    else:
        # Table output (default)
        typer.secho(f"Test Coverage: {test_suite.project_name}", bold=True)
        typer.echo()

        # Overall bar
        bar_width = 40
        filled = int(overall_pct / 100 * bar_width)
        bar = "█" * filled + "░" * (bar_width - filled)
        color = (
            typer.colors.GREEN
            if overall_pct >= 80
            else (typer.colors.YELLOW if overall_pct >= 50 else typer.colors.RED)
        )
        typer.echo(f"Overall: [{bar}] ", nl=False)
        typer.secho(f"{overall_pct:.1f}%", fg=color)
        typer.echo()

        # Category breakdown
        typer.echo("Category Breakdown:")
        categories = [
            ("Entities", coverage.entities_total, len(coverage.entities_covered)),
            ("State Machines", coverage.state_machines_total, len(coverage.state_machines_covered)),
            ("Personas", coverage.personas_total, len(coverage.personas_covered)),
            ("Workspaces", coverage.workspaces_total, len(coverage.workspaces_covered)),
            ("Events", coverage.events_total, len(coverage.events_covered)),
            ("Processes", coverage.processes_total, len(coverage.processes_covered)),
        ]

        for name, total, tested in categories:
            if total > 0:
                pct = tested / total * 100
                color = (
                    typer.colors.GREEN
                    if pct >= 80
                    else (typer.colors.YELLOW if pct >= 50 else typer.colors.RED)
                )
                typer.echo(f"  {name:18} ", nl=False)
                typer.secho(f"{tested:3}/{total:3} ({pct:5.1f}%)", fg=color)

        typer.echo()
        typer.echo(f"Total tests: {len(test_suite.designs)}")
        typer.echo(f"DSL hash: {test_suite.dsl_hash[:12]}")

        # Detailed breakdown
        if detailed:
            typer.echo()
            typer.secho("Detailed Coverage:", bold=True)

            # By entity
            typer.echo()
            typer.echo("  Entities:")
            entity_tests: dict[str, int] = {}
            for design in test_suite.designs:
                entities = design.get("entities", [])
                for entity in entities:
                    entity_tests[entity] = entity_tests.get(entity, 0) + 1

            for entity_name in sorted(coverage.entities_covered):
                count = entity_tests.get(entity_name, 0)
                icon = "✓" if count > 0 else "✗"
                color = typer.colors.GREEN if count > 0 else typer.colors.RED
                typer.secho(f"    {icon} {entity_name}: {count} tests", fg=color)

            # By persona
            if coverage.personas_covered:
                typer.echo()
                typer.echo("  Personas:")
                persona_tests: dict[str, int] = {}
                for design in test_suite.designs:
                    persona = design.get("persona")
                    if persona:
                        persona_tests[persona] = persona_tests.get(persona, 0) + 1

                for persona_id in sorted(coverage.personas_covered):
                    count = persona_tests.get(persona_id, 0)
                    icon = "✓" if count > 0 else "✗"
                    color = typer.colors.GREEN if count > 0 else typer.colors.RED
                    typer.secho(f"    {icon} {persona_id}: {count} tests", fg=color)


@test_app.command("agent")
def test_agent(
    manifest: str = typer.Option("dazzle.toml", "--manifest", "-m"),
    test_id: str = typer.Option(
        None,
        "--test",
        "-t",
        help="Specific test ID to run (default: all E2E tests)",
    ),
    headless: bool = typer.Option(
        False,
        "--headless/--no-headless",
        help="Run browser in headless mode",
    ),
    model: str = typer.Option(
        None,
        "--model",
        help="LLM model to use (default: claude-sonnet-4-20250514)",
    ),
    report: bool = typer.Option(
        True,
        "--report/--no-report",
        help="Generate HTML coverage report",
    ),
    report_dir: str = typer.Option(
        None,
        "--report-dir",
        help="Directory for reports (default: dsl/tests/reports)",
    ),
    base_url: str = typer.Option(
        None,
        "--base-url",
        help="Base URL of already-running server (skip auto-start)",
    ),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """
    [Tier 3] Run E2E tests using an LLM agent.

    Adaptive tests powered by Claude. Use this for:
    - Visual verification ("does this look right?")
    - Exploratory testing
    - Accessibility audits
    - Testing unknown or dynamic UIs

    Slower and costs API credits, but handles complexity that scripts cannot.

    Examples:
        dazzle test agent                    # Run with visible browser
        dazzle test agent --headless         # Run headless (faster)
        dazzle test agent -t WS_MY_WORK_NAV  # Run specific test
        dazzle test agent --no-report        # Skip HTML report generation
        dazzle test agent --base-url http://localhost:3000  # Use running server
    """
    import asyncio

    # Find manifest
    manifest_path = Path(manifest)
    if not manifest_path.exists():
        typer.echo(f"Manifest not found: {manifest_path}", err=True)
        raise typer.Exit(code=1)

    root = manifest_path.parent.resolve()

    try:
        from dazzle.testing.agent_e2e import run_agent_tests

        test_ids = [test_id] if test_id else None

        typer.echo(f"Running agent E2E tests for {root.name}...")
        if not headless:
            typer.echo("  Browser will be visible. Use --headless for faster runs.")

        results = asyncio.run(
            run_agent_tests(
                project_path=root,
                test_ids=test_ids,
                headless=headless,
                model=model,
                base_url=base_url,
            )
        )

        # Display results
        passed = sum(1 for r in results if r.passed)
        failed = len(results) - passed

        typer.echo()
        for result in results:
            icon = "✓" if result.passed else "✗"
            color = typer.colors.GREEN if result.passed else typer.colors.RED
            typer.secho(f"  {icon} {result.test_id}", fg=color)

            if verbose or not result.passed:
                typer.echo(f"    Steps: {len(result.steps)}")
                typer.echo(f"    Duration: {result.duration_ms:.0f}ms")
                if result.reasoning:
                    typer.echo(f"    Reasoning: {result.reasoning}")
                if result.error:
                    typer.secho(f"    Error: {result.error}", fg=typer.colors.RED)

        typer.echo()
        typer.secho(f"Results: {passed}/{len(results)} passed", bold=True)

        # Generate HTML report
        if report and results:
            from dazzle.testing.agent_e2e import generate_html_report

            output_dir = Path(report_dir) if report_dir else root / "dsl" / "tests" / "reports"
            report_path = generate_html_report(results, root.name, output_dir)
            typer.echo()
            typer.secho(f"Report: {report_path}", fg=typer.colors.CYAN)

        if failed > 0:
            raise typer.Exit(code=1)

    except ImportError as e:
        typer.echo(f"Missing dependency: {e}", err=True)
        typer.echo("Install with: pip install playwright anthropic && playwright install chromium")
        raise typer.Exit(code=1)
    except Exception as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1)


# ============================================================================
# Autonomous Workflow Commands (v0.25.0)
# ============================================================================


@test_app.command("populate")
def test_populate(
    manifest: str = typer.Option("dazzle.toml", "--manifest", "-m"),
    max_stories: int = typer.Option(30, "--max-stories", help="Maximum stories to propose"),
    include_test_designs: bool = typer.Option(
        True,
        "--include-tests/--no-tests",
        help="Also generate test designs from stories",
    ),
) -> None:
    """
    Auto-populate stories and test designs from DSL.

    This command runs the full autonomous workflow:
    1. Propose stories from DSL entities
    2. Auto-accept all stories
    3. Generate test designs from accepted stories
    4. Save everything to dsl/stories/ and dsl/tests/

    Use this for LLM-friendly autonomous operation.

    Examples:
        dazzle test populate                    # Full workflow
        dazzle test populate --max-stories 50   # More stories
        dazzle test populate --no-tests         # Stories only
    """
    from datetime import UTC, datetime

    from dazzle.core.ir.stories import StorySpec, StoryStatus, StoryTrigger
    from dazzle.core.ir.test_design import (
        TestDesignAction,
        TestDesignSpec,
        TestDesignStatus,
        TestDesignStep,
        TestDesignTrigger,
    )
    from dazzle.core.stories_persistence import add_stories, get_next_story_id
    from dazzle.testing.test_design_persistence import add_test_designs

    manifest_path = Path(manifest).resolve()
    root = manifest_path.parent

    # Load AppSpec
    try:
        mf = load_manifest(manifest_path)
        dsl_files = discover_dsl_files(root, mf)
        modules = parse_modules(dsl_files)
        appspec = build_appspec(modules, mf.project_root)
    except (ParseError, DazzleError) as e:
        typer.echo(f"Error loading spec: {e}", err=True)
        raise typer.Exit(code=1)

    typer.echo(f"Populating tests for '{appspec.name}'...")
    typer.echo()

    # 1. Propose and auto-accept stories
    typer.secho("Step 1: Proposing stories from DSL...", bold=True)

    base_id = get_next_story_id(root)
    base_num = int(base_id[3:])
    story_count = 0

    def next_story_id() -> str:
        nonlocal story_count
        result = f"ST-{base_num + story_count:03d}"
        story_count += 1
        return result

    now = datetime.now(UTC).isoformat()
    default_actor = "User"
    if appspec.personas:
        default_actor = appspec.personas[0].label or appspec.personas[0].id

    stories: list[StorySpec] = []

    for entity in appspec.domain.entities:
        if story_count >= max_stories:
            break

        # Create story
        stories.append(
            StorySpec(
                story_id=next_story_id(),
                title=f"{default_actor} creates a new {entity.title or entity.name}",
                actor=default_actor,
                trigger=StoryTrigger.FORM_SUBMITTED,
                scope=[entity.name],
                preconditions=[f"{default_actor} has permission to create {entity.name}"],
                happy_path_outcome=[
                    f"New {entity.name} is saved to database",
                    f"{default_actor} sees confirmation message",
                ],
                side_effects=[],
                constraints=[f.name + " must be valid" for f in entity.fields if f.is_required][:3],
                variants=["Validation error on required field"],
                status=StoryStatus.ACCEPTED,  # Auto-accept
                created_at=now,
                accepted_at=now,
            )
        )

        # State machine transitions
        if entity.state_machine:
            for transition in entity.state_machine.transitions[:3]:
                if story_count >= max_stories:
                    break
                sm = entity.state_machine
                stories.append(
                    StorySpec(
                        story_id=next_story_id(),
                        title=(
                            f"{default_actor} changes {entity.name}"
                            f" from {transition.from_state}"
                            f" to {transition.to_state}"
                        ),
                        actor=default_actor,
                        trigger=StoryTrigger.STATUS_CHANGED,
                        scope=[entity.name],
                        preconditions=[
                            f"{entity.name}.{sm.status_field} is '{transition.from_state}'"
                        ],
                        happy_path_outcome=[
                            f"{entity.name}.{sm.status_field} becomes '{transition.to_state}'",
                        ],
                        side_effects=[],
                        constraints=[],
                        variants=[],
                        status=StoryStatus.ACCEPTED,
                        created_at=now,
                        accepted_at=now,
                    )
                )

    # Save stories
    all_stories = add_stories(root, stories, overwrite=False)
    typer.secho(f"  ✓ Proposed and accepted {len(stories)} stories", fg=typer.colors.GREEN)
    typer.echo(f"    Total stories in project: {len(all_stories)}")

    # 2. Generate test designs from stories
    if include_test_designs:
        typer.echo()
        typer.secho("Step 2: Generating test designs from stories...", bold=True)

        trigger_map = {
            StoryTrigger.FORM_SUBMITTED: TestDesignTrigger.FORM_SUBMITTED,
            StoryTrigger.STATUS_CHANGED: TestDesignTrigger.STATUS_CHANGED,
            StoryTrigger.USER_CLICK: TestDesignTrigger.USER_CLICK,
        }

        test_designs: list[TestDesignSpec] = []

        for story in stories:
            test_id = story.story_id.replace("ST-", "TD-")

            steps: list[TestDesignStep] = [
                TestDesignStep(
                    action=TestDesignAction.LOGIN_AS,
                    target=story.actor,
                    rationale=f"Test from {story.actor}'s perspective",
                )
            ]

            if story.trigger == StoryTrigger.FORM_SUBMITTED:
                scope_entity = story.scope[0] if story.scope else "form"
                steps.extend(
                    [
                        TestDesignStep(
                            action=TestDesignAction.NAVIGATE_TO,
                            target=f"{scope_entity}_create",
                            rationale="Navigate to creation form",
                        ),
                        TestDesignStep(
                            action=TestDesignAction.FILL,
                            target="form",
                            data={"fields": "required_fields"},
                            rationale="Fill form with test data",
                        ),
                        TestDesignStep(
                            action=TestDesignAction.CLICK,
                            target="submit_button",
                            rationale="Submit the form",
                        ),
                    ]
                )
            elif story.trigger == StoryTrigger.STATUS_CHANGED:
                scope_entity = story.scope[0] if story.scope else "entity"
                steps.append(
                    TestDesignStep(
                        action=TestDesignAction.TRIGGER_TRANSITION,
                        target=scope_entity,
                        rationale="Trigger status change",
                    )
                )

            test_designs.append(
                TestDesignSpec(
                    test_id=test_id,
                    title=f"Verify: {story.title}",
                    description=f"Test generated from story {story.story_id}",
                    persona=story.actor,
                    trigger=trigger_map.get(story.trigger, TestDesignTrigger.USER_CLICK),
                    steps=steps,
                    expected_outcomes=story.happy_path_outcome.copy(),
                    entities=story.scope.copy(),
                    tags=[f"story:{story.story_id}", "auto-populated"],
                    status=TestDesignStatus.PROPOSED,
                )
            )

        add_test_designs(root, test_designs, overwrite=False, to_dsl=True)
        typer.secho(f"  ✓ Generated {len(test_designs)} test designs", fg=typer.colors.GREEN)

    # Summary
    typer.echo()
    typer.secho("Population complete!", bold=True, fg=typer.colors.GREEN)
    typer.echo()
    typer.echo("Next steps:")
    typer.echo("  dazzle test dsl-run              # Run Tier 1 API tests")
    typer.echo("  dazzle test run --tier 2         # Run Tier 2 Playwright tests")
    typer.echo("  dazzle test agent                # Run Tier 3 LLM agent tests")


@test_app.command("run-all")
def test_run_all(
    manifest: str = typer.Option("dazzle.toml", "--manifest", "-m"),
    tier: int = typer.Option(
        None,
        "--tier",
        "-t",
        help="Run specific tier only: 1 (API), 2 (Playwright), 3 (Agent)",
    ),
    headless: bool = typer.Option(True, "--headless/--headed"),
    output: str = typer.Option(None, "--output", "-o", help="Output JSON file for results"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
    format: str = typer.Option(
        "table",
        "--format",
        "-f",
        help="Output format: table (default) or json",
    ),
) -> None:
    """
    Run tests across all tiers (unified test runner).

    By default runs all applicable tiers. Use --tier to run specific tier:
    - Tier 1: API-based tests (fast, no browser)
    - Tier 2: Playwright scripted tests (browser, deterministic)
    - Tier 3: LLM agent tests (browser, adaptive)

    Examples:
        dazzle test run-all                    # Run all tiers
        dazzle test run-all --tier 1           # Run Tier 1 only (API)
        dazzle test run-all --tier 2           # Run Tier 2 only (Playwright)
        dazzle test run-all --tier 3           # Run Tier 3 only (Agent)
        dazzle test run-all --headed           # Show browser for Tier 2/3
        dazzle test run-all --format json      # JSON output for CI
    """
    import json

    manifest_path = Path(manifest).resolve()
    root = manifest_path.parent

    if not (root / "dazzle.toml").exists():
        typer.echo(f"No dazzle.toml found in {root}", err=True)
        raise typer.Exit(code=1)

    json_mode = format == "json"
    results: dict[str, Any] = {"tiers": {}, "overall": {"passed": 0, "failed": 0}}

    # Tier 1: API tests
    if tier is None or tier == 1:
        if not json_mode:
            typer.secho("Tier 1: Running API tests...", bold=True)
        try:
            from dazzle.testing.unified_runner import UnifiedTestRunner

            runner = UnifiedTestRunner(root)
            result = runner.run_all(generate=True)
            summary = result.get_summary()
            passed = summary["passed"]
            failed = summary["failed"]

            results["tiers"]["tier1"] = {
                "passed": passed,
                "failed": failed,
                "total": passed + failed,
            }
            results["overall"]["passed"] += passed
            results["overall"]["failed"] += failed

            if not json_mode:
                color = typer.colors.GREEN if failed == 0 else typer.colors.RED
                typer.secho(f"  Tier 1: {passed}/{passed + failed} passed", fg=color)

        except ImportError:
            if not json_mode:
                typer.echo("  Tier 1: Skipped (unified_runner not available)", err=True)
        except Exception as e:
            if not json_mode:
                typer.echo(f"  Tier 1: Error - {e}", err=True)
            results["tiers"]["tier1"] = {"error": str(e)}

    # Tier 2: Playwright tests
    if tier is None or tier == 2:
        if not json_mode:
            typer.echo()
            typer.secho("Tier 2: Running Playwright tests...", bold=True)
        try:
            from dazzle.testing.e2e_runner import E2ERunner, E2ERunOptions

            e2e_runner = E2ERunner(root)
            playwright_ok, _ = e2e_runner.ensure_playwright()

            if playwright_ok:
                options = E2ERunOptions(headless=headless)
                e2e_result = e2e_runner.run_all(options)

                passed = e2e_result.passed
                failed = e2e_result.failed

                results["tiers"]["tier2"] = {
                    "passed": passed,
                    "failed": failed,
                    "total": passed + failed,
                }
                results["overall"]["passed"] += passed
                results["overall"]["failed"] += failed

                if not json_mode:
                    color = typer.colors.GREEN if failed == 0 else typer.colors.RED
                    typer.secho(f"  Tier 2: {passed}/{passed + failed} passed", fg=color)
            else:
                if not json_mode:
                    typer.echo("  Tier 2: Skipped (Playwright not available)", err=True)
                results["tiers"]["tier2"] = {"skipped": True}

        except ImportError:
            if not json_mode:
                typer.echo("  Tier 2: Skipped (e2e_runner not available)", err=True)
        except Exception as e:
            if not json_mode:
                typer.echo(f"  Tier 2: Error - {e}", err=True)
            results["tiers"]["tier2"] = {"error": str(e)}

    # Tier 3: Agent tests
    if tier is None or tier == 3:
        if not json_mode:
            typer.echo()
            typer.secho("Tier 3: Running LLM agent tests...", bold=True)
        try:
            import asyncio

            from dazzle.testing.agent_e2e import run_agent_tests

            test_results = asyncio.run(
                run_agent_tests(
                    project_path=root,
                    test_ids=None,
                    headless=headless,
                )
            )

            passed = sum(1 for r in test_results if r.passed)
            failed = len(test_results) - passed

            results["tiers"]["tier3"] = {
                "passed": passed,
                "failed": failed,
                "total": len(test_results),
            }
            results["overall"]["passed"] += passed
            results["overall"]["failed"] += failed

            if not json_mode:
                color = typer.colors.GREEN if failed == 0 else typer.colors.RED
                typer.secho(f"  Tier 3: {passed}/{len(test_results)} passed", fg=color)

        except ImportError as e:
            if not json_mode:
                typer.echo(f"  Tier 3: Skipped ({e})", err=True)
            results["tiers"]["tier3"] = {"skipped": True}
        except Exception as e:
            if not json_mode:
                typer.echo(f"  Tier 3: Error - {e}", err=True)
            results["tiers"]["tier3"] = {"error": str(e)}

    if json_mode:
        typer.echo(json.dumps(results, indent=2))
    else:
        # Summary
        typer.echo()
        total_passed = results["overall"]["passed"]
        total_failed = results["overall"]["failed"]
        total = total_passed + total_failed

        if total_failed == 0 and total > 0:
            typer.secho(
                f"All tests passed: {total_passed}/{total}", fg=typer.colors.GREEN, bold=True
            )
        elif total > 0:
            typer.secho(
                f"Results: {total_passed}/{total} passed, {total_failed} failed",
                fg=typer.colors.RED,
                bold=True,
            )
        else:
            typer.echo("No tests were run.")

    # Output to file
    if output:
        output_path = Path(output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(results, indent=2))
        if not json_mode:
            typer.echo(f"Results saved to {output_path}")

    # Exit with error if failures
    total_failed = results["overall"]["failed"]
    if total_failed > 0:
        raise typer.Exit(code=1)


@test_app.command("create-sessions")
def test_create_sessions(
    manifest: str = typer.Option("dazzle.toml", "--manifest", "-m"),
    base_url: str = typer.Option(
        "http://localhost:8000",
        "--base-url",
        help="Base URL of the running application",
    ),
    force: bool = typer.Option(
        False,
        "--force",
        "-f",
        help="Recreate sessions even if they exist and are fresh",
    ),
    cleanup: bool = typer.Option(
        False,
        "--cleanup",
        help="Remove all stored sessions and exit",
    ),
) -> None:
    """
    Create authenticated sessions for all DSL-defined personas.

    Sessions are stored in .dazzle/test_sessions/ and reused across test runs,
    discovery sessions, and differential analysis.

    Examples:
        dazzle test create-sessions                         # Create all persona sessions
        dazzle test create-sessions --base-url http://...   # Against specific server
        dazzle test create-sessions --force                 # Recreate all sessions
        dazzle test create-sessions --cleanup               # Remove stored sessions
    """
    import asyncio

    manifest_path = Path(manifest).resolve()
    root = manifest_path.parent

    if not (root / "dazzle.toml").exists():
        typer.echo(f"No dazzle.toml found in {root}", err=True)
        raise typer.Exit(code=1)

    try:
        from dazzle.testing.session_manager import SessionManager
    except ImportError as e:
        typer.echo(f"Session manager not available: {e}", err=True)
        raise typer.Exit(code=1)

    manager = SessionManager(root, base_url=base_url)

    if cleanup:
        count = manager.cleanup()
        typer.echo(f"Removed {count} session files")
        return

    try:
        from dazzle.core.project import load_project

        appspec = load_project(root)
    except Exception as e:
        typer.echo(f"Failed to load DSL: {e}", err=True)
        raise typer.Exit(code=1)

    personas = appspec.personas if hasattr(appspec, "personas") else []
    if not personas:
        typer.echo("No personas defined in DSL", err=True)
        raise typer.Exit(code=1)

    typer.echo(f"Creating sessions for {len(personas)} personas against {base_url}...")

    try:
        manifest_result = asyncio.run(manager.create_all_sessions(appspec, force=force))
    except Exception as e:
        typer.echo(f"Error creating sessions: {e}", err=True)
        raise typer.Exit(code=1)

    for pid, _session in manifest_result.sessions.items():
        typer.secho(f"  {pid}: ", nl=False, bold=True)
        typer.secho("OK", fg=typer.colors.GREEN)

    failed = len(personas) - len(manifest_result.sessions)
    if failed > 0:
        typer.secho(f"\n{failed} persona(s) failed to authenticate", fg=typer.colors.RED)
        raise typer.Exit(code=1)

    typer.echo(f"\nSessions stored in {manager.sessions_dir}")


@test_app.command("diff-personas")
def test_diff_personas(
    route: str = typer.Argument(..., help="Route to compare (e.g. /contacts)"),
    manifest: str = typer.Option("dazzle.toml", "--manifest", "-m"),
    base_url: str = typer.Option(
        "http://localhost:8000",
        "--base-url",
        help="Base URL of the running application",
    ),
    personas: str = typer.Option(
        None,
        "--personas",
        "-p",
        help="Comma-separated persona IDs (default: all stored sessions)",
    ),
) -> None:
    """
    Compare route responses across personas (differential analysis).

    Fetches the same route as each persona and compares HTTP status, content
    length, table rows, and regions. Useful for ACL verification.

    Examples:
        dazzle test diff-personas /contacts
        dazzle test diff-personas /workspaces/admin_dashboard
        dazzle test diff-personas /contacts --personas admin,agent,customer
    """
    import asyncio

    manifest_path = Path(manifest).resolve()
    root = manifest_path.parent

    if not (root / "dazzle.toml").exists():
        typer.echo(f"No dazzle.toml found in {root}", err=True)
        raise typer.Exit(code=1)

    try:
        from dazzle.testing.session_manager import SessionManager
    except ImportError as e:
        typer.echo(f"Session manager not available: {e}", err=True)
        raise typer.Exit(code=1)

    manager = SessionManager(root, base_url=base_url)

    persona_ids = personas.split(",") if personas else None
    if not persona_ids:
        persona_ids = manager.list_sessions()

    if not persona_ids:
        typer.echo("No persona sessions found. Run 'dazzle test create-sessions' first.", err=True)
        raise typer.Exit(code=1)

    typer.echo(f"Route: {route}")
    typer.echo(f"Personas: {', '.join(persona_ids)}")
    typer.echo()

    try:
        result = asyncio.run(manager.diff_route(route, persona_ids))
    except Exception as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1)

    # Display results as a table
    for pid, info in result.get("personas", {}).items():
        status = info.get("status", "?")
        if status == 200:
            status_str = typer.style("200", fg=typer.colors.GREEN)
        elif status == 403:
            status_str = typer.style("403 Forbidden", fg=typer.colors.RED)
        elif status == 0:
            status_str = typer.style(f"ERROR: {info.get('error', '?')}", fg=typer.colors.RED)
        else:
            status_str = typer.style(str(status), fg=typer.colors.YELLOW)

        details = []
        if info.get("table_rows", 0) > 0:
            details.append(f"{info['table_rows']} rows")
        if info.get("regions", 0) > 0:
            details.append(f"{info['regions']} regions")
        if info.get("line_count", 0) > 0:
            details.append(f"{info['line_count']} lines")
        if info.get("redirected"):
            details.append(f"-> {info['final_url']}")

        detail_str = f" ({', '.join(details)})" if details else ""
        typer.echo(f"  {pid:20s} {status_str}{detail_str}")
