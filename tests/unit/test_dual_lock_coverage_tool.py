"""Phase A — dual_lock_coverage.py regenerates a consistent inventory."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.gate

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "packages" / "hatchi-maxchi" / "tools" / "dual_lock_coverage.py"
COMMITTED = REPO / "packages" / "hatchi-maxchi" / "DUAL_LOCK_COVERAGE.md"


def test_dual_lock_coverage_script_exits_zero() -> None:
    proc = subprocess.run(
        [sys.executable, str(SCRIPT)],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    assert "Dual-lock" in proc.stdout
    assert "schema+DOM" in proc.stdout


def test_committed_coverage_matches_generator() -> None:
    """Drift gate: regenerate --write only after intentional dual-lock changes."""
    assert COMMITTED.is_file(), "missing DUAL_LOCK_COVERAGE.md — run dual_lock_coverage.py --write"
    proc = subprocess.run(
        [sys.executable, str(SCRIPT)],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    # Normalize trailing newlines
    assert proc.stdout.rstrip("\n") == COMMITTED.read_text(encoding="utf-8").rstrip("\n")
