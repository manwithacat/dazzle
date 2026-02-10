"""
Pulse tool handler — founder-ready project health reports.

Chains multiple quality operations and translates their developer-facing
metrics into a single, plain-language briefing suitable for non-technical
founders and product owners.

Operations:
  run — Generate a full health report
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger("dazzle.mcp.handlers.pulse")


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def run_pulse_handler(project_path: Path, args: dict[str, Any]) -> str:
    """Generate a founder-ready project health report.

    Chains five data sources:
      1. pipeline(run, summary=True) — quality & validation
      2. story(coverage) — feature completeness
      3. sitespec(coherence) — live-site readiness
      4. policy(coverage) — security posture
      5. semantics(compliance) — regulatory alignment

    Returns JSON with both structured metrics and a markdown narrative.
    """
    business_context = args.get("business_context")

    t0 = time.monotonic()

    # Collect raw data from each source (failures are captured, not raised)
    pipeline_data = _collect_pipeline(project_path)
    stories_data = _collect_stories(project_path)
    coherence_data = _collect_coherence(project_path, business_context)
    policy_data = _collect_policy(project_path)
    compliance_data = _collect_compliance(project_path)

    # Derive project name from validate step
    project_name = _extract_project_name(pipeline_data, project_path)

    # Synthesise high-level metrics
    radar = _compute_radar(
        pipeline_data, stories_data, coherence_data, policy_data, compliance_data
    )
    health_score = _composite_health(radar)

    # Identify what needs the founder's attention
    needs_input = _founder_decisions(stories_data, coherence_data, policy_data)
    recent_wins = _recent_wins(pipeline_data, stories_data, policy_data)
    blockers = _framework_blockers(pipeline_data, coherence_data)

    # Render the founder-facing markdown
    markdown = _render_markdown(
        project_name=project_name,
        health_score=health_score,
        radar=radar,
        needs_input=needs_input,
        recent_wins=recent_wins,
        blockers=blockers,
        stories_data=stories_data,
        pipeline_data=pipeline_data,
    )

    duration_ms = (time.monotonic() - t0) * 1000

    return json.dumps(
        {
            "status": "complete",
            "project_name": project_name,
            "health_score": round(health_score, 1),
            "radar": radar,
            "needs_input": needs_input,
            "recent_wins": recent_wins,
            "blockers": blockers,
            "markdown": markdown,
            "duration_ms": round(duration_ms, 1),
        },
        indent=2,
    )


# ---------------------------------------------------------------------------
# Data collectors — each calls one handler and returns a parsed dict.
# Failures are captured as {"error": "..."} so the pulse never crashes.
# ---------------------------------------------------------------------------


def _collect_pipeline(project_path: Path) -> dict[str, Any]:
    from .pipeline import run_pipeline_handler

    try:
        raw = run_pipeline_handler(project_path, {"summary": True})
        result: dict[str, Any] = json.loads(raw)
        return result
    except Exception as e:
        logger.warning("pulse: pipeline failed: %s", e)
        return {"error": str(e)}


def _collect_stories(project_path: Path) -> dict[str, Any]:
    from .process import stories_coverage_handler

    try:
        raw = stories_coverage_handler(project_path, {})
        result: dict[str, Any] = json.loads(raw)
        return result
    except Exception as e:
        logger.warning("pulse: story coverage failed: %s", e)
        return {"error": str(e)}


def _collect_coherence(project_path: Path, business_context: str | None) -> dict[str, Any]:
    from .sitespec import coherence_handler

    try:
        coh_args: dict[str, Any] = {}
        if business_context:
            coh_args["business_context"] = business_context
        raw = coherence_handler(project_path, coh_args)
        result: dict[str, Any] = json.loads(raw)
        return result
    except Exception as e:
        logger.warning("pulse: coherence failed: %s", e)
        return {"error": str(e)}


def _collect_policy(project_path: Path) -> dict[str, Any]:
    from .policy import handle_policy

    try:
        raw = handle_policy(project_path, {"operation": "coverage"})
        result: dict[str, Any] = json.loads(raw)
        return result
    except Exception as e:
        logger.warning("pulse: policy coverage failed: %s", e)
        return {"error": str(e)}


def _collect_compliance(project_path: Path) -> dict[str, Any]:
    try:
        from dazzle.mcp.event_first_tools import handle_infer_compliance

        raw = handle_infer_compliance({}, project_path)
        result: dict[str, Any] = json.loads(raw)
        return result
    except Exception as e:
        logger.warning("pulse: compliance failed: %s", e)
        return {"error": str(e)}


# ---------------------------------------------------------------------------
# Metric synthesis
# ---------------------------------------------------------------------------

_RADAR_AXES = ("quality", "coverage", "content", "security", "compliance", "ux")


def _compute_radar(
    pipeline: dict[str, Any],
    stories: dict[str, Any],
    coherence: dict[str, Any],
    policy: dict[str, Any],
    compliance: dict[str, Any],
) -> dict[str, float]:
    """Compute 0-100 scores on six axes."""
    return {
        "quality": _quality_score(pipeline),
        "coverage": _coverage_score(stories),
        "content": _content_score(coherence),
        "security": _security_score(policy),
        "compliance": _compliance_score(compliance),
        "ux": _ux_score(coherence),
    }


def _quality_score(pipeline: dict[str, Any]) -> float:
    """Quality axis: pipeline pass rate."""
    summary = pipeline.get("summary", {})
    total = int(summary.get("total_steps", 0))
    passed = int(summary.get("passed", 0))
    if total == 0:
        return 0.0
    return float(round((passed / total) * 100, 1))


def _coverage_score(stories: dict[str, Any]) -> float:
    """Coverage axis: story implementation coverage."""
    if "error" in stories:
        return 0.0
    return float(round(float(stories.get("coverage_percent", 0.0)), 1))


def _content_score(coherence: dict[str, Any]) -> float:
    """Content axis: site coherence score (how complete the content is)."""
    if "error" in coherence:
        return 0.0
    return round(float(coherence.get("score", 0)), 1)


def _security_score(policy: dict[str, Any]) -> float:
    """Security axis: proportion of entity/persona combos with explicit rules."""
    summary = policy.get("summary", {})
    total = int(summary.get("total_combinations", 0))
    if total == 0:
        return 0.0
    # "covered" = explicit allow + explicit deny (not default-deny)
    covered = int(summary.get("allow", 0)) + int(summary.get("explicit_deny", 0))
    return float(round((covered / total) * 100, 1))


def _compliance_score(compliance: dict[str, Any]) -> float:
    """Compliance axis: sensitive-field detection coverage.

    If no sensitive fields are detected, score is 100 (nothing to protect).
    Otherwise, score is based on how many recommended frameworks are addressable.
    """
    if "error" in compliance:
        return 0.0
    pii = len(compliance.get("pii_fields", []))
    financial = len(compliance.get("financial_fields", []))
    health = len(compliance.get("health_fields", []))
    total_sensitive = pii + financial + health
    if total_sensitive == 0:
        return 100.0  # Nothing to protect
    # Presence of recommended frameworks shows awareness
    frameworks = compliance.get("recommended_frameworks", [])
    suggestions = compliance.get("classification_suggestions", [])
    # Score: proportion of sensitive fields with classification suggestions
    if total_sensitive > 0 and suggestions:
        return round(min(len(suggestions) / total_sensitive, 1.0) * 100, 1)
    # Frameworks detected but no suggestions yet → partial credit
    if frameworks:
        return 50.0
    return 0.0


def _ux_score(coherence: dict[str, Any]) -> float:
    """UX axis: coherence minus errors/warnings penalty."""
    if "error" in coherence:
        return 0.0
    base = float(coherence.get("score", 0))
    errors = int(coherence.get("error_count", 0))
    warnings = int(coherence.get("warning_count", 0))
    # Each error costs 10 pts, each warning costs 3 pts (floor at 0)
    penalty = errors * 10 + warnings * 3
    return float(round(max(base - penalty, 0.0), 1))


def _composite_health(radar: dict[str, float]) -> float:
    """Weighted composite of the six radar axes."""
    weights = {
        "quality": 0.20,
        "coverage": 0.25,
        "content": 0.15,
        "security": 0.15,
        "compliance": 0.10,
        "ux": 0.15,
    }
    total = sum(radar.get(axis, 0) * w for axis, w in weights.items())
    return round(total, 1)


# ---------------------------------------------------------------------------
# Founder-facing narrative helpers
# ---------------------------------------------------------------------------


def _extract_project_name(pipeline: dict[str, Any], project_path: Path) -> str:
    """Best-effort project name from pipeline or path."""
    # Try to find the validate step which has entity/surface counts
    for step in pipeline.get("steps", []):
        if step.get("operation") == "dsl(validate)":
            result = step.get("result", step.get("metrics", {}))
            name = result.get("project_path", "")
            if name:
                return Path(name).name
    return project_path.name


def _founder_decisions(
    stories: dict[str, Any],
    coherence: dict[str, Any],
    policy: dict[str, Any],
) -> list[dict[str, str]]:
    """Identify choices that need the founder's input."""
    decisions: list[dict[str, str]] = []

    # Partial stories need prioritisation
    partial = stories.get("partial", 0)
    uncovered = stories.get("uncovered", 0)
    if partial + uncovered > 0:
        decisions.append(
            {
                "category": "priority",
                "question": (
                    f"{partial + uncovered} customer stories need work — "
                    "which ones matter most for launch?"
                ),
            }
        )

    # Coherence errors need direction
    errors = coherence.get("error_count", 0)
    if errors > 0:
        decisions.append(
            {
                "category": "content",
                "question": (
                    f"Your site has {errors} broken element(s) — fix now or launch anyway?"
                ),
            }
        )

    # Default-deny permissions may need review
    summary = policy.get("summary", {})
    default_deny = summary.get("default_deny", 0)
    if default_deny > 10:
        decisions.append(
            {
                "category": "security",
                "question": (
                    f"{default_deny} permission combinations have no explicit rule — "
                    "review or accept secure defaults?"
                ),
            }
        )

    return decisions


