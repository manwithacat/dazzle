"""Wire #956 audit emitter callbacks against the service generator.

Cycle 3 built the diff computation and callback factory in
``audit_emitter``. Cycle 4 wires them into the runtime: for every
``audit on Entity:`` block in the AppSpec, register the emitter's
on_created / on_updated / on_deleted against the entity's service so
mutations capture before/after rows in the AuditEntry table.

The writer closure dispatches each diff row to the AuditEntry service
via its create_schema. The user-ID provider reads the cycle-4
ContextVar so audit rows pick up the active request's user without
threading through callback args.

This module is imported and called from ``server.py`` once services
are built and project hooks are registered. It silently no-ops for
apps without any ``audit:`` blocks.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def register_audit_callbacks(
    services: dict[str, Any],
    audits: list[Any],
) -> int:
    """Register audit-emitter callbacks for every ``audit on X:`` block.

    Args:
        services: ``{entity_name: BaseService}`` from the running
            server. Must include the framework's ``AuditEntry`` service
            when ``audits`` is non-empty (cycle 2 injects the entity).
        audits: List of ``AuditSpec`` from
            ``appspec.audits`` — each declares which entity to audit,
            which fields to track, and retention policy.

    Returns:
        Number of audit blocks successfully wired. Apps without audit
        blocks return 0; missing services / missing AuditEntry log a
        warning and skip rather than raising — audit registration must
        not break a deploy.
    """
    if not audits:
        return 0

    audit_service = services.get("AuditEntry")
    if audit_service is None:
        logger.warning(
            "Cannot wire audit callbacks: AuditEntry service missing. "
            "Cycle-2 linker injection should have added it; check the "
            "linker output for `audit on X:` blocks."
        )
        return 0

    from dazzle_back.runtime.audit_context import get_current_user_id
    from dazzle_back.runtime.audit_emitter import build_audit_callbacks

    writer = _make_audit_writer(audit_service)
    wired = 0

    for audit_spec in audits:
        entity_name = audit_spec.entity
        target_service = services.get(entity_name)
        if target_service is None:
            logger.warning(
                "Cannot wire audit for %s: service not found in services dict",
                entity_name,
            )
            continue

        callbacks = build_audit_callbacks(
            entity_type=entity_name,
            track=list(audit_spec.track),
            writer=writer,
            user_id_provider=get_current_user_id,
        )

        # `BaseService.on_*` accept a single async callable with the
        # standard four-arg shape — wired in service_generator.py.
        target_service.on_created(callbacks["on_created"])
        target_service.on_updated(callbacks["on_updated"])
        target_service.on_deleted(callbacks["on_deleted"])
        wired += 1

    if wired:
        logger.info("Wired audit callbacks for %d entit%s", wired, "y" if wired == 1 else "ies")
    return wired


def _make_audit_writer(audit_service: Any) -> Any:
    """Build the async writer closure that persists AuditEntry rows.

    The closure dispatches each row to the AuditEntry service via its
    create_schema (a Pydantic model). Failures are swallowed by the
    emitter's outer best-effort wrapper; this layer just produces the
    model and calls ``.create``.
    """
    create_schema = getattr(audit_service, "create_schema", None)
    if create_schema is None:
        # Fallback: pass the dict through to a generic execute path.
        async def _no_schema_writer(rows: list[dict[str, Any]]) -> None:
            for row in rows:
                await audit_service.execute(operation="create", data=row)

        return _no_schema_writer

    async def _writer(rows: list[dict[str, Any]]) -> None:
        for row in rows:
            try:
                model = create_schema(**row)
            except Exception:
                # Schema validation failure on a single row shouldn't
                # block the others — log and skip.
                logger.warning(
                    "AuditEntry schema validation failed for row %r — skipping",
                    row,
                    exc_info=True,
                )
                continue
            await audit_service.create(model)

    return _writer
