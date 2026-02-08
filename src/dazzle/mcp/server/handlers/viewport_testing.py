"""MCP handler for viewport assertion testing."""

from __future__ import annotations

import json
from pathlib import Path

from dazzle.core.loader import load_and_link


def run_viewport_tests_handler(
    project_path: str,
    headless: bool = True,
    viewports: list[str] | None = None,
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
    )
    result = runner.run(patterns, options)

    return result.to_json()
