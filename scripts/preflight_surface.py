#!/usr/bin/env python3
"""Surface preflight — fail unpaid structural/artifact drift before ship.

# Why this exists

Feature ships kept going green on ad-hoc unit tests while GitHub CI stayed
red for the same cluster every time:

* API surface baselines (``docs/api-surface/*``)
* Docs drift (AGENTS.md MCP table, cli.md groups, generated reference pages)
* Deferred-import / complexity ratchets
* Layer import contracts (``core ↛ page/api_kb``)
* Silent ``except Exception`` swallows
* UX catalogue CSS
* HaTchi-MaXchi gallery stale-dist (HM package suite)

Local ``make ci-fast`` already runs ``pytest -m gate``, but agents routinely
skipped it, or fixed only their new tests and pushed onto a red tip. This
script is a **named, early, hard** gate with remediation text so the pattern
cannot be "accidentally" skipped without reading the failure.

Wired into:

* ``make preflight-surface`` (standalone)
* ``scripts/ci_local.sh`` tier0 + tier1 (**first** step)
* ``/ship`` skill (mandatory before any tier)

Exit 0 = surface clean. Exit 1 = unpaid debt; print playbook; do not ship.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

# Ordered: cheapest / highest-signal first. All must stay gate-marked.
SURFACE_TESTS: tuple[str, ...] = (
    "tests/unit/test_api_surface_drift.py",
    "tests/unit/test_docs_drift.py",
    "tests/unit/test_deferred_imports_ratchet_1438.py",
    "tests/unit/test_import_contracts.py",
    "tests/unit/test_no_bare_except_pass.py",
    "tests/unit/test_ux_catalogue.py",
    "tests/unit/test_complexity_ratchet.py",
    "tests/unit/test_hm_package_suite_gate.py",
)

REMEDIATION = """
╔══════════════════════════════════════════════════════════════════════╗
║  PREFLIGHT-SURFACE FAILED — unpaid structural / artifact debt        ║
║  Do NOT ship or tag until this is green.                             ║
╚══════════════════════════════════════════════════════════════════════╝

Remediation by class (run from repo root, commit the regenerated files):

  API surface baselines
    dazzle inspect api mcp-tools --write
    dazzle inspect api ir-types --write
    dazzle inspect api dsl-constructs --write   # if that cycle drifted
    dazzle inspect api public-helpers --write
    dazzle inspect api runtime-urls --write

  Docs drift (AGENTS MCP table, cli.md groups, generated reference)
    # edit AGENTS.md / docs/reference/cli.md to match registry
    dazzle docs generate

  Deferred-import ratchet (#1438)
    # hoist imports or raise entry in:
    #   tests/unit/fixtures/deferred_imports_baseline.json
    # only when the deferred import is an unavoidable cycle workaround

  Complexity ratchet
    dazzle fitness code --write-baseline   # only after justified increase

  Import contracts (core ↛ page / api_kb / mcp)
    # relocate code; do not allow-list casually
    # validation must use pack-ops registry, not import page/api_kb

  Bare except Exception
    # logger.debug("...", exc_info=True) or narrow the exception type

  UX catalogue CSS
    .venv/bin/python scripts/gen_ux_catalogue.py

  HaTchi-MaXchi gallery (stale site/*)
    cd packages/hatchi-maxchi && python site/build_site.py
    # commit site/hatchi-maxchi.css|js and site/index.html

Re-run:
  make preflight-surface
  # then: make ci-fast   (or make ci-core for version bumps)

See: docs/contributing/local-ci-concordance.md
"""


def _python() -> str:
    venv_py = REPO / ".venv" / "bin" / "python"
    if venv_py.is_file():
        return str(venv_py)
    return sys.executable


def _check_paths_exist() -> list[str]:
    missing = [p for p in SURFACE_TESTS if not (REPO / p).is_file()]
    return missing


def run_preflight(*, quiet: bool = False) -> int:
    missing = _check_paths_exist()
    if missing:
        print("preflight-surface: missing test modules:", file=sys.stderr)
        for m in missing:
            print(f"  - {m}", file=sys.stderr)
        return 2

    py = _python()
    cmd = [
        py,
        "-m",
        "pytest",
        *SURFACE_TESTS,
        "-q",
        "--tb=line",
        "-m",
        "gate",
    ]
    if not quiet:
        print("==> preflight-surface")
        print("    " + " ".join(SURFACE_TESTS))
        print(f"    interpreter: {py}")
    proc = subprocess.run(cmd, cwd=REPO, check=False)
    if proc.returncode == 0:
        if not quiet:
            print("OK preflight-surface clean")
        return 0
    print(REMEDIATION, file=sys.stderr)
    return 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Fail on unpaid API/docs/import/ratchet/HM surface drift. "
            "Mandatory before /ship and as the first step of ci-fast/ci-core."
        )
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress the banner; still print remediation on failure",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="Print the surface test modules and exit 0",
    )
    args = parser.parse_args(argv)
    if args.list:
        for p in SURFACE_TESTS:
            print(p)
        return 0
    return run_preflight(quiet=args.quiet)


if __name__ == "__main__":
    raise SystemExit(main())
