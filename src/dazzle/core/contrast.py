"""WCAG 2.x contrast math for Dazzle's theme systems (#1567 slice 2).

One pure module, two consumers/vocabularies:
- HM aesthetic families (``packages/hatchi-maxchi/families/*.css``, HSL triplets
  like ``"220 30% 15%"``) — gated by ``tests/unit/test_family_contrast.py``.
- The parametric ThemeSpec palette (``core.oklch.generate_palette`` output,
  ``oklch()`` strings) — gated inside ``validate_themespec``.

Pairs a token map doesn't define (or values that aren't plain colours) are
SKIPPED — absence is not a violation, mirroring the slice-1 n/a stance.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass

__all__ = [
    "FAMILY_PAIRS",
    "THEMESPEC_PAIRS",
    "ContrastPair",
    "check_pairs",
    "contrast_ratio",
    "parse_css_color",
    "parse_family_modes",
    "relative_luminance",
]

RGB = tuple[float, float, float]

# --- colour parsing --------------------------------------------------------

_HSL_TRIPLET_RE = re.compile(r"^\s*([\d.]+)\s+([\d.]+)%\s+([\d.]+)%\s*$")
_HSL_FUNC_RE = re.compile(r"^\s*hsla?\(\s*([\d.]+)[,\s]+([\d.]+)%[,\s]+([\d.]+)%")
_OKLCH_RE = re.compile(r"^\s*oklch\(\s*([\d.]+)\s+([\d.]+)\s+([\d.]+)")
_HEX_RE = re.compile(r"^\s*#([0-9a-fA-F]{3}|[0-9a-fA-F]{6})\s*$")


def _hsl_to_rgb(h: float, s: float, lightness: float) -> RGB:
    s /= 100.0
    lightness /= 100.0
    c = (1 - abs(2 * lightness - 1)) * s
    hp = (h % 360.0) / 60.0
    x = c * (1 - abs(hp % 2 - 1))
    if hp < 1:
        r, g, b = c, x, 0.0
    elif hp < 2:
        r, g, b = x, c, 0.0
    elif hp < 3:
        r, g, b = 0.0, c, x
    elif hp < 4:
        r, g, b = 0.0, x, c
    elif hp < 5:
        r, g, b = x, 0.0, c
    else:
        r, g, b = c, 0.0, x
    m = lightness - c / 2
    return (r + m, g + m, b + m)


def _oklch_to_rgb(lightness: float, chroma: float, hue: float) -> RGB:
    """OKLCH -> OKLab -> LMS -> linear sRGB -> sRGB (clamped)."""
    h_rad = math.radians(hue)
    a, b = chroma * math.cos(h_rad), chroma * math.sin(h_rad)
    l_ = lightness + 0.3963377774 * a + 0.2158037573 * b
    m_ = lightness - 0.1055613458 * a - 0.0638541728 * b
    s_ = lightness - 0.0894841775 * a - 1.2914855480 * b
    l3, m3, s3 = l_**3, m_**3, s_**3
    lin = (
        +4.0767416621 * l3 - 3.3077115913 * m3 + 0.2309699292 * s3,
        -1.2684380046 * l3 + 2.6097574011 * m3 - 0.3413193965 * s3,
        -0.0041960863 * l3 - 0.7034186147 * m3 + 1.7076147010 * s3,
    )

    def to_srgb(u: float) -> float:
        u = min(1.0, max(0.0, u))
        return 12.92 * u if u <= 0.0031308 else 1.055 * u ** (1 / 2.4) - 0.055

    return (to_srgb(lin[0]), to_srgb(lin[1]), to_srgb(lin[2]))


def parse_css_color(value: str) -> RGB | None:
    """Parse a plain colour value to sRGB (0..1); None for non-colours."""
    m = _HEX_RE.match(value)
    if m:
        hx = m.group(1)
        if len(hx) == 3:
            hx = "".join(ch * 2 for ch in hx)
        return (
            int(hx[0:2], 16) / 255.0,
            int(hx[2:4], 16) / 255.0,
            int(hx[4:6], 16) / 255.0,
        )
    m = _OKLCH_RE.match(value)
    if m:
        return _oklch_to_rgb(float(m.group(1)), float(m.group(2)), float(m.group(3)))
    m = _HSL_FUNC_RE.match(value) or _HSL_TRIPLET_RE.match(value)
    if m:
        return _hsl_to_rgb(float(m.group(1)), float(m.group(2)), float(m.group(3)))
    return None


# --- WCAG maths -------------------------------------------------------------


def relative_luminance(rgb: RGB) -> float:
    """WCAG 2.x relative luminance of an sRGB colour (components 0..1)."""

    def lin(c: float) -> float:
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = (lin(c) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_ratio(a: RGB, b: RGB) -> float:
    """WCAG 2.x contrast ratio between two sRGB colours (>= 1.0, symmetric)."""
    la, lb = relative_luminance(a), relative_luminance(b)
    lighter, darker = max(la, lb), min(la, lb)
    return (lighter + 0.05) / (darker + 0.05)


# --- pair tables -------------------------------------------------------------


@dataclass(frozen=True)
class ContrastPair:
    """One fg/bg token pair with its WCAG minimum."""

    fg: str
    bg: str
    minimum: float  # 4.5 text, 3.0 UI
    kind: str  # "text" | "ui"


FAMILY_PAIRS: tuple[ContrastPair, ...] = (
    ContrastPair("foreground", "background", 4.5, "text"),
    ContrastPair("card-foreground", "card", 4.5, "text"),
    ContrastPair("popover-foreground", "popover", 4.5, "text"),
    ContrastPair("primary-foreground", "primary", 4.5, "text"),
    ContrastPair("secondary-foreground", "secondary", 4.5, "text"),
    ContrastPair("muted-foreground", "background", 4.5, "text"),
    ContrastPair("destructive-foreground", "destructive", 4.5, "text"),
    ContrastPair("accent-foreground", "accent", 4.5, "text"),
)

THEMESPEC_PAIRS: tuple[ContrastPair, ...] = (
    ContrastPair("text-primary", "bg-primary", 4.5, "text"),
    ContrastPair("text-primary", "bg-secondary", 4.5, "text"),
    ContrastPair("text-secondary", "bg-primary", 4.5, "text"),
    ContrastPair("success-text", "success-bg", 4.5, "text"),
    ContrastPair("warning-text", "warning-bg", 4.5, "text"),
    ContrastPair("danger-text", "danger-bg", 4.5, "text"),
    ContrastPair("info-text", "info-bg", 4.5, "text"),
)


def check_pairs(tokens: dict[str, str], pairs: tuple[ContrastPair, ...]) -> list[str]:
    """Return failure strings for pairs below their minimum; skip absent/unparseable."""
    failures: list[str] = []
    for p in pairs:
        fg_v, bg_v = tokens.get(p.fg), tokens.get(p.bg)
        if fg_v is None or bg_v is None:
            continue
        fg, bg = parse_css_color(fg_v), parse_css_color(bg_v)
        if fg is None or bg is None:
            continue
        ratio = contrast_ratio(fg, bg)
        if ratio < p.minimum:
            failures.append(f"{p.fg}/{p.bg} {ratio:.2f}:1 < {p.minimum}:1")
    return failures


# --- HM family CSS parsing ----------------------------------------------------

_TOKEN_DECL_RE = re.compile(r"--([a-z][\w-]*)\s*:\s*([^;]+);")
_COMMENT_RE = re.compile(r"/\*.*?\*/", re.S)


def parse_family_modes(css: str) -> dict[str, dict[str, str]]:
    """Extract {mode: {token: value}} from a family CSS file's
    ``[data-theme="light"|"dark"]`` blocks (brace-matched)."""
    css = _COMMENT_RE.sub("", css)
    modes: dict[str, dict[str, str]] = {}
    for mode in ("light", "dark"):
        marker = f'[data-theme="{mode}"]'
        idx = css.find(marker)
        if idx == -1:
            continue
        open_idx = css.index("{", idx)
        depth, end = 1, open_idx + 1
        while end < len(css) and depth:
            if css[end] == "{":
                depth += 1
            elif css[end] == "}":
                depth -= 1
            end += 1
        body = css[open_idx + 1 : end - 1]
        modes[mode] = {m.group(1): m.group(2).strip() for m in _TOKEN_DECL_RE.finditer(body)}
    return modes
