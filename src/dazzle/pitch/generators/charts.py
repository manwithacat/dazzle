"""
Chart generators for pitch materials.

Uses matplotlib (optional dependency) to generate PNG charts
for embedding in narrative Markdown documents.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from dazzle.pitch.extractor import PitchContext

logger = logging.getLogger(__name__)


def _check_matplotlib_available() -> bool:
    """Check if matplotlib is available."""
    try:
        import matplotlib  # noqa: F401

        return True
    except ImportError:
        return False


def generate_revenue_chart(
    ctx: PitchContext,
    output_dir: Path,
    colors: dict[str, str],
) -> Path | None:
    """Generate a revenue projection bar chart.

    Returns:
        Path to the generated PNG, or None if generation failed.
    """
    if not _check_matplotlib_available():
        logger.debug("matplotlib not available, skipping chart generation")
        return None

    fin = ctx.spec.financials
    if not fin or not fin.projections:
        return None

    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        years = [str(p.year) for p in fin.projections]
        revenue = [p.revenue for p in fin.projections]
        costs = [p.costs or 0 for p in fin.projections]

        fig, ax = plt.subplots(figsize=(8, 4))
        fig.patch.set_facecolor(colors.get("primary", "#0F1A2E"))
        ax.set_facecolor(colors.get("primary", "#0F1A2E"))

        x = range(len(years))
        bar_width = 0.35

        ax.bar(
            [i - bar_width / 2 for i in x],
            revenue,
            bar_width,
            label="Revenue",
            color=colors.get("success", "#28A745"),
        )
        if any(costs):
            ax.bar(
                [i + bar_width / 2 for i in x],
                costs,
                bar_width,
                label="Costs",
                color=colors.get("accent", "#2E86AB"),
                alpha=0.7,
            )

        ax.set_xticks(list(x))
        ax.set_xticklabels(years, color="white")
        ax.tick_params(colors="white")
        ax.spines["bottom"].set_color("white")
        ax.spines["left"].set_color("white")
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.yaxis.label.set_color("white")
        ax.set_ylabel("Amount")
        ax.legend(facecolor="#1a2740", edgecolor="white", labelcolor="white")

        output_path = output_dir / "revenue_chart.png"
        fig.savefig(output_path, dpi=150, bbox_inches="tight", transparent=False)
        plt.close(fig)

        logger.info(f"Generated revenue chart: {output_path}")
        return output_path

    except Exception as e:
        logger.warning(f"Failed to generate revenue chart: {e}")
        return None


def generate_market_chart(
    ctx: PitchContext,
    output_dir: Path,
    colors: dict[str, str],
) -> Path | None:
    """Generate a market size comparison chart.

    Returns:
        Path to the generated PNG, or None if generation failed.
    """
    if not _check_matplotlib_available():
        return None

    market = ctx.spec.market
    if not market:
        return None

    sizes = []
    labels = []
    if market.tam:
        labels.append("TAM")
        sizes.append(market.tam.value)
    if market.sam:
        labels.append("SAM")
        sizes.append(market.sam.value)
    if market.som:
        labels.append("SOM")
        sizes.append(market.som.value)

    if not sizes:
        return None

    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        fig, ax = plt.subplots(figsize=(6, 4))
        fig.patch.set_facecolor(colors.get("primary", "#0F1A2E"))
        ax.set_facecolor(colors.get("primary", "#0F1A2E"))

        bar_color = colors.get("accent", "#2E86AB")
        ax.barh(labels, sizes, color=bar_color)
        ax.tick_params(colors="white")
        ax.spines["bottom"].set_color("white")
        ax.spines["left"].set_color("white")
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)

        output_path = output_dir / "market_chart.png"
        fig.savefig(output_path, dpi=150, bbox_inches="tight", transparent=False)
        plt.close(fig)

        logger.info(f"Generated market chart: {output_path}")
        return output_path

    except Exception as e:
        logger.warning(f"Failed to generate market chart: {e}")
        return None


def generate_funds_chart(
    ctx: PitchContext,
    output_dir: Path,
    colors: dict[str, str],
) -> Path | None:
    """Generate a use-of-funds pie chart.

    Returns:
        Path to the generated PNG, or None if generation failed.
    """
    if not _check_matplotlib_available():
        return None

    fin = ctx.spec.financials
    if not fin or not fin.use_of_funds:
        return None

    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        labels = [f.category for f in fin.use_of_funds]
        sizes = [f.percent for f in fin.use_of_funds]

        fig, ax = plt.subplots(figsize=(6, 4))
        fig.patch.set_facecolor(colors.get("primary", "#0F1A2E"))

        chart_colors = [
            colors.get("accent", "#2E86AB"),
            colors.get("success", "#28A745"),
            "#E86F2C",
            "#9B59B6",
            "#F1C40F",
        ]

        ax.pie(
            sizes,
            labels=labels,
            autopct="%1.0f%%",
            colors=chart_colors[: len(sizes)],
            textprops={"color": "white"},
        )

        output_path = output_dir / "funds_chart.png"
        fig.savefig(output_path, dpi=150, bbox_inches="tight", transparent=False)
        plt.close(fig)

        logger.info(f"Generated funds chart: {output_path}")
        return output_path

    except Exception as e:
        logger.warning(f"Failed to generate funds chart: {e}")
        return None
