"""
Playwright Test Code Generator.

Generates executable Playwright Python test files from E2ETestSpec.
The generated tests use the console logging infrastructure from conftest.py.
"""

from __future__ import annotations

import re
from pathlib import Path

from dazzle.core.ir import (
    E2ETestSpec,
    FixtureSpec,
    FlowAssertionKind,
    FlowPriority,
    FlowSpec,
    FlowStep,
    FlowStepKind,
)

# =============================================================================
# Selector Mapping
# =============================================================================


def _parse_target(target: str) -> tuple[str, str]:
    """
    Parse a semantic target like 'view:task_list' or 'field:Task.title'.

    Returns:
        Tuple of (target_type, target_name)
    """
    if ":" in target:
        parts = target.split(":", 1)
        return parts[0], parts[1]
    return "unknown", target


def _target_to_selector(target: str) -> str:
    """
    Convert a semantic target to a Playwright selector.

    DNR uses data-dazzle-* attributes for semantic DOM elements.
    """
    target_type, target_name = _parse_target(target)

    if target_type == "view":
        # Views use data-dazzle-view attribute
        return f'[data-dazzle-view="{target_name}"]'

    elif target_type == "field":
        # Fields use data-dazzle-field attribute with name fallback
        # Target format: Entity.field_name
        if "." in target_name:
            _entity, field = target_name.split(".", 1)
            return f'[data-dazzle-field="{field}"], [name="{field}"]'
        return f'[data-dazzle-field="{target_name}"], [name="{target_name}"]'

    elif target_type == "action":
        # Actions use data-dazzle-action attribute with text fallbacks
        # Target format: Entity.action or just action
        if "." in target_name:
            entity, action = target_name.split(".", 1)
            if action in ("save", "create", "submit"):
                return f'[data-dazzle-action="{target_name}"], [data-dazzle-action="{entity}.create"], button[type="submit"]'
            if action == "delete":
                return f'[data-dazzle-action="{target_name}"], button:has-text("Delete")'
            if action == "edit":
                return f'[data-dazzle-action="{target_name}"], a:has-text("Edit")'
            return f'[data-dazzle-action="{target_name}"], [data-dazzle-action="{action}"]'
        return f'[data-dazzle-action="{target_name}"]'

    elif target_type == "row":
        # Table rows use data-dazzle-row attribute with tbody fallback
        return f'[data-dazzle-row="{target_name}"], tbody tr'

    elif target_type == "component":
        # Components use data-dazzle-component attribute
        return f'[data-dazzle-component="{target_name}"]'

    elif target_type == "auth":
        # Auth elements use specific data-dazzle-auth-* attributes or IDs
        return _auth_target_to_selector(target_name)

    else:
        # Fallback to test ID
        return f'[data-testid="{target_name}"]'


def _auth_target_to_selector(target_name: str) -> str:
    """Convert auth target to selector."""
    selectors = {
        "login_button": '[data-dazzle-auth-action="login"]',
        "logout_button": '[data-dazzle-auth-action="logout"]',
        "modal": "#dz-auth-modal",
        "form": "#dz-auth-form",
        "submit": "#dz-auth-submit",
        "error": "#dz-auth-error:not(.hidden)",
        "user_indicator": "[data-dazzle-auth-user]",
    }

    if target_name in selectors:
        return selectors[target_name]

    # Handle field.* and toggle.* patterns
    if target_name.startswith("field."):
        field_name = target_name[6:]  # Strip "field." prefix
        return f'#dz-auth-form [name="{field_name}"]'

    if target_name.startswith("toggle."):
        mode = target_name[7:]  # Strip "toggle." prefix
        return f'[data-dazzle-auth-toggle="{mode}"]'

    # Fallback
    return f'[data-dazzle-auth="{target_name}"]'


