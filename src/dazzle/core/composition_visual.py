"""Composition visual evaluation — LLM-powered screenshot analysis.

Uses Claude's vision API to evaluate captured section screenshots
across 6 evaluation dimensions: content rendering, icon/media rendering,
color consistency, layout overflow, visual hierarchy, and responsive fidelity.

Each dimension uses dimension-specific image preprocessing and structured
prompts to extract actionable findings.
"""

from __future__ import annotations

import base64
import logging
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .composition_capture import CapturedPage, CapturedSection

logger = logging.getLogger(__name__)

# ── Data Models ──────────────────────────────────────────────────────


@dataclass
class VisualFinding:
    """A single finding from visual evaluation."""

    section: str
    dimension: str
    category: str
    severity: str  # high, medium, low
    finding: str
    evidence: str
    remediation: str


@dataclass
class PageVisualResult:
    """Visual evaluation results for a single page."""

    route: str
    viewport: str
    findings: list[VisualFinding] = field(default_factory=list)
    visual_score: int = 100
    tokens_used: int = 0
    dimensions_evaluated: list[str] = field(default_factory=list)
    dimensions_skipped: list[dict[str, str]] = field(default_factory=list)


# ── Evaluation Dimensions ────────────────────────────────────────────

DIMENSIONS = [
    "content_rendering",
    "icon_media",
    "color_consistency",
    "layout_overflow",
    "visual_hierarchy",
    "responsive_fidelity",
]

# Map dimensions to the preprocessing filter they need
DIMENSION_PREPROCESSING: dict[str, str | None] = {
    "content_rendering": "monochrome",
    "icon_media": None,  # standard (full color)
    "color_consistency": "quantize",
    "layout_overflow": "edge",
    "visual_hierarchy": "blur",
    "responsive_fidelity": None,  # standard
}

# Dimensions that only apply to mobile viewport
MOBILE_ONLY_DIMENSIONS = {"responsive_fidelity"}

# Default token budget per page
DEFAULT_PAGE_TOKEN_BUDGET = 10_000


# ── Image Preprocessing Filters ─────────────────────────────────────


def apply_filter(img_path: Path, filter_name: str | None) -> Path:
    """Apply a preprocessing filter to an image.

    Args:
        img_path: Path to source image.
        filter_name: Filter to apply (None = no filter).

    Returns:
        Path to filtered image (or original if no filter / PIL unavailable).
    """
    if filter_name is None:
        return img_path

    try:
        from PIL import Image, ImageFilter
    except ImportError:
        logger.warning("Pillow not available — skipping filter %s", filter_name)
        return img_path

    img = Image.open(img_path)

    if filter_name == "blur":
        filtered = img.filter(ImageFilter.GaussianBlur(radius=8))
        out = img_path.with_stem(img_path.stem + "-blur")
        filtered.save(out)
        return out

    elif filter_name == "edge":
        gray = img.convert("L")
        edges = gray.filter(ImageFilter.FIND_EDGES)
        out = img_path.with_stem(img_path.stem + "-edges")
        edges.save(out)
        return out

    elif filter_name == "monochrome":
        gray = img.convert("L")
        mono = gray.point(lambda p: 255 if p > 128 else 0)
        out = img_path.with_stem(img_path.stem + "-mono")
        mono.save(out)
        return out

    elif filter_name == "quantize":
        rgb = img.convert("RGB")
        quantized = rgb.quantize(colors=8, method=Image.Quantize.MEDIANCUT)
        out = img_path.with_stem(img_path.stem + "-quant")
        quantized.convert("RGB").save(out)
        return out

    else:
        logger.warning("Unknown filter: %s", filter_name)
        return img_path


def image_to_base64(img_path: Path) -> str:
    """Read an image file and return its base64-encoded content."""
    return base64.b64encode(img_path.read_bytes()).decode("utf-8")


# ── Prompt Builders ──────────────────────────────────────────────────

SYSTEM_PROMPT = (
    "You are a design quality evaluator for Dazzle-generated web applications. "
    "Evaluate screenshots against specific quality dimensions. "
    "Return ONLY valid JSON — no prose, no markdown fences. "
    "Each finding must include: section, category, severity (high/medium/low), "
    "finding (what's wrong), evidence (what you see), remediation (how to fix)."
)


