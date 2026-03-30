"""Playwright-based screenshot capture per persona/workspace.

Produces one PNG screenshot per (persona, workspace) combination and
returns a list of :class:`CapturedScreen` records for downstream QA
evaluation.

Usage::

    from dazzle.qa.capture import build_capture_plan, capture_screenshots

    targets = build_capture_plan(appspec)
    screens = await capture_screenshots(
        targets,
        site_url="http://localhost:3000",
        api_url="http://localhost:8000",
        project_dir=Path("."),
    )
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dazzle.qa.models import CapturedScreen
from dazzle.testing.browser_gate import BrowserGate
from dazzle.testing.session_manager import SessionManager

logger = logging.getLogger("dazzle.qa.capture")


# =============================================================================
# CaptureTarget
# =============================================================================


@dataclass
class CaptureTarget:
    """A single persona/workspace combination to capture."""

    persona: str
    workspace: str
    url: str


# =============================================================================
# Planning
# =============================================================================


def build_capture_plan(appspec: Any) -> list[CaptureTarget]:
    """Build a list of capture targets from an AppSpec.

    Creates one :class:`CaptureTarget` for every (persona, workspace)
    combination found in *appspec*.  Returns an empty list when either
    collection is absent or empty.

    Args:
        appspec: A loaded Dazzle AppSpec (or any object exposing
            ``.workspaces`` and ``.personas`` (or ``.archetypes``) iterables).

    Returns:
        Ordered list of :class:`CaptureTarget` instances.
    """
    workspaces = list(getattr(appspec, "workspaces", None) or [])
    personas = list(
        getattr(appspec, "archetypes", None) or getattr(appspec, "personas", None) or []
    )

    if not workspaces or not personas:
        return []

    targets: list[CaptureTarget] = []
    for persona in personas:
        persona_id: str = str(
            getattr(persona, "name", None) or getattr(persona, "id", None) or "unknown"
        )
        for workspace in workspaces:
            workspace_name: str = str(getattr(workspace, "name", None) or "unknown")
            targets.append(
                CaptureTarget(
                    persona=persona_id,
                    workspace=workspace_name,
                    url=f"/app/workspaces/{workspace_name}",
                )
            )
    return targets


# =============================================================================
# Capture
# =============================================================================


async def capture_screenshots(
    targets: list[CaptureTarget],
    site_url: str,
    api_url: str,
    project_dir: Path,
    *,
    output_dir: Path | None = None,
) -> list[CapturedScreen]:
    """Capture screenshots for all targets using a headless Playwright browser.

    For each target the function:
    1. Obtains an authenticated session token via :class:`SessionManager`.
    2. Opens a browser context with the ``dazzle_session`` cookie set.
    3. Navigates to ``{site_url}{target.url}`` and waits for ``networkidle``.
    4. Takes a full-page screenshot and saves it to *output_dir*.

    Errors for individual targets are logged and skipped — a single bad
    target does not abort the entire run.

    Args:
        targets: Capture plan produced by :func:`build_capture_plan`.
        site_url: Base URL of the Dazzle UI (e.g. ``http://localhost:3000``).
        api_url: Base URL of the Dazzle API (e.g. ``http://localhost:8000``).
        project_dir: Root of the Dazzle project (used for session storage).
        output_dir: Directory to write screenshots to.  Defaults to
            ``{project_dir}/.dazzle/qa/screenshots/``.

    Returns:
        List of :class:`CapturedScreen` records for successfully captured targets.
    """
    site_url = site_url.rstrip("/")
    resolved_output_dir = output_dir or (Path(project_dir) / ".dazzle" / "qa" / "screenshots")
    resolved_output_dir.mkdir(parents=True, exist_ok=True)

    session_manager = SessionManager(project_dir, base_url=api_url)
    gate = BrowserGate(max_concurrent=1, headless=True)

    results: list[CapturedScreen] = []

    async with gate.async_browser() as browser:
        for target in targets:
            screen = await _capture_one(
                target=target,
                browser=browser,
                site_url=site_url,
                session_manager=session_manager,
                output_dir=resolved_output_dir,
            )
            if screen is not None:
                results.append(screen)

    return results


async def _capture_one(
    target: CaptureTarget,
    browser: Any,
    site_url: str,
    session_manager: SessionManager,
    output_dir: Path,
) -> CapturedScreen | None:
    """Capture a single persona/workspace screenshot.

    Args:
        target: The :class:`CaptureTarget` to capture.
        browser: An active Playwright ``Browser`` instance.
        site_url: Base URL of the Dazzle UI (no trailing slash).
        session_manager: :class:`SessionManager` used to obtain a session token.
        output_dir: Directory to save the PNG file.

    Returns:
        A :class:`CapturedScreen` on success, ``None`` on failure.
    """
    screenshot_path = output_dir / f"{target.workspace}_{target.persona}.png"

    try:
        session = await session_manager.create_session(target.persona)
        token = session.session_token
    except Exception as exc:
        logger.warning(
            "Could not create session for persona '%s': %s — skipping %s",
            target.persona,
            exc,
            target.workspace,
        )
        return None

    try:
        context = await browser.new_context()
        try:
            await context.add_cookies(
                [
                    {
                        "name": "dazzle_session",
                        "value": token,
                        "url": site_url,
                    }
                ]
            )
            page = await context.new_page()
            try:
                full_url = f"{site_url}{target.url}"
                await page.goto(full_url, wait_until="networkidle")
                await page.screenshot(path=str(screenshot_path), full_page=True)
                logger.info(
                    "Captured %s/%s → %s",
                    target.persona,
                    target.workspace,
                    screenshot_path,
                )
                return CapturedScreen(
                    persona=target.persona,
                    workspace=target.workspace,
                    url=full_url,
                    screenshot=screenshot_path,
                )
            finally:
                await page.close()
        finally:
            await context.close()
    except Exception as exc:
        logger.error(
            "Screenshot failed for persona '%s' / workspace '%s': %s",
            target.persona,
            target.workspace,
            exc,
        )
        return None
