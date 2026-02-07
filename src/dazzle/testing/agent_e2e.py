"""
LLM-Agent E2E Testing Infrastructure.

This module provides goal-oriented E2E testing using an LLM agent
to drive browser interactions via Playwright.

The agent:
1. Observes the current page state (DOM, accessibility tree, screenshot)
2. Decides what action to take based on test goals
3. Executes actions via Playwright
4. Verifies outcomes

Usage:
    from dazzle.testing.agent_e2e import E2EAgent, run_agent_tests

    async with E2EAgent() as agent:
        result = await agent.run_test(page, test_spec)
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

logger = logging.getLogger("dazzle.testing.agent_e2e")


# =============================================================================
# Data Models
# =============================================================================


class ActionType(StrEnum):
    """Types of actions the agent can take."""

    CLICK = "click"
    TYPE = "type"
    SELECT = "select"
    SCROLL = "scroll"
    NAVIGATE = "navigate"
    WAIT = "wait"
    ASSERT = "assert"
    DONE = "done"


@dataclass
class Element:
    """A UI element on the page."""

    tag: str
    text: str
    selector: str
    role: str | None = None
    rect: dict[str, float] | None = None
    attributes: dict[str, str] = field(default_factory=dict)


@dataclass
class PageState:
    """Captured state of a page for agent observation."""

    url: str
    title: str
    clickables: list[Element] = field(default_factory=list)
    inputs: list[Element] = field(default_factory=list)
    visible_text: str = ""
    screenshot_b64: str | None = None
    timestamp: datetime = field(default_factory=datetime.now)

    def to_prompt(self, include_screenshot: bool = True) -> str:
        """Convert page state to a prompt for the LLM."""
        lines = [
            "## Current Page State",
            f"URL: {self.url}",
            f"Title: {self.title}",
            "",
            "### Clickable Elements",
        ]

        for i, el in enumerate(self.clickables[:20]):  # Limit for context
            text_preview = el.text[:50] + "..." if len(el.text) > 50 else el.text
            lines.append(f'  [{i}] {el.tag}: "{text_preview}" (selector: {el.selector})')

        lines.append("")
        lines.append("### Input Fields")

        for i, el in enumerate(self.inputs[:15]):
            placeholder = el.attributes.get("placeholder", "")
            lines.append(f"  [{i}] {el.tag}: {placeholder} (selector: {el.selector})")

        if self.visible_text:
            lines.append("")
            lines.append("### Visible Text (excerpt)")
            lines.append(self.visible_text[:500])

        return "\n".join(lines)


@dataclass
class AgentAction:
    """An action decided by the agent."""

    type: ActionType
    target: str | None = None  # Selector or URL
    value: str | None = None  # Text to type, option to select
    reasoning: str = ""
    success: bool = True  # For DONE action


@dataclass
class AgentStep:
    """A single step in the agent's execution."""

    state: PageState
    action: AgentAction
    result: str = ""
    error: str | None = None
    duration_ms: float = 0.0
    # For coverage report
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
# Page Observer
# =============================================================================


