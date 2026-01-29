"""
PPTX pitch deck generator.

Generates professional investor pitch decks from PitchContext.
Uses python-pptx for slide creation with a dark navy theme.

python-pptx is an optional dependency. The generator checks for
its availability at runtime and returns a clear error if missing.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from dazzle.pitch.extractor import PitchContext
from dazzle.pitch.ir import BrandColors

logger = logging.getLogger(__name__)


@dataclass
class GeneratorResult:
    """Result of a generator run."""

    success: bool
    output_path: Path | None = None
    files_created: list[str] = field(default_factory=list)
    error: str | None = None
    slide_count: int = 0


def _check_pptx_available() -> bool:
    """Check if python-pptx is available."""
    try:
        import pptx  # noqa: F401

        return True
    except ImportError:
        return False


def _resolve_colors(brand: BrandColors) -> dict[str, Any]:
    """Convert brand hex colors to RGBColor objects."""
    from pptx.dml.color import RGBColor

    def hex_to_rgb(hex_color: str) -> RGBColor:
        h = hex_color.lstrip("#")
        return RGBColor(int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))

    return {
        "primary": hex_to_rgb(brand.primary),
        "accent": hex_to_rgb(brand.accent),
        "highlight": hex_to_rgb(brand.highlight),
        "success": hex_to_rgb(brand.success),
        "light": hex_to_rgb(brand.light),
        "white": RGBColor(0xFF, 0xFF, 0xFF),
        "dark_text": hex_to_rgb(brand.primary),
        "muted": RGBColor(0x99, 0x99, 0x99),
    }


def _add_text_box(
    slide: Any,
    left: Any,
    top: Any,
    width: Any,
    height: Any,
    text: str,
    *,
    font_size: int = 18,
    bold: bool = False,
    color: Any = None,
    alignment: int | None = None,
) -> Any:
    """Add a text box to a slide."""
    from pptx.util import Pt

    txbox = slide.shapes.add_textbox(left, top, width, height)
    tf = txbox.text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0]
    p.text = text
    p.font.size = Pt(font_size)
    p.font.bold = bold
    if color:
        p.font.color.rgb = color
    if alignment is not None:
        p.alignment = alignment
    return txbox


def _create_dark_slide(prs: Any, colors: dict[str, Any]) -> Any:
    """Create a slide with dark background."""
    slide = prs.slides.add_slide(prs.slide_layouts[6])  # blank layout
    background = slide.background
    fill = background.fill
    fill.solid()
    fill.fore_color.rgb = colors["primary"]
    return slide


def _add_speaker_notes(slide: Any, text: str) -> None:
    """Add speaker notes to a slide."""
    notes_slide = slide.notes_slide
    notes_slide.notes_text_frame.text = text


def _fmt_currency(amount: int, currency: str = "GBP") -> str:
    """Format an amount as currency."""
    symbols = {"GBP": "\u00a3", "USD": "$", "EUR": "\u20ac"}
    symbol = symbols.get(currency, currency + " ")
    if amount >= 1_000_000_000:
        return f"{symbol}{amount / 1_000_000_000:.1f}B"
    elif amount >= 1_000_000:
        return f"{symbol}{amount / 1_000_000:.1f}M"
    elif amount >= 1_000:
        return f"{symbol}{amount / 1_000:.0f}K"
    return f"{symbol}{amount:,}"


# =============================================================================
# Slide Builders
# =============================================================================


def _build_title_slide(prs: Any, ctx: PitchContext, colors: dict[str, Any]) -> None:
    """Build the title slide."""
    from pptx.enum.text import PP_ALIGN
    from pptx.util import Inches

    slide = _create_dark_slide(prs, colors)
    name = ctx.spec.company.name
    tagline = ctx.spec.company.tagline or ""

    _add_text_box(
        slide,
        Inches(1),
        Inches(2.5),
        Inches(11),
        Inches(1.5),
        name,
        font_size=48,
        bold=True,
        color=colors["white"],
        alignment=PP_ALIGN.CENTER,
    )
    if tagline:
        _add_text_box(
            slide,
            Inches(1),
            Inches(4.0),
            Inches(11),
            Inches(1),
            tagline,
            font_size=24,
            color=colors["accent"],
            alignment=PP_ALIGN.CENTER,
        )

    stage = ctx.spec.company.stage.value.replace("_", " ").title()
    _add_text_box(
        slide,
        Inches(5),
        Inches(5.5),
        Inches(3),
        Inches(0.5),
        stage,
        font_size=14,
        color=colors["muted"],
        alignment=PP_ALIGN.CENTER,
    )
    _add_speaker_notes(slide, f"Title slide for {name}. {tagline}")


def _build_problem_slide(prs: Any, ctx: PitchContext, colors: dict[str, Any]) -> None:
    """Build the problem slide."""
    from pptx.util import Inches

    problem = ctx.spec.problem
    if not problem:
        return

    slide = _create_dark_slide(prs, colors)
    _add_text_box(
        slide,
        Inches(0.8),
        Inches(0.5),
        Inches(11),
        Inches(1),
        problem.headline,
        font_size=36,
        bold=True,
        color=colors["highlight"],
    )

    y = 2.0
    for point in problem.points:
        _add_text_box(
            slide,
            Inches(1.2),
            Inches(y),
            Inches(10),
            Inches(0.6),
            f"\u2022 {point}",
            font_size=20,
            color=colors["white"],
        )
        y += 0.7

    if problem.market_failure:
        y += 0.3
        _add_text_box(
            slide,
            Inches(0.8),
            Inches(y),
            Inches(11),
            Inches(0.6),
            "Market Failure",
            font_size=24,
            bold=True,
            color=colors["accent"],
        )
        y += 0.7
        for failure in problem.market_failure:
            _add_text_box(
                slide,
                Inches(1.2),
                Inches(y),
                Inches(10),
                Inches(0.6),
                f"\u2192 {failure}",
                font_size=18,
                color=colors["muted"],
            )
            y += 0.6

    _add_speaker_notes(slide, f"Problem: {problem.headline}")


def _build_solution_slide(prs: Any, ctx: PitchContext, colors: dict[str, Any]) -> None:
    """Build the solution slide."""
    from pptx.util import Inches

    solution = ctx.spec.solution
    if not solution:
        return

    slide = _create_dark_slide(prs, colors)
    _add_text_box(
        slide,
        Inches(0.8),
        Inches(0.5),
        Inches(11),
        Inches(1),
        solution.headline,
        font_size=36,
        bold=True,
        color=colors["success"],
    )

    y = 2.0
    if solution.how_it_works:
        for i, step in enumerate(solution.how_it_works, 1):
            _add_text_box(
                slide,
                Inches(1.2),
                Inches(y),
                Inches(5),
                Inches(0.6),
                f"{i}. {step}",
                font_size=18,
                color=colors["white"],
            )
            y += 0.6

    if solution.value_props:
        vy = 2.0
        _add_text_box(
            slide,
            Inches(7),
            Inches(vy - 0.5),
            Inches(5),
            Inches(0.5),
            "Value Propositions",
            font_size=20,
            bold=True,
            color=colors["accent"],
        )
        for prop in solution.value_props:
            _add_text_box(
                slide,
                Inches(7.2),
                Inches(vy + 0.2),
                Inches(5),
                Inches(0.5),
                f"\u2713 {prop}",
                font_size=16,
                color=colors["white"],
            )
            vy += 0.5

    _add_speaker_notes(slide, f"Solution: {solution.headline}")


def _build_platform_slide(prs: Any, ctx: PitchContext, colors: dict[str, Any]) -> None:
    """Build platform overview slide from DSL data."""
    from pptx.enum.text import PP_ALIGN
    from pptx.util import Inches

    if not ctx.entities and not ctx.surfaces:
        return

    slide = _create_dark_slide(prs, colors)
    _add_text_box(
        slide,
        Inches(0.8),
        Inches(0.5),
        Inches(11),
        Inches(1),
        "Platform Overview",
        font_size=36,
        bold=True,
        color=colors["white"],
    )

    metrics: list[tuple[str, str]] = []
    if ctx.entities:
        metrics.append((str(len(ctx.entities)), "Data Models"))
    if ctx.surfaces:
        metrics.append((str(len(ctx.surfaces)), "Screens"))
    if ctx.state_machines:
        metrics.append((str(len(ctx.state_machines)), "Workflows"))
    if ctx.story_count:
        metrics.append((str(ctx.story_count), "User Stories"))

    if metrics:
        x_start = 1.0
        box_w = 2.5
        for i, (value, label) in enumerate(metrics[:4]):
            x = x_start + i * 3.0
            _add_text_box(
                slide,
                Inches(x),
                Inches(2.0),
                Inches(box_w),
                Inches(1),
                value,
                font_size=48,
                bold=True,
                color=colors["accent"],
                alignment=PP_ALIGN.CENTER,
            )
            _add_text_box(
                slide,
                Inches(x),
                Inches(3.0),
                Inches(box_w),
                Inches(0.5),
                label,
                font_size=16,
                color=colors["muted"],
                alignment=PP_ALIGN.CENTER,
            )

    if ctx.entities:
        y = 4.2
        _add_text_box(
            slide,
            Inches(0.8),
            Inches(y),
            Inches(5),
            Inches(0.5),
            "Core Entities",
            font_size=18,
            bold=True,
            color=colors["accent"],
        )
        y += 0.5
        entity_text = ", ".join(ctx.entities[:8])
        if len(ctx.entities) > 8:
            entity_text += f" +{len(ctx.entities) - 8} more"
        _add_text_box(
            slide,
            Inches(1.0),
            Inches(y),
            Inches(10),
            Inches(0.5),
            entity_text,
            font_size=14,
            color=colors["white"],
        )

    _add_speaker_notes(
        slide,
        f"Platform built with {len(ctx.entities)} entities, "
        f"{len(ctx.surfaces)} surfaces. Auto-generated from DSL.",
    )


def _build_personas_slide(prs: Any, ctx: PitchContext, colors: dict[str, Any]) -> None:
    """Build personas slide from DSL data."""
    from pptx.util import Inches

    if not ctx.personas:
        return

    slide = _create_dark_slide(prs, colors)
    _add_text_box(
        slide,
        Inches(0.8),
        Inches(0.5),
        Inches(11),
        Inches(1),
        "User Personas",
        font_size=36,
        bold=True,
        color=colors["white"],
    )

    y = 2.0
    for persona in ctx.personas[:6]:
        _add_text_box(
            slide,
            Inches(1.2),
            Inches(y),
            Inches(3),
            Inches(0.5),
            persona["label"],
            font_size=22,
            bold=True,
            color=colors["accent"],
        )
        if persona.get("description"):
            _add_text_box(
                slide,
                Inches(4.5),
                Inches(y),
                Inches(7),
                Inches(0.5),
                persona["description"],
                font_size=16,
                color=colors["muted"],
            )
        y += 0.8

    _add_speaker_notes(slide, f"{len(ctx.personas)} user personas defined in DSL.")


def _build_market_slide(prs: Any, ctx: PitchContext, colors: dict[str, Any]) -> None:
    """Build market sizing slide."""
    from pptx.enum.text import PP_ALIGN
    from pptx.util import Inches

    market = ctx.spec.market
    if not market:
        return

    slide = _create_dark_slide(prs, colors)
    _add_text_box(
        slide,
        Inches(0.8),
        Inches(0.5),
        Inches(11),
        Inches(1),
        "Market Opportunity",
        font_size=36,
        bold=True,
        color=colors["white"],
    )

    currency = ctx.spec.company.currency
    sizes = []
    if market.tam:
        sizes.append(("TAM", market.tam))
    if market.sam:
        sizes.append(("SAM", market.sam))
    if market.som:
        sizes.append(("SOM", market.som))

    x_start = 1.0
    for i, (label, size) in enumerate(sizes):
        x = x_start + i * 4.0
        _add_text_box(
            slide,
            Inches(x),
            Inches(2.0),
            Inches(3.5),
            Inches(0.5),
            label,
            font_size=20,
            bold=True,
            color=colors["muted"],
            alignment=PP_ALIGN.CENTER,
        )
        _add_text_box(
            slide,
            Inches(x),
            Inches(2.5),
            Inches(3.5),
            Inches(1),
            _fmt_currency(size.value, currency),
            font_size=42,
            bold=True,
            color=colors["accent"],
            alignment=PP_ALIGN.CENTER,
        )
        _add_text_box(
            slide,
            Inches(x),
            Inches(3.5),
            Inches(3.5),
            Inches(0.5),
            size.label,
            font_size=14,
            color=colors["white"],
            alignment=PP_ALIGN.CENTER,
        )

    if market.drivers:
        y = 5.0
        _add_text_box(
            slide,
            Inches(0.8),
            Inches(y),
            Inches(11),
            Inches(0.5),
            "Market Drivers",
            font_size=20,
            bold=True,
            color=colors["accent"],
        )
        y += 0.6
        for driver in market.drivers:
            _add_text_box(
                slide,
                Inches(1.2),
                Inches(y),
                Inches(10),
                Inches(0.4),
                f"\u25b8 {driver}",
                font_size=16,
                color=colors["white"],
            )
            y += 0.5

    _add_speaker_notes(slide, "Market sizing: TAM/SAM/SOM breakdown.")


def _build_business_model_slide(prs: Any, ctx: PitchContext, colors: dict[str, Any]) -> None:
    """Build business model / pricing slide."""
    from pptx.enum.text import PP_ALIGN
    from pptx.util import Inches

    bm = ctx.spec.business_model
    if not bm or not bm.tiers:
        return

    slide = _create_dark_slide(prs, colors)
    _add_text_box(
        slide,
        Inches(0.8),
        Inches(0.5),
        Inches(11),
        Inches(1),
        "Business Model",
        font_size=36,
        bold=True,
        color=colors["white"],
    )

    currency = ctx.spec.company.currency
    tier_count = len(bm.tiers)
    box_w = min(3.5, 11.0 / max(tier_count, 1))

    for i, tier in enumerate(bm.tiers):
        x = 0.8 + i * (box_w + 0.3)
        y = 2.0

        name_color = colors["highlight"] if tier.highlighted else colors["white"]
        _add_text_box(
            slide,
            Inches(x),
            Inches(y),
            Inches(box_w),
            Inches(0.5),
            tier.name,
            font_size=22,
            bold=True,
            color=name_color,
            alignment=PP_ALIGN.CENTER,
        )

        price_str = _fmt_currency(tier.price, currency) if tier.price else "Free"
        _add_text_box(
            slide,
            Inches(x),
            Inches(y + 0.6),
            Inches(box_w),
            Inches(0.8),
            f"{price_str}/{tier.period}",
            font_size=28,
            bold=True,
            color=colors["accent"],
            alignment=PP_ALIGN.CENTER,
        )

        if tier.features:
            _add_text_box(
                slide,
                Inches(x),
                Inches(y + 1.5),
                Inches(box_w),
                Inches(2),
                tier.features,
                font_size=14,
                color=colors["muted"],
                alignment=PP_ALIGN.CENTER,
            )

    _add_speaker_notes(slide, f"Business model with {tier_count} pricing tiers.")


def _build_financials_slide(prs: Any, ctx: PitchContext, colors: dict[str, Any]) -> None:
    """Build financials slide with projections."""
    from pptx.enum.text import PP_ALIGN
    from pptx.util import Inches

    fin = ctx.spec.financials
    if not fin or not fin.projections:
        return

    slide = _create_dark_slide(prs, colors)
    _add_text_box(
        slide,
        Inches(0.8),
        Inches(0.5),
        Inches(11),
        Inches(1),
        "Financial Projections",
        font_size=36,
        bold=True,
        color=colors["white"],
    )

    currency = ctx.spec.company.currency
    col_count = len(fin.projections)
    col_w = min(3.0, 11.0 / max(col_count, 1))

    for i, proj in enumerate(fin.projections):
        x = 0.8 + i * (col_w + 0.3)
        _add_text_box(
            slide,
            Inches(x),
            Inches(2.0),
            Inches(col_w),
            Inches(0.5),
            str(proj.year),
            font_size=20,
            bold=True,
            color=colors["muted"],
            alignment=PP_ALIGN.CENTER,
        )
        _add_text_box(
            slide,
            Inches(x),
            Inches(2.6),
            Inches(col_w),
            Inches(0.8),
            _fmt_currency(proj.revenue, currency),
            font_size=32,
            bold=True,
            color=colors["success"],
            alignment=PP_ALIGN.CENTER,
        )
        _add_text_box(
            slide,
            Inches(x),
            Inches(3.4),
            Inches(col_w),
            Inches(0.4),
            "Revenue",
            font_size=12,
            color=colors["muted"],
            alignment=PP_ALIGN.CENTER,
        )
        _add_text_box(
            slide,
            Inches(x),
            Inches(4.0),
            Inches(col_w),
            Inches(0.5),
            f"{proj.customers:,} customers",
            font_size=16,
            color=colors["white"],
            alignment=PP_ALIGN.CENTER,
        )

    if fin.use_of_funds:
        y = 5.2
        _add_text_box(
            slide,
            Inches(0.8),
            Inches(y),
            Inches(11),
            Inches(0.5),
            "Use of Funds",
            font_size=20,
            bold=True,
            color=colors["accent"],
        )
        y += 0.5
        parts = [f"{f.category} ({f.percent}%)" for f in fin.use_of_funds]
        _add_text_box(
            slide,
            Inches(1.0),
            Inches(y),
            Inches(11),
            Inches(0.5),
            "  |  ".join(parts),
            font_size=14,
            color=colors["white"],
        )

    _add_speaker_notes(slide, "Financial projections and use of funds breakdown.")


def _build_team_slide(prs: Any, ctx: PitchContext, colors: dict[str, Any]) -> None:
    """Build team slide."""
    from pptx.util import Inches

    team = ctx.spec.team
    if not team:
        return

    slide = _create_dark_slide(prs, colors)
    _add_text_box(
        slide,
        Inches(0.8),
        Inches(0.5),
        Inches(11),
        Inches(1),
        "Team",
        font_size=36,
        bold=True,
        color=colors["white"],
    )

    y = 2.0
    for member in team.founders:
        _add_text_box(
            slide,
            Inches(1.2),
            Inches(y),
            Inches(3),
            Inches(0.5),
            member.name,
            font_size=22,
            bold=True,
            color=colors["accent"],
        )
        _add_text_box(
            slide,
            Inches(4.5),
            Inches(y),
            Inches(2),
            Inches(0.5),
            member.role,
            font_size=18,
            color=colors["highlight"],
        )
        if member.bio:
            _add_text_box(
                slide,
                Inches(1.2),
                Inches(y + 0.4),
                Inches(10),
                Inches(0.4),
                member.bio,
                font_size=14,
                color=colors["muted"],
            )
            y += 1.0
        else:
            y += 0.7

    if team.advisors:
        y += 0.3
        _add_text_box(
            slide,
            Inches(0.8),
            Inches(y),
            Inches(11),
            Inches(0.5),
            "Advisors",
            font_size=20,
            bold=True,
            color=colors["accent"],
        )
        y += 0.5
        for advisor in team.advisors:
            _add_text_box(
                slide,
                Inches(1.2),
                Inches(y),
                Inches(5),
                Inches(0.4),
                f"{advisor.name} \u2014 {advisor.role}",
                font_size=16,
                color=colors["white"],
            )
            y += 0.5

    if team.key_hires:
        y += 0.3
        _add_text_box(
            slide,
            Inches(0.8),
            Inches(y),
            Inches(11),
            Inches(0.5),
            "Key Hires",
            font_size=20,
            bold=True,
            color=colors["accent"],
        )
        y += 0.5
        for hire in team.key_hires:
            timing = f" ({hire.timing})" if hire.timing else ""
            _add_text_box(
                slide,
                Inches(1.2),
                Inches(y),
                Inches(10),
                Inches(0.4),
                f"{hire.role}{timing}",
                font_size=16,
                color=colors["white"],
            )
            y += 0.5

    _add_speaker_notes(
        slide, f"Team: {len(team.founders)} founders, {len(team.advisors)} advisors."
    )


def _build_competition_slide(prs: Any, ctx: PitchContext, colors: dict[str, Any]) -> None:
    """Build competition slide."""
    from pptx.util import Inches

    if not ctx.spec.competitors:
        return

    slide = _create_dark_slide(prs, colors)
    _add_text_box(
        slide,
        Inches(0.8),
        Inches(0.5),
        Inches(11),
        Inches(1),
        "Competitive Landscape",
        font_size=36,
        bold=True,
        color=colors["white"],
    )

    y = 2.0
    _add_text_box(
        slide,
        Inches(1.0),
        Inches(y),
        Inches(3),
        Inches(0.5),
        "Competitor",
        font_size=16,
        bold=True,
        color=colors["accent"],
    )
    _add_text_box(
        slide,
        Inches(4.5),
        Inches(y),
        Inches(3.5),
        Inches(0.5),
        "Strength",
        font_size=16,
        bold=True,
        color=colors["success"],
    )
    _add_text_box(
        slide,
        Inches(8.5),
        Inches(y),
        Inches(3.5),
        Inches(0.5),
        "Weakness",
        font_size=16,
        bold=True,
        color=colors["highlight"],
    )
    y += 0.6

    for comp in ctx.spec.competitors[:6]:
        _add_text_box(
            slide,
            Inches(1.0),
            Inches(y),
            Inches(3),
            Inches(0.5),
            comp.name,
            font_size=16,
            bold=True,
            color=colors["white"],
        )
        if comp.strength:
            _add_text_box(
                slide,
                Inches(4.5),
                Inches(y),
                Inches(3.5),
                Inches(0.5),
                comp.strength,
                font_size=14,
                color=colors["muted"],
            )
        if comp.weakness:
            _add_text_box(
                slide,
                Inches(8.5),
                Inches(y),
                Inches(3.5),
                Inches(0.5),
                comp.weakness,
                font_size=14,
                color=colors["muted"],
            )
        y += 0.7

    _add_speaker_notes(slide, f"{len(ctx.spec.competitors)} competitors analyzed.")


def _build_milestones_slide(prs: Any, ctx: PitchContext, colors: dict[str, Any]) -> None:
    """Build milestones / roadmap slide."""
    from pptx.util import Inches

    ms = ctx.spec.milestones
    if not ms:
        return

    slide = _create_dark_slide(prs, colors)
    _add_text_box(
        slide,
        Inches(0.8),
        Inches(0.5),
        Inches(11),
        Inches(1),
        "Milestones & Roadmap",
        font_size=36,
        bold=True,
        color=colors["white"],
    )

    y = 2.0

    if ms.completed:
        _add_text_box(
            slide,
            Inches(0.8),
            Inches(y),
            Inches(5),
            Inches(0.5),
            "Completed \u2713",
            font_size=20,
            bold=True,
            color=colors["success"],
        )
        y += 0.5
        for item in ms.completed:
            _add_text_box(
                slide,
                Inches(1.2),
                Inches(y),
                Inches(10),
                Inches(0.4),
                f"\u2713 {item}",
                font_size=16,
                color=colors["muted"],
            )
            y += 0.5

    if ms.next_12_months:
        y += 0.3
        _add_text_box(
            slide,
            Inches(0.8),
            Inches(y),
            Inches(5),
            Inches(0.5),
            "Next 12 Months",
            font_size=20,
            bold=True,
            color=colors["accent"],
        )
        y += 0.5
        for item in ms.next_12_months:
            _add_text_box(
                slide,
                Inches(1.2),
                Inches(y),
                Inches(10),
                Inches(0.4),
                f"\u2192 {item}",
                font_size=16,
                color=colors["white"],
            )
            y += 0.5

    if ms.long_term:
        y += 0.3
        _add_text_box(
            slide,
            Inches(0.8),
            Inches(y),
            Inches(5),
            Inches(0.5),
            "Long Term Vision",
            font_size=20,
            bold=True,
            color=colors["highlight"],
        )
        y += 0.5
        for item in ms.long_term:
            _add_text_box(
                slide,
                Inches(1.2),
                Inches(y),
                Inches(10),
                Inches(0.4),
                f"\u25c6 {item}",
                font_size=16,
                color=colors["muted"],
            )
            y += 0.5

    _add_speaker_notes(slide, "Milestones and roadmap.")


def _build_ask_slide(prs: Any, ctx: PitchContext, colors: dict[str, Any]) -> None:
    """Build the funding ask slide."""
    from pptx.enum.text import PP_ALIGN
    from pptx.util import Inches

    if not ctx.spec.company.funding_ask:
        return

    slide = _create_dark_slide(prs, colors)
    _add_text_box(
        slide,
        Inches(0.8),
        Inches(0.5),
        Inches(11),
        Inches(1),
        "The Ask",
        font_size=36,
        bold=True,
        color=colors["white"],
    )

    currency = ctx.spec.company.currency
    ask_str = _fmt_currency(ctx.spec.company.funding_ask, currency)
    stage = ctx.spec.company.stage.value.replace("_", " ").title()

    _add_text_box(
        slide,
        Inches(1),
        Inches(2.5),
        Inches(11),
        Inches(1.5),
        ask_str,
        font_size=64,
        bold=True,
        color=colors["highlight"],
        alignment=PP_ALIGN.CENTER,
    )
    _add_text_box(
        slide,
        Inches(1),
        Inches(4.0),
        Inches(11),
        Inches(0.5),
        f"{stage} Round",
        font_size=24,
        color=colors["accent"],
        alignment=PP_ALIGN.CENTER,
    )

    if ctx.spec.company.runway_months:
        _add_text_box(
            slide,
            Inches(1),
            Inches(5.0),
            Inches(11),
            Inches(0.5),
            f"{ctx.spec.company.runway_months} months runway",
            font_size=18,
            color=colors["muted"],
            alignment=PP_ALIGN.CENTER,
        )

    if ctx.spec.financials and ctx.spec.financials.use_of_funds:
        y = 5.8
        parts = [f"{f.category} ({f.percent}%)" for f in ctx.spec.financials.use_of_funds]
        _add_text_box(
            slide,
            Inches(1),
            Inches(y),
            Inches(11),
            Inches(0.5),
            "  |  ".join(parts),
            font_size=14,
            color=colors["white"],
            alignment=PP_ALIGN.CENTER,
        )

    _add_speaker_notes(slide, f"Raising {ask_str} at {stage} stage.")


def _build_closing_slide(prs: Any, ctx: PitchContext, colors: dict[str, Any]) -> None:
    """Build the closing / thank you slide."""
    from pptx.enum.text import PP_ALIGN
    from pptx.util import Inches

    slide = _create_dark_slide(prs, colors)
    _add_text_box(
        slide,
        Inches(1),
        Inches(2.5),
        Inches(11),
        Inches(1.5),
        "Thank You",
        font_size=48,
        bold=True,
        color=colors["white"],
        alignment=PP_ALIGN.CENTER,
    )
    _add_text_box(
        slide,
        Inches(1),
        Inches(4.2),
        Inches(11),
        Inches(0.8),
        ctx.spec.company.name,
        font_size=28,
        color=colors["accent"],
        alignment=PP_ALIGN.CENTER,
    )
    if ctx.spec.company.tagline:
        _add_text_box(
            slide,
            Inches(1),
            Inches(5.0),
            Inches(11),
            Inches(0.5),
            ctx.spec.company.tagline,
            font_size=18,
            color=colors["muted"],
            alignment=PP_ALIGN.CENTER,
        )

    _add_speaker_notes(slide, "Closing slide. Open for questions.")


# =============================================================================
# Slide Catalog
# =============================================================================


def _has_problem(ctx: PitchContext) -> bool:
    return ctx.spec.problem is not None


def _has_solution(ctx: PitchContext) -> bool:
    return ctx.spec.solution is not None


def _has_dsl(ctx: PitchContext) -> bool:
    return bool(ctx.entities or ctx.surfaces)


def _has_personas(ctx: PitchContext) -> bool:
    return bool(ctx.personas)


def _has_market(ctx: PitchContext) -> bool:
    return ctx.spec.market is not None


def _has_tiers(ctx: PitchContext) -> bool:
    return ctx.spec.business_model is not None and bool(ctx.spec.business_model.tiers)


def _has_projections(ctx: PitchContext) -> bool:
    return ctx.spec.financials is not None and bool(ctx.spec.financials.projections)


def _has_team(ctx: PitchContext) -> bool:
    return ctx.spec.team is not None


def _has_competitors(ctx: PitchContext) -> bool:
    return bool(ctx.spec.competitors)


def _has_milestones(ctx: PitchContext) -> bool:
    return ctx.spec.milestones is not None


def _has_funding_ask(ctx: PitchContext) -> bool:
    return ctx.spec.company.funding_ask is not None


def _always(_ctx: PitchContext) -> bool:
    return True


# Ordered slide catalog: (name, builder, condition)
SlideCatalogEntry = tuple[str, Callable[..., None], Callable[[PitchContext], bool]]

SLIDE_CATALOG: list[SlideCatalogEntry] = [
    ("title", _build_title_slide, _always),
    ("problem", _build_problem_slide, _has_problem),
    ("solution", _build_solution_slide, _has_solution),
    ("platform", _build_platform_slide, _has_dsl),
    ("personas", _build_personas_slide, _has_personas),
    ("market", _build_market_slide, _has_market),
    ("business_model", _build_business_model_slide, _has_tiers),
    ("financials", _build_financials_slide, _has_projections),
    ("team", _build_team_slide, _has_team),
    ("competition", _build_competition_slide, _has_competitors),
    ("milestones", _build_milestones_slide, _has_milestones),
    ("ask", _build_ask_slide, _has_funding_ask),
    ("closing", _build_closing_slide, _always),
]


# =============================================================================
# Main Generator
# =============================================================================


def generate_pptx(ctx: PitchContext, output_path: Path) -> GeneratorResult:
    """Generate PPTX pitch deck from PitchContext.

    Args:
        ctx: PitchContext with merged PitchSpec + DSL data.
        output_path: Path to write the .pptx file.

    Returns:
        GeneratorResult with success status and output path.
    """
    if not _check_pptx_available():
        return GeneratorResult(
            success=False,
            error="python-pptx is not installed. Install with: pip install 'dazzle[pitch]'",
        )

    try:
        from pptx import Presentation as PptxPresentation
        from pptx.util import Inches

        prs = PptxPresentation()
        prs.slide_width = Inches(13.333)
        prs.slide_height = Inches(7.5)

        colors = _resolve_colors(ctx.spec.brand)

        slide_count = 0
        for name, builder, condition in SLIDE_CATALOG:
            if condition(ctx):
                builder(prs, ctx, colors)
                slide_count += 1
                logger.debug(f"Built slide: {name}")

        output_path.parent.mkdir(parents=True, exist_ok=True)
        prs.save(str(output_path))

        return GeneratorResult(
            success=True,
            output_path=output_path,
            files_created=[str(output_path)],
            slide_count=slide_count,
        )

    except Exception as e:
        logger.exception("Error generating PPTX")
        return GeneratorResult(success=False, error=str(e))
