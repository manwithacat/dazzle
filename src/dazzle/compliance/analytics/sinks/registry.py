"""Framework sink registry (v0.61.0 Phase 5).

Maps sink name (from DSL ``analytics.server_side.sink``) to a factory
that constructs the sink instance. Factories defer network-touching
setup so configuration errors surface at emit time, not at link time.

Extending: register a new sink by appending to ``FRAMEWORK_SINKS``. The
factory receives ``(default_config: dict[str, str])`` — everything
non-secret about the sink's global defaults. Secrets come from the
environment at emit time.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .base import AnalyticsSink
from .ga4 import GA4MeasurementProtocolSink


def _ga4_factory(config: dict[str, str]) -> AnalyticsSink:
    """Build a GA4 sink from the resolved config.

    Config keys read:
        - ``measurement_id`` — fallback property ID for tenants that
          don't supply their own.
    """
    return GA4MeasurementProtocolSink(
        default_measurement_id=config.get("measurement_id"),
    )


FRAMEWORK_SINKS: dict[str, Callable[[dict[str, str]], AnalyticsSink]] = {
    "ga4_measurement_protocol": _ga4_factory,
}


def get_sink_factory(name: str) -> Callable[[dict[str, str]], AnalyticsSink] | None:
    """Return the factory for a registered sink name, or None."""
    return FRAMEWORK_SINKS.get(name)


def list_sink_names() -> list[str]:
    """Return the sorted list of registered sink names."""
    return sorted(FRAMEWORK_SINKS.keys())


# `Any` import silences unused; kept so future sinks can import it.
_ = Any
