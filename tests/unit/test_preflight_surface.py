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
        # Allow pytest nodeids (path::test) — same split as preflight_surface._check_paths_exist
        file_rel = rel.split("::", 1)[0]
        path = REPO / file_rel
        assert path.is_file(), f"missing surface test module: {rel}"
        text = path.read_text(encoding="utf-8")
        assert "pytest.mark.gate" in text or "mark.gate" in text, (
            f"{file_rel} must carry pytest.mark.gate so preflight-surface stays in the gate suite"
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


def test_precommit_ruff_matches_the_locked_version() -> None:
    """`ruff-pre-commit` must track the ruff version in `uv.lock` (#1719).

    CI runs bare `ruff` from the committed lock (`uv sync --frozen`), while
    pre-commit runs whatever `rev:` pins in an isolated env. When the two
    disagree, pre-commit and CI apply different lint *and* format rules, and the
    symptom is pre-commit rewriting files CI already accepted — or rejecting
    files CI passed.

    The measured harm at the time of the fix was zero: the tree sat in the
    intersection of both versions, so both passed. That is exactly why it is
    worth pinning rather than watching for — the divergence only shows up on the
    next edit that the versions treat differently.
    """
    import re
    import tomllib
    from pathlib import Path

    repo = Path(__file__).resolve().parents[2]
    config = (repo / ".pre-commit-config.yaml").read_text(encoding="utf-8")

    match = re.search(
        r"repo:\s*https://github\.com/astral-sh/ruff-pre-commit\s*\n\s*rev:\s*v(\S+)",
        config,
    )
    assert match, "ruff-pre-commit repo/rev not found in .pre-commit-config.yaml"
    pinned = match.group(1).strip()

    with (repo / "uv.lock").open("rb") as handle:
        lock = tomllib.load(handle)

    locked = next(
        (p["version"] for p in lock.get("package", []) if p.get("name") == "ruff"),
        None,
    )
    assert locked, "ruff is not present in uv.lock"

    assert pinned == locked, (
        f"pre-commit pins ruff {pinned} but uv.lock has {locked}. CI runs the "
        "locked version, so pre-commit and CI would apply different lint and "
        "format rules. Run `pre-commit autoupdate` (or `make update-deps`) and "
        "commit the result."
    )
