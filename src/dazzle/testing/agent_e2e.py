"""
LLM-Agent E2E Testing Infrastructure.

This module provides goal-oriented E2E testing using an LLM agent
to drive browser interactions via Playwright.

The agent:
1. Observes the current page state (DOM, accessibility tree, screenshot)
2. Decides what action to take based on test goals
3. Executes actions via Playwright
4. Verifies outcomes

This is a backward-compatible wrapper around the generic DazzleAgent
framework at dazzle.agent. The underlying agent is mission-agnostic;
this module provides the E2E testing mission.

Usage:
    from dazzle.testing.agent_e2e import E2EAgent, run_agent_tests

    async with E2EAgent() as agent:
        result = await agent.run_test(page, test_spec)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from dazzle.agent.core import DazzleAgent
from dazzle.agent.executor import PlaywrightExecutor
from dazzle.agent.missions.testing import build_test_mission
from dazzle.agent.models import ActionType, Element, PageState
from dazzle.agent.observer import PlaywrightObserver
from dazzle.agent.transcript import AgentTranscript

logger = logging.getLogger("dazzle.testing.agent_e2e")


# =============================================================================
# Legacy Data Models (kept for backward compatibility)
# =============================================================================

# Re-export from agent.models for code that imports from here
ActionType = ActionType
Element = Element
PageState = PageState


@dataclass
class AgentAction:
    """An action decided by the agent."""

    type: ActionType
    target: str | None = None
    value: str | None = None
    reasoning: str = ""
    success: bool = True


@dataclass
class AgentStep:
    """A single step in the agent's execution."""

    state: PageState
    action: AgentAction
    result: str = ""
    error: str | None = None
    duration_ms: float = 0.0
    prompt: str = ""
    response: str = ""
    step_number: int = 0


@dataclass
class AgentTestResult:
    """Result of running an agent-based test."""

    test_id: str
    passed: bool
    steps: list[AgentStep] = field(default_factory=list)
    error: str | None = None
    duration_ms: float = 0.0
    reasoning: str = ""


# =============================================================================
# PageObserver (thin wrapper for backward compat)
# =============================================================================


class PageObserver:
    """
    Extracts semantic context from a Playwright page.

    This is a backward-compatible wrapper around PlaywrightObserver.
    """

    def __init__(self, include_screenshots: bool = True):
        self.include_screenshots = include_screenshots

    async def observe(self, page: Any) -> PageState:
        """Capture the current state of the page."""
        observer = PlaywrightObserver(page, include_screenshots=self.include_screenshots)
        return await observer.observe()


# =============================================================================
# E2E Agent (thin wrapper)
# =============================================================================


class E2EAgent:
    """
    LLM-driven E2E test agent.

    Backward-compatible wrapper around DazzleAgent with a testing mission.
    """

    MAX_STEPS = 15
    DEFAULT_MODEL = "claude-sonnet-4-20250514"

    def __init__(
        self,
        model: str | None = None,
        api_key: str | None = None,
        include_screenshots: bool = True,
    ):
        self.model = model or self.DEFAULT_MODEL
        self.api_key = api_key
        self.include_screenshots = include_screenshots

    async def __aenter__(self) -> E2EAgent:
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        pass

    async def run_test(
        self,
        page: Any,
        test_spec: dict[str, Any],
        base_url: str = "http://localhost:3000",
    ) -> AgentTestResult:
        """
        Run a single E2E test using the agent.

        Args:
            page: Playwright Page object
            test_spec: Test specification with goals and expected outcomes
            base_url: Base URL of the application

        Returns:
            AgentTestResult with pass/fail status and step details
        """
        test_id = test_spec.get("test_id", "unknown")

        # Build mission
        mission = build_test_mission(test_spec, base_url)

        # Create agent with Playwright backends
        observer = PlaywrightObserver(page, include_screenshots=self.include_screenshots)
        executor = PlaywrightExecutor(page)
        agent = DazzleAgent(observer, executor, model=self.model, api_key=self.api_key)

        # Run
        transcript = await agent.run(mission)

        # Convert transcript to legacy AgentTestResult
        return self._transcript_to_result(test_id, transcript)

    def _transcript_to_result(self, test_id: str, transcript: AgentTranscript) -> AgentTestResult:
        """Convert an AgentTranscript to the legacy AgentTestResult format."""
        steps: list[AgentStep] = []
        for step in transcript.steps:
            legacy_action = AgentAction(
                type=step.action.type,
                target=step.action.target,
                value=step.action.value,
                reasoning=step.action.reasoning,
                success=step.action.success,
            )
            legacy_step = AgentStep(
                state=step.state,
                action=legacy_action,
                result=step.result.message,
                error=step.result.error,
                duration_ms=step.duration_ms,
                prompt=step.prompt_text,
                response=step.response_text,
                step_number=step.step_number,
            )
            steps.append(legacy_step)

        # Determine pass/fail from last action
        passed = False
        reasoning = ""
        if transcript.steps:
            last_action = transcript.steps[-1].action
            if last_action.type == ActionType.DONE:
                passed = last_action.success
                reasoning = last_action.reasoning

        return AgentTestResult(
            test_id=test_id,
            passed=passed,
            steps=steps,
            error=transcript.error,
            duration_ms=transcript.duration_ms,
            reasoning=reasoning,
        )


