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

from dazzle.core import ir
from dazzle.http.runtime.atomic_flow_executor import (
    AtomicFlowError,
    execute_atomic_flow,
)

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
    access_specs: dict[str, Any] | None = None,
    fk_graph: Any = None,
    audit_logger: Any = None,
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
        auth_dep: FastAPI dependency yielding the authenticated user
            (an ``AuthContext`` in production wiring). If omitted, the
            route is unauthenticated (test-only).
        access_specs: ``{entity_name: EntityAccessSpec}`` — when provided
            (with an ``AuthContext``-yielding ``auth_dep``), each create
            step is routed through ``scope: create:`` enforcement inside
            the flow transaction (#1313 slice 1b, ADR-0029).
        fk_graph: FK graph for FK-path / EXISTS create-scope probe SQL.
        audit_logger: when provided (with an authed ``auth_dep``), each
            committed step is recorded as an audit fact via the async
            ``AuditLogger`` after the flow commits (#1313, ADR-0029 invariant
            5 — async-enqueue; see the ADR note on the relaxation vs strict
            in-transaction audit).

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
            access_specs=access_specs,
            fk_graph=fk_graph,
            audit_logger=audit_logger,
        )
    return router


def _register_one(
    router: APIRouter,
    flow: ir.AtomicFlowSpec,
    db_manager: Any,
    *,
    user_role_extractor: Callable[[Any], list[str]] | None,
    auth_dep: Callable[..., Any] | None,
    access_specs: dict[str, Any] | None = None,
    fk_graph: Any = None,
    audit_logger: Any = None,
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
        access_specs=access_specs,
        fk_graph=fk_graph,
        audit_logger=audit_logger,
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
    access_specs: dict[str, Any] | None = None,
    fk_graph: Any = None,
    audit_logger: Any = None,
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
            # `user` is the AuthContext from the auth dependency; pass it through
            # so the executor can enforce per-step scope (#1313 1b/1c).
            #
            # #1317 — a `audit: strict` flow writes its audit in-transaction inside
            # the executor (atomic with the mutation), so the async path here is
            # only for the default async-enqueue flows. For strict flows pass no
            # sink; the executor materialises its own and writes it on the flow
            # connection.
            strict = flow.audit_mode == ir.FlowAuditMode.STRICT
            use_async_audit = audit_logger is not None and not strict
            audit_sink: list[dict[str, str]] | None = [] if use_async_audit else None
            result = _run(
                flow,
                body,
                db_manager,
                auth_context=user,
                access_specs=access_specs,
                fk_graph=fk_graph,
                audit_sink=audit_sink,
            )
            # The flow committed (a denial would have raised); record each
            # touched entity as an audit fact via the async logger (#1313,
            # ADR-0029 invariant 5 — async-enqueue), correlated by flow name.
            # Strict flows already recorded in-transaction; skip the async path.
            if use_async_audit and audit_sink:
                await _log_flow_audit(audit_logger, flow.name, user, audit_sink)
            return result

        return authed_handler

    async def open_handler(
        body: InputModel = Body(...),  # type: ignore[valid-type]
    ) -> dict[str, Any]:
        return _run(flow, body, db_manager)

    return open_handler


async def _log_flow_audit(
    audit_logger: Any, flow_name: str, user: Any, audit_sink: list[dict[str, str]]
) -> None:
    """Record each committed atomic step as an audit fact via the async logger.

    One ``decision="allow"`` row per touched entity, correlated by the flow name
    in ``matched_policy`` (``atomic:<flow>``). Best-effort (the logger drops on
    queue overflow); the flow has already committed.
    """
    u = getattr(user, "user", None)
    user_id = str(u.id) if u is not None and getattr(u, "id", None) is not None else None
    user_email = getattr(u, "email", None) if u is not None else None
    user_roles = list(getattr(user, "roles", []) or [])
    for intent in audit_sink:
        await audit_logger.log_decision(
            operation=intent["operation"],
            entity_name=intent["entity"],
            entity_id=intent["entity_id"],
            decision="allow",
            matched_policy=f"atomic:{flow_name}",
            policy_effect="permit",
            user_id=user_id,
            user_email=user_email,
            user_roles=user_roles,
        )


def _run(
    flow: ir.AtomicFlowSpec,
    body: BaseModel,
    db_manager: Any,
    *,
    auth_context: Any = None,
    access_specs: dict[str, Any] | None = None,
    fk_graph: Any = None,
    audit_sink: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    """Execute the flow and translate errors into HTTP responses.

    A ``scope: create:`` denial raises ``HTTPException(403)`` from inside the
    executor (the flow transaction rolls back); it propagates unchanged — only
    ``NotImplementedError`` (stubbed step) and ``AtomicFlowError`` (DB failure)
    are translated here.
    """
    inputs = body.model_dump(mode="python")
    try:
        created = execute_atomic_flow(
            flow,
            inputs,
            db_manager,
            auth_context=auth_context,
            access_specs=access_specs,
            fk_graph=fk_graph,
            audit_sink=audit_sink,
        )
    except NotImplementedError as exc:
        # Defensive: `create` + `update` steps now execute; no step kind is
        # currently stubbed. If a future step kind is added IR-first (executor
        # stub), this surfaces a clean 501 rather than a 500 stacktrace.
        raise HTTPException(
            status_code=501,
            detail={"error": "atomic_step_not_implemented", "message": str(exc)},
        ) from exc
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
