#!/usr/bin/env python3
"""Generate the vendored Lucide icon registry (HaTchi-MaXchi TASTE-6).

Fetches SVGs for the curated set below from the pinned ``lucide-static``
npm package (version matched to the vendored client UMD bundle
``dazzle-icons.min.js``) and emits
``src/dazzle/render/fragment/icon_registry.py`` — an AUTO-GENERATED
mapping of icon name → inner SVG markup rendered server-side by the
``Icon`` fragment primitive (inline SVG, no JS, no icon font).

Adding an icon: append the kebab-case Lucide name to CURATED_ICONS and
re-run this script. The drift gate (tests/unit/test_icon_registry_drift.py)
pins the registry to this manifest.

Usage:
    python packages/hatchi-maxchi/icons/gen_registry.py          # regenerate (network)
    python packages/hatchi-maxchi/icons/gen_registry.py --sync   # rewrite both outputs, no network
    python packages/hatchi-maxchi/icons/gen_registry.py --list   # print manifest
"""

import argparse
import re
import sys
import urllib.request
from pathlib import Path

LUCIDE_VERSION = "0.577.0"  # matches static/dist/dazzle-icons.min.js
CDN = f"https://unpkg.com/lucide-static@{LUCIDE_VERSION}/icons"
PKG = Path(__file__).resolve().parent
OUT_HM = PKG / "registry.py"
# Dazzle's vendored copy — written only when running inside the monorepo
# (the standalone repo has no src/dazzle).
OUT_DAZZLE = PKG.parents[2] / "src" / "dazzle" / "render" / "fragment" / "icon_registry.py"

# Curated subset — common UI vocabulary. Kebab-case Lucide names, sorted.
CURATED_ICONS: list[str] = sorted(
    {
        # navigation / layout
        "arrow-down",
        "arrow-left",
        "arrow-right",
        "arrow-up",
        "arrow-up-right",
        "chevron-down",
        "chevron-left",
        "chevron-right",
        "chevron-up",
        "chevrons-left",
        "chevrons-right",
        "ellipsis",
        "ellipsis-vertical",
        "home",
        "layout-dashboard",
        "menu",
        "panel-left",
        "panel-right",
        "settings",
        "sliders-horizontal",
        # actions
        "archive",
        "ban",
        "check",
        "circle-plus",
        "copy",
        "download",
        "eraser",
        "external-link",
        "filter",
        "link",
        "log-in",
        "log-out",
        "pencil",
        "pin",
        "plus",
        "printer",
        "redo-2",
        "refresh-cw",
        "reply",
        "save",
        "scan",
        "search",
        "send",
        "share-2",
        "trash-2",
        "undo-2",
        "upload",
        "x",
        # status / feedback
        "badge-check",
        "bell",
        "bell-off",
        "circle-alert",
        "circle-check",
        "circle-help",
        "circle-x",
        "clock",
        "flag",
        "hourglass",
        "info",
        "loader-circle",
        "lock",
        "lock-open",
        "shield",
        "shield-check",
        "sparkles",
        "star",
        "thumbs-down",
        "thumbs-up",
        "triangle-alert",
        "zap",
        # objects / domain
        "banknote",
        "book-open",
        "box",
        "briefcase",
        "building-2",
        "calendar",
        "camera",
        "clipboard-list",
        "cloud",
        "code",
        "credit-card",
        "database",
        "file",
        "file-text",
        "folder",
        "folder-open",
        "gift",
        "globe",
        "image",
        "inbox",
        "key-round",
        "landmark",
        "layers",
        "lightbulb",
        "mail",
        "map-pin",
        "message-circle",
        "message-square",
        "mic",
        "monitor",
        "package",
        "paperclip",
        "phone",
        "receipt",
        "rocket",
        "server",
        "tag",
        "ticket",
        "truck",
        "user",
        "user-check",
        "user-plus",
        "users",
        "wallet",
        "wrench",
        # data / viz
        "chart-bar",
        "chart-column",
        "chart-line",
        "chart-pie",
        "gauge",
        "kanban",
        "list",
        "list-checks",
        "table",
        "target",
        "trending-down",
        "trending-up",
        # visibility / theme
        "eye",
        "eye-off",
        "moon",
        "sun",
        # misc
        "award",
        "bookmark",
        "calculator",
        "compass",
        "heart",
        "history",
        "puzzle",
        "scale",
        "timer",
    }
)

