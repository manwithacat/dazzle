"""Cross-persona pattern analyser for E2E journey testing.

Analyses multiple JourneySession results to detect systemic issues
that only become visible when comparing behaviour across personas.
"""

from __future__ import annotations

import re
import uuid
from collections import defaultdict

from dazzle.agent.journey_models import (
    AnalysisReport,
    CrossPersonaPattern,
    DeadEnd,
    JourneySession,
    NavBreak,
    Recommendation,
    Verdict,
)

# Patterns for detecting row counts and empty states in observations
_ROW_COUNT_RE = re.compile(r"(\d+)\s*rows?", re.IGNORECASE)
_EMPTY_RE = re.compile(r"\b(empty|no\s+results?|0\s*rows?)\b", re.IGNORECASE)
_UUID_RE = re.compile(r"\bUUID\b", re.IGNORECASE)
_TEXT_INPUT_RE = re.compile(r"\btext\s+input\b", re.IGNORECASE)

_SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}


def _entity_from_target(target: str) -> str:
    """Extract an entity-like key from a URL path.

    /app/tasks/create -> tasks
    /app/orders       -> orders
    """
    parts = [p for p in target.strip("/").split("/") if p]
    if len(parts) >= 2:
        return parts[1]
    if parts:
        return parts[0]
    return target


def _has_data(observation: str) -> bool:
    """Return True if the observation indicates populated data."""
    match = _ROW_COUNT_RE.search(observation)
    if match:
        count = int(match.group(1))
        return count > 0
    return False


def _is_empty(observation: str) -> bool:
    """Return True if the observation indicates empty/no data."""
    return bool(_EMPTY_RE.search(observation))


def _detect_scope_leaks(
    sessions: list[JourneySession],
) -> list[CrossPersonaPattern]:
    """Compare observations across personas for the same entity to find scope issues."""
    if len(sessions) < 2:
        return []

    # Group steps by entity and persona
    entity_persona_obs: dict[str, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))
    for session in sessions:
        for step in session.steps:
            entity = _entity_from_target(step.target)
            entity_persona_obs[entity][session.persona].append(step.observation)

    patterns: list[CrossPersonaPattern] = []
    for entity, persona_obs in entity_persona_obs.items():
        if len(persona_obs) < 2:
            continue

        populated_personas: list[str] = []
        empty_personas: list[str] = []

        for persona, observations in persona_obs.items():
            for obs in observations:
                if _has_data(obs):
                    populated_personas.append(persona)
                    break
                if _is_empty(obs):
                    empty_personas.append(persona)
                    break

        if populated_personas and empty_personas:
            all_affected = sorted(set(populated_personas + empty_personas))
            evidence = []
            for p in populated_personas:
                evidence.append(f"{p}: sees data for {entity}")
            for p in empty_personas:
                evidence.append(f"{p}: sees empty for {entity}")

            patterns.append(
                CrossPersonaPattern(
                    id="",  # assigned later
                    title=f"Scope filtering issue on {entity}",
                    severity="high",
                    affected_personas=all_affected,
                    description=(
                        f"Different personas see different data volumes for '{entity}'. "
                        f"This may indicate a scope-rule misconfiguration."
                    ),
                    evidence=evidence,
                    recommendation=f"Review scope rules for entity '{entity}' to ensure correct row filtering.",
                )
            )

    return patterns


def _detect_fk_uuid(sessions: list[JourneySession]) -> list[CrossPersonaPattern]:
    """Detect FK fields rendered as raw UUIDs or plain text inputs."""
    patterns: list[CrossPersonaPattern] = []
    seen_targets: set[str] = set()

    for session in sessions:
        for step in session.steps:
            if step.target in seen_targets:
                continue
            obs = step.observation
            if _UUID_RE.search(obs) or _TEXT_INPUT_RE.search(obs):
                seen_targets.add(step.target)
                entity = _entity_from_target(step.target)
                patterns.append(
                    CrossPersonaPattern(
                        id="",
                        title=f"FK/UUID display issue on {entity}",
                        severity="medium",
                        affected_personas=[step.persona],
                        description=(
                            f"A reference field on '{entity}' is rendered as a raw UUID or "
                            f"plain text input instead of a user-friendly selector."
                        ),
                        evidence=[f"{step.persona}: {obs[:120]}"],
                        recommendation=(
                            f"Add a lookup/select widget for foreign-key fields on '{entity}'."
                        ),
                    )
                )

    return patterns


