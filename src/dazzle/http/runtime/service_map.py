"""Entity-name view over the service registry.

``ctx.services`` (and the ``services`` dict every subsystem receives) is keyed by
*service name* (``list_tasks``, ``create_task``, …). Anything that starts from an
entity — island routes, transition-effect wiring (#1797) — needs the entity's
CRUD service and must not guess the key.
"""

from __future__ import annotations

from typing import Any


def entity_service_map(services: dict[str, Any]) -> dict[str, Any]:
    """``{entity_name: service}`` — the first service carrying each ``entity_name``."""
    entity_map: dict[str, Any] = {}
    for svc in services.values():
        ename = getattr(svc, "entity_name", None)
        if ename and ename not in entity_map:
            entity_map[ename] = svc
    return entity_map