# =============================================================================
# CLI Integration
# =============================================================================


def _load_env_file(project_path: Path) -> None:
    """Load environment variables from .env file if present."""
    import os

    search_paths = [project_path / ".env"]

    current = project_path
    while current != current.parent:
        if (current / ".git").exists() or (current / "dazzle.toml").exists():
            search_paths.append(current / ".env")
            break
        current = current.parent

    for env_path in search_paths:
        if env_path.exists():
            logger.debug(f"Loading environment from {env_path}")
            with open(env_path) as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        key, _, value = line.partition("=")
                        key = key.strip()
                        value = value.strip()
                        if key not in os.environ:
                            os.environ[key] = value
            break


async def run_agent_tests(
    project_path: Path,
    test_ids: list[str] | None = None,
    headless: bool = False,
    model: str | None = None,
    base_url: str | None = None,
) -> list[AgentTestResult]:
    """
    Run agent-based E2E tests for a project.

    Args:
        project_path: Path to the Dazzle project
        test_ids: Specific test IDs to run (None = all E2E tests)
        headless: Run browser in headless mode
        model: LLM model to use
        base_url: External server URL (skip server startup if provided)

    Returns:
        List of test results
    """
    _load_env_file(project_path)

    try:
        import playwright  # noqa: F401
    except ImportError:
        raise RuntimeError(
            "playwright package required. Install with: pip install playwright && playwright install chromium"
        )

    from dazzle.testing.browser_gate import get_browser_gate
    from dazzle.testing.unified_runner import UnifiedTestRunner

    runner = UnifiedTestRunner(project_path, base_url=base_url)

    if not runner.base_url and not runner.start_server():
        raise RuntimeError("Failed to start server")

    try:
        designs_path = project_path / "dsl" / "tests" / "dsl_generated_tests.json"
        if not designs_path.exists():
            raise FileNotFoundError(f"No tests found at {designs_path}")

        import json

        with open(designs_path) as f:
            data = json.load(f)

        def is_tier3_test(test: dict[str, Any]) -> bool:
            tags = set(test.get("tags", []))
            return bool(tags & {"tier3", "agent", "workspace", "persona", "navigation"})

        if test_ids:
            # When specific tests are requested, skip tag filtering
            agent_tests = [t for t in data.get("designs", []) if t.get("test_id") in test_ids]
        else:
            agent_tests = [d for d in data.get("designs", []) if is_tier3_test(d)]

        if not agent_tests:
            logger.info("No Tier 3 (agent) tests to run")
            return []

        results: list[AgentTestResult] = []
        base_url = runner.ui_url or runner.base_url or f"http://localhost:{runner.ui_port}"

        async with get_browser_gate().async_browser(headless=headless) as browser:
            context = await browser.new_context(viewport={"width": 1280, "height": 720})
            page = await context.new_page()

            async with E2EAgent(model=model) as agent:
                for test in agent_tests:
                    logger.info(f"Running: {test.get('test_id')}")
                    result = await agent.run_test(page, test, base_url)
                    results.append(result)

                    try:
                        await page.evaluate("localStorage.clear()")
                        await page.evaluate("sessionStorage.clear()")
                    except Exception:
                        pass  # localStorage may not be available on all pages

        return results

    finally:
        runner.stop_server()