def _build_content_rendering_prompt(section_type: str, spec_context: dict[str, Any]) -> str:
    headline = spec_context.get("headline", "")
    item_count = spec_context.get("item_count", 0)
    media_type = spec_context.get("media_type", "image")

    parts = [
        f"Examine this {section_type} section screenshot (monochrome-filtered).",
        "The sitespec declares this section should contain:",
    ]
    if headline:
        parts.append(f'- Headline: "{headline}"')
    if item_count:
        parts.append(f"- {item_count} items with titles and descriptions")
    if media_type != "none":
        parts.append(f"- {media_type} media")

    parts.append(
        "\nReport any MISSING content as findings. "
        "Empty white blocks in monochrome indicate missing content. "
        'Return JSON: {"findings": [{"section": "...", "category": "content_rendering", '
        '"severity": "high|medium|low", "finding": "...", "evidence": "...", '
        '"remediation": "..."}]}'
    )
    return "\n".join(parts)


def _build_icon_media_prompt(section_type: str, spec_context: dict[str, Any]) -> str:
    icon_count = spec_context.get("icon_count", 0)
    icon_type = spec_context.get("icon_type", "Lucide")

    return (
        f"This is a {section_type} section that should contain "
        f"{icon_count or 'several'} {icon_type} icons.\n"
        "Count the number of visible, rendered icons. Report any that appear as:\n"
        "- Blank squares or circles (placeholder)\n"
        "- Missing entirely (text without icon above)\n"
        "- Rendering as text fallback instead of graphical icon\n\n"
        'Return JSON: {"findings": [{"section": "...", "category": "icon_media", '
        '"severity": "high|medium|low", "finding": "...", "evidence": "...", '
        '"remediation": "..."}]}'
    )


def _build_color_consistency_prompt(section_type: str, spec_context: dict[str, Any]) -> str:
    brand_hue = spec_context.get("brand_hue", "")
    brand_desc = spec_context.get("brand_description", "brand color")

    return (
        f"This {section_type} section has been color-quantized to 8 dominant colors.\n"
        f"The brand palette uses: {brand_desc}"
        + (f" (hue ~{brand_hue})" if brand_hue else "")
        + ".\n\n"
        "Check CTA buttons, links, and accent elements:\n"
        "- Do they use the brand color, or do they appear as plain black (#000)?\n"
        "- Are all same-role elements (e.g. all buttons) the same color?\n"
        "- Is there any unexpected color not in the brand palette?\n\n"
        'Return JSON: {"findings": [{"section": "...", "category": "color_consistency", '
        '"severity": "high|medium|low", "finding": "...", "evidence": "...", '
        '"remediation": "..."}]}'
    )


def _build_layout_overflow_prompt(section_type: str, spec_context: dict[str, Any]) -> str:
    columns = spec_context.get("columns", 0)
    item_count = spec_context.get("item_count", 0)
    item_type = spec_context.get("item_type", "items")

    return (
        f"This {section_type} section uses edge detection to reveal layout structure.\n"
        + (
            f"Expected layout: {columns}-column grid for {item_count} {item_type}.\n"
            if columns
            else ""
        )
        + "Check:\n"
        "1. Do all items fit within the grid without unexpected wrapping?\n"
        "2. If items wrap, is the last row balanced (not a single orphan)?\n"
        "3. Are all items the same width/height?\n"
        "4. Is there any horizontal overflow or clipping?\n\n"
        'Return JSON: {"findings": [{"section": "...", "category": "layout_overflow", '
        '"severity": "high|medium|low", "finding": "...", "evidence": "...", '
        '"remediation": "..."}]}'
    )


def _build_visual_hierarchy_prompt(section_type: str, spec_context: dict[str, Any]) -> str:
    weights = spec_context.get("weights", {})
    weight_lines = [f"  {role}: {w}" for role, w in sorted(weights.items(), key=lambda x: -x[1])]
    weight_table = "\n".join(weight_lines) if weight_lines else "  (no weight data)"

    return (
        f"This {section_type} section has been Gaussian-blurred to reveal visual weight.\n"
        f"DOM audit computed these attention weights:\n{weight_table}\n\n"
        "The largest/most prominent visual area should correspond to the highest weight.\n"
        "Flag any elements that appear more or less prominent than their computed weight suggests.\n\n"
        'Return JSON: {"findings": [{"section": "...", "category": "visual_hierarchy", '
        '"severity": "high|medium|low", "finding": "...", "evidence": "...", '
        '"remediation": "..."}]}'
    )


