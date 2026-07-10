"""Deterministic per-component token-discipline rubric (#1567).

The LIVE half of the Hyperpart taste-gate: a cheap, render-free, DB-free score of
whether an HM component (`packages/hatchi-maxchi/components/*.css`) delegates to the
house token system rather than spraying raw values. It is the deterministic
app-internals rubric that `core/design_context.py`'s matrix flagged as its one empty
cell (#1566) — registered there as the 4th rubric.

Mirrors `core/sitespec_hygiene.py`: each dimension is a pure `str -> (0..1, detail)`
check; the weighted total is 0-100. Absence of a property class (a pure-layout
component with no colour declarations) scores that dimension 1.0 ("n/a") — absence is
not a violation.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

__all__ = [
    "COMPONENT_HYGIENE_DIMENSIONS",
    "PAGE_CHROME_EXEMPT",
    "ComponentDimension",
    "hm_component_paths",
    "score_component_css",
]

# Files that are page-level chrome / overlays rather than card/widget Hyperparts, so
# the component token-discipline floor (which assumes a component's selectors + values)
# does not fit them. Kept tiny and explicit — each entry is a deliberate, documented
# exemption, not a way to dodge the gate.
#   - transitions.css: page-level toast/view-transition/<dialog>-backdrop/body-state
#     helpers. Its own docstring documents the intentional literals (the scrim, a few
#     durations) and it targets page/pseudo/body selectors, not `.dz-` component classes.
PAGE_CHROME_EXEMPT: frozenset[str] = frozenset({"transitions.css"})

_COMMENT_RE = re.compile(r"/\*.*?\*/", re.S)


def _strip_comments(css: str) -> str:
    """Drop CSS comments so literals/selectors inside prose (e.g. `dz.css` in a
    docstring) don't register as declarations."""
    return _COMMENT_RE.sub("", css)


_RAW_COLOUR = r"#[0-9a-fA-F]{3,8}\b|rgba?\(|hsla?\("

_COLOUR_DECL_RE = re.compile(
    r"(?:color|background|background-color|border-color|outline-color|fill|stroke)\s*:\s*([^;{}]+)",
    re.I,
)


def _score_colour_tokens(css: str) -> tuple[float, str]:
    """Colours come from `var(--…)` tokens, not raw hex/rgb/hsl. Score = fraction of
    colour-bearing declarations that are token-driven (var, no raw literal)."""
    vals = [v.strip() for v in _COLOUR_DECL_RE.findall(css)]
    coloured = [v for v in vals if re.search(rf"var\(--|{_RAW_COLOUR}", v)]
    if not coloured:
        return (1.0, "no literal colour declarations (n/a)")
    # A declaration is token-driven if it references any `var(--…)` token — a hex/rgb
    # *fallback* inside that var() is legitimate (`var(--dz-x, #fallback)`), so only a
    # raw literal with NO var() reference counts against discipline.
    tok = sum(1 for v in coloured if "var(--" in v)
    raw = len(coloured) - tok
    return (tok / len(coloured), f"{tok}/{len(coloured)} colour decls token-driven; {raw} raw")


def _score_namespace(css: str) -> tuple[float, str]:
    """Selectors use the `.dz-` namespace (HM convention). Score = fraction of class
    selectors that are `.dz-`-prefixed."""
    classes = re.findall(r"\.([a-zA-Z][\w-]*)", css)
    if not classes:
        return (1.0, "no class selectors (n/a)")
    dz = sum(1 for c in classes if c.startswith("dz-"))
    return (dz / len(classes), f"{dz}/{len(classes)} class selectors .dz-namespaced")


_MOTION_DECL_RE = re.compile(r"(?:transition|animation)(?:-[a-z]+)?\s*:\s*([^;{}]+)", re.I)


def _score_motion_tokens(css: str) -> tuple[float, str]:
    """Motion timing comes from `var(--dz-transition…)` tokens, not inline durations.
    Score = fraction of transition/animation declarations referencing a var() token."""
    vals = [v.strip() for v in _MOTION_DECL_RE.findall(css)]
    if not vals:
        return (1.0, "no transition/animation declarations (n/a)")
    tok = sum(1 for v in vals if "var(" in v)
    return (tok / len(vals), f"{tok}/{len(vals)} motion decls token-driven")


_SIZE_DECL_RE = re.compile(
    r"(?:border-radius|padding|margin|gap|row-gap|column-gap)(?:-[a-z]+)?\s*:\s*([^;{}]+)",
    re.I,
)
_PX_RE = re.compile(r"\d*\.?\d+px\b")


def _score_sizing_tokens(css: str) -> tuple[float, str]:
    """Radius/spacing come from tokens or rem/em, not raw px. Score = fraction of
    sized radius/spacing declarations that are px-free."""
    vals = [v.strip() for v in _SIZE_DECL_RE.findall(css)]
    sized = [v for v in vals if re.search(r"var\(--|\d", v)]
    if not sized:
        return (1.0, "no sized spacing/radius declarations (n/a)")
    good = sum(1 for v in sized if not _PX_RE.search(v))
    px = len(sized) - good
    return (good / len(sized), f"{good}/{len(sized)} sizing decls px-free; {px} use px")


@dataclass(frozen=True)
class ComponentDimension:
    """One deterministic component token-discipline dimension."""

    key: str
    weight: int  # contribution to the /100 total
    description: str
    check: Callable[[str], tuple[float, str]]


# Weights sum to 100. Colour discipline is weighted highest — it is the clearest and
# most-varying token-discipline signal across the corpus.
COMPONENT_HYGIENE_DIMENSIONS: tuple[ComponentDimension, ...] = (
    ComponentDimension(
        "colour_tokens", 40, "Colours from var(--…) tokens, not raw hex/rgb", _score_colour_tokens
    ),
    ComponentDimension("namespace", 20, "Selectors use the .dz- namespace", _score_namespace),
    ComponentDimension(
        "motion_tokens", 20, "Motion timing from --dz-transition tokens", _score_motion_tokens
    ),
    ComponentDimension(
        "sizing_tokens", 20, "Radius/spacing from tokens or rem, not raw px", _score_sizing_tokens
    ),
)


def hm_component_paths() -> list[Path]:
    """The HM component CSS files under measurement, sorted by name."""
    root = Path(__file__).resolve().parents[3]
    comp_dir = root / "packages" / "hatchi-maxchi" / "components"
    return sorted(comp_dir.glob("*.css"))


def score_component_css(css: str) -> dict[str, object]:
    """Score one component's CSS against the token-discipline rubric. Returns the
    weighted /100 total plus a per-dimension breakdown (sub-score, points, detail)."""
    css = _strip_comments(css)
    breakdown: dict[str, dict[str, object]] = {}
    total = 0.0
    for d in COMPONENT_HYGIENE_DIMENSIONS:
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
