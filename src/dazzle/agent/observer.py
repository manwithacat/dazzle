"""
Observer backends for the Dazzle Agent.

Two implementations:
- PlaywrightObserver: Full DOM access via Playwright (for testing)
- HttpObserver: Lightweight HTTP + HTML parsing (for discovery)

Both produce the same PageState model, so the agent doesn't know
which backend it's using.
"""

from __future__ import annotations

import base64
import logging
import re
from typing import Any, Protocol, runtime_checkable

from .models import Element, PageState

logger = logging.getLogger("dazzle.agent.observer")


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


class PlaywrightObserver:
    """
    Full DOM access via Playwright.

    Use for testing where you need real browser interactions, screenshots,
    and JavaScript-evaluated element state.
    """

    def __init__(self, page: Any, include_screenshots: bool = True):
        self._page = page
        self._include_screenshots = include_screenshots

    @property
    def current_url(self) -> str:
        url: str = self._page.url
        return url

    async def navigate(self, url: str) -> None:
        await self._page.goto(url)
        await self._page.wait_for_load_state("networkidle")

    async def observe(self) -> PageState:
        url = self._page.url
        title = await self._page.title()
        clickables = await self._get_clickable_elements()
        inputs = await self._get_input_fields()
        visible_text = await self._get_visible_text()
        dazzle_attrs = await self._get_dazzle_attributes()

        screenshot_b64 = None
        if self._include_screenshots:
            screenshot_b64 = await self._take_screenshot()

        return PageState(
            url=url,
            title=title,
            clickables=clickables,
            inputs=inputs,
            visible_text=visible_text,
            screenshot_b64=screenshot_b64,
            dazzle_attributes=dazzle_attrs,
        )

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
            logger.warning(f"Error getting clickable elements: {e}")
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
            logger.warning(f"Error getting input fields: {e}")
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
            logger.warning(f"Error getting visible text: {e}")
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
            logger.warning(f"Error getting dazzle attributes: {e}")
            return {}

    async def _take_screenshot(self) -> str | None:
        try:
            screenshot_bytes = await self._page.screenshot(type="png", full_page=False)
            return base64.b64encode(screenshot_bytes).decode("utf-8")
        except Exception as e:
            logger.warning(f"Error taking screenshot: {e}")
            return None


# =============================================================================
# HTTP Observer
# =============================================================================


