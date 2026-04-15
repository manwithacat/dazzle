"""Shared Playwright bundle + persona-login helpers for ux_cycle strategies.

Current consumer:

- ``fitness_strategy.run_fitness_strategy``

Originally extracted to be shared with an explore strategy as well; the
explore path has since been re-homed onto the subagent-driven playbook
(``subagent_explore``) that drives a stateless helper via the Task tool,
so this module is currently fitness-only. Kept as a module (rather than
inlined) because a future strategy may need the same QA magic-link flow.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse


@dataclass
class PlaywrightBundle:
    """Playwright resources owned by a strategy for one cycle."""

    playwright: Any
    browser: Any
    context: Any
    page: Any

    async def close(self) -> None:
        await self.context.close()
        await self.browser.close()
        await self.playwright.stop()


async def setup_playwright(base_url: str) -> PlaywrightBundle:
    """Spin up a headless Chromium page pointed at ``base_url``.

    Separate from strategy engine construction so tests can patch it cleanly.
    """
    from playwright.async_api import async_playwright

    pw = await async_playwright().start()
    browser = await pw.chromium.launch(headless=True)
    context = await browser.new_context(base_url=base_url)
    page = await context.new_page()
    return PlaywrightBundle(playwright=pw, browser=browser, context=context, page=page)


async def login_as_persona(page: Any, persona_id: str, api_url: str) -> None:
    """Log a Playwright page in as a DSL persona via QA mode's magic-link flow.

    Two-step flow from issue #768:
        1. ``POST {api_url}/qa/magic-link`` with ``{"persona_id": persona_id}`` —
           gated by DAZZLE_ENV=development + DAZZLE_QA_MODE=1 on the example
           subprocess. Returns a single-use token.
        2. ``GET {api_url}/auth/magic/{token}?next=/`` — validates token,
           creates session cookie, redirects to ``next``.

    Raises:
        RuntimeError: if any step fails. Distinguishing messages let strategy
            loops record BLOCKED outcomes with useful context:
            - "magic-link endpoint returned 404" (QA flags missing OR persona
              not provisioned; see qa_routes.py:59,65)
            - "magic-link generation failed: HTTP {status}" (other non-2xx)
            - "persona login rejected: magic-link consumer did not create a
              session" (final page path is /auth/login or /login — path-exact
              check to avoid false positives on routes like /admin/login-history)
    """
    generator_url = f"{api_url}/qa/magic-link"
    response = await page.request.post(
        generator_url,
        data=json.dumps({"persona_id": persona_id}),
        headers={"Content-Type": "application/json"},
    )
    if not response.ok:
        if response.status == 404:
            raise RuntimeError(
                f"magic-link endpoint returned 404 for persona {persona_id!r} at "
                f"{generator_url} — check DAZZLE_ENV=development + DAZZLE_QA_MODE=1, "
                f"or that the persona is provisioned"
            )
        raise RuntimeError(
            f"magic-link generation failed: HTTP {response.status} at {generator_url}"
        )

    magic_link_payload = await response.json()
    # QA endpoint (dazzle_back/runtime/qa_routes.py:79) returns
    # MagicLinkResponse(url=f"/auth/magic/{token}") — a server-relative path.
    magic_link_path = magic_link_payload["url"]

    consumer_url = f"{api_url}{magic_link_path}?next=/"
    await page.goto(consumer_url)

    final_path = urlparse(page.url).path
    if final_path in ("/auth/login", "/login"):
        raise RuntimeError(
            f"persona login rejected: magic-link consumer did not create a session "
            f"for persona {persona_id!r} (final URL: {page.url})"
        )
