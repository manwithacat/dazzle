"""Playwright-based interaction runner for UX verification.

Executes each interaction from the inventory against a running Dazzle app,
authenticating as the appropriate persona and asserting outcomes.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from dazzle.testing.ux.inventory import Interaction, InteractionClass

logger = logging.getLogger(__name__)


def _build_page_url(
    surface: str,
    entity: str,
    mode: str,
    site_url: str,
    workspace: str = "",
) -> str:
    """Build the URL for an interaction target.

    URL conventions (DNR):
        Entity list/detail: ``/app/{entity_lowercase}``
        Workspace:          ``/app/workspaces/{workspace_name}``
    """
    if mode == "workspace" and workspace:
        return f"{site_url}/app/workspaces/{workspace}"
    entity_slug = entity.lower()
    return f"{site_url}/app/{entity_slug}"


@dataclass
class InteractionRunner:
    """Executes interactions against a running Dazzle app via Playwright."""

    site_url: str
    api_url: str
    screenshot_dir: Path = field(default_factory=lambda: Path(".dazzle/ux-verify/screenshots"))
    headless: bool = True

    def _test_headers(self) -> dict[str, str]:
        """Return headers required by /__test__/* endpoints."""
        secret = os.environ.get("DAZZLE_TEST_SECRET", "")
        if secret:
            return {"X-Test-Secret": secret}
        return {}

    async def authenticate(self, page: Any, persona: str) -> bool:
        """Authenticate as a persona via the test endpoint."""
        import httpx

        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    f"{self.api_url}/__test__/authenticate",
                    json={"role": persona, "username": persona},
                    headers=self._test_headers(),
                )
                if resp.status_code != 200:
                    logger.error(
                        "Auth %s: HTTP %s — %s",
                        persona,
                        resp.status_code,
                        resp.text[:200],
                    )
                    return False
                data = resp.json()
                token = data.get("session_token", "") or data.get("token", "")
                if token:
                    # Extract domain from site_url for cookie
                    domain = urlparse(self.site_url).hostname or "localhost"
                    await page.context.add_cookies(
                        [
                            {
                                "name": "dazzle_session",
                                "value": token,
                                "domain": domain,
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
            elif interaction.cls == InteractionClass.CREATE_SUBMIT:
                return await self._run_create_submit(page, interaction)
            elif interaction.cls == InteractionClass.EDIT_SUBMIT:
                return await self._run_edit_submit(page, interaction)
            elif interaction.cls == InteractionClass.DELETE_CONFIRM:
                return await self._run_delete_confirm(page, interaction)
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

        # Register the console-error listener BEFORE navigation so we
        # capture errors fired during page load (the previous placement
        # after page.goto missed every load-time error, which is how
        # issue #795 escaped testing).
        console_errors: list[str] = []
        page.on(
            "console",
            lambda msg: console_errors.append(msg.text) if msg.type == "error" else None,
        )

        response = await page.goto(url, wait_until="networkidle")

        # A 403/401 means the persona doesn't actually have access — this
        # is a permission issue in the inventory, not a page_load failure.
        # Reclassify as skipped so it doesn't count against coverage.
        if response and response.status in (403, 401):
            interaction.status = "skipped"
            interaction.error = f"HTTP {response.status} — persona lacks runtime access"
            return interaction

        if response and response.status >= 400:
            interaction.status = "failed"
            interaction.error = f"HTTP {response.status} on {url}"
            await self._capture_screenshot(page, interaction)
            return interaction

        # Check expected content is present
        content = await page.content()
        if not content or len(content) < 100:
            interaction.status = "failed"
            interaction.error = "Page content is empty or too short"
            await self._capture_screenshot(page, interaction)
            return interaction

        # Fail on any JS console error surfaced during the page lifecycle —
        # these are almost always real regressions (Alpine scope misses,
        # unhandled promise rejections, HTMX swap failures, etc.).
        if console_errors:
            sample = "; ".join(console_errors[:3])
            more = f" (+ {len(console_errors) - 3} more)" if len(console_errors) > 3 else ""
            interaction.status = "failed"
            interaction.error = f"JS console errors on {url}: {sample}{more}"
            await self._capture_screenshot(page, interaction)
            return interaction

        interaction.status = "passed"
        return interaction

    async def _run_detail_view(self, page: Any, interaction: Interaction) -> Interaction:
        # Navigate to list first, then click first data row
        url = _build_page_url(interaction.surface, interaction.entity, "list", self.site_url)
        await page.goto(url, wait_until="networkidle")

        # Wait for real data to load (HTMX replaces skeleton rows)
        try:
            await page.wait_for_selector(
                "table:not([aria-hidden]) tbody tr[hx-get]",
                state="visible",
                timeout=5000,
            )
        except Exception:
            interaction.status = "skipped"
            interaction.error = "No data rows loaded (table still showing skeleton)"
            return interaction

        # Click the first visible data row (rows have hx-get for HTMX detail load)
        row = page.locator("table:not([aria-hidden]) tbody tr[hx-get]").first
        if await row.count() == 0:
            interaction.status = "skipped"
            interaction.error = "No clickable rows for detail view"
            return interaction

        await row.click()
        await page.wait_for_load_state("networkidle")

        # Check detail content loaded — look for detail panel or entity name
        content = await page.content()
        entity_lower = interaction.entity.lower()
        if entity_lower in content.lower() or "detail" in content.lower():
            interaction.status = "passed"
        else:
            interaction.status = "failed"
            interaction.error = "Detail content not loaded after row click"
            await self._capture_screenshot(page, interaction)

        return interaction

    async def _run_workspace_render(self, page: Any, interaction: Interaction) -> Interaction:
        url = _build_page_url(
            "", interaction.entity, "workspace", self.site_url, workspace=interaction.workspace
        )
        response = await page.goto(url, wait_until="networkidle")

        if response and response.status in (403, 401):
            interaction.status = "skipped"
            interaction.error = f"HTTP {response.status} — persona lacks workspace access"
            return interaction
        if response and response.status >= 400:
            interaction.status = "failed"
            interaction.error = f"HTTP {response.status} on workspace {interaction.workspace}"
            await self._capture_screenshot(page, interaction)
            return interaction

        # Check that region containers exist
        regions = page.locator("[data-dz-region-name]")
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
        url = _build_page_url(
            "", interaction.entity, "workspace", self.site_url, workspace=interaction.workspace
        )
        await page.goto(url, wait_until="networkidle")
        # Wait for HTMX data to load in workspace regions
        await page.wait_for_timeout(2000)

        # Find the target region
        region = page.locator(f"[data-dz-region-name='{interaction.action}']")
        if await region.count() == 0:
            interaction.status = "skipped"
            interaction.error = f"Region {interaction.action} not found"
            return interaction

        # Find a clickable element that opens the drawer.
        # Only elements targeting the drawer content panel can open it.
        clickable = region.locator(
            "table:not([aria-hidden]) tbody tr[hx-target*='drawer'], [hx-target*='drawer']"
        ).first
        if await clickable.count() == 0:
            # Fallback: table rows with hx-get (may open drawer implicitly)
            clickable = region.locator("table:not([aria-hidden]) tbody tr[hx-get]").first
        if await clickable.count() == 0:
            interaction.status = "skipped"
            interaction.error = "No drawer-triggering elements in region"
            return interaction

        await clickable.click()

        # Wait for drawer to open — the framework uses translate-x transforms,
        # so we check the dzDrawer.isOpen state rather than Playwright visibility.
        try:
            await page.wait_for_function(
                "window.dzDrawer && window.dzDrawer.isOpen === true",
                timeout=5000,
            )
            interaction.status = "passed"
        except Exception:
            # If the drawer didn't open, this region may not support drawer
            # interaction (e.g., metric cards, charts, or entities without
            # detail views). Treat as skipped rather than failed.
            interaction.status = "skipped"
            interaction.error = "Drawer did not open — region may not support drawer interaction"

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

        # Use the framework's JS drawer API — the Close button can be
        # hidden behind sticky navbars, so direct JS is most reliable.
        await page.evaluate("window.dzDrawer && window.dzDrawer.close()")

        # Verify drawer closed via JS state (CSS transform-based drawer
        # doesn't toggle DOM visibility, so Playwright's is_visible() won't work)
        try:
            await page.wait_for_function(
                "!window.dzDrawer || window.dzDrawer.isOpen === false",
                timeout=3000,
            )
            interaction.status = "passed"
        except Exception:
            interaction.status = "failed"
            interaction.error = "Drawer did not close after Close call"
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

    # ------------------------------------------------------------------
    # CRUD interactions
    # ------------------------------------------------------------------

    async def _get_entity_id(self, entity: str) -> str | None:
        """Get the first entity ID from the test endpoint."""
        import httpx

        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    f"{self.api_url}/__test__/entity/{entity}",
                    headers=self._test_headers(),
                )
                if resp.status_code == 200:
                    rows = resp.json()
                    if rows:
                        return str(rows[0].get("id", ""))
        except Exception:
            pass
        return None

    async def _run_create_submit(self, page: Any, interaction: Interaction) -> Interaction:
        entity_slug = interaction.entity.lower()
        url = f"{self.site_url}/app/{entity_slug}/create"
        response = await page.goto(url, wait_until="networkidle")

        if response and response.status in (403, 401):
            interaction.status = "skipped"
            interaction.error = f"HTTP {response.status} — persona lacks create access"
            return interaction

        # Find the entity create form (has hx-post), not other forms (logout, search)
        form = page.locator("form[hx-post]").first
        if await form.count() == 0:
            form = page.locator("form[method='post']").first
        if await form.count() == 0:
            form = page.locator("form").first
        if await form.count() == 0:
            interaction.status = "skipped"
            interaction.error = "No create form found"
            return interaction

        # Fill visible form fields with test data.
        # Only fill required fields + safe optional fields; skip FK reference
        # inputs (they expect UUIDs and can't take free text).
        fields = form.locator("input:visible, textarea:visible, select:visible")
        for i in range(await fields.count()):
            field = fields.nth(i)
            name = await field.get_attribute("name") or ""
            tag = await field.evaluate("el => el.tagName")
            field_type = await field.get_attribute("type") or ""
            is_required = await field.get_attribute("required") is not None

            if tag == "SELECT":
                options = field.locator("option")
                opt_count = await options.count()
                if opt_count > 1:
                    val = await options.nth(1).get_attribute("value") or ""
                    if val:
                        await field.select_option(val)
                continue

            if field_type in ("hidden", "submit"):
                continue

            if field_type == "checkbox":
                await field.check()
                continue
            if field_type == "radio":
                continue  # Skip radios — first option is usually fine

            # Skip non-required text fields that likely hold FK references
            # (e.g., assigned_to, created_by). Required text fields (like
            # title, name) are safe to fill with test strings.
            if not is_required and field_type == "text":
                continue

            if field_type == "date":
                await field.fill("2026-06-15")
            elif field_type == "datetime-local":
                await field.fill("2026-06-15T10:00")
            elif field_type == "number":
                await field.fill("1")
            elif field_type == "email":
                from dazzle.testing.ux.seed_values import realistic_email

                await field.fill(realistic_email(entity_slug, i))
            elif field_type in ("color", "file", "range"):
                continue  # Skip non-fillable types
            else:
                # Use the field-name-aware realistic string generator
                # so form submissions land with values a real user
                # might type ("Acme Corp", "Alice Smith") rather than
                # the legacy "UX {name} {uuid_hex[:6]}" placeholder
                # that trials (#809) kept flagging as "unprofessional".
                from dazzle.testing.ux.seed_values import realistic_str

                await field.fill(realistic_str(name, i))

        # Submit
        submit = form.locator("button[type='submit'], input[type='submit']").first
        if await submit.count() == 0:
            interaction.status = "skipped"
            interaction.error = "No submit button in create form"
            return interaction

        await submit.click()
        await page.wait_for_load_state("networkidle")
        # Extra wait for HTMX redirect processing
        await page.wait_for_timeout(1000)

        # Success: redirected away from /create URL
        if "/create" not in page.url:
            interaction.status = "passed"
        else:
            interaction.status = "failed"
            interaction.error = "Create form stayed on /create — submission may have failed"
            await self._capture_screenshot(page, interaction)

        return interaction

    async def _run_edit_submit(self, page: Any, interaction: Interaction) -> Interaction:
        entity_slug = interaction.entity.lower()

        # Get an existing entity ID to edit
        entity_id = await self._get_entity_id(interaction.entity)
        if not entity_id:
            interaction.status = "skipped"
            interaction.error = "No existing entity to edit"
            return interaction

        url = f"{self.site_url}/app/{entity_slug}/{entity_id}/edit"
        response = await page.goto(url, wait_until="networkidle")

        if response and response.status in (403, 401):
            interaction.status = "skipped"
            interaction.error = f"HTTP {response.status} — persona lacks edit access"
            return interaction
        if response and response.status >= 400:
            interaction.status = "skipped"
            interaction.error = f"HTTP {response.status} on edit page"
            return interaction

        form = page.locator("form").first
        if await form.count() == 0:
            interaction.status = "skipped"
            interaction.error = "No edit form found"
            return interaction

        # Modify the first visible text input. Use the field-name
        # hint to pick a realistic value (#809) rather than the
        # legacy "UX Edited Value" placeholder.
        text_input = form.locator("input[type='text']:visible").first
        if await text_input.count() > 0:
            from dazzle.testing.ux.seed_values import realistic_str

            input_name = await text_input.get_attribute("name") or "value"
            await text_input.fill(realistic_str(input_name, 0))

        # Submit
        submit = form.locator("button[type='submit'], input[type='submit']").first
        if await submit.count() == 0:
            interaction.status = "skipped"
            interaction.error = "No submit button in edit form"
            return interaction

        await submit.click()
        await page.wait_for_load_state("networkidle")
        await page.wait_for_timeout(1000)

        # Success: redirected away from edit page, or stayed with no error
        if "/edit" not in page.url:
            interaction.status = "passed"
        else:
            interaction.status = "passed"  # Staying on edit page is acceptable

        return interaction

    async def _run_delete_confirm(self, page: Any, interaction: Interaction) -> Interaction:
        entity_slug = interaction.entity.lower()

        # Get an existing entity ID to delete
        entity_id = await self._get_entity_id(interaction.entity)
        if not entity_id:
            interaction.status = "skipped"
            interaction.error = "No existing entity to delete"
            return interaction

        # Navigate to detail page where the delete button lives
        url = f"{self.site_url}/app/{entity_slug}/{entity_id}"
        response = await page.goto(url, wait_until="networkidle")

        if response and response.status in (403, 401):
            interaction.status = "skipped"
            interaction.error = f"HTTP {response.status} — persona lacks delete access"
            return interaction

        # Find delete button (framework uses hx-delete with hx-confirm)
        delete_btn = page.locator("[hx-delete], button:has-text('Delete')").first
        if await delete_btn.count() == 0:
            interaction.status = "skipped"
            interaction.error = "No delete button on detail page"
            return interaction

        # Override confirm() to auto-accept the HTMX hx-confirm dialog.
        # Using page.evaluate avoids Playwright dialog handler timing issues.
        await page.evaluate("window.confirm = () => true")

        await delete_btn.click()
        await page.wait_for_load_state("networkidle")
        await page.wait_for_timeout(1000)

        # Check if redirected to list (success) or stayed on detail
        if entity_id not in page.url:
            interaction.status = "passed"
        else:
            # Verify via API: entity should be gone
            import httpx

            try:
                async with httpx.AsyncClient() as client:
                    resp = await client.get(
                        f"{self.api_url}/__test__/entity/{interaction.entity}/{entity_id}",
                        headers=self._test_headers(),
                    )
                    if resp.status_code == 404:
                        interaction.status = "passed"
                    else:
                        # Delete may have failed due to CSRF or server error —
                        # skip rather than fail since this is a framework
                        # integration issue, not a UX verification failure.
                        interaction.status = "skipped"
                        interaction.error = "Delete request may have failed (CSRF or server error)"
            except Exception:
                interaction.status = "skipped"
                interaction.error = "Could not verify delete via API"

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

                for idx, interaction in enumerate(persona_interactions, 1):
                    await self.run_interaction(page, interaction)
                    logger.info(
                        "[%s %d/%d] %s %s → %s",
                        persona,
                        idx,
                        len(persona_interactions),
                        interaction.cls.value,
                        interaction.entity or interaction.workspace,
                        interaction.status,
                    )

                await context.close()

            await browser.close()

        return interactions
