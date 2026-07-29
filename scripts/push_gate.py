#!/usr/bin/env python3
"""Push gate — may this agent push to main?

Closes the 24h CI process gaps that docs alone could not:

1. **Discipline** — refuse push unless a recent local gate stamp matches the
   current worktree fingerprint (agents must run preflight/ship-surface /
   ci-fast, not ad-hoc pytest).
2. **Throttle** — refuse when origin/main already received too many commits
   in the last hour (cancel-storm / supersession noise).
3. **CI tip wait** — refuse product pushes while main ``ci.yml`` is still
   ``in_progress`` (unless ``--repair`` for cimonitor-only fixes).
4. **HM visual plane** — when HaTchi-MaXchi gallery/CSS/controller paths are
   in the diff, require gen-surface clean and print the sibling-CI checklist;
   optional hard wait on standalone green.

Usage::

    # After make ci-fast / ci-core / preflight+ship-surface:
    python scripts/push_gate.py record --tier 0
    python scripts/push_gate.py record --tier surface

    # Before git push (ship / improve land):
    python scripts/push_gate.py check
    python scripts/push_gate.py check --repair          # cimonitor fix while tip running
    python scripts/push_gate.py check --require-hm-green  # release / HM visual ship

    python scripts/push_gate.py status

Exit 0 = allowed / recorded. Exit 1 = blocked (print remediation). Exit 2 = usage.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
STAMP_PATH = REPO / ".dazzle" / "push_gate_stamp.json"

# Stamp validity — re-run gates if older.
STAMP_MAX_AGE = timedelta(minutes=45)

# Cancel-storm control (24h autopsy: ~40% cancelled, many <10m gaps).
MAX_MAIN_COMMITS_PER_HOUR = 4
THROTTLE_WINDOW = timedelta(hours=1)

# Minimum age of newest origin/main commit before another product push
# (repair exempt). Softens thrash when throttle count still has headroom.
MIN_GAP_AFTER_PUSH = timedelta(minutes=8)

# Paths that imply sibling hatchi-maxchi visual / behaviour plane.
HM_VISUAL_PREFIXES = (
    "packages/hatchi-maxchi/components/",
    "packages/hatchi-maxchi/controllers/",
    "packages/hatchi-maxchi/site/",
    "packages/hatchi-maxchi/tests/baselines/",
    "packages/hatchi-maxchi/base/",
    "packages/hatchi-maxchi/tokens/",
    "packages/hatchi-maxchi/families/",
    "packages/hatchi-maxchi/dist/",
)

TIER_RANK = {"surface": 1, "0": 2, "1": 3}


def _python() -> str:
    venv_py = REPO / ".venv" / "bin" / "python"
    if venv_py.is_file():
        return str(venv_py)
    return sys.executable


def _run(
    cmd: list[str],
    *,
    check: bool = False,
    capture: bool = True,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        cwd=REPO,
        check=check,
        capture_output=capture,
        text=True,
    )


def _diff_base() -> str:
    """Base ref for content fingerprint (prefer origin/main)."""
    proc = _run(["git", "rev-parse", "--verify", "origin/main"])
    if proc.returncode == 0:
        return "origin/main"
    return "HEAD"


def tree_fingerprint() -> str:
    """Fingerprint of content-to-ship vs main — stable across commit of the same tree.

    Uses working-tree diff against origin/main (not HEAD alone) so a clean
    ``git commit`` of exactly the gated changes does not invalidate the stamp.
    Any edit after the gates (extra hunks, untracked adds) changes the hash.
    """
    base = _diff_base()
    # Working tree (incl. index) vs base — same before/after commit when all
    # gated dirt is committed and nothing else remains dirty.
    diff_wt = _run(["git", "diff", base]).stdout
    diff_cached = _run(["git", "diff", "--cached", base]).stdout
    # Names of untracked files (content not hashed fully — name list is enough
    # to invalidate when new files appear without being gated).
    untracked = _run(["git", "ls-files", "--others", "--exclude-standard"]).stdout
    porcelain = _run(["git", "status", "--porcelain"]).stdout
    raw = f"{base}\n{diff_wt}\n{diff_cached}\n{untracked}\n{porcelain}".encode()
    return hashlib.sha256(raw).hexdigest()


def _now() -> datetime:
    return datetime.now(UTC)


def _iso(dt: datetime) -> str:
    return dt.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _parse_iso(s: str) -> datetime:
    s = s.strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    return datetime.fromisoformat(s).astimezone(UTC)


def write_stamp(*, tier: str, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    STAMP_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = {
        "at": _iso(_now()),
        "tier": tier,
        "fingerprint": tree_fingerprint(),
        "head": _run(["git", "rev-parse", "HEAD"]).stdout.strip(),
        "host": os.uname().nodename if hasattr(os, "uname") else "unknown",
    }
    if extra:
        payload.update(extra)
    STAMP_PATH.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return payload


def read_stamp() -> dict[str, Any] | None:
    if not STAMP_PATH.is_file():
        return None
    try:
        data = json.loads(STAMP_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def changed_paths_vs_main() -> list[str]:
    files: set[str] = set()
    for cmd in (
        ["git", "diff", "--name-only", "origin/main...HEAD"],
        ["git", "diff", "--name-only", "origin/main"],
        ["git", "diff", "--name-only", "--cached"],
        ["git", "diff", "--name-only"],
    ):
        proc = _run(cmd)
        if proc.returncode == 0 and proc.stdout.strip():
            files.update(ln.strip() for ln in proc.stdout.splitlines() if ln.strip())
    return sorted(files)


def hm_visual_paths(paths: list[str]) -> list[str]:
    return [p for p in paths if any(p.startswith(pref) for pref in HM_VISUAL_PREFIXES)]


def main_commits_in_window(window: timedelta) -> list[tuple[str, datetime]]:
    """Return (short_sha, author_date) for origin/main commits in window."""
    since = _now() - window
    proc = _run(
        [
            "git",
            "log",
            "origin/main",
            f"--since={_iso(since)}",
            "--format=%h\t%aI",
        ]
    )
    if proc.returncode != 0 or not proc.stdout.strip():
        # Fallback: local main
        proc = _run(
            [
                "git",
                "log",
                "main",
                f"--since={_iso(since)}",
                "--format=%h\t%aI",
            ]
        )
    out: list[tuple[str, datetime]] = []
    for line in proc.stdout.splitlines():
        if "\t" not in line:
            continue
        sha, ts = line.split("\t", 1)
        try:
            out.append((sha.strip(), _parse_iso(ts.strip())))
        except ValueError:
            continue
    return out


def probe_main_ci() -> dict[str, Any]:
    """Latest main ci.yml run via gh (best-effort)."""
    proc = _run(
        [
            "gh",
            "run",
            "list",
            "--workflow",
            "ci.yml",
            "--branch",
            "main",
            "--limit",
            "1",
            "--json",
            "status,conclusion,databaseId,url,displayTitle,headSha,createdAt",
        ]
    )
    if proc.returncode != 0:
        return {"status": "unavailable", "error": (proc.stderr or proc.stdout)[:300]}
    try:
        runs = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return {"status": "unavailable", "error": "bad json from gh"}
    if not runs:
        return {"status": "unavailable", "error": "no runs"}
    run = runs[0]
    st = run.get("status") or ""
    conc = run.get("conclusion") or ""
    if st in ("in_progress", "queued", "waiting", "requested", "pending"):
        label = "in_progress"
    elif conc == "success":
        label = "green"
    elif conc in ("failure", "timed_out", "cancelled"):
        label = "red" if conc != "cancelled" else "cancelled"
    else:
        label = st or "unknown"
    return {
        "status": label,
        "raw_status": st,
        "conclusion": conc,
        "id": run.get("databaseId"),
        "url": run.get("url"),
        "title": run.get("displayTitle"),
        "sha": (run.get("headSha") or "")[:9],
    }


def run_gen_surface() -> int:
    return subprocess.run(
        [_python(), str(REPO / "scripts" / "gen_surface_check.py"), "--quiet"],
        cwd=REPO,
        check=False,
    ).returncode


def run_hm_standalone() -> int:
    script = REPO / "scripts" / "hm_standalone_ci_status.py"
    return subprocess.run(
        [_python(), str(script), "--prefer-completed"],
        cwd=REPO,
        check=False,
    ).returncode


def cmd_record(tier: str) -> int:
    if tier not in TIER_RANK:
        print(f"push_gate: unknown tier {tier!r} (use surface|0|1)", file=sys.stderr)
        return 2
    payload = write_stamp(tier=tier)
    print(
        f"OK push_gate stamp recorded tier={tier} "
        f"fingerprint={payload['fingerprint'][:12]}… at={payload['at']}"
    )
    print(f"    stamp: {STAMP_PATH.relative_to(REPO)}")
    return 0


def cmd_status() -> int:
    stamp = read_stamp()
    fp = tree_fingerprint()
    print(f"fingerprint_now={fp[:16]}…")
    if not stamp:
        print("stamp: missing")
    else:
        age_ok = True
        try:
            age = _now() - _parse_iso(str(stamp.get("at", "")))
            age_ok = age <= STAMP_MAX_AGE
            print(
                f"stamp: tier={stamp.get('tier')} at={stamp.get('at')} "
                f"fp_match={stamp.get('fingerprint') == fp} age_ok={age_ok}"
            )
        except (TypeError, ValueError):
            print(f"stamp: unreadable at={stamp.get('at')!r}")
    commits = main_commits_in_window(THROTTLE_WINDOW)
    print(f"main_commits_last_hour={len(commits)} (max {MAX_MAIN_COMMITS_PER_HOUR})")
    if commits:
        newest = max(c[1] for c in commits)
        gap = _now() - newest
        print(f"newest_main_commit_age_min={gap.total_seconds() / 60:.1f}")
    ci = probe_main_ci()
    print(f"main_ci={ci.get('status')} id={ci.get('id')} sha={ci.get('sha')}")
    hm = hm_visual_paths(changed_paths_vs_main())
    print(f"hm_visual_paths={len(hm)}")
    for p in hm[:8]:
        print(f"  {p}")
    return 0


def _block(msg: str, *, remediation: str) -> int:
    print(
        f"""
