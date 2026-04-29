#!/usr/bin/env python3
"""CSS clip-check — static detector for height-vs-line-box overflow.

For each CSS rule that declares ``height`` AND ``font-size`` AND
``line-height`` AND ``padding`` (in any form), compute:

    content_area = height - padding_top - padding_bottom
    line_box     = font_size * line_height_multiplier

When ``line_box > content_area + 0.5px`` the rule will clip descenders
on the rendered text. Browsers will not warn; the bug ships silently.

Pure stdlib — no tinycss2, no Playwright, no browser. Intentionally
single-rule-scoped (no cascade traversal): rules that declare height
+ font metrics in the same block are the only ones we can analyse
deterministically without false positives. Rules that inherit font
metrics from an ancestor are out of scope; they would require a real
DOM and a real layout engine.

Usage:
    python scripts/css_clip_check.py [css_root...]
    python scripts/css_clip_check.py --json [css_root...]

Exit codes:
    0 — no findings
    1 — at least one finding
    2 — usage / parse error
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

DEFAULT_CSS_ROOTS = [Path("src/dazzle_ui/runtime/static/css")]
TOLERANCE_PX = 0.5
REM_BASE_PX = 16.0
NORMAL_LINE_HEIGHT_MULTIPLIER = 1.2

# Selectors we never analyse — non-text-bearing chrome where height
# is intentionally decoupled from any inherited font metrics. Match is
# case-insensitive and substring-based on the trimmed selector.
SELECTOR_IGNORE_SUBSTRINGS = (
    "svg",
    "img",
    "iframe",
    "video",
    "canvas",
    "hr",
    "-icon",
    "-skeleton",
    "-spinner",
    "-bar",
    "-divider",
    "-stripe",
    "-dot",
    "-progress",
    "-handle",
    "-rail",
    "-track",
    "-thumb",
    "-resize",
    "-drag",
)

_RULE_RE = re.compile(r"([^{}]+?)\{([^{}]*)\}", re.DOTALL)
_COMMENT_RE = re.compile(r"/\*.*?\*/", re.DOTALL)
_DECL_RE = re.compile(r"([a-zA-Z-]+)\s*:\s*([^;]+?)(?:;|$)")
# Only px / rem dimensions — em/% need cascade context and we skip them.
_PX_RE = re.compile(r"(-?\d+(?:\.\d+)?)\s*px\b")
_REM_RE = re.compile(r"(-?\d+(?:\.\d+)?)\s*rem\b")
_NUMBER_RE = re.compile(r"^-?\d+(?:\.\d+)?$")


@dataclass(frozen=True)
class Finding:
    file: str
    line: int
    selector: str
    height_px: float
    padding_top_px: float
    padding_bottom_px: float
    content_area_px: float
    font_size_px: float
    line_height_multiplier: float
    line_box_px: float
    overflow_px: float

    def render(self) -> str:
        return (
            f"{self.file}:{self.line}  {self.selector}\n"
            f"    height={self.height_px:g}px "
            f"padding={self.padding_top_px:g}/{self.padding_bottom_px:g}px "
            f"font={self.font_size_px:g}px × {self.line_height_multiplier:g} = "
            f"{self.line_box_px:g}px line-box\n"
            f"    content-area={self.content_area_px:g}px → "
            f"overflow={self.overflow_px:g}px"
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "file": self.file,
            "line": self.line,
            "selector": self.selector,
            "height_px": self.height_px,
            "padding_top_px": self.padding_top_px,
            "padding_bottom_px": self.padding_bottom_px,
            "content_area_px": self.content_area_px,
            "font_size_px": self.font_size_px,
            "line_height_multiplier": self.line_height_multiplier,
            "line_box_px": self.line_box_px,
            "overflow_px": self.overflow_px,
        }


def _strip_comments(css: str) -> str:
    return _COMMENT_RE.sub("", css)


def _parse_dimension_px(value: str) -> float | None:
    """Return px dimension if value is unambiguously px or rem.

    Returns None for em/%/calc()/var()/auto/etc — we cannot compute
    those without a cascade or rendered font-size, and the
    framework-CI invariant we want is "rules whose self-contained
    declarations clip", not "rules that may clip in some context".
    """
    value = value.strip().lower()
    if value in ("0", "0px", "0rem"):
        return 0.0
    m = _PX_RE.search(value)
    if m:
        return float(m.group(1))
    m = _REM_RE.search(value)
    if m:
        return float(m.group(1)) * REM_BASE_PX
    return None


def _parse_padding_shorthand(value: str) -> tuple[float | None, float | None]:
    """Return (padding-top-px, padding-bottom-px) from a `padding:`
    shorthand. Either component returns None when the value uses a
    non-px/non-rem unit somewhere — we can't analyse safely.
    """
    parts = value.strip().split()
    px_parts: list[float | None] = [_parse_dimension_px(p) for p in parts]
    if any(p is None for p in px_parts):
        return None, None
    if len(px_parts) == 1:
        return px_parts[0], px_parts[0]
    if len(px_parts) == 2:
        return px_parts[0], px_parts[0]
    if len(px_parts) == 3:
        return px_parts[0], px_parts[2]
    if len(px_parts) >= 4:
        return px_parts[0], px_parts[2]
    return None, None


def _parse_line_height(value: str) -> float | None:
    """Return line-height as a font-size multiplier.

    Unitless numbers ARE the multiplier directly. ``normal`` resolves
    to 1.2 (browser-typical for most fonts). Pixel/rem absolute values
    are converted to a multiplier when paired with a known font-size
    by the caller.
    """
    value = value.strip().lower()
    if value == "normal":
        return NORMAL_LINE_HEIGHT_MULTIPLIER
    if _NUMBER_RE.match(value):
        return float(value)
    return None


def _selector_is_ignored(selector: str) -> bool:
    s = selector.lower()
    return any(token in s for token in SELECTOR_IGNORE_SUBSTRINGS)


def _line_of(css: str, offset: int) -> int:
    return css.count("\n", 0, offset) + 1


def _analyse_block(file: str, css: str, selector: str, body: str, line: int) -> list[Finding]:
    decls: dict[str, str] = {}
    for m in _DECL_RE.finditer(body):
        decls[m.group(1).strip().lower()] = m.group(2).strip()

    if "height" not in decls:
        return []
    height_px = _parse_dimension_px(decls["height"])
    if height_px is None or height_px <= 0:
        return []

    if "font-size" not in decls:
        return []
    font_size_px = _parse_dimension_px(decls["font-size"])
    if font_size_px is None or font_size_px <= 0:
        return []

    if "line-height" not in decls:
        return []
    raw_lh = decls["line-height"].strip().lower()
    line_height_mult = _parse_line_height(raw_lh)
    if line_height_mult is None:
        # Maybe absolute px/rem — convert via font-size.
        abs_lh = _parse_dimension_px(raw_lh)
        if abs_lh is None or abs_lh <= 0:
            return []
        line_height_mult = abs_lh / font_size_px

    pad_top: float | None
    pad_bottom: float | None
    if "padding" in decls:
        pad_top, pad_bottom = _parse_padding_shorthand(decls["padding"])
    else:
        pad_top = pad_bottom = 0.0

    if "padding-top" in decls:
        v = _parse_dimension_px(decls["padding-top"])
        if v is None:
            return []
        pad_top = v
    if "padding-bottom" in decls:
        v = _parse_dimension_px(decls["padding-bottom"])
        if v is None:
            return []
        pad_bottom = v
    if "padding-block" in decls:
        # Both top and bottom from a single value.
        v = _parse_dimension_px(decls["padding-block"])
        if v is None:
            return []
        pad_top = pad_bottom = v
    if "padding-block-start" in decls:
        v = _parse_dimension_px(decls["padding-block-start"])
        if v is None:
            return []
        pad_top = v
    if "padding-block-end" in decls:
        v = _parse_dimension_px(decls["padding-block-end"])
        if v is None:
            return []
        pad_bottom = v

    if pad_top is None or pad_bottom is None:
        return []

    findings: list[Finding] = []
    # Multi-selector rules: each comma-separated selector is its own
    # finding. Filter out ignored ones — but a rule with ANY text-
    # bearing selector still gets checked; we only suppress findings
    # for the chrome selectors.
    for raw_sel in selector.split(","):
        sel = raw_sel.strip()
        if not sel or _selector_is_ignored(sel):
            continue
        content_area = height_px - pad_top - pad_bottom
        line_box = font_size_px * line_height_mult
        overflow = line_box - content_area
        if overflow > TOLERANCE_PX:
            findings.append(
                Finding(
                    file=file,
                    line=line,
                    selector=sel,
                    height_px=height_px,
                    padding_top_px=pad_top,
                    padding_bottom_px=pad_bottom,
                    content_area_px=round(content_area, 3),
                    font_size_px=font_size_px,
                    line_height_multiplier=round(line_height_mult, 3),
                    line_box_px=round(line_box, 3),
                    overflow_px=round(overflow, 3),
                )
            )
    return findings


def scan_file(path: Path) -> list[Finding]:
    css = _strip_comments(path.read_text())
    findings: list[Finding] = []
    for m in _RULE_RE.finditer(css):
        selector = m.group(1).strip()
        body = m.group(2)
        if not selector or selector.startswith("@"):
            # @rules (media, keyframes, supports) need a recursive
            # parse; skip the wrapper itself, the inner rules are
            # picked up by re-running the rule regex over the body.
            for inner in _RULE_RE.finditer(body):
                inner_selector = inner.group(1).strip()
                if inner_selector.startswith("@"):
                    continue
                findings.extend(
                    _analyse_block(
                        str(path),
                        css,
                        inner_selector,
                        inner.group(2),
                        _line_of(css, inner.start()),
                    )
                )
            continue
        findings.extend(_analyse_block(str(path), css, selector, body, _line_of(css, m.start())))
    return findings


def scan_paths(roots: Iterable[Path]) -> list[Finding]:
    findings: list[Finding] = []
    for root in roots:
        if not root.exists():
            continue
        if root.is_file() and root.suffix == ".css":
            findings.extend(scan_file(root))
            continue
        for css_file in sorted(root.rglob("*.css")):
            findings.extend(scan_file(css_file))
    return findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("paths", nargs="*", type=Path)
    parser.add_argument(
        "--json", action="store_true", help="Emit findings as JSON for CI consumption"
    )
    parser.add_argument(
        "--max-findings",
        type=int,
        default=0,
        help="Pass when total findings ≤ N (used for staged adoption)",
    )
    args = parser.parse_args(argv)
    roots = args.paths or DEFAULT_CSS_ROOTS

    findings = scan_paths(roots)

    if args.json:
        json.dump([f.to_dict() for f in findings], sys.stdout, indent=2)
        sys.stdout.write("\n")
    else:
        for finding in findings:
            print(finding.render())
        if not findings:
            print("css_clip_check: 0 findings ✓")
        else:
            print(f"\ncss_clip_check: {len(findings)} finding(s)")

    if len(findings) > args.max_findings:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
