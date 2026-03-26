"""Data models for persona-driven E2E journey testing.

These are pure data types — no browser or LLM dependencies.
"""

from __future__ import annotations  # required: forward reference

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict


class Verdict(StrEnum):
    """Outcome verdict for a single journey step."""

    PASS = "pass"
    PARTIAL = "partial"
    FAIL = "fail"
    BLOCKED = "blocked"
    DEAD_END = "dead_end"
    SCOPE_LEAK = "scope_leak"
    CONFUSING = "confusing"
    NAV_BREAK = "nav_break"
    TIMEOUT = "timeout"


class JourneyStep(BaseModel):
    """Atomic unit of observation in a journey session."""

    model_config = ConfigDict(frozen=True)

    persona: str
    story_id: str | None = None
    phase: Literal["explore", "verify"]
    step_number: int
    action: str
    target: str
    url_before: str
    url_after: str
    expectation: str
    observation: str
    verdict: Verdict
    reasoning: str
    screenshot_path: str | None = None
    timestamp: datetime


class JourneySession(BaseModel):
    """Per-persona aggregate of journey steps."""

    persona: str
    run_date: str
    steps: list[JourneyStep]
    verdict_counts: dict[str, int]
    stories_attempted: int
    stories_covered: int

    @classmethod
    def from_steps(
        cls,
        persona: str,
        steps: list[JourneyStep],
        run_date: str,
    ) -> JourneySession:
        """Build a session from a list of steps, computing aggregates."""
        counts: dict[str, int] = {v.value: 0 for v in Verdict}
        for step in steps:
            counts[step.verdict.value] = counts.get(step.verdict.value, 0) + 1

        # Group verify-phase steps by story_id
        story_steps: dict[str, list[JourneyStep]] = {}
        for step in steps:
            if step.story_id is not None:
                story_steps.setdefault(step.story_id, []).append(step)

        stories_attempted = len(story_steps)
        passing = {Verdict.PASS, Verdict.PARTIAL}
        stories_covered = sum(
            1 for ss in story_steps.values() if all(s.verdict in passing for s in ss)
        )

        return cls(
            persona=persona,
            run_date=run_date,
            steps=steps,
            verdict_counts=counts,
            stories_attempted=stories_attempted,
            stories_covered=stories_covered,
        )


class CrossPersonaPattern(BaseModel):
    """Systemic finding across multiple personas."""

    model_config = ConfigDict(frozen=True)

    id: str
    title: str
    severity: Literal["critical", "high", "medium", "low"]
    affected_personas: list[str]
    description: str
    evidence: list[str]
    recommendation: str


class DeadEnd(BaseModel):
    """A navigation dead-end encountered during journey testing."""

    model_config = ConfigDict(frozen=True)

    id: str
    persona: str
    page: str
    story: str | None
    description: str


class NavBreak(BaseModel):
    """A broken navigation path affecting one or more personas."""

    model_config = ConfigDict(frozen=True)

    id: str
    description: str
    affected_personas: list[str]
    workaround: str | None


class Recommendation(BaseModel):
    """Prioritized recommendation from journey analysis."""

    model_config = ConfigDict(frozen=True)

    priority: int
    title: str
    description: str
    effort: str
    affected_entities: list[str]


class AnalysisReport(BaseModel):
    """Top-level cross-persona analysis report."""

    model_config = ConfigDict(frozen=True)

    run_id: str
    dazzle_version: str
    deployment_url: str
    personas_analysed: int
    personas_failed: list[str]
    total_steps: int
    total_stories: int
    verdict_counts: dict[str, int]
    cross_persona_patterns: list[CrossPersonaPattern]
    dead_ends: list[DeadEnd]
    nav_breaks: list[NavBreak]
    scope_leaks: list[str]
    recommendations: list[Recommendation]


class NavigationTarget(BaseModel):
    """A URL to visit during Phase 1 deterministic exploration."""

    model_config = ConfigDict(frozen=True)

    url: str
    entity_name: str
    surface_mode: str
    expectation: str
