"""MCP handler for ``discovery(operation='coherence')``."""

from .status import _compute_coherence_score, app_coherence_handler

__all__ = [
    "_compute_coherence_score",
    "app_coherence_handler",
]
