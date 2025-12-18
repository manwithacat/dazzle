"""
Process execution adapters for DAZZLE workflows.

This module provides the runtime infrastructure for executing
ProcessSpec and ScheduleSpec definitions from the DSL.

Runtime Modes:
- LiteProcessAdapter: In-process execution using SQLite/asyncio
- TemporalAdapter: Production execution using Temporal (Phase 5)
"""

from .adapter import (
    ProcessAdapter,
    ProcessRun,
    ProcessStatus,
    ProcessTask,
    TaskStatus,
)
from .context import ProcessContext
from .lite_adapter import LiteProcessAdapter

__all__ = [
    # Adapter interface
    "ProcessAdapter",
    "ProcessRun",
    "ProcessStatus",
    "ProcessTask",
    "TaskStatus",
    # Context
    "ProcessContext",
    # Implementations
    "LiteProcessAdapter",
]
