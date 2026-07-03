"""WCAG contrast gate over the token sheet (HaTchi-MaXchi TASTE-11).

Pure function of ``tokens.css``: parses the custom properties, resolves
``var()`` / ``light-dark()`` / relative ``oklch(from …)`` forms, converts
OKLCH to linear sRGB, and asserts WCAG ratios for the semantic pairs that
carry text. Closes the named gap from the taste spec: no machine contrast
gate existed before Phase 2.
"""

import math
import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.gate

TOKENS_CSS = Path(__file__).parents[2] / "packages" / "hatchi-maxchi" / "tokens" / "tokens.css"

_DECL = re.compile(r"(--[a-z0-9-]+)\s*:\s*([^;]+);")


def _parse_tokens() -> dict[str, str]:
    return {m.group(1): m.group(2).strip() for m in _DECL.finditer(TOKENS_CSS.read_text())}


def _resolve(tokens: dict[str, str], value: str, theme: str) -> str:
    """Resolve var()/light-dark() chains down to a colour literal."""
    for _ in range(12):
        value = value.strip()
        ld = re.match(r"light-dark\(\s*(.*)\s*\)$", value, re.DOTALL)
        if ld:
            parts = _split_top_level(ld.group(1))
            assert len(parts) == 2, value
            value = parts[0] if theme == "light" else parts[1]
            continue
        var = re.match(r"var\((--[a-z0-9-]+)\)$", value)
        if var:
            value = tokens[var.group(1)]
            continue
        return value
    raise AssertionError(f"resolution did not converge: {value}")


def _split_top_level(s: str) -> list[str]:
    parts, depth, cur = [], 0, []
    for ch in s:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if ch == "," and depth == 0:
            parts.append("".join(cur).strip())
            cur = []
        else:
            cur.append(ch)
    parts.append("".join(cur).strip())
    return parts


_OKLCH = re.compile(
    r"oklch\(\s*([\d.]+)%\s+([\d.]+)\s+([\d.]+)\s*\)$",
)
_OKLCH_FROM = re.compile(
    r"oklch\(from\s+(.+?)\s+([\d.]+)%\s+([\d.]+)\s+h\s*\)$",
)


def _oklch_components(tokens: dict[str, str], value: str, theme: str) -> tuple[float, float, float]:
    value = _resolve(tokens, value, theme)
    if value == "white":
        return (1.0, 0.0, 0.0)
    if value == "black":
        return (0.0, 0.0, 0.0)
    m = _OKLCH.match(value)
    if m:
        return (float(m.group(1)) / 100.0, float(m.group(2)), float(m.group(3)))
    m = _OKLCH_FROM.match(value)
    if m:
        # relative form: take hue from the base colour, L/C literal
        _, _, base_h = _oklch_components(tokens, m.group(1), theme)
        return (float(m.group(2)) / 100.0, float(m.group(3)), base_h)
    raise AssertionError(f"unparsed colour literal: {value!r}")


def _luminance(lch: tuple[float, float, float]) -> float:
    """OKLCH → linear sRGB → WCAG relative luminance."""
    lum, chroma, hue_deg = lch
    hue = math.radians(hue_deg)
    a = chroma * math.cos(hue)
    b = chroma * math.sin(hue)
    l_ = lum + 0.3963377774 * a + 0.2158037573 * b
    m_ = lum - 0.1055613458 * a - 0.0638541728 * b
    s_ = lum - 0.0894841775 * a - 1.2914855480 * b
    l3, m3, s3 = l_**3, m_**3, s_**3
    r = +4.0767416621 * l3 - 3.3077115913 * m3 + 0.2309699292 * s3
    g = -1.2684380046 * l3 + 2.6097574011 * m3 - 0.3413193965 * s3
    bb = -0.0041960863 * l3 - 0.7034186147 * m3 + 1.7076147010 * s3
    r, g, bb = (min(1.0, max(0.0, ch)) for ch in (r, g, bb))
    return 0.2126 * r + 0.7152 * g + 0.0722 * bb


def _contrast(tokens: dict[str, str], fg: str, bg: str, theme: str) -> float:
    y1 = _luminance(_oklch_components(tokens, tokens[fg], theme))
    y2 = _luminance(_oklch_components(tokens, tokens[bg], theme))
    lighter, darker = max(y1, y2), min(y1, y2)
    return (lighter + 0.05) / (darker + 0.05)


# (foreground, background, minimum ratio) — AA text 4.5:1; large/secondary 3:1.
PAIRS: list[tuple[str, str, float]] = [
    ("--colour-text", "--colour-bg", 4.5),
    ("--colour-text", "--colour-surface", 4.5),
    ("--colour-text-muted", "--colour-bg", 4.5),
    ("--colour-text-muted", "--colour-surface", 4.5),
    ("--colour-brand-contrast", "--colour-brand", 4.5),
    # semantic tone text on its soft wash (badges/alerts, light theme wash)
    ("--colour-danger", "--colour-danger-soft", 3.0),
    ("--colour-success", "--colour-success-soft", 3.0),
    ("--colour-warning", "--colour-warning-soft", 3.0),
    # borders only need non-text 3:1 against surface? Borders are decorative —
    # skip. Focus ring is alpha-composited — covered by axe at e2e time.
]


@pytest.mark.parametrize("theme", ["light", "dark"])
@pytest.mark.parametrize(("fg", "bg", "minimum"), PAIRS)
def test_semantic_pair_meets_wcag(theme: str, fg: str, bg: str, minimum: float) -> None:
    tokens = _parse_tokens()
    ratio = _contrast(tokens, fg, bg, theme)
    assert ratio >= minimum, (
        f"{fg} on {bg} [{theme}] = {ratio:.2f}:1, needs {minimum}:1 — "
        "recalibrate the ramp step in tokens.css (TASTE-7/11)"
    )