class PageObserver:
    """
    Extracts semantic context from a Playwright page.

    This provides the "eyes" for the LLM agent, converting the DOM
    into a structured representation suitable for prompting.
    """

    def __init__(self, include_screenshots: bool = True):
        self.include_screenshots = include_screenshots

    async def observe(self, page: Any) -> PageState:
        """
        Capture the current state of the page.

        Args:
            page: Playwright Page object

        Returns:
            PageState with extracted elements and optional screenshot
        """
        url = page.url
        title = await page.title()

        # Get clickable elements
        clickables = await self._get_clickable_elements(page)

        # Get input fields
        inputs = await self._get_input_fields(page)

        # Get visible text
        visible_text = await self._get_visible_text(page)

        # Take screenshot if enabled
        screenshot_b64 = None
        if self.include_screenshots:
            screenshot_b64 = await self._take_screenshot(page)

        return PageState(
            url=url,
            title=title,
            clickables=clickables,
            inputs=inputs,
            visible_text=visible_text,
            screenshot_b64=screenshot_b64,
        )

    async def _get_clickable_elements(self, page: Any) -> list[Element]:
        """Get all clickable elements with their labels and selectors."""
        try:
            elements = await page.evaluate(
                """() => {
                const clickables = document.querySelectorAll(
                    'button, a, [role="button"], [role="tab"], [role="menuitem"], ' +
                    '[role="link"], [onclick], input[type="submit"], input[type="button"]'
                );
                return Array.from(clickables)
                    .filter(el => {
                        const rect = el.getBoundingClientRect();
                        return rect.width > 0 && rect.height > 0 && el.offsetParent !== null;
                    })
                    .slice(0, 50)
                    .map((el, index) => {
                        // Generate a reliable selector
                        let selector = '';
                        if (el.id) {
                            selector = '#' + el.id;
                        } else if (el.dataset.testid) {
                            selector = `[data-testid="${el.dataset.testid}"]`;
                        } else {
                            // Use text content or index-based selector
                            const text = el.innerText.trim().slice(0, 30);
                            if (text) {
                                selector = `${el.tagName.toLowerCase()}:has-text("${text}")`;
                            } else {
                                selector = `${el.tagName.toLowerCase()}:nth-of-type(${index + 1})`;
                            }
                        }

                        return {
                            tag: el.tagName.toLowerCase(),
                            text: el.innerText.trim().slice(0, 100),
                            selector: selector,
                            role: el.getAttribute('role'),
                            rect: el.getBoundingClientRect().toJSON(),
                            attributes: {
                                href: el.getAttribute('href') || '',
                                type: el.getAttribute('type') || '',
                                'aria-label': el.getAttribute('aria-label') || ''
                            }
                        };
                    });
            }"""
            )
            return [Element(**el) for el in elements]
        except Exception as e:
            logger.warning(f"Error getting clickable elements: {e}")
            return []

    async def _get_input_fields(self, page: Any) -> list[Element]:
        """Get all input fields with their labels and current values."""
        try:
            elements = await page.evaluate(
                """() => {
                const inputs = document.querySelectorAll(
                    'input:not([type="hidden"]):not([type="submit"]):not([type="button"]), ' +
                    'textarea, select, [contenteditable="true"]'
                );
                return Array.from(inputs)
                    .filter(el => el.offsetParent !== null)
                    .slice(0, 30)
                    .map((el, index) => {
                        // Find associated label
                        let label = '';
                        if (el.id) {
                            const labelEl = document.querySelector(`label[for="${el.id}"]`);
                            if (labelEl) label = labelEl.innerText.trim();
                        }
                        if (!label && el.placeholder) {
                            label = el.placeholder;
                        }
                        if (!label && el.name) {
                            label = el.name;
                        }

                        // Generate selector
                        let selector = '';
                        if (el.id) {
                            selector = '#' + el.id;
                        } else if (el.name) {
                            selector = `[name="${el.name}"]`;
                        } else {
                            selector = `${el.tagName.toLowerCase()}:nth-of-type(${index + 1})`;
                        }

                        return {
                            tag: el.tagName.toLowerCase(),
                            text: label,
                            selector: selector,
                            role: el.getAttribute('role'),
                            attributes: {
                                type: el.getAttribute('type') || '',
                                name: el.getAttribute('name') || '',
                                placeholder: el.getAttribute('placeholder') || '',
                                value: el.value || '',
                                required: el.required ? 'true' : 'false'
                            }
                        };
                    });
            }"""
            )
            return [Element(**el) for el in elements]
        except Exception as e:
            logger.warning(f"Error getting input fields: {e}")
            return []

    async def _get_visible_text(self, page: Any) -> str:
        """Get the visible text content of the page."""
        try:
            text = await page.evaluate(
                """() => {
                // Get text from main content areas
                const mainContent = document.querySelector('main, [role="main"], .content, #content');
                if (mainContent) {
                    return mainContent.innerText.slice(0, 2000);
                }
                return document.body.innerText.slice(0, 2000);
            }"""
            )
            return str(text).strip()
        except Exception as e:
            logger.warning(f"Error getting visible text: {e}")
            return ""

    async def _take_screenshot(self, page: Any) -> str | None:
        """Take a screenshot and return as base64."""
        try:
            screenshot_bytes = await page.screenshot(type="png", full_page=False)
            return base64.b64encode(screenshot_bytes).decode("utf-8")
        except Exception as e:
            logger.warning(f"Error taking screenshot: {e}")
            return None


