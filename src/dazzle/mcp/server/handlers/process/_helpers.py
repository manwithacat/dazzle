"""
Shared helpers for process handler submodules.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from ..common import load_project_appspec

if TYPE_CHECKING:
    from dazzle.core.ir.appspec import AppSpec
    from dazzle.core.process.adapter import ProcessAdapter


def _load_app_spec(project_root: Path) -> AppSpec:
    """Load and build AppSpec from project."""
    return load_project_appspec(project_root)


def _get_process_adapter(project_root: Path) -> ProcessAdapter:
    """Get process adapter for project."""
    from dazzle.core.process import LiteProcessAdapter

    db_path = project_root / ".dazzle" / "processes.db"
    return LiteProcessAdapter(db_path=db_path)
