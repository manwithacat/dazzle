"""Set of entity names backed by non-PostgreSQL stores.

``SystemHealth``, ``SystemMetric``, ``ProcessRun``, ``LogEntry``,
``EventTrace`` are synthetic platform entities whose data lives in
Redis or in-memory buffers, not in Postgres. They appear in the
AppSpec (so the admin workspace can render them) but they have no
SQL table — :func:`dazzle.http.runtime.sa_schema.build_metadata`
filters them out, and :func:`dazzle.db.reset.db_reset_impl` must do
the same (#814).

Kept at the ``dazzle.db`` layer so both the server-side schema
builder and the client-side reset helper import the same source of
truth.

``ProcessRun`` exception (#1454): the entity NAME is ambiguous. The
pre-existing *admin-monitoring* ProcessRun is virtual (runtime-state
read, no table). But the *governed* ProcessRun injected when a process
has an ``llm_intent`` step is the AIJob subject — it is uuid-pk,
carries a ``started_by`` RBAC anchor, and is written by
``process_executor._process_run_service``, so it MUST be a real
persisted Postgres table. Discriminate by structure, not name:
:func:`is_virtual_entity` treats a ProcessRun with a ``started_by``
field as real. Call sites must filter via :func:`is_virtual_entity`
(EntitySpec-aware), not a bare ``name in VIRTUAL_ENTITY_NAMES`` check.
"""

from __future__ import annotations

from typing import Any

VIRTUAL_ENTITY_NAMES: frozenset[str] = frozenset(
    {
        "SystemHealth",
        "SystemMetric",
        "ProcessRun",
        "LogEntry",
        "EventTrace",
    }
)


def is_virtual_entity(entity: Any) -> bool:
    """True if ``entity`` has no backing Postgres table.

    Entity-aware companion to :data:`VIRTUAL_ENTITY_NAMES`. Resolves the
    ``ProcessRun`` name ambiguity (#1454): the governed ProcessRun carries a
    ``started_by`` field and IS persisted (real table); the admin-monitoring
    ProcessRun has no ``started_by`` and stays virtual. All other virtual
    entities are decided purely by name.

    Accepts any entity object exposing ``.name`` and a ``.fields`` iterable
    of field objects with a ``.name`` — works on both ``core.ir.EntitySpec``
    and the converted ``http`` FieldSpec shape (duck-typed).
    """
    name = getattr(entity, "name", None)
    if name == "ProcessRun":
        fields = getattr(entity, "fields", None) or ()
        return not any(getattr(f, "name", None) == "started_by" for f in fields)
    return name in VIRTUAL_ENTITY_NAMES
