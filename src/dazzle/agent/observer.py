"""
Observer backends for the Dazzle Agent.

PlaywrightObserver gives the agent full DOM access via Playwright and
produces the PageState model behind the Observer protocol.
"""

import base64
import logging
from typing import Any, Protocol, runtime_checkable

from .models import Element, ObserverMode, PageState

logger = logging.getLogger(__name__)


# =============================================================================
# Protocol
# =============================================================================


@runtime_checkable
class Observer(Protocol):
    """Extracts structured page state from whatever backend."""

    async def observe(self) -> PageState:
        """Capture the current state of the page."""
        ...

    async def navigate(self, url: str) -> None:
        """Navigate to a URL."""
        ...

    @property
    def current_url(self) -> str:
        """The current URL."""
        ...


# =============================================================================
# Playwright Observer
# =============================================================================


_CLICKABLE_ROLES = frozenset({"button", "link", "menuitem", "tab", "checkbox", "radio", "switch"})
_INPUT_ROLES = frozenset({"textbox", "searchbox", "spinbutton", "combobox", "slider", "textarea"})

_MAX_CONSOLE = 50
_MAX_NETWORK = 50
_A11Y_DEPTH_CAP = 10
_A11Y_CLICKABLE_CAP = 50
_A11Y_INPUT_CAP = 30


