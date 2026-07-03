"""Boundary gate — HM is upstream of Dazzle and must stay importable,
buildable, and testable with zero Dazzle code.

(The same rule is enforced structurally by the standalone repo's CI —
this test makes the failure local and immediate in the monorepo.)
"""

import ast
from pathlib import Path

PKG = Path(__file__).resolve().parents[1]


def _imports(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.append(node.module)
    return names


def test_no_dazzle_imports_anywhere_in_the_package() -> None:
    offenders = {
        str(py.relative_to(PKG)): bad
        for py in PKG.rglob("*.py")
        if "__pycache__" not in py.parts
        and (bad := [m for m in _imports(py) if m == "dazzle" or m.startswith("dazzle.")])
    }
    assert not offenders, (
        f"HM is upstream of Dazzle — these files import dazzle.*: {offenders}. "
        "Move the dependency into the package (like icons/) or drop it."
    )
