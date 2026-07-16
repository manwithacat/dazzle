"""Gate: preflight-surface module list stays real and gate-marked.

If an agent removes a drift test from ``scripts/preflight_surface.py`` without
a deliberate replacement, main goes red again while laptops look green.
"""

from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.gate

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "preflight_surface.py"


def _surface_tests_from_script() -> list[str]:
    tree = ast.parse(SCRIPT.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.AnnAssign) and getattr(node.target, "id", None) == "SURFACE_TESTS":
            assert isinstance(node.value, (ast.Tuple, ast.List))
            out: list[str] = []
            for elt in node.value.elts:
                assert isinstance(elt, ast.Constant) and isinstance(elt.value, str)
                out.append(elt.value)
            return out
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if getattr(t, "id", None) == "SURFACE_TESTS":
                    assert isinstance(node.value, (ast.Tuple, ast.List))
                    out = []
                    for elt in node.value.elts:
                        assert isinstance(elt, ast.Constant) and isinstance(elt.value, str)
                        out.append(elt.value)
                    return out
    raise AssertionError("SURFACE_TESTS not found in scripts/preflight_surface.py")


def test_preflight_script_exists() -> None:
    assert SCRIPT.is_file()


def test_surface_modules_exist_and_are_gate_marked() -> None:
    modules = _surface_tests_from_script()
    assert modules, "SURFACE_TESTS must not be empty"
    for rel in modules:
        path = REPO / rel
        assert path.is_file(), f"missing surface test module: {rel}"
        text = path.read_text(encoding="utf-8")
        assert "pytest.mark.gate" in text or "mark.gate" in text, (
            f"{rel} must carry pytest.mark.gate so preflight-surface stays in the gate suite"
        )


def test_preflight_list_exits_zero() -> None:
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--list"],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    listed = [ln.strip() for ln in proc.stdout.splitlines() if ln.strip()]
    assert listed == _surface_tests_from_script()
