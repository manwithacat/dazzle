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
    """Get a ProcessAdapter for the given project using the factory."""
    from dazzle.core.process import ProcessConfig, create_adapter

    config = ProcessConfig(backend="auto", project_root=project_root)
    return create_adapter(config)