def _build_responsive_fidelity_prompt(section_type: str, spec_context: dict[str, Any]) -> str:
    return (
        f"This is the {section_type} section at mobile viewport (375px wide).\n"
        "Check for:\n"
        "1. Text not clipped or overflowing container\n"
        "2. Elements properly stacked (not side-by-side at this width)\n"
        "3. Touch targets (buttons) at least 44px tall\n"
        "4. No horizontal scroll required\n"
        "5. Images properly scaled to mobile width\n\n"
        'Return JSON: {"findings": [{"section": "...", "category": "responsive_fidelity", '
        '"severity": "high|medium|low", "finding": "...", "evidence": "...", '
        '"remediation": "..."}]}'
    )


DIMENSION_PROMPT_BUILDERS: dict[str, Any] = {
    "content_rendering": _build_content_rendering_prompt,
    "icon_media": _build_icon_media_prompt,
    "color_consistency": _build_color_consistency_prompt,
    "layout_overflow": _build_layout_overflow_prompt,
    "visual_hierarchy": _build_visual_hierarchy_prompt,
    "responsive_fidelity": _build_responsive_fidelity_prompt,
}


# ── LLM Evaluation ──────────────────────────────────────────────────


def _call_vision_api(
    images: list[tuple[str, str]],
    prompt: str,
    *,
    api_key: str | None = None,
    model: str = "claude-sonnet-4-5-20250929",
    max_tokens: int = 2000,
) -> tuple[str, int]:
    """Call Claude's vision API with one or more images.

    Args:
        images: List of (base64_data, media_type) tuples.
        prompt: The evaluation prompt.
        api_key: Anthropic API key (reads ANTHROPIC_API_KEY if None).
        model: Model to use.
        max_tokens: Maximum output tokens.

    Returns:
        Tuple of (response_text, total_tokens_used).
    """
    try:
        import anthropic
    except ImportError:
        raise ImportError(
            "anthropic package required for visual evaluation. Install with: pip install anthropic"
        )

    if api_key:
        client = anthropic.Anthropic(api_key=api_key)
    else:
        client = anthropic.Anthropic()

    # Build multi-modal content
    content: list[dict[str, Any]] = []
    for img_b64, media_type in images:
        content.append(
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": media_type,
                    "data": img_b64,
                },
            }
        )
    content.append({"type": "text", "text": prompt})

    response = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        temperature=0.0,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": content}],  # type: ignore[typeddict-item]
    )

    text = response.content[0].text if hasattr(response.content[0], "text") else ""
    tokens = 0
    if hasattr(response, "usage"):
        tokens = (response.usage.input_tokens or 0) + (response.usage.output_tokens or 0)

    return text, tokens


def _parse_findings(response_text: str, section_type: str, dimension: str) -> list[VisualFinding]:
    """Parse LLM response into VisualFinding objects."""
    import json

    # Strip markdown fences if present
    text = response_text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:])
        if text.endswith("```"):
            text = text[:-3].strip()

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        logger.warning(
            "Failed to parse visual eval response as JSON for %s/%s",
            section_type,
            dimension,
        )
        return []

    findings_data = data.get("findings", [])
    results: list[VisualFinding] = []
    for f in findings_data:
        results.append(
            VisualFinding(
                section=f.get("section", section_type),
                dimension=dimension,
                category=f.get("category", dimension),
                severity=f.get("severity", "medium"),
                finding=f.get("finding", ""),
                evidence=f.get("evidence", ""),
                remediation=f.get("remediation", ""),
            )
        )
    return results


# ── Main Evaluation Entry Point ──────────────────────────────────────


