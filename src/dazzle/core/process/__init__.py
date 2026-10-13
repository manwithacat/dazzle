"""
Process execution adapters for DAZZLE workflows.

This module provides the runtime infrastructure for executing
ProcessSpec and ScheduleSpec definitions from the DSL.

Runtime Modes:
- EventBusProcessAdapter: Production execution using native event bus + Redis
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
]

# EventBus adapter (requires: redis)
try:
    from .eventbus_adapter import EventBusProcessAdapter

    __all__.append("EventBusProcessAdapter")
except ImportError:
    pass  # Redis not installed

# Optional Temporal adapter (requires: pip install dazzle-dsl[temporal])
try:
    from .temporal_adapter import TemporalAdapter

    __all__.append("TemporalAdapter")
except ImportError:
    pass  # Temporal SDK not installed
