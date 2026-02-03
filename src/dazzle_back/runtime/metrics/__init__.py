"""
Metrics collection for Dazzle applications.

Provides fire-and-forget metrics emission and HTTP middleware.
"""

from __future__ import annotations

from .emitter import MetricsEmitter, emit, get_emitter
from .middleware import MetricsMiddleware, add_metrics_middleware

__all__ = [
    "MetricsEmitter",
    "get_emitter",
    "emit",
    "MetricsMiddleware",
    "add_metrics_middleware",
]
