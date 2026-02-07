"""
Executor backends for the Dazzle Agent.

Two implementations:
- PlaywrightExecutor: Browser interactions via Playwright (for testing)
- HttpExecutor: HTTP requests with HTMX support (for discovery)

Both execute AgentActions and return ActionResults.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Protocol, runtime_checkable

from .models import ActionResult, ActionType, AgentAction

logger = logging.getLogger("dazzle.agent.executor")


# =============================================================================
# Protocol
# =============================================================================


@runtime_checkable
class Executor(Protocol):
    """Executes actions on a page."""

    async def execute(self, action: AgentAction) -> ActionResult:
        """Execute an action and return the result."""
        ...


# =============================================================================
# Playwright Executor
# =============================================================================


class PlaywrightExecutor:
    """
    Execute actions via Playwright page interactions.

    Use for testing where you need real browser behavior (JS execution,
    CSS rendering, network interception).
    """

    def __init__(self, page: Any):
        self._page = page

    async def execute(self, action: AgentAction) -> ActionResult:
        try:
            if action.type == ActionType.CLICK:
                await self._page.click(action.target, timeout=5000)
                await self._page.wait_for_load_state("networkidle", timeout=5000)
                return ActionResult(message=f"Clicked {action.target}")

            elif action.type == ActionType.TYPE:
                await self._page.fill(action.target, action.value or "", timeout=5000)
                return ActionResult(message=f"Typed '{action.value}' into {action.target}")

            elif action.type == ActionType.SELECT:
                await self._page.select_option(action.target, action.value, timeout=5000)
                return ActionResult(message=f"Selected '{action.value}' in {action.target}")

            elif action.type == ActionType.NAVIGATE:
                target = action.target or "/"
                if not target.startswith("http"):
                    base = self._page.url.split("/")[0:3]
                    target = "/".join(base) + target
                await self._page.goto(target)
                await self._page.wait_for_load_state("networkidle")
                return ActionResult(message=f"Navigated to {target}")

            elif action.type == ActionType.WAIT:
                await self._page.wait_for_selector(action.target, timeout=10000)
                return ActionResult(message=f"Found {action.target}")

            elif action.type == ActionType.ASSERT:
                try:
                    await self._page.wait_for_selector(action.target, timeout=3000)
                    return ActionResult(message=f"Assertion passed: {action.target} is visible")
                except Exception:
                    if await self._page.locator(f"text={action.target}").count() > 0:
                        return ActionResult(
                            message=f"Assertion passed: text '{action.target}' found"
                        )
                    return ActionResult(
                        message="",
                        error=f"Assertion failed: {action.target} not found",
                    )

            elif action.type == ActionType.SCROLL:
                await self._page.evaluate("window.scrollBy(0, 300)")
                return ActionResult(message="Scrolled down")

            elif action.type == ActionType.DONE:
                return ActionResult(message="Agent completed mission")

            elif action.type == ActionType.TOOL:
                # Tool actions are handled by the agent core, not the executor
                return ActionResult(message=f"Tool invocation: {action.target}")

            else:
                return ActionResult(message="", error=f"Unknown action type: {action.type}")

        except Exception as e:
            return ActionResult(message="", error=str(e))


# =============================================================================
# HTTP Executor
# =============================================================================


class HttpExecutor:
    """
    Execute actions via HTTP requests.

    Use for discovery where you don't need a full browser. Follows
    HTMX patterns (hx-target, hx-swap) and maintains cookie state.
    """

    def __init__(self, client: Any, base_url: str, observer: Any = None):
        """
        Args:
            client: httpx.AsyncClient with cookies configured
            base_url: Base URL of the application
            observer: Optional HttpObserver to update after navigation
        """
        self._client = client
        self._base_url = base_url.rstrip("/")
        self._observer = observer

    async def execute(self, action: AgentAction) -> ActionResult:
        try:
            if action.type == ActionType.NAVIGATE:
                return await self._navigate(action.target or "/")

            elif action.type == ActionType.CLICK:
                return await self._click(action)

            elif action.type == ActionType.TYPE:
                # HTTP executor stores form state; actual submission on CLICK/submit
                return ActionResult(
                    message=f"Set field {action.target} = '{action.value}'",
                    data={"field": action.target, "value": action.value},
                )

            elif action.type == ActionType.SELECT:
                return ActionResult(
                    message=f"Selected '{action.value}' for {action.target}",
                    data={"field": action.target, "value": action.value},
                )

            elif action.type == ActionType.ASSERT:
                # For HTTP executor, assert checks are based on last response content
                return ActionResult(
                    message=f"Assertion noted: {action.target}",
                    data={"assertion": action.target},
                )

            elif action.type == ActionType.WAIT:
                await asyncio.sleep(0.5)
                return ActionResult(message="Waited")

            elif action.type == ActionType.SCROLL:
                return ActionResult(message="Scroll (no-op for HTTP)")

            elif action.type == ActionType.DONE:
                return ActionResult(message="Agent completed mission")

            elif action.type == ActionType.TOOL:
                return ActionResult(message=f"Tool invocation: {action.target}")

            else:
                return ActionResult(message="", error=f"Unknown action type: {action.type}")

        except Exception as e:
            return ActionResult(message="", error=str(e))

    async def _navigate(self, url: str) -> ActionResult:
        """Navigate via HTTP GET."""
        if not url.startswith("http"):
            url = self._base_url + url
        response = await self._client.get(url, follow_redirects=True)
        if self._observer:
            self._observer._current_url = str(response.url)
            self._observer._last_html = response.text
        if response.status_code >= 400:
            return ActionResult(
                message=f"GET {url}",
                error=f"HTTP {response.status_code}",
            )
        return ActionResult(message=f"Navigated to {response.url}")

    async def _click(self, action: AgentAction) -> ActionResult:
        """Handle click by following href or hx-get/hx-post."""
        target = action.target or ""

        # If the target looks like a URL or path, navigate
        if target.startswith("/") or target.startswith("http"):
            return await self._navigate(target)

        # If target has href attribute info in the value, follow it
        if action.value and action.value.startswith("/"):
            return await self._navigate(action.value)

        # For hx-post targets, submit a POST
        if action.value and action.value.startswith("hx-post:"):
            post_url = action.value.replace("hx-post:", "")
            if not post_url.startswith("http"):
                post_url = self._base_url + post_url
            response = await self._client.post(post_url, follow_redirects=True)
            if self._observer:
                self._observer._current_url = str(response.url)
                self._observer._last_html = response.text
            return ActionResult(message=f"POST {post_url} -> {response.status_code}")

        return ActionResult(
            message=f"Click on {target}",
            data={"note": "HTTP executor: click may need URL context"},
        )
