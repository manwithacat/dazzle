"""
Shared helpers for process handler submodules.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from ..common import load_project_appspec as load_app_spec

if TYPE_CHECKING:
    from dazzle.core.process import ProcessAdapter

__all__ = ["load_app_spec", "get_process_adapter"]


def get_process_adapter(project_root: Path) -> ProcessAdapter:
    """Get a LiteProcessAdapter for the given project."""
    from dazzle.core.process import LiteProcessAdapter
    from dazzle.mcp.server.paths import project_processes_db

    db_path = project_processes_db(project_root)
    return LiteProcessAdapter(db_path=db_path)
