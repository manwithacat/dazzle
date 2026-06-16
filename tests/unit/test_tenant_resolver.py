"""Unit tests for tenant Resolver (#1289 slice 2)."""

from __future__ import annotations

import dataclasses
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest

from dazzle.back.runtime.tenant.resolver import (
    EntityProbe,
    ExpiredHistoryHit,
    HistoryHit,
    HistoryProbe,
    ResolvedTenant,
    Resolver,
)


def _id(n: int) -> UUID:
    return UUID(int=n)


# ---------------------------------------------------------------------------
# Result dataclasses
# ---------------------------------------------------------------------------


def test_resolved_tenant_is_frozen():
    rt = ResolvedTenant(kind="Trust", id=uuid4(), slug="acme", name="Acme")
    with pytest.raises(dataclasses.FrozenInstanceError):
        rt.slug = "other"  # type: ignore[misc]


def test_history_hit_carries_old_and_new_slugs():
    h = HistoryHit(old_slug="acme", new_slug="acme-corp")
    assert h.old_slug == "acme"
    assert h.new_slug == "acme-corp"


def test_expired_history_hit_is_distinct_type():
    e = ExpiredHistoryHit(old_slug="acme", new_slug="acme-corp")
    assert not isinstance(e, HistoryHit)


# ---------------------------------------------------------------------------
# Lookup chain
# ---------------------------------------------------------------------------


async def test_lookup_returns_first_matching_entity():
    rows = {("Trust", "acme"): {"id": _id(1), "slug": "acme", "name": "Acme"}}
    r = Resolver(
        probes=[EntityProbe("Trust", "slug"), EntityProbe("School", "slug")],
        history_probe=None,
        lookup_fn=lambda e, s: rows.get((e, s)),
    )
    res = await r.lookup("acme")
    assert isinstance(res, ResolvedTenant)
    assert res.kind == "Trust"
    assert res.id == _id(1)


async def test_lookup_falls_through_to_second_entity():
    rows = {
        ("School", "westwood"): {"id": _id(2), "slug": "westwood", "name": "Westwood"},
    }
    r = Resolver(
        probes=[EntityProbe("Trust", "slug"), EntityProbe("School", "slug")],
        history_probe=None,
        lookup_fn=lambda e, s: rows.get((e, s)),
    )
    res = await r.lookup("westwood")
    assert isinstance(res, ResolvedTenant)
    assert res.kind == "School"


async def test_lookup_returns_none_when_no_match_and_no_history():
    r = Resolver(
        probes=[EntityProbe("Trust", "slug")],
        history_probe=None,
        lookup_fn=lambda e, s: None,
    )
    assert await r.lookup("missing") is None


class _Entity:
    """A non-subscriptable row object, like the default Repository.list() shape."""

    def __init__(self, id: UUID, slug: str, name: str | None) -> None:
        self.id = id
        self.slug = slug
        self.name = name


async def test_lookup_tolerates_entity_object_rows() -> None:
    # #1396: Repository.list() returns entity OBJECTS, not dicts. Subscripting one
    # raised `TypeError: '<Entity>' object is not subscriptable` → 502 on every
    # matched-tenant request. The resolver must read fields via attribute access.
    rows = {("School", "westwood"): _Entity(_id(7), "westwood", "Westwood")}
    r = Resolver(
        probes=[EntityProbe("School", "slug")],
        history_probe=None,
        lookup_fn=lambda e, s: rows.get((e, s)),
    )
    res = await r.lookup("westwood")
    assert isinstance(res, ResolvedTenant)
    assert res.kind == "School"
    assert res.id == _id(7)
    assert res.slug == "westwood"
    assert res.name == "Westwood"


async def test_lookup_entity_object_with_custom_slug_field() -> None:
    # The slug field is probe-configurable; attribute access must honour it.
    rows = {("Trust", "acme"): _Entity(_id(8), "acme", None)}
    r = Resolver(
        probes=[EntityProbe("Trust", "slug")],
        history_probe=None,
        lookup_fn=lambda e, s: rows.get((e, s)),
    )
    res = await r.lookup("acme")
    assert isinstance(res, ResolvedTenant)
    assert res.name is None  # missing name → None, not an AttributeError


async def test_lookup_returns_history_hit_when_unexpired():
    future = datetime.now(UTC) + timedelta(days=30)
    r = Resolver(
        probes=[EntityProbe("Trust", "slug")],
        history_probe=HistoryProbe("TrustHistory"),
        lookup_fn=lambda e, s: None,
        history_lookup_fn=lambda e, s: {
            "old_slug": "acme",
            "new_slug": "acme-corp",
            "expires_at": future,
        },
    )
    res = await r.lookup("acme")
    assert isinstance(res, HistoryHit)
    assert res.new_slug == "acme-corp"


