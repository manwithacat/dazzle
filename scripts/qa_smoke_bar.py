#!/usr/bin/env python3
"""QA smoke residual for /improve — last smoke-crawl + hyperpart auto_seed.

Does **not** re-run Playwright. Scores artifacts under ``examples/*/dev_docs/``
so the improve driver can force ``agent_qa_smoke`` (or trials lane) digs.

Residual when a showcase app has:

* newest ``qa-smoke-*.json`` with non-empty ``auto_seed``, or
* newest ``qa-hyperpart-opportunities-*.json`` with non-empty ``auto_seed``, or
* ``trial.toml`` present but **no** smoke report in the last *stale_days*
  (default 7) — mechanical L2.5 never closed for that app.

Usage::

    python scripts/qa_smoke_bar.py --status
    python scripts/qa_smoke_bar.py --next
    python scripts/qa_smoke_bar.py --strict
"""

from __future__ import annotations

import argparse
import json
import time
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
DEFAULT_STALE_DAYS = 7


@dataclass
class AppSmokeBar:
    app: str
    smoke_auto_seed: int = 0
    hyperpart_auto_seed: int = 0
    smoke_report: str = ""
    smoke_age_days: float | None = None
    has_trial: bool = False
    stale: bool = False
    reasons: list[str] = field(default_factory=list)

    def is_residual(self) -> bool:
        return bool(self.reasons)

    def ok(self) -> bool:
        return not self.is_residual()


def _newest(app_dir: Path, glob_pat: str) -> Path | None:
    files = sorted(app_dir.glob(glob_pat), key=lambda p: p.stat().st_mtime, reverse=True)
    return files[0] if files else None


def _auto_seed_count(path: Path | None) -> int:
    if path is None or not path.is_file():
        return 0
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return 0
    seed = data.get("auto_seed") or []
    return len(seed) if isinstance(seed, list) else 0


def score_app(app: str, *, stale_days: float = DEFAULT_STALE_DAYS) -> AppSmokeBar:
    app_dir = EXAMPLES / app
    dev = app_dir / "dev_docs"
    row = AppSmokeBar(app=app, has_trial=(app_dir / "trial.toml").is_file())
    smoke = _newest(dev, "qa-smoke-*.json") if dev.is_dir() else None
    hyper = _newest(dev, "qa-hyperpart-opportunities-*.json") if dev.is_dir() else None
    if smoke:
        row.smoke_report = (
            str(smoke.relative_to(REPO)) if smoke.is_relative_to(REPO) else str(smoke)
        )
        row.smoke_auto_seed = _auto_seed_count(smoke)
        age = (time.time() - smoke.stat().st_mtime) / 86400.0
        row.smoke_age_days = round(age, 2)
        if row.smoke_auto_seed:
            row.reasons.append(f"smoke_auto_seed={row.smoke_auto_seed}")
        if age > stale_days:
            row.stale = True
            row.reasons.append(f"smoke_stale_days={row.smoke_age_days}>{stale_days}")
    elif row.has_trial:
        row.stale = True
        row.reasons.append("no_smoke_report")
    row.hyperpart_auto_seed = _auto_seed_count(hyper)
    if row.hyperpart_auto_seed:
        row.reasons.append(f"hyperpart_auto_seed={row.hyperpart_auto_seed}")
    return row


def scan(*, stale_days: float = DEFAULT_STALE_DAYS) -> list[AppSmokeBar]:
    return [score_app(a, stale_days=stale_days) for a in SHOWCASE if (EXAMPLES / a).is_dir()]


def format_status(rows: list[AppSmokeBar]) -> str:
    residual = [r for r in rows if r.is_residual()]
    nxt = residual[0].app if residual else "-"
    parts = [
        f"qa_smoke residual={len(residual)} next={nxt}",
    ]
    for r in residual[:6]:
        parts.append(f"{r.app}:{'/'.join(r.reasons)}")
    return " ".join(parts)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--status", action="store_true")
    p.add_argument("--next", action="store_true")
    p.add_argument("--json", action="store_true")
    p.add_argument("--strict", action="store_true")
    p.add_argument("--stale-days", type=float, default=DEFAULT_STALE_DAYS)
    args = p.parse_args(argv)
    rows = scan(stale_days=args.stale_days)
    residual = [r for r in rows if r.is_residual()]
    if args.json:
        print(json.dumps([asdict(r) for r in rows], indent=2))
    elif args.next:
        print(residual[0].app if residual else "")
    else:
        print(format_status(rows))
    if args.strict and residual:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
