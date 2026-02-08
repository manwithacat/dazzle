"""MCP handler for viewport assertion testing."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from dazzle.core.loader import load_and_link


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
    from dazzle.testing.viewport import derive_patterns_from_appspec
    from dazzle.testing.viewport_runner import ViewportRunner, ViewportRunOptions

    project = Path(project_path)
    if not project.is_dir():
        return json.dumps({"error": f"Project directory not found: {project_path}"})

    try:
        appspec = load_and_link(project)
    except Exception as exc:
        return json.dumps({"error": f"Failed to load AppSpec: {exc}"})

    patterns = derive_patterns_from_appspec(appspec)

    # Merge custom viewport specs if any
    from dazzle.testing.viewport_specs import (
        convert_to_patterns,
        load_custom_viewport_specs,
        merge_patterns,
    )

    custom_specs = load_custom_viewport_specs(project)
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

    runner = ViewportRunner(project)
    options = ViewportRunOptions(
        headless=headless,
        viewports=viewports,
        persona_id=persona_id,
        capture_screenshots=capture_screenshots,
        update_baselines=update_baselines,
    )
    result = runner.run(patterns, options)

    return result.to_json()


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
    from dazzle.testing.viewport_specs import (
        ViewportSpecEntry,
        load_custom_viewport_specs,
        save_custom_viewport_specs,
    )

    project = Path(project_path)
    if not project.is_dir():
        return json.dumps({"error": f"Project directory not found: {project_path}"})

    if operation == "list_viewport_specs":
        entries = load_custom_viewport_specs(project)
        return json.dumps(
            {
                "specs": [e.model_dump() for e in entries],
                "count": len(entries),
            },
            indent=2,
        )
    elif operation == "save_viewport_specs":
        if not specs:
            return json.dumps({"error": "No specs provided"})
        try:
            entries = [ViewportSpecEntry(**s) for s in specs]
        except Exception as exc:
            return json.dumps({"error": f"Invalid spec format: {exc}"})
        path = save_custom_viewport_specs(project, entries, to_dsl=to_dsl)
        return json.dumps(
            {
                "saved": True,
                "path": str(path),
                "count": len(entries),
            }
        )
    else:
        return json.dumps({"error": f"Unknown viewport spec operation: {operation}"})
