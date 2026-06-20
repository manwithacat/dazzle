"""
Metrics collection for Dazzle applications.

Provides fire-and-forget metrics emission and HTTP middleware.
"""

from .emitter import MetricsEmitter
from .middleware import MetricsMiddleware, add_metrics_middleware

__all__ = [
    "MetricsEmitter",
    "MetricsMiddleware",
    "add_metrics_middleware",
]
