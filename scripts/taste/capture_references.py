#!/usr/bin/env python3
"""Capture shadcn/Vercel-dialect reference screenshots for the taste panel.

Screenshots are the parity references for the blind judge panel
(spec: docs/superpowers/specs/2026-07-02-taste-house-aesthetic-design.md,
Phase 0). They are THIRD-PARTY content: written to .dazzle/ (gitignored),
never committed. Re-run this script to refresh; public pages drift and
that is fine — the panel is re-baselined per run.

Usage:
    python scripts/taste/capture_references.py            # capture all
    python scripts/taste/capture_references.py --list     # print targets
    python scripts/taste/capture_references.py --only shadcn_dashboard

Requires: playwright (`uv run playwright install chromium` if needed).
"""

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

VIEWPORT = {"width": 1440, "height": 900}
OUT_DIR = Path(".dazzle/composition/references/taste")

# (name, url, themes, scroll_to) — themes via Playwright color-scheme
# emulation; the reference sites default to system preference so emulation
# flips them. scroll_to (optional CSS selector) aligns the demo UI to the
# top of the 1440x900 frame so judges score the app surface, not the
# marketing hero above it. Selectors are utility-class based and may rot
# when the sites redeploy — a failed selector logs and falls back to the
# unscrolled fold, it never aborts the capture.
_DEMO = "div.rounded-lg.border.bg-background"  # shadcn /examples demo container
TARGETS: list[tuple[str, str, list[str], str | None]] = [
    ("shadcn_dashboard", "https://ui.shadcn.com/examples/dashboard", ["light", "dark"], _DEMO),
    ("shadcn_tasks", "https://ui.shadcn.com/examples/tasks", ["light", "dark"], _DEMO),
    ("shadcn_cards", "https://ui.shadcn.com/examples/cards", ["light", "dark"], _DEMO),
    ("shadcn_forms", "https://ui.shadcn.com/examples/forms", ["light", "dark"], _DEMO),
    ("shadcn_music", "https://ui.shadcn.com/examples/music", ["light", "dark"], _DEMO),
    ("vercel_home", "https://vercel.com", ["light", "dark"], None),
    ("linear_home", "https://linear.app", ["dark"], None),
    ("stripe_home", "https://stripe.com", ["light"], None),
]


def capture(only: str | None) -> int:
    from playwright.sync_api import sync_playwright

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    entries: list[dict[str, str]] = []
    failures = 0

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        for name, url, themes, scroll_to in TARGETS:
            if only and name != only:
                continue
            for theme in themes:
                out = OUT_DIR / f"{name}_{theme}.png"
                try:
                    context = browser.new_context(viewport=VIEWPORT, color_scheme=theme)
                    page = context.new_page()
                    page.goto(url, wait_until="networkidle", timeout=45_000)
                    page.wait_for_timeout(1_500)  # settle fonts/animations
                    if scroll_to:
                        try:
                            page.eval_on_selector(scroll_to, "el => el.scrollIntoView(true)")
                            page.wait_for_timeout(300)
                        except Exception as exc:  # noqa: BLE001
                            print(
                                f"  note: scroll_to '{scroll_to}' failed for {name} "
                                f"({exc.__class__.__name__}) — capturing unscrolled fold",
                                file=sys.stderr,
                            )
                    # Fixed-frame capture: the panel judges a 1440x900 frame
                    # for every image, Dazzle and reference alike.
                    page.screenshot(path=str(out), full_page=False)
                    context.close()
                    entries.append(
                        {"name": name, "url": url, "theme": theme, "screenshot": str(out)}
                    )
                    print(f"  captured {out}")
                except Exception as exc:  # noqa: BLE001 — operator script, keep going
                    failures += 1
                    print(f"  FAILED {name} ({theme}): {exc}", file=sys.stderr)
        browser.close()

    manifest = {
        "captured_at": datetime.now(UTC).isoformat(),
        "viewport": VIEWPORT,
        "references": entries,
    }
    (OUT_DIR / "references_manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    print(f"{len(entries)} captured, {failures} failed → {OUT_DIR}")
    return 1 if failures and not entries else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--list", action="store_true", help="print targets and exit")
    parser.add_argument("--only", help="capture a single named target")
    args = parser.parse_args()
    if args.list:
        for name, url, themes, _scroll_to in TARGETS:
            print(f"{name}\t{url}\t{','.join(themes)}")
        return 0
    return capture(args.only)


if __name__ == "__main__":
    raise SystemExit(main())
