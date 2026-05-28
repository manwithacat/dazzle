"""Approvals Explorer routes for runtime inspection (#1194).

Provides ``GET /_dazzle/approvals/pending`` — a per-approval-block
summary of pending rows, where "pending" means rows whose driving
entity field (``ApprovalSpec.trigger_field``) currently equals
``ApprovalSpec.trigger_value``.

This is the approval-system analogue of ``event_explorer.py`` and
``job_explorer.py``. Like its siblings the endpoint is always available
in development mode (localhost), carries no auth dependency, and is
registered only when the AppSpec actually declares any ``approval``
blocks.

Data source: the entity CRUD services keyed by ``service.entity_name``,
exactly mirroring ``service_generator.services_by_entity()``.
"""

import logging
from functools import partial
from typing import Any, Protocol, runtime_checkable

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from dazzle.core.ir.approvals import ApprovalSpec

logger = logging.getLogger(__name__)


@runtime_checkable
class EntityListService(Protocol):
    """Protocol for the CRUD-service methods the approvals explorer uses.

    Satisfied by ``service_generator.CRUDService`` — the auto-generated
    service wrapping any framework entity.
    """

    entity_name: str

    async def list(
        self,
        page: int = ...,
        page_size: int = ...,
        filters: dict[str, Any] | None = ...,
        sort: list[str] | None = ...,
    ) -> dict[str, Any]: ...


# =============================================================================
# Response Models
# =============================================================================


class ApprovalSummary(BaseModel):
    """Summary of pending rows for a single ApprovalSpec block."""

    name: str
    title: str | None = None
    entity: str
    trigger_field: str
    trigger_value: str
    count: int
    sample_ids: list[str] = Field(default_factory=list)
    error: str | None = None


class ApprovalPendingResponse(BaseModel):
    """Response for ``GET /_dazzle/approvals/pending``."""

    approvals: list[ApprovalSummary] = Field(default_factory=list)
    total_pending: int = 0
    limit: int = 20


# =============================================================================
# Helpers
# =============================================================================


def _row_field(row: Any, name: str) -> Any:
    """Read a field from a row that may be a model or a dict."""
    if isinstance(row, dict):
        return row.get(name)
    return getattr(row, name, None)


def _row_id(row: Any) -> str | None:
    """Best-effort extract a primary-key id from a row."""
    for key in ("id", "uuid", "pk"):
        value = _row_field(row, key)
        if value is not None:
            return str(value)
    return None


async def _query_pending_rows(
    service: EntityListService,
    trigger_field: str,
    trigger_value: str,
    sample_cap: int,
) -> tuple[int, list[str]]:
    """Page through the service's list endpoint, counting rows where
    ``trigger_field == trigger_value`` and collecting up to ``sample_cap``
    of their ids.

    Returns ``(count, sample_ids)``.
    """
    filters = {trigger_field: trigger_value}
    page = 1
    page_size = max(sample_cap, 50)
    count = 0
    sample_ids: list[str] = []

    while True:
        # Pass the trigger filter when the service supports it; many CRUD
        # services accept arbitrary equality filter dicts, but we tolerate
        # services that ignore unknown filters by re-checking each row.
        result = await service.list(page=page, page_size=page_size, filters=filters)
        if not isinstance(result, dict):
            break
        items = result.get("items", [])
        if not items:
            break

        for row in items:
            value = _row_field(row, trigger_field)
            if value != trigger_value:
                continue
            count += 1
            if len(sample_ids) < sample_cap:
                row_id = _row_id(row)
                if row_id is not None:
                    sample_ids.append(row_id)

        total = result.get("total", count)
        if (page * page_size) >= total or len(items) < page_size:
            break
        page += 1
    return count, sample_ids


# =============================================================================
# Module-level handler
# =============================================================================


async def _list_pending_approvals(
    services_by_entity: dict[str, EntityListService],
    approvals: list[ApprovalSpec],
    limit: int = Query(
        default=20,
        ge=1,
        le=100,
        description="Maximum sample_ids returned per approval block.",
    ),
) -> ApprovalPendingResponse:
    """List pending rows for every declared ApprovalSpec.

    For each ``ApprovalSpec`` we look up the entity's CRUD service and
    count rows where ``trigger_field == trigger_value``, returning up to
    ``limit`` sample row ids per approval.
    """
    summaries: list[ApprovalSummary] = []
    total_pending = 0

    for approval in approvals:
        entity = approval.entity
        trigger_field = approval.trigger_field or "status"
        trigger_value = approval.trigger_value

        service = services_by_entity.get(entity)
        if service is None:
            summaries.append(
                ApprovalSummary(
                    name=approval.name,
                    title=approval.title,
                    entity=entity,
                    trigger_field=trigger_field,
                    trigger_value=trigger_value,
                    count=0,
                    sample_ids=[],
                    error=f"No CRUD service registered for entity '{entity}'",
                )
            )
            continue

        try:
            count, sample_ids = await _query_pending_rows(
                service, trigger_field, trigger_value, sample_cap=limit
            )
        except Exception as e:  # pragma: no cover — defensive
            logger.warning(
                "Failed to list pending approvals for '%s' (%s): %s",
                approval.name,
                entity,
                e,
            )
            summaries.append(
                ApprovalSummary(
                    name=approval.name,
                    title=approval.title,
                    entity=entity,
                    trigger_field=trigger_field,
                    trigger_value=trigger_value,
                    count=0,
                    sample_ids=[],
                    error=str(e),
                )
            )
            continue

        total_pending += count
        summaries.append(
            ApprovalSummary(
                name=approval.name,
                title=approval.title,
                entity=entity,
                trigger_field=trigger_field,
                trigger_value=trigger_value,
                count=count,
                sample_ids=sample_ids,
            )
        )

    return ApprovalPendingResponse(
        approvals=summaries,
        total_pending=total_pending,
        limit=limit,
    )


# =============================================================================
# Approvals Explorer Routes
# =============================================================================


def create_approvals_routes(
    services_by_entity: dict[str, EntityListService],
    approvals: list[ApprovalSpec],
) -> APIRouter:
    """Create approvals explorer routes for runtime inspection.

    Args:
        services_by_entity: Dict keyed by ``service.entity_name`` —
            matches the shape returned by
            ``service_generator.services_by_entity()``.
        approvals: The list of declared ``ApprovalSpec`` blocks
            (``ctx.appspec.approvals``).

    Returns:
        APIRouter with the ``/_dazzle/approvals/*`` endpoints.
    """
    router = APIRouter(prefix="/_dazzle/approvals", tags=["Approvals Explorer"])

    router.add_api_route(
        "/pending",
        partial(_list_pending_approvals, services_by_entity, approvals),
        methods=["GET"],
        response_model=ApprovalPendingResponse,
    )

    return router
