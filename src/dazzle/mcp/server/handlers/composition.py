"""Composition analysis MCP handler.

Provides visual hierarchy auditing via the ``composition`` MCP tool.

Operations:
- ``audit`` — deterministic sitespec-based composition analysis
- ``capture`` — Playwright section-level screenshot pipeline
- ``analyze`` — LLM visual evaluation of captured screenshots
- ``report`` — combined audit + capture + analyze with merged scoring
- ``bootstrap`` — generate synthetic reference library for few-shot visual evaluation
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def audit_composition_handler(project_path: Path, args: dict[str, Any]) -> str:
    """Run deterministic composition audit from sitespec structure.

    Derives section elements from SiteSpec, computes attention weights,
    and evaluates composition rules.  Returns scored JSON report.
    """
    from dazzle.core.composition import run_composition_audit
    from dazzle.core.sitespec_loader import load_sitespec_with_copy

    routes_filter: list[str] | None = args.get("pages")

    try:
        sitespec = load_sitespec_with_copy(project_path, use_defaults=True)

        if not sitespec.pages:
            return json.dumps(
                {
                    "pages": [],
                    "overall_score": 100,
                    "summary": "No pages defined in sitespec",
                    "markdown": "# Composition Audit\n\nNo pages to audit.",
                }
            )

        result = run_composition_audit(sitespec, routes_filter=routes_filter)
        return json.dumps(result, indent=2)
    except Exception as e:
        logger.exception("Composition audit failed")
        return json.dumps({"error": str(e)})


async def capture_composition_handler(project_path: Path, args: dict[str, Any]) -> str:
    """Capture section-level screenshots from a running Dazzle app.

    Requires a ``base_url`` pointing to the running app.  Uses Playwright
    to navigate pages, locate ``.dz-section-{type}`` elements, and take
    clipped screenshots of each section.
    """
    from dataclasses import asdict

    from dazzle.core.composition_capture import capture_page_sections
    from dazzle.core.sitespec_loader import load_sitespec_with_copy

    base_url: str | None = args.get("base_url")
    if not base_url:
        return json.dumps(
            {"error": "base_url is required for capture (e.g. http://localhost:3000)"}
        )

    routes_filter: list[str] | None = args.get("pages")
    viewports: list[str] | None = args.get("viewports")
    output_dir = project_path / ".dazzle" / "composition" / "captures"

    try:
        sitespec = load_sitespec_with_copy(project_path, use_defaults=True)

        if not sitespec.pages:
            return json.dumps({"captures": [], "summary": "No pages to capture"})

        captures = await capture_page_sections(
            base_url,
            sitespec,
            output_dir=output_dir,
            viewports=viewports,
            routes_filter=routes_filter,
        )

        captures_data = [asdict(c) for c in captures]
        total_sections = sum(len(c.sections) for c in captures)
        total_tokens = sum(c.total_tokens_est for c in captures)

        return json.dumps(
            {
                "captures": captures_data,
                "total_sections": total_sections,
                "total_tokens_est": total_tokens,
                "output_dir": str(output_dir),
                "summary": (
                    f"Captured {total_sections} sections across "
                    f"{len(captures)} page/viewport combinations "
                    f"(~{total_tokens:,} tokens)"
                ),
            },
            indent=2,
        )
    except ImportError as e:
        return json.dumps({"error": str(e)})
    except Exception as e:
        logger.exception("Composition capture failed")
        return json.dumps({"error": str(e)})


def analyze_composition_handler(project_path: Path, args: dict[str, Any]) -> str:
    """Run LLM visual evaluation on previously captured screenshots.

    Loads captures from ``.dazzle/composition/captures/``, applies
    dimension-specific preprocessing, and submits to Claude's vision API.
    Requires ``ANTHROPIC_API_KEY`` environment variable or a running
    capture to evaluate.
    """
    from dazzle.core.composition_visual import (
        DIMENSIONS,
        build_visual_report,
        evaluate_captures,
    )

    focus: list[str] | None = args.get("focus")
    token_budget: int = args.get("token_budget", 50_000)
    captures_dir = project_path / ".dazzle" / "composition" / "captures"

    if not captures_dir.exists():
        return json.dumps(
            {
                "error": (
                    "No captures found. Run composition(operation='capture') first "
                    "to take screenshots."
                )
            }
        )

    # Reconstruct captures from saved files
    captures = _load_captures_from_dir(captures_dir)
    if not captures:
        return json.dumps({"error": "No capture files found in " + str(captures_dir)})

    # Filter dimensions if focus specified
    dimensions: list[str] | None = None
    if focus:
        dimensions = [d for d in DIMENSIONS if d in focus]
        if not dimensions:
            return json.dumps(
                {"error": f"No valid dimensions in focus: {focus}. Valid: {DIMENSIONS}"}
            )

    try:
        results = evaluate_captures(
            captures,
            dimensions=dimensions,
            token_budget=token_budget,
        )
        report = build_visual_report(results)
        return json.dumps(report, indent=2)
    except ImportError as e:
        return json.dumps({"error": str(e)})
    except Exception as e:
        logger.exception("Visual evaluation failed")
        return json.dumps({"error": str(e)})


def _load_captures_from_dir(captures_dir: Path) -> list[Any]:
    """Reconstruct CapturedPage objects from screenshot files on disk.

    Groups files by route-viewport and builds CapturedPage/CapturedSection
    objects from the naming convention: ``{slug}-{viewport}-{section}.png``.
    """
    from dazzle.core.composition_capture import CapturedPage, CapturedSection

    # Group PNG files by route-viewport prefix
    png_files = sorted(captures_dir.glob("*.png"))
    if not png_files:
        return []

    # Parse filenames: {slug}-{viewport}-{section_type}.png
    # or {slug}-{viewport}-full.png for full-page captures
    page_map: dict[tuple[str, str], CapturedPage] = {}

    for f in png_files:
        stem = f.stem
        # Skip preprocessed variants
        if stem.endswith(("-opt", "-blur", "-edges", "-mono", "-quant")):
            continue

        parts = stem.rsplit("-", 2)
        if len(parts) < 3:
            continue

        slug, viewport, section_type = parts[0], parts[1], parts[2]
        route = "/" if slug == "index" else f"/{slug.replace('-', '/')}"
        key = (route, viewport)

        if key not in page_map:
            page_map[key] = CapturedPage(route=route, viewport=viewport)

        if section_type == "full":
            page_map[key].full_page = str(f)
        else:
            try:
                from PIL import Image

                with Image.open(f) as img:
                    w, h = img.size
            except (ImportError, Exception):
                w, h = 1280, 400  # fallback

            from dazzle.core.composition_capture import estimate_tokens

            tokens = estimate_tokens(w, h)
            page_map[key].sections.append(
                CapturedSection(
                    section_type=section_type,
                    path=str(f),
                    width=w,
                    height=h,
                    tokens_est=tokens,
                )
            )
            page_map[key].total_tokens_est += tokens

    return list(page_map.values())


async def report_composition_handler(project_path: Path, args: dict[str, Any]) -> str:
    """Run combined composition report: audit + optional capture + analyze.

    Always runs the deterministic DOM audit.  When ``base_url`` is provided,
    also runs Playwright capture and LLM visual evaluation, then merges both
    scores into a combined report.
    """
    from dazzle.core.composition import run_composition_audit
    from dazzle.core.sitespec_loader import load_sitespec_with_copy

    base_url: str | None = args.get("base_url")
    routes_filter: list[str] | None = args.get("pages")
    viewports: list[str] | None = args.get("viewports")
    focus: list[str] | None = args.get("focus")
    token_budget: int = args.get("token_budget", 50_000)

    # Step 1: DOM audit (always runs)
    try:
        sitespec = load_sitespec_with_copy(project_path, use_defaults=True)
    except Exception as e:
        logger.exception("Failed to load sitespec")
        return json.dumps({"error": f"Failed to load sitespec: {e}"})

    if not sitespec.pages:
        return json.dumps(
            {
                "dom_score": 100,
                "visual_score": None,
                "combined_score": 100,
                "summary": "No pages defined in sitespec",
                "markdown": "# Composition Report\n\nNo pages to evaluate.",
            }
        )

    try:
        dom_result = run_composition_audit(sitespec, routes_filter=routes_filter)
    except Exception as e:
        logger.exception("DOM audit failed in report")
        return json.dumps({"error": f"DOM audit failed: {e}"})

    dom_score = dom_result.get("overall_score", 100)

    # Step 2: Visual evaluation (only when base_url provided)
    visual_report: dict[str, Any] | None = None
    visual_score: int | None = None

    if base_url:
        try:
            visual_report = await _run_visual_pipeline(
                project_path=project_path,
                base_url=base_url,
                sitespec=sitespec,
                routes_filter=routes_filter,
                viewports=viewports,
                focus=focus,
                token_budget=token_budget,
            )
            visual_score = visual_report.get("visual_score")
        except Exception as e:
            logger.warning("Visual pipeline failed, report will use DOM-only: %s", e)
            visual_report = {"error": str(e)}

    # Step 3: Combine scores
    if visual_score is not None:
        # Weighted average: DOM 40%, Visual 60% (visual catches rendering bugs)
        combined_score = int(dom_score * 0.4 + visual_score * 0.6)
    else:
        combined_score = dom_score

    # Build severity counts across both layers
    dom_violations: dict[str, int] = {}
    for page in dom_result.get("pages", []):
        for sev, count in page.get("violations_count", {}).items():
            dom_violations[sev] = dom_violations.get(sev, 0) + count

    visual_findings = visual_report.get("findings_by_severity", {}) if visual_report else {}

    total_findings = {
        "high": dom_violations.get("high", 0) + visual_findings.get("high", 0),
        "medium": dom_violations.get("medium", 0) + visual_findings.get("medium", 0),
        "low": dom_violations.get("low", 0) + visual_findings.get("low", 0),
    }

    # Build summary
    visual_part = (
        f", visual {visual_score}/100"
        if visual_score is not None
        else " (visual: not run — provide base_url)"
    )
    summary = (
        f"DOM {dom_score}/100{visual_part}, "
        f"combined {combined_score}/100. "
        f"Findings: {total_findings['high']} high, "
        f"{total_findings['medium']} medium, {total_findings['low']} low"
    )

    # Build markdown
    markdown = _build_combined_markdown(
        dom_result, visual_report, dom_score, visual_score, combined_score
    )

    report = {
        "dom_score": dom_score,
        "visual_score": visual_score,
        "combined_score": combined_score,
        "findings_by_severity": total_findings,
        "dom_report": dom_result,
        "visual_report": visual_report,
        "tokens_used": visual_report.get("tokens_used", 0) if visual_report else 0,
        "summary": summary,
        "markdown": markdown,
    }

    return json.dumps(report, indent=2)


async def _run_visual_pipeline(
    *,
    project_path: Path,
    base_url: str,
    sitespec: Any,
    routes_filter: list[str] | None,
    viewports: list[str] | None,
    focus: list[str] | None,
    token_budget: int,
) -> dict[str, Any]:
    """Run capture + analyze + geometry audit pipeline.

    Returns the visual report dict with geometry findings merged in.
    """
    from dazzle.core.composition import run_geometry_audit
    from dazzle.core.composition_capture import capture_page_sections
    from dazzle.core.composition_visual import (
        DIMENSIONS,
        build_visual_report,
        evaluate_captures,
    )

    output_dir = project_path / ".dazzle" / "composition" / "captures"

    # Capture
    captures = await capture_page_sections(
        base_url,
        sitespec,
        output_dir=output_dir,
        viewports=viewports,
        routes_filter=routes_filter,
    )

    if not captures:
        return {
            "visual_score": 100,
            "findings_by_severity": {"high": 0, "medium": 0, "low": 0},
            "tokens_used": 0,
            "pages": [],
            "geometry": {
                "violations": [],
                "violations_count": {"high": 0, "medium": 0, "low": 0},
                "geometry_score": 100,
            },
            "summary": "No sections captured",
            "markdown": "",
        }

    # Geometry audit (zero-cost — no LLM tokens)
    geometry_result = run_geometry_audit(captures, sitespec)

    # LLM visual analysis
    dimensions: list[str] | None = None
    if focus:
        dimensions = [d for d in DIMENSIONS if d in focus]

    results = evaluate_captures(
        captures,
        dimensions=dimensions,
        token_budget=token_budget,
    )

    report = build_visual_report(results)
    report["geometry"] = geometry_result

    # Merge geometry severity counts into visual findings
    for sev in ("high", "medium", "low"):
        report.setdefault("findings_by_severity", {})[sev] = report.get(
            "findings_by_severity", {}
        ).get(sev, 0) + geometry_result["violations_count"].get(sev, 0)

    return report


def _build_combined_markdown(
    dom_result: dict[str, Any],
    visual_report: dict[str, Any] | None,
    dom_score: int,
    visual_score: int | None,
    combined_score: int,
) -> str:
    """Build combined markdown report."""
    lines = [
        "# Composition Report",
        "",
        f"**Combined Score: {combined_score}/100**",
        "",
    ]

    # DOM section
    lines.append(f"## DOM Audit: {dom_score}/100")
    lines.append("")
    dom_md = dom_result.get("markdown", "")
    if dom_md:
        # Strip the top-level heading from DOM markdown (we have our own)
        for line in dom_md.split("\n"):
            if line.startswith("# "):
                continue
            lines.append(line)
    lines.append("")

    # Visual section
    if visual_score is not None and visual_report:
        lines.append(f"## Visual Evaluation: {visual_score}/100")
        lines.append("")
        visual_md = visual_report.get("markdown", "")
        if visual_md:
            for line in visual_md.split("\n"):
                if line.startswith("# "):
                    continue
                lines.append(line)
    elif visual_report and "error" in visual_report:
        lines.append("## Visual Evaluation: Skipped")
        lines.append("")
        lines.append(f"Error: {visual_report['error']}")
    else:
        lines.append("## Visual Evaluation: Not Run")
        lines.append("")
        lines.append("Provide `base_url` to enable visual evaluation.")

    lines.append("")
    return "\n".join(lines)


def bootstrap_composition_handler(project_path: Path, args: dict[str, Any]) -> str:
    """Generate the synthetic reference library for few-shot visual evaluation.

    Creates annotated section screenshots using PIL and stores them in
    ``.dazzle/composition/references/`` with per-section manifest.json files.
    """
    from dazzle.core.composition_references import estimate_reference_tokens, load_references
    from dazzle.core.composition_references_bootstrap import bootstrap_references

    overwrite = args.get("overwrite", False)
    ref_dir = project_path / ".dazzle" / "composition" / "references"

    # Check if references already exist
    if ref_dir.exists() and not overwrite:
        existing = load_references(ref_dir)
        if existing:
            total = sum(len(refs) for refs in existing.values())
            tokens = estimate_reference_tokens(existing)
            return json.dumps(
                {
                    "status": "exists",
                    "section_types": list(existing.keys()),
                    "total_references": total,
                    "estimated_tokens": tokens,
                    "summary": (
                        f"Reference library already exists with {total} images "
                        f"across {len(existing)} section types (~{tokens:,} tokens). "
                        "Use overwrite=true to regenerate."
                    ),
                }
            )

    try:
        by_section = bootstrap_references(ref_dir)
    except ImportError as e:
        return json.dumps({"error": f"Pillow required for bootstrap: {e}"})
    except Exception as e:
        logger.exception("Reference bootstrap failed")
        return json.dumps({"error": str(e)})

    total = sum(len(refs) for refs in by_section.values())
    good = sum(1 for refs in by_section.values() for r in refs if r.label == "good")
    bad = total - good

    # Estimate token cost
    loaded = load_references(ref_dir)
    tokens = estimate_reference_tokens(loaded)

    return json.dumps(
        {
            "status": "created",
            "section_types": list(by_section.keys()),
            "total_references": total,
            "good": good,
            "bad": bad,
            "estimated_tokens": tokens,
            "output_dir": str(ref_dir),
            "summary": (
                f"Bootstrapped {total} reference images ({good} good, {bad} bad) "
                f"across {len(by_section)} section types (~{tokens:,} tokens). "
                f"Stored in {ref_dir}"
            ),
        },
        indent=2,
    )