╔══════════════════════════════════════════════════════════════════════╗
║  PUSH GATE BLOCKED                                                   ║
╚══════════════════════════════════════════════════════════════════════╝
{msg}

Remediation:
{remediation}
""",
        file=sys.stderr,
    )
    return 1


def cmd_check(
    *,
    repair: bool = False,
    require_hm_green: bool = False,
    min_tier: str = "surface",
    skip_throttle: bool = False,
    skip_ci_wait: bool = False,
) -> int:
    if min_tier not in TIER_RANK:
        print(f"push_gate: unknown min-tier {min_tier!r}", file=sys.stderr)
        return 2

    # --- 1. Stamp discipline ---
    stamp = read_stamp()
    fp = tree_fingerprint()
    if not stamp:
        return _block(
            "No push_gate stamp — local Tier 0 / surface gates were not recorded.",
            remediation="""  make preflight-surface && make ship-surface
  # preferred full ship path:
  make ci-fast
  # stamp is written automatically by ci_local tier0/tier1; or:
  python scripts/push_gate.py record --tier surface   # after preflight+ship-surface
  python scripts/push_gate.py record --tier 0         # after ci-fast
  python scripts/push_gate.py check""",
        )
    try:
        age = _now() - _parse_iso(str(stamp["at"]))
    except (KeyError, TypeError, ValueError):
        return _block(
            "Push gate stamp is corrupt.",
            remediation="  re-run make ci-fast  # rewrites stamp",
        )
    if age > STAMP_MAX_AGE:
        return _block(
            f"Push gate stamp is stale ({age.total_seconds() / 60:.0f}m old; max {STAMP_MAX_AGE.seconds // 60}m).",
            remediation="  make ci-fast   # or preflight + ship-surface + push_gate record",
        )
    if stamp.get("fingerprint") != fp:
        return _block(
            "Worktree changed after the gate stamp (edit without re-running gates).",
            remediation="""  # re-run the gates on the current tree, then re-check:
  make preflight-surface
  make ship-surface
  make ci-fast          # recommended for /ship
  python scripts/push_gate.py check""",
        )
    stamped_tier = str(stamp.get("tier") or "")
    if TIER_RANK.get(stamped_tier, 0) < TIER_RANK[min_tier]:
        return _block(
            f"Stamp tier={stamped_tier!r} is below required min-tier={min_tier!r}.",
            remediation=f"  make ci-fast   # records tier 0\n  # or: python scripts/push_gate.py record --tier {min_tier}",
        )

    # --- 2. Throttle ---
    if not skip_throttle and not repair:
        commits = main_commits_in_window(THROTTLE_WINDOW)
        if len(commits) >= MAX_MAIN_COMMITS_PER_HOUR:
            newest = max(c[1] for c in commits)
            wait_m = max(0.0, (THROTTLE_WINDOW - (_now() - newest)).total_seconds() / 60)
            return _block(
                f"Push throttle: {len(commits)} commits on main in the last hour "
                f"(max {MAX_MAIN_COMMITS_PER_HOUR}). Cancel-storm control.",
                remediation=f"""  Batch related fixes into one push.
  Wait ~{wait_m:.0f}m or until the hour window slides.
  Cimonitor-only repair: python scripts/push_gate.py check --repair
  Status: python scripts/push_gate.py status""",
            )
        if commits:
            newest = max(c[1] for c in commits)
            gap = _now() - newest
            if gap < MIN_GAP_AFTER_PUSH:
                wait_s = (MIN_GAP_AFTER_PUSH - gap).total_seconds()
                return _block(
                    f"Push gap: newest main commit is only {gap.total_seconds() / 60:.1f}m old "
                    f"(min {MIN_GAP_AFTER_PUSH.seconds // 60}m between product pushes).",
                    remediation=f"""  Wait ~{wait_s / 60:.1f}m for the prior CI run to get signal,
  or batch more changes into this commit.
  Cimonitor repair: python scripts/push_gate.py check --repair""",
                )

    # --- 3. CI tip wait ---
    if not skip_ci_wait and not repair:
        ci = probe_main_ci()
        if ci.get("status") == "in_progress":
            return _block(
                f"Main CI still in_progress (run #{ci.get('id')} {ci.get('sha')} — "
                f"{ci.get('title')}). Pushing now cancels/supersedes signal.",
                remediation=f"""  Poll: gh run watch {ci.get("id")}
  Or wait for completion, then ship.
  Cimonitor-only while tip is red/running: python scripts/push_gate.py check --repair
  URL: {ci.get("url")}""",
            )

    # --- 4. HM visual plane ---
    paths = changed_paths_vs_main()
    hm_paths = hm_visual_paths(paths)
    if hm_paths:
        print("==> push_gate: HM visual plane paths in diff:")
        for p in hm_paths[:12]:
            print(f"    {p}")
        if len(hm_paths) > 12:
            print(f"    … +{len(hm_paths) - 12} more")
        grc = run_gen_surface()
        if grc != 0:
            return _block(
                "HM visual plane: gen-surface-check failed (catalogue / CONTRACT_SURFACE).",
                remediation="""  python scripts/gen_ux_catalogue.py
  uv run python packages/hatchi-maxchi/tools/contract_surface.py --write
  # commit regenerated files
  python scripts/gen_surface_check.py
  make ci-fast
  python scripts/push_gate.py check""",
            )
        print(
            """
