"""
Process execution adapters for DAZZLE workflows.

This module provides the runtime infrastructure for executing
ProcessSpec and ScheduleSpec definitions from the DSL.

Runtime Modes:
- LiteProcessAdapter: In-process execution using SQLite/asyncio
- TemporalAdapter: Production execution using Temporal

Factory:
- create_adapter(): Auto-selects backend based on availability
- ProcessConfig: Configuration for backend selection
"""

from .adapter import (
    ProcessAdapter,
    ProcessRun,
    ProcessStatus,
    ProcessTask,
    TaskStatus,
)
from .context import ProcessContext
from .factory import ProcessConfig, create_adapter, get_backend_info
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
    # Factory
    "ProcessConfig",
    "create_adapter",
    "get_backend_info",
    # Implementations
    "LiteProcessAdapter",
]

# Optional Temporal adapter (requires: pip install dazzle[temporal])
try:
    from .temporal_adapter import TemporalAdapter

    __all__.append("TemporalAdapter")
except ImportError:
    pass  # Temporal SDK not installed
