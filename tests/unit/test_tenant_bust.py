"""Tests for the public dazzle.tenant.bust API (#1289 slice 6).

Covers the public ``bust(slug)`` callable plus the slug-field registry
that ``Repository.update`` consults for the auto-bust hook
(#1289 follow-up).
"""

from __future__ import annotations

from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

import dazzle.tenant as t
from dazzle.http.runtime.repository import Repository
from dazzle.http.runtime.tenant.cache import TenantCache
from dazzle.tenant.cache_registry import (
    _register_slug_field,
    slug_field_for,
)


def test_public_bust_clears_every_registered_cache():
    """Calling bust(slug) removes the slug from each registered cache."""
    t._clear_registry()
    cache_a = TenantCache(max_entries=4, ttl_seconds=60)
    cache_b = TenantCache(max_entries=4, ttl_seconds=60)
    cache_a.set("acme", {"id": 1})
    cache_b.set("acme", {"id": 2})

    t._register_cache(cache_a)
    t._register_cache(cache_b)

    t.bust("acme")

    assert cache_a.get("acme") is None
    assert cache_b.get("acme") is None


def test_public_bust_is_noop_when_no_caches_registered():
    t._clear_registry()
    t.bust("never-registered")  # must not raise


def test_public_bust_is_noop_on_unknown_slug():
    t._clear_registry()
    cache = TenantCache(max_entries=4, ttl_seconds=60)
    cache.set("acme", {"id": 1})
    t._register_cache(cache)

    t.bust("not-this-one")

    assert cache.get("acme") == {"id": 1}


# --- slug-field registry ----------------------------------------------------


def test_slug_field_registry_round_trip():
    t._clear_registry()
    _register_slug_field("Trust", "slug")
    assert slug_field_for("Trust") == "slug"
    assert slug_field_for("UnregisteredEntity") is None


def test_clear_registry_drops_slug_fields():
    _register_slug_field("Trust", "slug")
    t._clear_registry()
    assert slug_field_for("Trust") is None


# --- Repository.update auto-bust hook ---------------------------------------


class _StubCursor:
    rowcount = 1

    def execute(self, *_args, **_kwargs) -> None:  # type: ignore[no-untyped-def]
        return None


class _StubConn:
    def cursor(self) -> _StubCursor:
        return _StubCursor()


class _StubDB:
    placeholder = "%s"

    @contextmanager
    def connection(self):
        yield _StubConn()


def _stub_repo(*, table: str) -> Repository:
    """Build a Repository skeleton that has only what update() needs:
    a placeholder DB layer, a mocked read(), and a table name. Skips
    the heavy entity-spec / model-class wiring."""
    repo = Repository.__new__(Repository)
    repo.db = _StubDB()
    repo.table_name = table
    repo._field_types = {}
    repo._computed_fields = []
    repo._metrics = None
    repo._relation_loader = None
    repo._subtype_join_sql = None
    repo._subtype_extra_cols = []
    repo.entity_spec = SimpleNamespace(name=table)
    return repo


@pytest.mark.asyncio
async def test_auto_bust_fires_on_slug_change(monkeypatch):
    t._clear_registry()
    _register_slug_field("Trust", "slug")

    busted: list[str] = []
    monkeypatch.setattr(
        "dazzle.tenant.cache_registry.bust",
        lambda slug: busted.append(slug),
    )

    from uuid import uuid4

    repo = _stub_repo(table="Trust")
    # Pre-update read returns "old-slug"; post-update read returns the new row.
    repo.read = AsyncMock(side_effect=[{"slug": "old-slug"}, {"slug": "new-slug"}])  # type: ignore[method-assign]

    result = await repo.update(uuid4(), {"slug": "new-slug"})

    assert result == {"slug": "new-slug"}
    assert busted == ["old-slug", "new-slug"]


@pytest.mark.asyncio
async def test_auto_bust_is_silent_when_slug_unchanged(monkeypatch):
    t._clear_registry()
    _register_slug_field("Trust", "slug")

    busted: list[str] = []
    monkeypatch.setattr(
        "dazzle.tenant.cache_registry.bust",
        lambda slug: busted.append(slug),
    )

    from uuid import uuid4

    repo = _stub_repo(table="Trust")
    repo.read = AsyncMock(side_effect=[{"slug": "same-slug"}, {"slug": "same-slug"}])  # type: ignore[method-assign]

    await repo.update(uuid4(), {"slug": "same-slug"})

    assert busted == []


@pytest.mark.asyncio
async def test_auto_bust_skipped_when_slug_field_not_in_update(monkeypatch):
    t._clear_registry()
    _register_slug_field("Trust", "slug")

    busted: list[str] = []
    monkeypatch.setattr(
        "dazzle.tenant.cache_registry.bust",
        lambda slug: busted.append(slug),
    )

    from uuid import uuid4

    repo = _stub_repo(table="Trust")
    repo.read = AsyncMock(return_value={"slug": "untouched", "name": "Acme Trust"})  # type: ignore[method-assign]

    await repo.update(uuid4(), {"name": "Renamed Trust"})

    assert busted == []
    # The pre-update read should NOT have fired — slug_field isn't in
    # the update payload, so the hook short-circuits.
    assert repo.read.await_count == 1  # only the post-update read


@pytest.mark.asyncio
async def test_no_bust_on_non_tenant_host_entity(monkeypatch):
    t._clear_registry()
    # No _register_slug_field call — this entity has no tenant_host:.

    busted: list[str] = []
    monkeypatch.setattr(
        "dazzle.tenant.cache_registry.bust",
        lambda slug: busted.append(slug),
    )

    from uuid import uuid4

    repo = _stub_repo(table="Article")
    repo.read = AsyncMock(return_value={"slug": "anything"})  # type: ignore[method-assign]

    await repo.update(uuid4(), {"slug": "new-slug"})

    assert busted == []
    # Only the post-update read — no pre-update read on non-tenant entities.
    assert repo.read.await_count == 1
