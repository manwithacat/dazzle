"""
MCP handler for capability discovery operations.

Operations:
  run     — Start a discovery session (async, returns session ID)
  report  — Get the discovery report from a completed session
  compile — Compile observations into prioritized proposals
  emit    — Generate valid DSL code from compiled proposals
  status  — Check status of a running/completed session
"""

from ._helpers import save_discovery_report
from .compiler import compile_discovery_handler, get_discovery_report_handler
from .emitter import emit_discovery_handler
from .missions import run_discovery_handler, run_headless_discovery_handler
from .status import (
    _compute_coherence_score,
    app_coherence_handler,
    discovery_status_handler,
    verify_all_stories_handler,
)

__all__ = [
    # Missions
    "run_discovery_handler",
    "run_headless_discovery_handler",
    # Compiler / report
    "get_discovery_report_handler",
    "compile_discovery_handler",
    # Emitter
    "emit_discovery_handler",
    # Status / verification / coherence
    "discovery_status_handler",
    "verify_all_stories_handler",
    "app_coherence_handler",
    "_compute_coherence_score",
    # Helpers
    "save_discovery_report",
]
