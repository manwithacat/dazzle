#!/usr/bin/env python3
"""Load-bearing CSS classifier + token-literal lint (HM Phase C).

Aggressive HM-convergence drains delete/rewrite Dazzle-native CSS. Aesthetic
breakage is acceptable; **functional** breakage is not. This tool classifies
declaration properties so agents know which rules need a functional gate
(display/z-index/pointer/overflow/…) vs pure polish (color/shadow/radius/…).

Also flags **token literals** (raw hex/rgb colours, non-token px spacing) in
HM/Dazzle CSS outside the tokens file — agent style discipline, not a CI
ship gate by default.

Usage (monorepo root):

    python scripts/hm_css_classify.py                 # summary
    python scripts/hm_css_classify.py --json          # machine-readable
    python scripts/hm_css_classify.py path/to/file.css
    python scripts/hm_css_classify.py --tokens-only   # only literal findings

Exit 0 always for advisory runs; use --strict-tokens to exit 1 when any
token-literal finding is present (optional local gate).
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parent.parent

# Properties that affect clickability, visibility, stacking, or layout
# participation — deleting without a functional check is unsafe.
LOAD_BEARING_PROPS: frozenset[str] = frozenset(
    {
        "display",
        "visibility",
        "opacity",  # opacity:0 hides; still load-bearing for a11y/hit-testing
        "pointer-events",
        "z-index",
        "position",
        "overflow",
        "overflow-x",
        "overflow-y",
        "clip",
        "clip-path",
        "content-visibility",
        "contain",
        "inset",
        "top",
        "right",
        "bottom",
        "left",
        "transform",  # often moves interactive hit targets
        "translate",
        "scale",
        "rotate",
        "width",
        "height",
        "min-width",
        "min-height",
        "max-width",
        "max-height",
        "flex",
        "flex-grow",
        "flex-shrink",
        "flex-basis",
        "flex-direction",
        "flex-wrap",
        "grid",
        "grid-template",
        "grid-template-columns",
        "grid-template-rows",
        "grid-column",
        "grid-row",
        "gap",
        "row-gap",
        "column-gap",
        "order",
        "align-items",
        "justify-content",
        "place-items",
        "place-content",
        "cursor",  # not layout, but interaction affordance
        "user-select",
        "touch-action",
        "scroll-snap-type",
        "overscroll-behavior",
    }
)

# Purely aesthetic (safe to restyle under functional gates).
AESTHETIC_PROPS: frozenset[str] = frozenset(
    {
        "color",
        "background",
        "background-color",
        "background-image",
        "background-size",
        "background-position",
        "background-repeat",
        "border",
        "border-color",
        "border-style",
        "border-width",
        "border-top",
        "border-right",
        "border-bottom",
        "border-left",
        "border-radius",
        "border-top-left-radius",
        "border-top-right-radius",
        "border-bottom-left-radius",
        "border-bottom-right-radius",
        "box-shadow",
        "text-shadow",
        "font",
        "font-family",
        "font-size",
        "font-weight",
        "font-style",
        "line-height",
        "letter-spacing",
        "text-decoration",
        "text-transform",
        "text-align",
        "white-space",
        "word-break",
        "filter",
        "backdrop-filter",
        "outline",
        "outline-color",
        "outline-offset",
        "transition",
        "transition-property",
        "transition-duration",
        "transition-timing-function",
        "transition-delay",
        "animation",
        "animation-name",
        "animation-duration",
        "fill",
        "stroke",
        "stroke-width",
    }
)

# Strip comments before classification.
_COMMENT_RE = re.compile(r"/\*.*?\*/", re.S)
# Rough property: value pairs (not a full CSS parser).
_DECL_RE = re.compile(
    r"(?P<prop>-?[a-zA-Z_][\w-]*)\s*:\s*(?P<val>[^;{}]+);",
    re.M,
)
# Hex / rgb(a) / hsl(a) colour literals.
_COLOR_LITERAL_RE = re.compile(
    r"(?i)(?:#(?:[0-9a-f]{3,4}|[0-9a-f]{6}|[0-9a-f]{8})\b"
    r"|rgba?\([^)]+\)"
    r"|hsla?\([^)]+\))"
)
# Spacing-like raw lengths that should usually be tokens (skip 0, 1px hairlines).
_SPACE_LITERAL_RE = re.compile(r"(?i)(?<![\w-])(-?(?:[2-9]|\d{2,})(?:\.\d+)?(?:px|rem|em))\b")

# Paths scanned by default (relative to monorepo root).
_DEFAULT_GLOBS = (
    "packages/hatchi-maxchi/components/**/*.css",
    "packages/hatchi-maxchi/tokens/**/*.css",
    "src/dazzle/page/runtime/static/css/**/*.css",
)

# Token source of truth — literals here are allowed by design.
_TOKEN_ALLOWLIST_SUFFIXES = (
    "/tokens/tokens.css",
    "/tokens.css",
)


def classify_prop(prop: str) -> str:
    """Return load_bearing | aesthetic | unknown for a CSS property name."""
    p = prop.strip().lower()
    if p.startswith("--"):
        return "token_var"  # custom props — neither; usually fine
    if p in LOAD_BEARING_PROPS:
        return "load_bearing"
    if p in AESTHETIC_PROPS:
        return "aesthetic"
    # margin/padding are layout-ish; treat as load-bearing for drain safety
    if p.startswith("margin") or p.startswith("padding"):
        return "load_bearing"
    return "unknown"


def _is_token_allowlisted(path: Path) -> bool:
    s = str(path).replace("\\", "/")
    return any(s.endswith(suf) for suf in _TOKEN_ALLOWLIST_SUFFIXES)


def analyse_css_text(text: str, *, path: str = "") -> dict[str, Any]:
    """Classify declarations and find token literals in one CSS string."""
    stripped = _COMMENT_RE.sub("", text)
    counts: Counter[str] = Counter()
    load_bearing_samples: list[dict[str, str]] = []
    token_findings: list[dict[str, str]] = []

    for m in _DECL_RE.finditer(stripped):
        prop = m.group("prop")
        val = m.group("val").strip()
        kind = classify_prop(prop)
        counts[kind] += 1
        if kind == "load_bearing" and len(load_bearing_samples) < 40:
            load_bearing_samples.append({"property": prop, "value": val[:80]})

        # Token-literal scan (skip allowlisted token files)
        if path and _is_token_allowlisted(Path(path)):
            continue
        # var(--…) is the desired form
        if "var(" in val:
            continue
        for cm in _COLOR_LITERAL_RE.finditer(val):
            token_findings.append(
                {
                    "kind": "color_literal",
                    "property": prop,
                    "match": cm.group(0),
                    "value": val[:100],
                }
            )
        # Only flag spacing-like props for length literals
        if (
            prop.startswith("margin")
            or prop.startswith("padding")
            or prop
            in {
                "gap",
                "row-gap",
                "column-gap",
                "top",
                "right",
                "bottom",
                "left",
                "inset",
                "width",
                "height",
                "min-width",
                "min-height",
                "max-width",
                "max-height",
                "font-size",
                "line-height",
                "border-radius",
                "border-width",
            }
        ):
            for sm in _SPACE_LITERAL_RE.finditer(val):
                token_findings.append(
                    {
                        "kind": "length_literal",
                        "property": prop,
                        "match": sm.group(0),
                        "value": val[:100],
                    }
                )

    total = sum(counts.values())
    return {
        "path": path,
        "declarations": total,
        "by_kind": dict(counts),
        "load_bearing": counts.get("load_bearing", 0),
        "aesthetic": counts.get("aesthetic", 0),
        "unknown": counts.get("unknown", 0),
        "token_var": counts.get("token_var", 0),
        "load_bearing_ratio": (counts.get("load_bearing", 0) / total) if total else 0.0,
        "load_bearing_samples": load_bearing_samples,
        "token_findings": token_findings[:50],
        "token_finding_count": len(token_findings),
    }


def _iter_css_files(repo: Path, paths: list[str] | None) -> list[Path]:
    if paths:
        out: list[Path] = []
        for raw in paths:
            p = Path(raw)
            if not p.is_absolute():
                p = repo / p
            if p.is_file() and p.suffix == ".css":
                out.append(p)
            elif p.is_dir():
                out.extend(sorted(p.rglob("*.css")))
        return out
    files: list[Path] = []
    for pattern in _DEFAULT_GLOBS:
        files.extend(sorted(repo.glob(pattern)))
    # de-dupe, skip vendor / dist min
    seen: set[Path] = set()
    clean: list[Path] = []
    for f in files:
        if f in seen:
            continue
        if "vendor" in f.parts or f.name.endswith(".min.css"):
            continue
        if "dist" in f.parts and f.name.startswith("dazzle"):
            continue
        seen.add(f)
        clean.append(f)
    return clean


def scan(repo: Path, paths: list[str] | None = None) -> dict[str, Any]:
    files = _iter_css_files(repo, paths)
    per_file: list[dict[str, Any]] = []
    totals: Counter[str] = Counter()
    token_total = 0
    high_risk: list[dict[str, Any]] = []

    for f in files:
        try:
            text = f.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        rel = str(f.relative_to(repo)) if f.is_relative_to(repo) else str(f)
        row = analyse_css_text(text, path=rel)
        per_file.append(row)
        for k, n in row["by_kind"].items():
            totals[k] += n
        token_total += row["token_finding_count"]
        # High-risk for aggressive delete: majority load-bearing
        if row["declarations"] >= 5 and row["load_bearing_ratio"] >= 0.45:
            high_risk.append(
                {
                    "path": rel,
                    "load_bearing": row["load_bearing"],
                    "declarations": row["declarations"],
                    "ratio": round(row["load_bearing_ratio"], 3),
                }
            )

    high_risk.sort(key=lambda r: (-r["ratio"], -r["load_bearing"]))
    decl_total = sum(totals.values())
    return {
        "files_scanned": len(per_file),
        "declarations": decl_total,
        "by_kind": dict(totals),
        "load_bearing": totals.get("load_bearing", 0),
        "aesthetic": totals.get("aesthetic", 0),
        "token_findings_total": token_total,
        "high_risk_files": high_risk[:25],
        "files": per_file,
        "policy": {
            "load_bearing": "functional gate required before delete/rewrite",
            "aesthetic": "safe under dual-lock + visual smoke",
            "token_literals": "prefer var(--…) from tokens.css; advisory unless --strict-tokens",
        },
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "paths", nargs="*", help="CSS files or dirs (default: HM components + Dazzle css)"
    )
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--tokens-only", action="store_true", help="only print token-literal findings")
    ap.add_argument(
        "--strict-tokens",
        action="store_true",
        help="exit 1 if any token-literal findings outside tokens.css",
    )
    args = ap.parse_args(argv)

    result = scan(REPO, list(args.paths) if args.paths else None)

    if args.json:
        # slim file rows for machine use
        slim = {
            **{k: v for k, v in result.items() if k != "files"},
            "files": [
                {
                    "path": f["path"],
                    "declarations": f["declarations"],
                    "load_bearing": f["load_bearing"],
                    "aesthetic": f["aesthetic"],
                    "load_bearing_ratio": f["load_bearing_ratio"],
                    "token_finding_count": f["token_finding_count"],
                    "token_findings": f["token_findings"][:10],
                }
                for f in result["files"]
            ],
        }
        print(json.dumps(slim, indent=2))
    elif args.tokens_only:
        print(f"token-literal findings: {result['token_findings_total']}")
        for f in result["files"]:
            if not f["token_findings"]:
                continue
            print(f"  {f['path']}  ({f['token_finding_count']})")
            for t in f["token_findings"][:8]:
                print(f"    {t['kind']:14}  {t['property']}: {t['match']}")
    else:
        print("HM CSS load-bearing classifier")
        print(f"  files: {result['files_scanned']}   declarations: {result['declarations']}")
        bk = result["by_kind"]
        print(
            f"  load_bearing: {bk.get('load_bearing', 0)}   "
            f"aesthetic: {bk.get('aesthetic', 0)}   "
            f"unknown: {bk.get('unknown', 0)}   "
            f"token_var: {bk.get('token_var', 0)}"
        )
        print(f"  token-literal findings (outside tokens.css): {result['token_findings_total']}")
        if result["high_risk_files"]:
            print("  high-risk files (load_bearing ≥ 45% of decls, n≥5) — gate before drain:")
            for h in result["high_risk_files"][:12]:
                print(
                    f"    {h['ratio']:.0%}  {h['load_bearing']:4d}/{h['declarations']:<4d}  {h['path']}"
                )
        print("  policy: load-bearing → functional test; aesthetic → dual-lock + smoke OK")

    if args.strict_tokens and result["token_findings_total"] > 0:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
