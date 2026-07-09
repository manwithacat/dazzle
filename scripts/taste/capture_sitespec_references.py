#!/usr/bin/env python3
"""Capture per-family marketing exemplar screenshots for the sitespec vision score.

Goal-2 (2A-ii) reference asset. Each aesthetic family (linear-dark / stripe / paper
/ expressive) is anchored to 2-3 real best-in-class marketing pages — the "what modern
X looks like" references the blind vision judge scores our rendered sitespec against,
AND (dual-use, per the north star doc) the visual target an agent studies when
customising HM for a new property.

Screenshots are THIRD-PARTY content: written to .dazzle/ (gitignored), never committed
— the same posture as the taste-panel references (scripts/taste/capture_references.py).
Re-run to refresh; public pages drift and that is fine — the panel re-baselines per run.

The exemplar URLs are curated from the standard designer-inspiration galleries (Godly,
Land-book, Lapa Ninja, Awwwards) — pick per family:
  linear-dark  crisp dark-tech   → linear.app, vercel.com, resend.com
  stripe       bright SaaS       → stripe.com, mercury.com, ramp.com
  paper        warm / neutral    → notion.so, things.com, apple.com
  expressive   motion/art-directed → framer.com, superlist.com, arc.net

Usage:
    python scripts/taste/capture_sitespec_references.py            # capture all
    python scripts/taste/capture_sitespec_references.py --list     # print targets
    python scripts/taste/capture_sitespec_references.py --family expressive
    python scripts/taste/capture_sitespec_references.py --only framer

Requires: playwright + a browser with outbound network (CI or a workstation — not the
sandbox). `uv run playwright install chromium` if needed.
"""

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

# Marketing heroes want a taller frame than the app-taste 1440x900 — landing pages
# lead with a full-width hero; a 1440x1024 fold captures headline + subhead + CTA.
VIEWPORT = {"width": 1440, "height": 1024}
OUT_DIR = Path(".dazzle/composition/references/sitespec")

# (family, name, url, themes) — one row per exemplar. `family` is the aesthetic
# dialect this page anchors; the judge scores our <family>-themed sitespec against
# the references tagged with that same family. Themes via Playwright color-scheme
# emulation. Curated per the galleries above; refresh freely (public pages drift).
TARGETS: list[tuple[str, str, str, list[str]]] = [
    # linear-dark — crisp dark-tech (Linear / Vercel)
    ("linear-dark", "linear", "https://linear.app", ["dark"]),
    ("linear-dark", "vercel", "https://vercel.com", ["dark"]),
    ("linear-dark", "resend", "https://resend.com", ["dark"]),
    # stripe — bright editorial SaaS (Stripe / Mercury)
    ("stripe", "stripe", "https://stripe.com", ["light"]),
    ("stripe", "mercury", "https://mercury.com", ["light"]),
    ("stripe", "ramp", "https://ramp.com", ["light"]),
    # paper — warm / neutral / timeless (Notion / Apple)
    ("paper", "notion", "https://www.notion.so", ["light"]),
    ("paper", "things", "https://culturedcode.com/things/", ["light"]),
    ("paper", "apple", "https://www.apple.com", ["light"]),
    # expressive — motion / art-directed (Framer / Superlist / Arc)
    ("expressive", "framer", "https://www.framer.com", ["light", "dark"]),
    ("expressive", "superlist", "https://www.superlist.com", ["dark"]),
    ("expressive", "arc", "https://arc.net", ["light"]),
]

FAMILIES = tuple(dict.fromkeys(fam for fam, *_ in TARGETS))  # ordered unique


def capture(only: str | None, family: str | None) -> int:
    from playwright.sync_api import sync_playwright

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    entries: list[dict[str, str]] = []
    failures = 0

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        for fam, name, url, themes in TARGETS:
            if only and name != only:
                continue
            if family and fam != family:
                continue
            for theme in themes:
                out = OUT_DIR / f"{fam}__{name}_{theme}.png"
                try:
                    context = browser.new_context(viewport=VIEWPORT, color_scheme=theme)  # type: ignore[arg-type]
                    page = context.new_page()
                    page.goto(url, wait_until="networkidle", timeout=45_000)
                    page.wait_for_timeout(1_800)  # settle fonts/hero animations
                    page.screenshot(path=str(out), full_page=False)  # the hero fold
                    context.close()
                    entries.append(
                        {
                            "family": fam,
                            "name": name,
                            "url": url,
                            "theme": theme,
                            "screenshot": str(out),
                        }
                    )
                    print(f"  captured {out}")
                except Exception as exc:  # noqa: BLE001 — operator script, keep going
                    failures += 1
                    print(f"  FAILED {fam}/{name} ({theme}): {exc}", file=sys.stderr)
        browser.close()

    manifest = {
        "captured_at": datetime.now(UTC).isoformat(),
        "viewport": VIEWPORT,
        "families": list(FAMILIES),
        "references": entries,
    }
    (OUT_DIR / "sitespec_references_manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    print(f"{len(entries)} captured, {failures} failed → {OUT_DIR}")
    return 1 if failures and not entries else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--list", action="store_true", help="print targets and exit")
    parser.add_argument("--only", help="capture a single named target")
    parser.add_argument("--family", choices=FAMILIES, help="capture one family's exemplars")
    args = parser.parse_args()
    if args.list:
        for fam, name, url, themes in TARGETS:
            print(f"{fam}\t{name}\t{url}\t{','.join(themes)}")
        return 0
    return capture(args.only, args.family)


if __name__ == "__main__":
    raise SystemExit(main())
