"""Composition styles — Playwright computed style extraction for diagnosis.

Uses ``getComputedStyle()`` via Playwright to inspect what the browser
actually renders, bridging the gap between "something looks wrong"
(detected by geometry audit) and "here's the CSS fix" (remediation).
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# Properties most useful for diagnosing layout issues.
DEFAULT_PROPERTIES: list[str] = [
    "display",
    "flex-direction",
    "align-items",
    "justify-content",
    "position",
    "width",
    "height",
    "overflow",
    "gap",
    "grid-template-columns",
]


async def inspect_computed_styles(
    base_url: str,
    route: str,
    selectors: dict[str, str],
    properties: list[str] | None = None,
) -> dict[str, dict[str, str] | None]:
    """Extract computed CSS styles from a running app via Playwright.

    Navigates to the given route, queries each selector, and reads
    ``getComputedStyle()`` for the requested properties.

    Args:
        base_url: Running app URL (e.g. ``http://localhost:3000``).
        route: Page route to inspect (e.g. ``/``).
        selectors: Mapping of label → CSS selector.
        properties: CSS properties to read (defaults to layout properties).

    Returns:
        Dict mapping each label to its computed property values,
        or ``None`` if the selector matched no element.

    Raises:
        ImportError: If Playwright is not installed.
    """
    try:
        import playwright  # noqa: F401
    except ImportError:
        raise ImportError(
            "Playwright is required for style inspection. "
            "Install with: pip install playwright && playwright install chromium"
        )

    from dazzle.testing.browser_gate import get_browser_gate

    props = properties or DEFAULT_PROPERTIES
    url = base_url.rstrip("/") + route

    results: dict[str, dict[str, str] | None] = {}

    async with get_browser_gate().async_browser() as browser:
        page = await browser.new_page()
        page.set_default_timeout(15000)

        try:
            await page.goto(url, wait_until="networkidle", timeout=15000)
            await page.wait_for_timeout(1000)
        except Exception as e:
            logger.warning("Failed to navigate to %s: %s", url, e)
            raise RuntimeError(f"Navigation failed: {e}") from e

        for label, selector in selectors.items():
            try:
                element = await page.query_selector(selector)
                if not element:
                    results[label] = None
                    continue

                computed = await page.evaluate(
                    """([el, props]) => {
                        const cs = window.getComputedStyle(el);
                        const result = {};
                        for (const p of props) {
                            result[p] = cs.getPropertyValue(p);
                        }
                        return result;
                    }""",
                    [element, props],
                )
                results[label] = computed
            except Exception as e:
                logger.warning("Failed to inspect %s (%s): %s", label, selector, e)
                results[label] = None

    return results