class HttpObserver:
    """
    Lightweight HTTP + HTML parsing observer.

    Use for discovery where token efficiency matters. Produces ~200-500 tokens
    per page vs 5000+ for Playwright.

    Extracts:
    - Links (a[href], [hx-get], [hx-post])
    - Forms (form, input, select, textarea)
    - data-dazzle-* semantic attributes
    - Visible text (main content area)
    """

    def __init__(self, client: Any, base_url: str):
        """
        Args:
            client: httpx.AsyncClient with cookies/auth configured
            base_url: Base URL of the application
        """
        self._client = client
        self._base_url = base_url.rstrip("/")
        self._current_url = base_url
        self._last_html = ""

    @property
    def current_url(self) -> str:
        return self._current_url

    async def navigate(self, url: str) -> None:
        if not url.startswith("http"):
            url = self._base_url + url
        response = await self._client.get(url, follow_redirects=True)
        response.raise_for_status()
        self._current_url = str(response.url)
        self._last_html = response.text

    async def observe(self) -> PageState:
        if not self._last_html:
            await self.navigate(self._current_url)

        html = self._last_html

        try:
            from bs4 import BeautifulSoup

            soup = BeautifulSoup(html, "html.parser")
        except ImportError:
            # Fallback to regex-based parsing
            return self._observe_regex(html)

        title = soup.title.string if soup.title else ""
        clickables = self._extract_clickables(soup)
        inputs = self._extract_inputs(soup)
        visible_text = self._extract_visible_text(soup)
        dazzle_attrs = self._extract_dazzle_attributes(soup)

        return PageState(
            url=self._current_url,
            title=title or "",
            clickables=clickables,
            inputs=inputs,
            visible_text=visible_text,
            dazzle_attributes=dazzle_attrs,
        )

    def _extract_clickables(self, soup: Any) -> list[Element]:
        """Extract clickable elements from HTML."""
        elements: list[Element] = []
        selectors = (
            "a[href], button, [role='button'], [hx-get], [hx-post], "
            "input[type='submit'], input[type='button']"
        )

        for el in soup.select(selectors)[:50]:
            text = el.get_text(strip=True)[:100]
            tag = el.name

            # Build selector
            if el.get("id"):
                selector = f"#{el['id']}"
            elif el.get("data-testid"):
                selector = f'[data-testid="{el["data-testid"]}"]'
            elif text:
                selector = f'{tag}:has-text("{text[:30]}")'
            else:
                selector = tag

            attrs: dict[str, str] = {}
            if el.get("href"):
                attrs["href"] = el["href"]
            if el.get("hx-get"):
                attrs["hx-get"] = el["hx-get"]
            if el.get("hx-post"):
                attrs["hx-post"] = el["hx-post"]
            if el.get("type"):
                attrs["type"] = el["type"]

            elements.append(
                Element(
                    tag=tag,
                    text=text,
                    selector=selector,
                    attributes=attrs,
                )
            )

        return elements

    def _extract_inputs(self, soup: Any) -> list[Element]:
        """Extract form input elements."""
        elements: list[Element] = []
        selectors = (
            "input:not([type='hidden']):not([type='submit']):not([type='button']), textarea, select"
        )

        for el in soup.select(selectors)[:30]:
            tag = el.name

            # Find label
            label = ""
            el_id = el.get("id", "")
            if el_id:
                label_el = soup.find("label", attrs={"for": el_id})
                if label_el:
                    label = label_el.get_text(strip=True)
            if not label:
                label = el.get("placeholder", "") or el.get("name", "")

            # Build selector
            if el_id:
                selector = f"#{el_id}"
            elif el.get("name"):
                selector = f'[name="{el["name"]}"]'
            else:
                selector = tag

            attrs: dict[str, str] = {
                "type": el.get("type", ""),
                "name": el.get("name", ""),
                "placeholder": el.get("placeholder", ""),
                "value": el.get("value", ""),
                "required": "true" if el.has_attr("required") else "false",
            }

            elements.append(
                Element(
                    tag=tag,
                    text=label,
                    selector=selector,
                    attributes=attrs,
                )
            )

        return elements

    def _extract_visible_text(self, soup: Any) -> str:
        """Extract visible text from main content area."""
        # Try main content areas first
        for selector in ["main", "[role='main']", ".content", "#content"]:
            main = soup.select_one(selector)
            if main:
                text: str = main.get_text(separator="\n", strip=True)[:2000]
                return text

        # Fallback to body
        body = soup.find("body")
        if body:
            text = body.get_text(separator="\n", strip=True)[:2000]
            return text
        return ""

    def _extract_dazzle_attributes(self, soup: Any) -> dict[str, list[str]]:
        """Extract all data-dazzle-* attributes."""
        attrs: dict[str, list[str]] = {}
        for el in soup.select(
            "[data-dazzle-view], [data-dazzle-entity], [data-dazzle-table], [data-dazzle-form], [data-dazzle-action], [data-dazzle-nav], [data-dazzle-field]"
        ):
            for key, value in el.attrs.items():
                if isinstance(key, str) and key.startswith("data-dazzle-"):
                    if key not in attrs:
                        attrs[key] = []
                    if isinstance(value, str) and value not in attrs[key]:
                        attrs[key].append(value)
        return attrs

    def _observe_regex(self, html: str) -> PageState:
        """Fallback regex-based parsing when BeautifulSoup isn't available."""
        title_match = re.search(r"<title>([^<]+)</title>", html, re.IGNORECASE)
        title = title_match.group(1) if title_match else ""

        # Extract links
        clickables: list[Element] = []
        for match in re.finditer(r'<a\s+[^>]*href="([^"]*)"[^>]*>([^<]*)</a>', html):
            clickables.append(
                Element(
                    tag="a",
                    text=match.group(2).strip()[:100],
                    selector=f'a[href="{match.group(1)}"]',
                    attributes={"href": match.group(1)},
                )
            )

        # Extract dazzle attributes
        dazzle_attrs: dict[str, list[str]] = {}
        for match in re.finditer(r'(data-dazzle-\w+)="([^"]*)"', html):
            key, value = match.group(1), match.group(2)
            if key not in dazzle_attrs:
                dazzle_attrs[key] = []
            if value not in dazzle_attrs[key]:
                dazzle_attrs[key].append(value)

        return PageState(
            url=self._current_url,
            title=title,
            clickables=clickables[:20],
            dazzle_attributes=dazzle_attrs,
        )
