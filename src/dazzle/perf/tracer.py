"""Configure the OpenTelemetry tracer for ``dazzle perf`` runs.

Exposes two public entry points:

- :func:`configure_tracer` — call once at process start to wire up
  the SQLite exporter. Returns the configured ``TracerProvider``.
- :func:`dazzle_span` — context manager / decorator that creates a
  span on the framework tracer. Accepts a mix of scalar and Pydantic-
  model attributes; models are flattened via
  :func:`dazzle.perf.serializer.pydantic_attrs`.

When ``configure_tracer`` hasn't been called, ``dazzle_span`` is a
zero-cost no-op — the framework keeps its ``dazzle_span(...)``
decorators in place without a runtime penalty when tracing is off.

``opentelemetry`` is the optional ``perf`` extra: this module must be
importable without it (``dazzle.cli`` imports ``dazzle.perf`` at boot).
The OTel imports are therefore deferred into :func:`configure_tracer`,
which is only reached when tracing is explicitly requested.
"""

from __future__ import annotations

import contextlib
import logging
import os
from collections.abc import Iterator
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel

from dazzle.perf.serializer import pydantic_attrs

if TYPE_CHECKING:
    from pathlib import Path

    from opentelemetry.sdk.trace import TracerProvider

_TRACER_NAME = "dazzle"

_PERF_EXTRA_HINT = (
    "dazzle perf tracing requires the optional 'perf' extra. "
    "Install it with:  pip install 'dazzle-dsl[perf]'"
)

# Environment variable consumed by :func:`configure_tracer` to attach a
# ``BatchSpanProcessor(OTLPSpanExporter(...))`` alongside the local SQLite
# exporter (#1192 slice 2). Value is a full URL — e.g.
# ``https://otel.example.com/v1/traces``. Never strip or transform it.
_OTLP_ENDPOINT_ENV = "DAZZLE_OTEL_ENDPOINT"

# Hint surfaced in the WARNING log when the OTLP endpoint env var is set
# but the optional ``observability`` extra is not installed. The local
# SQLite exporter remains wired — boot does not crash.
_OBSERVABILITY_EXTRA_HINT = (
    "DAZZLE_OTEL_ENDPOINT is set but the OTLP HTTP exporter is not "
    "installed. Install the optional 'observability' extra with:  "
    "pip install 'dazzle-dsl[observability]'  — continuing without "
    "OTLP push; the local SQLite span exporter is unaffected."
)

# Module-level provider reference.  ``dazzle_span`` calls
# ``_provider.get_tracer()`` directly so it bypasses OTel's frozen
# global (``set_tracer_provider`` is a one-shot after the first call).
# ``None`` means unconfigured → ``dazzle_span`` is a no-op. Only
# :func:`configure_tracer` ever sets it, so a non-``None`` value
# guarantees the ``perf`` extra is installed.
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

    Raises:
        RuntimeError: when the optional ``perf`` extra (opentelemetry)
            is not installed.
    """
    try:
        from opentelemetry import trace
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import (
            BatchSpanProcessor,
            SimpleSpanProcessor,
        )
    except ModuleNotFoundError as exc:
        raise RuntimeError(_PERF_EXTRA_HINT) from exc

    from dazzle.perf.exporter import SQLiteSpanExporter

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
    # OTLP push branch (#1192 slice 2). Additive — does not touch the
    # local SQLite processor above. The env-var check stays inside this
    # function so the no-env-var path is byte-identical to pre-#1192.
    _maybe_attach_otlp_processor(provider)
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


def _maybe_attach_otlp_processor(provider: TracerProvider) -> None:
    """Attach an OTLP HTTP span exporter when ``DAZZLE_OTEL_ENDPOINT`` is set.

    Reads the env var at call time. When unset, returns immediately —
    the existing local span processor is left untouched and no OTel-OTLP
    code path runs. This guarantees byte-identical behaviour to before
    #1192 slice 2 for the default install.

    When set, imports ``OTLPSpanExporter`` from the optional
    ``observability`` extra (``opentelemetry-exporter-otlp-proto-http``)
    and attaches a ``BatchSpanProcessor`` wrapping it onto ``provider``,
    in addition to the local SQLite processor. The endpoint string is
    passed through verbatim — operators are expected to provide the full
    URL (e.g. ``https://otel.example.com/v1/traces``).

    If the extra is not installed, logs a single WARNING naming the
    extra and returns without raising. The local exporter stays wired,
    so the tracer keeps working.
    """
    endpoint = os.environ.get(_OTLP_ENDPOINT_ENV)
    if not endpoint:
        return
    try:
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
            OTLPSpanExporter,
        )
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
    except ModuleNotFoundError:
        logging.getLogger(__name__).warning(_OBSERVABILITY_EXTRA_HINT)
        return

    otlp_exporter = OTLPSpanExporter(endpoint=endpoint)
    provider.add_span_processor(BatchSpanProcessor(otlp_exporter))


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

    When the tracer hasn't been configured — or the optional ``perf``
    extra isn't installed — this is a zero-cost no-op that yields
    ``None``.
    """
    # ``_provider`` is set only by ``configure_tracer``, which requires
    # opentelemetry; ``None`` means tracing is off → no-op.
    if _provider is None:
        yield None
        return
    tracer = _provider.get_tracer(_TRACER_NAME)
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
