from pathlib import Path

import pytest

from dazzle.fitness.maturity import read_maturity


def test_maturity_defaults_to_mvp(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("[project]\nname = 'x'\n")
    assert read_maturity(tmp_path) == "mvp"


def test_maturity_reads_beta(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("[dazzle.maturity]\nlevel = 'beta'\n")
    assert read_maturity(tmp_path) == "beta"


def test_maturity_reads_stable(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("[dazzle.maturity]\nlevel = 'stable'\n")
    assert read_maturity(tmp_path) == "stable"


def test_maturity_rejects_unknown_level(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("[dazzle.maturity]\nlevel = 'production'\n")
    with pytest.raises(ValueError, match="maturity level"):
        read_maturity(tmp_path)
