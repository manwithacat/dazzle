"""RBAC visibility for audit history (#956 cycle 7).

Wraps the cycle-1 ``AuditShowTo`` declaration into a runtime gate. The
audit *write* path captures every change regardless of viewer
identity (cycle 4); this module decides which viewers can *see* the
captured history on the detail surface.

Pairs with the ``load_history`` orchestrator below: the loader pulls
rows from the AuditEntry service, filters by entity, decodes (cycle
6), groups (cycle 6) — but only if `can_view_audit_history` passes.
Cycle 8 will hook this into the detail-surface region renderer.

The gate currently supports the ``"persona"`` ``show_to`` kind —
returns True when the viewer's personas intersect the allow-list. An
empty allow-list is *deny by default* (matches the pre-#957 RBAC
philosophy: explicit grant or no access). Future kinds (``"role"``,
``"all"``) plug into the same dispatch in ``can_view_audit_history``.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from typing import Any

from dazzle_back.runtime.audit_history import (
    HistoryChange,
    decode_audit_row,
    group_by_change,
)

logger = logging.getLogger(__name__)


def find_audit_spec(audits: Iterable[Any], entity_type: str) -> Any | None:
    """Return the first ``AuditSpec`` matching ``entity_type``, or None.

    `appspec.audits` carries one entry per `audit on X:` block. The
    cycle-3 emitter writes per-entity-type rows; this lookup is what
    the loader uses to decide *whether* the entity is audited at all
    and what its ``show_to`` policy is.
    """
    for spec in audits:
        if getattr(spec, "entity", None) == entity_type:
            return spec
    return None


def can_view_audit_history(audit_spec: Any, viewer_personas: Iterable[str]) -> bool:
    """Decide whether ``viewer_personas`` is allowed to see the history.

    Args:
        audit_spec: The matched ``AuditSpec`` for the entity. None
            means "no audit block declared for this entity" — caller
            should already short-circuit before calling this.
        viewer_personas: The active user's persona names. Compared
            against ``audit_spec.show_to.personas`` for the
            ``"persona"`` kind.

    Returns:
        True when the viewer can see the history, False otherwise.
        Empty / missing show_to defaults to *deny* — explicit grant
        is required, matching the framework's deny-by-default RBAC.
    """
    if audit_spec is None:
        return False
    show_to = getattr(audit_spec, "show_to", None)
    if show_to is None:
        return False

    kind = getattr(show_to, "kind", "persona")
    personas = list(getattr(show_to, "personas", []) or [])

    if kind == "persona":
        if not personas:
            return False  # explicit deny — no allow-list
        viewer_set = set(viewer_personas)
        return any(p in viewer_set for p in personas)

    # Future kinds (`"role"`, `"all"`) land here. For unknown values
    # we deny rather than open by default — fail-closed RBAC.
    logger.warning("Unknown show_to.kind %r — denying", kind)
    return False


async def load_history(
    *,
    audit_service: Any,
    audit_spec: Any,
    entity_type: str,
    entity_id: str,
    viewer_personas: Iterable[str],
    limit: int = 200,
) -> list[HistoryChange]:
    """Fetch + decode + group audit history for one entity row.

    Returns an empty list on any of:
      * `audit_spec` is None (entity not audited)
      * Viewer's personas don't satisfy ``show_to`` (RBAC deny)
      * No matching rows in the AuditEntry table

    The async DB call is the only IO this module does; everything
    else (visibility check, decode, group) is pure and tested
    independently in cycles 6 and 7.

    Args:
        audit_service: The framework's ``AuditEntry`` service from
            ``server.services["AuditEntry"]``. Must support
            ``await service.list(filters=..., page=..., page_size=...)``
            returning a list of dicts (or a paged response with
            ``items``).
        audit_spec: The matched ``AuditSpec`` for ``entity_type`` —
            typically obtained via ``find_audit_spec``.
        entity_type, entity_id: Discriminators for the AuditEntry
            row filter.
        viewer_personas: For RBAC. None / empty → deny.
        limit: Max rows to fetch — bounded so a long-lived row's
            history doesn't blow up the response.
    """
    if audit_spec is None:
        return []
    if not can_view_audit_history(audit_spec, viewer_personas):
        return []

    try:
        rows = await audit_service.list(
            filters={"entity_type": entity_type, "entity_id": entity_id},
            page=1,
            page_size=limit,
        )
    except Exception:
        logger.warning(
            "Audit history fetch failed for %s/%s", entity_type, entity_id, exc_info=True
        )
        return []

    # Service returns either a list of dicts or a paged response with
    # ``items`` — accept both shapes so cycle 8's region renderer
    # works regardless of which list-endpoint variant is wired.
    if isinstance(rows, dict) and "items" in rows:
        raw_items = rows["items"]
    else:
        raw_items = rows

    if not raw_items:
        return []

    entries = [decode_audit_row(_to_dict(r)) for r in raw_items]
    return group_by_change(entries)


def _to_dict(row: Any) -> dict[str, Any]:
    """Coerce one AuditEntry row to a dict — handles Pydantic models."""
    if isinstance(row, dict):
        return row
    if hasattr(row, "model_dump"):
        dumped: dict[str, Any] = row.model_dump()
        return dumped
    # Last resort — vars() handles dataclasses / SimpleNamespace.
    return dict(vars(row))
