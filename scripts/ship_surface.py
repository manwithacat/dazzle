#!/usr/bin/env python3
"""Ship-surface pack — recurrent CI red classes that Tier 0 used to miss.

# Why this exists

``make ci-fast`` (Tier 0) was green while GitHub stayed red on a rotating set
of *deterministic, cheap* checks:

* bandit medium on ``src/`` (e.g. B324 hashlib)
* example SPECIFICATION.md freshness after DSL edits
* simple_task brief golden + IR golden snapshot
* patterns.toml ``pattern_count`` meta
* IR reader orphan baseline
* viewport DRAWER_PATTERN selector freshness (browser-free)

These are **not** Postgres/Playwright Tier 2. They belong in the ship path so
agents do not discover them only after a full ``ci.yml`` matrix multiplies one
failure × 3 Pythons.

Wired into:

* ``make ship-surface`` / ``bash scripts/ci_local.sh ship-surface``
* ``scripts/ci_local.sh`` tier0 (**after** preflight-surface, before long gate suite)
* ``/ship`` skill (part of Tier 0)

Exit 0 = pack clean. Exit 1 = unpaid debt; print playbook; do not ship.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

# Ordered: cheapest / highest-signal first. Prefer nodeids when the whole
# module is large or mixed.
SHIP_TESTS: tuple[str, ...] = (
    "tests/unit/test_example_spec_bar.py",
    "tests/unit/test_example_product_maturity.py",
    "tests/unit/test_demo_fleet_bar.py",
    "tests/unit/test_improve_example_probes.py",
    "tests/unit/test_nav_platform_isolation_1626.py",
    "tests/unit/test_human_create_cta_label.py",
    "tests/unit/test_dashboard_card_remove_gating.py",
    "tests/unit/test_spec_narrative_brief_snapshot.py",
    "tests/unit/test_patterns_phase2_kb_1217.py::test_pattern_count_meta_matches_actual_count",
    "tests/unit/test_patterns_subtype_of_kb_1248.py::test_pattern_count_meta_matches_actual_count",
    "tests/unit/test_ir_field_reader_parity.py::test_no_new_ir_field_orphans",
    "tests/integration/test_golden_master.py::test_simple_dsl_to_ir_snapshot",
    "tests/unit/test_viewport.py::test_drawer_pattern_selectors_match_current_markup",
    # #1629 G6 compact status.mcp changelog (CI red 2026-07-18 after world-model ship)
    "tests/unit/mcp/test_status_handlers.py::TestNewSinceLastCheck",
    "tests/unit/test_mcp_agent_cognition_1629.py::test_mcp_status_changelog_compact_by_default",
)

REMEDIATION = """
╔══════════════════════════════════════════════════════════════════════╗
║  SHIP-SURFACE FAILED — recurrent badge-red class                     ║
║  Do NOT ship or tag until this is green.                             ║
╚══════════════════════════════════════════════════════════════════════╝

