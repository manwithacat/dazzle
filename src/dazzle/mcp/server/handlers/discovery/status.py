"""Discovery status, verification, and coherence handlers."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from dazzle.mcp.server.paths import project_discovery_dir, project_kg_db

from ..common import wrap_handler_errors
from ._helpers import _load_appspec

logger = logging.getLogger("dazzle.mcp.handlers.discovery")


@wrap_handler_errors
def verify_all_stories_handler(project_path: Path, args: dict[str, Any]) -> str:
    """
    Batch verify all accepted stories against API tests.

    Loads all accepted stories, maps each to its entity tests via scope,
    runs them, and returns a structured pass/fail report — the automated UAT.
    """
    from dazzle.core.ir.stories import StoryStatus
    from dazzle.core.stories_persistence import get_stories_by_status

    from ..dsl_test import verify_story_handler

    base_url = args.get("base_url")

    # Load accepted stories
    stories = get_stories_by_status(project_path, StoryStatus.ACCEPTED)
    if not stories:
        return json.dumps(
            {
                "status": "no_stories",
                "message": "No accepted stories found. Use story(operation='propose') and accept them first.",
            },
            indent=2,
        )

    # Run verify_story for all stories at once (the handler handles batching)
    all_ids = [s.story_id for s in stories]
    verify_args: dict[str, Any] = {
        "story_ids": all_ids,
    }
    if base_url:
        verify_args["base_url"] = base_url

    raw_result = verify_story_handler(project_path, verify_args)
    result_data = json.loads(raw_result)

    # Wrap with discovery-specific metadata
    if "error" in result_data:
        return raw_result

    response: dict[str, Any] = {
        "operation": "verify_all_stories",
        "total_accepted_stories": len(stories),
        **result_data,
        "summary": (
            f"{result_data.get('stories_passed', 0)}/{len(stories)} stories verified successfully"
        ),
    }

    return json.dumps(response, indent=2)


@wrap_handler_errors
def discovery_status_handler(project_path: Path, args: dict[str, Any]) -> str:
    """
    Check discovery infrastructure status.

    Reports whether the project has valid DSL, KG availability, etc.
    """
    result: dict[str, Any] = {
        "project_path": str(project_path),
        "dsl_valid": False,
        "kg_available": False,
        "reports_count": 0,
    }

    # Check DSL
    try:
        appspec = _load_appspec(project_path)
        result["dsl_valid"] = True
        result["entities"] = (
            len(appspec.domain.entities) if hasattr(appspec.domain, "entities") else 0
        )
        result["surfaces"] = len(appspec.surfaces)
        result["personas"] = len(appspec.personas)
    except Exception as e:
        result["dsl_error"] = str(e)

    # Check KG
    kg_db = project_kg_db(project_path)
    result["kg_available"] = kg_db.exists()

    # Check existing reports
    report_dir = project_discovery_dir(project_path)
    if report_dir.exists():
        result["reports_count"] = len(list(report_dir.glob("*.json")))

    return json.dumps(result, indent=2)


# =============================================================================
# App Coherence Handler
# =============================================================================

# Gap type → named coherence check + severity weight
_GAP_TO_CHECK: dict[str, tuple[str, str]] = {
    "workspace_unreachable": ("workspace_binding", "error"),
    "surface_inaccessible": ("surface_access", "error"),
    "story_no_surface": ("story_coverage", "error"),
    "process_step_no_surface": ("workflow_wiring", "error"),
    "experience_broken_step": ("experience_integrity", "error"),
    "experience_dangling_transition": ("experience_integrity", "warning"),
    "unreachable_experience": ("experience_reachable", "error"),
    "orphan_surfaces": ("dead_ends", "suggestion"),
    "cross_entity_gap": ("cross_entity_nav", "warning"),
    "nav_over_exposed": ("nav_filtering", "error"),
    "nav_under_exposed": ("nav_filtering", "warning"),
}

_SEVERITY_WEIGHTS: dict[str, int] = {
    "error": 20,
    "warning": 5,
    "suggestion": 1,
}

_PRIORITY_MULTIPLIERS: dict[str, float] = {
    "critical": 2.0,
    "high": 1.5,
    "medium": 1.0,
    "low": 0.5,
}


def _compute_coherence_score(deductions: float) -> int:
    """Compute a 0-100 coherence score from accumulated deductions."""
    return max(0, min(100, round(100 - deductions)))


@wrap_handler_errors
def app_coherence_handler(project_path: Path, args: dict[str, Any]) -> str:
    """
    Run persona-by-persona authenticated UX coherence checks.

    Synthesizes headless discovery gaps into named checks with a coherence
    score per persona, using the same scoring model as sitespec(coherence).

    Args (via args dict):
        persona: Optional persona ID to check (default: all)
    """
    from dazzle.agent.missions.persona_journey import run_headless_discovery

    appspec = _load_appspec(project_path)
    persona_filter = args.get("persona")
    persona_ids = [persona_filter] if persona_filter else None

    report = run_headless_discovery(
        appspec,
        persona_ids=persona_ids,
        include_entity_analysis=False,
        include_workflow_analysis=False,
    )

    persona_results: list[dict[str, Any]] = []

    for pr in report.persona_reports:
        # Aggregate gaps into named checks
        checks: dict[str, dict[str, Any]] = {}

        for gap in pr.gaps:
            check_name, severity_category = _GAP_TO_CHECK.get(gap.gap_type, ("other", "warning"))

            if check_name not in checks:
                checks[check_name] = {
                    "check": check_name,
                    "status": "pass",
                    "issues": [],
                }

            # Escalate status: pass → suggestion → warn → fail
            current = checks[check_name]["status"]
            if severity_category == "error" and current != "fail":
                checks[check_name]["status"] = "fail"
            elif severity_category == "warning" and current in ("pass", "suggestion"):
                checks[check_name]["status"] = "warn"
            elif severity_category == "suggestion" and current == "pass":
                checks[check_name]["status"] = "suggestion"

            checks[check_name]["issues"].append(
                {
                    "gap_type": gap.gap_type,
                    "severity": gap.severity,
                    "description": gap.description,
                    "surface_name": gap.surface_name or "",
                }
            )

        # Compute score with priority weighting
        # Build surface → priority lookup from appspec
        surface_priority: dict[str, str] = {}
        for s in getattr(appspec, "surfaces", []) or []:
            p = str(getattr(s, "priority", "medium")).lower()
            surface_priority[s.name] = p

        total_deductions: float = 0
        for check in checks.values():
            for issue in check["issues"]:
                gap_type = issue["gap_type"]
                _, sev_cat = _GAP_TO_CHECK.get(gap_type, ("other", "warning"))
                base_weight = _SEVERITY_WEIGHTS.get(sev_cat, 5)
                # Apply priority multiplier from the surface if available
                surface_name = issue.get("surface_name", "")
                priority = surface_priority.get(surface_name, "medium")
                multiplier = _PRIORITY_MULTIPLIERS.get(priority, 1.0)
                total_deductions += base_weight * multiplier

        # Add detail summary to each check
        for check in checks.values():
            if check["issues"]:
                check["detail"] = check["issues"][0]["description"]
                if len(check["issues"]) > 1:
                    check["detail"] += f" (+{len(check['issues']) - 1} more)"
            # Remove raw issues from output to keep it concise
            del check["issues"]

        # Ensure standard checks appear even when passed
        for standard_check in [
            "workspace_binding",
            "nav_filtering",
            "experience_reachable",
            "surface_access",
            "story_coverage",
        ]:
            if standard_check not in checks:
                checks[standard_check] = {
                    "check": standard_check,
                    "status": "pass",
                }

        score = _compute_coherence_score(total_deductions)
        persona_results.append(
            {
                "persona": pr.persona_id,
                "coherence_score": score,
                "workspace": pr.default_workspace,
                "checks": list(checks.values()),
                "gap_count": len(pr.gaps),
            }
        )

    # Overall score = average of persona scores
    overall_score = (
        round(sum(p["coherence_score"] for p in persona_results) / len(persona_results))
        if persona_results
        else 100
    )

    return json.dumps(
        {
            "overall_score": overall_score,
            "personas": persona_results,
            "skipped_personas": report.skipped_personas,
            "persona_count": len(persona_results),
        },
        indent=2,
    )
