"""Journey mission — persona-driven E2E exploration and story verification.

Phase 1: Deterministic workspace exploration (no LLM).
Phase 2: LLM-assisted story verification using DazzleAgent.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from dazzle.agent.journey_models import JourneyStep, NavigationTarget, Verdict
from dazzle.agent.models import Step

if TYPE_CHECKING:
    from dazzle.agent.journey_writer import SessionWriter

logger = logging.getLogger(__name__)


# =============================================================================
# Phase 1: Navigation Plan
# =============================================================================


def _entity_url_slug(entity_name: str) -> str:
    """Convert entity name to URL slug: 'AcademicYear' → 'academic-year'."""
    import re

    slug = re.sub(r"([a-z])([A-Z])", r"\1-\2", entity_name)
    return slug.lower().replace("_", "-")


def _can_access_workspace(workspace: Any, persona_id: str) -> bool:
    """Check if persona can access the workspace based on access rules."""
    if workspace.access is None:
        return True
    level = getattr(workspace.access, "level", None)
    if level is not None and getattr(level, "value", str(level)) == "persona":
        allowed = getattr(workspace.access, "allow_personas", [])
        denied = getattr(workspace.access, "deny_personas", [])
        if persona_id in denied:
            return False
        if allowed and persona_id not in allowed:
            return False
    return True


def build_navigation_plan(
    appspec: Any,
    persona_id: str,
) -> list[NavigationTarget]:
    """Build a deterministic navigation plan from the AppSpec for a persona.

    Reads workspaces, regions, and surfaces to produce a list of URLs
    the explorer should visit. No browser or LLM dependency.
    """
    targets: list[NavigationTarget] = []
    seen_entities: set[str] = set()

    # Build surface lookup: entity_ref → list of (mode, surface)
    surface_by_entity: dict[str, list[Any]] = {}
    for surface in appspec.surfaces:
        if surface.entity_ref:
            surface_by_entity.setdefault(surface.entity_ref, []).append(surface)

    # Walk accessible workspaces
    for workspace in appspec.workspaces:
        if not _can_access_workspace(workspace, persona_id):
            continue

        for region in workspace.regions:
            entity_name = region.source
            if not entity_name or entity_name in seen_entities:
                continue
            seen_entities.add(entity_name)

            slug = _entity_url_slug(entity_name)

            # Always add list URL
            targets.append(
                NavigationTarget(
                    url=f"/app/{slug}",
                    entity_name=entity_name,
                    surface_mode="list",
                    expectation=f"{entity_name} list page loads with data",
                )
            )

            # Check for create surface
            entity_surfaces = surface_by_entity.get(entity_name, [])
            for surf in entity_surfaces:
                mode_val = getattr(surf.mode, "value", str(surf.mode))
                if mode_val == "create":
                    targets.append(
                        NavigationTarget(
                            url=f"/app/{slug}/create",
                            entity_name=entity_name,
                            surface_mode="create",
                            expectation=f"{entity_name} create form renders with fields",
                        )
                    )
                    break  # Only one create target per entity

    return targets


# =============================================================================
# Phase 1: Exploration Runner
# =============================================================================


async def _attempt_login(
    page: Any,
    base_url: str,
    credentials: dict[str, str],
) -> tuple[bool, str]:
    """Navigate to login and fill credentials. Returns (success, observation)."""
    try:
        await page.goto(f"{base_url}/login", wait_until="domcontentloaded")
        await page.wait_for_load_state("networkidle")
    except TimeoutError:
        return False, "Login page timed out"

    try:
        # Fill email field
        email_sel = 'input[name="email"], input[type="email"], #email'
        await page.fill(email_sel, credentials["email"])

        # Fill password field
        pwd_sel = 'input[name="password"], input[type="password"], #password'
        await page.fill(pwd_sel, credentials["password"])

        # Submit
        submit_sel = 'button[type="submit"], input[type="submit"]'
        await page.click(submit_sel)
        await page.wait_for_load_state("networkidle")
    except Exception as exc:
        return False, f"Login interaction failed: {exc}"

    # Check if still on login page
    if "/login" in page.url:
        return False, "Still on login page after submit — credentials may be wrong"

    return True, f"Logged in successfully, redirected to {page.url}"


async def run_phase1_exploration(
    plan: list[NavigationTarget],
    page: Any,
    credentials: dict[str, str],
    persona: str,
    writer: SessionWriter,
    base_url: str,
) -> list[JourneyStep]:
    """Execute Phase 1 deterministic exploration.

    Logs in, then navigates to each target in the plan, recording
    a JourneyStep per navigation.
    """
    steps: list[JourneyStep] = []
    step_num = 0

    # --- Login ---
    step_num += 1
    url_before = page.url if isinstance(page.url, str) else str(page.url)
    login_ok, login_obs = await _attempt_login(page, base_url, credentials)

    login_step = JourneyStep(
        persona=persona,
        phase="explore",
        step_number=step_num,
        action="login",
        target="Login page",
        url_before=url_before,
        url_after=page.url if isinstance(page.url, str) else str(page.url),
        expectation="Login succeeds and redirects to app",
        observation=login_obs,
        verdict=Verdict.PASS if login_ok else Verdict.FAIL,
        reasoning="Login successful" if login_ok else "Login failed",
        timestamp=datetime.now(UTC),
    )
    steps.append(login_step)
    writer.write_step(login_step)

    if not login_ok:
        return steps

    # --- Navigate targets ---
    for target in plan:
        step_num += 1
        full_url = f"{base_url}{target.url}"
        url_before = page.url if isinstance(page.url, str) else str(page.url)

        try:
            await page.goto(full_url, wait_until="domcontentloaded")
            await page.wait_for_load_state("networkidle")
        except TimeoutError:
            step = JourneyStep(
                persona=persona,
                phase="explore",
                step_number=step_num,
                action="navigate",
                target=target.url,
                url_before=url_before,
                url_after=url_before,
                expectation=target.expectation,
                observation="Page load timed out",
                verdict=Verdict.TIMEOUT,
                reasoning="Navigation timed out",
                timestamp=datetime.now(UTC),
            )
            steps.append(step)
            writer.write_step(step)
            continue
        except Exception as exc:
            step = JourneyStep(
                persona=persona,
                phase="explore",
                step_number=step_num,
                action="navigate",
                target=target.url,
                url_before=url_before,
                url_after=url_before,
                expectation=target.expectation,
                observation=f"Navigation error: {exc}",
                verdict=Verdict.FAIL,
                reasoning=str(exc),
                timestamp=datetime.now(UTC),
            )
            steps.append(step)
            writer.write_step(step)
            continue

        # Inspect page
        current_url = page.url if isinstance(page.url, str) else str(page.url)
        observation_parts: list[str] = []
        verdict = Verdict.PASS
        reasoning = "Page loaded successfully"

        # Check for row count on list pages
        if target.surface_mode == "list":
            try:
                row_count = await page.evaluate(
                    "document.querySelectorAll('table tbody tr, [data-row], .list-item').length"
                )
                observation_parts.append(f"{row_count} rows visible")
                if row_count == 0:
                    observation_parts.append("empty list")
            except Exception:
                observation_parts.append("Could not count rows")

        # Check for form fields on create pages
        if target.surface_mode == "create":
            try:
                inputs = await page.query_selector_all("input, select, textarea")
                observation_parts.append(f"{len(inputs)} form fields")
            except Exception:
                observation_parts.append("Could not inspect form")

        # Screenshot — best-effort; absence shouldn't block journey progress (#smells-1.1).
        screenshot_path: str | None = None
        try:
            png = await page.screenshot()
            screenshot_path = writer.save_screenshot(persona, f"{step_num:03d}", png)
        except Exception:
            logger.debug("Screenshot failed for %s step %s", persona, step_num, exc_info=True)

        observation = "; ".join(observation_parts) if observation_parts else "Page loaded"

        step = JourneyStep(
            persona=persona,
            phase="explore",
            step_number=step_num,
            action="navigate",
            target=target.url,
            url_before=url_before,
            url_after=current_url,
            expectation=target.expectation,
            observation=observation,
            verdict=verdict,
            reasoning=reasoning,
            screenshot_path=screenshot_path,
            timestamp=datetime.now(UTC),
        )
        steps.append(step)
        writer.write_step(step)

    return steps


# =============================================================================
# Phase 2: Story Verification
# =============================================================================


def build_story_mission(
    persona: str,
    stories: list[Any],
    phase1_results: list[JourneyStep],
) -> Any | None:
    """Build a DazzleAgent Mission for story verification.

    Returns None if there are no stories to verify.
    """
    if not stories:
        return None

    from dazzle.agent.core import Mission

    # Build context from Phase 1 results
    reachable_urls = [s.url_after for s in phase1_results if s.verdict == Verdict.PASS]
    blocked_urls = [
        s.target
        for s in phase1_results
        if s.verdict in (Verdict.FAIL, Verdict.BLOCKED, Verdict.TIMEOUT)
    ]

    story_descriptions = []
    for story in stories:
        story_id = getattr(story, "id", "unknown")
        title = getattr(story, "title", getattr(story, "name", ""))
        desc = getattr(story, "description", "")
        story_descriptions.append(f"- {story_id}: {title}\n  {desc}")

    stories_text = "\n".join(story_descriptions)
    reachable_text = "\n".join(f"  - {u}" for u in reachable_urls[:30])
    blocked_text = "\n".join(f"  - {u}" for u in blocked_urls[:10])

    # Find the persona's default workspace URL from Phase 1
    start_url = None
    for step in phase1_results:
        if step.verdict == Verdict.PASS and step.action == "login":
            start_url = step.url_after
            break

    system_prompt = f"""You are testing a web application as persona '{persona}'.

