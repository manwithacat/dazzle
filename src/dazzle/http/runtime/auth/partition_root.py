"""Resolve a membership's ``archetype:tenant`` partition root (#1463).

The shared_schema RLS fence reads ``dazzle.tenant_id`` and matches it against each
row's partition-key column, which is populated at the **partition root** — the
top of the ``parent:`` chain of tenant-host kinds (ADR-0036/0037). A membership,
however, may be held at a *leaf* kind (e.g. a ``School`` in a ``Trust ▸ School``
tree) so the session can be host-confined to that leaf. Binding the raw
``membership.tenant_id`` (the School) then mismatches the rows' root (the Trust)
and the fence hides everything (#1463).

This module resolves the partition root **once, at write time** (``create_membership``)
and on boot reconciliation, so the security-critical bind path stays a synchronous,
inference-free column read (``membership.partition_root_id or tenant_id``).

The walk is a sync SQL probe-then-ascend over the *same* shared-schema database the
``memberships`` table lives in:

  1. **kind-probe** — the membership only stores an id, not its kind, so probe each
     non-root tenant-host kind's table for a row with that id.
  2. **ascend** — from the found kind, follow each kind's ``parent:`` FK column up
     the chain until a kind with no parent edge (the root); return that id.

Fail-safe: any gap (id not found at a non-root kind, NULL parent FK, a cycle, the
depth cap) returns the deepest id resolved so far. That can only ever *narrow*
visibility (bind a descendant, fence shows fewer rows) — never broaden it — so a
data anomaly degrades closed, not open.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from dazzle.http.runtime.query_builder import quote_identifier, validate_sql_identifier

logger = logging.getLogger(__name__)

# Mirrors the resolver's ancestor-walk cap (tenant.resolver._MAX_ANCESTOR_WALK):
# a defensive bound against a malformed parent chain that escaped link-time
# cycle validation.
_MAX_WALK = 16


@dataclass(frozen=True)
class PartitionHierarchy:
    """The tenant-host ``parent:`` graph, distilled to what the root walk needs.

    ``parent_edges`` maps a non-root tenant kind (entity/table name) to
    ``(parent_fk_column, parent_kind)`` — the ``ref`` column on that kind whose
    value is the parent row's id, and the parent kind's table name. A kind absent
    from this map is a root (or flat) kind. Empty map ⇒ no hierarchy
    (``build_partition_hierarchy`` returns ``None`` in that case).
    """

    parent_edges: dict[str, tuple[str, str]]

    @property
    def probe_kinds(self) -> tuple[str, ...]:
        """The kinds a leaf/mid membership id could belong to (those with a parent
        edge). A root-kind id never needs widening, so the probe skips root kinds —
        an unmatched probe simply returns the id unchanged."""
        return tuple(self.parent_edges.keys())


def build_partition_hierarchy(entities: Any) -> PartitionHierarchy | None:
    """Build the partition hierarchy from the app's IR entities, or ``None``.

    ``entities`` is ``appspec.domain.entities``. Reads each entity's
    ``tenant_host.parent`` edge (a ``ref`` field naming the parent kind) and the
    ref field's target. Returns ``None`` when no entity declares a ``parent:``
    edge (flat / single-level tenancy — the root walk is a no-op there and
    ``create_membership`` stores ``partition_root_id = tenant_id``).

    Table and column names are validated as safe SQL identifiers here (build time)
    so the resolver can interpolate them — they originate from the IR, never user
    input, but validating loud-fails on any malformed identifier rather than at
    query time.
    """
    parent_edges: dict[str, tuple[str, str]] = {}
    for e in entities or []:
        th = getattr(e, "tenant_host", None)
        if th is None:
            continue
        parent_fk = getattr(th, "parent", None)
        if not parent_fk:
            continue  # root / flat kind — no edge
        kind = e.name
        # The ref field named by `parent:` — its target is the parent kind. The
        # column name equals the field name (Dazzle stores `foo: ref Bar` as column
        # `foo`, e.g. Project.owner for `owner: ref Member`).
        field = next((f for f in getattr(e, "fields", []) if f.name == parent_fk), None)
        parent_kind = getattr(getattr(field, "type", None), "ref_entity", None) if field else None
        if not parent_kind:
            continue  # malformed edge → skip (link-time validation should catch)
        validate_sql_identifier(kind, "tenant kind table")
        validate_sql_identifier(parent_fk, "parent FK column")
        validate_sql_identifier(str(parent_kind), "parent kind table")
        parent_edges[kind] = (parent_fk, str(parent_kind))
    return PartitionHierarchy(parent_edges=parent_edges) if parent_edges else None


def resolve_partition_root(cur: Any, tenant_id: str, hierarchy: PartitionHierarchy | None) -> str:
    """Return the partition-root id for ``tenant_id`` (or ``tenant_id`` itself).

    ``cur`` is an open psycopg cursor (``dict_row``) on the shared-schema DB — the
    walk reuses the caller's transaction so it sees rows committed before it. When
    ``hierarchy`` is ``None`` (flat tenancy) the input is returned unchanged.

    Comparisons use ``id::text = %s`` so the probe is agnostic to whether a kind's
    pk column is ``uuid`` or ``text``; the returned id is always text.
    """
    if hierarchy is None:
        return tenant_id

    # 1. kind-probe: which non-root kind owns this id? (Root-kind ids are skipped —
    # they already equal their own partition root.) This relies on tenant ids being
    # globally unique across the tenant-kind tables — already a hard invariant of the
    # RLS model (the partition_key is compared globally, so colliding ids across two
    # tenant tables would break the fence everywhere, not just here). uuid pks (the
    # tenant-kind norm) guarantee it; the first matching kind is therefore THE kind.
    start_kind: str | None = None
    for kind in hierarchy.probe_kinds:
        cur.execute(
            f"SELECT 1 AS hit FROM {quote_identifier(kind)} WHERE id::text = %s LIMIT 1",
            (tenant_id,),
        )
        if cur.fetchone() is not None:
            start_kind = kind
            break
    if start_kind is None:
        return tenant_id  # a root-kind id, or an id not found at any leaf/mid kind

    # 2. ascend the parent chain to the root.
    cur_kind, cur_id = start_kind, tenant_id
    seen: set[str] = {cur_id}
    for _ in range(_MAX_WALK):
        edge = hierarchy.parent_edges.get(cur_kind)
        if edge is None:
            return cur_id  # reached a kind with no parent edge → the root
        parent_fk, parent_kind = edge
        cur.execute(
            f"SELECT {quote_identifier(parent_fk)}::text AS pid "
            f"FROM {quote_identifier(cur_kind)} WHERE id::text = %s",
            (cur_id,),
        )
        row = cur.fetchone()
        parent_id = row.get("pid") if row else None
        if not parent_id:
            return cur_id  # NULL parent FK / row gone → stop (narrow, fail-closed)
        if parent_id in seen:
            return cur_id  # cycle guard (validator should have rejected) → truncate
        seen.add(parent_id)
        cur_kind, cur_id = parent_kind, parent_id
    return cur_id


def reconcile_membership_partition_roots(store: Any, hierarchy: PartitionHierarchy | None) -> int:
    """Backfill / refresh every membership's ``partition_root_id`` (#1463).

    Run once at boot for tenant-hierarchy apps. Recomputes each membership's root
    via :func:`resolve_partition_root` and writes any that are ``NULL`` (a
    pre-existing row created before this fix) or **stale** (the tenant was
    re-parented across roots since the row was written — the "refresh on the rare
    cross-root re-parent" case). Idempotent: a second run with no change updates
    nothing, so concurrent boot workers converge.

    ``store`` is an ``AuthStore`` (uses its sync ``_transaction``). Returns the
    number of rows updated. ``None`` hierarchy (flat tenancy) is a no-op — flat
    rows are correct via the bind-path fallback and new writes set the value
    directly.

    A reconciliation failure degrades **closed**: an un-backfilled leaf membership
    binds its raw ``tenant_id`` (a descendant), so the fence shows *fewer* rows,
    never more. The caller therefore logs and continues rather than aborting boot.
    """
    if hierarchy is None:
        return 0
    updated = 0
    with store._transaction() as cur:
        # `rows` is materialised (list(fetchall())) BEFORE the loop reuses `cur` for
        # the per-row probe/ascend SELECTs + UPDATE — safe because resolve_partition_root
        # only queries the tenant-kind tables, never `memberships`, so the cursor is
        # never re-reading the result set it's iterating. Keep that invariant if the
        # resolver ever changes.
        cur.execute("SELECT id, tenant_id, partition_root_id FROM memberships")
        rows = list(cur.fetchall())
        for r in rows:
            root = resolve_partition_root(cur, r["tenant_id"], hierarchy)
            if root != r.get("partition_root_id"):
                cur.execute(
                    "UPDATE memberships SET partition_root_id = %s, updated_at = %s WHERE id = %s",
                    (root, datetime.now(UTC).isoformat(), r["id"]),
                )
                updated += 1
    if updated:
        logger.info("reconcile_membership_partition_roots: backfilled/refreshed %d row(s)", updated)
    return updated
