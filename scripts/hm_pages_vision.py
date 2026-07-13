#!/usr/bin/env python3
"""Subscription vision capture for the HM GitHub Pages gallery.

Capture (Playwright, local) → host-harness **Read** of PNGs (subscription)
→ structured findings / taste scores / **per-Hyperpart coherence**.
Does **not** call metered ``taste_panel.score_image`` / Anthropic HTTP.

Usage (monorepo root)::

    # Curated high-signal pages (default)
    python scripts/hm_pages_vision.py --capture
    python scripts/hm_pages_vision.py --write-prompt

    # ALL Hyperpart gallery pages (~90) — preferred quality sweep
    python scripts/hm_pages_vision.py --capture --all-hyperparts \\
        --base "file://$(pwd)/packages/hatchi-maxchi/site" \\
        --out .dazzle/hm-hyperpart-coherence
    python scripts/hm_pages_vision.py --write-coherence-prompt \\
        --out .dazzle/hm-hyperpart-coherence --batch-size 12
    # …host subagents Read PNGs per batch prompt, Write batch-*.json…
    python scripts/hm_pages_vision.py --ingest-coherence \\
        .dazzle/hm-hyperpart-coherence/batch-*.json \\
        --out .dazzle/hm-hyperpart-coherence

    # Live Pages
    python scripts/hm_pages_vision.py --capture --all-hyperparts

See also: ``scripts/hm_subscription_vision.py`` (dual-lock smoke),
``.claude/commands/improve/strategies/hyperpart_coherence.md``,
``.claude/commands/improve/strategies/visual_tier2_subagent.md``.
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
DEFAULT_SITE = REPO / "packages" / "hatchi-maxchi" / "site"
DEFAULT_COHERENCE_OUT = REPO / ".dazzle" / "hm-hyperpart-coherence"

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


def discover_hyperpart_pages(site_dir: Path | None = None) -> list[tuple[str, str]]:
    """Return ``(stem, /hyperparts/stem.html)`` for every gallery Hyperpart page."""
    root = site_dir or DEFAULT_SITE
    hp = root / "hyperparts"
    if not hp.is_dir():
        return []
    pages: list[tuple[str, str]] = []
    for f in sorted(hp.glob("*.html")):
        stem = f.stem
        pages.append((stem, f"/hyperparts/{stem}.html"))
    return pages


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


def capture(
    *,
    base: str,
    out: Path,
    pages: list[tuple[str, str]],
    full_page: bool,
    clip_demo: bool = False,
) -> dict:
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
                # Meta-refresh aliases (e.g. grid-edit → grid.html) need a beat to land.
                page.wait_for_timeout(500)
                try:
                    page.wait_for_load_state("networkidle", timeout=8000)
                except Exception:
                    pass
                page.wait_for_timeout(200)
                # detect GitHub Pages 404 chrome / blank file:// dead-ends
                body = page.inner_text("body")[:200]
                is_404 = (
                    status == 404
                    or "File not found" in body
                    or body.strip().startswith("404")
                    or not body.strip()
                )
                png = out / f"{name}.png"
                if not is_404 and clip_demo:
                    # Prefer the live demo region when present (less chrome noise).
                    loc = page.locator(
                        "main .hm-demo, main [data-hm-demo], .hm-hyperpart-demo, #demo, main"
                    ).first
                    try:
                        if loc.count() > 0:
                            loc.screenshot(path=str(png))
                        else:
                            page.screenshot(path=str(png), full_page=full_page)
                    except Exception:
                        page.screenshot(path=str(png), full_page=full_page)
                else:
                    page.screenshot(path=str(png), full_page=full_page and not is_404)
                screens.append(
                    {
                        "image_id": name,
                        "path": str(png.resolve()),
                        "label": f"HM hyperpart: {name}",
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
                        "label": f"HM hyperpart: {name}",
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
        "kind": "hm_pages_vision",
        "screens": screens,
        "n_screens": len(screens),
        "n_404": sum(1 for s in screens if s.get("is_404")),
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def _images_from_manifest(manifest_path: Path) -> list[dict[str, str]]:
    man = json.loads(manifest_path.read_text(encoding="utf-8"))
    return [
        {
            "image_id": s["image_id"],
            "path": s["path"],
            "label": s.get("label", s["image_id"]),
        }
        for s in man.get("screens", [])
        if s.get("path") and not s.get("is_404")
    ]


def write_prompt(manifest_path: Path, out_prompt: Path, findings_path: Path) -> str:
    sys.path.insert(0, str(REPO / "src"))
    from dazzle.qa.subscription_vision import build_subscription_score_prompt

    images = _images_from_manifest(manifest_path)
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


def write_coherence_prompts(
    manifest_path: Path,
    out_dir: Path,
    *,
    batch_size: int = 12,
) -> list[Path]:
    """Split Hyperpart images into batch mission prompts for parallel subagents."""
    sys.path.insert(0, str(REPO / "src"))
    from dazzle.qa.subscription_vision import build_hyperpart_coherence_prompt

    images = _images_from_manifest(manifest_path)
    out_dir.mkdir(parents=True, exist_ok=True)
    if batch_size < 1:
        batch_size = len(images) or 1

    written: list[Path] = []
    batches = [images[i : i + batch_size] for i in range(0, len(images), batch_size)] or [[]]
    index: list[dict] = []
    for bi, batch in enumerate(batches):
        if not batch:
            continue
        prompt_path = out_dir / f"coherence-prompt-batch-{bi:02d}.txt"
        findings_path = out_dir / f"batch-{bi:02d}-raw.json"
        label = f"batch {bi + 1}/{len(batches)} ({len(batch)} images)"
        prompt = build_hyperpart_coherence_prompt(
            batch,
            findings_path=findings_path,
            batch_label=label,
        )
        prompt_path.write_text(prompt, encoding="utf-8")
        written.append(prompt_path)
        index.append(
            {
                "batch": bi,
                "prompt": str(prompt_path.resolve()),
                "findings_target": str(findings_path.resolve()),
                "image_ids": [img["image_id"] for img in batch],
                "n": len(batch),
            }
        )
        try:
            rel = prompt_path.resolve().relative_to(REPO)
        except ValueError:
            rel = prompt_path
        print(f"wrote {rel}  n={len(batch)} → {findings_path.name}")

    (out_dir / "coherence-batches.json").write_text(
        json.dumps(
            {
                "created_at": datetime.now(UTC).isoformat(),
                "batch_size": batch_size,
                "n_images": len(images),
                "n_batches": len(index),
                "batches": index,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return written


def ingest_coherence(raw_paths: list[Path], out_dir: Path) -> Path:
    sys.path.insert(0, str(REPO / "src"))
    from dazzle.qa.subscription_vision import parse_hyperpart_coherence, write_coherence

    results = []
    for p in raw_paths:
        if not p.is_file():
            print(f"skip missing {p}", file=sys.stderr)
            continue
        text = p.read_text(encoding="utf-8")
        try:
            blob = json.loads(text)
        except json.JSONDecodeError:
            blob = text
        chunk = parse_hyperpart_coherence(blob)
        print(f"ingest {p.name}: {len(chunk)} result(s)")
        results.extend(chunk)

    # Dedup by image_id (later batches win)
    by_id: dict[str, object] = {}
    for r in results:
        by_id[r.image_id] = r
    merged = list(by_id.values())
    out = out_dir / "coherence.json"
    write_coherence(
        merged,  # type: ignore[arg-type]
        out,
        meta={
            "ingested_at": datetime.now(UTC).isoformat(),
            "sources": [str(p) for p in raw_paths],
        },
    )
    print(
        f"wrote {out}  n={len(merged)}  "
        f"coherent={sum(1 for r in merged if r.coherent)}  "  # type: ignore[attr-defined]
        f"incoherent={sum(1 for r in merged if not r.coherent)}"  # type: ignore[attr-defined]
    )
    worst = sorted(merged, key=lambda r: (r.score, r.image_id))[:12]  # type: ignore[attr-defined]
    for r in worst:
        flag = "OK " if r.coherent else "BAD"  # type: ignore[attr-defined]
        print(
            f"  {flag} {r.image_id:24} score={r.score}  {r.notes or (r.issues[0]['description'] if r.issues else '')}"[
                :100
            ]
        )  # type: ignore[attr-defined]
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--capture", action="store_true")
    ap.add_argument("--base", default=DEFAULT_BASE, help="Pages base URL or file:// site dir")
    ap.add_argument("--out", type=Path, default=None, help="Output dir (default depends on mode)")
    ap.add_argument("--full-page", action="store_true", help="full-page screenshots")
    ap.add_argument(
        "--clip-demo",
        action="store_true",
        help="prefer screenshot of demo region over full viewport",
    )
    ap.add_argument(
        "--all-hyperparts",
        action="store_true",
        help="capture every packages/hatchi-maxchi/site/hyperparts/*.html page",
    )
    ap.add_argument(
        "--site-dir",
        type=Path,
        default=DEFAULT_SITE,
        help="local site tree for --all-hyperparts discovery",
    )
    ap.add_argument(
        "--stems",
        default="",
        help="comma-separated hyperpart stems to capture (overrides default list)",
    )
    ap.add_argument("--limit", type=int, default=0, help="cap page count after selection")
    ap.add_argument("--write-prompt", action="store_true", help="taste-score mission prompt")
    ap.add_argument(
        "--write-coherence-prompt",
        action="store_true",
        help="write batched hyperpart-coherence mission prompts",
    )
    ap.add_argument(
        "--batch-size",
        type=int,
        default=12,
        help="images per coherence subagent batch (default 12)",
    )
    ap.add_argument("--ingest-findings", type=Path, default=None)
    ap.add_argument(
        "--ingest-coherence",
        nargs="*",
        default=None,
        help="raw batch JSON files (glob expanded by shell) → coherence.json",
    )
    ap.add_argument(
        "--list-hyperparts",
        action="store_true",
        help="print discovered hyperpart stems and exit",
    )
    args = ap.parse_args(argv)

    if args.list_hyperparts:
        pages = discover_hyperpart_pages(args.site_dir)
        for name, rel in pages:
            print(f"{name}\t{rel}")
        print(f"# {len(pages)} hyperparts", file=sys.stderr)
        return 0

    out = args.out
    if out is None:
        out = DEFAULT_COHERENCE_OUT if args.all_hyperparts else DEFAULT_OUT
    out = out.expanduser()
    if not out.is_absolute():
        out = (REPO / out).resolve()
    else:
        out = out.resolve()

    if args.capture:
        if args.stems:
            pages = [
                (s.strip(), f"/hyperparts/{s.strip()}.html")
                for s in args.stems.split(",")
                if s.strip()
            ]
        elif args.all_hyperparts:
            pages = discover_hyperpart_pages(args.site_dir)
            if not pages:
                print(f"error: no hyperparts under {args.site_dir / 'hyperparts'}", file=sys.stderr)
                return 2
            # Prefer local file:// when base is still the live default
            if args.base == DEFAULT_BASE and args.site_dir.is_dir():
                # Keep live default unless operator set --base; only auto-local when
                # site exists AND operator did not pass --base? Safer: document only.
                pass
        else:
            pages = list(DEFAULT_PAGES)
        if args.limit and args.limit > 0:
            pages = pages[: args.limit]
        man = capture(
            base=args.base,
            out=out,
            pages=pages,
            full_page=args.full_page,
            clip_demo=args.clip_demo,
        )
        print(
            f"manifest: {out / 'manifest.json'}  screens={len(man['screens'])}  404s={man['n_404']}"
        )

    if args.write_prompt:
        man_path = out / "manifest.json"
        if not man_path.is_file():
            print("error: run --capture first", file=sys.stderr)
            return 2
        prompt_path = out / "prompt.txt"
        findings_target = out / "findings-raw.json"
        write_prompt(man_path, prompt_path, findings_target)
        print(f"wrote {prompt_path}")
        print(f"findings target: {findings_target}")

    if args.write_coherence_prompt:
        man_path = out / "manifest.json"
        if not man_path.is_file():
            print("error: run --capture first", file=sys.stderr)
            return 2
        written = write_coherence_prompts(man_path, out, batch_size=args.batch_size)
        print(f"{len(written)} batch prompt(s) → {out / 'coherence-batches.json'}")

    if args.ingest_findings:
        raw = json.loads(args.ingest_findings.read_text(encoding="utf-8"))
        findings_out = out / "findings.json"
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
        findings_out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        n = len(payload.get("findings") or [])
        print(f"wrote {findings_out}  findings={n}")
        for f in (payload.get("findings") or [])[:12]:
            print(f"  [{f.get('severity')}] {f.get('page')}: {f.get('description', '')[:70]}")

    if args.ingest_coherence is not None:
        paths = [Path(p) for p in args.ingest_coherence]
        if not paths:
            # default: all batch-*-raw.json in out
            paths = sorted(out.glob("batch-*-raw.json"))
        if not paths:
            print("error: no coherence raw files to ingest", file=sys.stderr)
            return 2
        ingest_coherence(paths, out)

    if not any(
        [
            args.capture,
            args.write_prompt,
            args.write_coherence_prompt,
            args.ingest_findings,
            args.ingest_coherence is not None,
            args.list_hyperparts,
        ]
    ):
        ap.print_help()
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