# =============================================================================
# HTML Coverage Report
# =============================================================================


def generate_html_report(
    results: list[AgentTestResult],
    project_name: str,
    output_path: Path,
) -> Path:
    """
    Generate an HTML coverage report for agent E2E tests.

    Delegates to AgentTranscript.to_html_report for the generic report,
    but uses the legacy format for backward compatibility.
    """
    output_path.mkdir(parents=True, exist_ok=True)

    total = len(results)
    passed = sum(1 for r in results if r.passed)
    failed = total - passed
    total_steps = sum(len(r.steps) for r in results)
    total_duration = sum(r.duration_ms for r in results)
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Agent E2E Test Report - {project_name}</title>
    <style>
        :root {{
            --pass-color: #22c55e;
            --fail-color: #ef4444;
            --bg-color: #f8fafc;
            --card-bg: #ffffff;
            --border-color: #e2e8f0;
            --text-color: #1e293b;
            --text-muted: #64748b;
        }}
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: var(--bg-color);
            color: var(--text-color);
            line-height: 1.6;
            padding: 2rem;
        }}
        .container {{ max-width: 1400px; margin: 0 auto; }}
        h1 {{ font-size: 1.75rem; margin-bottom: 0.5rem; }}
        .timestamp {{ color: var(--text-muted); margin-bottom: 2rem; }}
        .summary {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
            gap: 1rem;
            margin-bottom: 2rem;
        }}
        .stat-card {{
            background: var(--card-bg);
            border: 1px solid var(--border-color);
            border-radius: 8px;
            padding: 1rem;
            text-align: center;
        }}
        .stat-value {{ font-size: 2rem; font-weight: bold; }}
        .stat-label {{ color: var(--text-muted); font-size: 0.875rem; }}
        .stat-pass {{ color: var(--pass-color); }}
        .stat-fail {{ color: var(--fail-color); }}
        .test-result {{
            background: var(--card-bg);
            border: 1px solid var(--border-color);
            border-radius: 8px;
            margin-bottom: 1.5rem;
            overflow: hidden;
        }}
        .test-header {{
            padding: 1rem;
            border-bottom: 1px solid var(--border-color);
            display: flex;
            align-items: center;
            gap: 0.75rem;
        }}
        .test-status {{ width: 12px; height: 12px; border-radius: 50%; }}
        .test-status.pass {{ background: var(--pass-color); }}
        .test-status.fail {{ background: var(--fail-color); }}
        .test-title {{ font-weight: 600; flex: 1; }}
        .test-meta {{ color: var(--text-muted); font-size: 0.875rem; }}
        .test-error {{
            background: #fef2f2; color: #991b1b; padding: 0.75rem 1rem;
            border-bottom: 1px solid var(--border-color);
            font-family: monospace; font-size: 0.875rem;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>Agent E2E Test Report</h1>
        <p class="timestamp">{project_name} &bull; {timestamp}</p>
        <div class="summary">
            <div class="stat-card"><div class="stat-value">{total}</div><div class="stat-label">Total Tests</div></div>
            <div class="stat-card"><div class="stat-value stat-pass">{passed}</div><div class="stat-label">Passed</div></div>
            <div class="stat-card"><div class="stat-value stat-fail">{failed}</div><div class="stat-label">Failed</div></div>
            <div class="stat-card"><div class="stat-value">{total_steps}</div><div class="stat-label">Total Steps</div></div>
            <div class="stat-card"><div class="stat-value">{total_duration / 1000:.1f}s</div><div class="stat-label">Duration</div></div>
        </div>
"""

    for result in results:
        status_class = "pass" if result.passed else "fail"
        html += f"""
        <div class="test-result">
            <div class="test-header">
                <div class="test-status {status_class}"></div>
                <span class="test-title">{result.test_id}</span>
                <span class="test-meta">{len(result.steps)} steps &bull; {result.duration_ms / 1000:.1f}s</span>
            </div>
"""
        if result.error:
            html += f'            <div class="test-error">{_escape_html(result.error)}</div>\n'
        html += "        </div>\n"

    html += """
    </div>
</body>
</html>
"""

    report_file = output_path / f"agent_e2e_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
    report_file.write_text(html)
    return report_file


def _escape_html(text: str) -> str:
    """Escape HTML special characters."""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;")
    )