def _target_to_route(target: str) -> str:
    """
    Convert a semantic target to a route path for navigation.

    Maps surface names to HTMX template routes:
      task_list   -> /task        (list surfaces)
      task_create -> /task/create (create surfaces)
      task_view   -> /task/test-id (view surfaces, placeholder ID)
      task_detail -> /task/test-id (detail surfaces, placeholder ID)
      task_edit   -> /task/test-id/edit (edit surfaces)

    Direct paths (starting with /) are returned as-is.
    """
    # Direct path targets (starting with /)
    if target.startswith("/"):
        return target

    target_type, target_name = _parse_target(target)

    if target_type == "view":
        # Parse {entity}_{mode} from surface name
        # Handle multi-word entity names: last segment is the mode
        parts = target_name.split("_")
        if len(parts) >= 2:
            mode = parts[-1]
            entity = "_".join(parts[:-1]).replace("_", "-")

            mode_routes = {
                "list": f"/{entity}",
                "create": f"/{entity}/create",
                "view": f"/{entity}/test-id",
                "detail": f"/{entity}/test-id",
                "edit": f"/{entity}/test-id/edit",
            }
            if mode in mode_routes:
                return mode_routes[mode]
            # Unknown mode — treat as list
            return f"/{entity}"
        return f"/{target_name}"

    return f"/{target_name}"


# =============================================================================
# Step Code Generation
# =============================================================================


