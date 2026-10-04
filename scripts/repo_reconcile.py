#!/usr/bin/env python3
"""Is the repository's record coherent with its code?

One command for the question an agent (or a person) otherwise answers with six
ad-hoc `gh` queries and an hour of context:

* **stale issues** — an open issue whose number already appears in a *merged*
  commit message. The work shipped; the issue stayed open. Four of these were
  open on this repo while their fix sat in ``main``.
* **PRs behind main** — green, mergeable, and waiting on nothing but a merge.
* **advisories not in a terminal state** — Dependabot alerts that are neither
  ``fixed`` nor ``dismissed``.
* **state that has rotted past its own threshold** — the improve backlog is over
  the 100 KB compaction line, and compaction only runs *inside* a cycle, so a
  stopped loop leaves it there.
* **a stopped loop** — the improve driver's heartbeat age. Nothing else reports
  this: the loop's continuity depends on a host-side ``scheduler_create``, and
  when that stops firing, every cycle-driven courtesy silently stops too.

Every check is advisory: this reports, it does not fail a build. The gates that
*do* fail builds are ``tests/unit/test_pip_audit.py`` (delegation targets) and
``tests/unit/test_improve_harness_paths.py`` (harness paths).

Usage::

    uv run python scripts/repo_reconcile.py            # human summary
    uv run python scripts/repo_reconcile.py --json     # machine readable
    uv run python scripts/repo_reconcile.py --skip-github   # offline checks only
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
BACKLOG = REPO / "dev_docs" / "improve-backlog.md"
IMPROVE_LOG = REPO / "dev_docs" / "improve-log.md"
SCHEDULE_STATE = REPO / ".dazzle" / "improve-schedule-state.json"

# The driver's own compaction trigger (SKILL.md, "State compaction"). Reported,
# never enforced here — the compaction script owns that decision.
BACKLOG_COMPACT_KB = 100

# A cycle older than this is a stopped loop, not a slow one. The driver
# self-schedules at 15m when quiet and ~45m after a ship.
LOOP_STALE_DAYS = 2


@dataclass
class Finding:
    """One thing the record and the code disagree about."""

    kind: str
    detail: str
    severity: str  # "action" | "notice"
    ref: str = ""

    def line(self) -> str:
        where = f"  {self.ref}" if self.ref else ""
        return f"[{self.severity:<6}] {self.kind}: {self.detail}{where}"


@dataclass
class Report:
    findings: list[Finding] = field(default_factory=list)
    facts: dict[str, object] = field(default_factory=dict)

    def add(self, kind: str, detail: str, severity: str = "action", ref: str = "") -> None:
        self.findings.append(Finding(kind, detail, severity, ref))


def _gh(*args: str) -> str | None:
    """Run a `gh` command, or return None if it is unavailable/auth-failing.

    A missing `gh` must read as "could not tell", never as "clean" — the same
    distinction `scripts/pip_audit.py` makes between *no verdict* and *clean*.
    """
    try:
        proc = subprocess.run(
            ["gh", *args], capture_output=True, text=True, cwd=REPO, timeout=120, check=False
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    return proc.stdout


def _gh_json(*args: str) -> object | None:
    raw = _gh(*args)
    if raw is None:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


# ---------------------------------------------------------------------------
# Git-side facts
# ---------------------------------------------------------------------------


def merged_commit_messages(limit: int = 400) -> list[str]:
    """Commit subjects on `main`, newest first."""
    proc = subprocess.run(
        ["git", "log", f"-{limit}", "--pretty=%s%n%b"],
        capture_output=True,
        text=True,
        cwd=REPO,
        check=False,
    )
    return proc.stdout.splitlines() if proc.returncode == 0 else []


def check_stale_issues(report: Report) -> None:
    """An open issue whose number is in a merged commit message.

    Not proof the issue is done — sometimes a commit cites an issue it only
    partially advanced — which is why this is reported for a human (or agent) to
    confirm rather than closed automatically.
    """
    issues = _gh_json(
        "issue", "list", "--state", "open", "--limit", "100", "--json", "number,title"
    )
    if issues is None:
        report.add("github", "could not read open issues (gh unavailable?)", "notice")
        return
    messages = merged_commit_messages()
    blob = "\n".join(messages)
    report.facts["open_issues"] = len(issues)  # type: ignore[arg-type]
    for issue in issues:  # type: ignore[union-attr]
        number = issue.get("number")
        # `#1234` but not `#12345`, and not a range like `#1234-#1240`.
        if re.search(rf"#{number}(?!\d)", blob):
            report.add(
                "stale-issue",
                f"#{number} is open but a merged commit cites it — the work may have shipped",
                "action",
                f"https://github.com/{_slug()}/issues/{number}",
            )


def check_pull_requests(report: Report) -> None:
    prs = _gh_json(
        "pr",
        "list",
        "--state",
        "open",
        "--limit",
        "50",
        "--json",
        "number,title,mergeable,mergeStateStatus,isDraft",
    )
    if prs is None:
        report.add("github", "could not read open pull requests (gh unavailable?)", "notice")
        return
    report.facts["open_prs"] = len(prs)  # type: ignore[arg-type]
    for pr in prs:  # type: ignore[union-attr]
        state = pr.get("mergeStateStatus")
        if pr.get("isDraft"):
            continue
        if pr.get("mergeable") == "MERGEABLE" and state in {"CLEAN", "BLOCKED", "BEHIND"}:
            note = " (behind main — update the branch)" if state == "BEHIND" else ""
            report.add(
                "pr-ready",
                f"#{pr['number']} is mergeable{note}: {str(pr.get('title'))[:70]}",
                "action",
                f"https://github.com/{_slug()}/pull/{pr['number']}",
            )


def check_advisories(report: Report) -> None:
    """Dependabot alerts that are neither fixed nor dismissed."""
    alerts = _gh_json("api", "repos/{owner}/{repo}/dependabot/alerts", "--paginate", "--slurp")
    if alerts is None:
        report.add(
            "github", "could not read Dependabot alerts (scope or gh unavailable?)", "notice"
        )
        return
    flat = [a for batch in alerts if isinstance(batch, list) for a in batch]  # type: ignore[union-attr]
    live = [a for a in flat if a.get("state") in {"open", "dismissed", "fixed", "auto_dismissed"}]
    open_alerts = [a for a in live if a.get("state") == "open"]
    report.facts["dependabot_alerts"] = len(flat)
    report.facts["dependabot_open"] = len(open_alerts)
    for alert in open_alerts[:10]:
        adv = alert.get("security_advisory", {})
        report.add(
            "advisory-open",
            f"{adv.get('severity', '?')} {adv.get('ghsa_id', '?')} in "
            f"{alert.get('dependency', {}).get('package', {}).get('name', '?')}",
            "action",
        )


# ---------------------------------------------------------------------------
# Loop state
# ---------------------------------------------------------------------------


def _age_days(path: Path) -> float | None:
    if not path.exists():
        return None
    mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)
    return (datetime.now(UTC) - mtime).days


_CYCLE_DATE = re.compile(r"^## Cycle \d+ — (\d{4}-\d{2}-\d{2})", re.MULTILINE)


def _days_since_last_cycle() -> float | None:
    """Days since the newest ``## Cycle N — <date>`` heading in the log.

    Deliberately the log's own content, not the file mtime: compaction rewrites
    the log, so an mtime heartbeat reports "ran today" for a loop that has not run
    since the last compaction — the exact false green this check exists to catch.
    """
    if not IMPROVE_LOG.exists():
        return None
    dates = _CYCLE_DATE.findall(IMPROVE_LOG.read_text(encoding="utf-8"))
    if not dates:
        return None
    newest = max(datetime.strptime(d, "%Y-%m-%d").replace(tzinfo=UTC) for d in dates)
    return (datetime.now(UTC) - newest).days


def _backlog_kb() -> float | None:
    return BACKLOG.stat().st_size / 1024 if BACKLOG.exists() else None


def check_loop_state(report: Report) -> None:
    """The improve driver's heartbeat, and the state it is supposed to compact."""
    log_age = _days_since_last_cycle()
    backlog_kb = _backlog_kb()
    report.facts["days_since_last_cycle"] = log_age
    report.facts["backlog_kb"] = round(backlog_kb, 1) if backlog_kb else None

    if log_age is None:
        report.add("improve-loop", "no improve log — has the loop ever run?", "notice")
    elif log_age > LOOP_STALE_DAYS:
        report.add(
            "improve-loop",
            f"last cycle {log_age:.0f} days ago (threshold {LOOP_STALE_DAYS}). The loop "
            "self-schedules via the host's scheduler_create; nothing reports when that "
            "stops firing",
            "action",
        )

    if backlog_kb and backlog_kb > BACKLOG_COMPACT_KB:
        report.add(
            "improve-state",
            f"backlog is {backlog_kb:.0f} KB, over the driver's own {BACKLOG_COMPACT_KB} KB "
            "compaction threshold — compaction runs inside a cycle, so a stopped loop "
            "leaves it there (run: python scripts/improve_compact.py)",
            "action",
        )