def _recent_wins(
    pipeline: dict[str, Any],
    stories: dict[str, Any],
    policy: dict[str, Any],
) -> list[str]:
    """Celebrate what's working well."""
    wins: list[str] = []

    # Pipeline passing
    summary = pipeline.get("summary", {})
    passed = summary.get("passed", 0)
    total = summary.get("total_steps", 0)
    if total > 0 and passed == total:
        wins.append(f"All {total} quality checks passing")

    # Story coverage milestones
    coverage = stories.get("coverage_percent", 0)
    covered = stories.get("covered", 0)
    total_stories = stories.get("total_stories", 0)
    if coverage >= 80:
        wins.append(f"{covered} of {total_stories} customer journeys working ({coverage:.0f}%)")
    elif covered > 0:
        wins.append(f"{covered} customer journeys implemented so far")

    # Security coverage
    policy_summary = policy.get("summary", {})
    allow = policy_summary.get("allow", 0)
    if allow > 0:
        wins.append(f"Access rules configured ({allow} permission grants)")

    return wins


def _framework_blockers(
    pipeline: dict[str, Any],
    coherence: dict[str, Any],
) -> list[str]:
    """Issues that are framework problems, not founder problems."""
    blockers: list[str] = []

    # Pipeline errors
    for step in pipeline.get("steps", []):
        if step.get("status") == "error":
            error = step.get("error", "unknown error")
            blockers.append(f"{step.get('operation', 'step')}: {error}")

    # Coherence issues that look like rendering bugs
    for issue in coherence.get("issues", []):
        if issue.get("severity") == "error":
            msg = issue.get("message", "")
            if "render" in msg.lower() or "template" in msg.lower():
                blockers.append(msg)

    return blockers[:5]  # Cap at 5


