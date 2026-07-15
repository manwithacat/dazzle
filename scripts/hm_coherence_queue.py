#!/usr/bin/env python3
"""Rank Hyperpart visual-coherence drain work for /improve hm-convergence.

Reads the latest subscription sweep under ``.dazzle/hm-hyperpart-coherence/``
(produced by ``scripts/hm_pages_vision.py`` + subagent Read) and surfaces a
machine queue the lane can pick without re-walking 90 PNGs.

Usage (monorepo root)::

    python scripts/hm_coherence_queue.py
    python scripts/hm_coherence_queue.py --json
    python scripts/hm_coherence_queue.py --top 5
    python scripts/hm_coherence_queue.py --write          # → packages/hatchi-maxchi/COHERENCE_QUEUE.md
    python scripts/hm_coherence_queue.py --seed-backlog   # print HMC table rows for PENDING seed
    python scripts/hm_coherence_queue.py --status         # one-line for improve driver logs

Consumed by:
  - ``improve/strategies/hyperpart_coherence.md`` (investigate + drain phases)
  - ``improve/lanes/hm-convergence.md`` pick table
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DEFAULT_COHERENCE = REPO / ".dazzle" / "hm-hyperpart-coherence" / "coherence.json"
DEFAULT_MANIFEST = REPO / ".dazzle" / "hm-hyperpart-coherence" / "manifest.json"
OUT_MD = REPO / "packages" / "hatchi-maxchi" / "COHERENCE_QUEUE.md"

# lower = drain sooner
_CATEGORY_PRIORITY: dict[str, int] = {
    "empty_demo": 10,
    "layout_broken": 20,
    "missing_content": 30,
    "chrome_collision": 40,
    "overflow": 50,
    "contrast": 60,
    "spacing": 70,
    "typography": 80,
    "copy": 90,
    "decorative_noise": 100,
    "other": 110,
}

_SEVERITY_BOOST: dict[str, int] = {
    "high": 0,
    "medium": 5,
    "low": 15,
}


@dataclass(frozen=True)
class CoherenceCandidate:
    stem: str
    score: int
    coherent: bool
    priority: int
    severity: str
    category: str
    description: str
    suggestion: str
    path: str
    suggested_action: str
    backlog_scope: str


def _load_coherence(path: Path) -> dict:
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _primary_issue(result: dict) -> dict:
    issues = result.get("issues") or []
    if not issues:
        return {
            "severity": "medium" if not result.get("coherent", True) else "low",
            "category": "other",
            "description": result.get("notes") or "incoherent without issue detail",
            "suggestion": "",
        }
    order = {"high": 0, "medium": 1, "low": 2}
    return min(issues, key=lambda i: order.get(str(i.get("severity")), 9))


def _suggested_action(category: str, stem: str) -> str:
    if category in ("empty_demo", "missing_content"):
        return (
            f"Investigate capture vs live page for `{stem}` "
            f"(file:// packages/hatchi-maxchi/site/hyperparts/{stem}.html); "
            "fix registry demo / partial / asset load."
        )
    if category == "layout_broken":
        return f"Fix layout/chrome for `{stem}` in HM components/site registry partial."
    if category in ("spacing", "typography", "contrast", "chrome_collision", "overflow"):
        return f"CSS/demo polish for `{stem}` under packages/hatchi-maxchi/ (not Dazzle CSS)."
    if category == "copy":
        return f"Fix gallery copy/OCR-visible text on `{stem}` page."
    return f"Triage `{stem}` against PNG + page; fix or dismiss with reason."


def build_queue(coherence_path: Path = DEFAULT_COHERENCE) -> list[CoherenceCandidate]:
    blob = _load_coherence(coherence_path)
    results = blob.get("results") or []
    cands: list[CoherenceCandidate] = []
    for r in results:
        if r.get("coherent", True) and int(r.get("score") or 10) >= 7:
            # still surface borderline notes? skip clean rows
            issues = r.get("issues") or []
            if not issues:
                continue
            # optional low-noise issues on coherent pages — only if medium+
            if all(str(i.get("severity")) == "low" for i in issues):
                continue
        primary = _primary_issue(r)
        sev = str(primary.get("severity") or "medium")
        cat = str(primary.get("category") or "other")
        score = int(r.get("score") or 5)
        stem = str(r.get("image_id") or "")
        if not stem:
            continue
        # Prefer incoherent / low score
        base = _CATEGORY_PRIORITY.get(cat, 110)
        boost = _SEVERITY_BOOST.get(sev, 10)
        # lower score → earlier
        priority = base + boost + score
        if not r.get("coherent", True):
            priority -= 50
        if score <= 4:
            priority -= 20
        cands.append(
            CoherenceCandidate(
                stem=stem,
                score=score,
                coherent=bool(r.get("coherent", True)),
                priority=priority,
                severity=sev,
                category=cat,
                description=str(primary.get("description") or "")[:240],
                suggestion=str(primary.get("suggestion") or "")[:240],
                path=str(r.get("path") or ""),
                suggested_action=_suggested_action(cat, stem),
                backlog_scope=f"coherence_drain {stem}",
            )
        )
    cands.sort(key=lambda c: (c.priority, c.score, c.stem))
    return cands


def status_line(coherence_path: Path = DEFAULT_COHERENCE) -> str:
    blob = _load_coherence(coherence_path)
    if not blob:
        return "coherence: missing (run investigate — hm_pages_vision --all-hyperparts)"
    n = int(blob.get("n") or 0)
    n_bad = int(blob.get("n_incoherent") or 0)
    mean = blob.get("mean_score")
    age = blob.get("meta", {}).get("ingested_at") or blob.get("created_at") or "?"
    queue = build_queue(coherence_path)
    return f"coherence: n={n} incoherent={n_bad} mean={mean} queue={len(queue)} ingested={age}"


def write_markdown(cands: list[CoherenceCandidate], path: Path, coherence_path: Path) -> None:
    blob = _load_coherence(coherence_path)
    lines = [
        "# HM Hyperpart coherence queue",
        "",
        "Auto-generated by `scripts/hm_coherence_queue.py --write`.",
        "Do not hand-edit — re-run after a sweep or drain.",
        "",
        f"Generated: {datetime.now(UTC).strftime('%Y-%m-%dT%H:%MZ')}",
        f"Source: `{coherence_path.relative_to(REPO) if coherence_path.is_relative_to(REPO) else coherence_path}`",
        f"Sweep: n={blob.get('n', '?')} coherent={blob.get('n_coherent', '?')} "
        f"incoherent={blob.get('n_incoherent', '?')} mean={blob.get('mean_score', '?')}",
        "",
        "Consumed by `/improve hm-convergence hyperpart_coherence` **drain** phase.",
        "",
        "| pri | stem | score | sev | category | description | action |",
        "|----:|------|------:|-----|----------|-------------|--------|",
    ]
    for c in cands:
        desc = c.description.replace("|", "/")[:80]
        act = c.suggested_action.replace("|", "/")[:60]
        lines.append(
            f"| {c.priority} | `{c.stem}` | {c.score} | {c.severity} | {c.category} "
            f"| {desc} | {act} |"
        )
    if not cands:
        lines.append("| — | — | — | — | — | queue empty (re-investigate when stale) | — |")
    lines.extend(
        [
            "",
            "## Loop",
            "",
            "1. **Investigate** (if no `coherence.json` or ≥20 cycles stale): "
            "`hm_pages_vision.py --capture --all-hyperparts` + subagent batches + ingest",
            "2. **Queue**: `python scripts/hm_coherence_queue.py --top 5`",
            "3. **Drain** top candidate → fix HM → re-capture `--stems <stem>` → re-score",
            "4. Seed backlog: `python scripts/hm_coherence_queue.py --seed-backlog`",
            "",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def seed_backlog_rows(cands: list[CoherenceCandidate], start_id: int = 56) -> list[str]:
    """Emit markdown table rows for improve-backlog (HMC-NNN)."""
    rows = []
    for i, c in enumerate(cands):
        hid = f"HMC-{start_id + i:03d}"
        scope = c.backlog_scope
        note = (
            f"FROM coherence sweep: score={c.score} sev={c.severity} cat={c.category}. "
            f"{c.description[:120]}"
        ).replace("|", "/")
        rows.append(f"| {hid} | {scope} | — | — | PENDING | 0 | — | {note} |")
    return rows


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--coherence",
        type=Path,
        default=DEFAULT_COHERENCE,
        help="path to coherence.json",
    )
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--top", type=int, default=None)
    ap.add_argument("--write", action="store_true", help=f"write {OUT_MD.name}")
    ap.add_argument(
        "--seed-backlog",
        action="store_true",
        help="print PENDING HMC table rows for improve-backlog.md",
    )
    ap.add_argument(
        "--start-id",
        type=int,
        default=56,
        help="first HMC-NNN number for --seed-backlog (default 56)",
    )
    ap.add_argument("--status", action="store_true", help="one-line driver status")
    args = ap.parse_args(argv)

    if args.status:
        print(status_line(args.coherence))
        if not args.coherence.is_file():
            return 2
        return 0

    if not args.coherence.is_file():
        print(
            f"error: missing {args.coherence} — run investigate first:\n"
            "  python scripts/hm_pages_vision.py --capture --all-hyperparts \\\n"
            '    --base "file://$(pwd)/packages/hatchi-maxchi/site" \\\n'
            "    --out .dazzle/hm-hyperpart-coherence",
            file=sys.stderr,
        )
        return 2

    cands = build_queue(args.coherence)
    if args.top is not None:
        cands = cands[: args.top]

    if args.seed_backlog:
        for row in seed_backlog_rows(cands, start_id=args.start_id):
            print(row)
        return 0

    if args.write:
        write_markdown(build_queue(args.coherence), OUT_MD, args.coherence)
        print(f"wrote {OUT_MD.relative_to(REPO)}  ({len(build_queue(args.coherence))} candidates)")

    if args.json:
        print(json.dumps([asdict(c) for c in cands], indent=2))
        return 0

    if not args.write:
        print(status_line(args.coherence))
        print(f"{'pri':>4}  {'score':>5}  {'sev':7}  {'cat':16}  stem")
        for c in cands:
            print(f"{c.priority:4d}  {c.score:5d}  {c.severity:7}  {c.category:16}  {c.stem}")
        if not cands:
            print("(empty — re-investigate or all coherent)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