def _detect_navigation_gaps(sessions: list[JourneySession]) -> list[CrossPersonaPattern]:
    """Detect steps with BLOCKED verdict as navigation gaps."""
    patterns: list[CrossPersonaPattern] = []
    seen_targets: set[str] = set()

    for session in sessions:
        for step in session.steps:
            if step.verdict == Verdict.BLOCKED and step.target not in seen_targets:
                seen_targets.add(step.target)
                patterns.append(
                    CrossPersonaPattern(
                        id="",
                        title=f"Blocked navigation to {step.target}",
                        severity="high",
                        affected_personas=[step.persona],
                        description=f"Navigation to '{step.target}' is blocked: {step.observation}",
                        evidence=[f"{step.persona}: {step.observation[:120]}"],
                        recommendation=f"Check access permissions and routing for '{step.target}'.",
                    )
                )

    return patterns


def _detect_common_failures(sessions: list[JourneySession]) -> list[CrossPersonaPattern]:
    """Detect entities where 3+ personas encounter failures."""
    entity_personas: dict[str, set[str]] = defaultdict(set)
    entity_evidence: dict[str, list[str]] = defaultdict(list)

    fail_verdicts = {Verdict.FAIL, Verdict.BLOCKED}
    for session in sessions:
        for step in session.steps:
            if step.verdict in fail_verdicts:
                entity = _entity_from_target(step.target)
                entity_personas[entity].add(step.persona)
                entity_evidence[entity].append(f"{step.persona}: {step.observation[:80]}")

    patterns: list[CrossPersonaPattern] = []
    for entity, personas in entity_personas.items():
        if len(personas) >= 3:
            patterns.append(
                CrossPersonaPattern(
                    id="",
                    title=f"Systemic failure on {entity}",
                    severity="critical" if len(personas) >= 4 else "high",
                    affected_personas=sorted(personas),
                    description=(
                        f"Entity '{entity}' fails for {len(personas)} personas. "
                        f"This is likely a systemic issue rather than a permissions problem."
                    ),
                    evidence=entity_evidence[entity][:6],
                    recommendation=f"Investigate the '{entity}' page for server-side errors.",
                )
            )

    return patterns


def _extract_dead_ends(sessions: list[JourneySession]) -> list[DeadEnd]:
    """Extract DEAD_END verdict steps as DeadEnd objects."""
    dead_ends: list[DeadEnd] = []
    counter = 0

    for session in sessions:
        for step in session.steps:
            if step.verdict == Verdict.DEAD_END:
                counter += 1
                dead_ends.append(
                    DeadEnd(
                        id=f"DE-{counter:03d}",
                        persona=step.persona,
                        page=step.target,
                        story=step.story_id,
                        description=step.observation,
                    )
                )

    return dead_ends


def _extract_nav_breaks(sessions: list[JourneySession]) -> list[NavBreak]:
    """Extract NAV_BREAK verdict steps, merging by target URL."""
    target_personas: dict[str, list[str]] = defaultdict(list)
    target_obs: dict[str, str] = {}

    for session in sessions:
        for step in session.steps:
            if step.verdict == Verdict.NAV_BREAK:
                if step.persona not in target_personas[step.target]:
                    target_personas[step.target].append(step.persona)
                if step.target not in target_obs:
                    target_obs[step.target] = step.observation

    nav_breaks: list[NavBreak] = []
    for i, (target, personas) in enumerate(target_personas.items(), 1):
        nav_breaks.append(
            NavBreak(
                id=f"NB-{i:03d}",
                description=f"Navigation break at {target}: {target_obs[target]}",
                affected_personas=sorted(personas),
                workaround=None,
            )
        )

    return nav_breaks


def _build_recommendations(
    patterns: list[CrossPersonaPattern],
    dead_ends: list[DeadEnd],
    nav_breaks: list[NavBreak],
) -> list[Recommendation]:
    """Generate prioritized recommendations from detected patterns."""
    recs: list[Recommendation] = []

    # Sort patterns by severity for priority assignment
    sorted_patterns = sorted(patterns, key=lambda p: _SEVERITY_ORDER.get(p.severity, 99))

    for i, pattern in enumerate(sorted_patterns, 1):
        # Extract entity from title
        entities: list[str] = []
        for word in pattern.title.split():
            if word not in {
                "Scope",
                "filtering",
                "issue",
                "on",
                "FK/UUID",
                "display",
                "Blocked",
                "navigation",
                "to",
                "Systemic",
                "failure",
            }:
                entities.append(word)

        effort = "small"
        if pattern.severity in ("critical", "high"):
            effort = "medium"
        if len(pattern.affected_personas) >= 3:
            effort = "large"

        recs.append(
            Recommendation(
                priority=i,
                title=f"Fix: {pattern.title}",
                description=pattern.recommendation,
                effort=effort,
                affected_entities=entities,
            )
        )

    # Dead ends
    for de in dead_ends:
        recs.append(
            Recommendation(
                priority=len(sorted_patterns) + 1,
                title=f"Resolve dead-end at {de.page}",
                description=f"Add navigation from {de.page} back to a parent page.",
                effort="small",
                affected_entities=[de.page],
            )
        )

    # Nav breaks
    for nb in nav_breaks:
        recs.append(
            Recommendation(
                priority=len(sorted_patterns) + 2,
                title=f"Fix navigation break: {nb.description[:60]}",
                description="Repair broken navigation link.",
                effort="small",
                affected_entities=[],
            )
        )

    # Re-sort by priority
    recs.sort(key=lambda r: r.priority)
    return recs


