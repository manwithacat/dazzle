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
from .compiler import (
    compile_discovery_handler,
    discovery_compile_impl,
    discovery_report_impl,
    get_discovery_report_handler,
)
from .emitter import discovery_emit_impl, emit_discovery_handler
from .explore_spike import discovery_explore_spike_handler
from .missions import (
    discovery_run_headless_impl,
    discovery_run_impl,
    run_discovery_handler,
    run_headless_discovery_handler,
)
from .status import (
    _compute_coherence_score,
    app_coherence_handler,
    discovery_status_handler,
    discovery_status_impl,
    discovery_verify_all_stories_impl,
    verify_all_stories_handler,
)

__all__ = [
    # Impl functions (pure, no MCP types)
    "discovery_run_impl",
    "discovery_run_headless_impl",
    "discovery_report_impl",
    "discovery_compile_impl",
    "discovery_emit_impl",
    "discovery_status_impl",
    "discovery_verify_all_stories_impl",
    # MCP handler wrappers
    "run_discovery_handler",
    "run_headless_discovery_handler",
    "get_discovery_report_handler",
    "compile_discovery_handler",
    "emit_discovery_handler",
    "discovery_status_handler",
    "verify_all_stories_handler",
    "app_coherence_handler",
    "_compute_coherence_score",
    # Cycle 198 spike — Path γ explore
    "discovery_explore_spike_handler",
    # Helpers
    "save_discovery_report",
]
