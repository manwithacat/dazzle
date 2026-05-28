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


def test_lookup_returns_first_matching_entity():
    rows = {("Trust", "acme"): {"id": _id(1), "slug": "acme", "name": "Acme"}}
    r = Resolver(
        probes=[EntityProbe("Trust", "slug"), EntityProbe("School", "slug")],
        history_probe=None,
        lookup_fn=lambda e, s: rows.get((e, s)),
    )
    res = r.lookup("acme")
    assert isinstance(res, ResolvedTenant)
    assert res.kind == "Trust"
    assert res.id == _id(1)


def test_lookup_falls_through_to_second_entity():
    rows = {
        ("School", "westwood"): {"id": _id(2), "slug": "westwood", "name": "Westwood"},
    }
    r = Resolver(
        probes=[EntityProbe("Trust", "slug"), EntityProbe("School", "slug")],
        history_probe=None,
        lookup_fn=lambda e, s: rows.get((e, s)),
    )
    res = r.lookup("westwood")
    assert isinstance(res, ResolvedTenant)
    assert res.kind == "School"


def test_lookup_returns_none_when_no_match_and_no_history():
    r = Resolver(
        probes=[EntityProbe("Trust", "slug")],
        history_probe=None,
        lookup_fn=lambda e, s: None,
    )
    assert r.lookup("missing") is None


def test_lookup_returns_history_hit_when_unexpired():
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
    res = r.lookup("acme")
    assert isinstance(res, HistoryHit)
    assert res.new_slug == "acme-corp"


def test_lookup_returns_expired_history_hit_when_past_ttl():
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
    res = r.lookup("acme")
    assert isinstance(res, ExpiredHistoryHit)


def test_lookup_accepts_iso_string_expires_at():
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
    assert isinstance(r.lookup("acme"), HistoryHit)
