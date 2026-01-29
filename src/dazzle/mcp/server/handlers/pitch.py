"""
MCP handler for pitch operations.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Sections that make a pitch deck investor-ready
_PITCH_SECTIONS = [
    "problem",
    "solution",
    "market",
    "business_model",
    "financials",
    "team",
    "milestones",
]


def _get_missing_sections(spec: Any) -> list[str]:
    """Return list of unpopulated pitch sections."""
    missing: list[str] = []
    for section in _PITCH_SECTIONS:
        val = getattr(spec, section, None)
        if val is None:
            missing.append(section)
    return missing


def _completeness_score(spec: Any) -> int:
    """Return percentage of sections populated (0-100)."""
    populated = sum(1 for s in _PITCH_SECTIONS if getattr(spec, s, None) is not None)
    return int(populated / len(_PITCH_SECTIONS) * 100)


def scaffold_pitchspec_handler(project_root: Path, args: dict[str, Any]) -> str:
    """Scaffold a pitchspec.yaml file."""
    from dazzle.pitch.loader import scaffold_pitchspec

    overwrite = args.get("overwrite", False)

    try:
        result = scaffold_pitchspec(project_root, overwrite=overwrite)

        if result:
            return json.dumps(
                {
                    "success": True,
                    "created": str(result),
                    "message": "Created pitchspec.yaml. Edit it and run pitch generate.",
                    "next_steps": [
                        "Edit pitchspec.yaml with your company details, problem, solution, and market data",
                        "Run pitch(operation='validate') to check completeness",
                        "Run pitch(operation='generate', format='all') to build the deck",
                    ],
                },
                indent=2,
            )
        else:
            return json.dumps(
                {
                    "success": False,
                    "message": "pitchspec.yaml already exists. Use overwrite=true to replace.",
                    "next_steps": [
                        "Run pitch(operation='get') to see current pitchspec contents",
                        "Run pitch(operation='validate') to check for issues",
                    ],
                },
                indent=2,
            )
    except Exception as e:
        logger.exception("Error scaffolding pitchspec")
        return json.dumps({"error": f"Failed to scaffold pitchspec: {e}"}, indent=2)


def generate_pitch_handler(project_root: Path, args: dict[str, Any]) -> str:
    """Generate pitch materials."""
    from dazzle.pitch.extractor import extract_pitch_context
    from dazzle.pitch.loader import PitchSpecError, load_pitchspec

    fmt = args.get("format", "pptx")

    try:
        spec = load_pitchspec(project_root)
    except PitchSpecError as e:
        return json.dumps(
            {
                "error": str(e),
                "hint": "Run pitch(operation='scaffold') first to create pitchspec.yaml",
            },
            indent=2,
        )

    ctx = extract_pitch_context(project_root, spec)
    results: list[dict[str, Any]] = []
    all_warnings: list[str] = []

    formats = ["pptx", "narrative"] if fmt == "all" else [fmt]

    for f in formats:
        if f == "pptx":
            from dazzle.pitch.generators.pptx_gen import generate_pptx

            output_path = project_root / "pitch_deck.pptx"
            result = generate_pptx(ctx, output_path)
            if result.warnings:
                all_warnings.extend(result.warnings)
            results.append(
                {
                    "format": "pptx",
                    "success": result.success,
                    "output": str(result.output_path) if result.output_path else None,
                    "slides": result.slide_count,
                    "error": result.error,
                }
            )
        elif f == "narrative":
            from dazzle.pitch.generators.narrative import generate_narrative

            output_path = project_root / "pitch_narrative.md"
            result = generate_narrative(ctx, output_path)
            if result.warnings:
                all_warnings.extend(result.warnings)
            results.append(
                {
                    "format": "narrative",
                    "success": result.success,
                    "output": str(result.output_path) if result.output_path else None,
                    "files": result.files_created,
                    "error": result.error,
                }
            )

    missing = _get_missing_sections(spec)

    # Build context-aware next_steps
    next_steps: list[str] = []
    if all_warnings:
        next_steps.append(
            "Fix layout warnings by reducing content or moving detail to speaker_notes"
        )
    if missing:
        next_steps.append(f"Add {', '.join(missing)} to pitchspec.yaml for a stronger deck")
    if not all_warnings and not missing:
        next_steps.append("Deck is complete. Review pitch_narrative.md for speaker script")
    next_steps.append("Run pitch(operation='review') for content quality analysis")

    response: dict[str, Any] = {"results": results}
    if all_warnings:
        response["warnings"] = all_warnings
    if missing:
        response["missing_sections"] = missing
    response["next_steps"] = next_steps

    return json.dumps(response, indent=2)


def validate_pitchspec_handler(project_root: Path, args: dict[str, Any]) -> str:
    """Validate the pitchspec.yaml."""
    from dazzle.pitch.loader import PitchSpecError, load_pitchspec, validate_pitchspec

    try:
        spec = load_pitchspec(project_root)
    except PitchSpecError as e:
        return json.dumps({"error": str(e)}, indent=2)

    result = validate_pitchspec(spec)

    # Build context-aware next_steps
    next_steps: list[str] = []
    if result.errors:
        next_steps.append("Fix errors above, then re-run pitch(operation='validate')")
    elif result.warnings:
        next_steps.append(
            "Address warnings for a stronger deck, then pitch(operation='generate', format='all')"
        )
    else:
        next_steps.append(
            "Validation passed. Run pitch(operation='generate', format='all') to build the deck"
        )

    missing = _get_missing_sections(spec)
    if missing:
        next_steps.append(f"Add {', '.join(missing)} sections to pitchspec.yaml for completeness")

    return json.dumps(
        {
            "is_valid": result.is_valid,
            "error_count": len(result.errors),
            "warning_count": len(result.warnings),
            "errors": result.errors,
            "warnings": result.warnings,
            "missing_sections": missing,
            "next_steps": next_steps,
        },
        indent=2,
    )


def get_pitchspec_handler(project_root: Path, args: dict[str, Any]) -> str:
    """Get the current pitchspec."""
    from dazzle.pitch.loader import PitchSpecError, load_pitchspec, pitchspec_exists

    try:
        spec = load_pitchspec(project_root)
        data = spec.model_dump(mode="json", exclude_none=True)
        missing = _get_missing_sections(spec)
        completeness = _completeness_score(spec)

        next_steps: list[str] = []
        if missing:
            next_steps.append(f"Add content for: {', '.join(missing)}")
        next_steps.append("Run pitch(operation='validate') to check for issues")
        next_steps.append("Run pitch(operation='generate', format='all') to build the deck")

        return json.dumps(
            {
                "exists": pitchspec_exists(project_root),
                "spec": data,
                "completeness": f"{completeness}%",
                "missing_sections": missing,
                "next_steps": next_steps,
            },
            indent=2,
        )
    except PitchSpecError as e:
        return json.dumps(
            {
                "exists": pitchspec_exists(project_root),
                "error": str(e),
                "next_steps": ["Run pitch(operation='scaffold') to create pitchspec.yaml"],
            },
            indent=2,
        )


def review_pitchspec_handler(project_root: Path, args: dict[str, Any]) -> str:
    """Analyze pitch content quality and suggest improvements."""
    from dazzle.pitch.loader import PitchSpecError, load_pitchspec

    try:
        spec = load_pitchspec(project_root)
    except PitchSpecError as e:
        return json.dumps(
            {
                "error": str(e),
                "next_steps": ["Run pitch(operation='scaffold') to create pitchspec.yaml"],
            },
            indent=2,
        )

    section_scores: dict[str, str] = {}
    suggestions: list[str] = []

    # --- Company ---
    if spec.company.name == "My App":
        section_scores["company"] = "thin"
        suggestions.append("Company: Replace default name 'My App' with your actual company name")
    elif spec.company.tagline and spec.company.funding_ask:
        section_scores["company"] = "strong"
    elif spec.company.tagline or spec.company.funding_ask:
        section_scores["company"] = "adequate"
    else:
        section_scores["company"] = "thin"
        suggestions.append("Company: Add a tagline and funding_ask for investor context")

    # --- Problem ---
    if spec.problem is None:
        section_scores["problem"] = "missing"
        suggestions.append(
            "Problem: Add a problem section — this is the most important slide for investors"
        )
    elif len(spec.problem.points) < 3:
        section_scores["problem"] = "thin"
        suggestions.append(
            f"Problem: Has {len(spec.problem.points)} pain point(s); investors expect 3-5"
        )
    elif len(spec.problem.points) >= 3:
        section_scores["problem"] = "strong" if spec.problem.market_failure else "adequate"
        if not spec.problem.market_failure:
            suggestions.append(
                "Problem: Add market_failure points to show why existing solutions fail"
            )

    # --- Solution ---
    if spec.solution is None:
        section_scores["solution"] = "missing"
        suggestions.append("Solution: Add a solution section showing how you solve the problem")
    elif not spec.solution.how_it_works and not spec.solution.value_props:
        section_scores["solution"] = "thin"
        suggestions.append("Solution: Add how_it_works steps and value_props for clarity")
    elif spec.solution.how_it_works and spec.solution.value_props:
        section_scores["solution"] = "strong"
    else:
        section_scores["solution"] = "adequate"

    # --- Market ---
    if spec.market is None:
        section_scores["market"] = "missing"
        suggestions.append("Market: Add TAM/SAM/SOM market sizing — required for investor decks")
    else:
        has_sizes = sum(
            1 for s in [spec.market.tam, spec.market.sam, spec.market.som] if s is not None
        )
        if has_sizes == 3 and spec.market.drivers:
            section_scores["market"] = "strong"
        elif has_sizes >= 2:
            section_scores["market"] = "adequate"
            if not spec.market.drivers:
                suggestions.append("Market: Add 2-3 market drivers/trends to support sizing")
        else:
            section_scores["market"] = "thin"
            suggestions.append(
                f"Market: Only {has_sizes}/3 market sizes defined — add TAM, SAM, and SOM"
            )

    # --- Business Model ---
    if spec.business_model is None:
        section_scores["business_model"] = "missing"
        suggestions.append("Business Model: Add pricing tiers to show revenue strategy")
    elif len(spec.business_model.tiers) >= 2:
        section_scores["business_model"] = "strong"
    elif len(spec.business_model.tiers) == 1:
        section_scores["business_model"] = "adequate"
        suggestions.append(
            "Business Model: Consider adding 2-3 tiers (free/pro/enterprise pattern)"
        )
    else:
        section_scores["business_model"] = "thin"

    # --- Financials ---
    if spec.financials is None:
        section_scores["financials"] = "missing"
        suggestions.append("Financials: Add revenue projections and use_of_funds")
    else:
        has_projections = len(spec.financials.projections) >= 2
        has_funds = len(spec.financials.use_of_funds) >= 2
        if has_projections and has_funds:
            section_scores["financials"] = "strong"
        elif has_projections or has_funds:
            section_scores["financials"] = "adequate"
            if not has_projections:
                suggestions.append("Financials: Add 3-year revenue projections")
            if not has_funds:
                suggestions.append("Financials: Add use_of_funds breakdown")
        else:
            section_scores["financials"] = "thin"
            suggestions.append("Financials: Add projections and use_of_funds for credibility")

    # --- Team ---
    if spec.team is None:
        section_scores["team"] = "missing"
        suggestions.append("Team: Add founders with bios — investors invest in people")
    elif len(spec.team.founders) >= 2:
        section_scores["team"] = "strong" if any(f.bio for f in spec.team.founders) else "adequate"
        if not any(f.bio for f in spec.team.founders):
            suggestions.append("Team: Add bios to founders highlighting relevant experience")
    elif spec.team.founders:
        section_scores["team"] = "adequate"
    else:
        section_scores["team"] = "thin"
        suggestions.append("Team: Add founder details")

    # --- Milestones ---
    if spec.milestones is None:
        section_scores["milestones"] = "missing"
        suggestions.append(
            "Milestones: Add completed and next_12_months milestones to show traction"
        )
    elif spec.milestones.completed and spec.milestones.next_12_months:
        section_scores["milestones"] = "strong"
    elif spec.milestones.completed or spec.milestones.next_12_months:
        section_scores["milestones"] = "adequate"
    else:
        section_scores["milestones"] = "thin"

    # Overall assessment
    score_values = {"missing": 0, "thin": 1, "adequate": 2, "strong": 3}
    avg = (
        sum(score_values.get(s, 0) for s in section_scores.values()) / len(section_scores)
        if section_scores
        else 0
    )

    if avg >= 2.5:
        overall = "investor_ready"
    elif avg >= 1.5:
        overall = "needs_polish"
    elif avg >= 0.5:
        overall = "early_draft"
    else:
        overall = "skeleton"

    # Priority ordering: missing > thin > adequate improvements
    priority_order = {"missing": 0, "thin": 1, "adequate": 2, "strong": 3}
    iteration_checklist = sorted(
        [s for s, score in section_scores.items() if score != "strong"],
        key=lambda s: priority_order.get(section_scores[s], 3),
    )

    next_steps: list[str] = []
    if suggestions:
        next_steps.append("Address suggestions above, starting with missing sections")
    next_steps.append("Run pitch(operation='validate') to check for structural errors")
    next_steps.append("Run pitch(operation='generate', format='all') to build the deck")

    return json.dumps(
        {
            "overall_assessment": overall,
            "section_scores": section_scores,
            "completeness": f"{_completeness_score(spec)}%",
            "suggestions": suggestions,
            "iteration_checklist": iteration_checklist,
            "next_steps": next_steps,
        },
        indent=2,
    )
