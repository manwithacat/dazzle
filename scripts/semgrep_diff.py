#!/usr/bin/env python3
"""Diff-scoped Semgrep security scan for agent / improve hygiene.

Default targets are git-changed paths (working tree + staged, or commits
against a base). Packs mirror the Claude-era security surface the codebase
still documents with ``# nosemgrep``:

  - p/python
  - p/owasp-top-ten
  - p/security-audit  (when registry reachable)

Also supports the shipped Sentinel modernisation ruleset via ``--sentinel``.

Exit codes:
  0 — no findings (or only INFO when ``--min-severity`` filters them)
  1 — findings at/above min severity
  2 — tooling / config error
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
SENTINEL_RULES = REPO / "src" / "dazzle" / "sentinel" / "rules" / "python_audit.yml"

# Registry packs used for agent/security hygiene (not CI-hard).
DEFAULT_CONFIGS = (
    "p/python",
    "p/owasp-top-ten",
    "p/security-audit",
)

SCAN_EXTS = {".py", ".js", ".ts", ".tsx", ".jsx", ".yml", ".yaml", ".toml", ".html"}
SKIP_DIR_PARTS = {
    ".venv",
    "node_modules",
    "__pycache__",
    ".git",
    "dist",
    "build",
    "site-packages",
    "tests/baselines",
    "packages/hatchi-maxchi/tests/baselines",
}


def _which_semgrep() -> str | None:
    return shutil.which("semgrep")


def _git_changed(base: str | None, staged_only: bool) -> list[Path]:
    cmds: list[list[str]] = []
    if staged_only:
        cmds.append(["git", "diff", "--name-only", "--cached"])
    elif base:
        cmds.append(["git", "diff", "--name-only", f"{base}...HEAD"])
        cmds.append(["git", "diff", "--name-only"])
        cmds.append(["git", "diff", "--name-only", "--cached"])
    else:
        cmds.append(["git", "diff", "--name-only", "HEAD"])
        cmds.append(["git", "diff", "--name-only", "--cached"])
        # Untracked (new) files in the worktree
        cmds.append(["git", "ls-files", "--others", "--exclude-standard"])

    names: set[str] = set()
    for cmd in cmds:
        try:
            out = subprocess.check_output(cmd, cwd=REPO, text=True)
        except (subprocess.CalledProcessError, FileNotFoundError):
            continue
        for line in out.splitlines():
            line = line.strip()
            if line:
                names.add(line)

    paths: list[Path] = []
    for name in sorted(names):
        p = REPO / name
        if not p.is_file():
            continue
        if p.suffix.lower() not in SCAN_EXTS:
            continue
        if any(part in p.parts for part in SKIP_DIR_PARTS):
            continue
        # Skip pure test noise unless explicitly under src/
        rel = p.relative_to(REPO).as_posix()
        if rel.startswith("tests/") and not rel.startswith("tests/security"):
            continue
        paths.append(p)
    return paths


def _run_semgrep(
    configs: list[str],
    targets: list[Path],
    *,
    quiet: bool,
) -> dict[str, Any]:
    sg = _which_semgrep()
    if not sg:
        raise RuntimeError("semgrep not on PATH — install via brew/pipx/uv")

    if not targets:
        return {"results": [], "errors": [], "paths": {"scanned": []}}

    cmd = [sg, "scan", "--json", "--metrics=off", "--disable-version-check"]
    for c in configs:
        cmd.extend(["--config", c])
    cmd.extend(str(t) for t in targets)

    # Registry configs may 404 offline; fall back to what works.
    proc = subprocess.run(
        cmd,
        cwd=REPO,
        capture_output=True,
        text=True,
        timeout=600,
    )
    raw = proc.stdout.strip()
    if not raw:
        # Common when all configs failed to load
        err = (proc.stderr or "").strip()
        if "Failed to download" in err or "Invalid configuration" in err:
            raise RuntimeError(f"semgrep config error:\n{err[:2000]}")
        return {"results": [], "errors": [{"message": err[:500]}], "paths": {}}

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"semgrep JSON parse failed: {exc}\n{raw[:500]}") from exc
    if not quiet and proc.stderr:
        # progress noise on stderr is normal
        pass
    return data


def _severity_rank(sev: str) -> int:
    order = {"ERROR": 3, "WARNING": 2, "INFO": 1}
    return order.get(sev.upper(), 0)


def _min_rank(name: str) -> int:
    return {"error": 3, "warning": 2, "info": 1}.get(name.lower(), 2)


def _format_table(results: list[dict[str, Any]], limit: int) -> str:
    lines = [
        f"{'SEV':<8} {'RULE':<48} {'PATH'}",
        "-" * 100,
    ]
    for item in results[:limit]:
        extra = item.get("extra") or {}
        sev = str(extra.get("severity") or "INFO").upper()
        check = str(item.get("check_id") or "")
        path = str(item.get("path") or "")
        start = (item.get("start") or {}).get("line", "?")
        lines.append(f"{sev:<8} {check[:48]:<48} {path}:{start}")
        msg = (extra.get("message") or "").strip().splitlines()
        if msg:
            lines.append(f"         {msg[0][:120]}")
    if len(results) > limit:
        lines.append(f"… {len(results) - limit} more")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--base",
        default=None,
        help="git merge-base style ref for changed files (e.g. origin/main)",
    )
    ap.add_argument(
        "--staged",
        action="store_true",
        help="only staged files",
    )
    ap.add_argument(
        "--paths",
        nargs="*",
        default=None,
        help="explicit paths (skip git diff selection)",
    )
    ap.add_argument(
        "--all-src",
        action="store_true",
        help="scan src/dazzle (security packs; slower)",
    )
    ap.add_argument(
        "--sentinel",
        action="store_true",
        help="use shipped Sentinel python_audit.yml instead of registry packs",
    )
    ap.add_argument(
        "--config",
        action="append",
        default=None,
        help="extra/override --config (repeatable); default = registry packs",
    )
    ap.add_argument(
        "--min-severity",
        default="warning",
        choices=("info", "warning", "error"),
        help="exit 1 when findings ≥ this (default: warning)",
    )
    ap.add_argument("--json", action="store_true", help="print raw JSON results")
    ap.add_argument("--limit", type=int, default=40, help="max findings to print")
    ap.add_argument("-q", "--quiet", action="store_true")
    args = ap.parse_args(argv)

    if args.sentinel:
        if not SENTINEL_RULES.is_file():
            print(f"missing sentinel rules: {SENTINEL_RULES}", file=sys.stderr)
            return 2
        configs = [str(SENTINEL_RULES)]
    elif args.config:
        configs = list(args.config)
    else:
        configs = list(DEFAULT_CONFIGS)

    if args.paths:
        targets = [Path(p).resolve() for p in args.paths if Path(p).is_file() or Path(p).is_dir()]
    elif args.all_src:
        targets = [REPO / "src" / "dazzle"]
    else:
        targets = _git_changed(args.base, args.staged)

    if not targets:
        if not args.quiet:
            print("semgrep_diff: no scannable targets (empty diff / filters)")
        print(json.dumps({"ok": True, "findings": 0, "targets": 0}))
        return 0

    # Prefer file list; for dirs pass as-is
    try:
        data = _run_semgrep(configs, targets, quiet=args.quiet)
    except RuntimeError as exc:
        # Retry without security-audit if that pack is the failure mode
        if "p/security-audit" in configs and len(configs) > 1:
            configs = [c for c in configs if c != "p/security-audit"]
            if not args.quiet:
                print("semgrep_diff: retrying without p/security-audit", file=sys.stderr)
            try:
                data = _run_semgrep(configs, targets, quiet=args.quiet)
            except RuntimeError as exc2:
                print(exc2, file=sys.stderr)
                return 2
        else:
            print(exc, file=sys.stderr)
            return 2

    results = list(data.get("results") or [])
    floor = _min_rank(args.min_severity)
    actionable = [
        r
        for r in results
        if _severity_rank(str((r.get("extra") or {}).get("severity") or "INFO")) >= floor
    ]

    # Sort ERROR first
    actionable.sort(
        key=lambda r: -_severity_rank(str((r.get("extra") or {}).get("severity") or "INFO"))
    )

    summary = {
        "ok": len(actionable) == 0,
        "findings": len(actionable),
        "findings_all_severities": len(results),
        "targets": len(targets),
        "configs": configs,
        "min_severity": args.min_severity,
    }

    if args.json:
        print(json.dumps({"summary": summary, "results": actionable}, indent=2))
    else:
        print(json.dumps(summary))
        if actionable and not args.quiet:
            print()
            print(_format_table(actionable, args.limit))

    return 0 if not actionable else 1


if __name__ == "__main__":
    raise SystemExit(main())