def evaluate_captures(
    captures: list[CapturedPage],
    *,
    dimensions: list[str] | None = None,
    spec_context: dict[str, Any] | None = None,
    references: dict[str, list[Any]] | None = None,
    api_key: str | None = None,
    model: str = "claude-sonnet-4-5-20250929",
    token_budget: int = 50_000,
) -> list[PageVisualResult]:
    """Evaluate captured screenshots using LLM vision analysis.

    Iterates over captured pages and their sections, applying
    dimension-specific preprocessing and evaluation prompts.

    Args:
        captures: List of CapturedPage from the capture pipeline.
        dimensions: Which evaluation dimensions to run (default: all).
        spec_context: Per-section spec context for prompt building.
            Keys are section_type strings, values are dicts with fields
            like headline, item_count, icon_count, brand_hue, weights, etc.
        references: Loaded reference library from composition_references.
            Maps section_type -> list of ReferenceImage with base64 loaded.
            When provided, includes few-shot examples in evaluation prompts.
        api_key: Anthropic API key (reads env if None).
        model: Model to use for evaluation.
        token_budget: Maximum total tokens across all evaluations.

    Returns:
        List of PageVisualResult with findings and scores.
    """
    dims = dimensions or [d for d in DIMENSIONS if d not in MOBILE_ONLY_DIMENSIONS]
    ctx = spec_context or {}
    refs = references or {}
    total_tokens_used = 0
    results: list[PageVisualResult] = []

    for capture in captures:
        page_result = PageVisualResult(
            route=capture.route,
            viewport=capture.viewport,
        )

        for section in capture.sections:
            sec_ctx = ctx.get(section.section_type, {})
            sec_refs = refs.get(section.section_type, [])

            for dim in dims:
                # Skip responsive_fidelity unless mobile viewport
                if dim in MOBILE_ONLY_DIMENSIONS and capture.viewport != "mobile":
                    continue

                # Check token budget
                if total_tokens_used >= token_budget:
                    logger.info(
                        "Token budget exhausted (%d/%d), stopping evaluation",
                        total_tokens_used,
                        token_budget,
                    )
                    break

                dim_label = f"{section.section_type}:{dim}"
                findings, tokens = _evaluate_section_dimension(
                    section=section,
                    dimension=dim,
                    spec_context=sec_ctx,
                    references=sec_refs,
                    api_key=api_key,
                    model=model,
                )

                if tokens > 0:
                    page_result.findings.extend(findings)
                    page_result.dimensions_evaluated.append(dim_label)
                    total_tokens_used += tokens
                    page_result.tokens_used += tokens
                else:
                    page_result.dimensions_skipped.append(
                        {"dimension": dim_label, "reason": "evaluation_failed"}
                    )

        # Score: deduct points per finding by severity
        page_result.visual_score = _score_findings(page_result.findings)
        results.append(page_result)

    return results


def _evaluate_section_dimension(
    *,
    section: CapturedSection,
    dimension: str,
    spec_context: dict[str, Any],
    references: list[Any] | None = None,
    api_key: str | None,
    model: str,
) -> tuple[list[VisualFinding], int]:
    """Evaluate a single section for a single dimension.

    Args:
        section: The captured section to evaluate.
        dimension: Evaluation dimension name.
        spec_context: Spec-derived context for prompt building.
        references: Optional list of ReferenceImage objects (with base64 loaded)
            relevant to this section type.  When provided, matching references
            are included as few-shot examples in the vision API call.
        api_key: Anthropic API key.
        model: Model to use.

    Returns:
        Tuple of (findings, tokens_used).
    """
    img_path = Path(section.path)
    if not img_path.exists():
        logger.warning("Screenshot not found: %s — skipping evaluation", img_path)
        return [], 0

    # Apply dimension-specific preprocessing
    filter_name = DIMENSION_PREPROCESSING.get(dimension)
    processed_path = apply_filter(img_path, filter_name)

    # Build prompt
    prompt_builder = DIMENSION_PROMPT_BUILDERS.get(dimension)
    if not prompt_builder:
        logger.warning("No prompt builder for dimension: %s — skipping", dimension)
        return [], 0

    prompt = prompt_builder(section.section_type, spec_context)

    # Build image list: reference images first (few-shot), then the target
    images: list[tuple[str, str]] = []

    # Add relevant reference images as few-shot examples
    ref_labels: list[str] = []
    if references:
        for ref in references:
            if dimension in getattr(ref, "dimensions", []):
                try:
                    images.append((ref.base64, "image/png"))
                    ref_labels.append(f"{ref.label}: {ref.description}")
                except (ValueError, AttributeError):
                    continue

    # Add the target image last
    img_b64 = image_to_base64(processed_path)
    images.append((img_b64, "image/png"))

    # Augment prompt with reference context if we have any
    if ref_labels:
        ref_intro = (
            "The first image(s) are reference examples showing good and bad patterns. "
            "The LAST image is the one to evaluate.\n\n"
            "References:\n"
        )
        for i, label in enumerate(ref_labels, 1):
            ref_intro += f"  Image {i}: {label}\n"
        ref_intro += f"\nNow evaluate Image {len(images)} (the target):\n\n"
        prompt = ref_intro + prompt

    try:
        response_text, tokens = _call_vision_api(
            images=images,
            prompt=prompt,
            api_key=api_key,
            model=model,
        )
        findings = _parse_findings(response_text, section.section_type, dimension)
        return findings, tokens
    except Exception as e:
        logger.error(
            "Visual evaluation failed for %s/%s: %s: %s",
            section.section_type,
            dimension,
            type(e).__name__,
            e,
        )
        return [], 0


