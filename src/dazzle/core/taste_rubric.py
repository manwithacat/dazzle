"""Taste rubric — the judged dimensions of the Dazzle house aesthetic.

Single source of truth consumed by the blind judge panel
(``dazzle.qa.taste_panel``), the composition pipeline (opt-in ``taste``
focus), and the drift gate on ``docs/reference/taste.md``.

Dimensions are phrased as generic design quality. They MUST NOT name or
allude to any specific framework, library, or company aesthetic — the
parity target is perceived quality, not resemblance (spec: Goodhart guard).
"""

from collections.abc import Sequence
from dataclasses import dataclass

__all__ = [
    "TASTE_DIMENSIONS",
    "TasteDimension",
    "build_judge_prompt",
    "dimensions_for_theme",
]


@dataclass(frozen=True)
class TasteDimension:
    """One judged dimension of visual taste."""

    key: str
    title: str
    question: str
    # (score, description) calibration anchors at 2 / 5 / 8 on a 1-10 scale.
    anchors: tuple[tuple[int, str], ...]
    applies_to: str  # "light" | "dark" | "both"


TASTE_DIMENSIONS: tuple[TasteDimension, ...] = (
    TasteDimension(
        key="typographic_hierarchy",
        title="Typographic hierarchy",
        question=(
            "Does type alone communicate what matters most on this screen? "
            "Judge scale contrast, weight discipline, line length/height, and "
            "whether headings, labels, values and captions are instantly "
            "distinguishable without relying on boxes or color."
        ),
        anchors=(
            (2, "Near-uniform text sizes; hierarchy only guessable from position."),
            (5, "Clear heading/body split but weak label/value/caption tiers."),
            (
                8,
                "Deliberate scale with confident weight contrast; every text "
                "role identifiable at a glance.",
            ),
        ),
        applies_to="both",
    ),
    TasteDimension(
        key="spatial_rhythm",
        title="Spatial rhythm",
        question=(
            "Do gaps, padding and alignment follow a consistent rhythm? Judge "
            "whether spacing looks like it sits on a fixed scale, whether "
            "related items cluster and unrelated items separate, and whether "
            "density feels intentional rather than cramped or vacant."
        ),
        anchors=(
            (2, "Arbitrary gaps; misaligned edges; crowding next to dead space."),
            (5, "Mostly consistent spacing with occasional off-scale gaps or ragged alignment."),
            (8, "Even, confident rhythm; alignment lines are visible; density reads as designed."),
        ),
        applies_to="both",
    ),
    TasteDimension(
        key="color_discipline",
        title="Color discipline",
        question=(
            "Is color used with restraint and meaning? Judge whether neutrals "
            "carry the structure, whether one accent is applied consistently to "
            "what matters, and whether semantic colors (success/warning/danger) "
            "appear only where they mean something."
        ),
        anchors=(
            (2, "Competing hues; decorative color; unclear what color signifies."),
            (5, "Restrained palette but accent applied inconsistently or semantics muddy."),
            (
                8,
                "Neutrals do the work; one accent, purposefully placed; color "
                "always means something.",
            ),
        ),
        applies_to="both",
    ),
    TasteDimension(
        key="state_completeness",
        title="State completeness",
        question=(
            "Do the visible interactive elements look deliberately designed in "
            "their current state? Judge buttons, inputs, rows and empty regions: "
            "are affordances crisp (borders, fills, focus/selection cues), do "
            "empty states look designed rather than absent, and is there any "
            "browser-default styling showing through?"
        ),
        anchors=(
            (2, "Browser-default controls; empty areas look broken or unfinished."),
            (5, "Styled controls but flat affordances; empty states present but perfunctory."),
            (8, "Every visible control and empty state looks intentionally finished."),
        ),
        applies_to="both",
    ),
    TasteDimension(
        key="dark_mode_integrity",
        title="Dark-mode integrity",
        question=(
            "Does this dark screen look designed as a dark material rather than "
            "an inverted light theme? Judge surface layering (does elevation "
            "read through lightness?), contrast comfort (no pure-black pits or "
            "glaring whites), and whether accents/semantic colors were "
            "recalibrated for the dark context."
        ),
        anchors=(
            (2, "Inverted-looking; harsh contrast; colors glow or vanish."),
            (5, "Serviceable dark theme; layering weak; some colors uncorrected."),
            (8, "Coherent dark material; elevation legible; recalibrated, comfortable palette."),
        ),
        applies_to="dark",
    ),
    TasteDimension(
        key="perceived_craft",
        title="Perceived craft",
        question=(
            "Overall, does this screen look like a design team sweated the "
            "details? Judge the gestalt: corner radii and border consistency, "
            "shadow/elevation quality, icon/text optical alignment, and the "
            "absence of anything that looks accidental."
        ),
        anchors=(
            (2, "Reads as unstyled scaffolding or template output."),
            (5, "Competent and clean but generic; nothing looks loved."),
            (8, "Polished and coherent; detail quality signals a strong design hand."),
        ),
        applies_to="both",
    ),
)


def dimensions_for_theme(theme: str) -> tuple[TasteDimension, ...]:
    """Return the dimensions applicable to *theme* ("light" or "dark")."""
    return tuple(d for d in TASTE_DIMENSIONS if d.applies_to in ("both", theme))


def build_judge_prompt(dimensions: Sequence[TasteDimension]) -> str:
    """Build the scoring prompt for one screenshot across *dimensions*.

    The judge sees ONE image and returns strict JSON:
    ``{"scores": {"<key>": int, ...}, "worst_detail": str}``.
    """
    lines = [
        "You are a senior product designer scoring a single UI screenshot.",
        "Score each dimension from 1 (worst) to 10 (best) using the anchors.",
        "Judge only what is visible. Do not guess at the technology used;",
        "score design quality, not style familiarity.",
        "",
    ]
    for d in dimensions:
        lines.append(f"## {d.key} — {d.title}")
        lines.append(d.question)
        for score, text in d.anchors:
            lines.append(f"  {score} = {text}")
        lines.append("")
    keys = ", ".join(f'"{d.key}": <1-10>' for d in dimensions)
    lines.append(
        "Respond with ONLY a JSON object, no prose, of the form: "
        f'{{"scores": {{{keys}}}, "worst_detail": "<one sentence naming the '
        'single weakest visible detail>"}'
    )
    return "\n".join(lines)
