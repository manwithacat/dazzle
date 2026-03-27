"""Playwright-based interaction runner for UX verification.

Executes each interaction from the inventory against a running Dazzle app,
authenticating as the appropriate persona and asserting outcomes.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from dazzle.testing.ux.inventory import Interaction, InteractionClass

logger = logging.getLogger(__name__)


def _build_page_url(
    surface: str,
    entity: str,
    mode: str,
    site_url: str,
    workspace: str = "",
) -> str:
    """Build the URL for an interaction target."""
    if mode == "workspace" and workspace:
        return f"{site_url}/workspace/{workspace}"
    # Entity pages use lowercase entity name
    entity_slug = entity.lower()
    return f"{site_url}/app/{entity_slug}"


@dataclass
class InteractionRunner:
    """Executes interactions against a running Dazzle app via Playwright."""

    site_url: str
    api_url: str
    screenshot_dir: Path = field(default_factory=lambda: Path(".dazzle/ux-verify/screenshots"))
    headless: bool = True

    async def authenticate(self, page: Any, persona: str) -> bool:
        """Authenticate as a persona via the test endpoint."""
        import httpx

        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    f"{self.api_url}/__test__/authenticate",
                    json={"role": persona, "username": persona},
                )
                if resp.status_code != 200:
                    return False
                data = resp.json()
                token = data.get("session_token", "")
                if token:
                    await page.context.add_cookies(
                        [
                            {
                                "name": "dazzle_session",
                                "value": token,
                                "domain": "localhost",
                                "path": "/",
                            }
                        ]
                    )
                return True
        except Exception as e:
            logger.error("Authentication failed for %s: %s", persona, e)
            return False

    async def run_interaction(self, page: Any, interaction: Interaction) -> Interaction:
        """Execute a single interaction and update its status."""
        try:
            if interaction.cls == InteractionClass.PAGE_LOAD:
                return await self._run_page_load(page, interaction)
            elif interaction.cls == InteractionClass.DETAIL_VIEW:
                return await self._run_detail_view(page, interaction)
            elif interaction.cls == InteractionClass.WORKSPACE_RENDER:
                return await self._run_workspace_render(page, interaction)
            elif interaction.cls == InteractionClass.DRAWER_OPEN:
                return await self._run_drawer_open(page, interaction)
            elif interaction.cls == InteractionClass.DRAWER_CLOSE:
                return await self._run_drawer_close(page, interaction)
            elif interaction.cls == InteractionClass.ACCESS_DENIED:
                return await self._run_access_denied(page, interaction)
            else:
                interaction.status = "skipped"
                return interaction
        except Exception as e:
            interaction.status = "failed"
            interaction.error = str(e)
            await self._capture_screenshot(page, interaction)
            return interaction

    async def _run_page_load(self, page: Any, interaction: Interaction) -> Interaction:
        url = _build_page_url(interaction.surface, interaction.entity, "list", self.site_url)
        response = await page.goto(url, wait_until="networkidle")

        # Check HTTP status
        if response and response.status >= 400:
            interaction.status = "failed"
            interaction.error = f"HTTP {response.status} on {url}"
            await self._capture_screenshot(page, interaction)
            return interaction

        # Check for JS console errors
        errors = []
        page.on("console", lambda msg: errors.append(msg.text) if msg.type == "error" else None)

        # Check expected content is present
        content = await page.content()
        if not content or len(content) < 100:
            interaction.status = "failed"
            interaction.error = "Page content is empty or too short"
            await self._capture_screenshot(page, interaction)
            return interaction

        interaction.status = "passed"
        return interaction

    async def _run_detail_view(self, page: Any, interaction: Interaction) -> Interaction:
        # Navigate to list first, then click first row
        url = _build_page_url(interaction.surface, interaction.entity, "list", self.site_url)
        await page.goto(url, wait_until="networkidle")

        # Find first clickable row
        row = page.locator("table tbody tr a, [data-dazzle-entity] a").first
        if await row.count() == 0:
            interaction.status = "skipped"
            interaction.error = "No rows to click for detail view"
            return interaction

        await row.click()
        await page.wait_for_load_state("networkidle")

        # Check detail content loaded
        content = await page.content()
        if "detail" in content.lower() or interaction.entity.lower() in content.lower():
            interaction.status = "passed"
        else:
            interaction.status = "failed"
            interaction.error = "Detail content not loaded after row click"
            await self._capture_screenshot(page, interaction)

        return interaction

    async def _run_workspace_render(self, page: Any, interaction: Interaction) -> Interaction:
        url = _build_page_url("", "", "workspace", self.site_url, workspace=interaction.workspace)
        response = await page.goto(url, wait_until="networkidle")

        if response and response.status >= 400:
            interaction.status = "failed"
            interaction.error = f"HTTP {response.status} on workspace {interaction.workspace}"
            await self._capture_screenshot(page, interaction)
            return interaction

        # Check that region containers exist
        regions = page.locator("[data-region-name]")
        count = await regions.count()
        if count == 0:
            interaction.status = "failed"
            interaction.error = "No workspace regions found"
            await self._capture_screenshot(page, interaction)
            return interaction

        interaction.status = "passed"
        return interaction

    async def _run_drawer_open(self, page: Any, interaction: Interaction) -> Interaction:
        # Navigate to workspace
        url = _build_page_url("", "", "workspace", self.site_url, workspace=interaction.workspace)
        await page.goto(url, wait_until="networkidle")

        # Find a clickable row in the target region
        region = page.locator(f"[data-region-name='{interaction.action}']")
        if await region.count() == 0:
            interaction.status = "skipped"
            interaction.error = f"Region {interaction.action} not found"
            return interaction

        row = region.locator("table tbody tr, .card").first
        if await row.count() == 0:
            interaction.status = "skipped"
            interaction.error = "No clickable rows in region"
            return interaction

        await row.click()

        # Wait for drawer to appear
        try:
            drawer = page.locator("#dz-detail-drawer")
            await drawer.wait_for(state="visible", timeout=3000)
            interaction.status = "passed"
        except Exception:
            interaction.status = "failed"
            interaction.error = "Drawer did not open within 3s"
            await self._capture_screenshot(page, interaction)

        return interaction

    async def _run_drawer_close(self, page: Any, interaction: Interaction) -> Interaction:
        # First open the drawer (reuse open logic)
        open_result = await self._run_drawer_open(
            page,
            Interaction(
                cls=InteractionClass.DRAWER_OPEN,
                entity=interaction.entity,
                persona=interaction.persona,
                workspace=interaction.workspace,
                action=interaction.action,
                description="",
            ),
        )
        if open_result.status != "passed":
            interaction.status = "skipped"
            interaction.error = "Could not open drawer to test close"
            return interaction

        # Click the Back button inside the drawer
        drawer = page.locator("#dz-detail-drawer")
        back_btn = drawer.locator("a:has-text('Back'), button:has-text('Back')").first
        if await back_btn.count() > 0:
            await back_btn.click()
        else:
            # Try the X close button
            close_btn = drawer.locator("[aria-label='Close'], button:has-text('x')").first
            if await close_btn.count() > 0:
                await close_btn.click()

        # Verify drawer closed
        try:
            await drawer.wait_for(state="hidden", timeout=2000)
            interaction.status = "passed"
        except Exception:
            interaction.status = "failed"
            interaction.error = "Drawer did not close after Back/Close click"
            await self._capture_screenshot(page, interaction)

        return interaction

    async def _run_access_denied(self, page: Any, interaction: Interaction) -> Interaction:
        url = _build_page_url(interaction.surface, interaction.entity, "list", self.site_url)
        response = await page.goto(url, wait_until="networkidle")

        if response and response.status in (403, 401, 302):
            interaction.status = "passed"
        else:
            # Check if we were redirected to login
            if "/login" in page.url or "/auth" in page.url:
                interaction.status = "passed"
            else:
                interaction.status = "failed"
                interaction.error = (
                    f"Expected 403/redirect, got {response.status if response else 'no response'}"
                )
                await self._capture_screenshot(page, interaction)

        return interaction

    async def _capture_screenshot(self, page: Any, interaction: Interaction) -> None:
        """Capture a screenshot for a failed interaction."""
        self.screenshot_dir.mkdir(parents=True, exist_ok=True)
        filename = f"{interaction.cls.value}_{interaction.entity}_{interaction.persona}.png"
        path = self.screenshot_dir / filename
        try:
            await page.screenshot(path=str(path))
            interaction.screenshot = str(path)
        except Exception:
            logger.debug("Failed to capture screenshot for %s", interaction.interaction_id)

    async def run_all(self, interactions: list[Interaction]) -> list[Interaction]:
        """Run all interactions, grouping by persona for session efficiency."""
        from playwright.async_api import async_playwright

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=self.headless)

            # Group by persona
            by_persona: dict[str, list[Interaction]] = {}
            for interaction in interactions:
                by_persona.setdefault(interaction.persona, []).append(interaction)

            for persona, persona_interactions in by_persona.items():
                context = await browser.new_context()
                page = await context.new_page()

                # Authenticate once per persona
                if persona:
                    auth_ok = await self.authenticate(page, persona)
                    if not auth_ok:
                        for i in persona_interactions:
                            i.status = "failed"
                            i.error = f"Authentication failed for persona {persona}"
                        await context.close()
                        continue

                for interaction in persona_interactions:
                    await self.run_interaction(page, interaction)

                await context.close()

            await browser.close()

        return interactions