def check_chain(report: Report) -> None:
    """Is the improve loop's *chain* armed, and has it stopped?

    The loop's continuity is `scheduler_create`, a host tool. Where it is absent
    the cycle ends in `STOP reason=no host scheduler_create` and nothing outside
    the cycle can see it — a stopped loop and a loop with nothing to do are the
    same state, which is how this one sat parked for 30 days while the loop's own
    courtesy work went with it (#1759 W6).
    """
    if not SCHEDULE_STATE.is_file():
        report.add("improve-chain", "no schedule state — has a cycle ever run?", "notice")
        return
    try:
        state = json.loads(SCHEDULE_STATE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        report.add("improve-chain", f"schedule state unreadable: {exc}", "notice")
        return
    report.facts["chain_armed"] = state.get("chain_armed")
    if state.get("parked_by_decision"):
        report.add(
            "improve-chain",
            f"the loop is parked by decision ({state.get('parked_reason', 'no reason')}) — "
            "cycles run by hand. Re-arm with a host scheduler or `make reconcile` once the "
            "reason no longer holds",
            "notice",
        )
        return
    if state.get("action") == "schedule" and state.get("chain_armed") is False:
        report.add(
            "improve-chain",
            "the loop decided to schedule but the chain was never armed "
            f"({state.get('chain_blocked_reason', 'no reason recorded')}) — "
            "the next cycle will not run unless a human or a host scheduler fires it",
            "action",
        )


def check_harness(report: Report) -> None:
    """The harness-path gate, restated as a fact for the summary."""
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "tests/unit/test_improve_harness_paths.py",
            "-q",
            "--tb=line",
        ],
        capture_output=True,
        text=True,
        cwd=REPO,
        check=False,
    )
    report.facts["harness_paths"] = "ok" if proc.returncode == 0 else "rotten"
    if proc.returncode != 0:
        report.add("harness", "a playbook names a path that does not exist", "action")