def _generate_step_code(step: FlowStep, fixtures: dict[str, FixtureSpec]) -> str:
    """Generate Playwright code for a single flow step."""
    lines: list[str] = []

    # Add comment with step description
    if step.description:
        lines.append(f"# {step.description}")

    target = step.target or ""

    if step.kind == FlowStepKind.NAVIGATE:
        route = _target_to_route(target)
        lines.append(f'page.goto(f"{{base_url}}{route}")')
        lines.append('page.wait_for_load_state("networkidle")')

    elif step.kind == FlowStepKind.FILL:
        selector = _target_to_selector(target)
        # Get value from fixture or step.value
        if step.fixture_ref:
            # fixture_ref format: "Entity_valid.field_name"
            fixture_id, field_name = step.fixture_ref.rsplit(".", 1)
            value = f'fixtures["{fixture_id}"]["{field_name}"]'

            # Use appropriate method based on field type
            if step.field_type in ("enum", "ref"):
                # Select fields use select_option with the value
                lines.append(f"page.locator('{selector}').select_option(str({value}))")
            elif step.field_type == "bool":
                # Checkbox fields use set_checked
                lines.append(f"page.locator('{selector}').set_checked(bool({value}))")
            else:
                # Text/number fields use fill
                lines.append(f"page.locator('{selector}').fill(str({value}))")
        elif step.value is not None:
            # Use appropriate method based on field type
            if step.field_type in ("enum", "ref"):
                lines.append(f"page.locator('{selector}').select_option(\"{step.value}\")")
            elif step.field_type == "bool":
                # Parse boolean value
                bool_val = step.value.lower() in ("true", "1", "yes")
                lines.append(f"page.locator('{selector}').set_checked({bool_val})")
            else:
                lines.append(f"page.locator('{selector}').fill(\"{step.value}\")")
        else:
            lines.append(f"page.locator('{selector}').fill(\"test_value\")")

    elif step.kind == FlowStepKind.CLICK:
        selector = _target_to_selector(target)
        lines.append(f"page.locator('{selector}').click()")
        # Wait for any navigation or network activity to settle
        lines.append('page.wait_for_load_state("networkidle")')

    elif step.kind == FlowStepKind.WAIT:
        if step.value:
            lines.append(f"page.wait_for_timeout({step.value})")
        else:
            selector = _target_to_selector(target)
            lines.append(f"page.locator('{selector}').wait_for()")

    elif step.kind == FlowStepKind.ASSERT:
        if step.assertion:
            assertion = step.assertion
            assertion_target = assertion.target or ""
            if assertion.kind == FlowAssertionKind.VISIBLE:
                selector = _target_to_selector(assertion_target)
                lines.append(f"expect(page.locator('{selector}')).to_be_visible()")

            elif assertion.kind == FlowAssertionKind.ENTITY_EXISTS:
                # Check that entity was created via API or table row exists
                lines.append(f"# Verify {assertion_target} entity exists")
                lines.append(
                    "expect(page.locator('[data-dazzle-row]')).to_have_count(1, timeout=5000)"
                )

            elif assertion.kind == FlowAssertionKind.ENTITY_NOT_EXISTS:
                lines.append(f"# Verify {assertion_target} entity was deleted")
                lines.append(
                    "expect(page.locator('[data-dazzle-row]')).to_have_count(0, timeout=5000)"
                )

            elif assertion.kind == FlowAssertionKind.VALIDATION_ERROR:
                lines.append("# Verify validation error appears")
                lines.append("expect(page.locator('[data-dazzle-error]')).to_be_visible()")

            elif assertion.kind == FlowAssertionKind.FIELD_VALUE:
                selector = _target_to_selector(assertion_target)
                lines.append(
                    f"expect(page.locator('{selector}')).to_have_value(\"{assertion.expected}\")"
                )

            # Auth assertions
            elif assertion.kind == FlowAssertionKind.IS_AUTHENTICATED:
                lines.append("# Verify user is authenticated")
                lines.append("expect(page.locator('[data-dazzle-auth-user]')).to_be_visible()")

            elif assertion.kind == FlowAssertionKind.IS_NOT_AUTHENTICATED:
                lines.append("# Verify user is not authenticated")
                lines.append(
                    "expect(page.locator('[data-dazzle-auth-action=\"login\"]')).to_be_visible()"
                )

            elif assertion.kind == FlowAssertionKind.LOGIN_SUCCEEDED:
                lines.append("# Verify login succeeded")
                lines.append(
                    "expect(page.locator('#dz-auth-modal')).not_to_be_visible(timeout=5000)"
                )
                lines.append("expect(page.locator('[data-dazzle-auth-user]')).to_be_visible()")

            elif assertion.kind == FlowAssertionKind.LOGIN_FAILED:
                lines.append("# Verify login failed with error")
                lines.append("expect(page.locator('#dz-auth-error:not(.hidden)')).to_be_visible()")

            elif assertion.kind == FlowAssertionKind.ROUTE_PROTECTED:
                lines.append("# Verify route is protected")
                lines.append("# Either auth modal is shown or login button is visible (redirected)")
                lines.append("modal_visible = page.locator('#dz-auth-modal').is_visible()")
                lines.append(
                    "login_visible = page.locator('[data-dazzle-auth-action=\"login\"]').is_visible()"
                )
                lines.append("assert modal_visible or login_visible, 'Route should be protected'")

            elif assertion.kind == FlowAssertionKind.HAS_PERSONA:
                persona = assertion_target
                lines.append(f"# Verify user has '{persona}' persona")
                lines.append(
                    f"expect(page.locator('[data-dazzle-persona=\"{persona}\"]')).to_be_visible()"
                )

    elif step.kind == FlowStepKind.SNAPSHOT:
        lines.append(f"# Snapshot: {target}")
        lines.append(f'page.screenshot(path=f"screenshots/{{test_name}}_{target}.png")')

    return "\n    ".join(lines)


# =============================================================================
# Test Function Generation
# =============================================================================


def _sanitize_test_name(name: str) -> str:
    """Convert a flow ID to a valid Python test function name."""
    # Replace non-alphanumeric characters with underscores
    name = re.sub(r"[^a-zA-Z0-9_]", "_", name)
    # Ensure it starts with test_
    if not name.startswith("test_"):
        name = f"test_{name}"
    return name


