"""Integration Retries Explorer routes for runtime inspection (#1194).

Provides ``GET /_dazzle/integrations/{name}/retries`` — a per-integration
view of recent retry attempts captured by ``MappingExecutor`` while
driving ``async_retrying_request``.

Architecture note — IN-PROCESS, VOLATILE STATE
-----------------------------------------------

The retry events surfaced here live in a module-level singleton
``RetryAccumulator`` (see :mod:`dazzle.http.runtime.retry_accumulator`).
The accumulator is in-process and **resets on every restart**. It is
deliberately not persisted to the operational DB — durable retry
history is the responsibility of the integration provider's own logs.
This trade-off is documented in CHANGELOG and in
``docs/guides/observability.md``.

The accumulator caps each integration's event list at
``RetryAccumulator.MAX_EVENTS_PER_INTEGRATION`` (default 100) entries,
dropping oldest-first when the cap is exceeded.

The endpoint is registered only when the AppSpec actually declares any
``integration`` blocks, mirroring the gating used by ``job_explorer``.
"""

import logging
from functools import partial
from typing import TYPE_CHECKING

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from dazzle.http.runtime.retry_accumulator import RetryAccumulator

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from dazzle.core.ir.integrations import IntegrationSpec


# =============================================================================
# Response Models
# =============================================================================


class IntegrationRetryEvent(BaseModel):
    """A single retry-attempt outcome captured by ``MappingExecutor``."""

    integration: str
    mapping: str | None = None
    attempt: int
    max_attempts: int
    status_code: int | None = None
    error: str | None = None
    payload_summary: str | None = None
    last_attempt_at: str
    next_retry_at: str | None = None
    backoff_seconds: float | None = None
    succeeded: bool = False


class IntegrationRetriesResponse(BaseModel):
    """Response for ``GET /_dazzle/integrations/{name}/retries``.

    The ``volatile`` flag is always True for this surface — see module
    docstring for rationale.
    """

    integration: str
    events: list[IntegrationRetryEvent] = Field(default_factory=list)
    total: int = 0
    limit: int = 50
    volatile: bool = True


# =============================================================================
# Module-level handler
# =============================================================================


async def _list_integration_retries(
    accumulator: RetryAccumulator,
    declared_names: frozenset[str],
    name: str,
    limit: int = Query(
        default=50,
        ge=1,
        le=200,
        description="Maximum retry events returned (newest first).",
    ),
) -> IntegrationRetriesResponse:
    """List retry events for a single named integration.

    Returns events newest-first up to ``limit``. Unknown integration
    names raise a 404.
    """
    if declared_names and name not in declared_names:
        raise HTTPException(
            status_code=404,
            detail=f"Integration '{name}' is not declared in the AppSpec",
        )

    events = accumulator.events_for(name)
    # Newest-first ordering
    ordered = list(reversed(events))
    response_events = [IntegrationRetryEvent(**event.to_dict()) for event in ordered[:limit]]

    return IntegrationRetriesResponse(
        integration=name,
        events=response_events,
        total=len(events),
        limit=limit,
        volatile=True,
    )


# =============================================================================
# Integration Retries Routes
# =============================================================================


def create_integrations_retries_routes(
    accumulator: RetryAccumulator,
    integrations: "list[IntegrationSpec]",
) -> APIRouter:
    """Create the integration-retries explorer routes.

    Args:
        accumulator: The shared :class:`RetryAccumulator` instance.
            ``MappingExecutor`` writes retry events into this same
            accumulator while driving the retry loop.
        integrations: The list of declared ``IntegrationSpec`` blocks
            (``ctx.appspec.integrations``). Used to validate that the
            ``{name}`` path-param actually refers to a declared
            integration (404 otherwise).

    Returns:
        APIRouter with the ``/_dazzle/integrations/{name}/retries``
        endpoint.
    """
    router = APIRouter(prefix="/_dazzle/integrations", tags=["Integrations Retries"])
    declared_names = frozenset(getattr(i, "name", "") for i in integrations)

    router.add_api_route(
        "/{name}/retries",
        partial(_list_integration_retries, accumulator, declared_names),
        methods=["GET"],
        response_model=IntegrationRetriesResponse,
    )

    return router
