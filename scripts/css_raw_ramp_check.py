#!/usr/bin/env python3
"""CSS raw-ramp check — surface raw colour-ramp tokens leaking
into component-level CSS (#942 cycle 1e).

The Dazzle design system splits colour tokens into two families:

- **Raw ramps** — ``--neutral-50`` through ``--neutral-950``,
  ``--brand-50`` through ``--brand-950``, ``--success-500``, etc.
  These are LIGHT-ONLY values; they don't change under
  ``[data-theme="dark"]``.
- **Semantic tokens** — ``--colour-bg``, ``--colour-surface``,
  ``--colour-text``, ``--colour-border``, ``--colour-brand``,
  ``--colour-success``, etc. Built FROM the ramps via
  ``light-dark()`` so they flip correctly when the theme toggles.

The contract for ``components/*.css`` is **semantic tokens only**.
Using a raw ramp value as a background, foreground, or border
colour leaves a panel that doesn't adapt to dark mode — exactly the
class of bug ``pdf-viewer.css`` shipped briefly in v0.61.115 and
v0.61.116 before the cycle 1d gates caught it.

This linter runs as a unit test and fails on any new raw-ramp
usage. The token files themselves (``tokens.css``,
``design-system.css``, plus ``themes/*.css``) are exempt — they
DEFINE the semantic tokens in terms of ramps. Component CSS lives
strictly downstream.

Usage::

    python scripts/css_raw_ramp_check.py
    python scripts/css_raw_ramp_check.py --json

Exit codes:
    0 — no findings
    1 — at least one finding
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

# CSS roots scanned by default. Token files + theme overrides are
# the legitimate places to reference raw ramps; components are not.
COMPONENT_CSS_ROOT = Path("src/dazzle_ui/runtime/static/css/components")

# Files that may legitimately reference raw ramps (they BUILD the
# semantic tokens from ramps, or are theme overrides binding the
# semantic family to ramp values for a specific brand).
EXEMPT_FILES = frozenset(
    {
        "tokens.css",
        "design-system.css",
        # site-sections.css contains `[data-theme="dark"]` bindings
        # that legitimately reference ramps inside theme-scoped
        # rules. The lint understands theme-scoped exemption (see
        # `_in_theme_scope`) so the file itself isn't a hard exempt.
    }
)

# Raw-ramp token families. Brand / success / warning / danger
# *can* technically be used directly (they're brand-fixed; they
# don't need to flip under dark mode), but using the
# ``--colour-brand`` semantic token is still preferred — it's the
# one a project theme override can rebind without touching every
# component file. Flag all five families and let ad-hoc cases land
# in the per-component allowlist if they're load-bearing.
_RAW_RAMP_FAMILIES = ("neutral", "brand", "success", "warning", "danger")
_RAW_RAMP_RE = re.compile(r"var\(--(?:" + "|".join(_RAW_RAMP_FAMILIES) + r")-(\d+|[a-z-]+)\)")
_COMMENT_RE = re.compile(r"/\*.*?\*/", re.DOTALL)
_THEME_BLOCK_RE = re.compile(
    r"\[data-theme\s*=\s*['\"]dark['\"]\]\s*[a-zA-Z\.\-_:#\(\)\[\],\s>+~\*]*\{"
    r"|@media\s*\(\s*prefers-color-scheme\s*:\s*dark\s*\)\s*\{"
)


@dataclass(frozen=True)
class Finding:
    file: str
    line: int
    snippet: str
    ramp: str

    def render(self) -> str:
        return (
            f"{self.file}:{self.line}\n"
            f"    raw ramp: var(--{self.ramp})\n"
            f"    in: {self.snippet}\n"
            f"    fix: replace with a --colour-* semantic token "
            f"(see tokens.css)"
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "file": self.file,
            "line": self.line,
            "snippet": self.snippet,
            "ramp": self.ramp,
        }


def _strip_comments(css: str) -> str:
    return _COMMENT_RE.sub("", css)


def _line_of(css: str, offset: int) -> int:
    return css.count("\n", 0, offset) + 1


def _in_theme_scope(css: str, offset: int) -> bool:
    """Whether the byte at ``offset`` falls inside a theme-scoped
    rule block — `[data-theme="dark"] { … }` or
    ``@media (prefers-color-scheme: dark) { … }``. Those blocks are
    legitimately allowed to reference raw ramps (they ARE the
    dark-mode override).

    Implemented as a simple brace counter: walk every theme-block
    opener up to ``offset``, find its matching close, and check
    whether ``offset`` falls inside.
    """
    pos = 0
    while True:
        m = _THEME_BLOCK_RE.search(css, pos)
        if not m or m.start() > offset:
            return False
        # Find the matching close brace.
        depth = 1
        i = m.end()
        while i < len(css) and depth > 0:
            if css[i] == "{":
                depth += 1
            elif css[i] == "}":
                depth -= 1
            i += 1
        if m.end() <= offset < i:
            return True
        pos = i


def scan_file(path: Path) -> list[Finding]:
    if path.name in EXEMPT_FILES:
        return []
    css = _strip_comments(path.read_text())
    findings: list[Finding] = []
    for m in _RAW_RAMP_RE.finditer(css):
        if _in_theme_scope(css, m.start()):
            continue
        line = _line_of(css, m.start())
        # Snippet: the line containing the match (trimmed).
        line_start = css.rfind("\n", 0, m.start()) + 1
        line_end = css.find("\n", m.end())
        if line_end == -1:
            line_end = len(css)
        snippet = css[line_start:line_end].strip()
        findings.append(
            Finding(
                file=str(path),
                line=line,
                snippet=snippet,
                ramp=m.group(0)[len("var(--") : -1],
            )
        )
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
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    roots = args.paths or [COMPONENT_CSS_ROOT]
    findings = scan_paths(roots)

    if args.json:
        json.dump([f.to_dict() for f in findings], sys.stdout, indent=2)
        sys.stdout.write("\n")
    else:
        for finding in findings:
            print(finding.render())
        if not findings:
            print("css_raw_ramp_check: 0 findings ✓")
        else:
            print(f"\ncss_raw_ramp_check: {len(findings)} finding(s)")

    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
