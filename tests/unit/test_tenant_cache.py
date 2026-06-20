"""Unit tests for TenantCache (#1289 slice 2)."""

from __future__ import annotations

import time

from dazzle.http.runtime.tenant.cache import NEGATIVE, TenantCache


def test_set_and_get_round_trip():
    cache = TenantCache(max_entries=4, ttl_seconds=60)
    cache.set("acme", {"id": 1})
    assert cache.get("acme") == {"id": 1}


def test_negative_sentinel_round_trip():
    cache = TenantCache(max_entries=4, ttl_seconds=60)
    cache.set("missing", NEGATIVE)
    assert cache.get("missing") is NEGATIVE


def test_miss_returns_none():
    cache = TenantCache(max_entries=4, ttl_seconds=60)
    assert cache.get("absent") is None


def test_ttl_expiry():
    cache = TenantCache(max_entries=4, ttl_seconds=0.05)
    cache.set("acme", {"id": 1})
    time.sleep(0.1)
    assert cache.get("acme") is None


def test_lru_eviction():
    cache = TenantCache(max_entries=2, ttl_seconds=60)
    cache.set("a", 1)
    cache.set("b", 2)
    cache.get("a")  # touch a so b is LRU
    cache.set("c", 3)  # evicts b
    assert cache.get("b") is None
    assert cache.get("a") == 1
    assert cache.get("c") == 3


def test_bust_removes_entry():
    cache = TenantCache(max_entries=4, ttl_seconds=60)
    cache.set("acme", {"id": 1})
    cache.bust("acme")
    assert cache.get("acme") is None


def test_bust_is_idempotent_on_missing_key():
    cache = TenantCache(max_entries=4, ttl_seconds=60)
    cache.bust("never-existed")  # must not raise
