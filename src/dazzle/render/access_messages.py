"""Access-denied detail payloads for HTTP responses.

Builds structured 403/401 detail dicts that disclose enough context for
the error page (or API client) to render a "you're signed in as X, this
page requires Y" message — closes the affordance gap from #808 where
``HTTPException(detail="Forbidden")`` stranded users with no recourse.

Lifted out of ``back.runtime.route_generator`` in #1094 (parent #1086)
so that ``ui/`` page handlers can build the same payload without
crossing the back↔ui boundary.
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)


def _forbidden_detail(
    *,
    entity_name: str,
    operation: Any,
    cedar_access_spec: Any,
    current_roles: list[str] | None = None,
) -> dict[str, Any]:
    """Build a structured 403 detail dict disclosing role requirements.

    Instead of raising ``HTTPException(detail="Forbidden")`` — which
    strands the user with no affordance (see #808) — emit enough
    context for the error page to render a "you're signed in as X,
    this page requires Y" disclosure. The framework already knows
    which personas are permitted for this operation on this entity;
    we just have to thread it through.

    Args:
        entity_name: The entity whose access was denied.
        operation: The access operation (read/list/create/update/…).
        cedar_access_spec: The entity's access spec (has permissions
            with ``personas`` lists per operation).
        current_roles: Roles the requesting user actually had.

    Returns:
        Dict suitable for passing as ``HTTPException(detail=...)``.
        The exception handler unpacks it; API clients receive it
        verbatim as JSON.
    """
    # `operation` may arrive as a string ("create") or an enum
    # (AccessOperationKind.CREATE). Normalise both to lowercase
    # strings so matching against rule.operation (which is an enum)
    # works either way.
    op_str = str(getattr(operation, "value", operation)).lower()

    permitted: list[str] = []
    try:
        for rule in getattr(cedar_access_spec, "permissions", []) or []:
            rule_op = str(
                getattr(getattr(rule, "operation", None), "value", getattr(rule, "operation", None))
            ).lower()
            if rule_op == op_str:
                for p in getattr(rule, "personas", None) or []:
                    if p not in permitted:
                        permitted.append(p)
    except Exception:  # pragma: no cover — defensive: never shadow the 403 (#smells-1.1)
        logger.debug("Permitted-personas computation failed; omitting from 403", exc_info=True)

    return {
        "error": "forbidden",
        "message": f"You don't have permission to {op_str} {entity_name}.",
        "entity": entity_name,
        "operation": op_str,
        "permitted_personas": permitted,
        "current_roles": list(current_roles or []),
    }