def _generate_test_function(
    flow: FlowSpec,
    fixtures: dict[str, FixtureSpec],
) -> str:
    """Generate a complete test function for a flow."""
    test_name = _sanitize_test_name(flow.id)

    # Generate step code
    step_code_parts: list[str] = []
    for step in flow.steps:
        step_code = _generate_step_code(step, fixtures)
        step_code_parts.append(step_code)

    step_code = "\n\n    ".join(step_code_parts)

    # Build fixture dictionary for the test
    fixture_refs: set[str] = set()
    for step in flow.steps:
        if step.fixture_ref:
            fixture_id = step.fixture_ref.rsplit(".", 1)[0]
            fixture_refs.add(fixture_id)

    # Generate pytest marks
    marks: list[str] = []
    marks.append("@pytest.mark.e2e")
    if flow.priority == FlowPriority.HIGH:
        marks.append("@pytest.mark.high_priority")
    if flow.tags:
        for tag in flow.tags:
            marks.append(f"@pytest.mark.{tag.replace('-', '_')}")

    marks_str = "\n".join(marks)

    # Generate docstring
    docstring = flow.description or f"Test flow: {flow.id}"
    if flow.entity:
        docstring += f"\n\n    Entity: {flow.entity}"
    if flow.tags:
        docstring += f"\n    Tags: {', '.join(flow.tags)}"

    # Only include fixtures dict if it's actually used
    fixtures_line = ""
    if fixture_refs:
        fixtures_line = (
            f"    fixtures: dict[str, Any] = {_generate_fixtures_dict(fixture_refs, fixtures)}\n\n"
        )

    return f'''
{marks_str}
def {test_name}(page: Page, page_diagnostics: Any, track_route: Any, track_crud: Any, base_url: str) -> None:
    """
    {docstring}
    """
{fixtures_line}    # Execute flow steps
    {step_code}

    # Check for console errors after test
    if page_diagnostics.has_errors():
        errors = page_diagnostics.get_errors()
        pytest.fail(f"Browser console errors detected: {{errors}}")
'''


def _generate_fixtures_dict(
    fixture_refs: set[str],
    fixtures: dict[str, FixtureSpec],
) -> str:
    """Generate a dictionary literal for fixture data."""
    if not fixture_refs:
        return "{}"

    parts: list[str] = []
    for ref in sorted(fixture_refs):
        if ref in fixtures:
            data = fixtures[ref].data
            # Format the data dictionary
            data_str = "{\n"
            for key, value in data.items():
                if isinstance(value, str):
                    data_str += f'            "{key}": "{value}",\n'
                else:
                    data_str += f'            "{key}": {value},\n'
            data_str += "        }"
            parts.append(f'        "{ref}": {data_str}')

    return "{\n" + ",\n".join(parts) + "\n    }"


# =============================================================================
# Test Module Generation
# =============================================================================


def generate_test_module(testspec: E2ETestSpec) -> str:
    """
    Generate a complete pytest module from E2ETestSpec.

    Args:
        testspec: The E2E test specification

    Returns:
        Complete Python test module as a string
    """
    # Convert fixtures list to dict for lookup
    fixtures: dict[str, FixtureSpec] = {f.id: f for f in testspec.fixtures}

    # Group flows by priority
    high_priority_flows = [f for f in testspec.flows if f.priority == FlowPriority.HIGH]
    medium_priority_flows = [f for f in testspec.flows if f.priority == FlowPriority.MEDIUM]
    low_priority_flows = [f for f in testspec.flows if f.priority == FlowPriority.LOW]

    # Generate test functions
    test_functions: list[str] = []

    # High priority first
    for flow in high_priority_flows:
        test_functions.append(_generate_test_function(flow, fixtures))

    # Then medium
    for flow in medium_priority_flows:
        test_functions.append(_generate_test_function(flow, fixtures))

    # Then low
    for flow in low_priority_flows:
        test_functions.append(_generate_test_function(flow, fixtures))

    tests_code = "\n".join(test_functions)

    # Generate complete module
    return f'''"""
Auto-generated E2E tests for {testspec.app_name}.

Generated from E2ETestSpec by Dazzle playwright_codegen.

This module uses the console logging infrastructure from conftest.py:
- page_diagnostics: Captures all browser console output
- Errors are reported at the end of each test

Test Count: {len(testspec.flows)}
- High Priority: {len(high_priority_flows)}
- Medium Priority: {len(medium_priority_flows)}
- Low Priority: {len(low_priority_flows)}
"""

from __future__ import annotations

from typing import Any

import pytest
from playwright.sync_api import Page, expect


# =============================================================================
# Generated Tests
# =============================================================================
{tests_code}
'''


