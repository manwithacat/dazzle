"""Vitality Phase-1 static-connectedness analyser (#1521).

Exercises the AST call graph, the registry/decorator dispatch augmentation, and the
islet-candidate identification on a small synthetic package.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from dazzle.fitness.vitality import analyze_connectedness, render_report_md


def _write(root: Path, rel: str, body: str) -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body, encoding="utf-8")


@pytest.fixture
def pkg(tmp_path: Path) -> Path:
    _write(tmp_path, "pkg/__init__.py", "")
    _write(
        tmp_path,
        "pkg/a.py",
        (
            "__all__ = ['entry']\n"
            "\n"
            "def entry():\n"
            "    helper()\n"
            "\n"
            "def helper():\n"  # called by entry → reachable, fan_in 1
            "    pass\n"
            "\n"
            "def orphan():\n"  # no caller, no reference → islet candidate
            "    pass\n"
            "\n"
            "def dispatched():\n"  # handed to a registry → dispatch-referenced
            "    pass\n"
            "\n"
            "register(dispatched)\n"
            "\n"
            "class Thing:\n"
            "    def __init__(self):\n"  # protocol method → never a candidate
            "        pass\n"
        ),
    )
    return tmp_path


def test_reachability_edges_and_entry_points(pkg: Path) -> None:
    r = analyze_connectedness(pkg)
    # helper has a real caller (entry) and is reached from the exported entry point.
    assert "pkg.a.helper" not in r.candidates
    # entry is an entry point (in __all__).
    assert "pkg.a.entry" not in r.candidates


def test_orphan_is_a_candidate(pkg: Path) -> None:
    r = analyze_connectedness(pkg)
    assert "pkg.a.orphan" in r.candidates


def test_registry_reference_rescues_and_moves_the_delta(pkg: Path) -> None:
    r = analyze_connectedness(pkg)
    # `register(dispatched)` hands the function to a registry → not an islet, and it
    # counts toward the augmentation delta (rescued beyond the raw call graph).
    assert "pkg.a.dispatched" not in r.candidates
    assert r.augmentation_delta >= 1


def test_protocol_method_never_a_candidate(pkg: Path) -> None:
    r = analyze_connectedness(pkg)
    assert "pkg.a.Thing.__init__" not in r.candidates


def test_report_renders_and_lists_the_orphan(pkg: Path) -> None:
    md = render_report_md(analyze_connectedness(pkg))
    assert "Vitality" in md
    assert "Augmentation delta" in md
    assert "pkg.a.orphan" in md
