#!/usr/bin/env python3
"""Build the HaTchi-MaXchi distribution bundle — self-contained, stdlib-only.

Produces:
    dist/hatchi-maxchi.css   tokens + base + components (design system only)
    dist/hatchi-maxchi.js    behaviour controllers (dz-confirm, dz-command)
    dist/fonts/              vendored Geist (OFL)

Unlike the Dazzle monorepo's ``scripts/build_dist.py`` (which bundles the
whole framework), this builds ONLY the design system, from package sources,
with no Dazzle imports — it runs identically in the standalone repo's CI.

Prefix (``--prefix``): the ``dz-`` namespace is the default, not a
requirement. Passing e.g. ``--prefix ax-`` rewrites every ``dz-``
occurrence — class names (``.dz-button``), data attributes
(``data-dz-tone``), and keyframes (``dz-fade-in``) — across the CSS and
JS. The rename is a plain textual transform, which works because the
namespace is used consistently; remember your markup must use the same
prefix (the gallery snippets are published with ``dz-``).
"""

import argparse
import re
import shutil
from pathlib import Path

PKG = Path(__file__).resolve().parent

# Concatenation order mirrors the monorepo cascade: fonts first (families
# exist before tokens reference them), tokens, base, then components.
CSS_SOURCES = [
    "base/fonts.css",
    "tokens/tokens.css",
    "base/design-system.css",
    "base/base.css",
    "components/alert.css",
    "components/badge.css",
    "components/button.css",
    "components/form.css",
    "components/fragment-primitives.css",
    "components/hm-core.css",
    "components/htmx-states.css",
    "components/table.css",
    "components/touch-targets.css",
]

JS_SOURCES = [
    "controllers/dz-confirm.js",
    "controllers/dz-command.js",
]

FONT_DIR = PKG / "site" / "fonts"  # tracked vendored copy (Geist, OFL)

_PREFIX_RE = re.compile(r"^[a-z][a-z0-9]*-$")


def build_css(prefix: str = "dz-") -> str:
    parts = []
    for rel in CSS_SOURCES:
        css = (PKG / rel).read_text(encoding="utf-8")
        # Dazzle serves fonts at /static/fonts/; the standalone bundle
        # keeps them relative, next to the CSS.
        css = css.replace("/static/fonts/", "fonts/")
        parts.append(f"/* ── {rel} ── */\n{css}")
    return apply_prefix("\n".join(parts), prefix)


def build_js(prefix: str = "dz-") -> str:
    parts = [f"/* ── {rel} ── */\n{(PKG / rel).read_text(encoding='utf-8')}" for rel in JS_SOURCES]
    return apply_prefix("\n".join(parts), prefix)


def apply_prefix(text: str, prefix: str) -> str:
    if prefix == "dz-":
        return text
    if not _PREFIX_RE.match(prefix):
        raise SystemExit(f"invalid prefix {prefix!r} — want lowercase like 'ax-'")
    return text.replace("dz-", prefix)


def build(out_dir: Path, prefix: str = "dz-") -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "hatchi-maxchi.css").write_text(build_css(prefix), encoding="utf-8")
    (out_dir / "hatchi-maxchi.js").write_text(build_js(prefix), encoding="utf-8")
    fonts_out = out_dir / "fonts"
    fonts_out.mkdir(exist_ok=True)
    for f in FONT_DIR.iterdir():
        if f.is_file():
            shutil.copyfile(f, fonts_out / f.name)
    print(f"built dist -> {out_dir} (prefix {prefix!r})")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default=str(PKG / "dist"))
    ap.add_argument("--prefix", default="dz-", help="class/attr namespace (default dz-)")
    args = ap.parse_args()
    build(Path(args.out), args.prefix)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