def _slug() -> str:
    try:
        return (
            subprocess.run(
                ["gh", "repo", "view", "--json", "nameWithOwner", "-q", ".nameWithOwner"],
                capture_output=True,
                text=True,
                cwd=REPO,
                check=False,
            ).stdout.strip()
            or "OWNER/REPO"
        )
    except (OSError, subprocess.SubprocessError):
        return "OWNER/REPO"


# ---------------------------------------------------------------------------


def build_report(*, skip_github: bool = False, skip_harness: bool = False) -> Report:
    report = Report()
    check_loop_state(report)
    check_chain(report)
    if not skip_github:
        check_stale_issues(report)
        check_pull_requests(report)
        check_advisories(report)
    if not skip_harness:
        check_harness(report)
    return report


def render(report: Report) -> str:
    facts = "\n".join(f"  {k}: {v}" for k, v in sorted(report.facts.items()))
    if not report.findings:
        return f"record coherent — nothing to reconcile\n\n{facts}"
    lines = [f"{len(report.findings)} thing(s) to reconcile:", ""]
    lines += [f.line() for f in report.findings]
    lines += [
        "",
        "A stale-issue hit means a merged commit *cites* the number — often as a residual",
        "tracker rather than as finished work, which is why this reports instead of closing.",
        "",
        facts,
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    ap.add_argument("--skip-github", action="store_true", help="offline checks only")
    ap.add_argument("--skip-harness", action="store_true", help="skip the harness-path gate")
    args = ap.parse_args(argv)

    report = build_report(skip_github=args.skip_github, skip_harness=args.skip_harness)
    if args.json:
        print(
            json.dumps(
                {
                    "findings": [asdict(f) for f in report.findings],
                    "facts": report.facts,
                    "coherent": not report.findings,
                },
                indent=2,
            )
        )
    else:
        print(render(report))
    # Advisory: a finding is something to look at, not a build failure.
    return 0


if __name__ == "__main__":
    sys.exit(main())
