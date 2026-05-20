"""Configure the OpenTelemetry tracer for ``dazzle perf`` runs.

Exposes two public entry points:

- :func:`configure_tracer` — call once at process start to wire up
  the SQLite exporter. Returns the configured ``TracerProvider``.
- :func:`dazzle_span` — context manager / decorator that creates a
  span on the framework tracer. Accepts a mix of scalar and Pydantic-
  model attributes; models are flattened via
  :func:`dazzle.perf.serializer.pydantic_attrs`.

When ``configure_tracer`` hasn't been called, ``dazzle_span`` resolves
the tracer from OTel's global provider (the default ``NoOpTracer``)
and silently does nothing — the framework can keep its
``dazzle_span(...)`` decorators in place without a runtime penalty
when tracing is disabled.
"""

from __future__ import annotations

import contextlib
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import (
    BatchSpanProcessor,
    SimpleSpanProcessor,
)
from pydantic import BaseModel

from dazzle.perf.exporter import SQLiteSpanExporter
from dazzle.perf.serializer import pydantic_attrs

_TRACER_NAME = "dazzle"

# Module-level provider reference.  ``dazzle_span`` always calls
# ``_provider.get_tracer()`` directly so it bypasses OTel's frozen
# global (``set_tracer_provider`` is a one-shot after the first call).
# ``None`` means unconfigured → fall back to OTel global (no-op).
_provider: TracerProvider | None = None


def configure_tracer(
    *,
    run_id: str,
    db_path: Path,
    batch: bool = True,
    app_name: str | None = None,
    manifest_path: str | None = None,
    command_line: str = "",
) -> TracerProvider:
    """Initialise the global tracer provider to write to ``db_path``.

    Args:
        run_id: Unique id for this trace session.
        db_path: SQLite file. Parent directories are created if missing.
        batch: When True, spans flush in batches (production default).
            Tests pass False so spans land synchronously and can be read
            back inside the test body.
        app_name / manifest_path / command_line: Metadata persisted to
            the ``runs`` row.
    """
    global _provider
    provider = TracerProvider()
    exporter = SQLiteSpanExporter(
        db_path=db_path,
        run_id=run_id,
        app_name=app_name,
        manifest_path=manifest_path,
        command_line=command_line,
    )
    processor: Any = BatchSpanProcessor(exporter) if batch else SimpleSpanProcessor(exporter)
    provider.add_span_processor(processor)
    _provider = provider
    # Best-effort set on the OTel global; ignored silently after the first
    # call in a process (OTel locks the global after initial assignment).
    try:
        trace.set_tracer_provider(provider)
    except Exception:  # noqa: BLE001
        # OTel emits a warning when the global is re-set; that's the only
        # observable side-effect, and we already keep our own reference
        # in ``_provider`` for the dazzle_span path. Swallowing is safe.
        import logging

        logging.getLogger(__name__).debug(
            "OTel set_tracer_provider rejected re-assignment (already set)",
            exc_info=True,
        )
    return provider


def reset_tracer() -> None:
    """Drop back to the no-op tracer.

    Test-only entry point — production code never calls this; the
    process exits after a single trace run.
    """
    global _provider
    _provider = None


def current_provider() -> TracerProvider | None:
    """Return the provider set by :func:`configure_tracer`, or ``None``.

    Callers that need a tracer — :func:`dazzle_span` and the OTel
    auto-instrumentors wired up in :mod:`dazzle.perf.instrument` — must
    resolve it through this rather than OTel's global provider.
    ``trace.set_tracer_provider`` is a one-shot per process: across a
    test session (or any process that reconfigures) the global stays
    frozen to the first provider, so auto-instrumentation would write
    spans to a stale exporter.
    """
    return _provider


@contextlib.contextmanager
def dazzle_span(name: str, **attrs: Any) -> Iterator[Any]:
    """Open a span on the ``dazzle`` tracer.

    ``attrs`` accept any mix of scalar OTel attribute values and
    Pydantic model instances; models are flattened with
    :func:`pydantic_attrs` and prefixed with the keyword name.

    Example::

        with dazzle_span("aggregate.expression.compile", expr=ref.expression):
            ...

    When the tracer hasn't been configured, this is effectively a
    no-op — OTel's ``NoOpTracer`` returns a non-recording span.
    """
    # Use the module-level provider directly to avoid OTel's frozen global.
    if _provider is not None:
        tracer = _provider.get_tracer(_TRACER_NAME)
    else:
        tracer = trace.get_tracer(_TRACER_NAME)
    flat: dict[str, Any] = {}
    for key, value in attrs.items():
        if value is None:
            continue
        if isinstance(value, BaseModel):
            flat.update(pydantic_attrs(value, prefix=key))
        else:
            flat[key] = value
    with tracer.start_as_current_span(name, attributes=flat) as span:
        yield span