def _assign_pattern_ids(patterns: list[CrossPersonaPattern]) -> list[CrossPersonaPattern]:
    """Assign sequential CPP-NNN IDs to patterns."""
    result: list[CrossPersonaPattern] = []
    for i, p in enumerate(patterns, 1):
        result.append(p.model_copy(update={"id": f"CPP-{i:03d}"}))
    return result


def _compute_verdict_counts(sessions: list[JourneySession]) -> dict[str, int]:
    """Aggregate verdict counts across all sessions."""
    counts: dict[str, int] = {v.value: 0 for v in Verdict}
    for session in sessions:
        for k, v in session.verdict_counts.items():
            counts[k] = counts.get(k, 0) + v
    return counts


def _compute_personas_failed(sessions: list[JourneySession]) -> list[str]:
    """Return personas that have any FAIL or BLOCKED verdicts."""
    failed: list[str] = []
    fail_keys = {Verdict.FAIL.value, Verdict.BLOCKED.value}
    for session in sessions:
        if any(session.verdict_counts.get(k, 0) > 0 for k in fail_keys):
            failed.append(session.persona)
    return sorted(failed)


def analyse_sessions(
    sessions: list[JourneySession],
    appspec: object | None = None,
    dazzle_version: str = "0.44.0",
    deployment_url: str = "",
) -> AnalysisReport:
    """Analyse journey sessions to detect cross-persona patterns.

    Parameters
    ----------
    sessions:
        Per-persona journey sessions to compare.
    appspec:
        Optional AppSpec for RBAC-specific checks. When None, those checks
        are skipped.
    dazzle_version:
        Version string for the report header.
    deployment_url:
        URL of the tested deployment.

    Returns
    -------
    AnalysisReport with detected patterns, dead-ends, nav breaks,
    and prioritized recommendations.
    """
    if not sessions:
        return AnalysisReport(
            run_id=uuid.uuid4().hex[:12],
            dazzle_version=dazzle_version,
            deployment_url=deployment_url,
            personas_analysed=0,
            personas_failed=[],
            total_steps=0,
            total_stories=0,
            verdict_counts={v.value: 0 for v in Verdict},
            cross_persona_patterns=[],
            dead_ends=[],
            nav_breaks=[],
            scope_leaks=[],
            recommendations=[],
        )

    # Run all detection passes
    patterns: list[CrossPersonaPattern] = []
    patterns.extend(_detect_scope_leaks(sessions))
    patterns.extend(_detect_fk_uuid(sessions))
    patterns.extend(_detect_navigation_gaps(sessions))
    patterns.extend(_detect_common_failures(sessions))

    # Assign sequential IDs
    patterns = _assign_pattern_ids(patterns)

    # Extract structural issues
    dead_ends = _extract_dead_ends(sessions)
    nav_breaks = _extract_nav_breaks(sessions)

    # Build recommendations
    recommendations = _build_recommendations(patterns, dead_ends, nav_breaks)

    # Compute aggregates
    total_steps = sum(len(s.steps) for s in sessions)
    total_stories = sum(s.stories_attempted for s in sessions)
    verdict_counts = _compute_verdict_counts(sessions)
    personas_failed = _compute_personas_failed(sessions)

    # Scope leaks as string summaries
    scope_leaks = [p.title for p in patterns if "scope" in p.title.lower()]

    return AnalysisReport(
        run_id=uuid.uuid4().hex[:12],
        dazzle_version=dazzle_version,
        deployment_url=deployment_url,
        personas_analysed=len(sessions),
        personas_failed=personas_failed,
        total_steps=total_steps,
        total_stories=total_stories,
        verdict_counts=verdict_counts,
        cross_persona_patterns=patterns,
        dead_ends=dead_ends,
        nav_breaks=nav_breaks,
        scope_leaks=scope_leaks,
        recommendations=recommendations,
    )
