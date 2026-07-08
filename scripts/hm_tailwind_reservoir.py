#!/usr/bin/env python3
"""HM-convergence Tailwind-reservoir metric.

Counts Tailwind *utility classes* still present in the Dazzle render/page
emitters — the reservoir the `hm-convergence` improve lane drains as it
delegates all frontend design into HaTchi-MaXchi (2026-07-08 directive).

The number is a governance signal, not a hard gate: it must **shrink**
cycle-over-cycle, and a rise (new Tailwind creeping into an emitter) is a
regression the lane investigates.

Method — precision over recall: we extract the LITERAL value of every
``class="…"`` attribute in the emitters' f-strings and classify each token.
Scoping to class attributes (not raw line grep) kills the noise that makes a
naive ``grep flex`` report ~850 false hits (CSS-property strings, comments,
substrings of words). A token is counted as Tailwind iff it carries a
responsive/state prefix (``sm:``/``hover:``/``group-hover:``…) or matches a
known utility shape (spacing/grid/typography/border/opacity/arbitrary-value),
and is NOT a ``dz-*`` semantic class (the HM-aligned target vocabulary).

Usage:
    python scripts/hm_tailwind_reservoir.py            # human summary
    python scripts/hm_tailwind_reservoir.py --json     # machine-readable
    python scripts/hm_tailwind_reservoir.py --write-baseline   # snapshot to .dazzle/
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

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


# Dazzle-native design-system CSS — the LARGER reservoir. Derived from the
# authoritative served-bundle list in `css_loader.py` (CSS_SOURCE_FILES +
# CSS_UNLAYERED_FILES) rather than a naive glob — the v1 glob missed the whole
# `css/components/` subdir (undercount ~4.6×) and counted non-served reference
# files. Excluded from the convergence target: the HM dist (layer=None — already
# HM-owned), `vendor/*` (third-party CSS), `reset.css` (reset layer, foundational),
# and `site-sections.css` (marketing/docs site chrome, not app design system).
_CSS_STATIC = "src/dazzle/page/runtime/static"
_CSS_EXCLUDE_RELS = {"css/reset.css", "css/site-sections.css"}


def _served_dazzle_native_rels() -> list[str]:
    """The served Dazzle-native design-system CSS files, from css_loader's
    source-of-truth lists (minus HM dist / vendor / reset / site chrome)."""
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


def _css_reservoir(repo_root: Path) -> dict:
    static = repo_root / _CSS_STATIC
    files: list[tuple[str, int]] = []
    total = 0
    for rel in _served_dazzle_native_rels():
        p = static / rel
        if not p.exists():
            continue
        n = p.read_text(encoding="utf-8", errors="replace").count("\n") + 1
        files.append((rel, n))
        total += n
    files.sort(key=lambda x: -x[1])
    return {"css_lines_dazzle_native": total, "css_files": files}


def scan(repo_root: Path) -> dict:
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


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    ap.add_argument(
        "--write-baseline",
        action="store_true",
        help="snapshot the current count to .dazzle/hm-reservoir-baseline.json",
    )
    args = ap.parse_args()

    repo_root = Path(__file__).resolve().parent.parent
    result = scan(repo_root)

    if args.write_baseline:
        out = repo_root / ".dazzle" / "hm-reservoir-baseline.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(
            json.dumps(
                {
                    "total_tailwind_tokens": result["total_tailwind_tokens"],
                    "files_with_tailwind": result["files_with_tailwind"],
                    "css_lines_dazzle_native": result["css_lines_dazzle_native"],
                },
                indent=2,
            )
            + "\n"
        )
        print(f"baseline written: {out.relative_to(repo_root)}")

    if args.json:
        print(json.dumps(result, indent=2))
        return 0

    print("HM-convergence reservoir metric")
    print("  [markup] Tailwind utility tokens in emitter class attrs:")
    print(
        f"    total tokens: {result['total_tailwind_tokens']}   files: {result['files_with_tailwind']}"
    )
    if result["top_tokens"]:
        print("    top tokens: " + ", ".join(f"{t}×{n}" for t, n in result["top_tokens"][:12]))
    print("  [css] Dazzle-native design-system CSS not yet owned by HM (the larger reservoir):")
    print(f"    total lines: {result['css_lines_dazzle_native']}")
    for name, n in result["css_files"][:10]:
        print(f"    {n:5d}  {name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