async def test_lookup_returns_expired_history_hit_when_past_ttl():
    past = datetime.now(UTC) - timedelta(days=1)
    r = Resolver(
        probes=[EntityProbe("Trust", "slug")],
        history_probe=HistoryProbe("TrustHistory"),
        lookup_fn=lambda e, s: None,
        history_lookup_fn=lambda e, s: {
            "old_slug": "acme",
            "new_slug": "acme-corp",
            "expires_at": past,
        },
    )
    res = await r.lookup("acme")
    assert isinstance(res, ExpiredHistoryHit)


async def test_lookup_accepts_iso_string_expires_at():
    """Repository may return expires_at as an ISO string; resolver normalises."""
    future_iso = (datetime.now(UTC) + timedelta(days=7)).isoformat()
    r = Resolver(
        probes=[EntityProbe("Trust", "slug")],
        history_probe=HistoryProbe("TrustHistory"),
        lookup_fn=lambda e, s: None,
        history_lookup_fn=lambda e, s: {
            "old_slug": "acme",
            "new_slug": "acme-corp",
            "expires_at": future_iso,
        },
    )
    assert isinstance(await r.lookup("acme"), HistoryHit)


# ---------------------------------------------------------------------------
# ADR-0037 Phase 5 — ancestor-chain walk (ResolvedTenant.ancestor_ids)
# ---------------------------------------------------------------------------


async def test_walk_populates_ancestor_ids_two_level():
    """A host that resolves to a child kind carries its root id in ancestor_ids."""
    trust_id, school_id = _id(1), _id(2)
    slug_rows = {("School", "westwood"): {"id": school_id, "slug": "westwood", "trust": trust_id}}
    by_id = {("Trust", str(trust_id)): {"id": trust_id, "slug": "acme"}}
    r = Resolver(
        probes=[EntityProbe("School", "slug")],
        history_probe=None,
        lookup_fn=lambda e, s: slug_rows.get((e, s)),
        parent_map={"School": ("trust", "Trust")},
        fetch_by_id_fn=lambda e, i: by_id.get((e, str(i))),
    )
    res = await r.lookup("westwood")
    assert isinstance(res, ResolvedTenant)
    assert res.kind == "School"
    assert res.id == school_id
    assert res.ancestor_ids == (str(trust_id),)


async def test_walk_three_level_chain():
    region_id, trust_id, school_id = _id(10), _id(11), _id(12)
    slug_rows = {
        ("School", "ws"): {"id": school_id, "slug": "ws", "trust": trust_id},
    }
    by_id = {
        ("Trust", str(trust_id)): {"id": trust_id, "region": region_id},
        ("Region", str(region_id)): {"id": region_id},
    }
    r = Resolver(
        probes=[EntityProbe("School", "slug")],
        history_probe=None,
        lookup_fn=lambda e, s: slug_rows.get((e, s)),
        parent_map={"School": ("trust", "Trust"), "Trust": ("region", "Region")},
        fetch_by_id_fn=lambda e, i: by_id.get((e, str(i))),
    )
    res = await r.lookup("ws")
    assert res.ancestor_ids == (str(trust_id), str(region_id))  # root last


async def test_no_parent_map_means_flat_no_ancestors():
    rows = {("Org", "acme"): {"id": _id(1), "slug": "acme", "trust": _id(9)}}
    r = Resolver(
        probes=[EntityProbe("Org", "slug")],
        history_probe=None,
        lookup_fn=lambda e, s: rows.get((e, s)),
    )
    res = await r.lookup("acme")
    assert res.ancestor_ids == ()


async def test_null_parent_fk_truncates_chain():
    rows = {("School", "ws"): {"id": _id(2), "slug": "ws", "trust": None}}
    r = Resolver(
        probes=[EntityProbe("School", "slug")],
        history_probe=None,
        lookup_fn=lambda e, s: rows.get((e, s)),
        parent_map={"School": ("trust", "Trust")},
        fetch_by_id_fn=lambda e, i: None,
    )
    res = await r.lookup("ws")
    assert res.ancestor_ids == ()  # NULL parent → no ancestors (fail-safe narrow)


async def test_missing_parent_row_records_id_then_stops():
    """If the parent FK is set but the parent row is gone, the id is still recorded
    (reachability stays correct) and the walk stops."""
    trust_id, school_id = _id(1), _id(2)
    slug_rows = {("School", "ws"): {"id": school_id, "slug": "ws", "trust": trust_id}}
    r = Resolver(
        probes=[EntityProbe("School", "slug")],
        history_probe=None,
        lookup_fn=lambda e, s: slug_rows.get((e, s)),
        parent_map={"School": ("trust", "Trust"), "Trust": ("region", "Region")},
        fetch_by_id_fn=lambda e, i: None,  # parent row not found
    )
    res = await r.lookup("ws")
    assert res.ancestor_ids == (str(trust_id),)
