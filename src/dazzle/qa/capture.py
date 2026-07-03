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

import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from dazzle.core.access import workspace_allowed_personas
from dazzle.core.ir.identity import spec_display_id
from dazzle.qa.models import CapturedScreen

if TYPE_CHECKING:
    from dazzle.testing.session_manager import SessionManager

logger = logging.getLogger(__name__)


# =============================================================================
# CaptureTarget
# =============================================================================


@dataclass
class CaptureTarget:
    """A single persona/workspace combination to capture."""

    persona: str
    workspace: str
    url: str


VIEWPORTS: dict[str, dict[str, int]] = {
    "desktop": {"width": 1440, "height": 900},
    "mobile": {"width": 390, "height": 844},
}


# =============================================================================
# Planning
# =============================================================================


def _workspace_access_map(workspaces: list[Any], personas: list[Any]) -> dict[str, set[str] | None]:
    """Per-workspace allowed-persona sets (None = open to all personas)."""
    allowed_by_ws: dict[str, set[str] | None] = {}
    for workspace in workspaces:
        workspace_name = str(getattr(workspace, "name", None) or "unknown")
        try:
            allowed = workspace_allowed_personas(workspace, personas)
        except Exception:  # pragma: no cover - duck-typed appspecs in tests
            allowed = None
        allowed_by_ws[workspace_name] = None if allowed is None else set(allowed)
    return allowed_by_ws


def build_capture_plan(appspec: Any, *, include_denied: bool = False) -> list[CaptureTarget]:
    """Build a list of capture targets from an AppSpec.

    Creates one :class:`CaptureTarget` per **accessible** (persona,
    workspace) combination — accessibility comes from
    :func:`dazzle.core.access.workspace_allowed_personas`, the same single
    source of truth the nav builder uses, so captures see what a real
    signed-in persona sees (#1536 follow-on: the old Cartesian product
    spent most of its screenshots on 403 pages). Returns an empty list
    when either collection is absent or empty.

    Args:
        appspec: A loaded Dazzle AppSpec (or any object exposing
            ``.workspaces`` and ``.personas`` (or ``.archetypes``) iterables).
        include_denied: Also emit the inaccessible combos (for auditing the
            denial pages themselves).

    Returns:
        Ordered list of :class:`CaptureTarget` instances.
    """
    workspaces = list(getattr(appspec, "workspaces", None) or [])
    personas = list(
        getattr(appspec, "archetypes", None) or getattr(appspec, "personas", None) or []
    )

    if not workspaces or not personas:
        return []

    allowed_by_ws = _workspace_access_map(workspaces, personas)

    targets: list[CaptureTarget] = []
    for persona in personas:
        persona_id: str = str(spec_display_id(persona))
        for workspace in workspaces:
            workspace_name = str(getattr(workspace, "name", None) or "unknown")
            allowed_set = allowed_by_ws[workspace_name]
            accessible = allowed_set is None or persona_id in allowed_set
            if not accessible and not include_denied:
                continue
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
    viewport: str = "desktop",
    color_scheme: str = "light",
    full_page: bool = True,
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

    # Deferred (#1438 pattern): dazzle.testing eagerly imports e2e_runner ->
    # httpx, which a bare `pip install dazzle-dsl` doesn't ship. Importing at
    # module level broke the console script on wheel-only installs (caught
    # by the PyPI smoke test).
    from dazzle.testing.browser_gate import BrowserGate
    from dazzle.testing.session_manager import SessionManager

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
                viewport=viewport,
                color_scheme=color_scheme,
                full_page=full_page,
            )
            if screen is not None:
                results.append(screen)

    return results


def write_manifest(
    screens: list[CapturedScreen],
    app_name: str,
    manifest_path: Path,
) -> None:
    """Append *screens* to a fleet-wide JSON manifest at *manifest_path*.

    Used by the `/improve` Tier 2 visual-QA sub-strategy: each example
    app calls :func:`capture_screenshots` and then this helper to add its
    screens under a per-app section. The strategy then hands the
    manifest to a CC subagent for evaluation, side-stepping the
    Anthropic API.

    If the manifest exists, the new screens are appended under their
    app_name key (replacing any prior entry for the same app — re-runs
    overwrite). If it doesn't exist, a new file is created.

    Args:
        screens: Captured screens for this app.
        app_name: Identifier for the app (e.g. "ops_dashboard").
        manifest_path: JSON manifest path. Parent dirs are created as needed.
    """
    manifest_path.parent.mkdir(parents=True, exist_ok=True)

    if manifest_path.exists():
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    else:
        data = {"timestamp": datetime.now(UTC).isoformat(), "apps": []}

    data["apps"] = [a for a in data.get("apps", []) if a.get("app") != app_name]
    data["apps"].append(
        {
            "app": app_name,
            "screens": [
                {
                    "persona": s.persona,
                    "workspace": s.workspace,
                    "url": s.url,
                    "screenshot": str(s.screenshot),
                    "viewport": s.viewport,
                    "theme": s.theme,
                }
                for s in screens
            ],
        }
    )

    manifest_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


async def _capture_one(
    target: CaptureTarget,
    browser: Any,
    site_url: str,
    session_manager: SessionManager,
    output_dir: Path,
    *,
    viewport: str = "desktop",
    color_scheme: str = "light",
    full_page: bool = True,
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
    screenshot_path = (
        output_dir / f"{target.workspace}_{target.persona}_{viewport}_{color_scheme}.png"
    )

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
        context = await browser.new_context(viewport=VIEWPORTS[viewport], color_scheme=color_scheme)
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
                await page.screenshot(path=str(screenshot_path), full_page=full_page)
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
                    viewport=viewport,
                    theme=color_scheme,
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
