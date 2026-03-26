"""MCP handler for viewport assertion testing."""

import json
from pathlib import Path
from typing import Any

from dazzle.core.loader import load_and_link

from .common import error_response, extract_progress, unknown_op_response, wrap_handler_errors

# ---------------------------------------------------------------------------
# run_viewport
# ---------------------------------------------------------------------------


def run_viewport_tests_impl(
    project_path: Path,
    headless: bool,
    viewports: list[str] | None,
    persona_id: str | None,
    capture_screenshots: bool,
    update_baselines: bool,
) -> str:
    """Run viewport assertions against a running app.

    Loads the AppSpec, derives responsive patterns, then launches Playwright
    to check computed CSS properties at each viewport size.

    Returns JSON report string (via ViewportResult.to_json()).
    """
    from dazzle.testing.viewport import derive_patterns_from_appspec
    from dazzle.testing.viewport_runner import ViewportRunner, ViewportRunOptions
    from dazzle.testing.viewport_specs import (
        convert_to_patterns,
        load_custom_viewport_specs,
        merge_patterns,
    )

    appspec = load_and_link(project_path)
    patterns = derive_patterns_from_appspec(appspec)

    custom_specs = load_custom_viewport_specs(project_path)
    if custom_specs:
        custom_patterns = convert_to_patterns(custom_specs)
        patterns = merge_patterns(patterns, custom_patterns)

    if not patterns:
        return json.dumps(
            {
                "status": "skipped",
                "message": "No viewport patterns derived from AppSpec",
            }
        )

    runner = ViewportRunner(project_path)
    options = ViewportRunOptions(
        headless=headless,
        viewports=viewports,
        persona_id=persona_id,
        capture_screenshots=capture_screenshots,
        update_baselines=update_baselines,
    )
    result = runner.run(patterns, options)
    return result.to_json()


@wrap_handler_errors
def run_viewport_tests_handler(
    project_path: str,
    headless: bool = True,
    viewports: list[str] | None = None,
    persona_id: str | None = None,
    capture_screenshots: bool = False,
    update_baselines: bool = False,
) -> str:
    """Run viewport assertions against a running app.

    Loads the AppSpec, derives responsive patterns, then launches Playwright
    to check computed CSS properties at each viewport size.

    Returns JSON report.
    """
    progress = extract_progress(None)
    progress.log_sync("Running viewport tests...")

    project = Path(project_path)
    if not project.is_dir():
        return error_response(f"Project directory not found: {project_path}")

    return run_viewport_tests_impl(
        project_path=project,
        headless=headless,
        viewports=viewports,
        persona_id=persona_id,
        capture_screenshots=capture_screenshots,
        update_baselines=update_baselines,
    )


# ---------------------------------------------------------------------------
# list_viewport_specs / save_viewport_specs
# ---------------------------------------------------------------------------


def list_viewport_specs_impl(project_path: Path) -> dict[str, Any]:
    """List custom viewport specs for the project. Returns dict with specs list."""
    from dazzle.testing.viewport_specs import load_custom_viewport_specs

    entries = load_custom_viewport_specs(project_path)
    return {
        "specs": [e.model_dump() for e in entries],
        "count": len(entries),
    }


def save_viewport_specs_impl(
    project_path: Path,
    specs: list[dict[str, Any]],
    to_dsl: bool,
) -> dict[str, Any]:
    """Save custom viewport specs for the project. Returns dict with save result."""
    from dazzle.testing.viewport_specs import ViewportSpecEntry, save_custom_viewport_specs

    entries = [ViewportSpecEntry(**s) for s in specs]
    path = save_custom_viewport_specs(project_path, entries, to_dsl=to_dsl)
    return {
        "saved": True,
        "path": str(path),
        "count": len(entries),
    }


@wrap_handler_errors
def manage_viewport_specs_handler(
    project_path: str,
    operation: str,
    specs: list[dict[str, Any]] | None = None,
    to_dsl: bool = True,
) -> str:
    """Manage custom viewport specs (list/save).

    Parameters
    ----------
    project_path:
        Path to the project directory.
    operation:
        "list_viewport_specs" or "save_viewport_specs".
    specs:
        Specs to save (for save operation).
    to_dsl:
        Save to dsl/ directory (version-controlled).

    Returns JSON response.
    """
    progress = extract_progress(None)
    progress.log_sync("Managing viewport specs...")

    project = Path(project_path)
    if not project.is_dir():
        return error_response(f"Project directory not found: {project_path}")

    if operation == "list_viewport_specs":
        result = list_viewport_specs_impl(project)
        return json.dumps(result, indent=2)
    elif operation == "save_viewport_specs":
        if not specs:
            return error_response("No specs provided")
        result = save_viewport_specs_impl(project, specs, to_dsl=to_dsl)
        return json.dumps(result)
    else:
        return unknown_op_response(operation, "viewport spec")