_SVG_INNER = re.compile(r"<svg\b[^>]*>(.*)</svg>", re.DOTALL)
_ALLOWED_TAGS = re.compile(
    r"^(?:\s*<(?:path|circle|rect|line|polyline|polygon|ellipse)\b[^>]*/?>\s*)+$"
)


def fetch_icon(name: str) -> str:
    with urllib.request.urlopen(f"{CDN}/{name}.svg", timeout=30) as resp:
        svg = resp.read().decode("utf-8")
    # Strip license comments, collapse whitespace, extract inner markup.
    svg = re.sub(r"<!--.*?-->", "", svg, flags=re.DOTALL)
    m = _SVG_INNER.search(svg)
    if not m:
        raise ValueError(f"{name}: no <svg> element in response")
    inner = re.sub(r"\s+", " ", m.group(1)).strip()
    if not _ALLOWED_TAGS.match(inner):
        raise ValueError(f"{name}: unexpected markup: {inner[:80]}")
    return inner


def generate() -> int:
    icons: dict[str, str] = {}
    failures: list[str] = []
    for name in CURATED_ICONS:
        try:
            icons[name] = fetch_icon(name)
            print(f"  {name}")
        except Exception as exc:  # noqa: BLE001 — operator script, report + continue
            failures.append(name)
            print(f"  FAILED {name}: {exc}", file=sys.stderr)
    if failures:
        print(f"\n{len(failures)} failed: {failures}", file=sys.stderr)
        return 1

    return write_outputs(icons)


def _emit(icons: dict[str, str], provenance: str) -> str:
    lines = [
        '"""Vendored Lucide icon registry — server-side inline SVG.',
        "",
        provenance,
        f"Source: lucide-static@{LUCIDE_VERSION} (https://lucide.dev), ISC license:",
        "Copyright (c) Lucide Contributors 2022 — permission to use, copy,",
        "modify, and/or distribute this software for any purpose with or",
        "without fee is hereby granted (full text: lucide.dev/license).",
        "",
        "Values are the inner markup of each icon's 24x24 stroke SVG; consumers",
        "wrap them in the <svg> shell at render time. Regenerate (never",
        "hand-edit) via packages/hatchi-maxchi/icons/gen_registry.py.",
        '"""',
        "",
        f'LUCIDE_VERSION = "{LUCIDE_VERSION}"',
        "",
        "ICONS: dict[str, str] = {",
    ]
    for name in CURATED_ICONS:
        lines.append(f'    "{name}": {icons[name]!r},')
    lines += ["}", ""]
    return "\n".join(lines)


def write_outputs(icons: dict[str, str]) -> int:
    OUT_HM.write_text(
        _emit(icons, "# AUTO-GENERATED by icons/gen_registry.py — do not edit."),
        encoding="utf-8",
    )
    print(f"{len(icons)} icons -> {OUT_HM}")
    if OUT_DAZZLE.parent.is_dir():
        OUT_DAZZLE.write_text(
            _emit(
                icons,
                "# AUTO-GENERATED vendored copy of packages/hatchi-maxchi/icons/registry.py\n"
                "# (regenerate via icons/gen_registry.py --sync) — do not edit.",
            ),
            encoding="utf-8",
        )
        print(f"{len(icons)} icons -> {OUT_DAZZLE} (vendored)")
    else:
        print("(no Dazzle tree — standalone repo, vendored copy skipped)")
    return 0


def sync() -> int:
    """Rewrite both outputs from the existing registry data — no network."""
    import importlib.util

    src = OUT_HM if OUT_HM.exists() else OUT_DAZZLE
    spec = importlib.util.spec_from_file_location("existing_registry", src)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert mod.LUCIDE_VERSION == LUCIDE_VERSION, (
        "bump LUCIDE_VERSION here first, then run a full (network) regen"
    )
    missing = [n for n in CURATED_ICONS if n not in mod.ICONS]
    assert not missing, f"registry missing {missing} — run a full (network) regen"
    return write_outputs({n: mod.ICONS[n] for n in CURATED_ICONS})


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--list", action="store_true", help="print manifest and exit")
    parser.add_argument(
        "--sync", action="store_true", help="rewrite both outputs from existing data (no network)"
    )
    args = parser.parse_args()
    if args.list:
        print("\n".join(CURATED_ICONS))
        return 0
    if args.sync:
        return sync()
    return generate()


if __name__ == "__main__":
    raise SystemExit(main())