Remediation by class (run from repo root):

  Bandit (B3xx / medium severity on src/)
    uv pip install 'bandit[toml]'
    bandit -c pyproject.toml -r src/ --severity-level medium
    # fix finding (e.g. hashlib.sha1(..., usedforsecurity=False) for non-crypto)

  Example SPECIFICATION.md stale / structure
    # DSL changed → refresh footer fingerprints (and add ## sections if needed):
    .venv/bin/python -c "from dazzle.spec_narrative.brief import build_brief, brief_fingerprint; ..."
    # or re-run /spec-narrate for prose; footer must match:
    #   dazzle spec brief -p examples/<app> --fingerprint
    pytest tests/unit/test_example_spec_bar.py -q

  Product maturity residual (example fleet warehouse-shaped)
    python scripts/example_product_maturity.py --strict
    # Fix: job workspaces + persona default_workspace (not more entity lists).
    # Docs: docs/reference/product-maturity.md
    # Improve: /improve example-apps product_maturity
    pytest tests/unit/test_example_product_maturity.py -q

  Demo fleet residual (#1626 nav/seed/stills floors)
    python scripts/demo_fleet_bar.py --strict
    # Fix: product nav isolation, blueprint mins, product stills (not only platform).
    # Improve: /improve example-apps demo_fleet
    pytest tests/unit/test_demo_fleet_bar.py -q

  Unified example probes (product + demo + journey for /improve OBSERVE)
    python scripts/improve_example_probes.py --status
    python scripts/improve_example_probes.py --strict
    pytest tests/unit/test_improve_example_probes.py -q

  simple_task brief golden
    dazzle spec brief -p examples/simple_task -f json \\
      > tests/unit/baselines/spec_brief_simple_task.json
    # review diff + CHANGELOG if public shape changed

  IR golden snapshot
    pytest tests/integration/test_golden_master.py::test_simple_dsl_to_ir_snapshot \\
      --snapshot-update -q
    # review tests/integration/__snapshots__/

  patterns.toml pattern_count
    # set [meta].pattern_count to the actual [patterns.X] entry count

  IR reader orphan baseline
    # remove resolved orphans from tests/unit/fixtures/ir_reader_baseline.json
    # (message lists the field paths)

  Viewport DRAWER_PATTERN freshness
    # selector must match AppShell chrome (chrome + rail toggles when open).
    # See tests/unit/test_viewport.py::_render_app_shell_chrome
    pytest tests/unit/test_viewport.py::test_drawer_pattern_selectors_match_current_markup -q

Re-run:
  make ship-surface
  # then: make ci-fast

See: docs/contributing/local-ci-concordance.md (Tier 0.5 ship-surface)
After a GitHub CI repair, **promote new recurrent classes into this pack**
(or preflight-surface) — do not fix-only (cimonitor close-the-loop).
"""


def _python() -> str:
    venv_py = REPO / ".venv" / "bin" / "python"
    if venv_py.is_file():
        return str(venv_py)
    return sys.executable


def _bandit_cmd() -> list[str] | None:
    """Return bandit argv or None if bandit cannot be invoked."""
    py = _python()
    # Prefer module form so venv-only installs work without a script on PATH.
    return [py, "-m", "bandit", "-c", "pyproject.toml", "-r", "src/", "--severity-level", "medium"]


def run_bandit(*, quiet: bool = False) -> int:
    cmd = _bandit_cmd()
    if cmd is None:
        print("ship-surface: bandit not available", file=sys.stderr)
        return 2
    if not quiet:
        print("==> ship-surface: bandit (medium, src/)")
    # Ensure bandit is importable; CI installs bandit[toml] on the fly.
    probe = subprocess.run(
        [_python(), "-c", "import bandit"],
        cwd=REPO,
        check=False,
        capture_output=True,
    )
    if probe.returncode != 0:
        # Match ci_local.sh / CI: uv pip install when missing.
        uv = shutil.which("uv") or str(Path.home() / ".local" / "bin" / "uv")
        if Path(uv).is_file() or shutil.which("uv"):
            uv_bin = uv if Path(uv).is_file() else "uv"
            if not quiet:
                print("    installing bandit[toml] via uv pip …")
            inst = subprocess.run(
                [uv_bin, "pip", "install", "bandit[toml]"],
                cwd=REPO,
                check=False,
            )
            if inst.returncode != 0:
                print(
                    "ship-surface: failed to install bandit[toml] — "
                    "run: uv pip install 'bandit[toml]'",
                    file=sys.stderr,
                )
                return 2
        else:
            print(
                "ship-surface: bandit not installed and uv not found — "
                "run: uv pip install 'bandit[toml]'",
                file=sys.stderr,
            )
            return 2
    proc = subprocess.run(cmd, cwd=REPO, check=False)
    return proc.returncode


def run_ship_tests(*, quiet: bool = False) -> int:
    missing = []
    for node in SHIP_TESTS:
        path = node.split("::", 1)[0]
        if not (REPO / path).is_file():
            missing.append(path)
    if missing:
        print("ship-surface: missing test modules:", file=sys.stderr)
        for m in missing:
            print(f"  - {m}", file=sys.stderr)
        return 2

    py = _python()
    cmd = [py, "-m", "pytest", *SHIP_TESTS, "-q", "--tb=line"]
    if not quiet:
        print("==> ship-surface: recurrent unit pack")
        for t in SHIP_TESTS:
            print(f"    {t}")
        print(f"    interpreter: {py}")
    return subprocess.run(cmd, cwd=REPO, check=False).returncode


def run_ship_surface(*, quiet: bool = False, skip_bandit: bool = False) -> int:
    if not skip_bandit:
        brc = run_bandit(quiet=quiet)
        if brc != 0:
            print(REMEDIATION, file=sys.stderr)
            return 1
    trc = run_ship_tests(quiet=quiet)
    if trc != 0:
        print(REMEDIATION, file=sys.stderr)
        return 1
    if not quiet:
        print("OK ship-surface clean")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Fail on recurrent badge-red classes (bandit + SPEC/IR/viewport pack). "
            "Part of Tier 0 / make ci-fast after preflight-surface."
        )
    )
    parser.add_argument("--quiet", action="store_true")
    parser.add_argument(
        "--list",
        action="store_true",
        help="Print ship test nodeids and exit 0",
    )
    parser.add_argument(
        "--skip-bandit",
        action="store_true",
        help="Run only the pytest pack (bandit already ran elsewhere)",
    )
    args = parser.parse_args(argv)
    if args.list:
        print("bandit -c pyproject.toml -r src/ --severity-level medium")
        for p in SHIP_TESTS:
            print(p)
        return 0
    return run_ship_surface(quiet=args.quiet, skip_bandit=args.skip_bandit)


if __name__ == "__main__":
    raise SystemExit(main())
