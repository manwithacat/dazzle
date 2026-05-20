"""Apply OTel auto-instrumentations to a Dazzle runtime app.

Called once from the runtime server when ``DAZZLE_PERF_ENABLED=1`` is
set in the environment (``dazzle perf trace`` sets the var before
launching ``dazzle serve``). Importing the instrumentation packages is
deferred so the framework's normal startup path doesn't pull OTel in
when the ``perf`` extra isn't installed.
"""

from __future__ import annotations

from typing import Any


def instrument_app(app: Any) -> None:
    """Wrap ``app`` with FastAPI / psycopg / asyncio instrumentation.

    Idempotent — repeated calls are tolerated by the underlying OTel
    instrumentation packages.

    The instrumentors are pinned to the provider from
    :func:`dazzle.perf.tracer.configure_tracer` rather than OTel's
    global. ``trace.set_tracer_provider`` is a one-shot per process, so
    a reconfigured tracer (e.g. across a test session) leaves the global
    frozen to the first provider — auto-instrumented spans would then
    land in a stale exporter. Passing ``tracer_provider`` explicitly
    keeps them on the live exporter.
    """
    from opentelemetry.instrumentation.asyncio import AsyncioInstrumentor
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    from opentelemetry.instrumentation.psycopg import PsycopgInstrumentor

    from dazzle.perf.tracer import current_provider

    provider = current_provider()
    FastAPIInstrumentor.instrument_app(app, tracer_provider=provider)
    PsycopgInstrumentor().instrument(tracer_provider=provider)
    AsyncioInstrumentor().instrument(tracer_provider=provider)
