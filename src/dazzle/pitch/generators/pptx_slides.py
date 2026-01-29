"""
PPTX slide builder functions.

Each function builds one slide type from PitchContext data.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from dazzle.pitch.extractor import PitchContext
from dazzle.pitch.generators.pptx_primitives import (
    CONTENT_BOTTOM,
    _add_bullet_list,
    _add_callout_box,
    _add_card,
    _add_columns,
    _add_divider,
    _add_rich_text_box,
    _add_slide_heading,
    _add_speaker_notes,
    _add_stat_box,
    _add_table,
    _add_text_box,
    _create_dark_slide,
    _create_light_slide,
    _fmt_currency,
)
from dazzle.pitch.ir import ExtraSlide, ExtraSlideLayout

logger = logging.getLogger(__name__)

# Re-export stat_box and columns for type-checker satisfaction
__all__ = [
    "_build_title_slide",
    "_build_problem_slide",
    "_build_solution_slide",
    "_build_platform_slide",
    "_build_personas_slide",
    "_build_market_slide",
    "_build_business_model_slide",
    "_build_financials_slide",
    "_build_team_slide",
    "_build_competition_slide",
    "_build_milestones_slide",
    "_build_ask_slide",
    "_build_closing_slide",
    "_build_extra_slide",
]

# Suppress unused-import warnings for primitives used only by specific builders
_ = (_add_stat_box, _add_columns, _add_rich_text_box, _add_callout_box, _add_table, _add_divider)


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

    # Logo embedding
    if ctx.spec.company.logo_path:
        logo = Path(ctx.spec.company.logo_path)
        if logo.exists():
            slide.shapes.add_picture(str(logo), Inches(5.5), Inches(0.5), Inches(2), Inches(1))

    notes = ctx.spec.company.speaker_notes if ctx.spec.company else None
    _add_speaker_notes(slide, notes or f"Title slide for {name}. {tagline}")


def _build_problem_slide(prs: Any, ctx: PitchContext, colors: dict[str, Any]) -> None:
    """Build the problem slide."""
    from pptx.util import Inches

    problem = ctx.spec.problem
    if not problem:
        return

    slide = _create_dark_slide(prs, colors)
    y = _add_slide_heading(slide, problem.headline, colors, text_color=colors["highlight"])

    y = _add_bullet_list(
        slide, Inches(1.2), y, Inches(10), problem.points, colors, font_size=20, spacing=0.7
    ).final_y

    if problem.market_failure:
        y += 0.3
        font_name = colors.get("font_family")
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
            font_name=font_name,
        )
        y += 0.7
        y = _add_bullet_list(
            slide,
            Inches(1.2),
            y,
            Inches(10),
            problem.market_failure,
            colors,
            font_size=18,
            spacing=0.6,
            bullet_char="\u2192",
            color=colors["muted"],
        ).final_y

    notes = problem.speaker_notes
    _add_speaker_notes(slide, notes or f"Problem: {problem.headline}")


def _build_solution_slide(prs: Any, ctx: PitchContext, colors: dict[str, Any]) -> None:
    """Build the solution slide."""
    from pptx.util import Inches

    solution = ctx.spec.solution
    if not solution:
        return

    slide = _create_dark_slide(prs, colors)
    y = _add_slide_heading(slide, solution.headline, colors, text_color=colors["success"])

    font_name = colors.get("font_family")
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
                font_name=font_name,
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
            font_name=font_name,
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
                font_name=font_name,
            )
            vy += 0.5

    notes = solution.speaker_notes
    _add_speaker_notes(slide, notes or f"Solution: {solution.headline}")


def _build_platform_slide(prs: Any, ctx: PitchContext, colors: dict[str, Any]) -> None:
    """Build platform overview slide from DSL data."""
    from pptx.enum.text import PP_ALIGN
    from pptx.util import Inches

    if not ctx.entities and not ctx.surfaces:
        return

    slide = _create_dark_slide(prs, colors)
    _add_slide_heading(slide, "Platform Overview", colors)

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
            # Card background behind each stat
            _add_card(
                slide,
                Inches(x - 0.2),
                Inches(1.8),
                Inches(box_w + 0.4),
                Inches(1.8),
                fill_color=colors.get("dark_text"),
                border_color=colors["accent"],
            )
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
    _add_slide_heading(slide, "User Personas", colors)

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
    _add_slide_heading(slide, "Market Opportunity", colors)

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

    # Embed market chart if available
    market_chart = ctx.chart_paths.get("market")
    if market_chart and Path(market_chart).exists():
        try:
            slide.shapes.add_picture(
                str(market_chart), Inches(7), Inches(4.5), Inches(5), Inches(2.5)
            )
        except Exception as e:
            logger.debug(f"Failed to embed market chart: {e}")

    notes = market.speaker_notes
    _add_speaker_notes(slide, notes or "Market sizing: TAM/SAM/SOM breakdown.")


def _build_business_model_slide(prs: Any, ctx: PitchContext, colors: dict[str, Any]) -> None:
    """Build business model / pricing slide."""
    from pptx.enum.text import PP_ALIGN
    from pptx.util import Inches

    bm = ctx.spec.business_model
    if not bm or not bm.tiers:
        return

    slide = _create_dark_slide(prs, colors)
    _add_slide_heading(slide, "Business Model", colors)

    currency = ctx.spec.company.currency
    tier_count = len(bm.tiers)
    box_w = min(3.5, 11.0 / max(tier_count, 1))

    for i, tier in enumerate(bm.tiers):
        x = 0.8 + i * (box_w + 0.3)
        y = 2.0

        # Card background for each tier
        card_border = colors["accent"] if tier.highlighted else colors["muted"]
        _add_card(
            slide,
            Inches(x - 0.1),
            Inches(y - 0.1),
            Inches(box_w + 0.2),
            Inches(2.3),
            fill_color=colors.get("dark_text"),
            border_color=card_border,
        )

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

    notes = bm.speaker_notes
    _add_speaker_notes(slide, notes or f"Business model with {tier_count} pricing tiers.")


def _build_financials_slide(prs: Any, ctx: PitchContext, colors: dict[str, Any]) -> None:
    """Build financials slide with projections."""
    from pptx.enum.text import PP_ALIGN
    from pptx.util import Inches

    fin = ctx.spec.financials
    if not fin or not fin.projections:
        return

    slide = _create_dark_slide(prs, colors)
    _add_slide_heading(slide, "Financial Projections", colors)

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

    # Embed revenue chart if available
    revenue_chart = ctx.chart_paths.get("revenue")
    if revenue_chart and Path(revenue_chart).exists():
        try:
            slide.shapes.add_picture(
                str(revenue_chart), Inches(0.8), Inches(4.5), Inches(5), Inches(2.5)
            )
        except Exception as e:
            logger.debug(f"Failed to embed revenue chart: {e}")

    notes = fin.speaker_notes
    _add_speaker_notes(slide, notes or "Financial projections and use of funds breakdown.")


def _build_team_slide(prs: Any, ctx: PitchContext, colors: dict[str, Any]) -> None:
    """Build team slide with light background."""
    from pptx.util import Inches

    team = ctx.spec.team
    if not team:
        return

    slide = _create_light_slide(prs, colors)
    y = _add_slide_heading(slide, "Team", colors, text_color=colors["dark_text"])

    font_name = colors.get("font_family")
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
            font_name=font_name,
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
            font_name=font_name,
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
                font_name=font_name,
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
            font_name=font_name,
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
                color=colors["dark_text"],
                font_name=font_name,
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
            font_name=font_name,
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
                color=colors["dark_text"],
                font_name=font_name,
            )
            y += 0.5

    notes = team.speaker_notes
    _add_speaker_notes(
        slide,
        notes or f"Team: {len(team.founders)} founders, {len(team.advisors)} advisors.",
    )


def _build_competition_slide(prs: Any, ctx: PitchContext, colors: dict[str, Any]) -> None:
    """Build competition slide with light background and table."""
    from pptx.util import Inches

    if not ctx.spec.competitors:
        return

    slide = _create_light_slide(prs, colors)
    _add_slide_heading(slide, "Competitive Landscape", colors, text_color=colors["dark_text"])

    headers = ["Competitor", "Strength", "Weakness"]
    rows = [
        [comp.name, comp.strength or "", comp.weakness or ""] for comp in ctx.spec.competitors[:6]
    ]
    _add_table(
        slide,
        Inches(0.8),
        Inches(2.2),
        Inches(11.5),
        headers,
        rows,
        colors,
        col_widths=[3.5, 4.0, 4.0],
        font_size=14,
    )  # returns (shape, LayoutResult) — unused here

    _add_speaker_notes(slide, f"{len(ctx.spec.competitors)} competitors analyzed.")


def _build_milestones_slide(prs: Any, ctx: PitchContext, colors: dict[str, Any]) -> None:
    """Build milestones / roadmap slide."""
    from pptx.util import Inches

    ms = ctx.spec.milestones
    if not ms:
        return

    slide = _create_dark_slide(prs, colors)
    y = _add_slide_heading(slide, "Milestones & Roadmap", colors)

    font_name = colors.get("font_family")

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
            font_name=font_name,
        )
        y += 0.5
        y = _add_bullet_list(
            slide,
            Inches(1.2),
            y,
            Inches(10),
            ms.completed,
            colors,
            font_size=16,
            spacing=0.5,
            bullet_char="\u2713",
            color=colors["muted"],
        ).final_y

    if ms.next_12_months:
        if ms.completed:
            _add_divider(slide, y + 0.1, colors)
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
            font_name=font_name,
        )
        y += 0.5
        y = _add_bullet_list(
            slide,
            Inches(1.2),
            y,
            Inches(10),
            ms.next_12_months,
            colors,
            font_size=16,
            spacing=0.5,
            bullet_char="\u2192",
        ).final_y

    if ms.long_term:
        if ms.completed or ms.next_12_months:
            _add_divider(slide, y + 0.1, colors)
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
            font_name=font_name,
        )
        y += 0.5
        y = _add_bullet_list(
            slide,
            Inches(1.2),
            y,
            Inches(10),
            ms.long_term,
            colors,
            font_size=16,
            spacing=0.5,
            bullet_char="\u25c6",
            color=colors["muted"],
        ).final_y

    notes = ms.speaker_notes
    _add_speaker_notes(slide, notes or "Milestones and roadmap.")


def _build_ask_slide(prs: Any, ctx: PitchContext, colors: dict[str, Any]) -> None:
    """Build the funding ask slide."""
    from pptx.enum.text import PP_ALIGN
    from pptx.util import Inches

    if not ctx.spec.company.funding_ask:
        return

    slide = _create_dark_slide(prs, colors)
    _add_slide_heading(slide, "The Ask", colors)

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

    # Embed funds chart if available
    funds_chart = ctx.chart_paths.get("funds")
    if funds_chart and Path(funds_chart).exists():
        try:
            slide.shapes.add_picture(
                str(funds_chart), Inches(8), Inches(4.5), Inches(4), Inches(2.5)
            )
        except Exception as e:
            logger.debug(f"Failed to embed funds chart: {e}")

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

    notes = ctx.spec.company.speaker_notes if ctx.spec.company else None
    _add_speaker_notes(slide, notes or "Closing slide. Open for questions.")


def _build_extra_slide(
    prs: Any, ctx: PitchContext, colors: dict[str, Any], extra: ExtraSlide
) -> None:
    """Build a user-defined extra slide based on its layout."""
    from pptx.enum.text import PP_ALIGN
    from pptx.util import Inches

    use_light = extra.theme == "light"
    slide = _create_light_slide(prs, colors) if use_light else _create_dark_slide(prs, colors)
    heading_color = colors["dark_text"] if use_light else colors["white"]
    text_color = colors["dark_text"] if use_light else colors["white"]
    y = _add_slide_heading(slide, extra.title, colors, text_color=heading_color)

    font_name = colors.get("font_family")

    if extra.layout == ExtraSlideLayout.BULLETS:
        _add_bullet_list(
            slide,
            Inches(1.2),
            y,
            Inches(10),
            extra.items,
            colors,
            font_size=20,
            spacing=0.7,
            color=text_color,
        )

    elif extra.layout == ExtraSlideLayout.STATS:
        parsed: list[tuple[str, str]] = []
        for item in extra.items:
            if "|" in item:
                val, lbl = item.split("|", 1)
                parsed.append((val.strip(), lbl.strip()))
            else:
                parsed.append((item, ""))
        _add_columns(
            slide,
            Inches(2.0),
            parsed,
            value_color=colors["accent"],
            label_color=colors["muted"],
            alignment=PP_ALIGN.CENTER,
        )

    elif extra.layout == ExtraSlideLayout.CARDS:
        # Multi-column card grid
        items = extra.items
        col_count = min(3, len(items)) if items else 1
        margin = 1.0
        gap = 0.3
        card_w = (11.0 - gap * (col_count - 1)) / col_count
        card_h = 0.8
        row_gap = 0.3
        for idx, item in enumerate(items):
            col = idx % col_count
            row = idx // col_count
            x = margin + col * (card_w + gap)
            cy = y + row * (card_h + row_gap)
            if cy + card_h > CONTENT_BOTTOM:
                break
            _add_card(
                slide,
                Inches(x),
                Inches(cy),
                Inches(card_w),
                Inches(card_h),
                fill_color=colors.get("dark_text"),
                border_color=colors["accent"],
            )
            _add_rich_text_box(
                slide,
                Inches(x + 0.3),
                Inches(cy + 0.1),
                Inches(card_w - 0.6),
                Inches(0.6),
                item,
                font_size=18,
                color=colors["white"] if not use_light else colors["white"],
                font_name=font_name,
            )

    elif extra.layout == ExtraSlideLayout.TABLE:
        # Parse items as pipe-separated: first item = headers, rest = rows
        if extra.items:
            headers = [h.strip() for h in extra.items[0].split("|")]
            rows = [[c.strip() for c in item.split("|")] for item in extra.items[1:]]
            _add_table(
                slide,
                Inches(0.8),
                Inches(y),
                Inches(11.5),
                headers,
                rows,
                colors,
                font_size=14,
            )  # returns (shape, LayoutResult) — unused here

    elif extra.layout == ExtraSlideLayout.CALLOUT:
        # First item as callout box, rest as supporting bullets
        if extra.items:
            _add_callout_box(
                slide,
                Inches(0.8),
                Inches(y),
                Inches(11.5),
                extra.items[0],
                colors,
                font_size=24,
            )
            if len(extra.items) > 1:
                _add_bullet_list(
                    slide,
                    Inches(1.2),
                    y + 1.5,
                    Inches(10),
                    extra.items[1:],
                    colors,
                    font_size=18,
                    spacing=0.6,
                    color=text_color,
                )

    elif extra.layout == ExtraSlideLayout.CUSTOM:
        # Handled by plugin system in pptx_gen.py
        pass

    elif extra.layout == ExtraSlideLayout.IMAGE:
        if extra.image_path:
            try:
                slide.shapes.add_picture(
                    extra.image_path,
                    Inches(1.5),
                    Inches(2.0),
                    Inches(10),
                    Inches(5),
                )
            except Exception as e:
                logger.warning(f"Failed to embed image {extra.image_path}: {e}")

    notes = extra.speaker_notes
    _add_speaker_notes(slide, notes or f"Extra slide: {extra.title}")
