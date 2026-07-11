#!/usr/bin/env python3
"""Subscription vision capture for the HM GitHub Pages gallery.

Capture (Playwright, local) → host-harness **Read** of PNGs (subscription)
→ structured findings / taste scores. Does **not** call metered
``taste_panel.score_image`` / Anthropic HTTP.

Usage (monorepo root)::

    # Live Pages (default base)
    python scripts/hm_pages_vision.py --capture
    python scripts/hm_pages_vision.py --write-prompt
    # …host agent Reads PNGs, Writes findings JSON…
    python scripts/hm_pages_vision.py --ingest-findings .dazzle/hm-pages-findings-raw.json

    # Local site/ tree (after build_site.py)
    python scripts/hm_pages_vision.py --capture --base file:///…/packages/hatchi-maxchi/site/

See also: ``scripts/hm_subscription_vision.py`` (dual-lock smoke),
``.claude/commands/improve/strategies/visual_tier2_subagent.md`` (fleet).
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DEFAULT_BASE = "https://manwithacat.github.io/hatchi-maxchi"
DEFAULT_OUT = REPO / ".dazzle" / "hm-pages-vision"

# High-signal surfaces + dual-lock exemplars + known alias checks
DEFAULT_PAGES: list[tuple[str, str]] = [
    ("index", "/"),
    ("guide", "/guide.html"),
    ("button", "/hyperparts/button.html"),
    ("money", "/hyperparts/money.html"),
    ("combobox", "/hyperparts/combobox.html"),
    ("tags", "/hyperparts/tags.html"),
    ("grid", "/hyperparts/grid.html"),
    ("grid-edit", "/hyperparts/grid-edit.html"),  # must not 404 (alias)
    ("master-detail", "/hyperparts/master-detail.html"),
    ("pdf", "/hyperparts/pdf.html"),
    ("wizard", "/hyperparts/wizard.html"),
    ("confirm", "/hyperparts/confirm.html"),
    ("dialog", "/hyperparts/dialog.html"),
    ("app-shell", "/hyperparts/app-shell.html"),
    ("command", "/hyperparts/command.html"),
]


def _url(base: str, path: str) -> str:
    base = base.rstrip("/")
    if path.startswith("http"):
        return path
    if not path.startswith("/"):
        path = "/" + path
    if base.startswith("file://"):
        # file:///…/site + /hyperparts/x.html
        root = base[len("file://") :]
        return Path(root + path).as_uri()
    return base + path


def capture(*, base: str, out: Path, pages: list[tuple[str, str]], full_page: bool) -> dict:
    from playwright.sync_api import sync_playwright

    out.mkdir(parents=True, exist_ok=True)
    screens: list[dict] = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        for name, rel in pages:
            url = _url(base, rel)
            status = None
            try:
                resp = page.goto(url, wait_until="networkidle", timeout=45000)
                status = resp.status if resp else None
                page.wait_for_timeout(350)
                # detect GitHub Pages 404 chrome
                body = page.inner_text("body")[:200]
                is_404 = status == 404 or "File not found" in body or body.strip().startswith("404")
                png = out / f"{name}.png"
                page.screenshot(path=str(png), full_page=full_page and not is_404)
                screens.append(
                    {
                        "image_id": name,
                        "path": str(png.resolve()),
                        "label": f"HM pages: {name}",
                        "url": url,
                        "http_status": status,
                        "is_404": is_404,
                    }
                )
                flag = "404" if is_404 else "ok"
                print(f"{flag:3} {name}  {url}")
            except Exception as e:
                print(f"ERR {name}: {e}")
                screens.append(
                    {
                        "image_id": name,
                        "path": "",
                        "label": f"HM pages: {name}",
                        "url": url,
                        "http_status": status,
                        "is_404": True,
                        "error": str(e),
                    }
                )
        browser.close()

    manifest = {
        "created_at": datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ"),
        "base": base,
        "billing": "subscription-playwright-only",
        "ship_gate": False,
        "screens": screens,
        "n_404": sum(1 for s in screens if s.get("is_404")),
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def write_prompt(manifest_path: Path, out_prompt: Path, findings_path: Path) -> str:
    sys.path.insert(0, str(REPO / "src"))
    from dazzle.qa.subscription_vision import build_subscription_score_prompt

    man = json.loads(manifest_path.read_text(encoding="utf-8"))
    images = [
        {
            "image_id": s["image_id"],
            "path": s["path"],
            "label": s.get("label", s["image_id"]),
        }
        for s in man.get("screens", [])
        if s.get("path") and not s.get("is_404")
    ]
    score_prompt = build_subscription_score_prompt(images, scores_path=str(findings_path))
    extra = """

