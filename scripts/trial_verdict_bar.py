#!/usr/bin/env python3
"""Trial verdict residual — last agent QA panel outcome as improve heat.

When ``trial.toml`` exists, look for the newest ``qa-trial-*.json`` under
``dev_docs/`` or ``.dazzle/``. Residual when:

* last report ``recommend`` ∈ {no, conditional}, or
* any adoption criterion scored ``fail``, or
* showcase app has trial.toml but **no** report (never panelled), or
* showcase app **missing** trial.toml (``no_trial`` policy — panel harness required)

Does not re-run trials — only scores artifacts so /improve can force
``agent_acceptance_panel`` digs.

Usage::

    python scripts/trial_verdict_bar.py --status
    python scripts/trial_verdict_bar.py --next
    python scripts/trial_verdict_bar.py --strict
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
EXAMPLES = REPO / "examples"

SHOWCASE = (
    "simple_task",
    "support_tickets",
    "invoice_ops",
    "contact_manager",
    "ops_dashboard",
    "project_tracker",
    "design_studio",
    "hr_records",
    "fieldtest_hub",
)


@dataclass
class AppTrialVerdict:
    app: str
    has_trial_toml: bool = False
    report_path: str | None = None
    recommend: str | None = None
    fail_criteria: list[str] = field(default_factory=list)
    issues: list[str] = field(default_factory=list)
    score: int = 0

    @property
    def is_residual(self) -> bool:
        return bool(self.issues)

    @property
    def ok(self) -> bool:
        return not self.issues


def _find_reports(app_dir: Path) -> list[Path]:
    hits: list[Path] = []
    for base in (app_dir / "dev_docs", app_dir / ".dazzle"):
        if not base.is_dir():
            continue
        hits.extend(base.glob("qa-trial-*.json"))
        hits.extend(base.rglob("qa-trial-*.json"))
    # de-dupe
    return sorted(set(hits), key=lambda p: p.stat().st_mtime if p.is_file() else 0, reverse=True)


def _parse_report(path: Path) -> tuple[str | None, list[str]]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None, []
    if not isinstance(data, dict):
        return None, []
    recommend = data.get("recommend") or data.get("verdict") or data.get("recommendation")
    if isinstance(recommend, dict):
        recommend = recommend.get("recommend") or recommend.get("value")
    fails: list[str] = []
    scores = data.get("criteria_scores") or data.get("adoption_scores") or {}
    if isinstance(scores, dict):
        for k, v in scores.items():
            val = v.get("score") if isinstance(v, dict) else v
            if str(val).lower() == "fail":
                fails.append(str(k))
    return (str(recommend).lower() if recommend else None), fails


def score_app(app: str, *, require_trial_toml: bool = True) -> AppTrialVerdict:
    """Score one app. Showcase apps residual without trial.toml when *require_trial_toml*."""
    row = AppTrialVerdict(app=app)
    root = EXAMPLES / app
    if not root.is_dir():
        return row
    trial = root / "trial.toml"
    row.has_trial_toml = trial.is_file()
    if not row.has_trial_toml:
        if require_trial_toml and app in SHOWCASE:
            row.issues.append("no_trial")
            row.score = 35
        return row

    reports = _find_reports(root)
    if not reports:
        row.issues.append("no_trial_report")
        row.score = 40
        return row

    latest = reports[0]
    row.report_path = str(latest.relative_to(REPO)) if latest.is_relative_to(REPO) else str(latest)
    recommend, fails = _parse_report(latest)
    row.recommend = recommend
    row.fail_criteria = fails
    if recommend in {"no", "conditional"}:
        row.issues.append(f"recommend:{recommend}")
        row.score += 60 if recommend == "no" else 35
    if fails:
        row.issues.append(f"criteria_fail:{','.join(fails[:4])}")
        row.score += 20 * min(len(fails), 3)
    return row


def scan() -> list[AppTrialVerdict]:
    rows = [score_app(a) for a in SHOWCASE if (EXAMPLES / a).is_dir()]
    rows.sort(key=lambda r: (-r.score, r.app))
    return rows


def format_status(rows: list[AppTrialVerdict]) -> str:
    residual = [r for r in rows if r.is_residual]
    nxt = residual[0].app if residual else "-"
    return f"trial_verdict apps={len(rows)} residual={len(residual)} next={nxt}"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--next", action="store_true")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--strict", action="store_true")
    ap.add_argument("--app")
    args = ap.parse_args(argv)

    rows = [score_app(args.app)] if args.app else scan()
    residual = [r for r in rows if r.is_residual]

    if args.next:
        print(residual[0].app if residual else "")
        return 0 if not residual else 1

    if args.status:
        print(format_status(rows))
    elif args.json:
        print(
            json.dumps(
                {
                    "status": format_status(rows),
                    "apps": [asdict(r) for r in rows],
                    "next": residual[0].app if residual else None,
                    "residual": len(residual),
                },
                indent=2,
            )
        )
    else:
        print(f"{'app':<22} rec{'':6} issues")
        print("-" * 60)
        for r in rows:
            print(f"{r.app:<22} {(r.recommend or '-'):<8} {','.join(r.issues) or '-'}")
        print(format_status(rows))

    if args.strict and residual:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
