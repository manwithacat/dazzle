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

# Re-export primitives for backwards compatibility
from dazzle.pitch.generators.pptx_primitives import (  # noqa: F401
    CONTENT_BOTTOM,
    CONTENT_TOP,
    SLIDE_HEIGHT,
    SLIDE_WIDTH,
    ContentRegion,
    LayoutResult,
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
    _estimate_text_height,
    _fmt_currency,
    _resolve_colors,
)

# Re-export slide builders for backwards compatibility
from dazzle.pitch.generators.pptx_slides import (  # noqa: F401
    _build_ask_slide,
    _build_business_model_slide,
    _build_closing_slide,
    _build_competition_slide,
    _build_extra_slide,
    _build_financials_slide,
    _build_market_slide,
    _build_milestones_slide,
    _build_personas_slide,
    _build_platform_slide,
    _build_problem_slide,
    _build_solution_slide,
    _build_team_slide,
    _build_title_slide,
)
from dazzle.pitch.ir import ExtraSlide, ExtraSlideLayout

__all__ = [
    "GeneratorResult",
    "generate_pptx",
    "ContentRegion",
    "LayoutResult",
    "_estimate_text_height",
    "SLIDE_WIDTH",
    "SLIDE_HEIGHT",
    "CONTENT_TOP",
    "CONTENT_BOTTOM",
    "_fmt_currency",
    "_resolve_colors",
    "_add_text_box",
    "_add_rich_text_box",
    "_create_dark_slide",
    "_create_light_slide",
    "_add_speaker_notes",
    "_add_card",
    "_add_stat_box",
    "_add_columns",
    "_add_slide_heading",
    "_add_bullet_list",
    "_add_table",
    "_add_callout_box",
    "_add_divider",
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

logger = logging.getLogger(__name__)


@dataclass
class GeneratorResult:
    """Result of a generator run."""

    success: bool
    output_path: Path | None = None
    files_created: list[str] = field(default_factory=list)
    error: str | None = None
    slide_count: int = 0
    warnings: list[str] = field(default_factory=list)


def _check_pptx_available() -> bool:
    """Check if python-pptx is available."""
    try:
        import pptx  # noqa: F401

        return True
    except ImportError:
        return False


# =============================================================================
# Condition functions
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
# Bounds Audit
# =============================================================================


def _audit_slide_bounds(prs: Any) -> list[str]:
    """Scan all shapes on all slides for overflow past slide height."""
    warnings: list[str] = []
    for slide_idx, slide in enumerate(prs.slides):
        for shape in slide.shapes:
            bottom = (shape.top + shape.height) / 914400  # EMU to inches
            if bottom > SLIDE_HEIGHT:
                warnings.append(
                    f"Slide {slide_idx + 1}: shape '{shape.name}' "
                    f'extends to {bottom:.1f}" (slide height {SLIDE_HEIGHT}")'
                )
    return warnings


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

        # Generate charts and populate ctx.chart_paths
        try:
            from dazzle.pitch.generators.charts import (
                generate_funds_chart,
                generate_market_chart,
                generate_revenue_chart,
            )

            chart_dir = output_path.parent / "charts"
            chart_dir.mkdir(parents=True, exist_ok=True)
            hex_colors: dict[str, Any] = {
                "primary": ctx.spec.brand.primary,
                "accent": ctx.spec.brand.accent,
                "highlight": ctx.spec.brand.highlight,
                "success": ctx.spec.brand.success,
                "light": ctx.spec.brand.light,
            }
            for name, gen_fn in [
                ("revenue", generate_revenue_chart),
                ("market", generate_market_chart),
                ("funds", generate_funds_chart),
            ]:
                path = gen_fn(ctx, chart_dir, hex_colors)
                if path:
                    ctx.chart_paths[name] = path
        except Exception as e:
            logger.debug(f"Chart generation skipped: {e}")

        # Capture warnings from slide builders
        pitch_logger = logging.getLogger("dazzle.pitch")
        builder_warnings: list[str] = []

        class _WarningCapture(logging.Handler):
            def emit(self, record: logging.LogRecord) -> None:
                if record.levelno >= logging.WARNING:
                    builder_warnings.append(record.getMessage())

        warning_handler = _WarningCapture()
        pitch_logger.addHandler(warning_handler)

        # Build catalog and extra slide maps
        catalog_map: dict[str, tuple[Callable[..., None], Callable[[PitchContext], bool]]] = {
            entry_name: (builder, condition) for entry_name, builder, condition in SLIDE_CATALOG
        }
        extra_map: dict[str, ExtraSlide] = {
            es.title.lower().replace(" ", "_"): es for es in ctx.spec.extra_slides
        }

        # Determine slide order
        if ctx.spec.slide_order:
            ordered_names = list(ctx.spec.slide_order)
        else:
            ordered_names = [entry_name for entry_name, _, _ in SLIDE_CATALOG]
            # Insert extras before closing
            if extra_map:
                closing_idx = (
                    ordered_names.index("closing")
                    if "closing" in ordered_names
                    else len(ordered_names)
                )
                for extra_name in extra_map:
                    ordered_names.insert(closing_idx, extra_name)
                    closing_idx += 1

        # Discover plugins
        from dazzle.pitch.generators.plugin_loader import discover_plugins

        plugin_root = ctx.project_root or output_path.parent
        plugin_registry = discover_plugins(plugin_root)

        slide_count = 0
        for slide_name in ordered_names:
            if slide_name in catalog_map:
                builder, condition = catalog_map[slide_name]
                if condition(ctx):
                    builder(prs, ctx, colors)
                    slide_count += 1
                    logger.debug(f"Built slide: {slide_name}")
            elif slide_name in extra_map:
                extra = extra_map[slide_name]
                if extra.layout == ExtraSlideLayout.CUSTOM and extra.builder:
                    custom_builder = plugin_registry.get(extra.builder)
                    if custom_builder:
                        try:
                            custom_builder(prs, ctx, colors, extra)
                            slide_count += 1
                            logger.debug(f"Built custom slide: {slide_name}")
                        except Exception as e:
                            logger.warning(f"Plugin builder '{extra.builder}' failed: {e}")
                    else:
                        logger.warning(f"No plugin builder found: {extra.builder}")
                else:
                    _build_extra_slide(prs, ctx, colors, extra)
                    slide_count += 1
                    logger.debug(f"Built extra slide: {slide_name}")

        # Remove warning capture handler
        pitch_logger.removeHandler(warning_handler)

        # Audit bounds before saving
        audit_warnings = _audit_slide_bounds(prs)
        for w in audit_warnings:
            logger.warning(w)

        all_warnings = builder_warnings + audit_warnings

        output_path.parent.mkdir(parents=True, exist_ok=True)
        prs.save(str(output_path))

        return GeneratorResult(
            success=True,
            output_path=output_path,
            files_created=[str(output_path)],
            slide_count=slide_count,
            warnings=all_warnings,
        )

    except Exception as e:
        logger.exception("Error generating PPTX")
        return GeneratorResult(success=False, error=str(e))
