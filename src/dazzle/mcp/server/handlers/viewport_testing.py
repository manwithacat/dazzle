"""MCP handler for viewport assertion testing."""

import json
from pathlib import Path

from .common import (
    load_project_appspec,
)

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

    appspec = load_project_appspec(project_path)
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
