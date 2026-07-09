"""Sitespec marketing vision rubric — the judged dimensions of a modern landing page.

The reference-anchored half of Goal 2's measurement (James: "rubric floor + reference
score"). Where `testing/sitespec_hygiene.py` scores the CSS *structure* deterministically,
this rubric is what a blind LLM-vision judge scores a *rendered* marketing page on —
holistic "does an experienced web developer read this as modern / industry-norm."

Reuses the taste-panel machinery: the same `TasteDimension` shape and `build_judge_prompt`
as `core.taste_rubric` (app internals), so the judge glue in `qa/taste_panel.py` drives
both. The dimensions differ because marketing pages are judged on landing-page vernacular
(hero impact, editorial hierarchy, confident whitespace) rather than app-density taste.

Two scoring passes compose the vision score (see the plan + the exemplar harness
`scripts/taste/capture_sitespec_references.py`):
1. HYGIENE-as-judged — these dimensions, scored on our rendered page in isolation.
2. FAMILY FIDELITY — the same page scored *against* its family's exemplar screenshots
   ("does this read as Stripe-esque / Linear-esque"), the `family_fidelity` dimension.
"""

from __future__ import annotations

from collections.abc import Sequence

from dazzle.core.taste_rubric import TasteDimension, build_judge_prompt

__all__ = [
    "SITESPEC_VISION_DIMENSIONS",
    "build_sitespec_judge_prompt",
]


# Anchors calibrate the 1-10 scale at 2 (weak) / 5 (competent) / 8 (strong). They
# encode what "modern marketing page" means so the judge is consistent across runs.
SITESPEC_VISION_DIMENSIONS: tuple[TasteDimension, ...] = (
    TasteDimension(
        key="hero_impact",
        title="Hero impact",
        question=(
            "Does the hero (the first fold) immediately land the value proposition with "
            "confidence — a dominant headline, supporting subhead, and a clear primary "
            "action — and does it look considered rather than templated?"
        ),
        anchors=(
            (2, "generic/templated hero; small or timid headline; unclear what this is"),
            (5, "clear headline + subhead + CTA; competent but unremarkable"),
            (8, "striking, confident hero; instantly communicates value; memorable"),
        ),
        applies_to="both",
    ),
    TasteDimension(
        key="visual_hierarchy",
        title="Visual hierarchy",
        question=(
            "Is there a clear, editorial reading order — one dominant element per section, "
            "supporting elements clearly subordinate — so the eye is led, not left to wander?"
        ),
        anchors=(
            (2, "flat or competing emphasis; everything the same weight; no clear path"),
            (5, "discernible hierarchy; headings vs body distinct"),
            (8, "commanding, editorial hierarchy; the eye is led effortlessly"),
        ),
        applies_to="both",
    ),
    TasteDimension(
        key="whitespace_rhythm",
        title="Whitespace & section rhythm",
        question=(
            "Does the page breathe — generous, confident whitespace and a consistent "
            "vertical rhythm between sections — versus cramped, uneven, or filler-padded?"
        ),
        anchors=(
            (2, "cramped or uneven; sections crash together or drift; nervous spacing"),
            (5, "adequate spacing; mostly consistent section rhythm"),
            (8, "generous, deliberate whitespace; a calm, confident cadence"),
        ),
        applies_to="both",
    ),
    TasteDimension(
        key="type_modernity",
        title="Type modernity",
        question=(
            "Does the typography read as current — a real scale, weight contrast, comfortable "
            "measure, fluid display sizes — rather than default/dated (browser defaults, one "
            "weight, tiny headings)?"
        ),
        anchors=(
            (2, "default or dated type; one weight; timid or oversized-without-scale"),
            (5, "coherent type scale; readable; unremarkable"),
            (8, "modern, expressive type; confident scale + weight contrast"),
        ),
        applies_to="both",
    ),
    TasteDimension(
        key="colour_confidence",
        title="Colour & imagery confidence",
        question=(
            "Is the palette cohesive and used with intent — a clear accent, tasteful use of "
            "gradient/imagery/depth — rather than muddy, arbitrary, or flat-and-lifeless?"
        ),
        anchors=(
            (2, "arbitrary or muddy colour; no clear accent; flat and lifeless"),
            (5, "cohesive palette; a clear accent; safe"),
            (8, "confident, intentional colour + imagery; depth used with taste"),
        ),
        applies_to="both",
    ),
    TasteDimension(
        key="cta_prominence",
        title="Call-to-action prominence",
        question=(
            "Is the primary action unmistakable and inviting — well-placed, high-contrast, "
            "and repeated at natural decision points — versus buried, timid, or ambiguous?"
        ),
        anchors=(
            (2, "primary action buried, timid, or indistinguishable from secondary links"),
            (5, "a clear primary CTA; adequate contrast"),
            (8, "inviting, prominent CTA; well-placed and reinforced down the page"),
        ),
        applies_to="both",
    ),
    TasteDimension(
        key="finish_polish",
        title="Finish & polish",
        question=(
            "Overall craft: alignment, consistency, considered motion/hover cues, and the "
            "absence of rough edges — does it feel shipped by a design-led team?"
        ),
        anchors=(
            (2, "rough: misalignment, inconsistency, unstyled edges; feels unfinished"),
            (5, "clean and consistent; competent finish"),
            (8, "high craft; every detail considered; design-led polish"),
        ),
        applies_to="both",
    ),
    TasteDimension(
        key="family_fidelity",
        title="Aesthetic-family fidelity",
        question=(
            "Compared with the provided exemplar references for this page's aesthetic family, "
            "does it convincingly read as the SAME vernacular (e.g. Stripe-esque / Linear-esque "
            "/ Notion-esque / Framer-esque) — not just competent, but on-family?"
        ),
        anchors=(
            (2, "off-family; does not evoke the intended vernacular"),
            (5, "gestures at the family; recognisable but generic"),
            (8, "convincingly on-family; sits naturally beside the exemplars"),
        ),
        applies_to="both",
    ),
)


def build_sitespec_judge_prompt(
    dimensions: Sequence[TasteDimension] = SITESPEC_VISION_DIMENSIONS,
) -> str:
    """Build the marketing-page scoring prompt (reuses the taste-panel prompt builder).
    The `family_fidelity` dimension expects exemplar reference images to be supplied
    alongside the page image in the same judge call."""
    return build_judge_prompt(dimensions)
