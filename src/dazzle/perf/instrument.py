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
    """
    from opentelemetry.instrumentation.asyncio import AsyncioInstrumentor
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    from opentelemetry.instrumentation.psycopg import PsycopgInstrumentor

    FastAPIInstrumentor.instrument_app(app)
    PsycopgInstrumentor().instrument()
    AsyncioInstrumentor().instrument()
