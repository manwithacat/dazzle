"""Sitespec aesthetic-hygiene rubric — the DETERMINISTIC floor for Goal 2.

Goal 2 measures whether the marketing/sitespec pages read as "consistent with
modern industry-norm trends" two ways (James, 2026-07-09):

1. a **deterministic rubric floor** (this module) — structural properties of the
   HM sitespec CSS system that a competent modern landing page exhibits. No
   browser, no external assets, fleet-independent: it scores the *design system*
   (`packages/hatchi-maxchi/components/sitespec.css`), which Phase 2B uplifts.
2. a reference-anchored LLM-vision "modernity score" (Phase 2A-ii) — the holistic
   "does a web dev recognise this as modern" judgment, scored against real
   exemplar screenshots per aesthetic family.

This module is (1). Each dimension returns a 0.0–1.0 sub-score with a human
detail; the weighted total is 0–100. It is intentionally a *hygiene floor*, not
the whole judgment — it catches gross modernity failures (ad-hoc type instead of
a scale, no fluid type, no responsive breakpoints, cramped rhythm), leaving the
holistic "feel" to the vision score.

The current (post-1B faithful-port) baseline scores modestly — ad-hoc font sizes
+ zero `clamp()` fluid type — which is the honest "before" for 2B.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass

__all__ = [
    "SITESPEC_HYGIENE_DIMENSIONS",
    "HygieneDimension",
    "hm_sitespec_css",
    "score_sitespec_css",
]

# --- individual deterministic checks (css text -> (0..1 score, detail)) --------


def _score_responsive(css: str) -> tuple[float, str]:
    """Modern landing pages stack/reflow on mobile — they carry responsive
    breakpoints. Full marks at >=3 `@media` blocks."""
    n = len(re.findall(r"@media\b", css))
    return (min(n / 3.0, 1.0), f"{n} @media breakpoints (>=3 = full)")


def _score_section_rhythm(css: str) -> tuple[float, str]:
    """Sections share a vertical-rhythm spacing token rather than ad-hoc margins.
    Full marks when the section/hero spacing tokens are used >=8 times."""
    n = len(re.findall(r"--dz-spacing-(?:section|hero)-y", css))
    return (min(n / 8.0, 1.0), f"{n} section/hero rhythm-token uses (>=8 = full)")


def _score_container(css: str) -> tuple[float, str]:
    """Readable line length / centered content — content is width-constrained.
    Full marks at >=6 `max-width` constraints."""
    n = len(re.findall(r"\bmax-width\s*:", css))
    return (min(n / 6.0, 1.0), f"{n} max-width containers (>=6 = full)")


_FONT_SIZE_RE = re.compile(r"font-size\s*:\s*([^;}\n]+)")


def _score_type_system(css: str) -> tuple[float, str]:
    """Type comes from a SYSTEM, not hand-picked pixels. Modern practice: heading
    sizes reference scale tokens (`var(--...)`) rather than a spray of hardcoded
    rem values. Score = fraction of font-size declarations that are token-driven."""
    values = [v.strip() for v in _FONT_SIZE_RE.findall(css)]
    if not values:
        return (0.0, "no font-size declarations found")
    tokened = sum(1 for v in values if "var(" in v)
    frac = tokened / len(values)
    hardcoded = len(values) - tokened
    return (frac, f"{tokened}/{len(values)} font-sizes token-driven; {hardcoded} hardcoded")


def _score_fluid_type(css: str) -> tuple[float, str]:
    """Modern display/hero type scales fluidly with the viewport — no hard jumps at
    breakpoints. That's true whether the fluidity is inline (`font-size: clamp(...)`)
    OR carried by a reference to HM's fluid `--text-*` scale, whose every step is
    clamp-defined. We measure the actual property (does the type scale fluidly),
    not a specific syntax: score = fraction of font-size declarations that are fluid."""
    sizes = [v.strip() for v in _FONT_SIZE_RE.findall(css)]
    if not sizes:
        return (0.0, "no font-size declarations found")
    fluid = sum(1 for v in sizes if "clamp(" in v or "var(--text-" in v)
    frac = fluid / len(sizes)
    return (frac, f"{fluid}/{len(sizes)} font-sizes fluid (inline clamp or --text-* scale)")


def _score_motion(css: str) -> tuple[float, str]:
    """Subtle, consistent motion (token-driven transitions) reads as considered.
    Full marks at >=6 transition-token uses."""
    n = len(re.findall(r"--dz-transition|transition\s*:", css))
    return (min(n / 6.0, 1.0), f"{n} transition uses (>=6 = full)")


@dataclass(frozen=True)
class HygieneDimension:
    """One deterministic sitespec-hygiene dimension."""

    key: str
    weight: int  # contribution to the /100 total
    description: str
    check: Callable[[str], tuple[float, str]]


# Weights sum to 100. Type system + fluid type are weighted highest because they
# are the clearest modernity signals and the current baseline's weakest points.
SITESPEC_HYGIENE_DIMENSIONS: tuple[HygieneDimension, ...] = (
    HygieneDimension(
        "type_system", 25, "Type from scale tokens, not hardcoded rem", _score_type_system
    ),
    HygieneDimension("fluid_type", 20, "Display type scales fluidly (clamp)", _score_fluid_type),
    HygieneDimension("responsive", 15, "Responsive breakpoints (mobile reflow)", _score_responsive),
    HygieneDimension(
        "section_rhythm", 15, "Consistent section vertical rhythm token", _score_section_rhythm
    ),
    HygieneDimension("container", 15, "Width-constrained readable content", _score_container),
    HygieneDimension("motion", 10, "Token-driven, consistent motion", _score_motion),
)


def hm_sitespec_css() -> str:
    """Read the HM sitespec component CSS (the design system under measurement)."""
    from pathlib import Path

    root = Path(__file__).resolve().parents[3]
    return (root / "packages" / "hatchi-maxchi" / "components" / "sitespec.css").read_text(
        encoding="utf-8"
    )


def score_sitespec_css(css: str) -> dict[str, object]:
    """Score sitespec CSS against the hygiene rubric. Returns the weighted /100
    total plus a per-dimension breakdown (sub-score, weighted points, detail)."""
    breakdown: dict[str, dict[str, object]] = {}
    total = 0.0
    for d in SITESPEC_HYGIENE_DIMENSIONS:
        sub, detail = d.check(css)
        sub = max(0.0, min(1.0, sub))
        pts = sub * d.weight
        total += pts
        breakdown[d.key] = {
            "sub_score": round(sub, 3),
            "weight": d.weight,
            "points": round(pts, 1),
            "detail": detail,
        }
    return {"total": round(total, 1), "breakdown": breakdown}