def generate_conftest() -> str:
    """Generate a conftest.py that provides fixtures for generated E2E tests.

    Provides: page, page_diagnostics, base_url, track_route, track_crud.
    """
    return '''\
"""
Auto-generated conftest for Dazzle E2E tests.

Provides Playwright fixtures with console logging, route tracking,
and CRUD tracking infrastructure.

Generated by Dazzle playwright_codegen — safe to regenerate.
"""

from __future__ import annotations

import json
import os
from collections.abc import Generator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest
from playwright.sync_api import Browser, ConsoleMessage, Page, sync_playwright

# Project root (for runtime file discovery)
PROJECT_ROOT = Path(__file__).parent.parent.parent

DEFAULT_UI_URL = "http://localhost:3000"
DEFAULT_API_URL = "http://localhost:8000"


def _load_runtime_ports() -> tuple[str, str]:
    """Load port config from .dazzle/runtime.json if available."""
    runtime_file = PROJECT_ROOT / ".dazzle" / "runtime.json"
    if runtime_file.exists():
        try:
            with open(runtime_file) as f:
                data = json.load(f)
            return (
                data.get("ui_url", DEFAULT_UI_URL),
                data.get("api_url", DEFAULT_API_URL),
            )
        except (json.JSONDecodeError, KeyError):
            pass
    return DEFAULT_UI_URL, DEFAULT_API_URL


# ---- Console diagnostics --------------------------------------------------


@dataclass
class ConsoleLogEntry:
    """A single browser console log entry."""

    type: str
    text: str
    url: str
    line_number: int


@dataclass
class PageDiagnostics:
    """Collected diagnostics from a page session."""

    console_logs: list[ConsoleLogEntry] = field(default_factory=list)
    page_errors: list[str] = field(default_factory=list)

    def add_console(self, msg: ConsoleMessage) -> None:
        loc = msg.location
        self.console_logs.append(
            ConsoleLogEntry(
                type=msg.type,
                text=msg.text,
                url=loc.get("url", ""),
                line_number=loc.get("lineNumber", 0),
            )
        )

    def add_error(self, error: Exception) -> None:
        self.page_errors.append(str(error))

    def has_errors(self) -> bool:
        return bool(self.page_errors) or any(
            log.type == "error" for log in self.console_logs
        )

    def get_errors(self) -> list[str]:
        errors = []
        for log in self.console_logs:
            if log.type == "error":
                errors.append(
                    f"CONSOLE [{log.url}:{log.line_number}]: {log.text}"
                )
        errors.extend(f"PAGE ERROR: {e}" for e in self.page_errors)
        return errors

    def print_summary(self, test_name: str = "") -> None:
        prefix = f"[{test_name}] " if test_name else ""
        if self.console_logs:
            print(
                f"\\n{prefix}=== Console Logs "
                f"({len(self.console_logs)} entries) ==="
            )
            for log in self.console_logs:
                loc = f"{log.url}:{log.line_number}" if log.url else "?"
                print(f"  {log.type.upper():8} [{loc}] {log.text[:200]}")
        if self.page_errors:
            print(
                f"\\n{prefix}=== Page Errors "
                f"({len(self.page_errors)}) ==="
            )
            for err in self.page_errors:
                print(f"  ERROR: {err[:200]}")


# ---- Route / CRUD tracking ------------------------------------------------


@dataclass
class RouteTracker:
    """Track navigated routes during a test."""

    routes: list[str] = field(default_factory=list)

    def __call__(self, route: str) -> None:
        self.routes.append(route)


@dataclass
class CrudTracker:
    """Track CRUD operations during a test."""

    ops: list[dict[str, Any]] = field(default_factory=list)

    def __call__(self, entity: str, action: str, **kwargs: Any) -> None:
        self.ops.append({"entity": entity, "action": action, **kwargs})


# ---- Fixtures --------------------------------------------------------------


@pytest.fixture(scope="session")
def base_url() -> str:
    """UI base URL (env var > runtime.json > default)."""
    if "DAZZLE_UI_URL" in os.environ:
        return os.environ["DAZZLE_UI_URL"]
    ui, _ = _load_runtime_ports()
    return ui


@pytest.fixture(scope="module")
def browser() -> Generator[Browser, None, None]:
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        yield b
        b.close()


@pytest.fixture
def page_diagnostics() -> PageDiagnostics:
    return PageDiagnostics()


@pytest.fixture
def page(
    browser: Browser, page_diagnostics: PageDiagnostics, request: Any
) -> Generator[Page, None, None]:
    context = browser.new_context(viewport={"width": 1280, "height": 720})
    pg = context.new_page()

    pg.on("console", lambda msg: page_diagnostics.add_console(msg))
    pg.on("pageerror", lambda err: page_diagnostics.add_error(err))

    yield pg

    test_name = request.node.name if request else ""
    if page_diagnostics.has_errors():
        page_diagnostics.print_summary(test_name)

    pg.close()
    context.close()


@pytest.fixture
def track_route() -> RouteTracker:
    return RouteTracker()


@pytest.fixture
def track_crud() -> CrudTracker:
    return CrudTracker()
'''