def _score_findings(findings: list[VisualFinding]) -> int:
    """Score page from 0-100 based on findings severity."""
    deductions = {"high": 20, "medium": 8, "low": 3}
    total_deduction = sum(deductions.get(f.severity, 5) for f in findings)
    return max(0, 100 - total_deduction)


def build_visual_report(results: list[PageVisualResult]) -> dict[str, Any]:
    """Build a summary report from visual evaluation results.

    Returns:
        Dict with pages, overall visual_score, findings_by_severity,
        total tokens_used, summary, and markdown report.
    """
    pages_data = []
    all_findings: list[VisualFinding] = []
    total_tokens = 0
    total_skipped = 0

    for page in results:
        all_findings.extend(page.findings)
        total_tokens += page.tokens_used
        total_skipped += len(page.dimensions_skipped)
        page_dict: dict[str, Any] = {
            "route": page.route,
            "viewport": page.viewport,
            "visual_score": page.visual_score,
            "findings": [asdict(f) for f in page.findings],
            "tokens_used": page.tokens_used,
            "dimensions_evaluated": page.dimensions_evaluated,
        }
        if page.dimensions_skipped:
            page_dict["dimensions_skipped"] = page.dimensions_skipped
        pages_data.append(page_dict)

    # Overall score: average of page scores (or 100 if no pages)
    if results:
        overall_score = sum(p.visual_score for p in results) // len(results)
    else:
        overall_score = 100

    severity_counts = {"high": 0, "medium": 0, "low": 0}
    for f in all_findings:
        if f.severity in severity_counts:
            severity_counts[f.severity] += 1

    total_findings = len(all_findings)
    summary = (
        f"{len(results)} page(s) evaluated, "
        f"{total_findings} finding(s) "
        f"({severity_counts['high']} high, {severity_counts['medium']} medium, "
        f"{severity_counts['low']} low), "
        f"visual score {overall_score}/100, "
        f"~{total_tokens:,} tokens used"
    )
    if total_skipped:
        summary += f", {total_skipped} dimension(s) skipped"

    markdown = _build_visual_markdown(pages_data, overall_score, severity_counts)

    report: dict[str, Any] = {
        "pages": pages_data,
        "visual_score": overall_score,
        "findings_by_severity": severity_counts,
        "tokens_used": total_tokens,
        "summary": summary,
        "markdown": markdown,
    }
    if total_skipped:
        report["dimensions_skipped_total"] = total_skipped
    return report


def _build_visual_markdown(
    pages: list[dict[str, Any]],
    overall_score: int,
    severity_counts: dict[str, int],
) -> str:
    """Build markdown report from visual evaluation results."""
    lines = [
        "# Visual Evaluation Report",
        "",
        f"**Overall Visual Score: {overall_score}/100**",
        "",
        f"Findings: {severity_counts['high']} high, "
        f"{severity_counts['medium']} medium, {severity_counts['low']} low",
        "",
    ]

    for page in pages:
        route = page["route"]
        vp = page["viewport"]
        score = page["visual_score"]
        icon = "ok" if score >= 90 else ("!!" if score < 70 else "!!")
        lines.append(f"## {route} ({vp}) — {score}/100 [{icon}]")
        lines.append("")

        if not page["findings"]:
            lines.append("No issues found.")
            lines.append("")
            continue

        for f in page["findings"]:
            sev = f["severity"].upper()
            lines.append(f"- **[{sev}]** {f['finding']}")
            lines.append(f"  - Evidence: {f['evidence']}")
            lines.append(f"  - Fix: {f['remediation']}")
        lines.append("")

    return "\n".join(lines)