# ---------------------------------------------------------------------------
# Markdown renderer
# ---------------------------------------------------------------------------


def _render_markdown(
    *,
    project_name: str,
    health_score: float,
    radar: dict[str, float],
    needs_input: list[dict[str, str]],
    recent_wins: list[str],
    blockers: list[str],
    stories_data: dict[str, Any],
    pipeline_data: dict[str, Any],
) -> str:
    """Render the founder-facing markdown briefing."""
    # Headline
    lines = [f"{project_name} — {health_score:.0f}% Launch Ready", ""]

    # Status summary (plain-language translation of each axis)
    lines.append("**This Session**")
    lines.append("")
    lines.extend(_render_status_lines(radar, stories_data, pipeline_data))
    lines.append("")

    # Decisions
    if needs_input:
        lines.append("**What Needs Your Input**")
        lines.append("")
        for i, decision in enumerate(needs_input, 1):
            lines.append(f"  {i}. {decision['question']}")
        lines.append("")

    # Blockers
    if blockers:
        lines.append("**Blocked (framework issues)**")
        lines.append("")
        for b in blockers:
            lines.append(f"  - {b}")
        lines.append("")

    # Wins
    if recent_wins:
        lines.append("**Recent Wins**")
        lines.append("")
        for w in recent_wins:
            lines.append(f"  + {w}")
        lines.append("")

    # Radar summary
    lines.append("**Readiness Radar**")
    lines.append("")
    for axis in _RADAR_AXES:
        score = radar.get(axis, 0)
        bar = _progress_bar(score)
        label = axis.replace("_", " ").title()
        lines.append(f"  {label:12s} {bar} {score:.0f}%")
    lines.append("")

    return "\n".join(lines)


def _render_status_lines(
    radar: dict[str, float],
    stories: dict[str, Any],
    pipeline: dict[str, Any],
) -> list[str]:
    """Translate radar scores into plain-language status lines."""
    lines: list[str] = []

    # Stories
    covered = stories.get("covered", 0)
    total = stories.get("total_stories", 0)
    pct = stories.get("coverage_percent", 0)
    if total > 0:
        lines.append(f"  Customer journeys: {covered} of {total} working ({pct:.0f}%)")

    # Quality
    summary = pipeline.get("summary", {})
    passed = summary.get("passed", 0)
    total_steps = summary.get("total_steps", 0)
    failed = summary.get("failed", 0)
    if total_steps > 0:
        if failed == 0:
            lines.append(f"  Quality: {passed} checks passing, 0 failing")
        else:
            lines.append(f"  Quality: {passed} of {total_steps} checks passing ({failed} failing)")

    # Security
    if radar.get("security", 0) > 0:
        lines.append(f"  Security: {radar['security']:.0f}% of permissions explicitly configured")

    # Content
    if radar.get("content", 0) > 0:
        lines.append(f"  Site content: {radar['content']:.0f}% coherence score")

    return lines


def _progress_bar(value: float, width: int = 20) -> str:
    """Render an ASCII progress bar."""
    filled = int(round(value / 100 * width))
    return "[" + "#" * filled + "-" * (width - filled) + "]"
