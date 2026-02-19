"""MCP handler for structural fidelity scoring."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from .common import extract_progress, load_project_appspec, wrap_handler_errors

logger = logging.getLogger("dazzle.mcp")


@wrap_handler_errors
def score_fidelity_handler(project_path: Path, arguments: dict[str, Any]) -> str:
    """Score rendered HTML fidelity against the AppSpec.

    Args:
        project_path: Path to the project directory.
        arguments: MCP tool arguments (optional surface_filter).

    Returns:
        JSON string with fidelity report.
    """
    progress = extract_progress(arguments)
    try:
        from dazzle.core.fidelity_scorer import score_appspec_fidelity
    except ImportError:
        return json.dumps({"error": "fidelity_scorer module not available"})

    # Parse and link DSL
    progress.log_sync("Loading project DSL...")
    appspec = load_project_appspec(project_path)

    # Validate DSL before proceeding
    progress.log_sync("Linting DSL...")
    from dazzle.core.lint import lint_appspec

    lint_errors, lint_warnings = lint_appspec(appspec)
    if lint_errors:
        return json.dumps(
            {
                "error": "DSL has validation errors. Fix these before running fidelity.",
                "lint_errors": lint_errors,
            }
        )

    # Try to compile and render surfaces
    try:
        from dazzle_ui.converters.template_compiler import compile_appspec_to_templates
        from dazzle_ui.runtime.template_renderer import render_page
    except ImportError:
        return json.dumps(
            {
                "error": "dazzle_ui not installed. Install it to enable fidelity scoring.",
                "hint": "pip install -e '.[dazzle-ui]'",
            }
        )

    progress.log_sync("Compiling templates...")
    page_contexts = compile_appspec_to_templates(appspec)

    # Render each page and build surface_name → HTML mapping
    progress.log_sync(f"Rendering {len(page_contexts)} pages...")
    rendered_pages: dict[str, str] = {}
    render_failure_details: list[dict[str, str]] = []
    for _route, ctx in page_contexts.items():
        try:
            html = render_page(ctx)
            # Use view_name from PageContext — this is the surface name
            rendered_pages[ctx.view_name] = html
        except Exception as e:  # nosec B112 - skip unrenderable pages gracefully
            logger.warning("Fidelity: failed to render %s: %s", ctx.view_name, e)
            render_failure_details.append({"surface": ctx.view_name, "error": str(e)})
            continue

    if page_contexts and not rendered_pages:
        return json.dumps(
            {
                "error": "All surfaces failed to render",
                "surfaces_attempted": len(page_contexts),
                "render_failure_details": render_failure_details,
                "hint": "Run status(operation='logs') for details",
            }
        )

    progress.log_sync("Scoring fidelity...")
    surface_filter = arguments.get("surface_filter")
    report = score_appspec_fidelity(appspec, rendered_pages, surface_filter, str(project_path))

    # Build response
    surface_breakdown = []
    for ss in report.surface_scores:
        surface_breakdown.append(
            {
                "surface": ss.surface_name,
                "structural": ss.structural,
                "semantic": ss.semantic,
                "story": ss.story,
                "overall": ss.overall,
                "gap_count": len(ss.gaps),
            }
        )

    gaps_only = arguments.get("gaps_only", False)
    if gaps_only:
        surface_breakdown = [
            s
            for s in surface_breakdown
            if s["overall"] < 1.0  # type: ignore[operator]
        ]

    # Top 5 recommendations from highest-severity gaps
    all_gaps = []
    for ss in report.surface_scores:
        all_gaps.extend(ss.gaps)
    severity_order = {"critical": 0, "major": 1, "minor": 2}
    all_gaps.sort(key=lambda g: severity_order.get(g.severity, 3))
    top_recommendations = [
        {
            "surface": g.surface_name,
            "category": g.category.value,
            "severity": g.severity,
            "recommendation": g.recommendation,
        }
        for g in all_gaps[:5]
    ]

    result: dict[str, Any] = {
        "overall_fidelity": report.overall,
        "story_coverage": report.story_coverage,
        "total_gaps": report.total_gaps,
        "gap_counts_by_category": report.gap_counts,
        "surfaces": surface_breakdown,
        "top_recommendations": top_recommendations,
        "next_steps": _build_next_steps(report),
    }
    if render_failure_details:
        result["render_failures"] = len(render_failure_details)
        result["render_failure_details"] = render_failure_details
    if lint_warnings:
        result["lint_warnings"] = lint_warnings

    if report.total_gaps > 0:
        result["discovery_hint"] = (
            f"{report.total_gaps} fidelity gaps found. "
            "Use discovery(operation='run', mode='entity_completeness') "
            "to analyze CRUD coverage gaps, or mode='persona' for deeper UX exploration."
        )

    return json.dumps(result, indent=2)


def _build_next_steps(report: Any) -> list[str]:
    """Generate actionable next steps from the report."""
    steps: list[str] = []
    if report.overall < 0.5:
        steps.append("Critical: Many surfaces have structural issues. Fix missing elements first.")
        steps.append(
            "If this looks like a Dazzle bug, file it: "
            "`contribution(operation='create', type='bug_fix')`"
        )
    elif report.overall < 0.8:
        steps.append("Fix major gaps to improve fidelity above 0.8.")

    if report.gap_counts.get("missing_field", 0) > 0:
        steps.append("Add missing fields to surface HTML outputs.")
    if report.gap_counts.get("incorrect_input_type", 0) > 0:
        steps.append("Correct input types to match field type kinds.")
    if report.gap_counts.get("missing_design_tokens", 0) > 0:
        steps.append("Include design tokens in rendered pages.")
    if report.story_coverage < 0.5:
        steps.append("Add story-related action affordances to surfaces.")

    if not steps:
        steps.append("Fidelity is good. Consider adding more story coverage.")

    return steps
