"""Contract surface snapshot — breaking-change detector for dual-locks."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.gate

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "packages" / "hatchi-maxchi" / "tools" / "contract_surface.py"
COMMITTED = REPO / "packages" / "hatchi-maxchi" / "CONTRACT_SURFACE.md"


def test_contract_surface_script_exits_zero() -> None:
    proc = subprocess.run(
        [sys.executable, str(SCRIPT)],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr + proc.stdout
    assert "Contract surface" in proc.stdout
    assert "combobox" in proc.stdout
    assert "grid_edit" in proc.stdout


def test_committed_contract_surface_matches_generator() -> None:
    assert COMMITTED.is_file(), "missing CONTRACT_SURFACE.md — run contract_surface.py --write"
    proc = subprocess.run(
        [sys.executable, str(SCRIPT)],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr + proc.stdout
    assert proc.stdout.rstrip("\n") == COMMITTED.read_text(encoding="utf-8").rstrip("\n")
