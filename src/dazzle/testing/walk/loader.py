"""Load scene walk YAML into :class:`SceneWalkSpec` (#1638)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from dazzle.testing.walk.models import SceneWalkSpec

try:
    import yaml
except ImportError:  # pragma: no cover — PyYAML is a hard runtime dep in practice
    yaml = None  # type: ignore[assignment]


class WalkLoadError(ValueError):
    """Walk file missing, unreadable, or structurally invalid."""

    def __init__(self, path: Path | str, message: str) -> None:
        self.path = Path(path)
        super().__init__(f"{self.path}: {message}")


def _require_yaml() -> Any:
    if yaml is None:
        raise WalkLoadError(
            "<yaml>",
            "PyYAML is required to load scene walks (pip install pyyaml)",
        )
    return yaml


def load_walk(path: Path | str) -> SceneWalkSpec:
    """Load and parse one walk YAML file.

    Sets ``walk_id`` from the file stem and ``source_path`` to the absolute path.
    """
    p = Path(path).resolve()
    if not p.is_file():
        raise WalkLoadError(p, "file not found")

    y = _require_yaml()
    try:
        raw = p.read_text(encoding="utf-8")
    except OSError as e:
        raise WalkLoadError(p, f"cannot read: {e}") from e

    try:
        data = y.safe_load(raw)
    except y.YAMLError as e:
        raise WalkLoadError(p, f"YAML parse error: {e}") from e

    if data is None:
        raise WalkLoadError(p, "empty document")
    if not isinstance(data, dict):
        raise WalkLoadError(p, f"expected mapping at root, got {type(data).__name__}")

    try:
        walk = SceneWalkSpec.model_validate(data)
    except Exception as e:
        raise WalkLoadError(p, f"schema validation failed: {e}") from e

    walk.walk_id = p.stem
    walk.source_path = str(p)
    return walk


def load_walks(paths: list[Path]) -> list[SceneWalkSpec]:
    """Load many walks; first error aborts (use validate for multi-file reports)."""
    return [load_walk(p) for p in paths]
