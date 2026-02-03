"""MCP handler for structural fidelity scoring."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger("dazzle.mcp")


def score_fidelity_handler(project_path: Path, arguments: dict[str, Any]) -> str:
    """Score rendered HTML fidelity against the AppSpec.

    Args:
        project_path: Path to the project directory.
        arguments: MCP tool arguments (optional surface_filter).

    Returns:
        JSON string with fidelity report.
    """
    try:
        from dazzle.core.fidelity_scorer import score_appspec_fidelity
    except ImportError:
        return json.dumps({"error": "fidelity_scorer module not available"})

    # Parse and link DSL
    from dazzle.core.fileset import discover_dsl_files
    from dazzle.core.linker import build_appspec
    from dazzle.core.manifest import load_manifest
    from dazzle.core.parser import parse_modules

    try:
        manifest = load_manifest(project_path / "dazzle.toml")
        dsl_files = discover_dsl_files(project_path, manifest)
        modules = parse_modules(dsl_files)
        appspec = build_appspec(modules, manifest.project_root)
    except Exception as e:
        return json.dumps({"error": f"Failed to parse/link DSL: {e}"})

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

    try:
        page_contexts = compile_appspec_to_templates(appspec)
    except Exception as e:
        return json.dumps({"error": f"Failed to compile templates: {e}"})

    # Render each page and build surface_name → HTML mapping
    rendered_pages: dict[str, str] = {}
    for _route, ctx in page_contexts.items():
        try:
            html = render_page(ctx)
            # Use view_name from PageContext — this is the surface name
            rendered_pages[ctx.view_name] = html
        except Exception as e:  # nosec B112 - skip unrenderable pages gracefully
            logger.warning("Fidelity: failed to render %s: %s", ctx.view_name, e)
            continue

    if page_contexts and not rendered_pages:
        return json.dumps(
            {
                "error": "All surfaces failed to render",
                "surfaces_attempted": len(page_contexts),
                "hint": "Run status(operation='logs') for details",
            }
        )

    render_failures = len(page_contexts) - len(rendered_pages)
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
    if render_failures > 0:
        result["render_failures"] = render_failures

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
