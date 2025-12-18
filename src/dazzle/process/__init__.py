"""
DAZZLE process execution module.

This module provides entry points for process workers.

Usage:
    python -m dazzle.process.worker
"""

from dazzle.core.process import (
    LiteProcessAdapter,
    ProcessAdapter,
    ProcessRun,
    ProcessStatus,
    ProcessTask,
    TaskStatus,
)
from dazzle.core.process.factory import (
    ProcessConfig,
    create_adapter,
    get_backend_info,
)

__all__ = [
    # Adapter interface
    "ProcessAdapter",
    "ProcessRun",
    "ProcessStatus",
    "ProcessTask",
    "TaskStatus",
    # Factory
    "ProcessConfig",
    "create_adapter",
    "get_backend_info",
    # Implementations
    "LiteProcessAdapter",
]
