"""
Markdown narrative generator for business plans.

Generates a structured Markdown document from PitchContext
with optional chart images if matplotlib is available.
"""

from __future__ import annotations

import logging
from pathlib import Path

from dazzle.pitch.extractor import PitchContext
from dazzle.pitch.generators.pptx_gen import GeneratorResult, _fmt_currency

logger = logging.getLogger(__name__)


def generate_narrative(ctx: PitchContext, output_path: Path) -> GeneratorResult:
    """Generate Markdown business plan from PitchContext.

    Args:
        ctx: PitchContext with merged PitchSpec + DSL data.
        output_path: Path to write the .md file.

    Returns:
        GeneratorResult with success status and output path.
    """
    try:
        lines: list[str] = []
        currency = ctx.spec.company.currency
        files_created: list[str] = []

        # Title
        lines.append(f"# {ctx.spec.company.name}")
        if ctx.spec.company.tagline:
            lines.append(f"\n*{ctx.spec.company.tagline}*")
        lines.append("")

        stage = ctx.spec.company.stage.value.replace("_", " ").title()
        lines.append(f"**Stage:** {stage}")
        if ctx.spec.company.funding_ask:
            lines.append(f"**Raising:** {_fmt_currency(ctx.spec.company.funding_ask, currency)}")
        lines.append("")

        # Executive Summary
        lines.append("## Executive Summary")
        lines.append("")
        if ctx.spec.problem:
            lines.append(f"**Problem:** {ctx.spec.problem.headline}")
        if ctx.spec.solution:
            lines.append(f"**Solution:** {ctx.spec.solution.headline}")
        if ctx.entities:
            lines.append(
                f"**Platform:** {len(ctx.entities)} data models, {len(ctx.surfaces)} screens"
            )
        lines.append("")

        # Problem
        if ctx.spec.problem:
            lines.append("## The Problem")
            lines.append("")
            lines.append(f"### {ctx.spec.problem.headline}")
            lines.append("")
            for point in ctx.spec.problem.points:
                lines.append(f"- {point}")
            if ctx.spec.problem.market_failure:
                lines.append("")
                lines.append("**Market Failure:**")
                for failure in ctx.spec.problem.market_failure:
                    lines.append(f"- {failure}")
            lines.append("")

        # Solution
        if ctx.spec.solution:
            lines.append("## Our Solution")
            lines.append("")
            lines.append(f"### {ctx.spec.solution.headline}")
            lines.append("")
            if ctx.spec.solution.how_it_works:
                lines.append("**How it works:**")
                for i, step in enumerate(ctx.spec.solution.how_it_works, 1):
                    lines.append(f"{i}. {step}")
                lines.append("")
            if ctx.spec.solution.value_props:
                lines.append("**Value Propositions:**")
                for prop in ctx.spec.solution.value_props:
                    lines.append(f"- {prop}")
            lines.append("")

        # Platform (from DSL)
        if ctx.entities or ctx.surfaces:
            lines.append("## Platform Overview")
            lines.append("")
            lines.append("| Metric | Count |")
            lines.append("|--------|-------|")
            if ctx.entities:
                lines.append(f"| Data Models | {len(ctx.entities)} |")
            if ctx.surfaces:
                lines.append(f"| Screens | {len(ctx.surfaces)} |")
            if ctx.personas:
                lines.append(f"| User Personas | {len(ctx.personas)} |")
            if ctx.state_machines:
                lines.append(f"| Workflows | {len(ctx.state_machines)} |")
            if ctx.story_count:
                lines.append(f"| User Stories | {ctx.story_count} |")
            lines.append("")
            if ctx.entities:
                lines.append(f"**Core Entities:** {', '.join(ctx.entities)}")
                lines.append("")

        # Market
        if ctx.spec.market:
            lines.append("## Market Opportunity")
            lines.append("")
            market = ctx.spec.market
            if market.tam:
                lines.append(
                    f"- **TAM:** {_fmt_currency(market.tam.value, currency)} "
                    f"\u2014 {market.tam.label}"
                )
            if market.sam:
                lines.append(
                    f"- **SAM:** {_fmt_currency(market.sam.value, currency)} "
                    f"\u2014 {market.sam.label}"
                )
            if market.som:
                lines.append(
                    f"- **SOM:** {_fmt_currency(market.som.value, currency)} "
                    f"\u2014 {market.som.label}"
                )
            if market.drivers:
                lines.append("")
                lines.append("**Market Drivers:**")
                for driver in market.drivers:
                    lines.append(f"- {driver}")
            lines.append("")

        # Business Model
        if ctx.spec.business_model and ctx.spec.business_model.tiers:
            lines.append("## Business Model")
            lines.append("")
            lines.append("| Tier | Price | Features |")
            lines.append("|------|-------|----------|")
            for tier in ctx.spec.business_model.tiers:
                price = _fmt_currency(tier.price, currency) if tier.price else "Free"
                features = tier.features or ""
                highlight = " **\u2605**" if tier.highlighted else ""
                lines.append(f"| {tier.name}{highlight} | {price}/{tier.period} | {features} |")
            lines.append("")

        # Financials
        if ctx.spec.financials and ctx.spec.financials.projections:
            lines.append("## Financial Projections")
            lines.append("")
            lines.append("| Year | Customers | Revenue | Costs |")
            lines.append("|------|-----------|---------|-------|")
            for proj in ctx.spec.financials.projections:
                costs = _fmt_currency(proj.costs, currency) if proj.costs else "\u2014"
                lines.append(
                    f"| {proj.year} | {proj.customers:,} | "
                    f"{_fmt_currency(proj.revenue, currency)} | {costs} |"
                )
            lines.append("")

            if ctx.spec.financials.use_of_funds:
                lines.append("### Use of Funds")
                lines.append("")
                for fund in ctx.spec.financials.use_of_funds:
                    desc = f" \u2014 {fund.description}" if fund.description else ""
                    lines.append(f"- **{fund.category}** ({fund.percent}%){desc}")
                lines.append("")

        # Team
        if ctx.spec.team:
            lines.append("## Team")
            lines.append("")
            team = ctx.spec.team
            if team.founders:
                lines.append("### Founders")
                for m in team.founders:
                    bio = f" \u2014 {m.bio}" if m.bio else ""
                    lines.append(f"- **{m.name}**, {m.role}{bio}")
                lines.append("")
            if team.advisors:
                lines.append("### Advisors")
                for m in team.advisors:
                    bio = f" \u2014 {m.bio}" if m.bio else ""
                    lines.append(f"- **{m.name}**, {m.role}{bio}")
                lines.append("")
            if team.key_hires:
                lines.append("### Key Hires Planned")
                for h in team.key_hires:
                    timing = f" ({h.timing})" if h.timing else ""
                    lines.append(f"- **{h.role}**{timing}")
                lines.append("")

        # Competition
        if ctx.spec.competitors:
            lines.append("## Competitive Landscape")
            lines.append("")
            lines.append("| Competitor | Strength | Weakness |")
            lines.append("|-----------|----------|----------|")
            for comp in ctx.spec.competitors:
                strength = comp.strength or "\u2014"
                weakness = comp.weakness or "\u2014"
                lines.append(f"| {comp.name} | {strength} | {weakness} |")
            lines.append("")

        # Milestones
        if ctx.spec.milestones:
            lines.append("## Milestones & Roadmap")
            lines.append("")
            ms = ctx.spec.milestones
            if ms.completed:
                lines.append("### Completed")
                for item in ms.completed:
                    lines.append(f"- [x] {item}")
                lines.append("")
            if ms.next_12_months:
                lines.append("### Next 12 Months")
                for item in ms.next_12_months:
                    lines.append(f"- [ ] {item}")
                lines.append("")
            if ms.long_term:
                lines.append("### Long Term")
                for item in ms.long_term:
                    lines.append(f"- {item}")
                lines.append("")

        # Footer
        lines.append("---")
        lines.append("*Generated by DAZZLE Pitch*")

        # Write output
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text("\n".join(lines), encoding="utf-8")
        files_created.insert(0, str(output_path))

        return GeneratorResult(
            success=True,
            output_path=output_path,
            files_created=files_created,
        )

    except Exception as e:
        logger.exception("Error generating narrative")
        return GeneratorResult(success=False, error=str(e))