## Your Stories
{stories_text}

## Phase 1 Navigation Results
Reachable pages:
{reachable_text}

{"Blocked/failed pages:" + chr(10) + blocked_text if blocked_text else "All pages were reachable."}

## Instructions
For each story, navigate to the relevant surfaces and evaluate whether
the workflow is achievable. Record your findings using the 'record_step' tool.
Be specific about what works and what doesn't. Note UX quality observations.

Call 'done' when you have attempted all stories."""

    return Mission(
        name=f"journey_verify:{persona}",
        system_prompt=system_prompt,
        max_steps=30,
        token_budget=100_000,
        start_url=start_url,
        context={
            "persona": persona,
            "story_count": len(stories),
        },
    )


async def run_phase2_verification(
    persona: str,
    stories: list[Any],
    phase1_steps: list[JourneyStep],
    page: Any,
    writer: SessionWriter,
    base_url: str,
) -> list[JourneyStep]:
    """Execute Phase 2 LLM-assisted story verification.

    Uses DazzleAgent with pre-authenticated browser from Phase 1.
    """
    mission = build_story_mission(persona, stories, phase1_steps)
    if mission is None:
        logger.info("Persona '%s' has no stories — Phase 2 skipped.", persona)
        return []

    from dazzle.agent.core import DazzleAgent
    from dazzle.agent.executor import PlaywrightExecutor
    from dazzle.agent.observer import PlaywrightObserver

    observer = PlaywrightObserver(page)
    executor = PlaywrightExecutor(page)
    agent = DazzleAgent(
        observer=observer,
        executor=executor,
    )

    # Collect steps from agent execution
    verify_steps: list[JourneyStep] = []
    step_offset = max((s.step_number for s in phase1_steps), default=0)

    def on_agent_step(step_number: int, step: Step) -> None:
        """Callback to convert agent steps to JourneySteps."""
        nonlocal step_offset
        step_offset = step_number

        # Determine story_id from context if possible
        story_id = None
        if hasattr(step, "action") and hasattr(step.action, "reasoning"):
            for story in stories:
                sid = getattr(story, "id", "")
                if sid and sid in step.action.reasoning:
                    story_id = sid
                    break

        # Get action type string safely
        action_type_val = getattr(step.action, "type", "observe")
        if hasattr(action_type_val, "value"):
            action_type_str = action_type_val.value
        else:
            action_type_str = str(action_type_val)

        js = JourneyStep(
            persona=persona,
            story_id=story_id,
            phase="verify",
            step_number=step_offset,
            action=action_type_str,
            target=getattr(step.action, "target", "") or "",
            url_before=getattr(step.state, "url", ""),
            url_after=getattr(step.state, "url", ""),
            expectation="Story workflow verification",
            observation=step.action.reasoning if hasattr(step.action, "reasoning") else "",
            verdict=Verdict.PASS,  # Agent steps default to PASS; failures caught by agent
            reasoning=step.action.reasoning if hasattr(step.action, "reasoning") else "",
            timestamp=datetime.now(UTC),
        )
        verify_steps.append(js)
        writer.write_step(js)

    # Run the agent
    try:
        await agent.run(mission=mission, on_step=on_agent_step)
    except Exception as exc:
        logger.warning("Phase 2 agent error for %s: %s", persona, exc)

    return verify_steps
