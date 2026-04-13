import tomllib
from pathlib import Path
from typing import Literal, cast

MaturityLevel = Literal["mvp", "beta", "stable"]
_VALID: set[str] = {"mvp", "beta", "stable"}


def read_maturity(project_root: Path) -> MaturityLevel:
    pyproject = project_root / "pyproject.toml"
    if not pyproject.exists():
        return "mvp"

    data = tomllib.loads(pyproject.read_text())
    level = data.get("dazzle", {}).get("maturity", {}).get("level", "mvp")

    if level not in _VALID:
        raise ValueError(f"Invalid maturity level {level!r}; expected one of {_VALID}")
    return cast(MaturityLevel, level)