def generate_test_file(
    testspec: E2ETestSpec,
    output_path: str | Path,
) -> Path:
    """
    Generate a pytest test file and conftest.py from E2ETestSpec.

    Args:
        testspec: The E2E test specification
        output_path: Path for the output test file

    Returns:
        Path to the generated test file
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    content = generate_test_module(testspec)
    output_path.write_text(content)

    # Write conftest.py alongside the test file (skip if hand-written)
    conftest_path = output_path.parent / "conftest.py"
    if not conftest_path.exists() or _is_generated_conftest(conftest_path):
        conftest_path.write_text(generate_conftest())

    return output_path


def _is_generated_conftest(path: Path) -> bool:
    """Check if an existing conftest.py was generated by us."""
    try:
        header = path.read_text()[:120]
        return "Auto-generated conftest for Dazzle E2E" in header
    except OSError:
        return False


# =============================================================================
# CLI Integration
# =============================================================================


def generate_tests_for_app(
    app_path: str | Path,
    output_dir: str | Path | None = None,
) -> Path:
    """
    Generate E2E tests for a DAZZLE application.

    This is the main entry point for test generation. It:
    1. Parses the DSL files
    2. Generates E2ETestSpec from AppSpec
    3. Generates Playwright test code

    Args:
        app_path: Path to the DAZZLE application directory
        output_dir: Output directory for tests (default: app_path/tests/e2e)

    Returns:
        Path to the generated test file
    """
    from glob import glob

    from dazzle.core import build_appspec, parse_modules
    from dazzle.core.manifest import load_manifest
    from dazzle.testing.testspec_generator import generate_e2e_testspec

    app_path = Path(app_path)
    output_dir = Path(output_dir) if output_dir else app_path / "tests" / "e2e"

    # Load manifest
    manifest_path = app_path / "dazzle.toml"
    manifest = load_manifest(manifest_path)

    # Parse all DSL files using proper parser
    dsl_dir = app_path / "dsl"
    dsl_files = [Path(f) for f in glob(str(dsl_dir / "**/*.dsl"), recursive=True)]
    modules = parse_modules(dsl_files)

    # Build AppSpec
    appspec = build_appspec(modules, manifest.project_root)

    # Generate E2ETestSpec (pass manifest for auth test generation)
    testspec = generate_e2e_testspec(appspec, manifest)

    # Generate test file
    test_file = output_dir / f"test_{appspec.name.lower()}_generated.py"
    return generate_test_file(testspec, test_file)
