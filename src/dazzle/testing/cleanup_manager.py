"""Created-entity tracking + dependency-safe teardown for the agent-E2E harness (#1446).

Extracted from ``DazzleClient`` (which had accreted transport, auth, CRUD, cleanup,
schema and data-generation onto one object). ``CleanupManager`` owns the list of
entities a test run created and tears them down in FK-dependency order, plus the
post-cleanup residue scan. It needs a client for the three capabilities it doesn't
own — ``get_spec`` (FK graph), ``delete_entity`` (teardown), ``get_entities``
(residue scan) — injected via the constructor.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from dazzle.testing.test_runner import DazzleClient

logger = logging.getLogger(__name__)


@dataclass
class CleanupReport:
    """#1307: outcome of :meth:`CleanupManager.cleanup_created_entities`.

    Pre-#1307 cleanup returned a bare ``(deleted, failed)`` tuple and counted
    every HTTP 404 at teardown as a *failure* — producing the alarming
    ``"N failed"`` line even though a 404 means the row is already gone (cleanup
    succeeded). The three-way split makes the report honest:

    - ``deleted`` — rows actually removed (200/204).
    - ``absent``  — rows already gone (404). Success for cleanup's purpose.
    - ``failed``  — genuine failures (auth/server/network); the row may persist.

    ``created_types`` is the set of entity types this run created, captured
    before the tracking list is cleared, so the caller can run the post-cleanup
    residue scan (``detect_residue``) over exactly those types.
    """

    deleted: int = 0
    absent: int = 0
    failed: int = 0
    created_types: list[str] = field(default_factory=list)


class CleanupManager:
    """Tracks created entities and tears them down in FK-dependency order.

    ``client`` supplies ``get_spec`` (FK graph), ``delete_entity`` (teardown), and
    ``get_entities`` (residue scan).
    """

    def __init__(self, client: DazzleClient):
        self._client = client
        # (entity_name, entity_id) of every row the run created — written by
        # DazzleClient.create_entity and the runner's post-step tracking.
        self.created: list[tuple[str, str]] = []

    def track(self, entity_name: str, entity_id: str) -> None:
        """Record a created entity for later dependency-safe teardown."""
        self.created.append((entity_name, entity_id))

    def _build_fk_reverse_map(self) -> dict[str, list[tuple[str, str]]]:
        """Build a map of parent_entity → [(child_entity, fk_field), ...] from the app spec.

        Used by cleanup to cascade-delete child records before parents.
        """
        result: dict[str, list[tuple[str, str]]] = {}
        spec = self._client.get_spec()
        if not spec:
            return result
        entities = spec.get("entities") or []
        if not entities:
            # Try domain.entities (full spec format)
            domain = spec.get("domain") or {}
            entities = domain.get("entities") or []
        for entity in entities:
            entity_name = entity.get("name", "")
            for fld in entity.get("fields", []):
                ftype = fld.get("type") or {}
                if ftype.get("kind") == "ref" and ftype.get("ref_entity"):
                    parent = ftype["ref_entity"]
                    result.setdefault(parent, []).append((entity_name, fld["name"]))
        return result

    def _topo_sort_for_delete(
        self,
        fk_map: dict[str, list[tuple[str, str]]],
    ) -> list[tuple[str, str]]:
        """Sort tracked entities so children come before parents.

        Uses the FK reverse map to determine entity-type ordering:
        if entity B has a FK to entity A, B must be deleted first.
        Within each type-level, entities keep their LIFO order.
        """
        tracked_types: set[str] = {name for name, _id in self.created}

        # Build adjacency list: child → parent (child must be deleted first).
        # Kahn's algorithm processes nodes with in_degree 0 first, so children
        # (no incoming edges) get the lowest order indices.
        successors: dict[str, set[str]] = {t: set() for t in tracked_types}
        in_degree: dict[str, int] = dict.fromkeys(tracked_types, 0)
        for parent_type, children in fk_map.items():
            if parent_type not in tracked_types:
                continue
            for child_type, _fk_field in children:
                if child_type in tracked_types and parent_type not in successors[child_type]:
                    successors[child_type].add(parent_type)
                    in_degree[parent_type] += 1

        # Deterministic LIFO ordering for tie-breaking (preserves LIFO for
        # unrelated types that all have in_degree 0).
        lifo_types = list(dict.fromkeys(name for name, _id in reversed(self.created)))
        queue = [t for t in lifo_types if in_degree[t] == 0]

        type_order: dict[str, int] = {}
        order_idx = 0
        while queue:
            t = queue.pop(0)
            type_order[t] = order_idx
            order_idx += 1
            for succ in successors.get(t, set()):
                in_degree[succ] -= 1
                if in_degree[succ] == 0:
                    queue.append(succ)

        # Types not in type_order (cycles) get highest index (delete last)
        max_order = order_idx
        for t in tracked_types:
            if t not in type_order:
                type_order[t] = max_order

        # Stable sort: primary by type_order (children=low, parents=high),
        # secondary preserves LIFO within same type-level.
        reversed_entities = list(reversed(self.created))
        reversed_entities.sort(key=lambda pair: type_order.get(pair[0], max_order))
        return reversed_entities

    def cleanup_created_entities(self) -> CleanupReport:
        """Delete all tracked entities in dependency-safe order.

        Uses the FK graph to topologically sort tracked entities so children
        are deleted before parents. Only deletes entities that were created
        during this test run — **no API queries for untracked records** (the
        #410 invariant; the residue scan is a *separate* phase, see
        ``detect_residue``). Uses multi-pass for remaining FK constraint
        failures.

        Returns a :class:`CleanupReport` (#1307) splitting deleted / absent
        (404 → already gone) / failed, plus the set of created entity types.
        """
        created_types = sorted({name for name, _id in self.created})
        if not self.created:
            return CleanupReport(created_types=created_types)

        # Build FK graph and sort tracked entities
        fk_map = self._build_fk_reverse_map()
        pending = self._topo_sort_for_delete(fk_map)

        # Deduplicate (same entity may be tracked multiple times)
        seen: set[tuple[str, str]] = set()
        unique_pending: list[tuple[str, str]] = []
        for pair in pending:
            if pair not in seen:
                seen.add(pair)
                unique_pending.append(pair)
        pending = unique_pending

        deleted = 0
        absent = 0
        max_passes = 3

        for pass_num in range(max_passes):
            still_pending: list[tuple[str, str]] = []
            pass_progress = 0
            for entity_name, entity_id in pending:
                outcome = self._client.entities.delete_entity(entity_name, entity_id)
                if outcome == "deleted":
                    deleted += 1
                    pass_progress += 1
                elif outcome == "absent":
                    # Already gone — success for cleanup. Don't retry (a 404
                    # won't become a 200 on a later pass).
                    absent += 1
                    pass_progress += 1
                else:
                    still_pending.append((entity_name, entity_id))
            pending = still_pending
            if not pending:
                break
            # Bail if no progress after first pass — retrying won't help
            if pass_num > 0 and pass_progress == 0:
                break

        self.created.clear()
        return CleanupReport(
            deleted=deleted,
            absent=absent,
            failed=len(pending),
            created_types=created_types,
        )

    def detect_residue(self, entity_types: list[str]) -> dict[str, int]:
        """Count test-data rows still present after cleanup (#1307).

        A SEPARATE phase from ``cleanup_created_entities`` (which is delete-only,
        per the #410 invariant) — this one *does* query the API. For each given
        entity type it lists the rows and counts those bearing this run's
        test-data signature (``is_generated_test_value`` — every runner-created
        row carries at least one generated string field). A nonzero count means
        cleanup left rows behind: rows the runner created but whose ids it never
        tracked (e.g. cascade-created children, or an id the create response
        didn't surface), which tracked-id deletion can't reach.

        Returns ``{entity_type: leftover_count}`` for types with residue > 0.
        Best-effort: a per-type query failure is skipped, not fatal.
        """
        from dazzle.core.field_values import is_generated_test_value

        residue: dict[str, int] = {}
        for entity_name in sorted(set(entity_types)):
            try:
                rows = self._client.entities.get_entities(entity_name)
            except Exception:
                logger.debug("residue scan: get_entities(%s) failed", entity_name, exc_info=True)
                continue
            count = sum(
                1
                for row in rows
                if isinstance(row, dict) and any(is_generated_test_value(v) for v in row.values())
            )
            if count:
                residue[entity_name] = count
        return residue
