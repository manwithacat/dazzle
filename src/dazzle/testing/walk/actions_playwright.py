"""Playwright click/wait helpers for scene walks (#1638 / #1640).

Kept separate from ``runner.py`` so HTTP orchestration stays MI-clean.
"""

from __future__ import annotations

import re
from typing import Any, cast
from urllib.parse import urljoin

import httpx

from dazzle.testing.walk.actions_api import playwright_click_api_fallback
from dazzle.testing.walk.models import ActionSpec
from dazzle.testing.walk.policies import cookies_for_playwright
from dazzle.testing.walk.results import ActionResult


def cookie_jar_for_playwright(
    *,
    client: httpx.AsyncClient | None,
    cookies: dict[str, str],
    base_url: str,
) -> list[dict[str, Any]]:
    """Session + CSRF cookies from the same jar as httpx (R4.1)."""
    if client is not None:
        return cookies_for_playwright(client, base_url)
    return [{"name": k, "value": v, "url": base_url} for k, v in cookies.items()]


def click_timeout_ms(action: ActionSpec) -> int:
    """Locator timeout; independent of api_fallback settle wait."""
    if action.api_fallback_status:
        return 5000
    return action.wait_ms or 5000


async def do_playwright_click(
    action: ActionSpec,
    *,
    base_url: str,
    last_url: str,
    cookies: dict[str, str],
    client: httpx.AsyncClient | None,
) -> tuple[bool, str, dict[str, Any], str | None, str | None]:
    """Launch Chromium and click by role/name.

    Returns ``(ok, message, detail, new_last_url, new_last_body)``.
    On failure, last_url/body are None (caller keeps prior state).
    """
    from playwright.async_api import async_playwright

    role = action.role or "button"
    name = action.name or ""
    timeout_ms = click_timeout_ms(action)
    click_message = f"clicked {role}/{name!r}"

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        ctx = await browser.new_context(base_url=base_url, storage_state=None)
        jar = cookie_jar_for_playwright(client=client, cookies=cookies, base_url=base_url)
        if jar:
            # Playwright SetCookieParam is TypedDict; our jar is plain dicts.
            await ctx.add_cookies(cast(Any, jar))
        page = await ctx.new_page()
        try:
            target = last_url or base_url + "/"
            if not target.startswith("http"):
                target = urljoin(base_url + "/", target.lstrip("/"))
            await page.goto(target, wait_until="networkidle", timeout=timeout_ms)
            # role is DSL-authored str; Playwright stubs want Literal AriaRole.
            aria_role = cast(Any, role)
            if action.regex and name:
                locator = page.get_by_role(aria_role, name=re.compile(name))
            else:
                locator = page.get_by_role(aria_role, name=name, exact=True)
            await locator.first.click(timeout=timeout_ms)
            await page.wait_for_load_state("networkidle", timeout=timeout_ms)
            body = await page.content()
            return True, click_message, {"url": page.url}, page.url, body
        except Exception as exc:
            return (
                False,
                f"click failed {role}/{name!r}: {type(exc).__name__}: {exc}",
                {},
                None,
                None,
            )
        finally:
            await ctx.close()
            await browser.close()


async def playwright_click_with_fallback(
    *,
    action: ActionSpec,
    base_url: str,
    last_url: str,
    client: httpx.AsyncClient | None,
    cookies: dict[str, str],
    vars_: dict[str, str],
) -> tuple[ActionResult, str | None, str | None, int | None]:
    """Full click path + optional ``api_fallback_status`` durability (#1640).

    Returns ``(result, new_last_url, new_last_body, new_last_status)``.
    """
    try:
        from playwright.async_api import async_playwright  # noqa: F401
    except ImportError:
        return (
            ActionResult(
                action.type.value,
                False,
                "playwright not installed (pip install playwright && playwright install chromium)",
            ),
            None,
            None,
            None,
        )

    click_ok, click_message, click_detail, new_url, new_body = await do_playwright_click(
        action,
        base_url=base_url,
        last_url=last_url,
        cookies=cookies,
        client=client,
    )
    new_status = 200 if new_url is not None else None

    wants_fallback = bool(action.api_fallback_status and (action.path_template or action.path))
    if wants_fallback:
        if client is None:
            return (
                ActionResult(
                    action.type.value,
                    False,
                    f"{click_message}; api_fallback needs HTTP client",
                    click_detail,
                ),
                new_url,
                new_body,
                new_status,
            )
        settle = action.wait_ms if action.wait_ms is not None else 1500
        result = await playwright_click_api_fallback(
            client,
            action,
            vars_,
            click_ok=click_ok,
            click_message=click_message,
            settle_ms=settle,
        )
        return result, new_url, new_body, new_status

    return (
        ActionResult(action.type.value, click_ok, click_message, click_detail),
        new_url,
        new_body,
        new_status,
    )
