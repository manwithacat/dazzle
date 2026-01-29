"""
MCP handler for pitch operations.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


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
                },
                indent=2,
            )
        else:
            return json.dumps(
                {
                    "success": False,
                    "message": "pitchspec.yaml already exists. Use overwrite=true to replace.",
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

    formats = ["pptx", "narrative"] if fmt == "all" else [fmt]

    for f in formats:
        if f == "pptx":
            from dazzle.pitch.generators.pptx_gen import generate_pptx

            output_path = project_root / "pitch_deck.pptx"
            result = generate_pptx(ctx, output_path)
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
            results.append(
                {
                    "format": "narrative",
                    "success": result.success,
                    "output": str(result.output_path) if result.output_path else None,
                    "files": result.files_created,
                    "error": result.error,
                }
            )

    return json.dumps({"results": results}, indent=2)


def validate_pitchspec_handler(project_root: Path, args: dict[str, Any]) -> str:
    """Validate the pitchspec.yaml."""
    from dazzle.pitch.loader import PitchSpecError, load_pitchspec, validate_pitchspec

    try:
        spec = load_pitchspec(project_root)
    except PitchSpecError as e:
        return json.dumps({"error": str(e)}, indent=2)

    result = validate_pitchspec(spec)

    return json.dumps(
        {
            "is_valid": result.is_valid,
            "error_count": len(result.errors),
            "warning_count": len(result.warnings),
            "errors": result.errors,
            "warnings": result.warnings,
        },
        indent=2,
    )


def get_pitchspec_handler(project_root: Path, args: dict[str, Any]) -> str:
    """Get the current pitchspec."""
    from dazzle.pitch.loader import PitchSpecError, load_pitchspec, pitchspec_exists

    try:
        spec = load_pitchspec(project_root)
        data = spec.model_dump(mode="json", exclude_none=True)
        return json.dumps(
            {
                "exists": pitchspec_exists(project_root),
                "spec": data,
            },
            indent=2,
        )
    except PitchSpecError as e:
        return json.dumps(
            {
                "exists": pitchspec_exists(project_root),
                "error": str(e),
            },
            indent=2,
        )