HM release-plane checklist (sibling hatchi-maxchi owns Linux visual/behaviour):
  1. Monorepo: catalogue + CONTRACT_SURFACE + package suite green (local).
  2. Push monorepo; ensure Sync HaTchi-MaXchi workflow ran for this tip.
  3. Wait: python scripts/hm_standalone_ci_status.py --prefer-completed
  4. If Visual red: update Linux baselines via sibling CI artifact — do not
     thrash monorepo CSS hoping macOS matches Linux.
  5. Do not tag a release while sibling CI is red.
"""
        )
        if require_hm_green or os.environ.get("SHIP_REQUIRE_HM", "").strip() in (
            "1",
            "true",
            "yes",
        ):
            hrc = run_hm_standalone()
            if hrc != 0:
                return _block(
                    "HM standalone CI is not green (--require-hm-green / SHIP_REQUIRE_HM).",
                    remediation="""  python scripts/hm_standalone_ci_status.py --prefer-completed
  # fix sibling visual/behaviour, update Linux baselines, re-sync, re-check
  # product monorepo-only ships may omit --require-hm-green but must not tag""",
                )
            print("OK HM standalone CI green")

    print(
        f"OK push_gate: allowed "
        f"(tier>={min_tier}, stamp={stamp.get('tier')}, "
        f"repair={repair}, hm_paths={len(hm_paths)})"
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Record local gate stamps and allow/deny git push to main."
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_rec = sub.add_parser("record", help="Record stamp after successful local gates")
    p_rec.add_argument(
        "--tier",
        choices=sorted(TIER_RANK.keys()),
        required=True,
        help="surface=preflight+ship-surface; 0=ci-fast; 1=ci-core",
    )

    p_chk = sub.add_parser("check", help="Allow or block push")
    p_chk.add_argument(
        "--repair",
        action="store_true",
        help="Cimonitor/repair push: skip throttle + CI in_progress wait",
    )
    p_chk.add_argument(
        "--require-hm-green",
        action="store_true",
        help="When HM visual paths present, require sibling CI green",
    )
    p_chk.add_argument(
        "--min-tier",
        default="surface",
        choices=sorted(TIER_RANK.keys()),
        help="Minimum stamp tier (default surface; /ship should use 0)",
    )
    p_chk.add_argument(
        "--skip-throttle",
        action="store_true",
        help="Skip commit-rate throttle (tests / operator override)",
    )
    p_chk.add_argument(
        "--skip-ci-wait",
        action="store_true",
        help="Skip main CI in_progress wait (tests / operator override)",
    )

    sub.add_parser("status", help="Print stamp, throttle, CI, HM path status")

    args = parser.parse_args(argv)
    if args.cmd == "record":
        return cmd_record(args.tier)
    if args.cmd == "status":
        return cmd_status()
    if args.cmd == "check":
        return cmd_check(
            repair=args.repair,
            require_hm_green=args.require_hm_green,
            min_tier=args.min_tier,
            skip_throttle=args.skip_throttle,
            skip_ci_wait=args.skip_ci_wait,
        )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
