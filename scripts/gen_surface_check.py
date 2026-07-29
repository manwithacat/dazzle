#!/usr/bin/env python3
"""Fail when committed generated surfaces would be rewritten by generators.

Covers the 24h CI class where feature unit tests passed but GitHub stayed red
on stale catalogue / CONTRACT_SURFACE after HM or render changes.

Does **not** write files — only checks. Remediation prints exact regen commands.

Usage::

    python scripts/gen_surface_check.py
    make gen-surface-check   # if wired

Exit 0 = surfaces current. Exit 1 = stale (do not ship without regen + commit).
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def _python() -> str:
    venv_py = REPO / ".venv" / "bin" / "python"
    if venv_py.is_file():
        return str(venv_py)
    return sys.executable


def run_check(*, quiet: bool = False) -> int:
    py = _python()
    rc = 0

    # UX catalogue md + CSS (has --mode=ci)
    cat = subprocess.run(
        [py, str(REPO / "scripts" / "gen_ux_catalogue.py"), "--mode=ci"],
        cwd=REPO,
        check=False,
        capture_output=quiet,
        text=True,
    )
    if cat.returncode != 0:
        rc = 1
        if quiet and cat.stderr:
            print(cat.stderr, file=sys.stderr, end="")
        if quiet and cat.stdout:
            print(cat.stdout, file=sys.stderr, end="")

    # CONTRACT_SURFACE — compare generator stdout to committed file via pytest nodeid
    # (tool has --write only; drift test is the check surface).
    cs = subprocess.run(
        [
            py,
            "-m",
            "pytest",
            "tests/unit/test_contract_surface_tool.py::test_committed_contract_surface_matches_generator",
            "-q",
            "--tb=line",
        ],
        cwd=REPO,
        check=False,
        capture_output=quiet,
        text=True,
    )
    if cs.returncode != 0:
        rc = 1
        if quiet and cs.stdout:
            print(cs.stdout, file=sys.stderr, end="")
        if quiet and cs.stderr:
            print(cs.stderr, file=sys.stderr, end="")

    if rc == 0:
        if not quiet:
            print("OK gen-surface-check: catalogue + CONTRACT_SURFACE current")
        return 0

    print(
        """
╔══════════════════════════════════════════════════════════════════════╗
║  GEN-SURFACE-CHECK FAILED — committed artifacts are stale            ║
║  Regenerate, commit the outputs, then re-run. Do not ship dirty.     ║
╚══════════════════════════════════════════════════════════════════════╝

  .venv/bin/python scripts/gen_ux_catalogue.py
  uv run python packages/hatchi-maxchi/tools/contract_surface.py --write
  # review docs/reference/ux-catalogue.md, docs/assets/dazzle-catalogue.css,
  #        packages/hatchi-maxchi/CONTRACT_SURFACE.md
  git add docs/reference/ux-catalogue.md docs/assets/dazzle-catalogue.css \\
          packages/hatchi-maxchi/CONTRACT_SURFACE.md

Re-run:
  .venv/bin/python scripts/gen_surface_check.py
  make preflight-surface
""",
        file=sys.stderr,
    )
    return 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress OK noise; still print remediation on failure",
    )
    args = parser.parse_args(argv)
    return run_check(quiet=args.quiet)


if __name__ == "__main__":
    raise SystemExit(main())
