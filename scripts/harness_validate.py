#!/usr/bin/env python3
"""Rehearse the `/improve` loop's mechanics, end to end, on this host.

Every gate in this repository checks that a *piece* of the harness is sound. None
checks that the loop **runs**: its steps execute in order, each produces a verdict,
and none leaves an agent at a dead end. That gap is not theoretical — seven
harness-changing commits landed after the last live cycle (2412), including the
toolchain probe in Step 0b, the parked-work guard in the inbox, the
findings-versus-staleness split, the belief stamp, and the chain marker. The loop
has never been executed with any of them.

    uv run python scripts/harness_validate.py            # human summary
    uv run python scripts/harness_validate.py --json     # machine-readable
    uv run python scripts/harness_validate.py --quick   # skip the two slow gates

Exit codes are the point:

    0  every mandatory step ran and answered; every unavailable step logged why
    1  a mandatory step could not run here — a dead end for a cycle on this host
    2  a step produced no verdict at all (silent) — worse than unavailable

The distinction the whole harness has been learning: *absent* is a fact,
*unavailable* is a fact with a reason, and *silent* is the failure.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

OK = "ok"
DEGRADED = "degraded"  # ran, but a dependency was absent — and it said so
UNAVAILABLE = "unavailable"  # could not run, with a logged reason
BLOCKED = "blocked"  # ran and refused: a real dead end
SILENT = "silent"  # no verdict — the only unacceptable outcome


@dataclass
class Step:
    name: str
    status: str
    detail: str = ""
    mandatory: bool = False
    seconds: float = 0.0
    stdout_tail: str = ""

    def line(self) -> str:
        mark = {
            OK: "ok  ",
            DEGRADED: "degr",
            BLOCKED: "BLK ",
            UNAVAILABLE: "unav",
            SILENT: "SILENT",
        }[self.status]
        flag = " (mandatory)" if self.mandatory else ""
        return f"[{mark}] {self.name}{flag:<13} {self.detail}"


def _run(cmd: list[str], timeout: int = 900) -> tuple[int, str, str]:
    try:
        proc = subprocess.run(
            cmd, cwd=REPO, capture_output=True, text=True, timeout=timeout, check=False
        )
        return proc.returncode, proc.stdout, proc.stderr
    except subprocess.TimeoutExpired:
        return 124, "", f"timed out after {timeout}s"
    except (OSError, subprocess.SubprocessError) as exc:
        return 127, "", f"{type(exc).__name__}: {exc}"


def _tail(text: str, n: int = 160) -> str:
    flat = " ".join(text.split())
    return flat[-n:] if len(flat) > n else flat


# ---------------------------------------------------------------------------
# Steps, in driver order
# ---------------------------------------------------------------------------


def step_0a_lock() -> Step:
    """Lock acquire → stale takeover → release, in a temp dir.

    A lock that cannot be taken, or that a stale holder keeps, is a dead end at
    the very first step of every cycle."""
    import time

    with tempfile.TemporaryDirectory() as tmp:
        lock = Path(tmp) / "improve.lock"
        lock.write_text(f"{os.getpid()} fresh\n", encoding="utf-8")
        # A fresh lock must be refused.
        age = time.time() - lock.stat().st_mtime
        if age < 900:
            refused = True
        else:
            refused = False
        # A stale lock must be reclaimable.
        old = time.time() - 3600
        os.utime(lock, (old, old))
        reclaimed = time.time() - lock.stat().st_mtime >= 900
        lock.unlink()
    if not refused:
        return Step("0a lock", SILENT, "a fresh lock was not distinguishable from a stale one")
    if not reclaimed:
        return Step("0a lock", BLOCKED, "a stale lock could not be reclaimed")
    return Step("0a lock", OK, "fresh refused, stale reclaimed, released")


def _gate(name: str, cmd: list[str], mandatory: bool, timeout: int = 900) -> Step:
    code, out, err = _run(cmd, timeout=timeout)
    detail = _tail(out or err)
    if code == 0:
        return Step(name, OK, detail, mandatory)
    # A gate that cannot run here is a dead end: Step 0b says STOP and fix.
    return Step(name, BLOCKED if mandatory else DEGRADED, f"exit {code}: {detail}", mandatory)


def step_0b_preflight(quick: bool) -> list[Step]:
    steps = [_gate("0b preflight", ["make", "preflight-surface"], mandatory=True)]
    if not quick:
        steps.append(_gate("0b ux-preflight", ["make", "test-ux-preflight"], mandatory=True))
    else:
        steps.append(Step("0b ux-preflight", DEGRADED, "skipped (--quick)", mandatory=True))
    code, out, err = _run([sys.executable, "scripts/improve_toolchain.py", "--status"], timeout=180)
    if code != 0:
        return steps + [Step("0b toolchain", SILENT, f"probe exited {code}: {_tail(err)}")]
    text = out
    if "capabilities available" not in text:
        return steps + [Step("0b toolchain", SILENT, f"probe printed no verdict: {_tail(text)}")]
    missing = text.count("[MISS]")
    total = text.count("[ok  ]") + missing
    status = OK if missing == 0 else DEGRADED
    return steps + [
        Step(
            "0b toolchain",
            status,
            f"{total - missing}/{total} capabilities present"
            + (
                f"; absent: {[ln.split()[1] for ln in text.splitlines() if '[MISS]' in ln]}"
                if missing
                else ""
            ),
        )
    ]


def _head_sha() -> str | None:
    code, out, _ = _run(["git", "rev-parse", "origin/main"], timeout=60)
    if code != 0:
        return None
    return out.strip() or None


def step_0c_ci() -> Step:
    """CI badge for the head of `main`, read from the check-runs API for a known
    SHA.

    Not `gh run list`: through this client that listing returned a 2026-07-31 run
    and then a 2026-06-23 run for the same branch minutes apart, while the badge
    was red throughout (4 failing checks on a6097e293). A rehearsal step that
    can read green from a red badge is worse than no step — a false green produced
    by the instrument meant to detect false greens. `gh` absent, or an answer with
    no verdict in it, reads as unavailable rather than as a pass.
    """
    if not _gh_available():
        return Step(
            "0c ci-badge", UNAVAILABLE, "gh unavailable — the driver logs `ci: unavailable`"
        )
    sha = _head_sha()
    if sha is None:
        return Step("0c ci-badge", UNAVAILABLE, "cannot resolve origin/main")
    jq = (
        "{total: .total_count,"
        ' failing: [.check_runs[] | select(.conclusion=="failure")] | length,'
        ' running: [.check_runs[] | select(.status!="completed")] | length}'
    )
    code, out, err = _run(
        ["gh", "api", f"repos/manwithacat/dazzle/commits/{sha}/check-runs", "--jq", jq],
        timeout=180,
    )
    if code != 0:
        return Step("0c ci-badge", UNAVAILABLE, f"check-runs API exited {code}: {_tail(err)}")
    try:
        data = json.loads(out)
    except json.JSONDecodeError:
        return Step("0c ci-badge", SILENT, f"unparseable: {_tail(out)}")
    if "failing" not in data:
        return Step("0c ci-badge", SILENT, f"no verdict in the answer: {_tail(out)}")
    failing, running, total = data["failing"], data["running"], data["total"]
    detail = f"main {sha[:9]}: {total} checks, {failing} failing, {running} running"
    if failing:
        return Step(
            "0c ci-badge",
            DEGRADED,
            detail + " — a cycle would be CI repair, not product work (Step 0c pre-empts)",
        )
    return Step("0c ci-badge", OK, detail)


def step_0c2_codeql() -> Step:
    if not _gh_available():
        return Step(
            "0c2 codeql", UNAVAILABLE, "gh unavailable — the driver logs `codeql: unavailable`"
        )
    code, out, _ = _run(
        [
            "gh",
            "api",
            "repos/manwithacat/dazzle/code-scanning/alerts",
            "--jq",
            '[.[] | select(.state=="open")] | length',
        ],
        timeout=120,
    )
    if code != 0:
        return Step("0c2 codeql", UNAVAILABLE, f"gh exited {code}")
    try:
        open_alerts = int(out.strip())
    except ValueError:
        return Step("0c2 codeql", SILENT, f"non-numeric alert count: {_tail(out)}")
    if open_alerts:
        return Step(
            "0c2 codeql",
            BLOCKED,
            f"{open_alerts} open alert(s) — this cycle would be CodeQL repair",
        )
    return Step("0c2 codeql", OK, "0 open alerts")


def step_0c3_inbox() -> Step:
    code, out, err = _run(
        [sys.executable, "scripts/improve_github_inbox.py", "--no-write-state"], timeout=300
    )
    if code != 0:
        return Step("0c3 inbox", UNAVAILABLE, f"probe exited {code}: {_tail(err)}")
    try:
        data = json.loads(out)
    except json.JSONDecodeError:
        return Step("0c3 inbox", SILENT, f"unparseable: {_tail(out)}")
    counts = data.get("counts", {})
    recommended = data.get("recommended") or []
    if not isinstance(recommended, list):
        recommended = []
    parked = [
        i["number"] for i in data.get("other_issues", []) if i.get("class") == "deferred_future"
    ]
    detail = (
        f"{counts.get('open_issues', '?')} open, {counts.get('open_prs', '?')} PRs, "
        f"{len(parked)} parked, recommended: "
        f"{[r.get('issue', '?') for r in recommended] or '-'}"
    )
    return Step("0c3 inbox", OK, detail)


def step_0d_signals() -> Step:
    code, out, err = _run(
        [
            sys.executable,
            "-c",
            "from dazzle.cli.runtime_impl.ux_cycle_signals import since_last_run;"
            "print(len(since_last_run(source='improve')))",
        ],
        timeout=180,
    )
    if code != 0:
        return Step("0d signals", UNAVAILABLE, f"read failed: {_tail(err)}")
    return Step("0d signals", OK, f"{out.strip()} fresh signal(s) since the last cycle")


def step_0e_compaction() -> Step:
    """The threshold check itself, not the compaction — a rehearsal must not
    mutate state."""
    backlog = REPO / "dev_docs" / "improve-backlog.md"
    if not backlog.is_file():
        return Step("0e compaction", UNAVAILABLE, "no backlog file")
    size = backlog.stat().st_size / 1024
    if size > 100:
        return Step(
            "0e compaction",
            DEGRADED,
            f"backlog {size:.0f} KB over the 100 KB line — a cycle would compact (run: "
            "python scripts/improve_compact.py)",
        )
    return Step("0e compaction", OK, f"backlog {size:.0f} KB, under the line")


def step_1_selection() -> Step:
    code, out, err = _run([sys.executable, "scripts/improve_policy.py", "--pick"], timeout=300)
    if code != 0:
        return Step(
            "1 selection", SILENT, f"policy --pick exited {code}: {_tail(err)}", mandatory=True
        )
    if not out.strip():
        return Step(
            "1 selection",
            OK,
            "no pick (nothing selectable) — must be explicit, not empty-by-accident",
        )
    pick = out.strip().split()[0]
    code2, out2, _ = _run([sys.executable, "scripts/improve_policy.py", "--status"], timeout=300)
    reason = ""
    for line in out2.splitlines():
        if line.startswith("pick "):
            reason = line[5:].strip()
            break
    return Step("1 selection", OK, f"pick={pick}; {reason}"[:200], mandatory=True)


def step_2_capability_declarations() -> Step:
    """Every strategy a selection could reach must declare its toolchain, and a
    `USED` map row must carry a belief. Both are gates; this confirms they run."""
    gates = [
        ("toolchain declarations", "tests/unit/test_toolchain_probe.py"),
        ("belief stamps", "tests/unit/test_capability_map_beliefs.py"),
        ("harness paths", "tests/unit/test_improve_harness_paths.py"),
        ("command surface", "tests/unit/test_harness_command_surface.py"),
        ("documented commands", "tests/unit/test_documented_commands.py"),
    ]
    failed = []
    for label, path in gates:
        code, out, err = _run(
            [sys.executable, "-m", "pytest", path, "-q", "--tb=line"], timeout=600
        )
        if code != 0:
            failed.append(f"{label} ({_tail(out or err, 90)})")
    if failed:
        return Step("2 declarations", BLOCKED, "; ".join(failed), mandatory=True)
    return Step("2 declarations", OK, f"{len(gates)} declaration gates green", mandatory=True)


def step_6_schedule() -> Step:
    code, out, err = _run(
        [
            sys.executable,
            "scripts/improve_schedule_next.py",
            "--result",
            "PASS",
            "--ci",
            "green",
            "--no-write-state",
            "--chain-armed",
            "0",
        ],
        timeout=300,
    )
    if code != 0:
        return Step("6 schedule", SILENT, f"exited {code}: {_tail(err)}", mandatory=True)
    try:
        data = json.loads(out)
    except json.JSONDecodeError:
        return Step("6 schedule", SILENT, f"unparseable: {_tail(out)}", mandatory=True)
    for key in ("action", "interval", "chain_armed", "chain_blocked_reason", "scheduler_create"):
        if key not in data:
            return Step("6 schedule", SILENT, f"decision is missing {key!r}", mandatory=True)
    armed = data["chain_armed"]
    return Step(
        "6 schedule",
        OK,
        f"action={data['action']} interval={data['interval']} chain_armed={armed}"
        + ("" if armed else " (marker recorded — a host without scheduler_create)"),
        mandatory=True,
    )


def step_reconcile() -> Step:
    code, out, err = _run(
        [sys.executable, "scripts/repo_reconcile.py", "--skip-harness"], timeout=600
    )
    if code != 0:
        return Step("reconcile", UNAVAILABLE, f"exited {code}: {_tail(err)}")
    actionable = out.count("[action]")
    notice = out.count("[notice]")
    return Step(
        "reconcile",
        OK if actionable == 0 else DEGRADED,
        f"{actionable} actionable, {notice} notice",
    )


# ---------------------------------------------------------------------------


def _gh_available() -> bool:
    from shutil import which

    if which("gh") is None:
        return False
    proc = subprocess.run(
        ["gh", "auth", "status"], capture_output=True, text=True, timeout=60, check=False
    )
    return proc.returncode == 0


def validate(*, quick: bool = False) -> list[Step]:
    steps: list[Step] = [step_0a_lock()]
    steps += step_0b_preflight(quick)
    steps += [
        step_0c_ci(),
        step_0c2_codeql(),
        step_0c3_inbox(),
        step_0d_signals(),
        step_0e_compaction(),
        step_1_selection(),
        step_2_capability_declarations(),
        step_6_schedule(),
        step_reconcile(),
    ]
    return steps


def verdict(steps: list[Step]) -> tuple[int, str]:
    silent = [s for s in steps if s.status == SILENT]
    if silent:
        return 2, f"{len(silent)} step(s) produced no verdict: {[s.name for s in silent]}"
    blocked = [s for s in steps if s.status == BLOCKED]
    if blocked:
        return 1, f"{len(blocked)} mandatory step(s) blocked: {[s.name for s in blocked]}"
    degraded = [s for s in steps if s.status == DEGRADED]
    note = f" ({len(degraded)} degraded with a logged reason)" if degraded else ""
    return 0, f"every step ran and answered{note}"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--quick", action="store_true", help="skip the two slow gates")
    args = ap.parse_args(argv)

    steps = validate(quick=args.quick)
    code, summary = verdict(steps)

    if args.json:
        print(
            json.dumps(
                {"verdict": summary, "exit": code, "steps": [asdict(s) for s in steps]}, indent=2
            )
        )
        return code

    print("harness rehearsal — /improve loop mechanics on this host\n")
    for step in steps:
        print(f"  {step.line()}")
    print(f"\n{summary}")
    return code


if __name__ == "__main__":
    sys.exit(main())