# =============================================================================
# E2E Agent
# =============================================================================


class E2EAgent:
    """
    LLM-driven E2E test agent.

    Uses Claude to observe pages and decide actions based on test goals.
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
        self.observer = PageObserver(include_screenshots=include_screenshots)
        self._client: Any = None

    async def __aenter__(self) -> E2EAgent:
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Async context manager exit."""
        pass

    def _get_client(self) -> Any:
        """Get or create Anthropic client."""
        if self._client is None:
            try:
                import anthropic

                # Only pass api_key if explicitly provided, otherwise use env var
                if self.api_key:
                    self._client = anthropic.Anthropic(api_key=self.api_key)
                else:
                    self._client = anthropic.Anthropic()
            except ImportError:
                raise RuntimeError(
                    "anthropic package required for agent E2E tests. "
                    "Install with: pip install anthropic"
                )
        return self._client

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
        description = test_spec.get("description", test_spec.get("title", ""))
        expected_outcomes = test_spec.get("expected_outcomes", [])

        start_time = datetime.now()
        steps: list[AgentStep] = []

        # Build system prompt
        system = self._build_system_prompt(description, expected_outcomes)

        # Navigate to starting point
        try:
            await page.goto(base_url)
            await page.wait_for_load_state("networkidle")
        except Exception as e:
            return AgentTestResult(
                test_id=test_id,
                passed=False,
                error=f"Failed to navigate to {base_url}: {e}",
                duration_ms=(datetime.now() - start_time).total_seconds() * 1000,
            )

        # Agent loop
        for step_num in range(self.MAX_STEPS):
            step_start = datetime.now()

            # Observe current state
            state = await self.observer.observe(page)

            # Get action from LLM
            try:
                action, prompt_text, response_text = await self._get_action(system, state, steps)
            except Exception as e:
                return AgentTestResult(
                    test_id=test_id,
                    passed=False,
                    steps=steps,
                    error=f"LLM error at step {step_num + 1}: {e}",
                    duration_ms=(datetime.now() - start_time).total_seconds() * 1000,
                )

            # Execute action
            result, error = await self._execute_action(page, action)

            step = AgentStep(
                state=state,
                action=action,
                result=result,
                error=error,
                duration_ms=(datetime.now() - step_start).total_seconds() * 1000,
                prompt=prompt_text,
                response=response_text,
                step_number=step_num + 1,
            )
            steps.append(step)

            # Check if done
            if action.type == ActionType.DONE:
                return AgentTestResult(
                    test_id=test_id,
                    passed=action.success,
                    steps=steps,
                    reasoning=action.reasoning,
                    duration_ms=(datetime.now() - start_time).total_seconds() * 1000,
                )

            # Small delay between actions
            await asyncio.sleep(0.5)

        # Max steps exceeded
        return AgentTestResult(
            test_id=test_id,
            passed=False,
            steps=steps,
            error=f"Max steps ({self.MAX_STEPS}) exceeded without completion",
            duration_ms=(datetime.now() - start_time).total_seconds() * 1000,
        )

    def _build_system_prompt(self, description: str, expected_outcomes: list[str]) -> str:
        """Build the system prompt for the agent."""
        outcomes_text = "\n".join(f"  - {o}" for o in expected_outcomes)

        return f"""You are an E2E test agent. Your goal is to test a web application by navigating and interacting with it.

## Test Goal
{description}

## Expected Outcomes
{outcomes_text}

## Available Actions
You can respond with one of these actions in JSON format:

1. click - Click an element
   {{"action": "click", "target": "selector", "reasoning": "why"}}

2. type - Type text into an input
   {{"action": "type", "target": "selector", "value": "text to type", "reasoning": "why"}}

3. select - Select an option from a dropdown
   {{"action": "select", "target": "selector", "value": "option value", "reasoning": "why"}}

4. navigate - Navigate to a URL
   {{"action": "navigate", "target": "/path", "reasoning": "why"}}

5. wait - Wait for something to appear
   {{"action": "wait", "target": "selector or text", "reasoning": "why"}}

6. assert - Verify something is visible/correct
   {{"action": "assert", "target": "what to check", "reasoning": "why"}}

7. done - Test is complete
   {{"action": "done", "success": true/false, "reasoning": "summary of what was verified"}}

## Rules
1. Analyze the current page state carefully
2. Take one action at a time toward the goal
3. Use the most reliable selectors (IDs, data-testid, unique text)
4. Call "done" when the test goal is achieved or you determine it cannot be achieved
5. Keep reasoning concise but informative

## CRITICAL OUTPUT FORMAT
You MUST respond with ONLY a single JSON object. No text before or after.
Do NOT explain your thinking outside the JSON.
Do NOT use markdown code blocks.
Your entire response must be parseable as JSON.

Example valid response:
{{"action": "click", "target": "#submit-btn", "reasoning": "Submit the form"}}"""

    async def _get_action(
        self, system: str, state: PageState, history: list[AgentStep]
    ) -> tuple[AgentAction, str, str]:
        """Get the next action from the LLM.

        Returns:
            Tuple of (action, prompt_text, response_text) for coverage report.
        """
        # Build conversation messages
        messages: list[dict[str, str | list[dict[str, Any]]]] = []

        # Add history context
        history_text = ""
        if history:
            history_text = "## Previous Actions\n"
            for i, step in enumerate(history[-5:]):  # Last 5 steps
                history_text += f"{i + 1}. {step.action.type.value}: {step.action.target}"
                if step.error:
                    history_text += f" (ERROR: {step.error})"
                history_text += "\n"
            messages.append({"role": "user", "content": history_text})
            messages.append(
                {
                    "role": "assistant",
                    "content": "I understand the history. What's the current state?",
                }
            )

        # Add current state
        content: list[dict[str, Any]] = []

        # Add screenshot if available
        if state.screenshot_b64:
            content.append(
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/png",
                        "data": state.screenshot_b64,
                    },
                }
            )

        # Add text description
        page_state_text = state.to_prompt()
        content.append({"type": "text", "text": page_state_text})

        messages.append({"role": "user", "content": content})

        # Build prompt text for report (without image data)
        prompt_text = f"## System\n{system}\n\n"
        if history_text:
            prompt_text += f"{history_text}\n"
        prompt_text += f"{page_state_text}"

        # Call LLM
        client = self._get_client()
        response = client.messages.create(
            model=self.model,
            max_tokens=500,
            system=system,
            messages=messages,
        )

        # Parse response
        response_text = response.content[0].text.strip()
        action = self._parse_action(response_text)

        return action, prompt_text, response_text

    def _parse_action(self, response: str) -> AgentAction:
        """Parse the LLM response into an AgentAction."""
        # Try to extract JSON from the response
        try:
            # Handle potential markdown code blocks
            if "```" in response:
                match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", response, re.DOTALL)
                if match:
                    response = match.group(1)

            data = json.loads(response)

            action_type = ActionType(data.get("action", "done"))
            return AgentAction(
                type=action_type,
                target=data.get("target"),
                value=data.get("value"),
                reasoning=data.get("reasoning", ""),
                success=data.get("success", True),
            )
        except (json.JSONDecodeError, ValueError) as e:
            logger.warning(f"Failed to parse action: {e}, response: {response[:200]}")
            return AgentAction(
                type=ActionType.DONE,
                success=False,
                reasoning=f"Failed to parse LLM response: {response[:100]}",
            )

    async def _execute_action(self, page: Any, action: AgentAction) -> tuple[str, str | None]:
        """
        Execute an action on the page.

        Returns:
            Tuple of (result message, error message or None)
        """
        try:
            if action.type == ActionType.CLICK:
                await page.click(action.target, timeout=5000)
                await page.wait_for_load_state("networkidle", timeout=5000)
                return f"Clicked {action.target}", None

            elif action.type == ActionType.TYPE:
                await page.fill(action.target, action.value or "", timeout=5000)
                return f"Typed '{action.value}' into {action.target}", None

            elif action.type == ActionType.SELECT:
                await page.select_option(action.target, action.value, timeout=5000)
                return f"Selected '{action.value}' in {action.target}", None

            elif action.type == ActionType.NAVIGATE:
                target = action.target or "/"
                if not target.startswith("http"):
                    base = page.url.split("/")[0:3]
                    target = "/".join(base) + target
                await page.goto(target)
                await page.wait_for_load_state("networkidle")
                return f"Navigated to {target}", None

            elif action.type == ActionType.WAIT:
                await page.wait_for_selector(action.target, timeout=10000)
                return f"Found {action.target}", None

            elif action.type == ActionType.ASSERT:
                # Check if element or text is visible
                try:
                    await page.wait_for_selector(action.target, timeout=3000)
                    return f"Assertion passed: {action.target} is visible", None
                except Exception:
                    # Try as text
                    if await page.locator(f"text={action.target}").count() > 0:
                        return f"Assertion passed: text '{action.target}' found", None
                    return "", f"Assertion failed: {action.target} not found"

            elif action.type == ActionType.DONE:
                return "Test completed", None

            elif action.type == ActionType.SCROLL:
                await page.evaluate("window.scrollBy(0, 300)")
                return "Scrolled down", None

            else:
                return "", f"Unknown action type: {action.type}"

        except Exception as e:
            return "", str(e)