## Also check for gallery-specific incongruities

For each image (and overall), note any of:

1. **404 / missing page** for a dual-lock contract id (grid-edit, etc.)
2. **Broken interactive demo** (empty table, spinner forever, dead mock)
3. **Theme toggle** — does Dark actually flip materials?
4. **Code snippet overflow** — unreadable truncated long lines without scroll
5. **Naming drift** — gallery unprefixed classes (`data-money`) vs Dazzle dual-lock
   (`data-dz-money`) called out for agents?
6. **Copy typos / OCR-visible text bugs** in guidance panels

Append a top-level JSON object key is wrong — instead Write a findings **array**
alongside scores if you prefer two files. Preferred single file shape for
``--ingest-findings``:

```json
{
  "billing": "subscription-host-read",
  "ship_gate": false,
  "findings": [
    {
      "id": "F1",
      "severity": "high|medium|low",
      "page": "grid-edit",
      "category": "missing_page|demo_broken|theme|overflow|naming|copy|layout",
      "description": "…",
      "suggestion": "…"
    }
  ],
  "scores": [ /* optional, same shape as hm_subscription_vision */ ]
}
```
"""
    full = score_prompt + extra
    out_prompt.parent.mkdir(parents=True, exist_ok=True)
    out_prompt.write_text(full, encoding="utf-8")
    return full


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--capture", action="store_true")
    ap.add_argument("--base", default=DEFAULT_BASE, help="Pages base URL or file:// site dir")
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--full-page", action="store_true", help="full-page screenshots (huge index)")
    ap.add_argument("--write-prompt", action="store_true")
    ap.add_argument("--ingest-findings", type=Path, default=None)
    args = ap.parse_args(argv)

    if args.capture:
        man = capture(
            base=args.base,
            out=args.out,
            pages=DEFAULT_PAGES,
            full_page=args.full_page,
        )
        print(
            f"manifest: {args.out / 'manifest.json'}  screens={len(man['screens'])}  404s={man['n_404']}"
        )

    if args.write_prompt:
        man_path = args.out / "manifest.json"
        if not man_path.is_file():
            print("error: run --capture first", file=sys.stderr)
            return 2
        prompt_path = args.out / "prompt.txt"
        findings_target = args.out / "findings-raw.json"
        write_prompt(man_path, prompt_path, findings_target)
        print(f"wrote {prompt_path}")
        print(f"findings target: {findings_target}")

    if args.ingest_findings:
        raw = json.loads(args.ingest_findings.read_text(encoding="utf-8"))
        out = args.out / "findings.json"
        if isinstance(raw, list):
            payload = {
                "billing": "subscription-host-read",
                "ship_gate": False,
                "findings": raw,
            }
        else:
            payload = raw
            payload.setdefault("billing", "subscription-host-read")
            payload.setdefault("ship_gate", False)
        out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        n = len(payload.get("findings") or [])
        print(f"wrote {out}  findings={n}")
        for f in (payload.get("findings") or [])[:12]:
            print(f"  [{f.get('severity')}] {f.get('page')}: {f.get('description', '')[:70]}")

    if not (args.capture or args.write_prompt or args.ingest_findings):
        ap.print_help()
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