class PlaywrightObserver:
    """
    Full DOM access via Playwright.

    Use for testing where you need real browser interactions, screenshots,
    and JavaScript-evaluated element state.

    Supports two observation modes:

    * ``dom`` (default) — scrapes the DOM via JavaScript evaluation.
    * ``accessibility`` — uses ``page.accessibility.snapshot()`` to build
      role-based selectors compatible with ``page.get_by_role()``.

    Optional console/network capture attaches error and warning messages
    from the browser console and failing network responses to ``PageState``.
    """

    def __init__(
        self,
        page: Any,
        include_screenshots: bool = True,
        mode: str = "dom",
        capture_console: bool = False,
        capture_network: bool = False,
    ):
        self._page = page
        self._include_screenshots = include_screenshots
        self._mode = ObserverMode(mode)
        self._capture_console = capture_console
        self._capture_network = capture_network
        self._console_buffer: list[dict[str, Any]] = []
        self._network_buffer: list[dict[str, Any]] = []

        if capture_console:
            page.on("console", self._on_console)
        if capture_network:
            page.on("response", self._on_response)

    def _on_console(self, msg: Any) -> None:
        if msg.type in ("error", "warning") and len(self._console_buffer) < _MAX_CONSOLE:
            location = msg.location if hasattr(msg, "location") else {}
            self._console_buffer.append(
                {
                    "level": msg.type,
                    "text": str(msg.text)[:500],
                    "url": (location.get("url", "") if isinstance(location, dict) else ""),
                    "line_number": (
                        location.get("lineNumber", 0) if isinstance(location, dict) else 0
                    ),
                }
            )

    def _on_response(self, response: Any) -> None:
        if response.status >= 400 and len(self._network_buffer) < _MAX_NETWORK:
            self._network_buffer.append(
                {
                    "url": str(response.url)[:200],
                    "status": response.status,
                    "method": response.request.method,
                }
            )

    @property
    def current_url(self) -> str:
        url: str = self._page.url
        return url

    async def navigate(self, url: str) -> None:
        # Match PlaywrightExecutor: workspace shells keep HTMX/SSE open, so
        # default "load"/unbounded networkidle can hang past 30s and abort
        # qa trials before step 1 (design_studio reviewer cold start).
        await self._page.goto(url, wait_until="domcontentloaded", timeout=60_000)
        try:
            await self._page.wait_for_load_state("networkidle", timeout=5_000)
        except Exception:
            # Expected when HTMX/SSE keeps the socket busy past 5s —
            # navigate already succeeded on domcontentloaded.
            logger.debug("networkidle wait timed out after navigate to %s", url, exc_info=True)

    async def observe(self) -> PageState:
        if self._mode == ObserverMode.ACCESSIBILITY:
            return await self._observe_accessibility()
        return await self._observe_dom()

    def _drain_buffers(self) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """Drain and return console/network buffers."""
        console = list(self._console_buffer)
        network = list(self._network_buffer)
        self._console_buffer.clear()
        self._network_buffer.clear()
        return console, network

    async def _observe_dom(self) -> PageState:
        """Original DOM-scraping observation mode."""
        url = self._page.url
        title = await self._page.title()
        clickables = await self._get_clickable_elements()
        inputs = await self._get_input_fields()
        visible_text = await self._get_visible_text()
        dazzle_attrs = await self._get_dazzle_attributes()

        screenshot_b64 = None
        if self._include_screenshots:
            screenshot_b64 = await self._take_screenshot()

        console_msgs, network_errs = self._drain_buffers()

        return PageState(
            url=url,
            title=title,
            clickables=clickables,
            inputs=inputs,
            visible_text=visible_text,
            screenshot_b64=screenshot_b64,
            dazzle_attributes=dazzle_attrs,
            console_messages=console_msgs,
            network_errors=network_errs,
        )

    async def _observe_accessibility(self) -> PageState:
        """Accessibility-snapshot observation mode."""
        url = self._page.url
        title = await self._page.title()

        snapshot = await self._page.accessibility.snapshot()
        clickables: list[Element] = []
        inputs: list[Element] = []
        a11y_tree: list[dict[str, Any]] = []

        if snapshot:
            self._flatten_a11y_tree(snapshot, clickables, inputs, a11y_tree, depth=0)

        visible_text = await self._get_visible_text()
        dazzle_attrs = await self._get_dazzle_attributes()

        screenshot_b64 = None
        if self._include_screenshots:
            screenshot_b64 = await self._take_screenshot()

        console_msgs, network_errs = self._drain_buffers()

        return PageState(
            url=url,
            title=title,
            clickables=clickables,
            inputs=inputs,
            visible_text=visible_text,
            screenshot_b64=screenshot_b64,
            dazzle_attributes=dazzle_attrs,
            accessibility_tree=a11y_tree,
            console_messages=console_msgs,
            network_errors=network_errs,
        )

    def _flatten_a11y_tree(
        self,
        node: dict[str, Any],
        clickables: list[Element],
        inputs: list[Element],
        a11y_tree: list[dict[str, Any]],
        depth: int,
    ) -> None:
        """Recursively walk an accessibility snapshot and extract elements."""
        if depth > _A11Y_DEPTH_CAP:
            return

        role = node.get("role", "")
        name = node.get("name", "")
        selector = self._build_a11y_selector(role, name)

        if role in _CLICKABLE_ROLES and len(clickables) < _A11Y_CLICKABLE_CAP:
            el = Element(tag=role, text=name, selector=selector, role=role)
            clickables.append(el)
            a11y_tree.append({"role": role, "name": name, "selector": selector})
        elif role in _INPUT_ROLES and len(inputs) < _A11Y_INPUT_CAP:
            el = Element(
                tag=role,
                text=name,
                selector=selector,
                role=role,
                attributes={"value": node.get("value", "")},
            )
            inputs.append(el)
            a11y_tree.append({"role": role, "name": name, "selector": selector})

        for child in node.get("children", []):
            self._flatten_a11y_tree(child, clickables, inputs, a11y_tree, depth + 1)

    @staticmethod
    def _build_a11y_selector(role: str, name: str) -> str:
        """Build a Playwright-compatible role selector."""
        if name:
            escaped = name.replace('"', '\\"')
            return f'role={role}[name="{escaped}"]'
        return f"role={role}"

    async def _get_clickable_elements(self) -> list[Element]:
        try:
            elements = await self._page.evaluate(
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
                        let selector = '';
                        if (el.id) {
                            selector = '#' + el.id;
                        } else if (el.dataset.testid) {
                            selector = `[data-testid="${el.dataset.testid}"]`;
                        } else {
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
            logger.warning("Error getting clickable elements: %s", e)
            return []

    async def _get_input_fields(self) -> list[Element]:
        try:
            elements = await self._page.evaluate(
                """() => {
                const inputs = document.querySelectorAll(
                    'input:not([type="hidden"]):not([type="submit"]):not([type="button"]), ' +
                    'textarea, select, [contenteditable="true"]'
                );
                return Array.from(inputs)
                    .filter(el => el.offsetParent !== null)
                    .slice(0, 30)
                    .map((el, index) => {
                        let label = '';
                        if (el.id) {
                            const labelEl = document.querySelector(`label[for="${el.id}"]`);
                            if (labelEl) label = labelEl.innerText.trim();
                        }
                        if (!label && el.placeholder) label = el.placeholder;
                        if (!label && el.name) label = el.name;

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
            logger.warning("Error getting input fields: %s", e)
            return []

    async def _get_visible_text(self) -> str:
        try:
            text = await self._page.evaluate(
                """() => {
                const mainContent = document.querySelector('main, [role="main"], .content, #content');
                if (mainContent) return mainContent.innerText.slice(0, 2000);
                return document.body.innerText.slice(0, 2000);
            }"""
            )
            return str(text).strip()
        except Exception as e:
            logger.warning("Error getting visible text: %s", e)
            return ""

    async def _get_dazzle_attributes(self) -> dict[str, list[str]]:
        """Extract data-dazzle-* attributes from the page."""
        try:
            attrs = await self._page.evaluate(
                """() => {
                const result = {};
                const els = document.querySelectorAll('[data-dazzle-view], [data-dazzle-entity], [data-dazzle-table], [data-dazzle-form], [data-dazzle-action], [data-dazzle-nav]');
                for (const el of els) {
                    for (const attr of el.attributes) {
                        if (attr.name.startsWith('data-dazzle-')) {
                            const key = attr.name;
                            if (!result[key]) result[key] = [];
                            if (!result[key].includes(attr.value)) {
                                result[key].push(attr.value);
                            }
                        }
                    }
                }
                return result;
            }"""
            )
            result: dict[str, list[str]] = attrs
            return result
        except Exception as e:
            logger.warning("Error getting dazzle attributes: %s", e)
            return {}

    async def _take_screenshot(self) -> str | None:
        try:
            screenshot_bytes = await self._page.screenshot(type="png", full_page=False)
            return base64.b64encode(screenshot_bytes).decode("utf-8")
        except Exception as e:
            logger.warning("Error taking screenshot: %s", e)
            return None