# =============================================================================
# CLI Integration
# =============================================================================


def _load_env_file(project_path: Path) -> None:
    """Load environment variables from .env file if present."""
    import os

    # Try project-level .env first, then parent directories up to repo root
    search_paths = [project_path / ".env"]

    # Walk up to find repo root (has .git or dazzle.toml)
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
                        # Only set if not already in environment
                        if key not in os.environ:
                            os.environ[key] = value
            break


async def run_agent_tests(
    project_path: Path,
    test_ids: list[str] | None = None,
    headless: bool = False,
    model: str | None = None,
) -> list[AgentTestResult]:
    """
    Run agent-based E2E tests for a project.

    Args:
        project_path: Path to the Dazzle project
        test_ids: Specific test IDs to run (None = all E2E tests)
        headless: Run browser in headless mode
        model: LLM model to use

    Returns:
        List of test results
    """
    # Load .env file if present
    _load_env_file(project_path)

    try:
        from playwright.async_api import async_playwright
    except ImportError:
        raise RuntimeError(
            "playwright package required. Install with: pip install playwright && playwright install chromium"
        )

    # Load test specs
    from dazzle.testing.unified_runner import UnifiedTestRunner

    runner = UnifiedTestRunner(project_path)

    # Start server
    if not runner.start_server():
        raise RuntimeError("Failed to start server")

    try:
        # Get E2E tests
        designs_path = project_path / "dsl" / "tests" / "dsl_generated_tests.json"
        if not designs_path.exists():
            raise FileNotFoundError(f"No tests found at {designs_path}")

        import json

        with open(designs_path) as f:
            data = json.load(f)

        # Filter for Tier 3 (agent) tests - these require LLM-driven testing
        # Tier 3 tests are tagged with "tier3" or "agent"
        # Note: "tier2" or "playwright" tags are for scripted Playwright tests
        def is_tier3_test(test: dict[str, Any]) -> bool:
            tags = set(test.get("tags", []))
            return bool(tags & {"tier3", "agent"})

        agent_tests = [d for d in data.get("designs", []) if is_tier3_test(d)]

        if test_ids:
            agent_tests = [t for t in agent_tests if t.get("test_id") in test_ids]

        if not agent_tests:
            logger.info("No Tier 3 (agent) tests to run")
            return []

        # Run tests
        results: list[AgentTestResult] = []
        base_url = f"http://localhost:{runner.ui_port}"

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=headless)
            context = await browser.new_context(viewport={"width": 1280, "height": 720})
            page = await context.new_page()

            async with E2EAgent(model=model) as agent:
                for test in agent_tests:
                    logger.info(f"Running: {test.get('test_id')}")
                    result = await agent.run_test(page, test, base_url)
                    results.append(result)

                    # Clear state between tests
                    await page.evaluate("localStorage.clear()")
                    await page.evaluate("sessionStorage.clear()")

            await browser.close()

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

    Args:
        results: List of test results
        project_name: Name of the project
        output_path: Directory to save the report

    Returns:
        Path to the generated HTML file
    """
    output_path.mkdir(parents=True, exist_ok=True)

    # Calculate summary stats
    total = len(results)
    passed = sum(1 for r in results if r.passed)
    failed = total - passed
    total_steps = sum(len(r.steps) for r in results)
    total_duration = sum(r.duration_ms for r in results)

    # Generate timestamp
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Build HTML
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

        /* Summary Cards */
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

        /* Test Results */
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
        .test-status {{
            width: 12px;
            height: 12px;
            border-radius: 50%;
        }}
        .test-status.pass {{ background: var(--pass-color); }}
        .test-status.fail {{ background: var(--fail-color); }}
        .test-title {{ font-weight: 600; flex: 1; }}
        .test-meta {{ color: var(--text-muted); font-size: 0.875rem; }}
        .test-error {{
            background: #fef2f2;
            color: #991b1b;
            padding: 0.75rem 1rem;
            border-bottom: 1px solid var(--border-color);
            font-family: monospace;
            font-size: 0.875rem;
        }}
        .test-reasoning {{
            background: #f0fdf4;
            color: #166534;
            padding: 0.75rem 1rem;
            border-bottom: 1px solid var(--border-color);
        }}

        /* Steps */
        .steps {{ padding: 1rem; }}
        .step {{
            border: 1px solid var(--border-color);
            border-radius: 6px;
            margin-bottom: 1rem;
        }}
        .step-header {{
            padding: 0.75rem 1rem;
            background: #f8fafc;
            border-bottom: 1px solid var(--border-color);
            display: flex;
            align-items: center;
            gap: 0.75rem;
            cursor: pointer;
        }}
        .step-header:hover {{ background: #f1f5f9; }}
        .step-number {{
            background: var(--text-color);
            color: white;
            width: 24px;
            height: 24px;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 0.75rem;
            font-weight: bold;
        }}
        .step-action {{ font-weight: 500; }}
        .step-target {{ color: var(--text-muted); font-family: monospace; font-size: 0.875rem; }}
        .step-duration {{ margin-left: auto; color: var(--text-muted); font-size: 0.875rem; }}
        .step-error-badge {{
            background: var(--fail-color);
            color: white;
            padding: 0.125rem 0.5rem;
            border-radius: 4px;
            font-size: 0.75rem;
        }}
        .step-content {{ display: none; padding: 1rem; border-top: 1px solid var(--border-color); }}
        .step.expanded .step-content {{ display: block; }}

        /* Screenshot */
        .screenshot {{
            max-width: 100%;
            border: 1px solid var(--border-color);
            border-radius: 4px;
            margin-bottom: 1rem;
        }}

        /* Collapsible sections */
        .collapsible {{
            margin-bottom: 1rem;
        }}
        .collapsible-header {{
            background: #f1f5f9;
            padding: 0.5rem 1rem;
            cursor: pointer;
            border-radius: 4px;
            font-weight: 500;
            font-size: 0.875rem;
        }}
        .collapsible-header:hover {{ background: #e2e8f0; }}
        .collapsible-content {{
            display: none;
            padding: 1rem;
            background: #f8fafc;
            border-radius: 0 0 4px 4px;
            font-family: monospace;
            font-size: 0.8rem;
            white-space: pre-wrap;
            word-break: break-word;
            max-height: 400px;
            overflow-y: auto;
        }}
        .collapsible.expanded .collapsible-content {{ display: block; }}

        /* Result/Error in step */
        .step-result {{
            padding: 0.5rem;
            border-radius: 4px;
            font-size: 0.875rem;
            margin-top: 0.5rem;
        }}
        .step-result.success {{ background: #f0fdf4; color: #166534; }}
        .step-result.error {{ background: #fef2f2; color: #991b1b; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>Agent E2E Test Report</h1>
        <p class="timestamp">{project_name} • {timestamp}</p>

        <div class="summary">
            <div class="stat-card">
                <div class="stat-value">{total}</div>
                <div class="stat-label">Total Tests</div>
            </div>
            <div class="stat-card">
                <div class="stat-value stat-pass">{passed}</div>
                <div class="stat-label">Passed</div>
            </div>
            <div class="stat-card">
                <div class="stat-value stat-fail">{failed}</div>
                <div class="stat-label">Failed</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">{total_steps}</div>
                <div class="stat-label">Total Steps</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">{total_duration / 1000:.1f}s</div>
                <div class="stat-label">Duration</div>
            </div>
        </div>
"""

    # Add each test result
    for result in results:
        status_class = "pass" if result.passed else "fail"
        html += f"""
        <div class="test-result">
            <div class="test-header">
                <div class="test-status {status_class}"></div>
                <span class="test-title">{result.test_id}</span>
                <span class="test-meta">{len(result.steps)} steps • {result.duration_ms / 1000:.1f}s</span>
            </div>
"""

        if result.error:
            html += f'            <div class="test-error">{_escape_html(result.error)}</div>\n'

        if result.reasoning and result.passed:
            html += (
                f'            <div class="test-reasoning">{_escape_html(result.reasoning)}</div>\n'
            )

        html += '            <div class="steps">\n'

        # Add each step
        for step in result.steps:
            action_text = step.action.type.value
            target_text = step.action.target or ""
            error_badge = '<span class="step-error-badge">ERROR</span>' if step.error else ""

            html += f"""
                <div class="step" onclick="this.classList.toggle('expanded')">
                    <div class="step-header">
                        <span class="step-number">{step.step_number}</span>
                        <span class="step-action">{action_text}</span>
                        <span class="step-target">{_escape_html(target_text[:50])}</span>
                        {error_badge}
                        <span class="step-duration">{step.duration_ms:.0f}ms</span>
                    </div>
                    <div class="step-content">
"""

            # Screenshot
            if step.state.screenshot_b64:
                html += f'                        <img class="screenshot" src="data:image/png;base64,{step.state.screenshot_b64}" alt="Step {step.step_number} screenshot">\n'

            # Prompt (collapsible)
            if step.prompt:
                html += f"""
                        <div class="collapsible" onclick="event.stopPropagation(); this.classList.toggle('expanded')">
                            <div class="collapsible-header">📝 Prompt</div>
                            <div class="collapsible-content">{_escape_html(step.prompt)}</div>
                        </div>
"""

            # Response (collapsible)
            if step.response:
                html += f"""
                        <div class="collapsible" onclick="event.stopPropagation(); this.classList.toggle('expanded')">
                            <div class="collapsible-header">🤖 Response</div>
                            <div class="collapsible-content">{_escape_html(step.response)}</div>
                        </div>
"""

            # Result or error
            if step.result:
                html += f'                        <div class="step-result success">✓ {_escape_html(step.result)}</div>\n'
            if step.error:
                html += f'                        <div class="step-result error">✗ {_escape_html(step.error)}</div>\n'

            html += """
                    </div>
                </div>
"""

        html += "            </div>\n"  # Close steps
        html += "        </div>\n"  # Close test-result

    html += """
    </div>
</body>
</html>
"""

    # Write to file
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
