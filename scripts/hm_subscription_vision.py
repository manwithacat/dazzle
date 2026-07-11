#!/usr/bin/env python3
"""Subscription vision scores for HM dual-lock smoke — zero metered API calls.

**Capture (local):** ``scripts/hm_visual_smoke.py`` or ``dazzle qa capture``.
**Judge (subscription):** host-harness subagent **Reads** PNGs in-session
(same model as ``visual_tier2_subagent``). Writes structured taste scores to
gitignored ``.dazzle/``.

Does **not** import or call ``anthropic`` / ``taste_panel.score_image``.

Usage (monorepo root)::

    # 1) capture (Playwright only)
    python scripts/hm_visual_smoke.py --dazzle-emit

    # 2) emit a mission prompt for a host subagent (or the outer agent)
    python scripts/hm_subscription_vision.py --from-smoke --write-prompt

    # 3) agent Reads PNGs, Writes scores JSON (see prompt), then:
    python scripts/hm_subscription_vision.py --ingest .dazzle/hm-visual-scores-raw.json

    # Fleet path (existing): see
    #   .claude/commands/improve/strategies/visual_tier2_subagent.md
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--from-smoke",
        action="store_true",
        help="use .dazzle/hm-visual-smoke/manifest.json (default smoke dir)",
    )
    ap.add_argument(
        "--manifest",
        type=Path,
        default=None,
        help="path to hm_visual_smoke manifest.json",
    )
    ap.add_argument(
        "--png",
        type=Path,
        action="append",
        default=[],
        help="extra PNG paths (repeatable)",
    )
    ap.add_argument(
        "--write-prompt",
        action="store_true",
        help="write mission prompt to .dazzle/hm-subscription-vision-prompt.txt",
    )
    ap.add_argument(
        "--scores-out",
        type=Path,
        default=None,
        help="path the subagent should write (default .dazzle/hm-visual-scores-raw.json)",
    )
    ap.add_argument(
        "--ingest",
        type=Path,
        default=None,
        help="validate + copy scores into .dazzle/hm-visual-scores.json",
    )
    ap.add_argument("--json", action="store_true", help="print image list / result as JSON")
    args = ap.parse_args(argv)

    # Late import so CLI --help works without full package env quirks
    sys.path.insert(0, str(REPO / "src"))
    from dazzle.qa.subscription_vision import (
        build_subscription_score_prompt,
        load_scores,
        parse_subscription_scores,
        scores_from_smoke_manifest,
        write_scores,
    )

    dazzle_dir = REPO / ".dazzle"
    scores_raw = args.scores_out or (dazzle_dir / "hm-visual-scores-raw.json")
    scores_final = dazzle_dir / "hm-visual-scores.json"
    prompt_path = dazzle_dir / "hm-subscription-vision-prompt.txt"

    if args.ingest:
        text = args.ingest.read_text(encoding="utf-8")
        scores = parse_subscription_scores(text)
        if not scores:
            # maybe wrapped by write_scores already
            try:
                scores = load_scores(args.ingest)
            except Exception:
                scores = []
        if not scores:
            print("error: no valid scores in", args.ingest, file=sys.stderr)
            return 2
        write_scores(
            scores,
            scores_final,
            meta={
                "ingested_at": datetime.now(UTC).isoformat(),
                "source": str(args.ingest),
            },
        )
        # also mirror last-run pointer fields
        last = dazzle_dir / "hm-visual-last.json"
        if last.is_file():
            try:
                blob = json.loads(last.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                blob = {}
        else:
            blob = {}
        blob["scores_path"] = str(scores_final)
        blob["scores_mean"] = round(
            sum(s.mean() for s in scores) / len(scores),
            2,
        )
        blob["billing"] = "subscription-host-read"
        blob["ship_gate"] = False
        last.write_text(json.dumps(blob, indent=2) + "\n", encoding="utf-8")
        if args.json:
            print(
                json.dumps(
                    {
                        "scores_path": str(scores_final),
                        "n": len(scores),
                        "means": {s.image_id: round(s.mean(), 2) for s in scores},
                    },
                    indent=2,
                )
            )
        else:
            print(f"wrote {scores_final.relative_to(REPO)}  ({len(scores)} image(s))")
            for s in scores:
                print(f"  {s.image_id}: mean={s.mean():.1f}  worst={s.worst_detail[:60]}")
        return 0

    images: list[dict[str, str]] = []
    manifest = args.manifest
    if args.from_smoke and manifest is None:
        manifest = dazzle_dir / "hm-visual-smoke" / "manifest.json"
    if manifest is not None:
        if not manifest.is_file():
            print(
                f"error: missing smoke manifest {manifest}\n"
                "hint: python scripts/hm_visual_smoke.py --dazzle-emit",
                file=sys.stderr,
            )
            return 2
        images.extend(scores_from_smoke_manifest(manifest))
    for i, png in enumerate(args.png or []):
        p = png if png.is_absolute() else REPO / png
        images.append(
            {
                "image_id": f"png-{i}-{p.stem}",
                "path": str(p.resolve()),
                "label": p.name,
            }
        )
    if not images:
        print(
            "error: no images — use --from-smoke and/or --png PATH",
            file=sys.stderr,
        )
        return 2

    if args.write_prompt:
        prompt = build_subscription_score_prompt(images, scores_path=scores_raw)
        prompt_path.parent.mkdir(parents=True, exist_ok=True)
        prompt_path.write_text(prompt, encoding="utf-8")
        if args.json:
            print(
                json.dumps(
                    {
                        "prompt": str(prompt_path),
                        "scores_target": str(scores_raw),
                        "images": images,
                    },
                    indent=2,
                )
            )
        else:
            print(f"wrote {prompt_path.relative_to(REPO)}")
            print(f"scores target: {scores_raw}")
            print(f"images: {len(images)}")
            print()
            print("Next (subscription — no API key):")
            print("  1. Dispatch a host-harness subagent with the prompt file contents")
            print("     (or Read the PNGs yourself in this session).")
            print(f"  2. Subagent Writes scores JSON to {scores_raw}")
            print(f"  3. python scripts/hm_subscription_vision.py --ingest {scores_raw}")
            print()
            print("Fleet alternative: .claude/commands/improve/strategies/visual_tier2_subagent.md")
        return 0

    if args.json:
        print(json.dumps({"images": images}, indent=2))
    else:
        print("Subscription vision images:")
        for img in images:
            print(f"  {img['image_id']}: {img['path']}")
        print("hint: add --write-prompt to emit the subagent mission")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
