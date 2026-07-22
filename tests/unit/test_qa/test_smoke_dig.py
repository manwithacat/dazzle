"""Unit tests for L2.5 smoke dig fleet rotation helpers."""

from __future__ import annotations

from pathlib import Path

from dazzle.qa.smoke_dig import SHOWCASE, repo_root, showcase_apps


def test_repo_root_is_monorepo_not_src() -> None:
    """parents[2] wrongly lands on src/; monorepo root has examples/ + pyproject."""
    root = repo_root()
    assert root.name != "src"
    assert (root / "examples").is_dir()
    assert (root / "pyproject.toml").is_file()
    # Module lives under src/dazzle/qa — root must be three levels up.
    mod = Path(__file__).resolve()
    # tests/unit/test_qa → parents[3] is also monorepo root
    assert root == mod.parents[3]


def test_showcase_apps_finds_dazzle_toml() -> None:
    apps = showcase_apps()
    assert apps, "expected at least one showcase app with dazzle.toml"
    assert set(apps) <= set(SHOWCASE)
    for a in apps:
        assert (repo_root() / "examples" / a / "dazzle.toml").is_file()
