#!/usr/bin/env python3
"""HM zero-floor: no Tailwind utilities in emitters, no Dazzle-native design CSS.

The 2026-07 HM-convergence **drain campaign is complete** (grand total 0).
This script remains as:

1. A **CI zero-floor** helper (``tests/unit/test_hm_tailwind_reservoir.py``).
2. A human/CLI diagnostic when the floor goes red.

It is **not** a shrink-over-cycle migration thermometer anymore. CSS
boundary ownership lives in ``tests/unit/test_hm_delegation_proof.py``
(exact allowlist of every served Dazzle-native stylesheet). This script
covers what the allowlist does not: Tailwind-shaped tokens in
``class="…"`` literals under ``src/dazzle/render`` + ``src/dazzle/page``.

Method — precision over recall: extract the LITERAL value of every
``class="…"`` attribute and classify each token. Scoping to class
attributes (not raw line grep) kills false hits from CSS-property
strings, comments, and substrings. A token is Tailwind iff it carries a
responsive/state prefix or matches a known utility shape, and is NOT a
``dz-*`` semantic class (HM-aligned target vocabulary).

Usage:
    python scripts/hm_tailwind_reservoir.py         # human summary (exit 1 if floor red)
    python scripts/hm_tailwind_reservoir.py --json  # machine-readable (exit 1 if floor red)
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

ROOTS = ("src/dazzle/render", "src/dazzle/page")

# Literal class-attribute values (skip pure f-expr `class="{…}"`, which carry
# no literal tokens). Captures the literal portion of mixed values too.
_CLASS_ATTR_RE = re.compile(r'class="([^"]*)"')

# Responsive + state prefixes that are unambiguously Tailwind.
_PREFIX_RE = re.compile(
    r"^(sm|md|lg|xl|2xl|hover|focus|focus-within|active|disabled|group-hover"
    r"|group-focus|peer-hover|peer-focus|motion-safe|motion-reduce):"
)

# Utility shapes (no prefix) that are unambiguously Tailwind, not semantic dz-*.
_UTILITY_RES = tuple(
    re.compile(p)
    for p in (
        r"^(p|m)[xytrbl]?-\d",  # padding/margin scale
        r"^space-[xy]-\d",
        r"^gap-\d",
        r"^grid-cols-\d",
        r"^col-span-\d",
        r"^row-span-\d",
        r"^w-\d+$",  # exact — excludes dz skeleton fractional widths (w-3-4, w-5-6)
        r"^h-\d+$",
        r"^min-w-",
        r"^max-w-",
        r"^text-(xs|sm|base|lg|xl|\dxl)$",
        r"^font-(thin|light|normal|medium|semibold|bold|extrabold)$",
        r"^leading-",
        r"^tracking-",
        r"^rounded(-|$)",
        r"^opacity-\d",
        r"^shadow(-|$)",
        r"^(bg|text|border|ring)-\[",  # arbitrary values e.g. bg-[hsl(var(--card))]
        r"^border(-\d|$)",
        r"^inline-flex$",
        r"^items-(center|start|end|baseline|stretch)$",
        r"^justify-(center|between|around|evenly|start|end)$",
    )
)


def is_tailwind_token(tok: str) -> bool:
    if not tok or tok.startswith("dz-"):
        return False  # semantic HM-aligned class — the target vocabulary
    if _PREFIX_RE.match(tok):
        return True
    return any(r.match(tok) for r in _UTILITY_RES)


# Dazzle-native design-system CSS still outside HM (must stay at 0).
# Derived from css_loader source lists. HM dist (layer=None), vendor/*, and
# reset.css are excluded — reset is a documented KEEP in the delegation allowlist.
# Peripheral themes/*.css that carry the AUTO-GENERATED-from-HM marker are HM-owned.
_CSS_STATIC = "src/dazzle/page/runtime/static"
_CSS_EXCLUDE_RELS = {"css/reset.css"}
_CSS_PERIPHERAL_GLOBS = ("css/themes/*.css",)
_HM_GENERATED_MARKER = "AUTO-GENERATED from packages/hatchi-maxchi/"


def _served_dazzle_native_rels() -> list[str]:
    """Served Dazzle-native design CSS from css_loader (minus HM/vendor/reset)."""
    from dazzle.page.runtime.css_loader import CSS_SOURCE_FILES, CSS_UNLAYERED_FILES

    rels: list[str] = []
    for layer, rel in CSS_SOURCE_FILES:
        if layer is None:  # HM dist artifact — already HM-owned
            continue
        if rel.startswith("vendor/") or rel in _CSS_EXCLUDE_RELS:
            continue
        rels.append(rel)
    rels.extend(r for r in CSS_UNLAYERED_FILES if r not in _CSS_EXCLUDE_RELS)
    return rels


def _is_hm_generated(path: Path) -> bool:
    try:
        with path.open(encoding="utf-8", errors="replace") as fh:
            return _HM_GENERATED_MARKER in fh.readline()
    except OSError:
        return False


def _peripheral_rels(static: Path) -> list[str]:
    """Non-HM design CSS served outside the main bundle (must stay empty)."""
    rels: list[str] = []
    for pattern in _CSS_PERIPHERAL_GLOBS:
        if "*" in pattern:
            parent = static / Path(pattern).parent
            rels.extend(
                str(p.relative_to(static))
                for p in sorted(parent.glob(Path(pattern).name))
                if not _is_hm_generated(p)
            )
        elif (static / pattern).exists() and not _is_hm_generated(static / pattern):
            rels.append(pattern)
    return rels


def _lines(p: Path) -> int:
    return p.read_text(encoding="utf-8", errors="replace").count("\n") + 1


def _css_reservoir(repo_root: Path) -> dict[str, Any]:
    static = repo_root / _CSS_STATIC
    files: list[tuple[str, int]] = []
    total = 0
    for rel in _served_dazzle_native_rels():
        p = static / rel
        if not p.exists():
            continue
        n = _lines(p)
        files.append((rel, n))
        total += n
    files.sort(key=lambda x: -x[1])

    peripheral: list[tuple[str, int]] = []
    peripheral_total = 0
    for rel in _peripheral_rels(static):
        n = _lines(static / rel)
        peripheral.append((rel, n))
        peripheral_total += n
    peripheral.sort(key=lambda x: -x[1])

    return {
        "css_lines_dazzle_native": total,
        "css_files": files,
        "css_lines_peripheral": peripheral_total,
        "css_peripheral_files": peripheral,
        "css_lines_grand_total": total + peripheral_total,
    }


def scan(repo_root: Path) -> dict[str, Any]:
    """Count Tailwind tokens in emitters + residual Dazzle-native design CSS."""
    per_file: Counter[str] = Counter()
    token_counts: Counter[str] = Counter()
    for root in ROOTS:
        base = repo_root / root
        if not base.exists():
            continue
        for py in base.rglob("*.py"):
            text = py.read_text(encoding="utf-8", errors="replace")
            hits = 0
            for cls_val in _CLASS_ATTR_RE.findall(text):
                for tok in cls_val.split():
                    if is_tailwind_token(tok):
                        hits += 1
                        token_counts[tok] += 1
            if hits:
                per_file[str(py.relative_to(repo_root))] = hits
    css = _css_reservoir(repo_root)
    return {
        "total_tailwind_tokens": sum(per_file.values()),
        "files_with_tailwind": len(per_file),
        "top_files": per_file.most_common(15),
        "top_tokens": token_counts.most_common(20),
        **css,
    }


def floor_is_green(result: dict[str, Any]) -> bool:
    return result["total_tailwind_tokens"] == 0 and result["css_lines_grand_total"] == 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    args = ap.parse_args()

    repo_root = Path(__file__).resolve().parent.parent
    result = scan(repo_root)
    green = floor_is_green(result)

    if args.json:
        print(json.dumps({**result, "floor_green": green}, indent=2))
        return 0 if green else 1

    print("HM zero-floor (Tailwind utilities + residual Dazzle design CSS)")
    print("  [markup] Tailwind utility tokens in emitter class attrs:")
    print(
        f"    total tokens: {result['total_tailwind_tokens']}   "
        f"files: {result['files_with_tailwind']}"
    )
    if result["top_tokens"]:
        print("    top tokens: " + ", ".join(f"{t}×{n}" for t, n in result["top_tokens"][:12]))
    if result["top_files"]:
        print("    files:")
        for name, n in result["top_files"][:10]:
            print(f"      {n:5d}  {name}")
    print("  [css] Dazzle-native design CSS not owned by HM (main + peripheral):")
    print(f"    main-bundle lines: {result['css_lines_dazzle_native']}")
    for name, n in result["css_files"][:10]:
        print(f"      {n:5d}  {name}")
    print(f"    peripheral lines: {result['css_lines_peripheral']}")
    for name, n in result["css_peripheral_files"][:10]:
        print(f"      {n:5d}  {name}")
    print(f"  [css/GRAND TOTAL]: {result['css_lines_grand_total']}")
    print("  [floor]: " + ("GREEN (0 / 0)" if green else "RED — restore zero before merge"))
    print(
        "  CSS boundary proof: tests/unit/test_hm_delegation_proof.py "
        "(exact allowlist; stronger than line counts)."
    )
    return 0 if green else 1


if __name__ == "__main__":
    sys.exit(main())
