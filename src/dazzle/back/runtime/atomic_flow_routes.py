"""Atomic-flow route registration (#1228 Phase 3c slice 3c.iii).

Builds a FastAPI router with one ``POST /api/atomic/<name>`` endpoint
per parsed ``AtomicFlowSpec``. Each endpoint:

1. Validates the request body against a Pydantic model auto-generated
   from ``flow.inputs``.
2. Checks the caller's role against ``flow.permit_execute`` — 403 if
   not permitted.
3. Calls :func:`execute_atomic_flow` with the validated inputs.
4. Returns ``{"created": {EntityName: uuid, ...}}`` on success, or
   HTTP 4xx with ``failed_at`` identifying the offending create on
   failure.

The router is intended to be mounted by the runtime server during
startup wiring; the standalone build helper lets unit tests exercise
the router without spinning up the full server.
"""

from collections.abc import Callable
from datetime import date, datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Body, Depends, HTTPException
from pydantic import BaseModel, create_model

from dazzle.back.runtime.atomic_flow_executor import (
    AtomicFlowError,
    execute_atomic_flow,
)
from dazzle.core import ir

# Map IR field-type kinds to Python types for Pydantic input models.
# Conservative: anything not in the map falls back to ``str`` so the
# server boots and the route is callable; richer typing lands as needs
# arise.
_TYPE_MAP: dict[ir.FieldTypeKind, type] = {
    ir.FieldTypeKind.STR: str,
    ir.FieldTypeKind.TEXT: str,
    ir.FieldTypeKind.EMAIL: str,
    ir.FieldTypeKind.URL: str,
    ir.FieldTypeKind.SLUG: str,
    ir.FieldTypeKind.TIMEZONE: str,
    ir.FieldTypeKind.INT: int,
    ir.FieldTypeKind.FLOAT: float,
    ir.FieldTypeKind.DECIMAL: float,
    ir.FieldTypeKind.MONEY: int,  # framework convention: minor units
    ir.FieldTypeKind.BOOL: bool,
    ir.FieldTypeKind.DATE: date,
    ir.FieldTypeKind.DATETIME: datetime,
    ir.FieldTypeKind.UUID: UUID,
    ir.FieldTypeKind.REF: UUID,
}


def build_input_model(flow: ir.AtomicFlowSpec) -> type[BaseModel]:
    """Build a Pydantic model class from the flow's ``inputs:`` block."""
    fields: dict[str, Any] = {}
    for inp in flow.inputs:
        py_type: type = _TYPE_MAP.get(inp.type.kind, str)
        if inp.required:
            fields[inp.name] = (py_type, ...)
        else:
            fields[inp.name] = (py_type | None, None)
    model_name = f"{flow.name.title().replace('_', '')}Input"
    return create_model(model_name, **fields)


def build_atomic_flow_router(
    atomic_flows: list[ir.AtomicFlowSpec],
    db_manager: Any,
    *,
    user_role_extractor: Callable[[Any], list[str]] | None = None,
    auth_dep: Callable[..., Any] | None = None,
) -> APIRouter:
    """Build a router exposing ``POST /api/atomic/<name>`` per flow.

    Args:
        atomic_flows: parsed flow specs (typically from
            ``appspec.atomic_flows``).
        db_manager: runtime DB manager (passed through to the executor).
        user_role_extractor: callable that maps the value returned by
            ``auth_dep`` to a list of role names the user holds. The
            handler checks the intersection with ``flow.permit_execute``.
            If omitted, permit enforcement is skipped (acceptable for
            test wiring; production wiring should always pass one).
        auth_dep: FastAPI dependency yielding the authenticated user.
            If omitted, the route is unauthenticated (test-only).

    Returns:
        An ``APIRouter`` with prefix ``/api/atomic``.
    """
    router = APIRouter(prefix="/api/atomic", tags=["atomic"])

    for flow in atomic_flows:
        _register_one(
            router,
            flow,
            db_manager,
            user_role_extractor=user_role_extractor,
            auth_dep=auth_dep,
        )
    return router


def _register_one(
    router: APIRouter,
    flow: ir.AtomicFlowSpec,
    db_manager: Any,
    *,
    user_role_extractor: Callable[[Any], list[str]] | None,
    auth_dep: Callable[..., Any] | None,
) -> None:
    """Register a single flow's POST endpoint."""
    InputModel = build_input_model(flow)
    permitted = set(flow.permit_execute)

    handler = _make_handler(
        flow,
        db_manager,
        InputModel,
        permitted,
        user_role_extractor=user_role_extractor,
        auth_dep=auth_dep,
    )
    handler.__name__ = f"atomic_{flow.name}"
    handler.__doc__ = flow.intent or flow.label

    router.add_api_route(
        f"/{flow.name}",
        handler,
        methods=["POST"],
        name=f"atomic.{flow.name}",
        summary=flow.label,
        description=flow.intent,
    )


def _make_handler(
    flow: ir.AtomicFlowSpec,
    db_manager: Any,
    InputModel: type[BaseModel],
    permitted: set[str],
    *,
    user_role_extractor: Callable[[Any], list[str]] | None,
    auth_dep: Callable[..., Any] | None,
) -> Callable[..., Any]:
    """Build the actual FastAPI handler closure for one flow."""
    if auth_dep is not None:

        async def authed_handler(
            body: InputModel = Body(...),  # type: ignore[valid-type]
            user: Any = Depends(auth_dep),
        ) -> dict[str, Any]:
            if user_role_extractor is not None:
                user_roles = set(user_role_extractor(user))
                if not (user_roles & permitted):
                    raise HTTPException(
                        status_code=403,
                        detail=(
                            f"Atomic flow '{flow.name}' requires one of "
                            f"{sorted(permitted)}; user has {sorted(user_roles)}."
                        ),
                    )
            return _run(flow, body, db_manager)

        return authed_handler

    async def open_handler(
        body: InputModel = Body(...),  # type: ignore[valid-type]
    ) -> dict[str, Any]:
        return _run(flow, body, db_manager)

    return open_handler


def _run(flow: ir.AtomicFlowSpec, body: BaseModel, db_manager: Any) -> dict[str, Any]:
    """Execute the flow and translate errors into HTTP responses."""
    inputs = body.model_dump(mode="python")
    try:
        created = execute_atomic_flow(flow, inputs, db_manager)
    except AtomicFlowError as exc:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "atomic_flow_failed",
                "failed_at": exc.failed_at,
                "message": str(exc),
            },
        ) from exc
    return {"created": {name: str(uid) for name, uid in created.items()}}
