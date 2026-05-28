"""Tests for the public dazzle.tenant.bust API (#1289 slice 6)."""

from __future__ import annotations

import dazzle.tenant as t
from dazzle.back.runtime.tenant.cache import TenantCache


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
